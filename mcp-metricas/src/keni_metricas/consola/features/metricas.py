"""Feature Metricas: dashboard consolidado de redes + export CSV.

Reutiliza las funciones de metricas ya existentes (`config`, `reporte`,
`dashboard`); no reimplementa nada de eso. El dashboard se embebe en un <iframe>
y es autocontenido (CSS inline, sin recursos de red).
"""

from __future__ import annotations

from html import escape

from starlette.requests import Request
from starlette.responses import HTMLResponse, PlainTextResponse, Response
from starlette.routing import Route

from ...config import cargar_config, construir_fuente
from ...dashboard import generar_dashboard
from ...reporte import construir_reporte, render_csv
from ...schema import RANGOS_DIAS
from .. import layout
from . import Feature, features_ordenadas

# Rangos validos (misma fuente de verdad que el schema).
RANGOS_VALIDOS = tuple(RANGOS_DIAS.keys())


def _pagina_metricas() -> str:
    # Selector de marca desde la fuente activa (scoped por config si aplica).
    try:
        fuente = construir_fuente(cargar_config())
        cuentas = fuente.cuentas()
    except Exception:  # noqa: BLE001 -- sin fuente valida igualmente mostramos la pestana
        cuentas = []

    opciones_marca = ['<option value="">Todas las marcas</option>']
    for c in cuentas:
        opciones_marca.append(f'<option value="{escape(c.id)}">{escape(c.nombre)}</option>')

    etiquetas_rango = {"semana": "Semana", "mes": "Mes", "7d": "7 dias", "30d": "30 dias"}
    opciones_rango = []
    for r in RANGOS_VALIDOS:
        sel = " selected" if r == "mes" else ""
        opciones_rango.append(f'<option value="{escape(r)}"{sel}>{escape(etiquetas_rango.get(r, r))}</option>')

    contenido = f"""
<h1>Metricas</h1>
<p class="intro">Dashboard consolidado de redes (mismas funciones que el reporte). Elige marca y rango.</p>
<div class="controles">
  <label>Marca
    <select id="sel-marca">{"".join(opciones_marca)}</select>
  </label>
  <label>Rango
    <select id="sel-rango">{"".join(opciones_rango)}</select>
  </label>
  <a id="enlace-csv" class="boton" href="/metricas/export.csv?rango=mes" download>Descargar CSV</a>
</div>
<iframe id="iframe-dashboard" class="dashboard" title="Dashboard de metricas" src="about:blank"></iframe>
"""
    return layout.render_pagina(
        features=features_ordenadas(),
        activa=FEATURE.id,
        titulo="Metricas",
        contenido=contenido,
    )


def _fuente_para(marca: str | None):
    """Fuente activa, opcionalmente acotada a UNA marca (selector de la pestana)."""
    from ...config import FuenteScoped

    fuente = construir_fuente(cargar_config())
    if marca:
        return FuenteScoped(fuente, [marca])
    return fuente


def _validar_rango(rango: str) -> str:
    return rango if rango in RANGOS_VALIDOS else "mes"


def _pagina_error(mensaje: str) -> str:
    return layout.render_pagina(
        features=features_ordenadas(),
        activa=FEATURE.id,
        titulo="Metricas",
        contenido=f'<p class="aviso-global" role="alert">{escape(mensaje)}</p>',
    )


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #


async def pagina_metricas(request: Request) -> Response:
    return HTMLResponse(_pagina_metricas())


async def metricas_dashboard(request: Request) -> Response:
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    marca = request.query_params.get("marca") or None
    try:
        fuente = _fuente_para(marca)
        html = generar_dashboard(fuente, rango)
    except ValueError as e:
        return HTMLResponse(_pagina_error(str(e)), status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al navegador
        return HTMLResponse(_pagina_error("No se pudo generar el dashboard."), status_code=500)
    return HTMLResponse(html)


async def metricas_export_csv(request: Request) -> Response:
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    marca = request.query_params.get("marca") or None
    try:
        fuente = _fuente_para(marca)
        rep = construir_reporte(fuente, rango)
        csv_texto = render_csv(rep)
    except ValueError as e:
        return PlainTextResponse(f"Error: {e}", status_code=400)
    except Exception:  # noqa: BLE001
        return PlainTextResponse("No se pudo generar el CSV.", status_code=500)
    sufijo = f"-{marca}" if marca else ""
    nombre = f"metricas-{rango}{sufijo}.csv"
    cabecera = f'attachment; filename="{nombre}"'
    return Response(
        csv_texto,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": cabecera},
    )


FEATURE = Feature(
    id="metricas",
    etiqueta="Metricas",
    orden=20,
    descripcion="Dashboard consolidado de redes y descarga de datos en CSV.",
    rutas=[
        Route("/metricas", pagina_metricas),
        Route("/metricas/dashboard", metricas_dashboard),
        Route("/metricas/export.csv", metricas_export_csv),
    ],
)
