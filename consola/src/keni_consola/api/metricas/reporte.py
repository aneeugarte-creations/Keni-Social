"""Endpoints de reporte consolidado: `opciones`, `reporte`, `comparar`.

`opciones` puebla los selectores (marcas + rangos); `reporte` da el total consolidado
+ por cuenta (nombres resueltos); `comparar` cruza dos periodos (total + por marca).
Todos los helpers de serialización/comparación de ESTOS tres endpoints viven aquí.
"""

from __future__ import annotations

import asyncio

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ._comun import (
    RANGOS_VALIDOS,
    _etiqueta_rango,
    _gate_marca_metricas,
    _log,
    _nombre_marca_id,
    _validar_rango,
    engagement_pct,
    marcas,
    metricas_cache,
)

__all__ = [
    "opciones",
    "reporte",
    "comparar",
    "_comparar_totales",
    "_suma_clics",
    "_cobertura_por_marca",
]


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


# Métricas de CONTEO comparables entre dos periodos, en orden de presentación. Son
# sumas homogéneas (no porcentajes), así que su delta/variación se calculan igual.
# `visualizaciones`/`interacciones` vienen del reporte; el resto (granulares +
# seguidores) se inyectan desde el desglose y la serie de seguidores (ver
# `_total_comparable`). Una métrica ausente en este nivel (p. ej. el desglose por marca
# solo trae vistas/interacciones) se OMITE: no se pinta una tarjeta con datos a medias.
_METRICAS_CONTEO_COMPARABLES: tuple[str, ...] = (
    "visualizaciones",
    "interacciones",
    "likes",
    "comentarios",
    "compartidos",
    "guardados",
    "video_views",
    "clics_enlace",
    "seguidores_netos",
)


def _comparar_totales(total_a: dict, total_b: dict) -> dict:
    """Comparativa del total consolidado: conteos (vistas, interacciones, granulares,
    seguidores) + engagement.

    A = periodo "antes", B = periodo "actual" (así lo pinta la UI: B es el valor grande,
    A el "antes"). La VARIACIÓN y la DIFERENCIA miden B respecto a A —cuánto cambió lo
    ACTUAL frente a lo ANTERIOR—; al revés (A respecto a B) la flecha y el signo salían
    invertidos (subir 170M→236M aparecía como −28 % en vez de +39 %).

    Solo se emiten las métricas de conteo presentes en los totales (las ausentes se
    omiten: el desglose por marca trae menos que el total global). El engagement NO se
    toma crudo del total: viene `None` cuando hay varias redes (denominadores
    heterogéneos, #138). Se RECALCULA int/vis por periodo —igual que
    `_reporte_serializable`— para que deje de salir "—".

    NO incluye `alcance`: no se mide con la fuente de posts (sería siempre null y la UI ya
    no lo muestra). Emitirlo dejaba una fila con valor null que reventaba el comparador.
    """
    metricas = []
    for clave in _METRICAS_CONTEO_COMPARABLES:
        va = total_a.get(clave)
        vb = total_b.get(clave)
        if va is None and vb is None:
            continue  # métrica no provista a este nivel (no se inventa una tarjeta vacía)
        metricas.append(
            {
                "metrica": clave,
                "a": va,
                "b": vb,
                # B (actual) respecto a A (antes): el sentido que ve el operador.
                "diferencia": _delta(vb, va),
                "variacion_pct": _variacion_pct(vb, va),
            }
        )
    eng_a = _engagement_pct(total_a.get("interacciones"), total_a.get("visualizaciones"))
    eng_b = _engagement_pct(total_b.get("interacciones"), total_b.get("visualizaciones"))
    eng_d = _delta(eng_b, eng_a)
    metricas.append(
        {
            "metrica": "engagement_pct",
            "a": eng_a,
            "b": eng_b,
            "diferencia": round(eng_d, 1) if eng_d is not None else None,
            "variacion_pct": _variacion_pct(eng_b, eng_a),
        }
    )
    return {"metricas": metricas}


# Granulares que el desglose (`/api/metricas/desglose` › `totales`) ya agrega por periodo.
_GRANULARES_DESGLOSE: tuple[str, ...] = (
    "likes",
    "comentarios",
    "compartidos",
    "guardados",
    "video_views",
)


