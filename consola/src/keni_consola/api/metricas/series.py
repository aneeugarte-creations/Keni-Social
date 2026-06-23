"""Endpoints de series temporales / desglose del periodo.

  - `tendencia`: serie diaria (visualizaciones + interacciones).
  - `seguidores`: serie de seguidores (total + por red).
  - `desglose`: desglose de interacciones por marca×red.
  - `crosstab`: rendimiento cruzado marca×red×formato.
  - `correlacion`: seguidores ganados ↔ piezas publicadas.

Todos comparten la misma forma: validan rango+marca, leen de cache (lazy fill) y
añaden `etiqueta_rango` + `generado_en` al payload.
"""

from __future__ import annotations

from datetime import date
from statistics import median

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ...tiempo import ahora_iso
from ._comun import (
    _conjunto_redes,
    _etiqueta_rango,
    _gate_marca_metricas,
    _log,
    _validar_formatos,
    _validar_rango,
    _validar_redes,
    marcas,
    metricas_cache,
    servicio,
)

__all__ = ["tendencia", "seguidores", "desglose", "crosstab", "correlacion", "ads", "ingesta"]

# Un canal (marca×red×formato) se marca ESTANCADO si su última pieza es >= este nº de días
# MÁS VIEJA que la última pieza de su marca: el resto del feed avanza y este se quedó atrás
# (p.ej. los Reels de FB de una marca dejan de sincronizar mientras el resto entra al día).
_UMBRAL_ESTANCADO_DIAS = 7

# El rezago contra el resto del feed NO basta: una marca que publica a diario deja por detrás
# a CUALQUIER canal de baja frecuencia (TikTok foto que el equipo apenas usa, residuo sin
# formato que Metricool no clasifica…). Eso son falsos positivos, no atascos de ingesta. Para
# distinguir "se atascó" de "se publica poco" pedimos: (1) volumen suficiente para fijar una
# cadencia fiable y (2) que el rezago supere VARIAS VECES el ritmo normal del propio canal.
_MIN_PIEZAS_CADENCIA = 4  # nº mínimo de piezas en el periodo para estimar su cadencia
_FACTOR_CADENCIA = 3  # el rezago debe superar ≥3× la cadencia mediana del canal para alertar


def _fecha(s: str) -> date | None:
    try:
        return date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def _filtrar_seguidores_por_red(payload: dict, red) -> dict:
    """Restringe la serie de seguidores a una o VARIAS redes sobre el payload cacheado.

    `red` admite un id, una colección o None (todas). El payload ya trae el stock por red
    (`puntos[].por_red`) y el neto por red (`neto_por_red`): por cada día, `total` pasa a
    ser la SUMA del stock de las redes elegidas y `por_red` queda con solo esas; `neto` es
    la suma de sus netos. Coste 0: no recomputa nada, solo proyecta el desglose que ya existe.
    """
    reds = _conjunto_redes(red)
    puntos = []
    for pt in payload.get("puntos") or []:
        por_red_pt = {r: v for r, v in (pt.get("por_red") or {}).items() if r in reds and v is not None}
        puntos.append(
            {
                **pt,
                "total": sum(por_red_pt.values()),
                "por_red": por_red_pt,
            }
        )
    neto_por_red_orig = payload.get("neto_por_red") or {}
    neto_por_red = {r: v for r, v in neto_por_red_orig.items() if r in reds}
    return {
        **payload,
        "puntos": puntos,
        "neto": sum(neto_por_red.values()),
        "neto_por_red": neto_por_red,
    }


def _filtrar_desglose_por_red(payload: dict, red) -> dict:
    """Restringe el desglose de interacciones a una o VARIAS redes (celdas + totales re-sumados).

    `red` admite un id, una colección o None. El desglose ya es por marca×red: se conservan
    solo las celdas de las redes elegidas y los `totales` se re-suman sobre ellas (mismas
    claves del payload, así funciona con la forma real y la mockeada). `engagement_pct`, si
    está en los totales, se recalcula sobre el agregado (interacciones/visualizaciones).
    """
    reds = _conjunto_redes(red)
    celdas = [c for c in (payload.get("celdas") or []) if c.get("red") in reds]
    totales_orig = payload.get("totales") or {}
    totales = {
        clave: sum(int(c.get(clave, 0) or 0) for c in celdas)
        for clave in totales_orig
        if clave != "engagement_pct"
    }
    if "engagement_pct" in totales_orig:
        vis = totales.get("visualizaciones", 0)
        totales["engagement_pct"] = (
            round(totales.get("interacciones", 0) / vis * 100, 2) if vis else 0.0
        )
    return {**payload, "celdas": celdas, "totales": totales}


