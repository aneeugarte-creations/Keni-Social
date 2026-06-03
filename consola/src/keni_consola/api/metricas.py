"""API Metricas: opciones, reporte consolidado, comparativa de rangos y export.

Consume la fachada estable `keni_metricas.servicio` (SOLO LECTURA); ya no importa
internals (`config`/`reporte`/`schema`). El SPA dibuja el dashboard a partir de
`/api/metricas/reporte` (ya no hay endpoint HTML de dashboard).

  - `/api/metricas/opciones`: marcas + rangos para poblar los selectores.
  - `/api/metricas/reporte`: total consolidado + por cuenta (nombres resueltos).
  - `/api/metricas/comparar`: comparativa A vs B (total + por marca).
  - `/api/metricas/analisis`: análisis diario con narrativa "qué cambió y por qué"
    + siguiente paso (F6/#146); ensambla reporte + picos en una lectura accionable.
  - `/api/metricas/piezas-export`: descarga del Top 5 / Peores 5 de piezas (csv|md|json).
  - `/api/metricas/piezas-por-etiqueta`: rendimiento del periodo por serie/tipo (cruce
    piezas↔contenido para resolver tipo_contenido + etiquetas; Item C).
  - `/api/metricas/lineas`: rendimiento del periodo por LÍNEA (etiqueta clase `vertical`)
    y por ORIGEN (clase `origen`); "qué línea funciona" + dual editorial-vs-impuesto.
  - `/api/metricas/export.{csv,md,json}`: descargas (misma serializacion que el CLI).

DEFERIDO / BLOQUEADO — "procedencia de la audiencia" (de dónde viene quién ve el
contenido): NO implementado a propósito. Requiere la Meta Graph API por cliente
(insights de audiencia/demografía con token y permisos de cada página), que el
proveedor primario (Metricool) no expone de forma uniforme. Queda fuera del v1 de
solo-lectura multi-fuente hasta cablear Meta por cliente.
"""

from __future__ import annotations

import asyncio
import logging

from keni_metricas import servicio
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Route

from .. import marcas, metricas_cache, metricas_linea, metricas_pieza, repos

_log = logging.getLogger("keni_consola.api.metricas")

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


def _agregar_por_red(rep: dict) -> list[dict]:
    """Agrega el `por_plataforma` de TODAS las cuentas del reporte, por red.

    Suma `visualizaciones` e `interacciones`; el `alcance` suma solo los no-null y
    queda `None` si NINGUNA cuenta mide esa red (criterio #138, igual que el `total`:
    no se inventa un 0). El engagement se recalcula sobre los agregados de la red.
    Devuelve las redes ordenadas por visualizaciones desc. La red se emite como id de
    plataforma (el frontend lo traduce a nombre legible).
    """
    acc: dict[str, dict] = {}
    for fila in rep.get("cuentas", []):
        r = fila.get("resumen") or {}
        for p in r.get("por_plataforma", []) or []:
            red = p.get("plataforma", "")
            d = acc.setdefault(
                red, {"visualizaciones": 0, "alcance": None, "interacciones": 0}
            )
            d["visualizaciones"] += p.get("visualizaciones", 0) or 0
            d["interacciones"] += p.get("interacciones", 0) or 0
            alcance = p.get("alcance")
            if alcance is not None:
                d["alcance"] = (d["alcance"] or 0) + alcance
    por_red = []
    for red, d in acc.items():
        vis = d["visualizaciones"]
        inter = d["interacciones"]
        por_red.append(
            {
                "red": red,
                "visualizaciones": vis,
                "alcance": d["alcance"],
                "interacciones": inter,
                "engagement_pct": round(inter / vis * 100, 1) if vis else 0.0,
            }
        )
    por_red.sort(key=lambda x: x["visualizaciones"], reverse=True)
    return por_red


