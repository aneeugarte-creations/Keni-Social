"""Fusión SEMÁNTICA de historias del MISMO evento con Haiku (Fase 2b).

El clustering léxico (clustering.asignar) une variantes claras del MISMO titular (url canónica o
título fuzzy ≥ umbral), pero NO une coberturas del mismo evento con titulares distintos
("Zelensky responde" vs "Rusia lanza misiles"). Esta capa, OPCIONAL y gateada, le pasa a Haiku el
lote de historias recientes de una marca y le pide AGRUPAR las que son del mismo evento; el daemon
funde cada grupo en una sola historia (n_fuentes real → mejor señal de tendencia/corroboración).

Este módulo es NEUTRO y PURO de I/O: solo construye el prompt, llama al ejecutor (inyectable en
tests) y parsea los grupos. La FUSIÓN efectiva (reasignar items + borrar absorbidos + recalcular)
la hace el daemon (`ingesta_daemon`), que es quien tiene los repos. BEST-EFFORT: ante cualquier
fallo devuelve [] (no se funde nada).
"""

from __future__ import annotations

import json
import logging
import tempfile
from collections.abc import Callable
from typing import Any

from . import json_llm

_log = logging.getLogger("keni_consola.dominio.fusion_semantica")

Ejecutor = Callable[[str, str], str]

# Cotas de tamaño del prompt.
_MAX_CLUSTERS = 40           # historias por lote que se mandan a Haiku
_MAX_CHARS_ITEM = 240        # recorte de titulo+resumen por historia


# La plantilla vive en la Biblioteca de Texto como prompt EDITABLE (pestaña «Prompts»). La lista
# JSON de historias se inserta en `{{HISTORIAS}}`. Si el store fallara, la red es la SEMILLA del
# paquete (fuente única, sin texto duplicado aquí).
_PROMPT_ID = "prompt/noticias/fusion-historias"
_MARCA_HISTORIAS = "{{HISTORIAS}}"


def _plantilla() -> str:
    """Cuerpo EFECTIVO de la plantilla (store del equipo > semilla del paquete)."""
    from .. import libtexto

    try:
        cuerpo = (libtexto.cuerpo_efectivo(_PROMPT_ID) or "").strip()
    except Exception:  # noqa: BLE001 -- nunca dejar la fusión sin prompt por un fallo de lectura
        cuerpo = ""
    return cuerpo or libtexto.cuerpo_semilla(_PROMPT_ID).strip()


def _construir_prompt(payload_json: str) -> str:
    """Prompt para que Haiku agrupe historias del MISMO evento (plantilla editable + lista JSON)."""
    plantilla = _plantilla()
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
    la fusión con el Haiku real; un fallo del callback no afecta a la fusión (es observabilidad).
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
        _log.warning("fusion_semantica: falló la llamada a Haiku: %s", e)
        return []
    if al_ejecutar is not None:
        try:
            al_ejecutar(prompt, salida)
        except Exception:  # noqa: BLE001 -- el callback (registrar actividad) es best-effort
            _log.warning("fusion_semantica: fallo en al_ejecutar.", exc_info=True)

    vistos: set[str] = set()
    salida_grupos: list[list[str]] = []
    for grupo in _extraer_grupos(salida):
        # Solo ids del input, sin repetir entre grupos (disjuntos), preservando orden.
        limpio = [i for i in dict.fromkeys(grupo) if i in ids_validos and i not in vistos]
        if len(limpio) >= 2:
            vistos.update(limpio)
            salida_grupos.append(limpio)
    return salida_grupos


def _ejecutar_haiku(prompt: str, dir_permitido: str) -> str:
    """Ejecutor real: reutiliza el runner síncrono de `traduccion` (claude -p --output-format json)."""
    from .traduccion import _ejecutar_claude_json

    return _ejecutar_claude_json(prompt, dir_permitido)
