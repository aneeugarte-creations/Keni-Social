"""API Metricas: opciones, reporte consolidado, comparativa de rangos y export.

Consume la fachada estable `keni_metricas.servicio` (SOLO LECTURA); ya no importa
internals (`config`/`reporte`/`schema`). El SPA dibuja el dashboard a partir de
`/api/metricas/reporte` (ya no hay endpoint HTML de dashboard).

  - `/api/metricas/opciones`: marcas + rangos para poblar los selectores.
  - `/api/metricas/reporte`: total consolidado + por cuenta (nombres resueltos).
  - `/api/metricas/comparar`: comparativa A vs B (total + por marca).
  - `/api/metricas/analisis`: análisis diario con narrativa "qué cambió y por qué"
    + siguiente paso (F6/#146); ensambla reporte + picos en una lectura accionable.
  - `/api/metricas/export.{csv,md,json}`: descargas (misma serializacion que el CLI).
"""

from __future__ import annotations

import asyncio

from keni_metricas import servicio
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Route

from .. import marcas, metricas_cache, metricas_pieza, repos

# Rangos validos: contrato de la fachada (no se importa el schema directamente).
RANGOS_VALIDOS = servicio.RANGOS_VALIDOS

# Etiqueta legible de un rango (preset o token mes:/rango:). Delega en la fachada para
# que presets y tokens (mes:AAAA-MM, rango:AAAA-MM-DD_AAAA-MM-DD) tengan una sola fuente.
def _etiqueta_rango(rango: str) -> str:
    return servicio.etiqueta_rango(rango)


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
    """Acepta presets y tokens de fecha; lo demás cae a 'mes'.

    Los tokens (`mes:AAAA-MM`, `rango:AAAA-MM-DD_AAAA-MM-DD`) pasan tal cual: la fachada
    valida su formato y lanza ValueError (→400) si está mal. Un rango basura cualquiera
    cae a 'mes' (compat con el comportamiento previo, sin romper la vista).
    """
    if rango in RANGOS_VALIDOS:
        return rango
    if rango.startswith(("mes:", "rango:")):
        return rango
    return "mes"


def _variacion_pct(a: float | None, b: float | None) -> float | None:
    """Variacion de A respecto a B en %. None si falta algun dato (#138: alcance/
    engagement pueden ser n/d); 0.0 si B es 0 (no divide entre cero)."""
    if a is None or b is None:
        return None
    return round((a - b) / b * 100, 1) if b else 0.0


