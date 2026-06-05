"""Traducción + tropicalización MX de títulos/resúmenes extranjeros con Haiku.

Patrón SÍNCRONO POR LOTES: una sola llamada `claude -p --output-format json`
traduce TODOS los ítems de una vez (minimiza el nro de subprocesos). Mismo patrón
que `importador_calendario._ejecutar_claude_json` y `dominio.insumos_parse`, con
`--model` de `config.insumos_modelo()`.

API pública:
    traducir_items(items, *, ejecutor=None) -> list[dict]

`items` es una lista de dicts con al menos `{id, titulo, resumen}` en idioma extranjero.
Devuelve `[{id, titulo_es, resumen_es}]` traducidos y tropicalizados al español MX.

Ejecutor inyectable (tests): si `ejecutor` es None se usa el subproceso real
(`_ejecutar_claude_json`); en tests se pasa una función falsa para no llamar a `claude`.

BEST-EFFORT: ante cualquier fallo (subproceso, timeout, JSON inválido, etc.) devuelve
los ítems originales mapeados a `titulo_es`/`resumen_es` (sin romper el Radar).

Acotado por tamaño de prompt: si la lista es muy larga, se trunca el texto de cada ítem
para no superar el límite razonable de contexto de entrada (ver `_MAX_CHARS_ITEM`).
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from typing import Any

from .. import config

_log = logging.getLogger("keni_consola.dominio.traduccion")

# Timeout del subproceso. Haiku es rápido; 60 s es más que suficiente para un lote de 15 ítems.
_CLAUDE_TIMEOUT_S = 90

# Máximo de caracteres de titulo+resumen que se pasan al prompt POR ÍTEM.
# Protección contra prompts enormes (feeds con artículos larguísimos).
_MAX_CHARS_ITEM = 600

# Tipo del ejecutor inyectable (misma firma que en insumos_parse).
Ejecutor = Callable[[str, str], str]


# --------------------------------------------------------------------------- #
# Ejecutor real                                                                 #
# --------------------------------------------------------------------------- #


def _ejecutar_claude_json(prompt: str, dir_permitido: str) -> str:
    """Corre `claude -p <prompt> --output-format json [--model X] --add-dir <dir>`.

    Síncrono, acotado por `_CLAUDE_TIMEOUT_S`. Hereda el entorno (incluido
    `CLAUDE_CODE_OAUTH_TOKEN`). No tocar en tests: se inyecta un ejecutor falso.
    """
    from . import stream  # import perezoso: evita ciclo importador<->dominio

    if shutil.which("claude") is None:
        raise RuntimeError("El asistente (claude) no está disponible en el servidor.")
    modelo = config.insumos_modelo()
    argv: list[str] = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "json",
        "--add-dir",
        dir_permitido,
        *stream.arg_skip_permisos(),
    ]
    if modelo:
        argv += ["--model", modelo]
    res = subprocess.run(  # noqa: S603 -- argv fijo, sin shell; prompt va como argumento
        argv,
        capture_output=True,
        text=True,
        timeout=_CLAUDE_TIMEOUT_S,
        check=False,
        env=dict(os.environ),
    )
    if res.returncode != 0:
        raise RuntimeError((res.stderr or "claude terminó con error").strip()[:300])
    try:
        envelope = json.loads(res.stdout or "{}")
    except (json.JSONDecodeError, ValueError):
        return res.stdout or ""
    if isinstance(envelope, dict):
        return str(envelope.get("result") or "")
    return res.stdout or ""


# --------------------------------------------------------------------------- #
# Prompt                                                                        #
# --------------------------------------------------------------------------- #


def _construir_prompt(items_json: str) -> str:
    """Prompt de traducción por lotes para Haiku."""
    return (
        "Eres un traductor y localizador para el equipo de redes sociales de UnoTV en México. "
        "Recibes una lista JSON de titulares y resúmenes en idioma extranjero. "
        "Tradúcelos al español mexicano (MX): usa vocabulario natural de México, "
        "tropicaliza nombres/referencias si corresponde, sé conciso y periodístico. "
        "Devuelve EXCLUSIVAMENTE un objeto JSON con la forma "
        '{"traducciones": [{"id": "...", "titulo_es": "...", "resumen_es": "..."}, ...]} '
        "sin ningún texto adicional ni ```json. "
        "Si un resumen está vacío, devuelve resumen_es vacío también. "
        "No inventes ni añadas información que no esté en el original.\n\n"
        f"Lista de ítems:\n{items_json}"
    )


# --------------------------------------------------------------------------- #
# Extracción tolerante del JSON de respuesta                                   #
# --------------------------------------------------------------------------- #


def _extraer_traducciones(texto: str) -> list[dict[str, str]] | None:
    """Extrae la lista de traducciones del texto de Claude. Tolera ```json fences."""
    if not texto or not texto.strip():
        return None
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
            return None
        try:
            data = json.loads(s[inicio:])
        except (json.JSONDecodeError, ValueError):
            return None
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for clave in ("traducciones", "items", "translations", "resultados"):
            if isinstance(data.get(clave), list):
                return data[clave]
    return None


# --------------------------------------------------------------------------- #
# API pública                                                                   #
# --------------------------------------------------------------------------- #


def traducir_items(
    items: list[dict[str, Any]],
    *,
    ejecutor: Ejecutor | None = None,
) -> list[dict[str, Any]]:
    """Traduce+tropicaliza una lista de ítems al español MX con una sola llamada a Haiku.

    Parámetros:
        items: lista de dicts con al menos `{id, titulo, resumen}` en idioma extranjero.
        ejecutor: función `(prompt, dir_permitido) -> str` inyectable (para tests). Si es
            None se usa el subproceso real.

    Devuelve: `[{id, titulo_es, resumen_es}]`. En cualquier fallo (subproceso, timeout,
    JSON inválido, ítem no encontrado en la respuesta) devuelve los originales como
    `titulo_es`/`resumen_es` (best-effort, sin romper el Radar).
    """
    if not items:
        return []

    correr = ejecutor or _ejecutar_claude_json

    # Construye el payload de entrada, recortando campos largos.
    payload: list[dict[str, str]] = []
    for item in items:
        titulo = str(item.get("titulo", "")).strip()[:_MAX_CHARS_ITEM]
        resumen = str(item.get("resumen", "") or "").strip()
        # Recorta resumen para que titulo+resumen juntos no superen el cap.
        espacio_resumen = max(0, _MAX_CHARS_ITEM - len(titulo))
        resumen = resumen[:espacio_resumen]
        payload.append({
            "id": str(item.get("id", "")),
            "titulo": titulo,
            "resumen": resumen,
        })

    def _fallback() -> list[dict[str, Any]]:
        return [
            {
                "id": str(it.get("id", "")),
                "titulo_es": str(it.get("titulo", "")),
                "resumen_es": str(it.get("resumen", "") or ""),
            }
            for it in items
        ]

    try:
        items_json = json.dumps(payload, ensure_ascii=False)
        prompt = _construir_prompt(items_json)
        with tempfile.TemporaryDirectory(prefix="keni-traduccion-") as carpeta:
            salida = correr(prompt, carpeta)
    except Exception as e:  # noqa: BLE001 -- best-effort: cualquier fallo -> originales
        _log.warning("traducir_items falló al llamar a claude: %s", e)
        return _fallback()

    traducciones = _extraer_traducciones(salida)
    if traducciones is None:
        _log.warning("traducir_items: no se pudo extraer JSON de la respuesta de Haiku.")
        return _fallback()

    # Normaliza la respuesta y rellena con originales los ítems que falten.
    resultado: list[dict[str, Any]] = []
    por_id: dict[str, dict[str, Any]] = {}
    for t in traducciones:
        if isinstance(t, dict) and "id" in t:
            por_id[str(t["id"])] = t

    for item in items:
        item_id = str(item.get("id", ""))
        trad = por_id.get(item_id)
        if trad and isinstance(trad.get("titulo_es"), str):
            resultado.append({
                "id": item_id,
                "titulo_es": str(trad["titulo_es"]).strip() or str(item.get("titulo", "")),
                "resumen_es": str(trad.get("resumen_es", "") or "").strip(),
            })
        else:
            # ítem no encontrado en la respuesta -> devuelve el original
            resultado.append({
                "id": item_id,
                "titulo_es": str(item.get("titulo", "")),
                "resumen_es": str(item.get("resumen", "") or ""),
            })

    return resultado
