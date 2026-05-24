"""Feature Metricas: dashboard consolidado de redes + comparar periodos + export.

Reutiliza las funciones de metricas ya existentes (`config`, `reporte`,
`dashboard`); no reimplementa nada de eso. El dashboard se embebe en un <iframe>
y es autocontenido (CSS inline, sin recursos de red).

Anade dos capacidades sobre el dashboard embebido (que se mantiene tal cual):

  - Comparar DOS rangos (A vs B), opcionalmente acotado a una marca: el endpoint
    `GET /metricas/comparar.json` construye el reporte de cada rango con
    `reporte.construir_reporte` y devuelve una comparativa JSON (total + por
    marca) de visualizaciones, alcance, interacciones y engagement con su
    diferencia/variacion. El JS propio la pinta como tabla, sin red.
  - Descargar el reporte consolidado en Markdown y JSON (ademas del CSV que ya
    existia), reutilizando la MISMA serializacion que el CLI de `reporte`
    (`construir_reporte` + `render_markdown` / `json.dumps`).
"""

from __future__ import annotations

import json
from html import escape
from pathlib import Path

from starlette.requests import Request
from starlette.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    Response,
)
from starlette.routing import Route

from ...config import cargar_config, construir_fuente
from ...dashboard import generar_dashboard
from ...reporte import construir_reporte, render_csv, render_markdown
from ...schema import RANGOS_DIAS
from .. import layout
from . import Feature, RecursoEstatico, features_ordenadas

_ESTATICOS = Path(__file__).parent.parent / "estaticos"

# Rangos validos (misma fuente de verdad que el schema).
RANGOS_VALIDOS = tuple(RANGOS_DIAS.keys())

# Etiquetas legibles de cada rango (para selectores y para la tabla comparativa).
ETIQUETAS_RANGO = {"semana": "Semana", "mes": "Mes", "7d": "7 dias", "30d": "30 dias"}

# Mapeo id-de-cuenta (slug con guion_bajo de la fuente) -> nombre humano legible.
# El `value` del <option> sigue siendo el id crudo que Metricas necesita
# (`claro_sports`, `nacion_gamer`, ...); solo cambia la ETIQUETA visible para que
# coincida con la de Skills (ver `skills.MARCAS`) y el equipo vea los mismos
# nombres en TODA la consola. Ids no listados caen a su `nombre` de la fuente.
NOMBRE_MARCA: dict[str, str] = {
    "unotv": "UnoTV",
    "claro_sports": "Claro Sports",
    "nacion_gamer": "Nación Gamer",
    "piso_15": "Piso 15",
    "fundacion": "Fundación",
}


def _etiqueta_marca(cuenta) -> str:  # noqa: ANN001 -- Cuenta del schema (id, nombre)
    """Nombre humano legible de una cuenta (cae a su `nombre` si no esta mapeada)."""
    return NOMBRE_MARCA.get(cuenta.id, cuenta.nombre)


def _nombre_marca_id(cuenta_id: str, nombres: dict[str, str]) -> str:
    """Nombre legible a partir del id crudo. Prioriza el mapa comun de la consola
    (coherente con Skills) y cae al `nombre` de la fuente, luego al id."""
    return NOMBRE_MARCA.get(cuenta_id) or nombres.get(cuenta_id) or cuenta_id


def _opciones_marca(cuentas) -> list[str]:  # noqa: ANN001
    opciones = ['<option value="">Todas las marcas</option>']
    for c in cuentas:
        opciones.append(
            f'<option value="{escape(c.id)}">{escape(_etiqueta_marca(c))}</option>'
        )
    return opciones


def _opciones_rango(seleccionado: str) -> list[str]:
    opciones = []
    for r in RANGOS_VALIDOS:
        sel = " selected" if r == seleccionado else ""
        etiqueta = ETIQUETAS_RANGO.get(r, r)
        opciones.append(f'<option value="{escape(r)}"{sel}>{escape(etiqueta)}</option>')
    return opciones


