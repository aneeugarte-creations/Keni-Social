"""Fusionar SEMÁNTICAMENTE historias del MISMO evento con claude (Fase 2b).

El agrupar léxico (agrupar.asignar) une variantes claras del MISMO titular (url canónica o
título fuzzy ≥ umbral), pero NO une coberturas del mismo evento con titulares distintos
("Zelensky responde" vs "Rusia lanza misiles"). Esta capa, OPCIONAL y gateada, le pasa a Haiku el
lote de historias recientes de una marca y le pide AGRUPAR las que son del mismo evento; el daemon
fusiona cada grupo en una sola historia (n_fuentes real → mejor señal de tendencia/corroboración).

Este módulo es NEUTRO y PURO de I/O: solo construye el prompt, llama al ejecutor (inyectable en
tests) y parsea los grupos. Fusionar de verdad (reasignar items + borrar absorbidos + recalcular)
lo hace el daemon (`recolectar_daemon`), que es quien tiene los repos. BEST-EFFORT: ante cualquier
fallo devuelve `Fusiones([], [])` (no se fusiona ni etiqueta nada).

UNA PASADA del LLM (prompt `fusionar`) resuelve DOS agrupados del mismo lote, que antes eran dos
llamadas paralelas que leían los mismos titulares:
  - `grupos`: historias que son el MISMO HECHO concreto → el daemon las FUNDE en una.
  - `familias`: historias DISTINTAS de un mismo GRAN evento (cumbre, torneo, desastre…) → el daemon
    las ETIQUETA con `tema_macro` (no las funde); producción arma un carrusel del evento.

Los grupos pasan además por una VERIFICACIÓN por grupo (prompt `fusionar-verificar`, «Cotejar»):
re-pregunta con SOLO esas historias y el grupo sale confirmado, PARTIDO en subgrupos o descartado
(fusionar por error es caro: infla la corroboración y auto-produce piezas con fuentes que no hablan
de lo mismo — pasó con «Shakira en la inauguración» fundida con «alerta de la embajada» por el
«Mundial»). Las familias NO se verifican (no se funden). El modelo es `config.fusion_modelo()`.
"""

from __future__ import annotations

import json
import logging
import tempfile
from collections.abc import Callable
from typing import Any, NamedTuple

from . import json_llm

_log = logging.getLogger("keni_consola.dominio.fusionar_semantica")

Ejecutor = Callable[[str, str], str]


class Fusiones(NamedTuple):
    """Salida de `proponer_fusiones`: dos agrupados del MISMO lote en una sola pasada del LLM.

    `grupos`: ids del MISMO hecho concreto (ya verificados) que el daemon FUNDE.
    `familias`: `{tema, ids}` de historias DISTINTAS del mismo gran evento que el daemon ETIQUETA.
    """

    grupos: list[list[str]]
    familias: list[dict[str, Any]]

# Cotas de tamaño del prompt.
_MAX_CLUSTERS = 40           # historias por lote que se mandan a Haiku
_MAX_CHARS_ITEM = 240        # recorte del titulo por historia


