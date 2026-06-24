"""Endpoints de descarga: reporte (`export.{csv,md,json}`) y Top/Peores de piezas.

`export_csv`/`export_md`/`export_json` reusan la serialización del CLI vía la fachada.
`piezas_export` (Item B) descarga el Top/Peores del periodo en csv|md|json reusando el
MISMO cache que la pantalla `/api/metricas/piezas` (no recalcula nada nuevo).
"""

from __future__ import annotations

import asyncio
from datetime import date

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

from ._comun import (
    _etiqueta_rango,
    _gate_marca_metricas,
    _log,
    _validar_rango,
    _validar_redes,
    metricas_cache,
    servicio,
)
from ._digital import ensamblar_datos, meses_ventana, render_csv_digital

__all__ = ["export_csv", "export_md", "export_json", "piezas_export", "export_digitales"]


def _nombre_descarga(rango: str, marca: str | None, ext: str) -> str:
    sufijo = f"-{marca}" if marca else ""
    return f"metricas-{rango}{sufijo}.{ext}"


def _descarga(texto: str, nombre: str, media_type: str) -> Response:
    cabecera = f'attachment; filename="{nombre}"'
    return Response(texto, media_type=media_type, headers={"Content-Disposition": cabecera})


async def export_csv(request: Request) -> Response:
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    marca, rechazo = _gate_marca_metricas(request, request.query_params.get("marca") or None)
    if rechazo is not None:
        # Export devuelve texto plano; traducimos el JSON del gate a un texto/error coherente.
        return PlainTextResponse("Acceso restringido por marca.", status_code=rechazo.status_code)
    try:
        texto = servicio.reporte_csv(rango, marca)
    except ValueError as e:
        return PlainTextResponse(f"Error: {e}", status_code=400)
    except Exception:  # noqa: BLE001
        _log.exception("Fallo al exportar CSV (rango=%s, marca=%s).", rango, marca or "todas")
        return PlainTextResponse("No se pudo generar el CSV.", status_code=500)
    return _descarga(texto, _nombre_descarga(rango, marca, "csv"), "text/csv; charset=utf-8")


async def export_md(request: Request) -> Response:
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    marca, rechazo = _gate_marca_metricas(request, request.query_params.get("marca") or None)
    if rechazo is not None:
        return PlainTextResponse("Acceso restringido por marca.", status_code=rechazo.status_code)
    try:
        texto = servicio.reporte_markdown(rango, marca)
    except ValueError as e:
        return PlainTextResponse(f"Error: {e}", status_code=400)
    except Exception:  # noqa: BLE001
        _log.exception("Fallo al exportar Markdown (rango=%s, marca=%s).", rango, marca or "todas")
        return PlainTextResponse("No se pudo generar el reporte.", status_code=500)
    return _descarga(texto, _nombre_descarga(rango, marca, "md"), "text/markdown; charset=utf-8")


async def export_json(request: Request) -> Response:
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    marca, rechazo = _gate_marca_metricas(request, request.query_params.get("marca") or None)
    if rechazo is not None:
        return PlainTextResponse("Acceso restringido por marca.", status_code=rechazo.status_code)
    try:
        texto = servicio.reporte_json(rango, marca)
    except ValueError as e:
        return PlainTextResponse(f"Error: {e}", status_code=400)
    except Exception:  # noqa: BLE001
        _log.exception("Fallo al exportar JSON (rango=%s, marca=%s).", rango, marca or "todas")
        return PlainTextResponse("No se pudo generar el reporte.", status_code=500)
    return _descarga(texto, _nombre_descarga(rango, marca, "json"), "application/json; charset=utf-8")


# --------------------------------------------------------------------------- #
# Métricas Digitales: reporte mensual por plataforma (el Excel de dirección)    #
# --------------------------------------------------------------------------- #
#
# Reproduce el reporte que el equipo arma a mano cada mes para su dirección: por cada red
# (TikTok/IG/FB/X/YouTube), una serie de 13 meses de cada métrica + la comparativa de los
# dos últimos meses con datos. Lee del MISMO cache que el dashboard, un combo `mes:AAAA-MM`
# por mes (cacheado en Postgres): la primera descarga llena los meses fríos, las siguientes
# son inmediatas. Lo que la fuente no provee (monetización USD, impresiones/horas de YouTube)
# sale como celda vacía, igual que hoy el equipo la completa de otra fuente. Ver `_digital.py`.

