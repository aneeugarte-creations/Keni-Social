"""Sugerir hashtags (etapa de producción, tras Redactar): propone hashtags para un CONTENIDO
que aún no los lleva, sin tocar el copy.

Los hashtags son GEMELOS en todas las redes de un contenido: se calculan UNA vez por contenido
(`publicacion_id`), NO por pieza, y se escriben idénticos en todas sus piezas. Así X e Instagram
nunca divergen. Cuando un contenido recién redactado NO tiene hashtags (`falta_hashtags`), esta
etapa ENCOLA un `claude -p` READ-ONLY que, a partir del copy + la voz de la marca, elige de la
`hashtags_biblioteca` de la marca los más relevantes al tema. El post-procesado ARMA la lista
final: los FIJOS de la marca (su firma: nombre/portal — van siempre, no los elige la IA porque no
dependen del tema), los temáticos que propuso la IA, y relleno por frecuencia hasta la cantidad
típica; todo del pool de la marca. Se persiste en `pieza.hashtags_sugeridos` (JSON, cada tag con
'#') de cada pieza gemela.

El humano tiene la última palabra: el feed muestra esa sugerencia en GRIS junto al copy para
aceptarla (se inyecta) o descartarla de un clic; nada se publica ni se reescribe solo. Gateado
por `KENI_PIPELINE_SUGERIR_HASHTAGS`.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from .. import config, hashtags_biblioteca, marcas, repos
from . import generar, jobspec

_log = logging.getLogger("keni_consola.sugerir_hashtags")

PROMPT_SUGERIR = "prompt/sugerir-hashtags"

# Estados de pieza donde `aplicar_sugerencia` ESCRIBE. La sugerencia se encadena al crear el copy
# (la pieza está en `borrador`); se incluye `en_revision` por si avanzó mientras el job de hashtags
# esperaba en la cola. `programado` queda FUERA a propósito: `falta_hashtags` es un estado
# obligatorio de resolver ANTES de programar, así que una pieza programada ya no debería necesitar
# sugerencia; `publicado` tampoco (no se reescribe lo que ya salió).
ESTADOS_SUGERIBLES = ("borrador", "en_revision")

# Un hashtag en el caption: MISMO patrón que `piezas._falta_hashtags` (saber si ya hay alguno).
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
    """Run READ-ONLY y barato: veta escritura/red, acota turnos y coste (es solo elegir hashtags)."""
    return {
        "disallowed_tools": list(_TOOLS_VETADAS),
        "max_turns": 8,
        "max_budget_usd": 2.0,
    }


def falta_hashtags(pub: dict[str, Any]) -> bool:
    """True si el copy (caption) NO lleva ningún hashtag. Mismo criterio que el feed."""
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


def _contexto_editorial(marca: str) -> str:
    """Voz/normas de la marca como contexto (best-effort, "" si no hay). Reusa `adjuntos_copy`."""
    try:
        docs = generar.adjuntos_copy(marca)
    except Exception:  # noqa: BLE001 -- el contexto editorial es opcional; nunca rompe el lanzamiento
        return ""
    cuerpos = [d.cuerpo.strip() for d in docs if getattr(d, "cuerpo", "").strip()]
    if not cuerpos:
        return ""
    return "\n\n## Contexto editorial de la marca\n\n" + "\n\n---\n\n".join(cuerpos)


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
    return cuerpo + _contexto_editorial(marca)


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
    if not config.sugerir_hashtags_activo() or not twins:
        return None
    if not any(falta_hashtags(t) for t in twins):
        return None
    if any(_sugeridos_actuales(t) for t in twins):
        return None
    marca = str(twins[0].get("marca") or "")
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
        titulo=f"Sugerir hashtags · {twins[0].get('titulo', '') or 'contenido'}",
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


def _parsear_hashtags(salida: str) -> list[str]:
    """Extrae `hashtags` del JSON de la salida de claude. [] si no es legible."""
    if not salida:
        return []
    texto = salida.strip()
    valla = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", texto, re.DOTALL)
    crudo = valla.group(1) if valla else None
    if crudo is None:
        ini = texto.find("{")
        fin = texto.rfind("}")
        crudo = texto[ini : fin + 1] if ini != -1 and fin > ini else None
    if not crudo:
        return []
    try:
        datos = json.loads(crudo)
    except (ValueError, TypeError):
        return []
    if not isinstance(datos, dict):
        return []
    lista = datos.get("hashtags")
    return [str(x) for x in lista] if isinstance(lista, list) else []


def _normalizar(tag: str) -> str:
    """Normaliza un hashtag propuesto a un único '#' + cuerpo en minúscula. "" si no queda nada."""
    cuerpo = str(tag or "").strip().lstrip("#").strip().lower()
    return f"#{cuerpo}" if cuerpo else ""


def ensamblar(propuestos: list[str], *, marca: str, cantidad: int) -> list[str]:
    """ARMA la sugerencia final del contenido, hasta `cantidad`, toda del pool de la marca:

      1. FIJOS de la marca (su firma: nombre/portal) — SIEMPRE, no dependen del tema; se reserva
         al menos un hueco para algo temático cuando hay sitio.
      2. Temáticos que propuso la IA, en su orden de relevancia (los de fuera del pool se descartan).
      3. Relleno por frecuencia (los más usados de la marca) hasta llegar a la cantidad típica.

    Dedup por el cuerpo sin '#' en minúscula. Garantiza que la firma esté y que el cupo se llene
    aunque la IA devuelva poco o nada usable (era el bug: copy sin hashtags y sugerencia vacía).
    """
    if cantidad <= 0:
        return []
    pool = hashtags_biblioteca.candidatos(marca)
    permitidos = set(pool)
    salida: list[str] = []
    vistos: set[str] = set()

    def add(crudo: str) -> None:
        cuerpo = str(crudo or "").strip().lstrip("#").strip().lower()
        if not cuerpo or cuerpo in vistos or cuerpo not in permitidos or len(salida) >= cantidad:
            return
        vistos.add(cuerpo)
        salida.append(f"#{cuerpo}")

    fijos = hashtags_biblioteca.fijos(marca)
    reserva_tematica = 1 if cantidad >= 2 else 0
    for cuerpo in fijos[: max(0, cantidad - reserva_tematica)]:
        add(cuerpo)
    for tag in propuestos:
        add(tag)
    for cuerpo in pool:
        add(cuerpo)
    return salida


def aplicar_sugerencia(publicacion_id: str, propuestos: list[str]) -> list[str]:
    """Arma la sugerencia del contenido y la escribe IDÉNTICA en todas sus piezas SUGERIBLES (gemelas).

    Los hashtags son gemelos entre redes: se calcula una vez (cantidad = máximo entre las redes del
    contenido) y se persiste el mismo JSON en cada pieza en `ESTADOS_SUGERIBLES` (borrador o en
    revisión: una pieza pudo avanzar sola a revisión mientras el job corría). Devuelve la lista
    guardada ([] si no toca).
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
    for f in elegibles:
        repos.actualizar_pieza(str(f.get("id") or ""), {"hashtags_sugeridos": payload})
    return lista


def construir_procesar_sugerir_hashtags(*, publicacion_id: str):  # noqa: ANN201
    """Devuelve el callback `procesar(salida, metricas) -> dict` del job (corre en el worker)."""

    def procesar(salida: str, _metricas: object) -> dict[str, object]:
        propuestos = _parsear_hashtags(salida)
        guardados = aplicar_sugerencia(publicacion_id, propuestos)
        return {"sugerir_hashtags": {"hashtags": guardados}}

    return procesar
