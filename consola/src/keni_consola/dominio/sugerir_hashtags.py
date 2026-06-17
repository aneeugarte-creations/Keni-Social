"""Sugerir hashtags (etapa de producción, tras Redactar): propone hashtags para una pieza
que aún no los lleva, sin tocar el copy.

Cuando una pieza recién redactada NO tiene hashtags (`falta_hashtags`), esta etapa ENCOLA un
`claude -p` READ-ONLY que, a partir del copy + la voz de la marca, elige los hashtags más
relevantes SOLO de la `hashtags_biblioteca` de la marca (los que de verdad usa en redes). El
post-procesado filtra la salida contra esa misma biblioteca, la acota a la cantidad típica de la
red (`cantidad_sugerida`) y la persiste en `pieza.hashtags_sugeridos` (JSON, cada tag con '#').

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
    *, pub: dict[str, Any], marca: str, red: str, candidatos: list[str], cantidad: int
) -> str:
    """Renderiza `prompt/sugerir-hashtags` con el copy, la red y la biblioteca de la marca."""
    from .. import libprompts

    cuerpo = libprompts.cuerpo_efectivo(PROMPT_SUGERIR) or libprompts.cuerpo_inicial(PROMPT_SUGERIR)
    lista = " ".join(f"#{c}" for c in candidatos[:_MAX_CANDIDATOS]) or "(la marca no tiene biblioteca)"
    sust = {
        "{{MARCA}}": marcas.etiqueta_de(marca) or marca or "la marca",
        "{{RED}}": str(red or "la red"),
        "{{COPY}}": str(pub.get("contenido") or "").strip() or "(sin copy)",
        "{{CANTIDAD}}": str(cantidad),
        "{{CANDIDATOS}}": lista,
    }
    for marcador, valor in sust.items():
        cuerpo = cuerpo.replace(marcador, valor)
    return cuerpo + _contexto_editorial(marca)


def lanzar_para_publicacion(pieza_id: str) -> dict[str, Any] | None:
    """ENCOLA la sugerencia de hashtags de una pieza si toca. None si no aplica.

    No aplica si: el flag está OFF; la pieza no existe; ya lleva hashtags (`falta_hashtags`
    False); la red de la marca no usa hashtags (`cantidad_sugerida` 0); o ya tiene una sugerencia
    calculada. Idempotente por la clave `sugerir-hashtags:{id}` (no relanza con uno en curso).
    """
    if not config.sugerir_hashtags_activo():
        return None
    pub = repos.obtener_pieza(pieza_id)
    if pub is None:
        return None
    if not falta_hashtags(pub):
        return None
    if _sugeridos_actuales(pub):
        return None
    marca = str(pub.get("marca") or "")
    red = str(pub.get("red") or "")
    cantidad = hashtags_biblioteca.cantidad_sugerida(marca, red)
    if cantidad <= 0:
        return None
    candidatos = hashtags_biblioteca.candidatos(marca)
    if not candidatos:
        return None

    procesar_spec = jobspec.construir_sugerir_hashtags(pieza_id=pieza_id)
    procesar = jobspec.reconstruir_procesar({"procesar": procesar_spec})
    prompt = _componer_prompt(pub=pub, marca=marca, red=red, candidatos=candidatos, cantidad=cantidad)
    plat = repos.obtener_pieza_fila(pieza_id) or {}
    return generar.lanzar(
        tipo="sugerir-hashtags",
        titulo=f"Sugerir hashtags · {pub.get('titulo', '') or 'pieza'}",
        marca=marca,
        prompt=prompt,
        procesar=procesar,
        procesar_spec=procesar_spec,
        endurecer=_endurecer(),
        clave_idem=f"sugerir-hashtags:{pieza_id}",
        publicacion_id=str(plat.get("publicacion_id", "") or ""),
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


def depurar(propuestos: list[str], *, marca: str, cantidad: int) -> list[str]:
    """Filtra los hashtags propuestos a los que están en la biblioteca, dedup y acota a `cantidad`.

    La biblioteca es la FUENTE de verdad: un hashtag que la IA invente (fuera de la lista) se
    descarta. Compara por el cuerpo sin '#' en minúscula. Preserva el orden de la propuesta.
    """
    permitidos = set(hashtags_biblioteca.candidatos(marca))
    salida: list[str] = []
    vistos: set[str] = set()
    for tag in propuestos:
        norm = _normalizar(tag)
        cuerpo = norm.lstrip("#")
        if not cuerpo or cuerpo in vistos or cuerpo not in permitidos:
            continue
        vistos.add(cuerpo)
        salida.append(norm)
        if len(salida) >= cantidad:
            break
    return salida


def aplicar_sugerencia(pieza_id: str, propuestos: list[str]) -> list[str]:
    """Persiste la sugerencia depurada en `pieza.hashtags_sugeridos`. Devuelve la lista guardada."""
    pub = repos.obtener_pieza(pieza_id)
    if pub is None:
        return []
    marca = str(pub.get("marca") or "")
    red = str(pub.get("red") or "")
    cantidad = hashtags_biblioteca.cantidad_sugerida(marca, red)
    lista = depurar(propuestos, marca=marca, cantidad=cantidad) if cantidad > 0 else []
    repos.actualizar_pieza(pieza_id, {"hashtags_sugeridos": json.dumps(lista, ensure_ascii=False)})
    return lista


def construir_procesar_sugerir_hashtags(*, pieza_id: str):  # noqa: ANN201
    """Devuelve el callback `procesar(salida, metricas) -> dict` del job (corre en el worker)."""

    def procesar(salida: str, _metricas: object) -> dict[str, object]:
        propuestos = _parsear_hashtags(salida)
        guardados = aplicar_sugerencia(pieza_id, propuestos)
        return {"sugerir_hashtags": {"hashtags": guardados}}

    return procesar