def _pagina_metricas() -> str:
    # Selector de marca desde la fuente activa (scoped por config si aplica).
    try:
        fuente = construir_fuente(cargar_config())
        cuentas = fuente.cuentas()
    except Exception:  # noqa: BLE001 -- sin fuente valida igualmente mostramos la pestana
        cuentas = []

    opciones_marca = _opciones_marca(cuentas)
    opciones_rango = _opciones_rango("mes")
    # La comparativa reusa las mismas opciones de marca; los rangos arrancan en
    # combinaciones utiles distintas (semana vs mes) para que tenga sentido al abrir.
    op_marca_cmp = _opciones_marca(cuentas)
    op_rango_a = _opciones_rango("semana")
    op_rango_b = _opciones_rango("mes")

    contenido = f"""
<h1>Metricas</h1>
<p class="intro">Dashboard consolidado de redes (mismas funciones que el reporte). Elige marca y rango.</p>
<div class="controles">
  <label for="sel-marca">Marca
    <select id="sel-marca">{"".join(opciones_marca)}</select>
  </label>
  <label for="sel-rango">Rango
    <select id="sel-rango">{"".join(opciones_rango)}</select>
  </label>
  <a id="enlace-csv" class="boton" href="/metricas/export.csv?rango=mes" download>Descargar CSV</a>
  <a id="enlace-md" class="boton" href="/metricas/export.md?rango=mes" download>Descargar MD</a>
  <a id="enlace-json" class="boton" href="/metricas/export.json?rango=mes" download>Descargar JSON</a>
</div>
<iframe id="iframe-dashboard" class="dashboard" title="Dashboard de metricas"
  sandbox="allow-same-origin" src="about:blank"></iframe>

<section class="comparar" aria-labelledby="titulo-comparar">
  <h2 id="titulo-comparar">Comparar periodos</h2>
  <p class="intro">Compara dos rangos (A vs B): diferencia en visualizaciones, alcance, interacciones y engagement.</p>
  <div class="controles">
    <label for="cmp-marca">Marca
      <select id="cmp-marca">{"".join(op_marca_cmp)}</select>
    </label>
    <label for="cmp-rango-a">Rango A
      <select id="cmp-rango-a">{"".join(op_rango_a)}</select>
    </label>
    <label for="cmp-rango-b">Rango B
      <select id="cmp-rango-b">{"".join(op_rango_b)}</select>
    </label>
    <button type="button" id="btn-comparar" class="boton">Comparar</button>
  </div>
  <div id="cmp-resultado" class="cmp-resultado" aria-live="polite"></div>
</section>
"""
    return layout.render_pagina(
        features=features_ordenadas(),
        activa=FEATURE.id,
        titulo="Metricas",
        contenido=contenido,
        css=FEATURE.css,
        js=FEATURE.js,
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


def _variacion_pct(a: int | float, b: int | float) -> float:
    """Variacion de A respecto a B en %. 0.0 si B es 0 (no se divide entre cero)."""
    return round((a - b) / b * 100, 1) if b else 0.0


def _comparar_totales(total_a: dict, total_b: dict) -> dict:
    """Comparativa del total consolidado de dos reportes.

    Para cada metrica devuelve el valor en A, en B, la diferencia absoluta y la
    variacion en % (engagement tambien lleva su delta en PUNTOS, misma convencion
    que `comparar_periodos`/`variacion_vs_anterior` del MCP)."""
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
            # engagement es un %: la "diferencia" es el delta en PUNTOS.
            "diferencia": round(eng_a - eng_b, 1),
            "variacion_pct": _variacion_pct(eng_a, eng_b),
        }
    )
    return {"metricas": metricas}


def _comparar_por_marca(rep_a: dict, rep_b: dict) -> list[dict]:
    """Comparativa metrica-a-metrica por marca (union de las marcas de A y B).

    Una marca puede no tener datos en un rango; en ese caso su lado vale 0. Usa
    el nombre legible de la marca para que la tabla sea entendible por no tecnicos.
    """
    nombres = {**(rep_b.get("nombres") or {}), **(rep_a.get("nombres") or {})}

    def por_id(rep: dict) -> dict[str, dict]:
        return {f["resumen"]["cuenta"]: f["resumen"] for f in rep.get("cuentas", [])}

    res_a = por_id(rep_a)
    res_b = por_id(rep_b)
    # Orden estable: marcas de A primero (en su orden) y luego las que solo esten en B.
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