# Tope de concurrencia de los fetch por mes (13 reportes + 13 desgloses): evita martillear la
# fuente y saturar el thread-pool del loop en la primera carga (todavía fría).
_CONCURRENCIA_DIGITAL = asyncio.Semaphore(6)


async def _cacheado(fn, rango: str, marca: str | None) -> dict:
    """Lee un combo del cache de métricas (lazy fill) respetando el tope de concurrencia."""
    async with _CONCURRENCIA_DIGITAL:
        payload, _ = await fn(rango, marca)
    return payload


async def export_digitales(request: Request) -> Response:
    """GET /api/metricas/export.digitales?marca=<id>: reporte mensual por plataforma (CSV).

    13 meses por red + comparativa de los dos últimos meses con datos, en el layout exacto
    del Excel del cliente (`;`, números europeos, BOM para Excel es-MX). Necesita una marca
    concreta —el reporte es por marca—; sin ella (vista "todas") devuelve 400.
    """
    marca, _ = _gate_marca_metricas(request, request.query_params.get("marca") or None)
    if not marca:
        return PlainTextResponse(
            "Métricas Digitales necesita una marca concreta. Elígela en el selector.",
            status_code=400,
        )
    ref = date.today()
    meses = meses_ventana(ref)
    tokens = [token for token, _, _, _ in meses]
    desde = f"{meses[0][2]:04d}-{meses[0][3]:02d}-01"
    rango_seguidores = f"rango:{desde}_{ref.isoformat()}"
    try:
        reportes = await asyncio.gather(
            *(_cacheado(metricas_cache.reporte_async, t, marca) for t in tokens)
        )
        desgloses = await asyncio.gather(
            *(_cacheado(metricas_cache.desglose_async, t, marca) for t in tokens)
        )
        seguidores = await _cacheado(metricas_cache.seguidores_async, rango_seguidores, marca)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        _log.exception("Fallo al generar Métricas Digitales (marca=%s).", marca)
        return PlainTextResponse("No se pudo generar el reporte.", status_code=500)
    datos = ensamblar_datos(tokens, reportes, desgloses, seguidores)
    csv = render_csv_digital(datos, meses)
    nombre = f"metricas-digitales-{marca}-{ref:%Y-%m}.csv"
    # BOM para que Excel (es-MX) abra los acentos sin recodificar.
    return _descarga("\ufeff" + csv, nombre, "text/csv; charset=utf-8")


# --------------------------------------------------------------------------- #
# Export del Top/Peores de piezas (Item B)                                      #
# --------------------------------------------------------------------------- #
#
# La analitica de piezas (/api/metricas/piezas) ya trae `top` (mejores 5) y `peores`
# (peores 5) del periodo. Este endpoint las DESCARGA en csv|md|json sin recalcular nada
# nuevo: lee del MISMO cache (lazy fill) que la pantalla y serializa esas dos listas.

# Columnas exportadas por pieza (orden estable, alineado con la tabla de la UI).
_COLUMNAS_PIEZA_EXPORT: tuple[tuple[str, str], ...] = (
    ("grupo", "Grupo"),
    ("titulo", "Título"),
    ("plataforma", "Plataforma"),
    ("publicado", "Publicado"),
    ("visualizaciones", "Visualizaciones"),
    ("interacciones", "Interacciones"),
    ("engagement_pct", "Engagement %"),
    ("url", "URL"),
)


def _filas_piezas_export(payload: dict) -> list[dict]:
    """Aplana `top`/`peores` del payload de piezas a filas con su grupo (Top/Peores)."""
    filas: list[dict] = []
    # La etiqueta del grupo lleva el conteo REAL (Top N / Peores N), derivado de la lista, para
    # no quedar desfasada si cambia el número de piezas.
    for grupo, clave in (("Top", "top"), ("Peores", "peores")):
        items = payload.get(clave, []) or []
        etiqueta = f"{grupo} {len(items)}"
        for p in items:
            filas.append(
                {
                    "grupo": etiqueta,
                    "titulo": p.get("titulo", ""),
                    "plataforma": p.get("plataforma", ""),
                    "publicado": p.get("publicado", ""),
                    "visualizaciones": p.get("visualizaciones", 0),
                    "interacciones": p.get("interacciones", 0),
                    "engagement_pct": p.get("engagement_pct", 0.0),
                    "url": p.get("url") or "",
                }
            )
    return filas