# Universo de redes sociales que Metricool mide a nivel de analítica (ids de
# plataforma del contrato). "web" NO es una red de analítica de Metricool, así que se
# excluye de la auditoría de cobertura. El orden es el de presentación en la UI.
_REDES_AUDITABLES: tuple[str, ...] = ("facebook", "instagram", "x", "tiktok", "youtube")

# Texto legible por estado de cobertura (lo que la UI muestra como explicación del
# "por qué no hay datos"). `con_datos` no necesita motivo (None).
_MOTIVO_COBERTURA: dict[str, str | None] = {
    "con_datos": None,
    "sin_metricas": "Conectada, pero sin actividad ni métricas en este rango.",
    "sin_lectura": (
        "No se pudo leer de Metricool: la red no está conectada o la métrica no está "
        "disponible en el plan."
    ),
    "no_configurada": "Esta red no está dada de alta en Metricool para la marca.",
    "sin_credenciales": "Faltan credenciales para leer esta red.",
    "presupuesto_agotado": "Límite de la API de Metricool alcanzado; reintenta más tarde.",
}


def _cobertura_por_marca(rep: dict) -> list[dict]:
    """Auditoría de cobertura: por cada marca, TODAS las redes auditables con su estado.

    Deriva de lo que el reporte YA trae por cuenta (`resumen.por_plataforma` +
    `resumen.cobertura`), sin llamadas extra a la API. Para cada red del universo
    `_REDES_AUDITABLES` clasifica:

      - en `por_plataforma` con vis/inter > 0 -> "con_datos" (con sus métricas).
      - en `por_plataforma` pero todo a 0     -> "sin_metricas" (conectada, sin actividad).
      - en `cobertura.omitidas`               -> el motivo de omisión ("error_api" se
                                                 presenta como "sin_lectura").
      - en ninguno de los dos                 -> "no_configurada" (la marca no la tiene).

    Las métricas van `null` cuando la red no respondió (no se inventa un 0). Así el
    operador ve TODAS las redes y por qué cada una aporta (o no) datos.
    """
    nombres = rep.get("nombres") or {}
    salida: list[dict] = []
    for fila in rep.get("cuentas", []):
        r = fila.get("resumen") or {}
        cid = r.get("cuenta", "")
        por_plat = {p.get("plataforma", ""): p for p in (r.get("por_plataforma") or [])}
        cob = r.get("cobertura") or {}
        omitidas = set(cob.get("omitidas") or [])
        motivos = cob.get("motivo") or {}
        redes: list[dict] = []
        for red in _REDES_AUDITABLES:
            if red in por_plat:
                p = por_plat[red]
                vis = p.get("visualizaciones", 0) or 0
                inter = p.get("interacciones", 0) or 0
                estado = "con_datos" if (vis or inter) else "sin_metricas"
                redes.append(
                    {
                        "red": red,
                        "estado": estado,
                        "visualizaciones": vis,
                        "alcance": p.get("alcance"),
                        "interacciones": inter,
                        "engagement_pct": p.get("engagement_pct", 0.0),
                        "motivo": _MOTIVO_COBERTURA[estado],
                    }
                )
            else:
                if red in omitidas:
                    motivo_id = str(motivos.get(red, "error_api"))
                    estado = "sin_lectura" if motivo_id == "error_api" else motivo_id
                else:
                    estado = "no_configurada"
                redes.append(
                    {
                        "red": red,
                        "estado": estado,
                        "visualizaciones": None,
                        "alcance": None,
                        "interacciones": None,
                        "engagement_pct": None,
                        "motivo": _MOTIVO_COBERTURA.get(estado, _MOTIVO_COBERTURA["sin_lectura"]),
                    }
                )
        salida.append({"marca_id": cid, "marca": _nombre_marca_id(cid, nombres), "redes": redes})
    return salida


