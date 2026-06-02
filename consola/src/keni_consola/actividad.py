"""Dominio ACTIVIDAD: vista UNIFICADA de la actividad de IA de la consola.

La "verdad" de lo que la IA produce vive en DOS registros SEPARADOS:

  - GENERACIONES (`generaciones.py`): los TRABAJOS de IA de la consola (copy, rss,
    autogen, hashtags, imagen, verificacion, qa-editorial, prompt). Cada uno trae su
    `tipo`, `marca`, `etiqueta`, `estado`, `fecha_inicio` y `metricas`.
  - RUNS (`agentes.py`): las ejecuciones de un prompt en la carpeta de un agente
    (`<raiz>/<marca>/runs/<id>.yaml`). Traen `prompt`, `estado`, `fecha_inicio` y
    `metricas` (con `tokens_in`/`tokens_out`/`total_cost_usd`/`duration_ms`/`num_turns`).

Este modulo NORMALIZA ambos a un mismo ITEM de actividad y los combina/agrega. Es
DOMINIO PURO: todas las funciones reciben listas ya leidas (no tocan disco ni la BD),
de modo que se prueban sin Postgres ni ficheros. La capa `api/actividad.py` es la que
lee `generaciones.listar(...)` y los runs via el dominio `agentes`, y se las pasa.

FORMA del ITEM (congelada; el frontend depende de ella):

    {
      "id": str,
      "fuente": "generacion" | "run",
      "tipo": str,            # tipo de la generacion, o "run" para los runs
      "etiqueta": str,
      "marca": str,
      "estado": str,
      "fecha": str,           # ISO (fecha_inicio del origen)
      "metricas": {"tokens": int|None, "coste_usd": float|None,
                   "duration_ms": int|None, "num_turns": int|None},
      "resultado_url": str|None,  # ruta del SPA al resultado (solo generaciones COMPLETADAS)
    }
"""

from __future__ import annotations

from typing import Any

# Longitud maxima de la `etiqueta` derivada del prompt de un run (recorte legible).
_ETIQUETA_RUN_MAX = 80


def _entero_o_none(valor: Any) -> int | None:
    """`valor` como entero, o None si ausente/no numerico (los bool no cuentan)."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    return int(valor)


def _numero_o_none(valor: Any) -> float | None:
    """`valor` como float, o None si ausente/no numerico (los bool no cuentan)."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    return float(valor)


def _suma_tokens(metricas: dict[str, Any] | None) -> int | None:
    """tokens_in + tokens_out de un run; None si no hay ninguno de los dos."""
    if not isinstance(metricas, dict):
        return None
    ent = _entero_o_none(metricas.get("tokens_in"))
    sal = _entero_o_none(metricas.get("tokens_out"))
    if ent is None and sal is None:
        return None
    return (ent or 0) + (sal or 0)


def _metricas_generacion(metricas: dict[str, Any] | None) -> dict[str, Any]:
    """Bloque de metricas normalizado de una GENERACION.

    Las generaciones ya guardan `tokens_in`/`tokens_out` (de la skill) ademas de
    `total_cost_usd`/`duration_ms`/`num_turns`; agregamos tokens como en los runs.
    """
    if not isinstance(metricas, dict):
        metricas = {}
    return {
        "tokens": _suma_tokens(metricas),
        "coste_usd": _numero_o_none(metricas.get("total_cost_usd")),
        "duration_ms": _entero_o_none(metricas.get("duration_ms")),
        "num_turns": _entero_o_none(metricas.get("num_turns")),
    }


def _metricas_run(metricas: dict[str, Any] | None) -> dict[str, Any]:
    """Bloque de metricas normalizado de un RUN (mismo mapeo que la generacion)."""
    if not isinstance(metricas, dict):
        metricas = {}
    return {
        "tokens": _suma_tokens(metricas),
        "coste_usd": _numero_o_none(metricas.get("total_cost_usd")),
        "duration_ms": _entero_o_none(metricas.get("duration_ms")),
        "num_turns": _entero_o_none(metricas.get("num_turns")),
    }


# Ruta del SPA donde aterriza el RESULTADO de cada tipo de generacion COMPLETADA. Los
# resultados no tienen deep-link por id, asi que enlazamos a la superficie que los
# muestra (el copy/rss cae como borradores en el tablero; la imagen en el estudio; etc.).
# Los tipos sin pagina de resultado propia (hashtags/prompt) y los runs no llevan enlace.
_URL_RESULTADO_POR_TIPO = {
    "copy": "/parrilla/pendientes",
    "rss": "/parrilla/pendientes",
    "imagen": "/estudio",
    "verificacion": "/revision/verificacion",
    "qa-editorial": "/revision/editorial",
}


def _resultado_url(g: dict[str, Any]) -> str | None:
    """Ruta del SPA al resultado de una generacion COMPLETADA, o None.

    Solo aplica a generaciones en estado `completado` con un `tipo` que tenga pagina de
    resultado. No hay deep-link por id: enlazamos a la superficie que muestra ese tipo
    de resultado (el frontend resuelve el 404/estado vacio si ya no esta).
    """
    if str(g.get("estado", "") or "") != "completado":
        return None
    return _URL_RESULTADO_POR_TIPO.get(str(g.get("tipo", "") or ""))


def normalizar_generacion(g: dict[str, Any]) -> dict[str, Any]:
    """Normaliza una GENERACION (dict publico de `generaciones`) a un ITEM de actividad."""
    return {
        "id": str(g.get("id", "") or ""),
        "fuente": "generacion",
        "tipo": str(g.get("tipo", "") or ""),
        "etiqueta": str(g.get("etiqueta", "") or ""),
        "marca": str(g.get("marca", "") or ""),
        "estado": str(g.get("estado", "") or ""),
        "fecha": str(g.get("fecha_inicio", "") or ""),
        "metricas": _metricas_generacion(g.get("metricas")),
        "resultado_url": _resultado_url(g),
    }