def _suma_clics(listado: dict) -> int | None:
    """Suma `clics_enlace` del listado de piezas del periodo. None si NINGUNA lo expone.

    Los clics no se agregan en el desglose (solo existen a nivel pieza), así que se suman
    aquí desde el listado de piezas ya cacheado. None (no 0) cuando ninguna pieza trae el
    dato: degradación honesta (la tarjeta no se pinta en vez de un 0 falso)."""
    piezas = (listado or {}).get("piezas") or []
    presentes = [p.get("clics_enlace") for p in piezas if p.get("clics_enlace") is not None]
    return sum(presentes) if presentes else None


def _total_comparable(rep: dict, desglose: dict, seguidores: dict, listado: dict) -> dict:
    """Total de un periodo enriquecido para la comparativa: reporte + granulares + seguidores.

    Parte del `total` del reporte (vistas, interacciones) y le añade, SIN tocar el MCP:
      - los granulares (likes/comentarios/compartidos/guardados/reproducciones) que el
        DESGLOSE ya suma por periodo (`totales`);
      - los CLICS a enlace, sumados del listado de piezas (no están en el desglose);
      - el neto de SEGUIDORES del periodo (serie de seguidores › `neto`).

    Así la comparativa muestra esas métricas que antes faltaban. Cada campo queda en `None`
    si su fuente no lo expone (degradación honesta: la tarjeta no se pinta en vez de mostrar
    un 0 falso); `seguidores_netos` sí puede ser 0 real (stock plano en el periodo).
    """
    total = dict(rep.get("total") or {})
    tg = (desglose or {}).get("totales") or {}
    for clave in _GRANULARES_DESGLOSE:
        total[clave] = tg.get(clave)
    total["clics_enlace"] = _suma_clics(listado)
    # La serie de seguidores siempre trae `neto` (0 si la fuente no expone followers).
    total["seguidores_netos"] = (seguidores or {}).get("neto")
    return total


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
                    # engagement se RECALCULA dentro a partir de int/vis; no se pasa crudo.
                    {k: ra.get(k, 0) for k in ("visualizaciones", "interacciones")},
                    {k: rb.get(k, 0) for k in ("visualizaciones", "interacciones")},
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
                "engagement_pct": _engagement_pct(inter, vis),
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
    "no_conectada": "Esta red no está conectada a Metricool para la marca.",
    "sin_lectura": (
        "No se pudo leer de Metricool: error temporal de la API o métrica no disponible "
        "en el plan."
    ),
    "no_configurada": "Esta red no está dada de alta en Metricool para la marca.",
    "sin_credenciales": "Faltan credenciales para leer esta red.",
    "presupuesto_agotado": "Límite de la API de Metricool alcanzado; reintenta más tarde.",
}