async def tendencia(request: Request) -> Response:
    """GET /api/metricas/tendencia: serie diaria del periodo (visualizaciones + interacciones).

    `?marca=` acota el ámbito (suma de sus cuentas); sin marca, todas. `?red=` acota a UNA
    red y `?formato=` a esos formatos canónicos (valor desconocido →400): la serie filtrada
    se deriva de las piezas, así que CON red o formato se recomputa al vuelo (en executor),
    no se cachea cada combinación. Sin red ni formato se sirve de cache (lazy fill).
    `puntos` vacío = la fuente no expone serie diaria.
    """
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    marca, rechazo = _gate_marca_metricas(request, request.query_params.get("marca") or None)
    if rechazo is not None:
        return rechazo
    try:
        redes = _validar_redes(request.query_params.get("red"))
        formatos = _validar_formatos(request.query_params.get("formato"))
        if redes or formatos:
            payload = await run_in_threadpool(
                servicio.construir_tendencia_diaria, rango, marca, redes, formatos
            )
            generado_en = ahora_iso()
        else:
            payload, generado_en = await metricas_cache.tendencia_async(rango, marca)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        _log.exception("Fallo al generar la tendencia (rango=%s, marca=%s).", rango, marca or "todas")
        return JSONResponse({"error": "No se pudo generar la tendencia."}, status_code=500)
    return JSONResponse({**payload, "etiqueta_rango": _etiqueta_rango(rango), "generado_en": generado_en})


async def ads(request: Request) -> Response:
    """GET /api/metricas/ads: campañas de publicidad PAGADA del periodo (Meta/TikTok Ads).

    El INORGÁNICO a nivel marca: lista de campañas (impresiones, gasto, clics) + totales.
    `?marca=` acota a una marca; sin marca, todas. `?red=` conserva solo las campañas de
    esa red y re-suma los totales (red desconocida →400). Servido desde cache (lazy fill).
    Lista vacía = sin Ads conectado o sin entrega en el periodo (degradación honesta).
    """
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    marca, rechazo = _gate_marca_metricas(request, request.query_params.get("marca") or None)
    if rechazo is not None:
        return rechazo
    try:
        redes = _validar_redes(request.query_params.get("red"))
        payload, generado_en = await metricas_cache.ads_async(rango, marca)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        _log.exception("Fallo al leer los ads (rango=%s, marca=%s).", rango, marca or "todas")
        return JSONResponse({"error": "No se pudieron leer las campañas de Ads."}, status_code=500)
    lista = payload.get("ads") or []
    if redes:
        lista = [a for a in lista if a.get("red") in redes]
    total = {
        "visualizaciones": sum(int(a.get("impresiones") or 0) for a in lista),
        "gasto": round(sum(float(a.get("gasto") or 0.0) for a in lista), 2),
        "clics": sum(int(a.get("clics") or 0) for a in lista),
        "campanias": len(lista),
        "moneda": next((a.get("moneda") for a in lista if a.get("moneda")), ""),
    }
    return JSONResponse(
        {"ads": lista, "total": total, "etiqueta_rango": _etiqueta_rango(rango), "generado_en": generado_en}
    )


