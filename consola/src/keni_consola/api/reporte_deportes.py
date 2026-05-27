"""API Reporte de deportes: el deck semanal de Claro Sports (PPTX).

Consume la fachada estable `keni_metricas.servicio` (SOLO LECTURA); ya no importa
internals (`config`/`reporte_deck`/`schema`/`fuentes`): top-3 por plataforma por
visualizaciones + interacciones, promocion de las cuentas hermanas y la agenda
editorial de la proxima semana. La agenda es curaduria manual: la pagina la manda
en el cuerpo del POST (por eso preview/export son POST, no GET).

  - `GET  /api/reporte-deportes/opciones`: rangos + cuenta principal + hermanas.
  - `POST /api/reporte-deportes/preview`: datos estructurados (para previsualizar).
  - `POST /api/reporte-deportes/export.pptx`: descarga la presentacion .pptx.
  - `POST /api/reporte-deportes/export.pdf`: descarga el PDF nativo (sin LibreOffice).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from keni_metricas import servicio
from keni_metricas.servicio import CuentaNoEncontrada
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

CUENTA_PRINCIPAL = servicio.CUENTA_DEPORTES_PRINCIPAL
CUENTAS_HERMANAS = servicio.CUENTAS_DEPORTES_HERMANAS
# Rangos que ofrece el deck: la semana cerrada (por defecto, #141) + los rodantes.
RANGOS_VALIDOS = servicio.RANGOS_DEPORTES
RANGO_DEFECTO = servicio.RANGO_DEPORTES_DEFECTO
ETIQUETAS_RANGO = {
    "semana_cerrada": "Semana cerrada (lun–dom)",
    "semana": "Últimos 7 días",
    "mes": "Últimos 30 días",
    "7d": "7 días",
    "30d": "30 días",
}

# Media type oficial de un .pptx (Open XML) y de un PDF.
_MEDIA_PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
_MEDIA_PDF = "application/pdf"


def _validar_rango(rango: str | None) -> str:
    return rango if rango in RANGOS_VALIDOS else RANGO_DEFECTO


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
    return servicio.construir_reporte_deportes(rango=rango, top=top, agenda=agenda)


async def opciones(request: Request) -> Response:
    nombres = dict(servicio.cuentas_disponibles())
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


async def _exportar(request: Request, *, ext: str, media: str, render, error_render: str) -> Response:
    """Comun a pptx/pdf: arma el reporte, renderiza a un temporal y devuelve bytes.

    `render` es el renderer de la fachada (`render_reporte_deportes_pptx`/`_pdf`).
    Captura `RuntimeError` (falta el extra `deck`: python-pptx o reportlab) como 500
    con el mensaje accionable que ya trae la fachada.
    """
    try:
        rep = await _reporte_desde_request(request)
        # el render escribe a disco; usamos un temporal y devolvemos los bytes.
        with tempfile.TemporaryDirectory() as tmp:
            ruta = render(rep, Path(tmp) / f"reporte-deportes.{ext}")
            datos = ruta.read_bytes()
    except (ValueError, CuentaNoEncontrada) as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except RuntimeError as e:  # falta el extra deck (python-pptx / reportlab)
        return JSONResponse({"error": str(e)}, status_code=500)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        return JSONResponse({"error": error_render}, status_code=500)

    nombre = f"reporte-deportes-{rep['rango']}.{ext}"
    return Response(
        datos,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


async def export_pptx(request: Request) -> Response:
    return await _exportar(
        request,
        ext="pptx",
        media=_MEDIA_PPTX,
        render=servicio.render_reporte_deportes_pptx,
        error_render="No se pudo generar la presentación.",
    )


async def export_pdf(request: Request) -> Response:
    return await _exportar(
        request,
        ext="pdf",
        media=_MEDIA_PDF,
        render=servicio.render_reporte_deportes_pdf,
        error_render="No se pudo generar el PDF.",
    )


RUTAS = [
    Route("/api/reporte-deportes/opciones", opciones, methods=["GET"]),
    Route("/api/reporte-deportes/preview", preview, methods=["POST"]),
    Route("/api/reporte-deportes/export.pptx", export_pptx, methods=["POST"]),
    Route("/api/reporte-deportes/export.pdf", export_pdf, methods=["POST"]),
]