def _etiqueta_run(r: dict[str, Any]) -> str:
    """Etiqueta legible de un run: su prompt recortado (o el nombre del agente)."""
    prompt = r.get("prompt")
    if isinstance(prompt, str) and prompt.strip():
        texto = prompt.strip()
        if len(texto) > _ETIQUETA_RUN_MAX:
            return texto[: _ETIQUETA_RUN_MAX - 1].rstrip() + "…"
        return texto
    for clave in ("agente_nombre", "agente"):
        valor = r.get(clave)
        if isinstance(valor, str) and valor.strip():
            return valor.strip()
    return ""


def normalizar_run(r: dict[str, Any]) -> dict[str, Any]:
    """Normaliza un RUN de agente (dict de `agentes`) a un ITEM de actividad.

    `marca` = el agente del run (`agente` o `agente_nombre`); `tipo` = "run";
    `etiqueta` = prompt recortado o nombre del agente. Las metricas mapean
    tokens_in+tokens_out -> tokens y total_cost_usd -> coste_usd.
    """
    marca = r.get("agente") or r.get("agente_nombre") or r.get("marca") or ""
    return {
        "id": str(r.get("id", "") or ""),
        "fuente": "run",
        "tipo": "run",
        "etiqueta": _etiqueta_run(r),
        "marca": str(marca or ""),
        "estado": str(r.get("estado", "") or ""),
        "fecha": str(r.get("fecha_inicio", "") or ""),
        "metricas": _metricas_run(r.get("metricas")),
        "resultado_url": None,
    }


def _items(
    generaciones: list[dict[str, Any]], runs: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Normaliza y MEZCLA generaciones + runs, ordenados por `fecha` desc (luego id)."""
    items = [normalizar_generacion(g) for g in generaciones]
    items.extend(normalizar_run(r) for r in runs)
    items.sort(key=lambda i: (i["fecha"], i["id"]), reverse=True)
    return items


def combinar(
    generaciones: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    *,
    fuente: str = "",
    tipo: str = "",
    offset: int = 0,
    limite: int = 50,
) -> tuple[list[dict[str, Any]], int]:
    """Combina, FILTRA y PAGINA la actividad. Devuelve `(items_pagina, total)`.

    - Normaliza ambas listas, mezcla y ordena por `fecha` desc.
    - Filtra por `fuente` ("generacion"/"run") y/o por `tipo` (un tipo concreto, p.ej.
      "copy" o "run"); un filtro vacio no filtra por ese eje.
    - `total` = nº de items TRAS filtrar (antes de paginar).
    - Pagina con `offset`/`limite` (offset y limite negativos se saturan a 0).
    """
    items = _items(generaciones, runs)
    if fuente:
        items = [i for i in items if i["fuente"] == fuente]
    if tipo:
        items = [i for i in items if i["tipo"] == tipo]
    total = len(items)
    inicio = max(0, int(offset or 0))
    fin = inicio + max(0, int(limite or 0))
    return items[inicio:fin], total


def _redondear(valor: float) -> float:
    """Redondea un coste a 6 decimales (consistente con `agentes.agregados_runs`)."""
    return round(valor, 6)


def agregados(
    generaciones: list[dict[str, Any]], runs: list[dict[str, Any]]
) -> dict[str, Any]:
    """Agrega coste/tokens/items sobre generaciones + runs (sin paginar ni filtrar).

    Devuelve:
      - `total`: `{items, coste_usd, tokens}` sobre TODA la actividad.
      - `por_tipo`: una fila por `tipo` (incluye "run" como un tipo mas),
        `{tipo, items, coste_usd, tokens}`, de mayor a menor coste (luego por tipo).
      - `por_dia`: una fila por dia (`YYYY-MM-DD` de la `fecha`), `{dia, items,
        coste_usd}`, recientes primero.
    """
    items = _items(generaciones, runs)

    total_items = len(items)
    total_coste = 0.0
    total_tokens = 0

    por_tipo: dict[str, dict[str, Any]] = {}
    por_dia: dict[str, dict[str, Any]] = {}

    for it in items:
        m = it["metricas"]
        coste = m["coste_usd"] or 0.0
        tokens = m["tokens"] or 0
        total_coste += coste
        total_tokens += tokens

        t = por_tipo.setdefault(
            it["tipo"], {"tipo": it["tipo"], "items": 0, "coste_usd": 0.0, "tokens": 0}
        )
        t["items"] += 1
        t["coste_usd"] += coste
        t["tokens"] += tokens

        dia = (it["fecha"] or "")[:10]
        d = por_dia.setdefault(dia, {"dia": dia, "items": 0, "coste_usd": 0.0})
        d["items"] += 1
        d["coste_usd"] += coste

    filas_tipo = [
        {"tipo": f["tipo"], "items": f["items"],
         "coste_usd": _redondear(f["coste_usd"]), "tokens": f["tokens"]}
        for f in por_tipo.values()
    ]
    filas_tipo.sort(key=lambda f: (-f["coste_usd"], f["tipo"]))

    filas_dia = [
        {"dia": f["dia"], "items": f["items"], "coste_usd": _redondear(f["coste_usd"])}
        for f in por_dia.values()
    ]
    filas_dia.sort(key=lambda f: f["dia"], reverse=True)

    return {
        "total": {
            "items": total_items,
            "coste_usd": _redondear(total_coste),
            "tokens": total_tokens,
        },
        "por_tipo": filas_tipo,
        "por_dia": filas_dia,
    }
