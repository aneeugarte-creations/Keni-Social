"""API Reporte de deportes: el deck semanal de Claro Sports (PPTX).

Reutiliza `keni_metricas.reporte_deck` (no reimplementa nada): top-3 por plataforma
por visualizaciones + interacciones, promocion de las cuentas hermanas y la agenda
editorial de la proxima semana. La agenda es curaduria manual: la pagina la manda
en el cuerpo del POST (por eso preview/export son POST, no GET).

  - `GET  /api/reporte-deportes/opciones`: rangos + cuenta principal + hermanas.
  - `POST /api/reporte-deportes/preview`: datos estructurados (para previsualizar).
  - `POST /api/reporte-deportes/export.pptx`: descarga la presentacion .pptx.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from keni_metricas.config import cargar_config, construir_fuente
from keni_metricas.fuentes.base import CuentaNoEncontrada
from keni_metricas.reporte_deck import (
    CUENTA_PRINCIPAL,
    CUENTAS_HERMANAS,
    construir_reporte_deportes,
    render_pptx,
)
from keni_metricas.schema import RANGOS_DIAS
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

RANGOS_VALIDOS = tuple(RANGOS_DIAS.keys())
ETIQUETAS_RANGO = {"semana": "Semana", "mes": "Mes", "7d": "7 días", "30d": "30 días"}

# Media type oficial de un .pptx (Open XML).
_MEDIA_PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def _validar_rango(rango: str | None) -> str:
    return rango if rango in RANGOS_VALIDOS else "semana"


def _top(valor: object) -> int:
    try:
        return max(1, min(int(valor), 10))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 3


def _agenda_desde_body(body: dict) -> dict | None:
    """Normaliza la agenda del cuerpo a {'principales': [...], 'propios': [...]}.

    Cada evento es {nombre, plan}; se descartan los que no traen nombre. Si no hay
    ningun evento se devuelve None (el deck pone la seccion como pendiente).
    """
    ag = body.get("agenda")
    if not isinstance(ag, dict):
        return None

    def limpiar(lista: object) -> list[dict]:
        out: list[dict] = []
        if isinstance(lista, list):
            for it in lista:
                if isinstance(it, dict) and str(it.get("nombre", "")).strip():
                    out.append(
                        {"nombre": str(it["nombre"]).strip(), "plan": str(it.get("plan", "")).strip()}
                    )
        return out

    principales = limpiar(ag.get("principales"))
    propios = limpiar(ag.get("propios"))
    if not principales and not propios:
        return None
    return {"principales": principales, "propios": propios}


async def _reporte_desde_request(request: Request) -> dict:
    """Lee el cuerpo del POST y arma el reporte. Propaga CuentaNoEncontrada/ValueError."""
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 -- cuerpo vacio o no-JSON: usamos defaults
        body = {}
    if not isinstance(body, dict):
        body = {}
    rango = _validar_rango(body.get("rango"))
    top = _top(body.get("top", 3))
    agenda = _agenda_desde_body(body)
    fuente = construir_fuente(cargar_config())
    return construir_reporte_deportes(fuente, rango=rango, n_por_plataforma=top, agenda=agenda)


async def opciones(request: Request) -> Response:
    fuente = construir_fuente(cargar_config())
    try:
        nombres = {c.id: c.nombre for c in fuente.cuentas()}
    except Exception:  # noqa: BLE001
        nombres = {}
    rangos = [{"id": r, "etiqueta": ETIQUETAS_RANGO.get(r, r)} for r in RANGOS_VALIDOS]
    return JSONResponse(
        {
            "rangos": rangos,
            "cuenta": {"id": CUENTA_PRINCIPAL, "nombre": nombres.get(CUENTA_PRINCIPAL, CUENTA_PRINCIPAL)},
            "hermanas": [{"id": cid, "nombre": nombres.get(cid, cid)} for cid in CUENTAS_HERMANAS],
        }
    )


async def preview(request: Request) -> Response:
    try:
        rep = await _reporte_desde_request(request)
    except (ValueError, CuentaNoEncontrada) as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        return JSONResponse({"error": "No se pudo generar el reporte."}, status_code=500)
    return JSONResponse(rep)


async def export_pptx(request: Request) -> Response:
    try:
        rep = await _reporte_desde_request(request)
        # render_pptx escribe a disco; usamos un temporal y devolvemos los bytes.
        with tempfile.TemporaryDirectory() as tmp:
            ruta = render_pptx(rep, Path(tmp) / "reporte-deportes.pptx")
            datos = ruta.read_bytes()
    except (ValueError, CuentaNoEncontrada) as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except RuntimeError as e:  # falta python-pptx (extra deck)
        return JSONResponse({"error": str(e)}, status_code=500)
    except Exception:  # noqa: BLE001
        return JSONResponse({"error": "No se pudo generar la presentación."}, status_code=500)

    nombre = f"reporte-deportes-{rep['rango']}.pptx"
    return Response(
        datos,
        media_type=_MEDIA_PPTX,
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


RUTAS = [
    Route("/api/reporte-deportes/opciones", opciones, methods=["GET"]),
    Route("/api/reporte-deportes/preview", preview, methods=["POST"]),
    Route("/api/reporte-deportes/export.pptx", export_pptx, methods=["POST"]),
]
