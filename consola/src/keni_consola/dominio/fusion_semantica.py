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
import re
import tempfile
from collections.abc import Callable
from typing import Any

_log = logging.getLogger("keni_consola.dominio.fusion_semantica")

Ejecutor = Callable[[str, str], str]

# Cotas de tamaño del prompt.
_MAX_CLUSTERS = 40           # historias por lote que se mandan a Haiku
_MAX_CHARS_ITEM = 240        # recorte de titulo+resumen por historia


def _construir_prompt(payload_json: str) -> str:
    """Prompt para que Haiku agrupe historias del MISMO evento."""
    return (
        "Eres un editor de un newsroom en México. Recibes una lista JSON de HISTORIAS "
        "(cada una con id, titulo y resumen). Algunas cubren el MISMO acontecimiento desde "
        "ángulos o fuentes distintas (p. ej. el mismo conflicto, el mismo partido, el mismo "
        "anuncio). AGRÚPALAS: junta en un mismo grupo las historias que son del mismo evento. "
        "Sé CONSERVADOR: si dudas, NO las agrupes (mejor dejarlas separadas que fusionar temas "
        "distintos). Una historia puede ir en UN solo grupo. Ignora las que no casan con ninguna. "
        "Devuelve EXCLUSIVAMENTE un objeto JSON con la forma "
        '{"grupos": [["id1","id2"], ["id3","id4","id5"]]} (solo grupos de 2 o más ids), '
        "sin ningún texto adicional ni ```json.\n\n"
        f"Historias:\n{payload_json}"
    )


def _extraer_grupos(texto: str) -> list[list[str]]:
    """Extrae los grupos de ids del texto de Haiku. Tolera ```json fences. [] si falla."""
    if not texto or not texto.strip():
        return []
    s = texto.strip()
    cerca = re.search(r"```(?:json)?\s*(.*?)```", s, re.DOTALL)
    if cerca:
        s = cerca.group(1).strip()
    data: Any = None
    try:
        data = json.loads(s)
    except (json.JSONDecodeError, ValueError):
        inicio = next((i for i, c in enumerate(s) if c in "[{"), -1)
        if inicio < 0:
            return []
        try:
            data = json.loads(s[inicio:])
        except (json.JSONDecodeError, ValueError):
            return []
    bruto = data if isinstance(data, list) else (data.get("grupos") if isinstance(data, dict) else None)
    if not isinstance(bruto, list):
        return []
    grupos: list[list[str]] = []
    for g in bruto:
        if isinstance(g, list):
            ids = [str(x) for x in g if isinstance(x, (str, int))]
            if len(ids) >= 2:
                grupos.append(ids)
    return grupos


def proponer_fusiones(
    clusters: list[dict[str, Any]], *, ejecutor: Ejecutor | None = None
) -> list[list[str]]:
    """Propone grupos de ids de historias del MISMO evento (Haiku). PURO de repos.

    `clusters`: dicts con al menos `{id, titulo, resumen}`. Devuelve grupos VÁLIDOS y DISJUNTOS
    (ids del input, sin repetir entre grupos, tamaño ≥ 2). [] ante <2 historias o cualquier fallo.
    """
    validos = [c for c in clusters if (c.get("id") and (c.get("titulo") or "").strip())][:_MAX_CLUSTERS]
    if len(validos) < 2:
        return []
    ids_validos = {str(c["id"]) for c in validos}

    payload = [
        {
            "id": str(c["id"]),
            "titulo": str(c.get("titulo", "")).strip()[:_MAX_CHARS_ITEM],
            "resumen": str(c.get("resumen", "") or "").strip()[:_MAX_CHARS_ITEM],
        }
        for c in validos
    ]
    correr = ejecutor or _ejecutar_haiku
    try:
        with tempfile.TemporaryDirectory(prefix="keni-fusion-") as carpeta:
            salida = correr(_construir_prompt(json.dumps(payload, ensure_ascii=False)), carpeta)
    except Exception as e:  # noqa: BLE001 -- best-effort: cualquier fallo -> no fusiona nada
        _log.warning("fusion_semantica: falló la llamada a Haiku: %s", e)
        return []

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
