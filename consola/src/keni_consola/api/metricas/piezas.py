"""Endpoints de piezas: analítica, rendimiento, listado, histórico, por etiqueta y categorías.

  - `piezas`: estadísticas + top/peores + distribución del periodo (filtrable por red).
  - `piezas_rendimiento`: drill-down marca -> pieza publicada con rendimiento REAL.
  - `piezas_listado`: listado COMPLETO de piezas del periodo (con categoría editorial).
  - `pieza_historico`: serie histórica de UNA pieza + velocidad de crecimiento.
  - `piezas_por_etiqueta`: rendimiento del periodo por SERIE/TIPO.
  - `categorias`: rendimiento del periodo por CATEGORÍA (clase `categoria`) y ORIGEN (clase `origen`).
"""

from __future__ import annotations

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ...tiempo import ahora_iso
from ._comun import (
    _conjunto_formatos,
    _etiqueta_rango,
    _formato_canonico,
    _gate_marca_metricas,
    _log,
    _validar_formatos,
    _validar_rango,
    _validar_redes,
    marcas,
    metricas_cache,
    metricas_categoria,
    metricas_pieza,
    repos,
    servicio,
)

__all__ = [
    "piezas",
    "piezas_rendimiento",
    "piezas_listado",
    "pieza_historico",
    "piezas_por_etiqueta",
    "categorias",
]


async def piezas(request: Request) -> Response:
    """GET /api/metricas/piezas: estadísticas + top 10 + peores 10 + distribución.

    `?marca=` acota a una marca (sus piezas); sin marca, agrega todas (tab "Todas").
    `?red=` acota a UNA red y `?formato=` a esos formatos canónicos (valor desconocido →400);
    top/peores/estadísticas se calculan SOLO sobre las piezas que pasan ambos filtros. Sin
    `red` ni `formato` se sirve de cache (lazy fill); con cualquiera de ellos se recomputa
    al vuelo (en executor) — vista filtrada bajo demanda, no se cachea cada combinación.
    Incluye `etiqueta_rango` y `generado_en`.
    """
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    marca, rechazo = _gate_marca_metricas(request, request.query_params.get("marca") or None)
    if rechazo is not None:
        return rechazo
    try:
        redes = _validar_redes(request.query_params.get("red"))
        formatos = _validar_formatos(request.query_params.get("formato"))
        if redes or formatos:
            # Vista filtrada por red/formato: recálculo bajo demanda (trabajo bloqueante de
            # la fuente) en threadpool para no congelar el event loop; no usa cache por combo.
            payload = await run_in_threadpool(
                servicio.construir_analitica_piezas, rango, marca, redes, formatos
            )
            generado_en = ahora_iso()
        else:
            payload, generado_en = await metricas_cache.piezas_async(rango, marca)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        _log.exception(
            "Fallo al generar la analítica de piezas (rango=%s, marca=%s, red=%s, formato=%s).",
            rango, marca or "todas", ",".join(redes) or "todas", ",".join(formatos) or "todos",
        )
        return JSONResponse({"error": "No se pudo generar la analítica de piezas."}, status_code=500)
    return JSONResponse({**payload, "etiqueta_rango": _etiqueta_rango(rango), "generado_en": generado_en})


def _marca_consola_de_metricas(id_metricas: str | None) -> str | None:
    """Traduce un id de marca de la frontera de métricas (guion_bajo) al id de la Consola.

    Los selectores de Analíticas envían `?marca=` en forma `id_metricas` (igual que el
    resto de endpoints de métricas). El tablero (`listar_publicacion`) filtra por el id de
    marca de la Consola, así que cruzamos la frontera con el catálogo único. Si no
    resuelve (marca desconocida), devolvemos el valor tal cual: `listar_publicacion`
    simplemente no encontrará piezas (lista vacía, sin romper).
    """
    if not id_metricas:
        return None
    marca = marcas.marca_por_id_metricas(id_metricas)
    return marca.id if marca is not None else id_metricas


