"""API Metricas: opciones, reporte consolidado, comparativa de rangos y export.

Consume la fachada estable `keni_metricas.servicio` (SOLO LECTURA); ya no importa
internals (`config`/`reporte`/`schema`). El SPA dibuja el dashboard a partir de
`/api/metricas/reporte` (ya no hay endpoint HTML de dashboard).

  - `/api/metricas/opciones`: marcas + rangos para poblar los selectores.
  - `/api/metricas/reporte`: total consolidado + por cuenta (nombres resueltos).
  - `/api/metricas/comparar`: comparativa A vs B (total + por marca).
  - `/api/metricas/export.{csv,md,json}`: descargas (misma serializacion que el CLI).
"""

from __future__ import annotations

from keni_metricas import servicio
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Route

from .. import marcas

# Rangos validos: contrato de la fachada (no se importa el schema directamente).
RANGOS_VALIDOS = servicio.RANGOS_VALIDOS

# Etiquetas legibles de cada rango.
ETIQUETAS_RANGO = {"semana": "Semana", "mes": "Mes", "7d": "7 días", "30d": "30 días"}


def _nombre_marca_id(cuenta_id: str, nombres: dict[str, str]) -> str:
    """Nombre legible: prioriza el catalogo unico de marcas, cae al nombre de la
    fuente de datos y luego al propio id.

    `cuenta_id` viene de la fuente de metricas, asi que esta en forma `id_metricas`
    (guion_bajo): se resuelve por esa frontera, no por el id canonico.
    """
    etiqueta = marcas.etiqueta_por_id_metricas(cuenta_id)
    if etiqueta != cuenta_id:
        return etiqueta
    return nombres.get(cuenta_id) or cuenta_id


def _validar_rango(rango: str) -> str:
    return rango if rango in RANGOS_VALIDOS else "mes"


def _variacion_pct(a: int | float, b: int | float) -> float:
    """Variacion de A respecto a B en %. 0.0 si B es 0 (no divide entre cero)."""
    return round((a - b) / b * 100, 1) if b else 0.0


def _fuente_combinada(rep_a: dict, rep_b: dict) -> str:
    """Fuente de una comparativa A vs B: "muestra" si CUALQUIERA de los dos lo es.

    La comparativa cruza dos reportes; basta con que uno sea de datos de muestra para
    que el resultado deba advertirse como muestra (no se mezclan datos ficticios con
    reales sin que la UI lo marque). Cae a "muestra" por prudencia si falta el campo
    (riesgo operativo del piloto AMX), igual que `/reporte`.
    """
    fuente_a = rep_a.get("fuente") or "muestra"
    fuente_b = rep_b.get("fuente") or "muestra"
    if "muestra" in (fuente_a, fuente_b):
        return "muestra"
    return fuente_a


def _comparar_totales(total_a: dict, total_b: dict) -> dict:
    """Comparativa del total consolidado de dos reportes (4 metricas)."""
    metricas = []
    for clave in ("visualizaciones", "alcance", "interacciones"):
        va = total_a.get(clave, 0)
        vb = total_b.get(clave, 0)
        metricas.append(
            {
                "metrica": clave,
                "a": va,
                "b": vb,
                "diferencia": va - vb,
                "variacion_pct": _variacion_pct(va, vb),
            }
        )
    eng_a = total_a.get("engagement_pct", 0.0)
    eng_b = total_b.get("engagement_pct", 0.0)
    metricas.append(
        {
            "metrica": "engagement_pct",
            "a": eng_a,
            "b": eng_b,
            "diferencia": round(eng_a - eng_b, 1),
            "variacion_pct": _variacion_pct(eng_a, eng_b),
        }
    )
    return {"metricas": metricas}


def _comparar_por_marca(rep_a: dict, rep_b: dict) -> list[dict]:
    """Comparativa metrica-a-metrica por marca (union de las marcas de A y B)."""
    nombres = {**(rep_b.get("nombres") or {}), **(rep_a.get("nombres") or {})}

    def por_id(rep: dict) -> dict[str, dict]:
        return {f["resumen"]["cuenta"]: f["resumen"] for f in rep.get("cuentas", [])}

    res_a = por_id(rep_a)
    res_b = por_id(rep_b)
    ids: list[str] = list(res_a.keys())
    for cid in res_b:
        if cid not in res_a:
            ids.append(cid)

    filas = []
    for cid in ids:
        ra = res_a.get(cid, {})
        rb = res_b.get(cid, {})
        filas.append(
            {
                "marca_id": cid,
                "marca": _nombre_marca_id(cid, nombres),
                "comparativa": _comparar_totales(
                    {k: ra.get(k, 0) for k in ("visualizaciones", "alcance", "interacciones", "engagement_pct")},
                    {k: rb.get(k, 0) for k in ("visualizaciones", "alcance", "interacciones", "engagement_pct")},
                )["metricas"],
            }
        )
    return filas


