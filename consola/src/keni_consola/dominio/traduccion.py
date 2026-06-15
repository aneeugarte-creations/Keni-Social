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
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Callable
from typing import Any

from .. import config
from . import json_llm

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

# ACUMULADOR de métricas del ejecutor síncrono, POR HILO. El envelope JSON de `claude -p
# --output-format json` trae el coste real de cada llamada (tokens/coste/duración), pero los
# pasos del pool (fusión, encaje, traducción, insumos) lo descartaban: sus registros de
# actividad salían SIN métricas en Producción. Cada llamada SUMA aquí; quien registra la
# actividad lo recoge (y resetea) con `tomar_metricas_acumuladas()`. Thread-local: los pasos
# del daemon corren secuenciales en su hilo, así la atribución no se cruza con otros hilos
# (worker/insumos) que usan este mismo ejecutor.
_metricas_hilo = threading.local()


def _metricas_de_envelope(envelope: dict[str, Any]) -> dict[str, Any] | None:
    """Métricas del envelope de `claude -p --output-format json`, o None si no trae ninguna.

    Forma compatible con `generaciones.metricas` (la que normaliza el dominio `actividad`):
    `{tokens_in, tokens_out, total_cost_usd, duration_ms, num_turns}`. PURA y tolerante:
    campos ausentes/ilegibles se omiten.
    """
    if not isinstance(envelope, dict):
        return None
    out: dict[str, Any] = {}
    usage = envelope.get("usage") if isinstance(envelope.get("usage"), dict) else {}
    for destino, fuente, conv in (
        ("tokens_in", usage.get("input_tokens"), int),
        ("tokens_out", usage.get("output_tokens"), int),
        ("total_cost_usd", envelope.get("total_cost_usd"), float),
        ("duration_ms", envelope.get("duration_ms"), int),
        ("num_turns", envelope.get("num_turns"), int),
    ):
        if isinstance(fuente, bool) or not isinstance(fuente, (int, float)):
            continue
        out[destino] = conv(fuente)
    return out or None


def _acumular_metricas(metricas: dict[str, Any] | None) -> None:
    """Suma `metricas` al acumulador del hilo (no-op con None)."""
    if not metricas:
        return
    acc = getattr(_metricas_hilo, "acumulado", None)
    if acc is None:
        acc = {}
        _metricas_hilo.acumulado = acc
    for clave, valor in metricas.items():
        acc[clave] = acc.get(clave, 0) + valor


def tomar_metricas_acumuladas() -> dict[str, Any] | None:
    """Devuelve y RESETEA las métricas acumuladas del hilo desde la última toma (None si nada).

    Lo usa quien registra la actividad de un paso IA del pool justo después de ejecutarlo
    (p. ej. `ingesta_daemon._registrar_actividad_ia`): lo acumulado desde la toma anterior
    es el coste de ESE paso. Tomar también sirve para DESCARTAR restos entre pasos.
    """
    acc = getattr(_metricas_hilo, "acumulado", None)
    _metricas_hilo.acumulado = None
    return acc or None


def _ejecutar_claude_json(prompt: str, dir_permitido: str, modelo: str | None = None) -> str:
    """Corre `claude -p <prompt> --output-format json [--model X] --add-dir <dir>`.

    Síncrono, acotado por `_CLAUDE_TIMEOUT_S`. Hereda el entorno (incluido
    `CLAUDE_CODE_OAUTH_TOKEN`). `modelo=None` cae al de insumos (`KENI_INSUMOS_MODELO`);
    un llamante puede fijar el suyo (la fusión usa el de `KENI_FUSION_MODELO`). No tocar
    en tests: se inyecta un ejecutor falso.
    """
    from . import stream  # import perezoso: evita ciclo importador<->dominio

    if shutil.which("claude") is None:
        raise RuntimeError("El asistente (claude) no está disponible en el servidor.")
    if modelo is None:
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
        # Coste REAL de la llamada (tokens/coste/duración): se acumula para que el
        # registro de actividad del paso lo selle (visible en Producción).
        _acumular_metricas(_metricas_de_envelope(envelope))
        return str(envelope.get("result") or "")
    return res.stdout or ""


# --------------------------------------------------------------------------- #
# Prompt                                                                        #
# --------------------------------------------------------------------------- #


# La plantilla vive en la Biblioteca de Texto como prompt EDITABLE (pestaña «Prompts»). La lista
# JSON a traducir se inserta en `{{ITEMS}}`. Si el store fallara, la red es la SEMILLA del
# paquete (fuente única, sin texto duplicado aquí).
_PROMPT_ID = "prompt/traducir"
_MARCA_ITEMS = "{{ITEMS}}"


def _plantilla() -> str:
    """Cuerpo EFECTIVO de la plantilla (store del equipo > semilla del paquete)."""
    from .. import libtexto

    try:
        cuerpo = (libtexto.cuerpo_efectivo(_PROMPT_ID) or "").strip()
    except Exception:  # noqa: BLE001 -- nunca dejar Traducir sin prompt por un fallo de lectura
        cuerpo = ""
    return cuerpo or libtexto.cuerpo_semilla(_PROMPT_ID).strip()


def _construir_prompt(items_json: str) -> str:
    """Prompt de traducción por lotes para Haiku (plantilla editable + lista JSON)."""
    plantilla = _plantilla()
    if _MARCA_ITEMS in plantilla:
        return plantilla.replace(_MARCA_ITEMS, items_json)
    return f"{plantilla}\n\nLista de ítems:\n{items_json}"


# --------------------------------------------------------------------------- #
# Extracción tolerante del JSON de respuesta                                   #
# --------------------------------------------------------------------------- #


def _extraer_traducciones(texto: str) -> list[dict[str, str]] | None:
    """Extrae la lista de traducciones del texto de Claude (extractor compartido)."""
    return json_llm.extraer_lista(
        texto, claves=("traducciones", "items", "translations", "resultados")
    )


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

    # Construye el payload de entrada, recortando campos largos (truncado centralizado).
    payload: list[dict[str, str]] = []
    for item in items:
        item_id = str(item.get("id", ""))
        titulo, _ = json_llm.truncar_avisando(
            str(item.get("titulo", "")).strip(), _MAX_CHARS_ITEM,
            campo=f"titulo de {item_id}", log=_log,
        )
        # Recorta resumen para que titulo+resumen juntos no superen el cap.
        espacio_resumen = max(0, _MAX_CHARS_ITEM - len(titulo))
        resumen, _ = json_llm.truncar_avisando(
            str(item.get("resumen", "") or "").strip(), espacio_resumen,
            campo=f"resumen de {item_id}", log=_log,
        )
        payload.append({
            "id": item_id,
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

    sin_traducir: list[str] = []
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
            # Ítem ausente (o sin `titulo_es`) en la respuesta -> conserva el original. El
            # fallback es razonable, pero NO silencioso: el prompt pide TODOS los ítems.
            sin_traducir.append(item_id)
            resultado.append({
                "id": item_id,
                "titulo_es": str(item.get("titulo", "")),
                "resumen_es": str(item.get("resumen", "") or ""),
            })
    if sin_traducir:
        _log.warning(
            "traducir_items: %d de %d ítem(s) sin traducción en la respuesta "
            "(se conserva el original): %s",
            len(sin_traducir), len(items), ", ".join(sin_traducir[:10]),
        )

    return resultado