def _piezas_export_csv(filas: list[dict]) -> str:
    import csv
    import io

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([etiqueta for _, etiqueta in _COLUMNAS_PIEZA_EXPORT])
    for fila in filas:
        w.writerow([fila.get(clave, "") for clave, _ in _COLUMNAS_PIEZA_EXPORT])
    return buf.getvalue()


def _piezas_export_md(filas: list[dict], etiqueta_rango: str) -> str:
    cabeceras = [etiqueta for _, etiqueta in _COLUMNAS_PIEZA_EXPORT]
    lineas = [
        f"# Top y peores piezas — {etiqueta_rango}",
        "",
        "| " + " | ".join(cabeceras) + " |",
        "| " + " | ".join("---" for _ in cabeceras) + " |",
    ]
    for fila in filas:
        celdas = [str(fila.get(clave, "")) for clave, _ in _COLUMNAS_PIEZA_EXPORT]
        lineas.append("| " + " | ".join(celdas) + " |")
    return "\n".join(lineas) + "\n"


def _piezas_export_json(payload: dict, filas: list[dict]) -> str:
    import json

    salida = {
        "rango": payload.get("rango", ""),
        "etiqueta_rango": payload.get("etiqueta_rango", ""),
        "cuenta": payload.get("cuenta"),
        "fuente": payload.get("fuente", "muestra"),
        "top": payload.get("top", []),
        "peores": payload.get("peores", []),
        "filas": filas,
    }
    return json.dumps(salida, ensure_ascii=False, indent=2)


async def piezas_export(request: Request) -> Response:
    """GET /api/metricas/piezas-export?fmt=csv|md|json: descarga el Top/Peores de piezas.

    Reusa el cache de `/api/metricas/piezas` (lazy fill en executor): no recalcula nada
    nuevo, solo serializa `top` + `peores` del combo (rango, marca) en el formato pedido.
    `?red=` acota a UNA red (Top/Peores SOLO de esa red; red desconocida →400): igual que
    `/api/metricas/piezas`, sin `red` se sirve de cache y con `red` se recomputa al vuelo
    (en executor), no se cachea cada combinación marca×red. `fmt` desconocido cae a csv
    (igual criterio tolerante que el resto de la API).
    """
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    marca, rechazo = _gate_marca_metricas(request, request.query_params.get("marca") or None)
    if rechazo is not None:
        return PlainTextResponse("Acceso restringido por marca.", status_code=rechazo.status_code)
    fmt = (request.query_params.get("fmt") or "csv").lower()
    if fmt not in ("csv", "md", "json"):
        fmt = "csv"
    try:
        redes = _validar_redes(request.query_params.get("red"))
        if redes:
            payload = await run_in_threadpool(
                servicio.construir_analitica_piezas, rango, marca, redes
            )
        else:
            payload, _ = await metricas_cache.piezas_async(rango, marca)
    except ValueError as e:
        return PlainTextResponse(f"Error: {e}", status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        _log.exception(
            "Fallo al exportar piezas (fmt=%s, rango=%s, marca=%s).", fmt, rango, marca or "todas"
        )
        return PlainTextResponse("No se pudo generar la descarga de piezas.", status_code=500)

    payload = {**payload, "rango": rango, "etiqueta_rango": _etiqueta_rango(rango)}
    filas = _filas_piezas_export(payload)
    nombre = _nombre_descarga(f"piezas-{rango}", marca, fmt)
    if fmt == "csv":
        return _descarga(_piezas_export_csv(filas), nombre, "text/csv; charset=utf-8")
    if fmt == "md":
        return _descarga(
            _piezas_export_md(filas, payload["etiqueta_rango"]),
            nombre,
            "text/markdown; charset=utf-8",
        )
    return _descarga(
        _piezas_export_json(payload, filas), nombre, "application/json; charset=utf-8"
    )