def _reporte_serializable(rep: dict, rango: str, marca: str | None) -> dict:
    """Forma JSON del reporte para el SPA: total + cuentas con nombres resueltos."""
    nombres = rep.get("nombres") or {}
    cuentas = []
    for fila in rep.get("cuentas", []):
        r = fila["resumen"]
        cid = r["cuenta"]
        cuentas.append(
            {
                "marca_id": cid,
                "marca": _nombre_marca_id(cid, nombres),
                "visualizaciones": r.get("visualizaciones", 0),
                "alcance": r.get("alcance", 0),
                "interacciones": r.get("interacciones", 0),
                "engagement_pct": r.get("engagement_pct", 0.0),
            }
        )
    t = rep.get("total") or {}
    return {
        "rango": rango,
        "etiqueta_rango": ETIQUETAS_RANGO.get(rango, rango),
        "marca": marca or "",
        # Fuente de los datos: "muestra" (ficticios) o "real". La UI pinta un badge
        # de advertencia con esto para que no se confundan datos de muestra con
        # reales (riesgo operativo del piloto AMX). Cae a "muestra" por prudencia.
        "fuente": rep.get("fuente") or "muestra",
        "total": {
            "visualizaciones": t.get("visualizaciones", 0),
            "alcance": t.get("alcance", 0),
            "interacciones": t.get("interacciones", 0),
            "engagement_pct": t.get("engagement_pct", 0.0),
        },
        "cuentas": cuentas,
    }


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #


async def opciones(request: Request) -> Response:
    # La frontera con metricas habla en `id_metricas` (guion_bajo): este `id` es el
    # que viaja como `?marca=` y acota la fuente (FuenteScoped), no el id canonico.
    marcas_lista = [{"id": mid, "nombre": etiqueta} for mid, etiqueta in marcas.opciones_metricas()]
    rangos = [{"id": r, "etiqueta": ETIQUETAS_RANGO.get(r, r)} for r in RANGOS_VALIDOS]
    return JSONResponse({"marcas": marcas_lista, "rangos": rangos})


async def reporte(request: Request) -> Response:
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    marca = request.query_params.get("marca") or None
    try:
        rep = servicio.construir_reporte(rango, marca)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        return JSONResponse({"error": "No se pudo generar el reporte."}, status_code=500)
    return JSONResponse(_reporte_serializable(rep, rango, marca))


async def comparar(request: Request) -> Response:
    rango_a = _validar_rango(request.query_params.get("rango_a", "semana"))
    rango_b = _validar_rango(request.query_params.get("rango_b", "mes"))
    marca = request.query_params.get("marca") or None
    try:
        rep_a = servicio.construir_reporte(rango_a, marca)
        rep_b = servicio.construir_reporte(rango_b, marca)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        return JSONResponse({"error": "No se pudo construir la comparativa."}, status_code=500)
    return JSONResponse(
        {
            "marca": marca or "",
            "rango_a": rango_a,
            "rango_b": rango_b,
            "etiqueta_a": ETIQUETAS_RANGO.get(rango_a, rango_a),
            "etiqueta_b": ETIQUETAS_RANGO.get(rango_b, rango_b),
            # Fuente de los datos de la comparativa: "muestra" si cualquiera de los dos
            # reportes lo es. La UI pinta un badge de advertencia con esto (N6, igual que
            # /reporte) para no confundir datos de muestra con reales (piloto AMX).
            "fuente": _fuente_combinada(rep_a, rep_b),
            "total": _comparar_totales(rep_a["total"], rep_b["total"]),
            "por_marca": _comparar_por_marca(rep_a, rep_b),
        }
    )


def _nombre_descarga(rango: str, marca: str | None, ext: str) -> str:
    sufijo = f"-{marca}" if marca else ""
    return f"metricas-{rango}{sufijo}.{ext}"


def _descarga(texto: str, nombre: str, media_type: str) -> Response:
    cabecera = f'attachment; filename="{nombre}"'
    return Response(texto, media_type=media_type, headers={"Content-Disposition": cabecera})


async def export_csv(request: Request) -> Response:
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    marca = request.query_params.get("marca") or None
    try:
        texto = servicio.reporte_csv(rango, marca)
    except ValueError as e:
        return PlainTextResponse(f"Error: {e}", status_code=400)
    except Exception:  # noqa: BLE001
        return PlainTextResponse("No se pudo generar el CSV.", status_code=500)
    return _descarga(texto, _nombre_descarga(rango, marca, "csv"), "text/csv; charset=utf-8")


async def export_md(request: Request) -> Response:
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    marca = request.query_params.get("marca") or None
    try:
        texto = servicio.reporte_markdown(rango, marca)
    except ValueError as e:
        return PlainTextResponse(f"Error: {e}", status_code=400)
    except Exception:  # noqa: BLE001
        return PlainTextResponse("No se pudo generar el reporte.", status_code=500)
    return _descarga(texto, _nombre_descarga(rango, marca, "md"), "text/markdown; charset=utf-8")


async def export_json(request: Request) -> Response:
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    marca = request.query_params.get("marca") or None
    try:
        texto = servicio.reporte_json(rango, marca)
    except ValueError as e:
        return PlainTextResponse(f"Error: {e}", status_code=400)
    except Exception:  # noqa: BLE001
        return PlainTextResponse("No se pudo generar el reporte.", status_code=500)
    return _descarga(texto, _nombre_descarga(rango, marca, "json"), "application/json; charset=utf-8")


RUTAS = [
    Route("/api/metricas/opciones", opciones, methods=["GET"]),
    Route("/api/metricas/reporte", reporte, methods=["GET"]),
    Route("/api/metricas/comparar", comparar, methods=["GET"]),
    Route("/api/metricas/export.csv", export_csv, methods=["GET"]),
    Route("/api/metricas/export.md", export_md, methods=["GET"]),
    Route("/api/metricas/export.json", export_json, methods=["GET"]),
]