def _reporte_serializable(rep: dict, rango: str, marca: str | None) -> dict:
    """Forma JSON del reporte para el SPA: total + cuentas con nombres resueltos."""
    nombres = rep.get("nombres") or {}
    cuentas = []
    for fila in rep.get("cuentas", []):
        r = fila.get("resumen") or {}
        cid = r.get("cuenta", "")
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
    por_red = _agregar_por_red(rep)
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
        "por_red": por_red,
        "cobertura_redes": _cobertura_por_marca(rep),
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
        _log.exception("Fallo al generar el reporte (rango=%s, marca=%s).", rango, marca or "todas")
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
        _log.exception(
            "Fallo al construir la comparativa (rango_a=%s, rango_b=%s, marca=%s).",
            rango_a, rango_b, marca or "todas",
        )
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
            "total": _comparar_totales(rep_a.get("total") or {}, rep_b.get("total") or {}),
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
        _log.exception("Fallo al generar el análisis (rango=%s, marca=%s).", rango, marca or "todas")
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
        _log.exception(
            "Fallo al generar la analítica de piezas (rango=%s, marca=%s).", rango, marca or "todas"
        )
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
        _log.exception("Fallo al generar la tendencia (rango=%s, marca=%s).", rango, marca or "todas")
        return JSONResponse({"error": "No se pudo generar la tendencia."}, status_code=500)
    return JSONResponse({**payload, "etiqueta_rango": _etiqueta_rango(rango), "generado_en": generado_en})


async def seguidores(request: Request) -> Response:
    """GET /api/metricas/seguidores: serie de seguidores del periodo (total + por red).

    `?marca=` acota el ámbito; sin marca, todas. Servido desde cache (lazy fill).
    `puntos` vacío = la fuente activa no expone serie de seguidores (degradación honesta).
    """
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    marca = request.query_params.get("marca") or None
    try:
        payload, generado_en = await metricas_cache.seguidores_async(rango, marca)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        _log.exception("Fallo al generar la serie de seguidores (rango=%s, marca=%s).", rango, marca or "todas")
        return JSONResponse({"error": "No se pudo generar la serie de seguidores."}, status_code=500)
    return JSONResponse({**payload, "etiqueta_rango": _etiqueta_rango(rango), "generado_en": generado_en})


async def desglose(request: Request) -> Response:
    """GET /api/metricas/desglose: desglose de interacciones por marca×red.

    `?marca=` acota a una marca; sin marca, todas. Servido desde cache (lazy fill).
    """
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    marca = request.query_params.get("marca") or None
    try:
        payload, generado_en = await metricas_cache.desglose_async(rango, marca)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        _log.exception("Fallo al generar el desglose (rango=%s, marca=%s).", rango, marca or "todas")
        return JSONResponse({"error": "No se pudo generar el desglose de interacciones."}, status_code=500)
    return JSONResponse({**payload, "etiqueta_rango": _etiqueta_rango(rango), "generado_en": generado_en})


async def crosstab(request: Request) -> Response:
    """GET /api/metricas/crosstab: rendimiento cruzado marca×red×formato.

    `?marca=` acota a una marca; sin marca, todas. Servido desde cache (lazy fill).
    """
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    marca = request.query_params.get("marca") or None
    try:
        payload, generado_en = await metricas_cache.crosstab_async(rango, marca)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        _log.exception("Fallo al generar el crosstab (rango=%s, marca=%s).", rango, marca or "todas")
        return JSONResponse({"error": "No se pudo generar el crosstab."}, status_code=500)
    return JSONResponse({**payload, "etiqueta_rango": _etiqueta_rango(rango), "generado_en": generado_en})


async def correlacion(request: Request) -> Response:
    """GET /api/metricas/correlacion: correlación seguidores ganados ↔ piezas publicadas.

    `?marca=` acota a una marca; sin marca, todas. Servido desde cache (lazy fill).
    """
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    marca = request.query_params.get("marca") or None
    try:
        payload, generado_en = await metricas_cache.correlacion_async(rango, marca)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        _log.exception("Fallo al generar la correlación (rango=%s, marca=%s).", rango, marca or "todas")
        return JSONResponse({"error": "No se pudo generar la correlación de seguidores."}, status_code=500)
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
        _log.exception(
            "Fallo al generar el listado de piezas (marca=%s).", marca_metricas or "todas"
        )
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


