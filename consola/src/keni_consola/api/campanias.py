"""API Campañas: agrupan piezas YA publicadas por uno o varios hashtags.

Una campaña define un FILTRO (marcas + hashtags); su analítica (KPIs, tendencia, tabla de
piezas, comparativa) se computa AL VUELO en `consola.campanias` sobre el listado de Métricas.
Este módulo solo es la frontera HTTP.
"""

from __future__ import annotations

import csv as _csv
import io
import json as _json
import re
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Route

from .. import campanias, marcas
from .._http_json import leer_json

_MARCAS_IDS = {mid for mid, _ in marcas.opciones()}


# --------------------------------------------------------------------------- #
# Campañas (agrupan piezas por hashtag; analítica al vuelo)                     #
# --------------------------------------------------------------------------- #


def _leer_hashtags(valor: Any) -> tuple[list[str] | None, str | None]:
    """Acepta lista de strings o un string con hashtags separados por espacios/comas."""
    if isinstance(valor, str):
        valor = [t for t in valor.replace(",", " ").split() if t]
    if not isinstance(valor, list) or not all(isinstance(t, str) for t in valor):
        return None, "Los hashtags deben ser una lista de texto."
    return valor, None


async def listar_campanias(request: Request) -> Response:
    """Campañas, opcionalmente filtradas por `?marca=`."""
    marca = request.query_params.get("marca") or None
    if marca and marca not in _MARCAS_IDS:
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)
    return JSONResponse(
        {
            "campanias": campanias.listar_campanias(marca=marca),
            "fuente": campanias.fuente_actual(),
        }
    )


def _leer_marcas(valor: Any) -> tuple[list[str] | None, str | None]:
    """Acepta una lista de ids de marca (o un string único, retrocompat). Valida allowlist."""
    if isinstance(valor, str):
        valor = [valor] if valor else []
    if not isinstance(valor, list) or not all(isinstance(m, str) for m in valor):
        return None, "Las marcas deben ser una lista de ids."
    if not valor:
        return None, "Elige al menos una marca."
    if any(m not in _MARCAS_IDS for m in valor):
        return None, "Marca no permitida."
    return valor, None


async def crear_campania(request: Request) -> Response:
    """Crea una campaña (multimarca): `{marcas: [...], nombre, hashtags: [...]}`."""
    datos = await leer_json(request)
    # `marcas` (lista) es la forma actual; se acepta `marca` (string) por retrocompat.
    marcas_ids, error = _leer_marcas(datos.get("marcas", datos.get("marca")))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)
    nombre = datos.get("nombre")
    if not isinstance(nombre, str):
        return JSONResponse({"error": "El nombre debe ser texto."}, status_code=400)
    tags, error = _leer_hashtags(datos.get("hashtags"))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)
    try:
        cam = campanias.crear_campania(marcas_ids=marcas_ids, nombre=nombre, hashtags=tags)
    except campanias.CampaniaInvalida as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"campania": cam}, status_code=201)


async def detalle_campania(request: Request) -> Response:
    cam = campanias.obtener_campania(request.path_params["campania_id"])
    if cam is None:
        return JSONResponse({"error": "Esa campaña ya no existe."}, status_code=404)
    return JSONResponse({"campania": cam})


async def actualizar_campania(request: Request) -> Response:
    """Edición parcial: `{nombre?, marcas?, hashtags?, activa?}`; 404 si no existe."""
    campania_id = request.path_params["campania_id"]
    datos = await leer_json(request)
    campos: dict[str, Any] = {}
    if "nombre" in datos:
        if not isinstance(datos["nombre"], str):
            return JSONResponse({"error": "El nombre debe ser texto."}, status_code=400)
        campos["nombre"] = datos["nombre"]
    if "marcas" in datos:
        marcas_ids, error = _leer_marcas(datos.get("marcas"))
        if error is not None:
            return JSONResponse({"error": error}, status_code=400)
        campos["marcas"] = marcas_ids
    if "hashtags" in datos:
        tags, error = _leer_hashtags(datos.get("hashtags"))
        if error is not None:
            return JSONResponse({"error": error}, status_code=400)
        campos["hashtags"] = tags
    if "activa" in datos:
        campos["activa"] = bool(datos["activa"])
    try:
        cam = campanias.actualizar_campania(campania_id, campos)
    except campanias.CampaniaInvalida as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    if cam is None:
        return JSONResponse({"error": "Esa campaña ya no existe."}, status_code=404)
    return JSONResponse({"campania": cam})


