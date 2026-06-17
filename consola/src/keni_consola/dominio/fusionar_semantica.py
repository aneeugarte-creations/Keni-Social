"""Fusionar SEMÁNTICAMENTE historias del MISMO evento con claude (Fase 2b).

El agrupar léxico (agrupar.asignar) une variantes claras del MISMO titular (url canónica o
título fuzzy ≥ umbral), pero NO une coberturas del mismo evento con titulares distintos
("Zelensky responde" vs "Rusia lanza misiles"). Esta capa, OPCIONAL y gateada, le pasa a Haiku el
lote de historias recientes de una marca y le pide AGRUPAR las que son del mismo evento; el daemon
fusiona cada grupo en una sola historia (n_fuentes real → mejor señal de tendencia/corroboración).

Este módulo es NEUTRO y PURO de I/O: solo construye el prompt, llama al ejecutor (inyectable en
tests) y parsea los grupos. Fusionar de verdad (reasignar items + borrar absorbidos + recalcular)
lo hace el daemon (`recolectar_daemon`), que es quien tiene los repos. BEST-EFFORT: ante cualquier
fallo devuelve [] (no se fusiona nada).

DOS PASADAS (fusionar por error es caro: infla la corroboración y puede auto-producir una
pieza con fuentes que no hablan de lo mismo — pasó con «Shakira en la inauguración» fusionada
con «alerta de seguridad de la embajada» por compartir «Mundial»):
  1. PROPUESTA sobre el lote completo (prompt `fusionar`).
  2. VERIFICACIÓN por grupo propuesto (prompt `fusionar-verificar`): re-pregunta con SOLO
     esas historias y el grupo puede salir confirmado, PARTIDO en subgrupos o descartado.
     Mismo contrato JSON; cualquier fallo descarta el grupo (conservador).
El modelo es el de `config.fusion_modelo()` (def sonnet: pocas llamadas, juicio fino).
"""

from __future__ import annotations

import json
import logging
import tempfile
from collections.abc import Callable
from typing import Any

from . import json_llm

_log = logging.getLogger("keni_consola.dominio.fusionar_semantica")

Ejecutor = Callable[[str, str], str]

# Cotas de tamaño del prompt.
_MAX_CLUSTERS = 40           # historias por lote que se mandan a Haiku
_MAX_CHARS_ITEM = 240        # recorte de titulo+resumen por historia


# La plantilla vive en la Prompts de Texto como prompt EDITABLE (pestaña «Prompts»). La lista
# JSON de historias se inserta en `{{HISTORIAS}}`. Si el store fallara, la red es la INICIAL del
# paquete (fuente única, sin texto duplicado aquí).
_PROMPT_ID = "prompt/fusionar"
_PROMPT_VERIFICACION_ID = "prompt/fusionar-verificar"
_PROMPT_MACRO_ID = "prompt/fusionar-macroevento"
_MARCA_HISTORIAS = "{{HISTORIAS}}"


def _plantilla(prompt_id: str = _PROMPT_ID) -> str:
    """Cuerpo EFECTIVO de la plantilla (store del equipo > inicial del paquete)."""
    from .. import libprompts

    try:
        cuerpo = (libprompts.cuerpo_efectivo(prompt_id) or "").strip()
    except Exception:  # noqa: BLE001 -- nunca dejar Fusionar sin prompt por un fallo de lectura
        cuerpo = ""
    return cuerpo or libprompts.cuerpo_inicial(prompt_id).strip()


def _construir_prompt(payload_json: str, prompt_id: str = _PROMPT_ID) -> str:
    """Prompt de agrupación/verificación (plantilla editable + lista JSON de historias)."""
    plantilla = _plantilla(prompt_id)
    if _MARCA_HISTORIAS in plantilla:
        return plantilla.replace(_MARCA_HISTORIAS, payload_json)
    return f"{plantilla}\n\nHistorias:\n{payload_json}"


def _extraer_grupos(texto: str) -> list[list[str]]:
    """Extrae los grupos de ids del texto de Haiku (extractor compartido). [] si falla."""
    bruto = json_llm.extraer_lista(texto, claves=("grupos",))
    if bruto is None:
        return []
    grupos: list[list[str]] = []
    for g in bruto:
        if isinstance(g, list):
            ids = [str(x) for x in g if isinstance(x, (str, int))]
            if len(ids) >= 2:
                grupos.append(ids)
    return grupos


