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
    RANGOS_PRESET_UI,
    _conjunto_formatos,
    _conjunto_redes,
    _etiqueta_rango,
    _formato_canonico,
    _gate_marca_metricas,
    _log,
    _nombre_marca_id,
    _validar_formatos,
    _validar_rango,
    _validar_redes,
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
    "_filtrar_reporte_por_red",
    "_recomputar_reporte_por_formato",
]


def _variacion_pct(a: float | None, b: float | None) -> float | None:
    """Variacion de A respecto a B en %. None si falta algun dato (alcance/
    engagement pueden ser n/d); 0.0 si B es 0 (no divide entre cero)."""
    if a is None or b is None:
        return None
    return round((a - b) / b * 100, 1) if b else 0.0


def _delta(a: float | None, b: float | None) -> float | None:
    """Diferencia A-B tolerante a None (alcance/engagement pueden ser n/d)."""
    if a is None or b is None:
        return None
    return a - b


def _fuente_combinada(rep_a: dict, rep_b: dict) -> str:
    """Fuente de una comparativa A vs B: "muestra" si CUALQUIERA de los dos lo es.

    La comparativa cruza dos reportes; basta con que uno sea de datos de muestra para
    que el resultado deba advertirse como muestra (no se mezclan datos ficticios con
    reales sin que la UI lo marque). Cae a "muestra" por prudencia si falta el campo
    (riesgo operativo del piloto), igual que `/reporte`.
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
    heterogéneos). Se RECALCULA int/vis por periodo —igual que
    `_reporte_serializable`— para que deje de salir "—".

    NO incluye `alcance` en la comparativa: puede ser null cuando ninguna red Meta lo
    reporta y una fila con valor null revienta el comparador. El alcance se lee por red en
    la tabla, no en las tarjetas comparadas.
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

    Suma `visualizaciones`, `impresiones` e `interacciones`; el `alcance` suma solo los
    no-null y queda `None` si NINGUNA cuenta mide esa red (criterio igual que el `total`:
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
                red,
                {"visualizaciones": 0, "impresiones": 0, "alcance": None, "interacciones": 0},
            )
            d["visualizaciones"] += p.get("visualizaciones", 0) or 0
            d["impresiones"] += p.get("impresiones", 0) or 0
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
                "impresiones": d["impresiones"],
                "alcance": d["alcance"],
                "interacciones": inter,
                "engagement_pct": _engagement_pct(inter, vis),
            }
        )
    por_red.sort(key=lambda x: x["visualizaciones"], reverse=True)
    return por_red


def _comparar_por_red(rep_a: dict, rep_b: dict) -> list[dict]:
    """Comparativa metrica-a-metrica por red (union de las redes de A y B).

    Espejo de `_comparar_por_marca`: agrega cada periodo por red con `_agregar_por_red`
    (suma entre TODAS las marcas del reporte) y compara visualizaciones/interacciones
    (con su engagement recalculado) red a red, para que la comparativa de periodos se
    pueda leer desglosada por red además de por marca.
    """
    red_a = {r["red"]: r for r in _agregar_por_red(rep_a)}
    red_b = {r["red"]: r for r in _agregar_por_red(rep_b)}
    redes: list[str] = list(red_a.keys())
    for red in red_b:
        if red not in red_a:
            redes.append(red)

    filas = []
    for red in redes:
        ra = red_a.get(red, {})
        rb = red_b.get(red, {})
        filas.append(
            {
                "red": red,
                "comparativa": _comparar_totales(
                    {k: ra.get(k, 0) for k in ("visualizaciones", "interacciones")},
                    {k: rb.get(k, 0) for k in ("visualizaciones", "interacciones")},
                )["metricas"],
            }
        )
    return filas


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
                            "stories": p.get("stories"),
                            "motivo": None,
                        }
                    )
                else:
                    # Conectada pero SIN actividad en el rango: métricas a null (no un 0/0.0%
                    # falso) + motivo, igual que el resto de estados no-con_datos.
                    redes.append(
                        {
                            "red": red,
                            "estado": "sin_metricas",
                            "visualizaciones": None,
                            "alcance": None,
                            "interacciones": None,
                            "engagement_pct": None,
                            # Stories es VOLUMEN (no rendimiento): se muestra aunque la red no
                            # tenga vis/interacciones de posts/reels en el periodo.
                            "stories": p.get("stories"),
                            "motivo": _MOTIVO_COBERTURA["sin_metricas"],
                        }
                    )
            else:
                if red in omitidas:
                    motivo_id = str(motivos.get(red, "error_api"))
                    estado = "sin_lectura" if motivo_id == "error_api" else motivo_id
                else:
                    estado = "no_configurada"
                motivo = _MOTIVO_COBERTURA.get(estado, _MOTIVO_COBERTURA["sin_lectura"])
                redes.append(
                    {
                        "red": red,
                        "estado": estado,
                        "visualizaciones": None,
                        "alcance": None,
                        "interacciones": None,
                        "engagement_pct": None,
                        "stories": None,
                        "motivo": motivo,
                    }
                )
        salida.append({"marca_id": cid, "marca": _nombre_marca_id(cid, nombres), "redes": redes})
    return salida


def _engagement_pct(interacciones, visualizaciones) -> float:
    """Engagement de DISPLAY = interacciones ÷ vistas × 100 (0.0 si no hay vistas).

    El `engagement_pct` AGREGADO del resumen es `None` cuando la marca tiene varias redes
    (denominadores heterogéneos). Para el reporte que pinta la UI lo derivamos
    siempre como un número (int/vis), igual que ya hacían las tablas en cliente: así nunca
    llega `null` (que reventaba el comparador) y el engagement deja de salir "—" en todo.

    Coacciona `None`→0 y delega en la fórmula única del monorepo (`keni_shared`).
    """
    return engagement_pct(interacciones or 0, visualizaciones or 0)


def _filtrar_reporte_por_red(rep: dict, red, piezas_red: int) -> dict:
    """Copia del reporte CRUDO restringida a una o VARIAS redes, lista para `_reporte_serializable`.

    `red` admite un id, una colección de ids o None (todas). Cada cuenta queda con las
    métricas SUMADAS de las redes elegidas —sus entradas de `por_plataforma`, o 0/None si
    no tiene ninguna— y `por_plataforma` reducido a esas redes; la `cobertura` se conserva
    para que la auditoría siga clasificando las redes. El total se re-suma sobre las cuentas
    filtradas (no se toma el global). `MetricaPlataforma` no cuenta piezas, así que
    `total.piezas` viene del conteo del LISTADO por red (`piezas_red`), no del global.
    """
    reds = _conjunto_redes(red)
    cuentas: list[dict] = []
    tot_vis = tot_inter = tot_impr = 0
    tot_alc: int | None = None
    for fila in rep.get("cuentas", []):
        r = dict(fila.get("resumen") or {})
        de_red = [p for p in (r.get("por_plataforma") or []) if p.get("plataforma") in reds]
        vis = sum(p.get("visualizaciones", 0) or 0 for p in de_red)
        impr = sum(p.get("impresiones", 0) or 0 for p in de_red)
        inter = sum(p.get("interacciones", 0) or 0 for p in de_red)
        alcs = [p.get("alcance") for p in de_red if p.get("alcance") is not None]
        alc = sum(alcs) if alcs else None
        r["visualizaciones"] = vis
        r["impresiones"] = impr
        r["interacciones"] = inter
        r["alcance"] = alc
        r["por_plataforma"] = de_red
        cuentas.append({**fila, "resumen": r})
        tot_vis += vis
        tot_impr += impr
        tot_inter += inter
        if alc is not None:
            tot_alc = (tot_alc or 0) + alc
    nuevo = dict(rep)
    nuevo["cuentas"] = cuentas
    nuevo["total"] = {
        **(rep.get("total") or {}),
        "visualizaciones": tot_vis,
        "impresiones": tot_impr,
        "alcance": tot_alc,
        "interacciones": tot_inter,
        "engagement_pct": None,
        "piezas": piezas_red,
    }
    return nuevo


def _recomputar_reporte_por_formato(salida: dict, listado: dict, redes, formatos) -> dict:
    """Recalcula `total`, `cuentas` y `por_red` DESDE LAS PIEZAS cuando hay filtro de formato.

    El reporte cacheado agrega por red sin dimensión de formato, así que un filtro de formato
    no se puede proyectar sobre él: se recompone desde el listado de piezas del periodo (mismo
    coste 0 de API, cache lazy fill) quedándose con las que pasan formato CANÓNICO ∩ red.
    `visualizaciones`/`interacciones` son sumables; `engagement_pct` se agrupa
    (interacciones/visualizaciones); `alcance` NO es sumable a nivel pieza, así que queda
    `None` cuando el filtro de formato está activo. `cobertura_redes` se deja como está (no
    tiene dimensión de formato). El resto de `salida` (rango, marca, fuente…) se conserva.
    """
    reds = _conjunto_redes(redes)
    fmts = _conjunto_formatos(formatos)
    piezas = [
        p
        for p in (listado.get("piezas") or [])
        if _formato_canonico(p.get("formato") or "") in fmts
        and (not reds or p.get("red") in reds)
    ]

    def _vis(p: dict) -> int:
        return int(p.get("visualizaciones") or 0)

    def _impr(p: dict) -> int:
        return int(p.get("impresiones") or 0)

    def _inter(p: dict) -> int:
        return int(p.get("interacciones") or 0)

    tot_vis = sum(_vis(p) for p in piezas)
    tot_impr = sum(_impr(p) for p in piezas)
    tot_inter = sum(_inter(p) for p in piezas)
    salida = dict(salida)
    salida["total"] = {
        "visualizaciones": tot_vis,
        # impresiones (veces mostrada) SÍ es aditiva entre piezas: se suma como las vistas.
        "impresiones": tot_impr,
        # El alcance (usuarios únicos) no es sumable entre piezas: con filtro de formato
        # no hay un agregado honesto, así que se omite (None) en vez de inventar una suma.
        "alcance": None,
        "interacciones": tot_inter,
        "engagement_pct": _engagement_pct(tot_inter, tot_vis),
        "piezas": len(piezas),
    }

    # Nombre legible por id de marca: reaprovecha el que ya resolvió `_reporte_serializable`.
    nombres = {c.get("marca_id", ""): c.get("marca", "") for c in salida.get("cuentas") or []}

    por_red_acc: dict[str, dict[str, int]] = {}
    cuentas_acc: dict[str, dict[str, int]] = {}
    for p in piezas:
        red = p.get("red") or ""
        dr = por_red_acc.setdefault(
            red, {"visualizaciones": 0, "impresiones": 0, "interacciones": 0}
        )
        dr["visualizaciones"] += _vis(p)
        dr["impresiones"] += _impr(p)
        dr["interacciones"] += _inter(p)
        cid = p.get("cuenta") or ""
        dc = cuentas_acc.setdefault(
            cid, {"visualizaciones": 0, "impresiones": 0, "interacciones": 0}
        )
        dc["visualizaciones"] += _vis(p)
        dc["impresiones"] += _impr(p)
        dc["interacciones"] += _inter(p)

    por_red = [
        {
            "red": red,
            "visualizaciones": d["visualizaciones"],
            "impresiones": d["impresiones"],
            "alcance": None,
            "interacciones": d["interacciones"],
            "engagement_pct": _engagement_pct(d["interacciones"], d["visualizaciones"]),
        }
        for red, d in por_red_acc.items()
    ]
    por_red.sort(key=lambda x: x["visualizaciones"], reverse=True)
    salida["por_red"] = por_red

    salida["cuentas"] = [
        {
            "marca_id": cid,
            "marca": nombres.get(cid) or _nombre_marca_id(cid, {}),
            "visualizaciones": d["visualizaciones"],
            "impresiones": d["impresiones"],
            "alcance": None,
            "interacciones": d["interacciones"],
            "engagement_pct": _engagement_pct(d["interacciones"], d["visualizaciones"]),
        }
        for cid, d in cuentas_acc.items()
    ]
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
                # impresiones: veces que el contenido se mostró (volumen aditivo). 0 si la
                # fuente no la expone.
                "impresiones": r.get("impresiones") or 0,
                # alcance: suma de alcances por post Meta (IG/FB); 0 si ningún post lo
                # reporta o la red no es Meta.
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
        # reales (riesgo operativo del piloto). Cae a "muestra" por prudencia.
        "fuente": rep.get("fuente") or "muestra",
        "total": {
            "visualizaciones": t.get("visualizaciones", 0),
            # impresiones: cifra de VOLUMEN de cabecera (aditiva por post → red → total). 0
            # si la fuente no la expone.
            "impresiones": t.get("impresiones") or 0,
            # alcance: usuarios únicos. None cuando la fuente no mide alcance de cuenta (no
            # se coacciona a 0: un 0 falso ocultaría que el dato no existe).
            "alcance": t.get("alcance"),
            "interacciones": t.get("interacciones", 0),
            "engagement_pct": _engagement_pct(t.get("interacciones"), t.get("visualizaciones")),
            "piezas": t.get("piezas", 0),
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
    # Solo los presets OFRECIDOS (sin "7d"/"30d", duplicados exactos de "semana"/"mes");
    # la validacion de entrada sigue aceptando RANGOS_VALIDOS, asi un token persistido no rompe.
    rangos = [{"id": r, "etiqueta": _etiqueta_rango(r)} for r in RANGOS_PRESET_UI]
    return JSONResponse({"marcas": marcas_lista, "rangos": rangos})


async def reporte(request: Request) -> Response:
    rango = _validar_rango(request.query_params.get("rango", "mes"))
    marca, rechazo = _gate_marca_metricas(request, request.query_params.get("marca") or None)
    if rechazo is not None:
        return rechazo
    try:
        # `red` admite una o VARIAS redes (combinación a antojo); None = todas (igual que
        # antes). `formato` admite uno o varios ids canónicos. Validación primero: un valor
        # mal escrito falla limpio (→400).
        redes = _validar_redes(request.query_params.get("red"))
        formatos = _validar_formatos(request.query_params.get("formato"))
        # Lee de cache (instantaneo); si el combo falta, lo calcula al vuelo y lo guarda.
        # En executor: un combo frío golpea la API externa y NO debe bloquear el loop.
        rep, generado_en = await metricas_cache.reporte_async(rango, marca)
        listado = None
        if redes or formatos:
            # El listado cacheado por (rango, marca) es el insumo por-pieza que necesitan
            # tanto el conteo de piezas por red como el recálculo por formato (coste 0 API).
            listado, _ = await metricas_cache.piezas_listado_async(rango, marca)
        if redes and not formatos:
            # El conteo de piezas por red NO está en el resumen (`por_plataforma` no
            # cuenta piezas): se deriva del listado filtrando por plataforma.
            piezas_red = sum(
                1 for p in (listado.get("piezas") or []) if p.get("red") in redes
            )
            rep = _filtrar_reporte_por_red(rep, redes, piezas_red)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        _log.exception("Fallo al generar el reporte (rango=%s, marca=%s).", rango, marca or "todas")
        return JSONResponse({"error": "No se pudo generar el reporte."}, status_code=500)
    salida = _reporte_serializable(rep, rango, marca)
    if formatos:
        # Con filtro de formato el reporte se recompone desde las piezas (red ∩ formato):
        # total/cuentas/por_red salen del listado, no del resumen cacheado sin formato.
        salida = _recomputar_reporte_por_formato(salida, listado, redes, formatos)
    if redes:
        # Con filtro de red, la auditoría de cobertura muestra SOLO esas redes por marca
        # (la vista "solo de Instagram + …" no lista el resto de redes). El campo `red` se
        # emite como CSV (igual que entra), así una sola red queda como su id a secas.
        salida["red"] = ",".join(redes)
        salida["cobertura_redes"] = [
            {**m, "redes": [r for r in m["redes"] if r["red"] in redes]}
            for m in salida["cobertura_redes"]
        ]
    if formatos:
        # Eco del filtro de formato como CSV (igual que `red`), para que la UI sepa que las
        # cifras están recompuestas sobre esos formatos.
        salida["formato"] = ",".join(formatos)
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
            # /reporte) para no confundir datos de muestra con reales (piloto).
            "fuente": _fuente_combinada(rep_a, rep_b),
            "total": _comparar_totales(
                _total_comparable(rep_a, des_a, seg_a, lis_a),
                _total_comparable(rep_b, des_b, seg_b, lis_b),
            ),
            "por_marca": _comparar_por_marca(rep_a, rep_b),
            "por_red": _comparar_por_red(rep_a, rep_b),
        }
    )