# Override de motivo para casos CONOCIDOS por (red, estado). X (Twitter) en Metricool es
# una LICENCIA APARTE no contratada en el piloto: por eso sale "no conectada" en TODAS las
# marcas. Se aclara para que el equipo no intente "conectarla" (es una decisión de
# contratación, no un hueco de configuración). simpleProfiles no distingue este caso del
# genérico —ambos son `twitter: null`—, así que el matiz se añade aquí.
_MOTIVO_RED_ESPECIAL: dict[tuple[str, str], str] = {
    ("x", "no_conectada"): "Requiere licencia adicional de Metricool (no contratada).",
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
                if vis or inter:
                    redes.append(
                        {
                            "red": red,
                            "estado": "con_datos",
                            "visualizaciones": vis,
                            "alcance": p.get("alcance"),
                            "interacciones": inter,
                            "engagement_pct": p.get("engagement_pct", 0.0),
                            "motivo": None,
                        }
                    )
                else:
                    # Conectada pero SIN actividad en el rango: métricas a null (no un 0/0.0%
                    # falso) + motivo, igual que el resto de estados no-con_datos. Antes
                    # emitía 0/0/0.0%, que se leía como dato real (justo lo que mina la
                    # confianza en la página).
                    redes.append(
                        {
                            "red": red,
                            "estado": "sin_metricas",
                            "visualizaciones": None,
                            "alcance": None,
                            "interacciones": None,
                            "engagement_pct": None,
                            "motivo": _MOTIVO_COBERTURA["sin_metricas"],
                        }
                    )
            else:
                if red in omitidas:
                    motivo_id = str(motivos.get(red, "error_api"))
                    estado = "sin_lectura" if motivo_id == "error_api" else motivo_id
                else:
                    estado = "no_configurada"
                motivo = _MOTIVO_RED_ESPECIAL.get((red, estado)) or _MOTIVO_COBERTURA.get(
                    estado, _MOTIVO_COBERTURA["sin_lectura"]
                )
                redes.append(
                    {
                        "red": red,
                        "estado": estado,
                        "visualizaciones": None,
                        "alcance": None,
                        "interacciones": None,
                        "engagement_pct": None,
                        "motivo": motivo,
                    }
                )
        salida.append({"marca_id": cid, "marca": _nombre_marca_id(cid, nombres), "redes": redes})
    return salida


def _engagement_pct(interacciones, visualizaciones) -> float:
    """Engagement de DISPLAY = interacciones ÷ vistas × 100 (0.0 si no hay vistas).

    El `engagement_pct` AGREGADO del resumen es `None` cuando la marca tiene varias redes
    (denominadores heterogéneos, ADR/#138). Para el reporte que pinta la UI lo derivamos
    siempre como un número (int/vis), igual que ya hacían las tablas en cliente: así nunca
    llega `null` (que reventaba el comparador) y el engagement deja de salir "—" en todo.

    Coacciona `None`→0 y delega en la fórmula única del monorepo (`keni_shared`, #97).
    """
    return engagement_pct(interacciones or 0, visualizaciones or 0)


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
                # alcance no se mide con posts -> 0 (nunca null; la UI ya no lo muestra).
                "alcance": r.get("alcance") or 0,
                "interacciones": r.get("interacciones", 0),
                "engagement_pct": _engagement_pct(r.get("interacciones"), r.get("visualizaciones")),
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
            "alcance": t.get("alcance") or 0,
            "interacciones": t.get("interacciones", 0),
            "engagement_pct": _engagement_pct(t.get("interacciones"), t.get("visualizaciones")),
        },
        "cuentas": cuentas,
        "por_red": por_red,
        "cobertura_redes": _cobertura_por_marca(rep),
    }


async def opciones(request: Request) -> Response:
    # La frontera con metricas habla en `id_metricas` (guion_bajo): este `id` es el
    # que viaja como `?marca=` y acota la fuente (FuenteScoped), no el id canonico.
    # El selector ofrece TODAS las marcas: cualquiera puede consultar las metricas de cualquier
    # marca (el equipo es multidisciplinar). La marca preferente solo fija el foco por defecto
    # del SPA, no recorta el catalogo.
    pares = marcas.opciones_metricas()
    marcas_lista = [{"id": mid, "nombre": etiqueta} for mid, etiqueta in pares]
    rangos = [{"id": r, "etiqueta": _etiqueta_rango(r)} for r in RANGOS_VALIDOS]
    return JSONResponse({"marcas": marcas_lista, "rangos": rangos})


async def reporte(request: Request) -> Response:
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    marca, rechazo = _gate_marca_metricas(request, request.query_params.get("marca") or None)
    if rechazo is not None:
        return rechazo
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
    marca, rechazo = _gate_marca_metricas(request, request.query_params.get("marca") or None)
    if rechazo is not None:
        return rechazo
    try:
        # Reporte + desglose (granulares) + seguidores de AMBOS periodos, todo de cache
        # (lazy fill) y CONCURRENTE (gather): combos fríos no bloquean el event loop y, si
        # están fríos, se calculan en paralelo. El desglose aporta likes/comentarios/…
        # y la serie de seguidores el neto; con eso la comparativa deja de ir a medias.
        (
            (rep_a, gen_a),
            (rep_b, gen_b),
            (des_a, _da),
            (des_b, _db),
            (seg_a, _sa),
            (seg_b, _sb),
            (lis_a, _la),
            (lis_b, _lb),
        ) = await asyncio.gather(
            metricas_cache.reporte_async(rango_a, marca),
            metricas_cache.reporte_async(rango_b, marca),
            metricas_cache.desglose_async(rango_a, marca),
            metricas_cache.desglose_async(rango_b, marca),
            metricas_cache.seguidores_async(rango_a, marca),
            metricas_cache.seguidores_async(rango_b, marca),
            metricas_cache.piezas_listado_async(rango_a, marca),
            metricas_cache.piezas_listado_async(rango_b, marca),
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
            "total": _comparar_totales(
                _total_comparable(rep_a, des_a, seg_a, lis_a),
                _total_comparable(rep_b, des_b, seg_b, lis_b),
            ),
            "por_marca": _comparar_por_marca(rep_a, rep_b),
        }
    )