async def ingesta(request: Request) -> Response:
    """GET /api/metricas/ingesta: detecta canales (marca×red×formato) con la ingesta
    ESTANCADA — un canal que PUBLICABA con regularidad y se quedó muy por detrás del resto.

    Caza casos como "los Reels de Facebook de Claro Sports no entran desde el 15-mayo
    mientras el resto sí": un problema de sincronización de la fuente (Metricool) que de otro
    modo solo se descubre a mano. Para no confundirlo con un canal de baja frecuencia (que por
    naturaleza queda por detrás de una marca que publica a diario), solo alerta si el canal
    tiene cadencia fiable (`_MIN_PIEZAS_CADENCIA`) y su rezago supera varias veces su ritmo
    normal (`_FACTOR_CADENCIA`); el residuo sin formato clasificado se ignora. Se computa
    sobre el listado de piezas (cache, lazy fill); sin coste de API extra. `?marca=` acota."""
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    marca, rechazo = _gate_marca_metricas(request, request.query_params.get("marca") or None)
    if rechazo is not None:
        return rechazo
    try:
        payload, generado_en = await metricas_cache.piezas_listado_async(rango, marca)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        _log.exception("Fallo al evaluar la ingesta (rango=%s, marca=%s).", rango, marca or "todas")
        return JSONResponse({"error": "No se pudo evaluar la ingesta."}, status_code=500)

    piezas = payload.get("piezas") or []
    # Acumulamos TODAS las fechas de cada combo (no solo la última): su cadencia propia es lo
    # que separa un atasco de un canal de baja frecuencia.
    fechas_combo: dict[tuple[str, str, str], list[date]] = {}
    ult_marca: dict[str, date] = {}  # cuenta -> última fecha (cualquier red/formato)
    for p in piezas:
        f = _fecha(p.get("publicado"))
        if f is None:
            continue
        cuenta = str(p.get("cuenta") or "")
        if cuenta and f > ult_marca.get(cuenta, date.min):
            ult_marca[cuenta] = f  # frescura de la marca: cuenta cualquier pieza, formato o no
        red = p.get("red") or ""
        formato = str(p.get("formato") or "")
        # Sin red o sin formato CLASIFICADO no hay canal atribuible: las piezas que Metricool
        # no logra clasificar (formato vacío) son residuo, no un canal que vigilar. Suman a la
        # frescura de la marca (arriba) pero no generan su propio combo/alerta.
        if not red or not formato:
            continue
        fechas_combo.setdefault((cuenta, red, formato), []).append(f)

    # Referencia temporal: el FIN del periodo del listado (no el reloj de pared). Si la
    # entrada de cache viene con retraso, medir contra "hoy" inflaría dias_sin_piezas con
    # días que el feed ni siquiera cubre (y acusaría a Metricool de un hueco nuestro).
    referencia = (
        _fecha((payload.get("periodo") or {}).get("hasta"))
        or max(ult_marca.values(), default=None)
        or date.today()
    )
    alertas = []
    for (cuenta, red, formato), fechas in fechas_combo.items():
        f_marca = ult_marca.get(cuenta)
        if f_marca is None:
            continue
        # Con una o dos piezas no se puede afirmar que el canal "se atascó", solo que se
        # publica poco: sin cadencia fiable, no alertamos (evita el falso positivo de
        # formatos que el equipo apenas usa).
        if len(fechas) < _MIN_PIEZAS_CADENCIA:
            continue
        fechas.sort()
        f_combo = fechas[-1]
        rezago = (f_marca - f_combo).days  # silencio del canal medido contra el dato más fresco
        if rezago < _UMBRAL_ESTANCADO_DIAS:
            continue
        # Cadencia propia (mediana de huecos entre piezas consecutivas): un canal que publica
        # cada ~10 días no está estancado por ir 12 por detrás; uno que publica cada 2 y va 24
        # por detrás, sí. El rezago debe superar varias veces su ritmo normal.
        huecos = [(b - a).days for a, b in zip(fechas, fechas[1:]) if b > a]
        if not huecos:  # todas el mismo día: ráfaga sin ritmo, no podemos juzgar atasco
            continue
        if rezago < _FACTOR_CADENCIA * median(huecos):
            continue
        alertas.append({
            "marca": marcas.etiqueta_por_id_metricas(cuenta),
            "red": red,
            "formato": formato,
            "ultima_pieza": f_combo.isoformat(),
            "dias_sin_piezas": (referencia - f_combo).days,
            "rezago_dias": rezago,
        })
    alertas.sort(key=lambda a: a["rezago_dias"], reverse=True)
    return JSONResponse(
        {"alertas": alertas, "etiqueta_rango": _etiqueta_rango(rango), "generado_en": generado_en}
    )


async def seguidores(request: Request) -> Response:
    """GET /api/metricas/seguidores: serie de seguidores del periodo (total + por red).

    `?marca=` acota el ámbito; sin marca, todas. `?red=` acota a UNA red (red desconocida
    →400): proyecta el stock/neto de esa red sobre el payload cacheado (no recomputa).
    Servido desde cache (lazy fill). `puntos` vacío = la fuente no expone serie de
    seguidores (degradación honesta).
    """
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    marca, rechazo = _gate_marca_metricas(request, request.query_params.get("marca") or None)
    if rechazo is not None:
        return rechazo
    try:
        redes = _validar_redes(request.query_params.get("red"))
        payload, generado_en = await metricas_cache.seguidores_async(rango, marca)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        _log.exception("Fallo al generar la serie de seguidores (rango=%s, marca=%s).", rango, marca or "todas")
        return JSONResponse({"error": "No se pudo generar la serie de seguidores."}, status_code=500)
    if redes:
        payload = _filtrar_seguidores_por_red(payload, redes)
    return JSONResponse({**payload, "etiqueta_rango": _etiqueta_rango(rango), "generado_en": generado_en})