async def piezas_listado(request: Request) -> Response:
    """GET /api/metricas/piezas-listado: listado COMPLETO de piezas del periodo.

    A diferencia de `/api/metricas/piezas` (estadísticas + top/peores) y de
    `/api/metricas/piezas-rendimiento` (las publicaciones de la Consola con su
    rendimiento real), esto devuelve TODAS las piezas de la(s) cuenta(s) del periodo
    tal como las emite la fuente única (`servicio.construir_listado_piezas`): cada una
    con su id de Metricool, granulares y url. Es el insumo de la tabla "Todas las piezas
    del periodo" (con buscador + orden + detalle por pieza). Servido desde cache (lazy fill).

    `?marca=` (en forma `id_metricas`) acota a una marca; sin marca, agrega todas.
    """
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    marca = request.query_params.get("marca") or None
    try:
        payload, generado_en = await metricas_cache.piezas_listado_async(rango, marca)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        _log.exception(
            "Fallo al generar el listado de piezas (rango=%s, marca=%s).", rango, marca or "todas"
        )
        return JSONResponse(
            {"error": "No se pudo generar el listado de piezas."}, status_code=500
        )
    return JSONResponse(
        {
            "rango": rango,
            "etiqueta_rango": _etiqueta_rango(rango),
            "marca": marca or "",
            "periodo": payload.get("periodo") or {"desde": "", "hasta": ""},
            "fuente": payload.get("fuente") or "muestra",
            "piezas": payload.get("piezas", []),
            "total": payload.get("total", 0),
            "generado_en": generado_en,
        }
    )


def _velocidad_pieza(serie: list[dict]) -> dict | None:
    """Calcula la VELOCIDAD de una pieza a partir de sus snapshots (None si <2 puntos).

    Honesto, sin inventar datos. Sobre los snapshots ordenados por `ts` (la serie ya
    viene ascendente de `repos.serie_pieza`):

      - `pct_en_primeras_24h`: qué fracción de las visualizaciones FINALES había
        acumulado la pieza en su 1er snapshot dentro de las 24 h del primero
        (vis_24h / vis_final * 100). Mide si la pieza "explota" pronto o crece lento.
        None si vis_final es 0 (sin baseline) o no hay un snapshot dentro de 24 h.
      - `delta_medio_por_dia`: visualizaciones ganadas por día entre el primer y el
        último snapshot ((vis_final - vis_inicial) / días transcurridos). None si el
        lapso es < ~1 min (no se divide por casi-cero).
      - `n_snapshots`: cuántos puntos respaldan el cálculo (transparencia).

    Devuelve None si hay menos de 2 snapshots (no hay velocidad medible).
    """
    if len(serie) < 2:
        return None

    def _ts(p: dict):
        from datetime import datetime

        try:
            return datetime.fromisoformat(str(p.get("ts", "")))
        except ValueError:
            return None

    primero = serie[0]
    ultimo = serie[-1]
    t0 = _ts(primero)
    t1 = _ts(ultimo)
    vis_inicial = float(primero.get("visualizaciones", 0) or 0)
    vis_final = float(ultimo.get("visualizaciones", 0) or 0)

    # pct en las primeras 24 h: último snapshot cuyo ts está dentro de 24 h del primero.
    from datetime import timedelta

    pct_24h: float | None = None
    if t0 is not None and vis_final > 0:
        vis_24h: float | None = None
        for p in serie:
            tp = _ts(p)
            if tp is not None and tp - t0 <= timedelta(hours=24):
                vis_24h = float(p.get("visualizaciones", 0) or 0)
        if vis_24h is not None:
            pct_24h = round(vis_24h / vis_final * 100, 1)

    # delta medio por día entre el primer y el último snapshot.
    delta_dia: float | None = None
    if t0 is not None and t1 is not None:
        dias = (t1 - t0).total_seconds() / 86400.0
        if dias >= (60 / 86400.0):  # al menos ~1 min de lapso real
            delta_dia = round((vis_final - vis_inicial) / dias, 1)

    return {
        "pct_en_primeras_24h": pct_24h,
        "delta_medio_por_dia": delta_dia,
        "n_snapshots": len(serie),
    }


