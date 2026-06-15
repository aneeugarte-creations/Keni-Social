"""Endpoints de descarga: reporte (`export.{csv,md,json}`) y Top/Peores de piezas.

`export_csv`/`export_md`/`export_json` reusan la serialización del CLI vía la fachada.
`piezas_export` (Item B) descarga el Top/Peores del periodo en csv|md|json reusando el
MISMO cache que la pantalla `/api/metricas/piezas` (no recalcula nada nuevo).
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

from ._comun import (
    _etiqueta_rango,
    _gate_marca_metricas,
    _log,
    _validar_rango,
    metricas_cache,
    servicio,
)

__all__ = ["export_csv", "export_md", "export_json", "piezas_export"]


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
    `fmt` desconocido cae a csv (igual criterio tolerante que el resto de la API).
    """
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    marca, rechazo = _gate_marca_metricas(request, request.query_params.get("marca") or None)
    if rechazo is not None:
        return PlainTextResponse("Acceso restringido por marca.", status_code=rechazo.status_code)
    fmt = (request.query_params.get("fmt") or "csv").lower()
    if fmt not in ("csv", "md", "json"):
        fmt = "csv"
    try:
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