async def desglose(request: Request) -> Response:
    """GET /api/metricas/desglose: desglose de interacciones por marca×red.

    `?marca=` acota a una marca; sin marca, todas. `?red=` acota a UNA red (red desconocida
    →400): conserva solo sus celdas y re-suma los totales. `?formato=` acota a esos formatos
    canónicos (es un predicado por-pieza ANTES de agregar, así que con formato se recomputa
    al vuelo; valor desconocido →400). Sin formato, servido desde cache (lazy fill).
    """
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    marca, rechazo = _gate_marca_metricas(request, request.query_params.get("marca") or None)
    if rechazo is not None:
        return rechazo
    try:
        redes = _validar_redes(request.query_params.get("red"))
        formatos = _validar_formatos(request.query_params.get("formato"))
        if formatos:
            payload = await run_in_threadpool(
                servicio.construir_desglose_interacciones, rango, marca, formatos
            )
            generado_en = ahora_iso()
        else:
            payload, generado_en = await metricas_cache.desglose_async(rango, marca)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        _log.exception("Fallo al generar el desglose (rango=%s, marca=%s).", rango, marca or "todas")
        return JSONResponse({"error": "No se pudo generar el desglose de interacciones."}, status_code=500)
    if redes:
        payload = _filtrar_desglose_por_red(payload, redes)
    return JSONResponse({**payload, "etiqueta_rango": _etiqueta_rango(rango), "generado_en": generado_en})


async def crosstab(request: Request) -> Response:
    """GET /api/metricas/crosstab: rendimiento cruzado marca×red×formato.

    `?marca=` acota a una marca; sin marca, todas. `?red=` conserva solo las celdas de esa
    red (red desconocida →400). `?formato=` acota a esos formatos canónicos (predicado
    por-pieza antes de agrupar, así que con formato se recomputa al vuelo; valor desconocido
    →400). Sin formato, servido desde cache (lazy fill).
    """
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    marca, rechazo = _gate_marca_metricas(request, request.query_params.get("marca") or None)
    if rechazo is not None:
        return rechazo
    try:
        redes = _validar_redes(request.query_params.get("red"))
        formatos = _validar_formatos(request.query_params.get("formato"))
        if formatos:
            payload = await run_in_threadpool(
                servicio.construir_crosstab, rango, marca, formatos
            )
            generado_en = ahora_iso()
        else:
            payload, generado_en = await metricas_cache.crosstab_async(rango, marca)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        _log.exception("Fallo al generar el crosstab (rango=%s, marca=%s).", rango, marca or "todas")
        return JSONResponse({"error": "No se pudo generar el crosstab."}, status_code=500)
    if redes:
        payload = {
            **payload,
            "celdas": [c for c in (payload.get("celdas") or []) if c.get("red") in redes],
        }
    return JSONResponse({**payload, "etiqueta_rango": _etiqueta_rango(rango), "generado_en": generado_en})


async def correlacion(request: Request) -> Response:
    """GET /api/metricas/correlacion: correlación seguidores ganados ↔ piezas publicadas.

    `?marca=` acota a una marca; sin marca, todas. `?red=` conserva solo los items de esa
    red (red desconocida →400). `?formato=` acota el recuento de piezas (n_posts/estrella) a
    esos formatos canónicos (predicado por-pieza, así que con formato se recomputa al vuelo;
    valor desconocido →400). Sin formato, servido desde cache (lazy fill).
    """
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    marca, rechazo = _gate_marca_metricas(request, request.query_params.get("marca") or None)
    if rechazo is not None:
        return rechazo
    try:
        redes = _validar_redes(request.query_params.get("red"))
        formatos = _validar_formatos(request.query_params.get("formato"))
        if formatos:
            payload = await run_in_threadpool(
                servicio.construir_correlacion_seguidores, rango, marca, formatos
            )
            generado_en = ahora_iso()
        else:
            payload, generado_en = await metricas_cache.correlacion_async(rango, marca)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        _log.exception("Fallo al generar la correlación (rango=%s, marca=%s).", rango, marca or "todas")
        return JSONResponse({"error": "No se pudo generar la correlación de seguidores."}, status_code=500)
    if redes:
        payload = {
            **payload,
            "items": [it for it in (payload.get("items") or []) if it.get("red") in redes],
        }
    return JSONResponse({**payload, "etiqueta_rango": _etiqueta_rango(rango), "generado_en": generado_en})