def _punto_historico(snap: dict) -> dict:
    """Forma JSON de un punto del histórico de una pieza (ts + métricas disponibles)."""
    return {
        "ts": snap.get("ts", ""),
        "visualizaciones": snap.get("visualizaciones", 0),
        "interacciones": snap.get("interacciones", 0),
        "engagement_pct": snap.get("engagement_pct", 0.0),
        "alcance": snap.get("alcance", 0),
        "likes": snap.get("likes", 0),
        "comentarios": snap.get("comentarios", 0),
        "compartidos": snap.get("compartidos", 0),
        "guardados": snap.get("guardados", 0),
        "video_views": snap.get("video_views", 0),
        "tiempo_medio_vis_s": snap.get("tiempo_medio_vis_s", 0),
        "clics_enlace": snap.get("clics_enlace", 0),
    }


async def pieza_historico(request: Request) -> Response:
    """GET /api/metricas/pieza-historico?id=<pieza_id>: serie histórica + velocidad.

    Devuelve los snapshots acumulados de UNA pieza (ADR 0007, tabla
    `metricas_pieza_snapshots`), que el daemon de refresco alimenta SOLO para las piezas
    SEGUIDAS por la Consola (con `id_post_metricool`). Para la mayoría de piezas de
    Metricool aún no habrá histórico: `puntos` vacío => la UI lo dice honestamente
    ("sin histórico todavía"), nunca inventa una curva.

    `velocidad` resume cómo crece la pieza (pct en las primeras 24 h, delta medio por
    día); None si hay menos de 2 snapshots (sin velocidad medible).
    """
    pieza_id = request.query_params.get("id") or ""
    if not pieza_id:
        return JSONResponse({"error": "Falta el parámetro 'id'."}, status_code=400)
    try:
        serie = await asyncio.get_running_loop().run_in_executor(
            None, repos.serie_pieza, pieza_id
        )
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        _log.exception("Fallo al leer el histórico de la pieza (id=%s).", pieza_id)
        return JSONResponse(
            {"error": "No se pudo leer el histórico de la pieza."}, status_code=500
        )
    return JSONResponse(
        {
            "pieza_id": pieza_id,
            "puntos": [_punto_historico(s) for s in serie],
            "velocidad": _velocidad_pieza(serie),
        }
    )


async def piezas_por_etiqueta(request: Request) -> Response:
    """GET /api/metricas/piezas-por-etiqueta: rendimiento del periodo por SERIE/TIPO.

    Metricool no expone la categoría editorial de un post; este endpoint la resuelve
    cruzando las piezas del periodo con el `contenido` de la BD (enlace por
    `id_post_metricool`; fallback fuzzy por título) y agrega engagement medio +
    visualizaciones + nº de piezas por cada eje (tipo de contenido + clases de etiqueta).
    `?marca=` (en forma `id_metricas`) acota; sin marca, todas. Trabajo bloqueante (BD +
    listado de piezas de la fuente) en executor para no congelar el event loop.
    """
    marca_metricas = request.query_params.get("marca") or None
    marca_consola = _marca_consola_de_metricas(marca_metricas)
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    try:
        payload = await asyncio.get_running_loop().run_in_executor(
            None, metricas_pieza.analitica_por_etiqueta, rango, marca_consola, marca_metricas
        )
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        _log.exception(
            "Fallo al generar la analítica por serie (rango=%s, marca=%s).",
            rango, marca_metricas or "todas",
        )
        return JSONResponse(
            {"error": "No se pudo generar la analítica por serie."}, status_code=500
        )
    return JSONResponse(
        {
            "marca": marca_metricas or "",
            "rango": rango,
            "etiqueta_rango": _etiqueta_rango(rango),
            **payload,
        }
    )