def _construir_comparativa(marca: str | None, rango_a: str, rango_b: str) -> dict:
    """Comparativa JSON-serializable de dos rangos (total + por marca)."""
    fuente = _fuente_para(marca)
    rep_a = construir_reporte(fuente, rango_a)
    rep_b = construir_reporte(fuente, rango_b)
    return {
        "marca": marca or "",
        "rango_a": rango_a,
        "rango_b": rango_b,
        "etiqueta_a": ETIQUETAS_RANGO.get(rango_a, rango_a),
        "etiqueta_b": ETIQUETAS_RANGO.get(rango_b, rango_b),
        "total": _comparar_totales(rep_a["total"], rep_b["total"]),
        "por_marca": _comparar_por_marca(rep_a, rep_b),
    }


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


async def metricas_comparar(request: Request) -> Response:
    """Comparativa de dos rangos (A vs B) en JSON. El JS propio la pinta."""
    rango_a = _validar_rango(request.query_params.get("rango_a", "semana"))
    rango_b = _validar_rango(request.query_params.get("rango_b", "mes"))
    marca = request.query_params.get("marca") or None
    try:
        datos = _construir_comparativa(marca, rango_a, rango_b)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al navegador
        return JSONResponse({"error": "No se pudo construir la comparativa."}, status_code=500)
    return JSONResponse(datos)


def _nombre_descarga(rango: str, marca: str | None, ext: str) -> str:
    sufijo = f"-{marca}" if marca else ""
    return f"metricas-{rango}{sufijo}.{ext}"


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
    nombre = _nombre_descarga(rango, marca, "csv")
    cabecera = f'attachment; filename="{nombre}"'
    return Response(
        csv_texto,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": cabecera},
    )


async def metricas_export_md(request: Request) -> Response:
    """Reporte consolidado en Markdown (misma serializacion que el CLI de reporte)."""
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    marca = request.query_params.get("marca") or None
    try:
        fuente = _fuente_para(marca)
        rep = construir_reporte(fuente, rango)
        texto = render_markdown(rep)
    except ValueError as e:
        return PlainTextResponse(f"Error: {e}", status_code=400)
    except Exception:  # noqa: BLE001
        return PlainTextResponse("No se pudo generar el reporte.", status_code=500)
    nombre = _nombre_descarga(rango, marca, "md")
    cabecera = f'attachment; filename="{nombre}"'
    return Response(
        texto,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": cabecera},
    )


async def metricas_export_json(request: Request) -> Response:
    """Reporte consolidado en JSON (misma serializacion que el CLI de reporte)."""
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    marca = request.query_params.get("marca") or None
    try:
        fuente = _fuente_para(marca)
        rep = construir_reporte(fuente, rango)
        texto = json.dumps(rep, ensure_ascii=False, indent=2)
    except ValueError as e:
        return PlainTextResponse(f"Error: {e}", status_code=400)
    except Exception:  # noqa: BLE001
        return PlainTextResponse("No se pudo generar el reporte.", status_code=500)
    nombre = _nombre_descarga(rango, marca, "json")
    cabecera = f'attachment; filename="{nombre}"'
    return Response(
        texto,
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": cabecera},
    )


FEATURE = Feature(
    id="metricas",
    etiqueta="Metricas",
    orden=20,
    descripcion="Dashboard de redes, comparar periodos y descarga del reporte (CSV/MD/JSON).",
    rutas=[
        Route("/metricas", pagina_metricas),
        Route("/metricas/dashboard", metricas_dashboard),
        Route("/metricas/comparar.json", metricas_comparar),
        Route("/metricas/export.csv", metricas_export_csv),
        Route("/metricas/export.md", metricas_export_md),
        Route("/metricas/export.json", metricas_export_json),
    ],
    estaticos=[
        RecursoEstatico("metricas.css", _ESTATICOS / "metricas.css", "text/css; charset=utf-8"),
        RecursoEstatico("metricas.js", _ESTATICOS / "metricas.js", "application/javascript; charset=utf-8"),
    ],
    css=["metricas.css"],
    js=["metricas.js"],
)