# La plantilla vive en la Prompts de Texto como prompt EDITABLE (pestaña «Prompts»). La lista
# JSON de historias se inserta en `{{HISTORIAS}}`. Si el store fallara, la red es la INICIAL del
# paquete (fuente única, sin texto duplicado aquí).
_PROMPT_ID = "prompt/fusionar"
_PROMPT_VERIFICACION_ID = "prompt/fusionar-verificar"
_PROMPT_SUBTEMA_ID = "prompt/fusionar-subtema"
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
) -> Fusiones:
    """En UNA pasada del LLM propone `grupos` (mismo hecho, a fundir) y `familias` (mismo gran
    evento, a etiquetar). PURO de repos.

    `clusters`: dicts con al menos `{id, titulo}` (y `tema_macro` opcional, que viaja en el payload
    para que las familias REUTILICEN una etiqueta existente). Los `grupos` salen VÁLIDOS, DISJUNTOS y
    VERIFICADOS (ids del input, sin repetir entre grupos, ≥2); las `familias` son `{tema, ids}` con
    ids válidos del input (≥2). `Fusiones([], [])` ante <2 historias o cualquier fallo de la llamada.

    `al_ejecutar(prompt, salida)`: callback OPCIONAL con el PROMPT y la SALIDA reales del LLM tras
    cada llamada (antes de parsear). El daemon lo usa para registrar la actividad IA de Fusionar con
    el LLM real; un fallo del callback no afecta a Fusionar (es observabilidad).
    """
    validos = [c for c in clusters if (c.get("id") and (c.get("titulo") or "").strip())][:_MAX_CLUSTERS]
    if len(validos) < 2:
        return Fusiones([], [])
    ids_validos = {str(c["id"]) for c in validos}

    payload = [
        {
            "id": str(c["id"]),
            "titulo": json_llm.truncar_avisando(
                str(c.get("titulo", "")).strip(), _MAX_CHARS_ITEM,
                campo=f"titulo de {c['id']}", log=_log,
            )[0],
            # Etiqueta de familia ACTUAL del cluster (puede estar vacía): se manda para que el modelo
            # REUTILICE verbatim una etiqueta existente en vez de inventar un sinónimo.
            "tema_macro": str(c.get("tema_macro") or ""),
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
        return Fusiones([], [])
    if al_ejecutar is not None:
        try:
            al_ejecutar(prompt, salida)
        except Exception:  # noqa: BLE001 -- el callback (registrar actividad) es best-effort
            _log.warning("fusionar_semantica: fallo en al_ejecutar.", exc_info=True)

    # GRUPOS (a fundir): disjuntos, solo ids del input, ≥2.
    vistos: set[str] = set()
    salida_grupos: list[list[str]] = []
    for grupo in _extraer_grupos(salida):
        limpio = [i for i in dict.fromkeys(grupo) if i in ids_validos and i not in vistos]
        if len(limpio) >= 2:
            vistos.update(limpio)
            salida_grupos.append(limpio)

    # FAMILIAS (a etiquetar, NO se funden): {tema, ids} con ids del input, sin repetir DENTRO, ≥2.
    familias: list[dict[str, Any]] = []
    for f in _extraer_familias(salida):
        ids = [i for i in dict.fromkeys(f["ids"]) if i in ids_validos]
        if len(ids) >= 2:
            familias.append({"tema": f["tema"], "ids": ids})

    # VERIFICACIÓN («Cotejar»): cada grupo propuesto se re-pregunta con un prompt enfocado (solo esas
    # historias). El verificador confirma, PARTE en subgrupos o descarta; un grupo que no la supera NO
    # se funde (conservador). Las familias no se verifican. El parseo y los ejecutores de test no cambian.
    payload_por_id = {q["id"]: q for q in payload}
    confirmados: list[list[str]] = []
    for grupo in salida_grupos:
        confirmados.extend(_verificar_grupo(grupo, payload_por_id, correr, al_ejecutar))
    return Fusiones(confirmados, familias)


def _verificar_grupo(
    grupo: list[str],
    payload_por_id: dict[str, dict[str, Any]],
    correr: Ejecutor,
    al_ejecutar: Callable[[str, str], None] | None,
) -> list[list[str]]:
    """Verifica UN grupo propuesto; devuelve los subgrupos confirmados (subset, ≥2, disjuntos)."""
    # La verificación juzga "mismo HECHO concreto": solo {id, titulo}, sin `tema_macro` (un tema
    # compartido NO basta para fundir, así que no debe entrar como ruido en el prompt de Cotejar).
    payload = [{"id": payload_por_id[i]["id"], "titulo": payload_por_id[i]["titulo"]}
               for i in grupo if i in payload_por_id]
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


def _extraer_subtemas(texto: str) -> list[dict[str, Any]]:
    """Extrae los subtemas de un macro-evento del texto de Haiku. [] si falla.

    Cada subtema es `{"subtema": "<etiqueta>", "ids": ["id1", ...]}`; a diferencia de las
    familias, un subtema válido puede tener UN solo id (faceta con una sola historia).
    """
    bruto = json_llm.extraer_lista(texto, claves=("subtemas",))
    if bruto is None:
        return []
    subtemas: list[dict[str, Any]] = []
    for s in bruto:
        if not isinstance(s, dict):
            continue
        etiqueta = str(s.get("subtema", "") or "").strip()
        crudo = s.get("ids")
        if not etiqueta or not isinstance(crudo, list):
            continue
        ids = [str(x) for x in crudo if isinstance(x, (str, int))]
        if ids:
            subtemas.append({"subtema": etiqueta, "ids": ids})
    return subtemas


def proponer_subtemas(
    clusters: list[dict[str, Any]],
    *,
    ejecutor: Ejecutor | None = None,
    al_ejecutar: Callable[[str, str], None] | None = None,
) -> list[dict[str, Any]]:
    """Parte un MACRO-EVENTO ya etiquetado en SUBTEMAS coherentes (Haiku). PURO de repos.

    `clusters`: las historias de UNA familia de macro-evento (dicts con `{id, titulo}` y
    `subtema` opcional para reutilizar la etiqueta). Devuelve `[{"subtema": "<etiqueta>",
    "ids": [...]}, ...]` con cada id en UN solo subtema (disjuntos, del input). Un subtema
    puede tener un solo id. [] ante <2 historias o cualquier fallo (best-effort).

    Separa el evento por FACETA (partidos, incidentes, espectáculo…) para que cada carrusel
    sea de un tipo (un concierto no entra en el resumen de partidos) y la cadencia sea por
    subtema, no por el evento entero.
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
            # Subtema ACTUAL del cluster (puede estar vacío): que Haiku REUTILICE la etiqueta.
            "subtema": str(c.get("subtema") or ""),
        }
        for c in validos
    ]
    correr = ejecutor or _ejecutar_haiku
    prompt = _construir_prompt(
        json.dumps(payload, ensure_ascii=False), prompt_id=_PROMPT_SUBTEMA_ID
    )
    try:
        with tempfile.TemporaryDirectory(prefix="keni-subtema-") as carpeta:
            salida = correr(prompt, carpeta)
    except Exception as e:  # noqa: BLE001 -- best-effort: cualquier fallo -> no parte nada
        _log.warning("fusionar_semantica: falló la llamada a Haiku (subtema): %s", e)
        return []
    if al_ejecutar is not None:
        try:
            al_ejecutar(prompt, salida)
        except Exception:  # noqa: BLE001 -- el callback (registrar actividad) es best-effort
            _log.warning("fusionar_semantica: fallo en al_ejecutar (subtema).", exc_info=True)

    vistos: set[str] = set()
    subtemas: list[dict[str, Any]] = []
    for s in _extraer_subtemas(salida):
        # Solo ids del input, sin repetir entre subtemas (disjuntos), preservando orden.
        ids = [i for i in dict.fromkeys(s["ids"]) if i in ids_validos and i not in vistos]
        if ids:
            vistos.update(ids)
            subtemas.append({"subtema": s["subtema"], "ids": ids})
    return subtemas


def _ejecutar_haiku(prompt: str, dir_permitido: str) -> str:
    """Ejecutor real: el runner síncrono de `traduccion` con el modelo de la fusión.

    El modelo real lo decide `config.fusion_modelo()` (def sonnet). La fusión es una
    clasificación INLINE (agrupar ids por evento): se acota a NO agéntica —`max_turns=1` y
    `sin_tools=True` (sin `--add-dir`)— para que el modelo responda en un turno sin abrir un
    bucle de herramientas.
    """
    from .. import config
    from .traducir import _ejecutar_claude_json

    return _ejecutar_claude_json(
        prompt, dir_permitido, modelo=config.fusion_modelo(),
        max_turns=1, sin_tools=True,
    )
