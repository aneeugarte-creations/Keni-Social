"""Sugerir hashtags (etapa de producción, tras Redactar): propone hashtags para un CONTENIDO
que aún no los lleva, sin tocar el copy.

Los hashtags son GEMELOS en todas las redes de un contenido: se calculan UNA vez por contenido
(`publicacion_id`), NO por pieza, y se escriben idénticos en todas sus piezas. Así X e Instagram
nunca divergen. Cuando un contenido recién redactado NO tiene hashtags (`falta_hashtags`), esta
etapa ENCOLA un `claude -p` READ-ONLY que, a partir del copy + la voz de la marca, elige de la
`hashtags_biblioteca` de la marca los más relevantes al tema. El post-procesado ARMA la lista
final: los FIJOS de la marca (su firma: nombre/portal — van siempre, no los elige la IA porque no
dependen del tema) y los temáticos que propuso la IA, recortados a la cantidad típica; los temáticos
salen del pool de la marca y son relevantes al tema (no se rellena por frecuencia). Se persiste en
`pieza.hashtags_sugeridos` (JSON, cada tag con '#') de cada pieza gemela. El hashtag de la LÍNEA
editorial NO va aquí: se propone APARTE y en rojo (`pieza.hashtags_linea`, derivado de la etiqueta
de línea), y el gate `falta_hashtags` lo exige en el caption.

El humano tiene la última palabra: el feed muestra esa sugerencia en GRIS junto al copy para
aceptarla (se inyecta) o descartarla de un clic; nada se publica ni se reescribe solo. Gateado
por `KENI_PIPELINE_SUGERIR_HASHTAGS`.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from typing import Any

from keni_shared import marcas

from .. import config, hashtags_biblioteca, repos
from . import generar, jobspec

_log = logging.getLogger("keni_consola.sugerir_hashtags")

PROMPT_SUGERIR = "prompt/sugerir-hashtags"

# Estados de pieza donde `aplicar_sugerencia` ESCRIBE. La sugerencia se encadena al crear el copy
# (la pieza está en `borrador`); se incluye `en_revision` por si avanzó mientras el job de hashtags
# esperaba en la cola. `programado` queda FUERA a propósito: `falta_hashtags` es un estado
# obligatorio de resolver ANTES de programar, así que una pieza programada ya no debería necesitar
# sugerencia; `publicado` tampoco (no se reescribe lo que ya salió).
ESTADOS_SUGERIBLES = ("borrador", "en_revision")

# Un hashtag en el caption: saber si ya hay ALGUNO (gate de LANZAMIENTO de la sugerencia, que solo
# corre cuando el copy no trae ninguno). Distinto del gate de AVANCE (`piezas._falta_hashtags`), que
# además exige el hashtag de la línea: aquí solo nos importa si falta arrancar la propuesta.
_PAT_HASHTAG = re.compile(r"#\w+", re.UNICODE)

# Tope de candidatos que viajan en el prompt: la biblioteca está ordenada por frecuencia, así que
# los primeros son los más habituales. Acota el tamaño del prompt sin perder la cabeza de la lista.
_MAX_CANDIDATOS = 150

# Herramientas VETADAS: la etapa solo razona sobre texto y propone; no escribe, no navega, no
# toca el tablero. Mismo criterio READ-ONLY que la crítica IA.
_TOOLS_VETADAS: tuple[str, ...] = (
    "Write",
    "Edit",
    "MultiEdit",
    "NotebookEdit",
    "Bash",
    "WebFetch",
    "WebSearch",
    "mcp__keni-social__keni_crear_publicacion",
    "mcp__keni-social__keni_actualizar_publicacion",
    "mcp__keni-social__keni_enviar_a_revision",
    "mcp__keni-social__keni_aprobar",
    "mcp__keni-social__keni_rechazar",
)


def _endurecer() -> dict[str, Any]:
    """Run READ-ONLY y barato: cero tools, acota turnos y coste, y va con `hashtags_modelo`
    (haiku por defecto: elegir de una lista fija no necesita el modelo grande).

    `sin_tools=True` hace que el run vaya con `--tools ""` (no expone esquema de herramienta
    alguno → ahorro de contexto); la etapa solo razona sobre texto y propone hashtags.
    `disallowed_tools` se conserva como veto explícito de respaldo si se desactivara `sin_tools`.
    """
    return {
        "sin_tools": True,
        "disallowed_tools": list(_TOOLS_VETADAS),
        "max_turns": 8,
        "max_budget_usd": 2.0,
        "modelo": config.hashtags_modelo(),
    }


def falta_hashtags(pub: dict[str, Any]) -> bool:
    """True si el copy (caption) NO lleva ningún hashtag: gate de LANZAMIENTO de la sugerencia (solo
    se arranca para un copy que no trae ninguno). El gate de AVANCE de la pieza vive en
    `piezas._falta_hashtags` y es más estricto (exige también el hashtag de la línea)."""
    return not _PAT_HASHTAG.search(str(pub.get("contenido") or ""))


def _sugeridos_actuales(pub: dict[str, Any]) -> list[str]:
    """Lista ya persistida en `pieza.hashtags_sugeridos` (JSON). [] si vacía o ilegible."""
    crudo = pub.get("hashtags_sugeridos")
    if isinstance(crudo, (list, tuple)):
        return [str(x) for x in crudo]
    if isinstance(crudo, str) and crudo.strip():
        try:
            datos = json.loads(crudo)
        except (ValueError, TypeError):
            return []
        if isinstance(datos, list):
            return [str(x) for x in datos]
    return []


def _componer_prompt(
    *, copy: str, marca: str, redes: list[str], candidatos: list[str], cantidad: int
) -> str:
    """Renderiza `prompt/sugerir-hashtags` con el copy, las redes y la biblioteca de la marca."""
    from .. import libprompts
    from .. import redes as cat_redes

    cuerpo = libprompts.cuerpo_efectivo(PROMPT_SUGERIR) or libprompts.cuerpo_inicial(PROMPT_SUGERIR)
    lista = " ".join(f"#{c}" for c in candidatos[:_MAX_CANDIDATOS]) or "(la marca no tiene biblioteca)"
    nombres_red = ", ".join(cat_redes.nombre_por_id(r) or r for r in redes) or "sus redes"
    sust = {
        "{{MARCA}}": marcas.etiqueta_de(marca) or marca or "la marca",
        "{{REDES}}": nombres_red,
        "{{COPY}}": str(copy or "").strip() or "(sin copy)",
        "{{CANTIDAD}}": str(cantidad),
        "{{CANDIDATOS}}": lista,
    }
    for marcador, valor in sust.items():
        cuerpo = cuerpo.replace(marcador, valor)
    return cuerpo


def cantidad_contenido(marca: str, redes: list[str]) -> int:
    """CUÁNTOS hashtags sugerir para un CONTENIDO: el máximo entre sus redes (la sugerencia es
    gemela, así que una sola cantidad la gobierna). 0 si NINGUNA red de la marca usa hashtags."""
    return max((hashtags_biblioteca.cantidad_sugerida(marca, r) for r in redes), default=0)


def lanzar_para_contenido(publicacion_id: str, twins: list[dict[str, Any]]) -> dict[str, Any] | None:
    """ENCOLA UNA sugerencia de hashtags para un contenido (todas sus piezas gemelas). None si no aplica.

    `twins` son las piezas SUGERIBLES del contenido (borrador o en revisión, las mismas del
    barrido). No aplica si: el flag está OFF; ninguna pieza existe; el copy ya lleva hashtags
    (`falta_hashtags` False en todas); ya hay una sugerencia calculada en alguna; la marca no usa
    hashtags en ninguna red (`cantidad` 0); o la marca no tiene biblioteca. Idempotente por la
    clave `sugerir-hashtags:{publicacion_id}`.
    """
    if not twins:
        return None
    marca = str(twins[0].get("marca") or "")
    if not config.etapa_activa(config.ENV_PIPELINE_SUGERIR_HASHTAGS, marca):
        return None
    if not any(falta_hashtags(t) for t in twins):
        return None
    if any(_sugeridos_actuales(t) for t in twins):
        return None
    redes = sorted({str(t.get("red") or "") for t in twins if t.get("red")})
    cantidad = cantidad_contenido(marca, redes)
    if cantidad <= 0:
        return None
    candidatos = hashtags_biblioteca.candidatos(marca)
    if not candidatos:
        return None

    copy = next((str(t.get("contenido") or "") for t in twins if str(t.get("contenido") or "").strip()), "")
    procesar_spec = jobspec.construir_sugerir_hashtags(publicacion_id=publicacion_id)
    procesar = jobspec.reconstruir_procesar({"procesar": procesar_spec})
    prompt = _componer_prompt(copy=copy, marca=marca, redes=redes, candidatos=candidatos, cantidad=cantidad)
    return generar.lanzar(
        tipo="sugerir-hashtags",
        titulo=f"Keywords · {twins[0].get('titulo', '') or 'contenido'}",
        marca=marca,
        prompt=prompt,
        procesar=procesar,
        procesar_spec=procesar_spec,
        endurecer=_endurecer(),
        clave_idem=f"sugerir-hashtags:{publicacion_id}",
        publicacion_id=publicacion_id,
    )


# --------------------------------------------------------------------------- #
# Post-procesado (corre en el WORKER al terminar el job)                        #
# --------------------------------------------------------------------------- #


def _parsear_salida(salida: str) -> dict[str, Any]:
    """Extrae el objeto JSON de la salida de claude ({} si no es legible)."""
    if not salida:
        return {}
    texto = salida.strip()
    valla = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", texto, re.DOTALL)
    crudo = valla.group(1) if valla else None
    if crudo is None:
        ini = texto.find("{")
        fin = texto.rfind("}")
        crudo = texto[ini : fin + 1] if ini != -1 and fin > ini else None
    if not crudo:
        return {}
    try:
        datos = json.loads(crudo)
    except (ValueError, TypeError):
        return {}
    return datos if isinstance(datos, dict) else {}


def _parsear_hashtags(salida: str) -> list[str]:
    """Extrae `hashtags` del JSON de la salida de claude. [] si no es legible."""
    lista = _parsear_salida(salida).get("hashtags")
    return [str(x) for x in lista] if isinstance(lista, list) else []


def _parsear_imagen_clave(salida: str) -> str:
    """Extrae `imagen_clave` (keyword para buscar foto) del JSON de la salida. "" si no hay."""
    valor = _parsear_salida(salida).get("imagen_clave")
    return str(valor).strip()[:120] if isinstance(valor, str) else ""


def _normalizar(tag: str) -> str:
    """Normaliza un hashtag propuesto a un único '#' + cuerpo en minúscula. "" si no queda nada."""
    cuerpo = str(tag or "").strip().lstrip("#").strip().lower()
    return f"#{cuerpo}" if cuerpo else ""


def _plegar(cuerpo: str) -> str:
    """Pliega un cuerpo de hashtag para comparar: sin acentos y en minúscula. Así un tag que la IA
    propone sin tilde ("futbolconcausa") casa con el del pool ("fútbolconcausa")."""
    base = unicodedata.normalize("NFKD", str(cuerpo or "").strip().lstrip("#").strip().lower())
    return "".join(c for c in base if not unicodedata.combining(c))


def ensamblar(propuestos: list[str], *, marca: str, cantidad: int) -> list[str]:
    """ARMA la sugerencia GRIS del contenido, hasta `cantidad`:

      1. FIJOS de la marca (su firma: nombre/portal) — no dependen del tema; se reserva al menos
         un hueco para algo temático cuando hay sitio.
      2. Temáticos que propuso la IA, en su orden de relevancia (los de fuera del pool se descartan).

    Cada propuesto se casa con el pool PLEGANDO acentos (la IA suele devolver el tag sin tilde) y se
    guarda con la ORTOGRAFÍA del pool: así no se pierde un tag relevante por un diacrítico (era el
    bug de "salían 2 de 5"). Dedup por el cuerpo plegado. `cantidad` es un TOPE, no un cupo a llenar:
    NO se rellena con los hashtags más usados de la marca, para que una pieza off-topic no arrastre
    los tags genéricos que no encajan con su tema. El hashtag de la LÍNEA NO va aquí: se propone
    aparte (es la firma de la sección, no un temático del pool).
    """
    if cantidad <= 0:
        return []
    pool = hashtags_biblioteca.candidatos(marca)
    # Plegado (sin acentos) -> ortografía canónica del pool: recupera el tag aunque la IA lo
    # proponga sin tilde y lo emite tal y como la marca lo escribe de verdad.
    canon: dict[str, str] = {}
    for cuerpo in pool:
        canon.setdefault(_plegar(cuerpo), cuerpo)
    salida: list[str] = []
    vistos: set[str] = set()

    def add(crudo: str) -> None:
        plegado = _plegar(crudo)
        canonico = canon.get(plegado)
        if not canonico or plegado in vistos or len(salida) >= cantidad:
            return
        vistos.add(plegado)
        salida.append(f"#{canonico}")

    fijos = hashtags_biblioteca.fijos(marca)
    reserva_tematica = 1 if cantidad >= 2 else 0
    for cuerpo in fijos[: max(0, cantidad - reserva_tematica)]:
        add(cuerpo)
    for tag in propuestos:
        add(tag)
    return salida


def aplicar_sugerencia(
    publicacion_id: str, propuestos: list[str], imagen_clave: str = ""
) -> list[str]:
    """Arma la sugerencia del contenido y la escribe IDÉNTICA en todas sus piezas SUGERIBLES (gemelas).

    Los hashtags son gemelos entre redes: se calcula una vez (cantidad = máximo entre las redes del
    contenido) y se persiste el mismo JSON en cada pieza en `ESTADOS_SUGERIBLES` (borrador o en
    revisión: una pieza pudo avanzar sola a revisión mientras el job corría). La `imagen_clave`
    (keyword para buscar foto de stock) viaja en el mismo paso, también gemela. Devuelve la lista
    de hashtags guardada ([] si no toca).
    """
    filas = repos.listar_piezas_fila(publicacion_id=publicacion_id) or []
    elegibles = [f for f in filas if str(f.get("estado") or "") in ESTADOS_SUGERIBLES]
    if not elegibles:
        return []
    marca = str(elegibles[0].get("marca") or "")
    redes = sorted({str(f.get("red") or "") for f in elegibles if f.get("red")})
    cantidad = cantidad_contenido(marca, redes)
    lista = ensamblar(propuestos, marca=marca, cantidad=cantidad)
    payload = json.dumps(lista, ensure_ascii=False)
    campos: dict[str, Any] = {"hashtags_sugeridos": payload}
    # Solo escribe `imagen_clave` si la IA dio una (no piso una previa con vacío).
    if imagen_clave.strip():
        campos["imagen_clave"] = imagen_clave.strip()[:120]
    for f in elegibles:
        repos.actualizar_pieza(str(f.get("id") or ""), campos)
    return lista


def construir_procesar_sugerir_hashtags(*, publicacion_id: str):  # noqa: ANN201
    """Devuelve el callback `procesar(salida, metricas) -> dict` del job (corre en el worker)."""

    def procesar(salida: str, _metricas: object) -> dict[str, object]:
        datos = _parsear_salida(salida)
        propuestos = [str(x) for x in datos.get("hashtags", [])] if isinstance(datos.get("hashtags"), list) else []
        imagen_clave = _parsear_imagen_clave(salida)
        guardados = aplicar_sugerencia(publicacion_id, propuestos, imagen_clave)
        return {"sugerir_hashtags": {"hashtags": guardados, "imagen_clave": imagen_clave}}

    return procesar