async def eliminar_campania(request: Request) -> Response:
    if not campanias.borrar_campania(request.path_params["campania_id"]):
        return JSONResponse({"error": "Esa campaña ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Campaña eliminada."})


async def analitica_campania(request: Request) -> Response:
    """Analítica de una campaña en un periodo: `?rango=` (def `mes`). 404 si no existe."""
    campania_id = request.path_params["campania_id"]
    rango = request.query_params.get("rango") or campanias.RANGO_DEF
    try:
        datos = await campanias.analitica_campania(campania_id, rango)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    if datos is None:
        return JSONResponse({"error": "Esa campaña ya no existe."}, status_code=404)
    return JSONResponse(datos)


# --------------------------------------------------------------------------- #
# Descarga de la analítica (csv | md | json)                                    #
# --------------------------------------------------------------------------- #
#
# Reúsa el MISMO cómputo que la pantalla (`campanias.analitica_campania`, cacheado): no
# recalcula nada nuevo, solo serializa el payload en el formato pedido. Tres formatos, igual
# que las descargas de Métricas:
#   - csv  : la tabla de piezas del periodo (una fila por publicación), para Excel/Sheets.
#   - md   : reporte legible (resumen de KPIs + desglose por red + tabla de piezas).
#   - json : el payload íntegro de la analítica.
# `ocultar_ads=1` aplica el "modo cliente": funde lo pagado en las vistas y omite TODO rastro
# de pauta (columna Ads, origen, bloque inorgánico), igual que el toggle de la UI.


def _slug(texto: str, def_: str = "") -> str:
    """Trozo ASCII seguro para el nombre de archivo (la cabecera HTTP es latin-1 y el rango
    puede ser un token con ':' como `rango:2026-01-01_2026-06-01`)."""
    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", (texto or "").strip().lower()).strip("-")
    return s or def_


def _nombre_descarga(cam: dict[str, Any], rango: str, ext: str) -> str:
    return f"campania-{_slug(cam.get('nombre', ''), 'campania')}-{_slug(rango, 'periodo')}.{ext}"


def _descarga(texto: str, nombre: str, media_type: str) -> Response:
    cabecera = f'attachment; filename="{nombre}"'
    return Response(texto, media_type=media_type, headers={"Content-Disposition": cabecera})


def _vistas(p: dict[str, Any], ocultar_ads: bool) -> int:
    """Vistas a MOSTRAR de una pieza: en modo cliente se suman las pagadas a las orgánicas."""
    return int(p.get("visualizaciones") or 0) + (
        int(p.get("visualizaciones_pagadas") or 0) if ocultar_ads else 0
    )


def _origen(p: dict[str, Any]) -> str:
    if p.get("es_inorganico"):
        return "Inorgánico (Ads)"
    return "Cross-post" if p.get("por_cross_post") else "Orgánico"


# Columnas de la tabla de piezas (clave de cálculo, etiqueta). El cálculo de cada celda vive
# en `_celda_pieza`; las columnas de pauta (ads, origen) se omiten en modo cliente.
def _columnas_pieza(ocultar_ads: bool) -> list[tuple[str, str]]:
    cols = [
        ("titulo", "Publicación"),
        ("red", "Red"),
        ("marca", "Marca"),
        ("formato", "Formato"),
        ("publicado", "Publicado"),
        ("vistas", "Vistas"),
    ]
    if not ocultar_ads:
        cols.append(("ads", "Ads"))
    cols += [("interacciones", "Interacciones"), ("engagement_pct", "Engagement %")]
    if not ocultar_ads:
        cols.append(("origen", "Origen"))
    cols.append(("url", "URL"))
    return cols


def _celda_pieza(p: dict[str, Any], clave: str, ocultar_ads: bool) -> Any:
    if clave == "vistas":
        return _vistas(p, ocultar_ads)
    if clave == "ads":
        return int(p.get("visualizaciones_pagadas") or 0)
    if clave == "origen":
        return _origen(p)
    if clave == "engagement_pct":
        return p.get("engagement_pct", 0.0)
    return p.get(clave, "")