def proponer_fusiones(
    clusters: list[dict[str, Any]],
    *,
    ejecutor: Ejecutor | None = None,
    al_ejecutar: Callable[[str, str], None] | None = None,
) -> list[list[str]]:
    """Propone grupos de ids de historias del MISMO evento (Haiku). PURO de repos.

    `clusters`: dicts con al menos `{id, titulo, resumen}`. Devuelve grupos VÁLIDOS y DISJUNTOS
    (ids del input, sin repetir entre grupos, tamaño ≥ 2). [] ante <2 historias o cualquier fallo.

    `al_ejecutar(prompt, salida)`: callback OPCIONAL que se invoca con el PROMPT y la SALIDA reales
    de Haiku tras la llamada (antes de parsear). El daemon lo usa para registrar la actividad IA de
    Fusionar con el Haiku real; un fallo del callback no afecta a Fusionar (es observabilidad).
    """
    validos = [c for c in clusters if (c.get("id") and (c.get("titulo") or "").strip())][:_MAX_CLUSTERS]
    if len(validos) < 2:
        return []
    ids_validos = {str(c["id"]) for c in validos}

    payload = [
        {
            "id": str(c["id"]),
            "titulo": json_llm.truncar_avisando(
                str(c.get("titulo", "")).strip(), _MAX_CHARS_ITEM,
                campo=f"titulo de {c['id']}", log=_log,
            )[0],
            "resumen": json_llm.truncar_avisando(
                str(c.get("resumen", "") or "").strip(), _MAX_CHARS_ITEM,
                campo=f"resumen de {c['id']}", log=_log,
            )[0],
        }
        for c in validos
    ]
    correr = ejecutor or _ejecutar_haiku
    prompt = _construir_prompt(json.dumps(payload, ensure_ascii=False))
    try:
        with tempfile.TemporaryDirectory(prefix="keni-fusion-") as carpeta:
            salida = correr(prompt, carpeta)
    except Exception as e:  # noqa: BLE001 -- best-effort: cualquier fallo -> no fusiona nada
        _log.warning("fusionar_semantica: falló la llamada a Haiku: %s", e)
        return []
    if al_ejecutar is not None:
        try:
            al_ejecutar(prompt, salida)
        except Exception:  # noqa: BLE001 -- el callback (registrar actividad) es best-effort
            _log.warning("fusionar_semantica: fallo en al_ejecutar.", exc_info=True)

    vistos: set[str] = set()
    salida_grupos: list[list[str]] = []
    for grupo in _extraer_grupos(salida):
        # Solo ids del input, sin repetir entre grupos (disjuntos), preservando orden.
        limpio = [i for i in dict.fromkeys(grupo) if i in ids_validos and i not in vistos]
        if len(limpio) >= 2:
            vistos.update(limpio)
            salida_grupos.append(limpio)

    # SEGUNDA PASADA: cada grupo propuesto se VERIFICA con un prompt enfocado (solo esas
    # historias). El verificador puede confirmar, PARTIR en subgrupos o descartar; un grupo
    # que no supera la verificación NO se fusiona (conservador: fusionar mal infla la
    # corroboración). Mismo contrato JSON, así el parseo y los ejecutores de test no cambian.
    payload_por_id = {q["id"]: q for q in payload}
    confirmados: list[list[str]] = []
    for grupo in salida_grupos:
        confirmados.extend(_verificar_grupo(grupo, payload_por_id, correr, al_ejecutar))
    return confirmados


def _verificar_grupo(
    grupo: list[str],
    payload_por_id: dict[str, dict[str, Any]],
    correr: Ejecutor,
    al_ejecutar: Callable[[str, str], None] | None,
) -> list[list[str]]:
    """Verifica UN grupo propuesto; devuelve los subgrupos confirmados (subset, ≥2, disjuntos)."""
    payload = [payload_por_id[i] for i in grupo if i in payload_por_id]
    if len(payload) < 2:
        return []
    prompt = _construir_prompt(
        json.dumps(payload, ensure_ascii=False), prompt_id=_PROMPT_VERIFICACION_ID
    )
    try:
        with tempfile.TemporaryDirectory(prefix="keni-fusion-verifica-") as carpeta:
            salida = correr(prompt, carpeta)
    except Exception as e:  # noqa: BLE001 -- conservador: sin verificación no se funde
        _log.warning("fusionar_semantica: falló la verificación del grupo (%s); se descarta.", e)
        return []
    if al_ejecutar is not None:
        try:
            al_ejecutar(prompt, salida)
        except Exception:  # noqa: BLE001 -- el callback (registrar actividad) es best-effort
            _log.warning("fusionar_semantica: fallo en al_ejecutar (verificación).", exc_info=True)
    miembros = set(grupo)
    vistos: set[str] = set()
    confirmados: list[list[str]] = []
    for g in _extraer_grupos(salida):
        limpio = [i for i in dict.fromkeys(g) if i in miembros and i not in vistos]
        if len(limpio) >= 2:
            vistos.update(limpio)
            confirmados.append(limpio)
    return confirmados