def _listado_piezas_publicadas(marca_consola: str | None) -> list[dict]:
    """Construye el listado de piezas publicadas (con rendimiento) para una marca.

    Trabajo BLOQUEANTE (lecturas de BD + golpe a Metricool por pieza): se ejecuta en un
    hilo del threadpool desde `piezas_rendimiento`, no en el event loop. Aislado en una
    función síncrona para poder pasarlo a `run_in_threadpool`.
    """
    items = repos.listar_publicacion(marca=marca_consola)
    por_contenido: dict[str, list[dict]] = {}
    for plat in repos.listar_piezas_fila():
        por_contenido.setdefault(plat["publicacion_id"], []).append(plat)
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
    enlaza a la pieza en el tablero (`publicacion_id` -> `/operacion/feed/lista`).

    `?marca=` (en forma `id_metricas`, como el resto de Analíticas) acota a una marca;
    sin marca, agrega todas. Degradación honesta: las piezas que Metricool aún no tiene
    salen con `encontrado=False` (la UI muestra "sin datos todavía", nunca ceros falsos).
    """
    marca_metricas, rechazo = _gate_marca_metricas(
        request, request.query_params.get("marca") or None
    )
    if rechazo is not None:
        return rechazo
    marca_consola = _marca_consola_de_metricas(marca_metricas)
    try:
        # Lee BD + golpea Metricool por pieza (lazy-fill con TTL): potencialmente lento, así
        # que se ejecuta en el threadpool para no bloquear el event loop al cambiar de tab.
        piezas = await run_in_threadpool(_listado_piezas_publicadas, marca_consola)
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
    `/api/metricas/piezas-rendimiento` (las piezas de la Consola con su
    rendimiento real), esto devuelve TODAS las piezas de la(s) cuenta(s) del periodo
    tal como las emite la fuente única (`servicio.construir_listado_piezas`): cada una
    con su id de Metricool, granulares y url. Es el insumo de la tabla "Todas las piezas
    del periodo" (con buscador + orden + detalle por pieza). Servido desde cache (lazy fill).

    `?marca=` (en forma `id_metricas`) acota a una marca; sin marca, agrega todas.
    `?red=a,b` acota a esas redes (combinación libre) y `?formato=a,b` a esos formatos
    canónicos; sin filtro, todas. La cache guarda el listado completo y el recorte por
    red/formato se aplica aquí sobre la salida (valor desconocido →400).
    """
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    try:
        redes = _validar_redes(request.query_params.get("red"))
        formatos = _validar_formatos(request.query_params.get("formato"))
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    marca, rechazo = _gate_marca_metricas(request, request.query_params.get("marca") or None)
    if rechazo is not None:
        return rechazo
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
    piezas_crudas = payload.get("piezas", [])
    # Enriquecemos cada pieza con su CATEGORÍA editorial (cruce con la BD) y normalizamos el
    # campo `red` -> `plataforma` (contrato `PiezaListado`). El cruce de categorías es trabajo
    # bloqueante de BD: va en el threadpool para no congelar el event loop. La cache guarda
    # el listado crudo; la categoría se resuelve aquí (lectura de BD barata, sin volver a Metricool).
    marca_consola = _marca_consola_de_metricas(marca)
    try:
        categoria_map = await run_in_threadpool(
            metricas_categoria.categorias_por_pieza, marca_consola, piezas_crudas
        )
    except Exception:  # noqa: BLE001 -- la categoría es best-effort; sin ella, todo "Sin categoría"
        _log.exception("Fallo al resolver categorías del listado (marca=%s).", marca or "todas")
        categoria_map = {}
    piezas = [_pieza_listado_serializable(p, categoria_map) for p in piezas_crudas]
    total = payload.get("total", 0)
    # Recorte por red(es): el contrato `PiezaListado` emite la red en `plataforma`
    # (con `twitter` ya normalizado a `x` en la fuente). Una pieza fuera del foco
    # desaparece del listado por completo, igual que en el resto del dashboard.
    if redes:
        piezas = [p for p in piezas if (p.get("plataforma") or "").lower() in redes]
        total = len(piezas)
    # Recorte por formato(s) canónico(s): una pieza cuyo formato canónico no está en el
    # foco desaparece del listado, igual que con la red.
    if formatos:
        fmts = _conjunto_formatos(formatos)
        piezas = [p for p in piezas if _formato_canonico(p.get("formato") or "") in fmts]
        total = len(piezas)
    return JSONResponse(
        {
            "rango": rango,
            "etiqueta_rango": _etiqueta_rango(rango),
            "marca": marca or "",
            "periodo": payload.get("periodo") or {"desde": "", "hasta": ""},
            "fuente": payload.get("fuente") or "muestra",
            "piezas": piezas,
            "total": total,
            "generado_en": generado_en,
        }
    )