def _export_csv(datos: dict[str, Any], ocultar_ads: bool) -> str:
    cols = _columnas_pieza(ocultar_ads)
    buf = io.StringIO()
    w = _csv.writer(buf)
    w.writerow([etiqueta for _, etiqueta in cols])
    for p in datos.get("piezas", []):
        w.writerow([_celda_pieza(p, clave, ocultar_ads) for clave, _ in cols])
    return buf.getvalue()


_ETIQUETAS_KPI = {
    "piezas": "Piezas",
    "visualizaciones": "Vistas",
    "interacciones": "Interacciones",
    "engagement_pct": "Engagement %",
}


def _export_md(datos: dict[str, Any], ocultar_ads: bool) -> str:
    cam = datos["campania"]
    periodo = datos.get("periodo", {})
    hashtags = " ".join(f"#{h}" for h in cam.get("hashtags", []))
    lineas = [
        f"# {cam.get('nombre', 'Campaña')}",
        "",
        f"- **Periodo:** {periodo.get('desde', '')} – {periodo.get('hasta', '')} "
        f"({datos.get('rango', '')})",
        f"- **Marcas:** {', '.join(cam.get('marcas_nombres', [])) or '—'}",
        f"- **Hashtags:** {hashtags or '—'}",
        f"- **Fuente:** {datos.get('fuente') or '—'}",
        f"- **Generado:** {datos.get('generado_en', '')}",
        "",
        "## Resumen",
        "",
    ]
    kpis = datos.get("kpis", {})
    if ocultar_ads:
        # Modo cliente: solo el valor (sin comparativa), con las vistas ya fundidas.
        inorg_vistas = int(datos.get("inorganico", {}).get("visualizaciones") or 0)
        vistas = int(kpis.get("visualizaciones") or 0) + inorg_vistas
        lineas += ["| Métrica | Valor |", "| --- | ---: |"]
        lineas.append(f"| Piezas | {kpis.get('piezas', 0)} |")
        lineas.append(f"| Vistas | {vistas} |")
        lineas.append(f"| Interacciones | {kpis.get('interacciones', 0)} |")
        lineas.append(f"| Engagement % | {kpis.get('engagement_pct', 0.0)} |")
    else:
        comp = datos.get("comparativa", {})
        lineas += [
            "| Métrica | Actual | Anterior | Δ | Variación % |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
        for clave in ("piezas", "visualizaciones", "interacciones", "engagement_pct"):
            c = comp.get(clave, {})
            var = c.get("variacion_pct")
            lineas.append(
                f"| {_ETIQUETAS_KPI[clave]} | {c.get('actual', 0)} | {c.get('anterior', 0)} "
                f"| {c.get('delta', 0)} | {'—' if var is None else var} |"
            )
        inorg = datos.get("inorganico", {})
        if int(inorg.get("visualizaciones") or 0) > 0:
            lineas += [
                "",
                "## Inorgánico (Meta Ads)",
                "",
                f"- **Vistas pagadas:** {inorg.get('visualizaciones', 0)}",
                f"- **Gasto:** {inorg.get('gasto', 0)} {inorg.get('moneda', '')}".rstrip(),
                f"- **Clics:** {inorg.get('clics', 0)}",
                f"- **Campañas:** {inorg.get('campanias', 0)}",
            ]

    desglose = datos.get("desglose_red", [])
    if desglose:
        lineas += [
            "",
            "## Por red",
            "",
            "| Red | Piezas | Vistas | Interacciones | Me gusta | Comentarios | "
            "Compartidos | Guardados | Engagement % |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for f in desglose:
            lineas.append(
                f"| {f.get('red', '') or '—'} | {f.get('piezas', 0)} | {f.get('visualizaciones', 0)} "
                f"| {f.get('interacciones', 0)} | {f.get('likes', 0)} | {f.get('comentarios', 0)} "
                f"| {f.get('compartidos', 0)} | {f.get('guardados', 0)} | {f.get('engagement_pct', 0.0)} |"
            )

    piezas = datos.get("piezas", [])
    cols = _columnas_pieza(ocultar_ads)
    lineas += [
        "",
        f"## Piezas del periodo ({len(piezas)})",
        "",
        "| " + " | ".join(etiqueta for _, etiqueta in cols) + " |",
        "| " + " | ".join("---" for _ in cols) + " |",
    ]
    for p in piezas:
        celdas = [str(_celda_pieza(p, clave, ocultar_ads)).replace("|", "\\|") for clave, _ in cols]
        lineas.append("| " + " | ".join(celdas) + " |")
    return "\n".join(lineas) + "\n"


def _payload_modo_cliente(datos: dict[str, Any]) -> dict[str, Any]:
    """Copia del payload SIN rastro de pauta: vistas fundidas, sin columnas/bloque de Ads."""
    salida = dict(datos)
    salida.pop("inorganico", None)
    piezas = []
    for p in datos.get("piezas", []):
        q = dict(p)
        q["visualizaciones"] = _vistas(p, ocultar_ads=True)
        q.pop("visualizaciones_pagadas", None)
        q.pop("es_inorganico", None)
        piezas.append(q)
    salida["piezas"] = piezas
    return salida


def _export_json(datos: dict[str, Any], ocultar_ads: bool) -> str:
    salida = _payload_modo_cliente(datos) if ocultar_ads else datos
    return _json.dumps(salida, ensure_ascii=False, indent=2)


async def exportar_campania(request: Request) -> Response:
    """GET /api/campanias/{id}/export?fmt=csv|md|json&rango=&ocultar_ads=1: descarga la analítica.

    Reúsa `campanias.analitica_campania` (cacheado): no recalcula nada. `fmt` desconocido cae a
    csv (criterio tolerante, igual que Métricas). 404 si la campaña no existe.
    """
    campania_id = request.path_params["campania_id"]
    rango = request.query_params.get("rango") or campanias.RANGO_DEF
    fmt = (request.query_params.get("fmt") or "csv").lower()
    if fmt not in ("csv", "md", "json"):
        fmt = "csv"
    ocultar_ads = request.query_params.get("ocultar_ads") in ("1", "true")
    try:
        datos = await campanias.analitica_campania(campania_id, rango)
    except ValueError as e:
        return PlainTextResponse(f"Error: {e}", status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        return PlainTextResponse("No se pudo generar la descarga de la campaña.", status_code=500)
    if datos is None:
        return PlainTextResponse("Esa campaña ya no existe.", status_code=404)

    nombre = _nombre_descarga(datos["campania"], rango, fmt)
    if fmt == "md":
        return _descarga(_export_md(datos, ocultar_ads), nombre, "text/markdown; charset=utf-8")
    if fmt == "json":
        return _descarga(_export_json(datos, ocultar_ads), nombre, "application/json; charset=utf-8")
    return _descarga(_export_csv(datos, ocultar_ads), nombre, "text/csv; charset=utf-8")


# --------------------------------------------------------------------------- #
# Enlaces públicos (capability-URL de solo lectura)                             #
# --------------------------------------------------------------------------- #
#
# Un token indescifrable mapea a UNA campaña y un periodo+modo congelados. El endpoint
# `/api/publico/campania/{token}` es PÚBLICO (exento del gate de sesión en `seguridad.py`):
# devuelve SOLO esa analítica, marcado `noindex`. Crear/listar/revocar enlaces exige sesión.

_CABECERAS_PUBLICAS = {"X-Robots-Tag": "noindex"}


def _publico_modo_cliente(datos: dict[str, Any]) -> dict[str, Any]:
    """Versión SIN rastro de pauta CONSERVANDO la forma del payload (el panel la consume):
    funde lo pagado en las vistas (KPI + por pieza) y deja Ads/inorgánico a cero. A diferencia
    de `_payload_modo_cliente` (export), no borra claves: el panel público las espera."""
    inorg_vis = int(datos.get("inorganico", {}).get("visualizaciones") or 0)
    kpis = dict(datos.get("kpis", {}))
    kpis["visualizaciones"] = int(kpis.get("visualizaciones") or 0) + inorg_vis
    piezas = []
    for p in datos.get("piezas", []):
        q = dict(p)
        q["visualizaciones"] = _vistas(p, ocultar_ads=True)
        q["visualizaciones_pagadas"] = 0
        q["es_inorganico"] = False
        piezas.append(q)
    return {
        **datos,
        "kpis": kpis,
        "piezas": piezas,
        "inorganico": {"visualizaciones": 0, "gasto": 0, "clics": 0, "campanias": 0, "moneda": ""},
    }


async def analitica_publica(request: Request) -> Response:
    """GET /api/publico/campania/{token}: analítica de UNA campaña, sin login (solo lectura).

    El token resuelve a la campaña + periodo + modo congelados; si está revocado/caducado o no
    existe -> 404. Aplica el modo cliente del enlace (sin pauta). `noindex` para que no se indexe.
    """
    enlace = campanias.enlace_publico_vigente(request.path_params["token"])
    if enlace is None:
        return JSONResponse(
            {"error": "Este enlace ya no es válido."}, status_code=404, headers=_CABECERAS_PUBLICAS
        )
    try:
        datos = await campanias.analitica_campania(enlace["campania_id"], enlace["rango"])
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al público
        return JSONResponse(
            {"error": "No se pudo cargar el informe."},
            status_code=500,
            headers=_CABECERAS_PUBLICAS,
        )
    if datos is None:
        return JSONResponse(
            {"error": "Esta campaña ya no existe."}, status_code=404, headers=_CABECERAS_PUBLICAS
        )
    if enlace["ocultar_ads"]:
        datos = _publico_modo_cliente(datos)
    return JSONResponse(
        {**datos, "ocultar_ads": bool(enlace["ocultar_ads"])}, headers=_CABECERAS_PUBLICAS
    )


async def crear_enlace_publico(request: Request) -> Response:
    """POST /api/campanias/{id}/enlaces: crea un enlace público `{rango?, ocultar_ads?}`."""
    campania_id = request.path_params["campania_id"]
    datos = await leer_json(request)
    rango = datos.get("rango") or campanias.RANGO_DEF
    if not isinstance(rango, str):
        return JSONResponse({"error": "El rango debe ser texto."}, status_code=400)
    ocultar_ads = bool(datos.get("ocultar_ads", True))
    enlace = campanias.crear_enlace_publico(campania_id, rango=rango, ocultar_ads=ocultar_ads)
    if enlace is None:
        return JSONResponse({"error": "Esa campaña ya no existe."}, status_code=404)
    return JSONResponse({"enlace": enlace}, status_code=201)


async def listar_enlaces_publicos(request: Request) -> Response:
    """GET /api/campanias/{id}/enlaces: enlaces públicos de la campaña (gestión)."""
    campania_id = request.path_params["campania_id"]
    return JSONResponse({"enlaces": campanias.listar_enlaces_publicos(campania_id)})


async def revocar_enlace_publico(request: Request) -> Response:
    """DELETE /api/campanias/{id}/enlaces/{enlace_id}: revoca un enlace (corta el acceso)."""
    campania_id = request.path_params["campania_id"]
    enlace_id = request.path_params["enlace_id"]
    if not campanias.revocar_enlace_publico(enlace_id, campania_id):
        return JSONResponse({"error": "Ese enlace ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Enlace revocado."})


RUTAS = [
    Route("/api/campanias", listar_campanias, methods=["GET"]),
    Route("/api/campanias", crear_campania, methods=["POST"]),
    Route("/api/campanias/{campania_id}", detalle_campania, methods=["GET"]),
    Route("/api/campanias/{campania_id}", actualizar_campania, methods=["PUT"]),
    Route("/api/campanias/{campania_id}", eliminar_campania, methods=["DELETE"]),
    Route(
        "/api/campanias/{campania_id}/analitica",
        analitica_campania,
        methods=["GET"],
    ),
    Route(
        "/api/campanias/{campania_id}/export",
        exportar_campania,
        methods=["GET"],
    ),
    # Enlaces públicos: el endpoint de lectura es PÚBLICO (exento en seguridad.py); gestión con sesión.
    Route("/api/publico/campania/{token}", analitica_publica, methods=["GET"]),
    Route("/api/campanias/{campania_id}/enlaces", listar_enlaces_publicos, methods=["GET"]),
    Route("/api/campanias/{campania_id}/enlaces", crear_enlace_publico, methods=["POST"]),
    Route(
        "/api/campanias/{campania_id}/enlaces/{enlace_id}",
        revocar_enlace_publico,
        methods=["DELETE"],
    ),
]