def _extraer_familias(texto: str) -> list[dict[str, Any]]:
    """Extrae las familias de macro-evento del texto de Haiku. [] si falla.

    Cada familia es `{"tema": "<etiqueta>", "ids": ["id1", "id2", ...]}`; descarta entradas mal
    formadas (sin lista de ids o con tema vacío). El extractor compartido tolera fences/prosa.
    """
    bruto = json_llm.extraer_lista(texto, claves=("familias",))
    if bruto is None:
        return []
    familias: list[dict[str, Any]] = []
    for f in bruto:
        if not isinstance(f, dict):
            continue
        tema = str(f.get("tema", "") or "").strip()
        crudo = f.get("ids")
        if not tema or not isinstance(crudo, list):
            continue
        ids = [str(x) for x in crudo if isinstance(x, (str, int))]
        if ids:
            familias.append({"tema": tema, "ids": ids})
    return familias


def proponer_macro_eventos(
    clusters: list[dict[str, Any]],
    *,
    ejecutor: Ejecutor | None = None,
    al_ejecutar: Callable[[str, str], None] | None = None,
) -> list[dict[str, Any]]:
    """Propone FAMILIAS de macro-evento (Haiku): historias DISTINTAS de un mismo gran evento.

    A diferencia de `proponer_fusiones` (que FUNDE duplicados del mismo hecho en una historia),
    esto solo ETIQUETA familias: clusters que cuentan hechos DISTINTOS pero pertenecen al mismo
    gran acontecimiento (una cumbre, un desastre, un torneo, una elección). No fusiona nada; es
    aditivo y no se solapa con el fundir.

    `clusters`: dicts con al menos `{id, titulo, resumen}`. Devuelve
    `[{"tema": "<etiqueta corta en español>", "ids": ["<cluster_id>", ...]}, ...]` con SOLO las
    familias de 2+ ids DISTINTOS y VÁLIDOS (que existan en el input). [] ante <2 historias o
    cualquier fallo (best-effort, igual que `proponer_fusiones`).

    `al_ejecutar(prompt, salida)`: callback OPCIONAL con el PROMPT y la SALIDA reales de Haiku tras
    la llamada (antes de parsear), para observabilidad; un fallo del callback no afecta al proceso.
    """
    validos = [c for c in clusters if (c.get("id") and (c.get("titulo") or "").strip())][:_MAX_CLUSTERS]
    if len(validos) < 2:
        return []
    ids_validos = {str(c["id"]) for c in validos}

    payload = [
        {
            "id": str(c["id"]),
            "titulo": json_llm.truncar_avisando(
                str(c.get("titulo", "")).strip(), _MAX_CHARS_ITEM,
                campo=f"titulo de {c['id']}", log=_log,
            )[0],
            "resumen": json_llm.truncar_avisando(
                str(c.get("resumen", "") or "").strip(), _MAX_CHARS_ITEM,
                campo=f"resumen de {c['id']}", log=_log,
            )[0],
            # Etiqueta de familia ACTUAL del cluster (puede estar vacía). Se manda para que Haiku
            # REUTILICE verbatim una etiqueta ya existente en vez de inventar un sinónimo.
            "tema_macro": str(c.get("tema_macro") or ""),
        }
        for c in validos
    ]
    correr = ejecutor or _ejecutar_haiku
    prompt = _construir_prompt(
        json.dumps(payload, ensure_ascii=False), prompt_id=_PROMPT_MACRO_ID
    )
    try:
        with tempfile.TemporaryDirectory(prefix="keni-macroevento-") as carpeta:
            salida = correr(prompt, carpeta)
    except Exception as e:  # noqa: BLE001 -- best-effort: cualquier fallo -> no etiqueta nada
        _log.warning("fusionar_semantica: falló la llamada a Haiku (macro-evento): %s", e)
        return []
    if al_ejecutar is not None:
        try:
            al_ejecutar(prompt, salida)
        except Exception:  # noqa: BLE001 -- el callback (registrar actividad) es best-effort
            _log.warning("fusionar_semantica: fallo en al_ejecutar (macro-evento).", exc_info=True)

    familias: list[dict[str, Any]] = []
    for f in _extraer_familias(salida):
        # Solo ids del input, sin repetir DENTRO de la familia, preservando orden.
        ids = [i for i in dict.fromkeys(f["ids"]) if i in ids_validos]
        if len(ids) >= 2:
            familias.append({"tema": f["tema"], "ids": ids})
    return familias


def _ejecutar_haiku(prompt: str, dir_permitido: str) -> str:
    """Ejecutor real: el runner síncrono de `traduccion` con el modelo de la fusión.

    El modelo real lo decide `config.fusion_modelo()` (def sonnet).
    """
    from .. import config
    from .traducir import _ejecutar_claude_json

    return _ejecutar_claude_json(prompt, dir_permitido, modelo=config.fusion_modelo())