def _pieza_listado_serializable(p: dict, categoria_map: dict[str, str]) -> dict:
    """Adapta una pieza del listado crudo al contrato `PiezaListado`.

    El listado de la fuente (`construir_listado_piezas`) emite la red como `red`; el
    contrato (y la UI) la esperan como `plataforma`. Además añade `categoria` (nombre de la
    categoría editorial, o `null` si no es atribuible — `categoria_map` solo trae las resueltas).
    El resto de campos (granulares, url, cuenta, rendimiento_relativo) pasa tal cual.
    """
    salida = dict(p)
    salida["plataforma"] = p.get("plataforma") or p.get("red") or ""
    salida.pop("red", None)
    salida["categoria"] = categoria_map.get(str(p.get("id") or "")) or None
    return salida


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
    # RIESGO RESIDUAL (alcance por marca): `id` es un id de pieza de Metricool (espacio plano,
    # sin marca asociada en la tabla de snapshots). Acotar esto por tenant exigiria un cruce/
    # columna de marca en `metricas_pieza_snapshots` (cambio de db.py, reservado a otro agente).
    # Datos de baja sensibilidad (serie de vis/inter de UNA pieza) -> se deja al dueño cerrarlo
    # cuando exista el cruce. Ver ADR 0003.
    try:
        serie = await run_in_threadpool(repos.serie_pieza, pieza_id)
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
    `?marca=` (en forma `id_metricas`) acota; sin marca, todas. `?red=a,b` acota a esas
    redes y `?formato=a,b` a esos formatos canónicos (valor desconocido →400); las piezas
    fuera del foco no entran en la agregación. Trabajo bloqueante (BD + listado de piezas de
    la fuente) en executor para no congelar el event loop.
    """
    marca_metricas, rechazo = _gate_marca_metricas(
        request, request.query_params.get("marca") or None
    )
    if rechazo is not None:
        return rechazo
    marca_consola = _marca_consola_de_metricas(marca_metricas)
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    try:
        redes = _validar_redes(request.query_params.get("red"))
        formatos = _validar_formatos(request.query_params.get("formato"))
        payload = await run_in_threadpool(
            metricas_pieza.analitica_por_etiqueta,
            rango, marca_consola, marca_metricas, redes, formatos,
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


async def categorias(request: Request) -> Response:
    """GET /api/metricas/categorias: rendimiento del periodo por CATEGORÍA y por ORIGEN.

    Agrupa el rendimiento REAL de las piezas del periodo por su CATEGORÍA editorial (etiqueta
    clase `categoria`) y por su ORIGEN (clase `origen`), cruzando las piezas de la fuente
    única de métricas con su `contenido` de la BD (enlace por `id_post_metricool`; fallback
    fuzzy por título), igual que `piezas-por-etiqueta`. Devuelve, por cada cubo, nº de
    piezas + suma de visualizaciones + suma de interacciones + engagement medio. Las piezas
    sin categoría/origen caen en "Sin categoría"/"Sin origen".

    `?marca=` (en forma `id_metricas`) acota; sin marca, todas. `?rango=` (preset o token).
    `?red=a,b` acota a esas redes y `?formato=a,b` a esos formatos canónicos (valor
    desconocido →400); las piezas fuera del foco no entran en la agregación. Trabajo
    bloqueante (BD + listado de piezas de la fuente) en executor para no congelar el event
    loop.
    """
    marca_metricas, rechazo = _gate_marca_metricas(
        request, request.query_params.get("marca") or None
    )
    if rechazo is not None:
        return rechazo
    marca_consola = _marca_consola_de_metricas(marca_metricas)
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    try:
        redes = _validar_redes(request.query_params.get("red"))
        formatos = _validar_formatos(request.query_params.get("formato"))
        payload = await run_in_threadpool(
            metricas_categoria.categorias_y_origenes,
            rango, marca_consola, marca_metricas, redes, formatos,
        )
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        _log.exception(
            "Fallo al generar la analítica por categoría (rango=%s, marca=%s).",
            rango, marca_metricas or "todas",
        )
        return JSONResponse(
            {"error": "No se pudo generar la analítica por categoría."}, status_code=500
        )
    return JSONResponse(
        {
            "marca": marca_metricas or "",
            "rango": rango,
            "etiqueta_rango": _etiqueta_rango(rango),
            **payload,
        }
    )