def _delta(a: float | None, b: float | None) -> float | None:
    """Diferencia A-B tolerante a None (#138: alcance/engagement pueden ser n/d)."""
    if a is None or b is None:
        return None
    return a - b


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
        va = total_a.get(clave)
        vb = total_b.get(clave)
        metricas.append(
            {
                "metrica": clave,
                "a": va,
                "b": vb,
                "diferencia": _delta(va, vb),
                "variacion_pct": _variacion_pct(va, vb),
            }
        )
    eng_a = total_a.get("engagement_pct")
    eng_b = total_b.get("engagement_pct")
    eng_d = _delta(eng_a, eng_b)
    metricas.append(
        {
            "metrica": "engagement_pct",
            "a": eng_a,
            "b": eng_b,
            "diferencia": round(eng_d, 1) if eng_d is not None else None,
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
        "etiqueta_rango": _etiqueta_rango(rango),
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
    rangos = [{"id": r, "etiqueta": _etiqueta_rango(r)} for r in RANGOS_VALIDOS]
    return JSONResponse({"marcas": marcas_lista, "rangos": rangos})


async def reporte(request: Request) -> Response:
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    marca = request.query_params.get("marca") or None
    try:
        # Lee de cache (instantaneo); si el combo falta, lo calcula al vuelo y lo guarda.
        # En executor: un combo frío golpea la API externa y NO debe bloquear el loop.
        rep, generado_en = await metricas_cache.reporte_async(rango, marca)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        return JSONResponse({"error": "No se pudo generar el reporte."}, status_code=500)
    salida = _reporte_serializable(rep, rango, marca)
    salida["generado_en"] = generado_en
    return JSONResponse(salida)


async def comparar(request: Request) -> Response:
    rango_a = _validar_rango(request.query_params.get("rango_a", "semana"))
    rango_b = _validar_rango(request.query_params.get("rango_b", "mes"))
    marca = request.query_params.get("marca") or None
    try:
        # Ambos reportes salen de cache (lazy fill); la comparativa se computa en memoria.
        # En executor y CONCURRENTES (gather): combos fríos no bloquean el event loop y,
        # si ambos están fríos, se calculan en paralelo en vez de en serie.
        (rep_a, gen_a), (rep_b, gen_b) = await asyncio.gather(
            metricas_cache.reporte_async(rango_a, marca),
            metricas_cache.reporte_async(rango_b, marca),
        )
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        return JSONResponse({"error": "No se pudo construir la comparativa."}, status_code=500)
    return JSONResponse(
        {
            "marca": marca or "",
            "rango_a": rango_a,
            "rango_b": rango_b,
            "etiqueta_a": _etiqueta_rango(rango_a),
            "etiqueta_b": _etiqueta_rango(rango_b),
            # El mas antiguo de los dos: la comparativa es tan fresca como su dato mas viejo.
            "generado_en": min(gen_a, gen_b),
            # Fuente de los datos de la comparativa: "muestra" si cualquiera de los dos
            # reportes lo es. La UI pinta un badge de advertencia con esto (N6, igual que
            # /reporte) para no confundir datos de muestra con reales (piloto AMX).
            "fuente": _fuente_combinada(rep_a, rep_b),
            "total": _comparar_totales(rep_a["total"], rep_b["total"]),
            "por_marca": _comparar_por_marca(rep_a, rep_b),
        }
    )


def _pieza_serializable(pieza: dict | None) -> dict | None:
    """Forma JSON mínima de una pieza para el SPA (la que explica un movimiento)."""
    if not pieza:
        return None
    return {
        "titulo": pieza.get("titulo", ""),
        "plataforma": pieza.get("plataforma", ""),
        "engagement_pct": pieza.get("engagement_pct", 0.0),
        "url": pieza.get("url"),
    }


def _movimiento_serializable(mov: dict, nombres: dict[str, str]) -> dict:
    """Un movimiento (qué se movió y la pieza que lo explica) con nombre resuelto."""
    cid = mov.get("marca_id", "")
    return {
        "marca_id": cid,
        # El catálogo de marcas de la Consola tiene prioridad sobre el nombre de la
        # fuente (mismo criterio que /reporte): resuelve el id_metricas a etiqueta.
        "marca": _nombre_marca_id(cid, nombres),
        "variacion_vis_pct": mov.get("variacion_vis_pct", 0.0),
        "direccion": mov.get("direccion", "estable"),
        "visualizaciones": mov.get("visualizaciones", 0),
        "engagement_pct": mov.get("engagement_pct"),
        "pieza": _pieza_serializable(mov.get("pieza")),
    }


def _analisis_serializable(analisis: dict, rango: str, marca: str | None) -> dict:
    """Forma JSON del análisis diario para el SPA: lectura + movimientos + paso.

    Resuelve los nombres de marca con el catálogo de la Consola y mantiene
    `fuente`/`es_muestra` para que la UI marque cuando los datos son de muestra
    (issue #131). El texto narrativo (render Markdown) NO se incluye: el SPA pinta
    su propia tarjeta a partir de los campos estructurados.
    """
    nombres = analisis.get("nombres") or {}
    paso = analisis.get("siguiente_paso")
    paso_out = None
    if paso is not None:
        cid = paso.get("marca_id", "")
        paso_out = {
            "marca_id": cid,
            "marca": _nombre_marca_id(cid, nombres),
            "engagement_pct": paso.get("engagement_pct"),
            "pieza": _pieza_serializable(paso.get("pieza")),
            "texto": paso.get("texto", ""),
        }
    return {
        "rango": rango,
        "etiqueta_rango": _etiqueta_rango(rango),
        "marca": marca or "",
        # Procedencia: "muestra" (ficticios) o nombre de la fuente real. La UI pinta
        # un badge de advertencia y un aviso con esto (issue #131).
        "fuente": analisis.get("fuente") or "muestra",
        "es_muestra": bool(analisis.get("es_muestra")),
        "movimientos": [
            _movimiento_serializable(m, nombres) for m in analisis.get("movimientos", [])
        ],
        "movimientos_resto": analisis.get("movimientos_resto", 0),
        "marcas_estables": analisis.get("marcas_estables", 0),
        "cobertura_parcial": [
            _nombre_marca_id(c, nombres)
            for c in (analisis.get("cobertura") or {}).get("cuentas_parciales", [])
        ],
        "siguiente_paso": paso_out,
    }


async def analisis(request: Request) -> Response:
    rango = _validar_rango(request.query_params.get("rango", "semana"))
    marca = request.query_params.get("marca") or None
    try:
        # Lee de cache (instantaneo); lazy fill (en executor) si el combo aun no esta guardado.
        a, generado_en = await metricas_cache.analisis_async(rango, marca)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        return JSONResponse({"error": "No se pudo generar el análisis."}, status_code=500)
    salida = _analisis_serializable(a, rango, marca)
    salida["generado_en"] = generado_en
    return JSONResponse(salida)


async def piezas(request: Request) -> Response:
    """GET /api/metricas/piezas: estadísticas + top 5 + peores 5 + distribución.

    `?marca=` acota a una marca (sus piezas); sin marca, agrega todas (tab "Todas").
    Servido desde cache (lazy fill); incluye `etiqueta_rango` y `generado_en`.
    """
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    marca = request.query_params.get("marca") or None
    try:
        payload, generado_en = await metricas_cache.piezas_async(rango, marca)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        return JSONResponse({"error": "No se pudo generar la analítica de piezas."}, status_code=500)
    return JSONResponse({**payload, "etiqueta_rango": _etiqueta_rango(rango), "generado_en": generado_en})


async def tendencia(request: Request) -> Response:
    """GET /api/metricas/tendencia: serie diaria del periodo (visualizaciones + interacciones).

    `?marca=` acota el ámbito (suma de sus cuentas); sin marca, todas. Servido desde
    cache (lazy fill). `puntos` vacío = la fuente activa no expone serie diaria.
    """
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    marca = request.query_params.get("marca") or None
    try:
        payload, generado_en = await metricas_cache.tendencia_async(rango, marca)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        return JSONResponse({"error": "No se pudo generar la tendencia."}, status_code=500)
    return JSONResponse({**payload, "etiqueta_rango": _etiqueta_rango(rango), "generado_en": generado_en})


def _marca_consola_de_metricas(id_metricas: str | None) -> str | None:
    """Traduce un id de marca de la frontera de métricas (guion_bajo) al id de la Consola.

    Los selectores de Analíticas envían `?marca=` en forma `id_metricas` (igual que el
    resto de endpoints de métricas). El tablero (`listar_contenido`) filtra por el id de
    marca de la Consola, así que cruzamos la frontera con el catálogo único. Si no
    resuelve (marca desconocida), devolvemos el valor tal cual: `listar_contenido`
    simplemente no encontrará piezas (lista vacía, sin romper).
    """
    if not id_metricas:
        return None
    marca = marcas.marca_por_id_metricas(id_metricas)
    return marca.id if marca is not None else id_metricas


def _listado_piezas_publicadas(marca_consola: str | None) -> list[dict]:
    """Construye el listado de piezas publicadas (con rendimiento) para una marca.

    Trabajo BLOQUEANTE (lecturas de BD + golpe a Metricool por pieza): se ejecuta en un
    hilo del executor desde `piezas_rendimiento`, no en el event loop. Aislado en una
    función síncrona para poder pasarlo a `run_in_executor`.
    """
    items = repos.listar_contenido(marca=marca_consola)
    por_contenido: dict[str, list[dict]] = {}
    for plat in repos.listar_contenido_plataforma():
        por_contenido.setdefault(plat["contenido_id"], []).append(plat)
    contenidos = [
        {
            "id": it["id"],
            "titulo": it.get("titulo", ""),
            "marca": it.get("marca", ""),
            "marca_nombre": marcas.etiqueta_de(it["marca"]) if it.get("marca") else "",
            "plataformas": por_contenido.get(it["id"], []),
        }
        for it in items
    ]
    return metricas_pieza.listado_piezas_publicadas(contenidos)


async def piezas_rendimiento(request: Request) -> Response:
    """GET /api/metricas/piezas-rendimiento: drill-down marca -> pieza con rendimiento REAL.

    Lista las piezas YA PUBLICADAS (las que tienen `id_post_metricool`) con su
    rendimiento leído de Metricool —la MISMA fuente única que alimenta el dashboard y las
    tarjetas del tablero, sin desfase— para la sección "Piezas" de Analíticas. Cada fila
    enlaza a la pieza en el tablero (`contenido_id` -> `/parrilla/pendientes`).

    `?marca=` (en forma `id_metricas`, como el resto de Analíticas) acota a una marca;
    sin marca, agrega todas. Degradación honesta: las piezas que Metricool aún no tiene
    salen con `encontrado=False` (la UI muestra "sin datos todavía", nunca ceros falsos).
    """
    marca_metricas = request.query_params.get("marca") or None
    marca_consola = _marca_consola_de_metricas(marca_metricas)
    try:
        # Lee BD + golpea Metricool por pieza (lazy-fill con TTL): potencialmente lento, así
        # que se ejecuta en el executor para no bloquear el event loop al cambiar de tab.
        piezas = await asyncio.get_running_loop().run_in_executor(
            None, _listado_piezas_publicadas, marca_consola
        )
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        return JSONResponse(
            {"error": "No se pudo generar el listado de piezas."}, status_code=500
        )
    # Fuente del listado: si cualquier pieza viene de muestra, lo marcamos como muestra
    # (mismo criterio honesto que /reporte). Sin piezas encontradas, "desconocida".
    fuentes = {p["fuente"] for p in piezas if p.get("encontrado")}
    fuente = "muestra" if "muestra" in fuentes else (next(iter(fuentes), "") or "desconocida")
    return JSONResponse(
        {
            "marca": marca_metricas or "",
            "fuente": fuente,
            "total": len(piezas),
            "piezas": piezas,
        }
    )


def _rango_opcional(raw: str | None) -> str | None:
    """Rango para /estado y /refrescar: preset o token válido, si no None (sin combo)."""
    if not raw:
        return None
    if raw in RANGOS_VALIDOS or raw.startswith(("mes:", "rango:")):
        return raw
    return None


async def estado(request: Request) -> Response:
    """GET /api/metricas/estado: estado del refresco + `generado_en` del combo.

    `?rango=` y `?marca=` (opcionales) acotan el `generado_en` que devuelve (el del
    reporte cacheado de ese combo, "" si aun no hay). La UI lo usa para "Actualizado
    hace X" y para saber cuando dejar de pollear (`corriendo` -> false).
    """
    rango = _rango_opcional(request.query_params.get("rango"))
    marca = request.query_params.get("marca") or None
    return JSONResponse(metricas_cache.estado(rango, marca))


async def refrescar(request: Request) -> Response:
    """POST /api/metricas/refrescar: dispara un refresco en 2o plano (idempotente).

    Prioriza el combo `?rango=&marca=` que se esta viendo (se recalcula primero) y
    sigue con el resto en segundo plano. Si ya hay un refresco corriendo, NO arranca
    otro: devuelve el estado actual. Responde 202 (aceptado, trabajo en curso).
    """
    rango = _rango_opcional(request.query_params.get("rango"))
    marca = request.query_params.get("marca") or None
    estado_actual = metricas_cache.disparar_refresco(rango, marca)
    return JSONResponse(estado_actual, status_code=202)


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
    for grupo, clave in (("Top 5", "top"), ("Peores 5", "peores")):
        for p in payload.get(clave, []) or []:
            filas.append(
                {
                    "grupo": grupo,
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
    marca = request.query_params.get("marca") or None
    fmt = (request.query_params.get("fmt") or "csv").lower()
    if fmt not in ("csv", "md", "json"):
        fmt = "csv"
    try:
        payload, _ = await metricas_cache.piezas_async(rango, marca)
    except ValueError as e:
        return PlainTextResponse(f"Error: {e}", status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
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


RUTAS = [
    Route("/api/metricas/opciones", opciones, methods=["GET"]),
    Route("/api/metricas/reporte", reporte, methods=["GET"]),
    Route("/api/metricas/comparar", comparar, methods=["GET"]),
    Route("/api/metricas/analisis", analisis, methods=["GET"]),
    Route("/api/metricas/piezas", piezas, methods=["GET"]),
    Route("/api/metricas/piezas-export", piezas_export, methods=["GET"]),
    Route("/api/metricas/piezas-rendimiento", piezas_rendimiento, methods=["GET"]),
    Route("/api/metricas/tendencia", tendencia, methods=["GET"]),
    Route("/api/metricas/estado", estado, methods=["GET"]),
    Route("/api/metricas/refrescar", refrescar, methods=["POST"]),
    Route("/api/metricas/export.csv", export_csv, methods=["GET"]),
    Route("/api/metricas/export.md", export_md, methods=["GET"]),
    Route("/api/metricas/export.json", export_json, methods=["GET"]),
]