async def lineas(request: Request) -> Response:
    """GET /api/metricas/lineas: rendimiento del periodo por LÍNEA y por ORIGEN.

    Agrupa el rendimiento REAL de las piezas del periodo por su LÍNEA editorial (etiqueta
    clase `vertical`) y por su ORIGEN (clase `origen`), cruzando las piezas de la fuente
    única de métricas con su `contenido` de la BD (enlace por `id_post_metricool`; fallback
    fuzzy por título), igual que `piezas-por-etiqueta`. Devuelve, por cada cubo, nº de
    piezas + suma de visualizaciones + suma de interacciones + engagement medio. Las piezas
    sin línea/origen caen en "Sin línea"/"Sin origen".

    `?marca=` (en forma `id_metricas`) acota; sin marca, todas. `?rango=` (preset o token).
    Trabajo bloqueante (BD + listado de piezas de la fuente) en executor para no congelar
    el event loop.
    """
    marca_metricas = request.query_params.get("marca") or None
    marca_consola = _marca_consola_de_metricas(marca_metricas)
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    try:
        payload = await asyncio.get_running_loop().run_in_executor(
            None, metricas_linea.lineas_y_origenes, rango, marca_consola, marca_metricas
        )
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        _log.exception(
            "Fallo al generar la analítica por línea (rango=%s, marca=%s).",
            rango, marca_metricas or "todas",
        )
        return JSONResponse(
            {"error": "No se pudo generar la analítica por línea."}, status_code=500
        )
    return JSONResponse(
        {
            "marca": marca_metricas or "",
            "rango": rango,
            "etiqueta_rango": _etiqueta_rango(rango),
            **payload,
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
        _log.exception("Fallo al exportar CSV (rango=%s, marca=%s).", rango, marca or "todas")
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
        _log.exception("Fallo al exportar Markdown (rango=%s, marca=%s).", rango, marca or "todas")
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
    # no quedar desfasada si cambia el número de piezas (antes estaba fija en "5").
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
    marca = request.query_params.get("marca") or None
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


RUTAS = [
    Route("/api/metricas/opciones", opciones, methods=["GET"]),
    Route("/api/metricas/reporte", reporte, methods=["GET"]),
    Route("/api/metricas/comparar", comparar, methods=["GET"]),
    Route("/api/metricas/analisis", analisis, methods=["GET"]),
    Route("/api/metricas/piezas", piezas, methods=["GET"]),
    Route("/api/metricas/piezas-export", piezas_export, methods=["GET"]),
    Route("/api/metricas/piezas-rendimiento", piezas_rendimiento, methods=["GET"]),
    Route("/api/metricas/piezas-listado", piezas_listado, methods=["GET"]),
    Route("/api/metricas/pieza-historico", pieza_historico, methods=["GET"]),
    Route("/api/metricas/piezas-por-etiqueta", piezas_por_etiqueta, methods=["GET"]),
    Route("/api/metricas/lineas", lineas, methods=["GET"]),
    Route("/api/metricas/tendencia", tendencia, methods=["GET"]),
    Route("/api/metricas/seguidores", seguidores, methods=["GET"]),
    Route("/api/metricas/desglose", desglose, methods=["GET"]),
    Route("/api/metricas/crosstab", crosstab, methods=["GET"]),
    Route("/api/metricas/correlacion", correlacion, methods=["GET"]),
    Route("/api/metricas/estado", estado, methods=["GET"]),
    Route("/api/metricas/refrescar", refrescar, methods=["POST"]),
    Route("/api/metricas/export.csv", export_csv, methods=["GET"]),
    Route("/api/metricas/export.md", export_md, methods=["GET"]),
    Route("/api/metricas/export.json", export_json, methods=["GET"]),
]
