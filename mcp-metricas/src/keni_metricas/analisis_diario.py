"""Análisis del periodo: lectura multi-dimensión "qué pasó y por qué".

Los datos ya existen (`construir_reporte` + `picos` + `mejores_piezas` + la serie de
seguidores y la serie diaria); lo que falta es la LECTURA. Sobre las métricas de un
periodo emite una lista de HALLAZGOS jerarquizados (lo más relevante primero) que
cubren dimensiones DISTINTAS —vistas por marca, red que empujó, formato que despunta,
seguidores (con la señal de variación representativa), engagement, pieza estrella y la
variación propia del periodo (semana ≠ mes)—, más un siguiente paso accionable. No es
un cálculo nuevo de métricas: ENSAMBLA lo que ya producen el reporte consolidado, el
detector de picos y las series, y lo redacta en castellano llano para alguien que NO
está inmerso en métricas.

Frontera (UX-roadmap §0): keni-social CONSOLIDA y SUGIERE; la interpretación final y la
decisión de qué cambiar quedan en el equipo. Los hallazgos NO atribuyen causas de
coyuntura externas: se limitan a "este número se movió y esto lo acompaña", más una
sugerencia de loop a la acción.

Honestidad: si la fuente es de muestra, el análisis lo MARCA en la estructura
(`es_muestra`/`aviso`) y en el render. Si una marca no tiene engagement comparable o el
reporte viene vacío, degrada sin inventar. El umbral de movimiento deja de ser una
puerta binaria: por debajo se narra como estabilidad (cifra + contexto), no se calla.
"""

from __future__ import annotations

import statistics
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from .formato import (
    AVISO_MUESTRA_TXT,
    aviso_muestra_md,
    es_fuente_muestra,
    etiqueta_marca,
    miles,
    signo,
)
from .fuentes.base import FuenteMetricas
from .picos import detectar_picos
from .reporte import construir_reporte

if TYPE_CHECKING:
    from .historico import Historico

# Umbral (en puntos %) a partir del cual una variación de visualizaciones se considera
# un "movimiento" fuerte (dirección sube/baja); por debajo se narra como estabilidad
# ("sin cambios relevantes"), NO se calla. Señal sobre ruido: un ±2% no es noticia.
UMBRAL_MOVIMIENTO_PCT = 5.0

# Cuántas marcas describir como movimiento de vistas antes de colapsar el resto en una
# línea (mismo criterio top-N + resto que picos/dashboard).
MAX_MOVIMIENTOS = 3

# Nº mínimo de hallazgos que se intenta emitir cuando hay datos, cubriendo dimensiones
# distintas (petición de Mariana: "al menos 5 bullets específicos"). Es un OBJETIVO, no
# un mínimo forzado: si el periodo no da para tantas dimensiones con dato real, se emiten
# las que haya (nunca se rellena con ruido inventado).
HALLAZGOS_OBJETIVO = 5

# Factor sobre la mediana de |deltas diarios| a partir del cual la variación de un día de
# seguidores se considera REPRESENTATIVA (una señal, no ruido diario). Mariana: "con
# diario tienes bajas, muchas veces no son representativas... si hay una variación mucho
# más fuerte, ahí sí me hace mucho más sentido". k=3 marca solo los desplomes/picos que
# se salen claramente del ritmo habitual del propio periodo.
K_SEGUIDORES_REPRESENTATIVO = 3.0

# Nombres legibles de red (id de plataforma -> etiqueta), para redactar la dimensión de
# red sin exponer el id crudo. Espejo del `nombreRed` del frontend.
_NOMBRE_RED: dict[str, str] = {
    "facebook": "Facebook",
    "instagram": "Instagram",
    "x": "X",
    "tiktok": "TikTok",
    "youtube": "YouTube",
}

# Nombres de mes en es-MX (índice 1-12) para redactar la fecha de una señal de seguidores.
_MESES_ABREV_ES: tuple[str, ...] = (
    "ene", "feb", "mar", "abr", "may", "jun",
    "jul", "ago", "sep", "oct", "nov", "dic",
)


def _nombre_red(red: str) -> str:
    return _NOMBRE_RED.get(red, red)


def _fecha_es(iso: str) -> str:
    """`AAAA-MM-DD` -> "15-jun" (día y mes abreviado en es-MX); el ISO tal cual si falla."""
    try:
        d = date.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso
    return f"{d.day}-{_MESES_ABREV_ES[d.month - 1]}"


def _hallazgo(
    dimension: str,
    texto: str,
    direccion: str = "estable",
    pieza: dict | None = None,
) -> dict:
    """Un hallazgo del periodo: dimensión + frase + dirección + pieza opcional.

    `dimension` clasifica el eje ("vistas", "red", "formato", "seguidores",
    "engagement", "pieza", "periodo") para que la UI pinte el icono adecuado; `direccion`
    ("sube"|"baja"|"estable") fija la flecha; `pieza` enlaza cuando el hallazgo apunta a
    una pieza concreta.
    """
    h: dict = {"dimension": dimension, "texto": texto, "direccion": direccion}
    if pieza is not None:
        h["pieza"] = pieza
    return h


def _variacion_vis(resumen: dict) -> float | None:
    """Variación de visualizaciones vs. el periodo anterior, o None si no la hay.

    Sale de `variacion_vs_anterior` del resumen, que el reporte rellena con el histórico
    (variación REAL) o con el modelo de la fuente (muestra). None si la clave no está
    (sin periodo anterior comparable): no se inventa un 0.
    """
    var = resumen.get("variacion_vs_anterior") or {}
    v = var.get("visualizaciones_pct")
    return float(v) if v is not None else None


def _pieza_estrella_marca(fila: dict) -> dict | None:
    """La pieza de mejor engagement de una marca (la que "explica" su movimiento)."""
    piezas = fila.get("mejores_piezas") or []
    return piezas[0] if piezas else None


def _movimiento(fila: dict, nombres: dict[str, str]) -> dict | None:
    """Movimiento de vistas de UNA marca.

    `variacion_vis_pct` es None cuando no hay periodo anterior comparable (o el análisis
    está acotado a una red, que no tiene variación por red en el histórico): entonces el
    movimiento se narra por NIVEL de vistas, no por variación. None solo si la marca no
    tiene ni vistas ni variación (nada que contar).
    """
    resumen = fila.get("resumen") or {}
    var = _variacion_vis(resumen)
    vis = resumen.get("visualizaciones", 0)
    if var is None and not vis:
        return None
    cuenta_id = resumen.get("cuenta", "")
    if var is None:
        direccion = "estable"
    else:
        direccion = "sube" if var > 0 else "baja" if var < 0 else "estable"
    return {
        "marca_id": cuenta_id,
        "marca": etiqueta_marca(cuenta_id, nombres),
        "variacion_vis_pct": var,
        "direccion": direccion,
        "visualizaciones": vis,
        "engagement_pct": resumen.get("engagement_pct"),
        "pieza": _pieza_estrella_marca(fila),
    }


def _marca_lider(movimientos: list[dict]) -> dict | None:
    """La marca de mayor engagement con pieza estrella (para el siguiente paso)."""
    candidatos = [
        m for m in movimientos if m.get("engagement_pct") is not None and m.get("pieza")
    ]
    if not candidatos:
        return None
    return max(candidatos, key=lambda m: m["engagement_pct"])


def _pieza_hallazgo(pieza: dict | None) -> dict | None:
    """Forma mínima de una pieza para un hallazgo (título + red + engagement + url)."""
    if not pieza:
        return None
    return {
        "titulo": pieza.get("titulo", ""),
        "plataforma": pieza.get("plataforma", ""),
        "engagement_pct": pieza.get("engagement_pct", 0.0),
        "url": pieza.get("url"),
    }


# --------------------------------------------------------------------------- #
# Dimensiones (cada una emite 0..N hallazgos a partir de datos ya calculados). #
# --------------------------------------------------------------------------- #


def _hallazgos_vistas(movimientos: list[dict], umbral: float) -> list[dict]:
    """Vistas por marca vs. el periodo anterior: movimientos fuertes primero, luego el
    resto como estabilidad honesta (cifra + contexto), nunca 0-1 bullets vacíos.

    Las marcas SIN variación comparable (`variacion_vis_pct` None: sin periodo anterior o
    análisis acotado a una red) se narran por NIVEL de vistas, sin afirmar un cambio.
    """
    con_var = [m for m in movimientos if m["variacion_vis_pct"] is not None]
    sin_var = [m for m in movimientos if m["variacion_vis_pct"] is None]
    fuertes = [m for m in con_var if abs(m["variacion_vis_pct"]) >= umbral]
    estables = [m for m in con_var if abs(m["variacion_vis_pct"]) < umbral]
    out: list[dict] = []
    for m in fuertes[:MAX_MOVIMIENTOS]:
        vis = miles(m["visualizaciones"])
        verbo = "subió" if m["direccion"] == "sube" else "bajó"
        arranque = m["direccion"] != "estable" and m["variacion_vis_pct"] == 0
        if arranque:
            frase = f"{m['marca']} estrenó vistas (antes no tenía) y sumó {vis} en el periodo"
        else:
            frase = f"{m['marca']} {verbo} {signo(m['variacion_vis_pct'])}% en vistas ({vis} en el periodo)"
        if m.get("engagement_pct") is not None:
            frase += f", con {m['engagement_pct']}% de engagement"
        frase += "."
        out.append(_hallazgo("vistas", frase, m["direccion"], _pieza_hallazgo(m.get("pieza"))))
    if len(fuertes) > MAX_MOVIMIENTOS:
        resto = len(fuertes) - MAX_MOVIMIENTOS
        plural = "marca más" if resto == 1 else "marcas más"
        out.append(_hallazgo("vistas", f"Otras {resto} {plural} también se movieron en vistas."))
    # Estabilidad: cuando NO hubo movimientos fuertes, se informa igualmente (no se calla).
    if not fuertes and estables:
        if len(estables) == 1:
            m = estables[0]
            vis = miles(m["visualizaciones"])
            out.append(
                _hallazgo(
                    "vistas",
                    f"{m['marca']} se mantuvo estable en vistas ({signo(m['variacion_vis_pct'])}%, "
                    f"{vis} en el periodo): sin cambios relevantes frente al periodo anterior.",
                )
            )
        else:
            n = len(estables)
            out.append(
                _hallazgo(
                    "vistas",
                    f"Las {n} marcas se mantuvieron estables en vistas: sin cambios relevantes "
                    "frente al periodo anterior.",
                )
            )
    # Nivel de vistas para las marcas sin variación comparable (típico con foco de red): la
    # de mayor volumen lidera, para no dejar la dimensión de vistas vacía en ese caso.
    if not fuertes and not estables and sin_var:
        lider = max(sin_var, key=lambda m: m["visualizaciones"])
        if lider["visualizaciones"]:
            out.append(
                _hallazgo(
                    "vistas",
                    f"{lider['marca']} lideró en vistas con {miles(lider['visualizaciones'])} "
                    "en el periodo.",
                    pieza=_pieza_hallazgo(lider.get("pieza")),
                )
            )
    return out


def _hallazgo_red(rep: dict) -> dict | None:
    """La red que más EMPUJÓ el periodo (mayor cuota de visualizaciones entre todas las
    marcas). None si el reporte no desglosa por plataforma.
    """
    por_red: dict[str, int] = {}
    for fila in rep.get("cuentas", []):
        r = fila.get("resumen") or {}
        for p in r.get("por_plataforma") or []:
            red = p.get("plataforma", "")
            por_red[red] = por_red.get(red, 0) + (p.get("visualizaciones", 0) or 0)
    con_vistas = {r: v for r, v in por_red.items() if v > 0}
    total = sum(con_vistas.values())
    if total <= 0 or len(con_vistas) < 2:
        # Con una sola red con vistas (típico bajo foco de red) "qué red empujó" es trivial:
        # no aporta un hallazgo.
        return None
    red, vis = max(con_vistas.items(), key=lambda kv: kv[1])
    cuota = round(vis / total * 100)
    return _hallazgo(
        "red",
        f"{_nombre_red(red)} fue la red que más aportó: {cuota}% de las vistas del periodo "
        f"({miles(vis)}).",
    )


def _hallazgo_formato(piezas: list[dict]) -> dict | None:
    """El formato que despunta por engagement medio (con ≥2 piezas para que sea señal, no
    una pieza suelta). None si las piezas no traen formato o no hay suficientes.
    """
    por_formato: dict[str, list[float]] = {}
    for p in piezas:
        fmt = p.get("formato")
        eng = p.get("engagement_pct")
        if fmt and eng is not None:
            por_formato.setdefault(fmt, []).append(float(eng))
    candidatos = {f: engs for f, engs in por_formato.items() if len(engs) >= 2}
    if not candidatos:
        return None
    fmt, engs = max(candidatos.items(), key=lambda kv: statistics.mean(kv[1]))
    media = round(statistics.mean(engs), 1)
    return _hallazgo(
        "formato",
        f"El formato «{fmt}» fue el de mejor engagement ({media}% de media en {len(engs)} piezas).",
        "sube",
    )


def _hallazgo_seguidores(serie: dict | None) -> dict | None:
    """Seguidores del periodo: la VARIACIÓN REPRESENTATIVA si la hay (un día cuyo delta se
    sale del ritmo diario habitual), o el neto sereno si no.

    Distingue señal de ruido: compara |delta de cada día| contra la mediana de |deltas| del
    propio periodo; solo el que supera `K_SEGUIDORES_REPRESENTATIVO` × mediana es una señal
    ("El 15-jun Instagram perdió 12 400, muy por encima del ritmo diario habitual"). Sin
    señal, un bullet sereno del neto. None si la fuente no expone followers.
    """
    if not serie:
        return None
    puntos = serie.get("puntos") or []
    neto = serie.get("neto", 0)
    señal = _senal_seguidores(puntos)
    if señal is not None:
        fecha, red, delta = señal
        verbo = "ganó" if delta > 0 else "perdió"
        direccion = "sube" if delta > 0 else "baja"
        red_txt = f"{_nombre_red(red)} " if red else ""
        return _hallazgo(
            "seguidores",
            f"El {_fecha_es(fecha)} {red_txt}{verbo} {miles(abs(delta))} seguidores, muy por "
            "encima del ritmo diario habitual del periodo.",
            direccion,
        )
    # Sin señal fuerte: neto sereno del periodo.
    if neto == 0:
        return _hallazgo(
            "seguidores",
            "Los seguidores se mantuvieron sin cambios netos en el periodo.",
        )
    verbo = "ganó" if neto > 0 else "perdió"
    direccion = "sube" if neto > 0 else "baja"
    return _hallazgo(
        "seguidores",
        f"En el periodo se {verbo} un neto de {miles(abs(neto))} seguidores, dentro del ritmo habitual.",
        direccion,
    )


def _senal_seguidores(puntos: list[dict]) -> tuple[str, str, int] | None:
    """El día de variación de seguidores más REPRESENTATIVA `(fecha, red, delta)`, o None.

    Sobre la serie diaria del TOTAL, calcula el delta de cada día (punto N − N−1) y la
    mediana de sus valores absolutos (el "ritmo diario habitual"). Devuelve el día cuyo
    |delta| es máximo Y supera `K_SEGUIDORES_REPRESENTATIVO` × mediana; `red` es la red que
    más aportó a ese delta (o "" si no se puede desglosar). None si no hay señal por encima
    del ruido (o menos de 3 puntos, sin base para una mediana).
    """
    if len(puntos) < 3:
        return None
    totales = [p.get("total", 0) for p in puntos]
    deltas = [totales[i] - totales[i - 1] for i in range(1, len(totales))]
    abs_deltas = [abs(d) for d in deltas]
    mediana = statistics.median(abs_deltas)
    if mediana <= 0:
        return None
    idx_max = max(range(len(deltas)), key=lambda i: abs(deltas[i]))
    delta = deltas[idx_max]
    if abs(delta) < K_SEGUIDORES_REPRESENTATIVO * mediana:
        return None
    # `puntos[idx_max + 1]` es el día del delta (el segundo punto de la pareja).
    punto = puntos[idx_max + 1]
    previo = puntos[idx_max]
    red = _red_dominante_delta(previo.get("por_red") or {}, punto.get("por_red") or {})
    return punto.get("fecha", ""), red, delta


def _red_dominante_delta(por_red_previo: dict, por_red_actual: dict) -> str:
    """La red que más aportó al delta diario del total (mayor |cambio| entre los dos días).

    Devuelve "" si no hay desglose por red (no se puede atribuir la señal a una red).
    """
    redes = set(por_red_previo) | set(por_red_actual)
    if not redes:
        return ""
    def _delta_red(red: str) -> int:
        return por_red_actual.get(red, 0) - por_red_previo.get(red, 0)
    red = max(redes, key=lambda r: abs(_delta_red(r)))
    return red if _delta_red(red) != 0 else ""


def _hallazgo_engagement(total: dict, rep: dict) -> dict | None:
    """Engagement del periodo: nivel + dirección. Usa el engagement del total si es
    comparable (una sola red); si no (varias redes -> None), cae a la MEDIA de los
    engagement por marca comparables. None si ninguna marca lo tiene.
    """
    eng = total.get("engagement_pct")
    if eng is None:
        engs = [
            r["engagement_pct"]
            for fila in rep.get("cuentas", [])
            if (r := fila.get("resumen") or {}).get("engagement_pct") is not None
        ]
        if not engs:
            return None
        eng = round(statistics.mean(engs), 1)
        return _hallazgo(
            "engagement",
            f"El engagement medio de las marcas fue del {eng}% en el periodo.",
        )
    return _hallazgo("engagement", f"El engagement global del periodo fue del {eng}%.")


def _hallazgo_pieza_estrella(movimientos: list[dict]) -> dict | None:
    """La pieza de mayor engagement del periodo, como hallazgo propio (por si ningún
    movimiento de vistas la lleva). None si ninguna marca tiene pieza estrella.
    """
    candidatas = [m for m in movimientos if m.get("pieza")]
    if not candidatas:
        return None
    mejor = max(
        candidatas,
        key=lambda m: (m["pieza"] or {}).get("engagement_pct", 0.0),
    )
    pieza = mejor["pieza"]
    return _hallazgo(
        "pieza",
        f"La pieza que más destacó fue «{pieza.get('titulo', '')}» de {mejor['marca']} en "
        f"{_nombre_red(pieza.get('plataforma', ''))} ({pieza.get('engagement_pct', 0)}% de engagement).",
        "sube",
        _pieza_hallazgo(pieza),
    )


def _hallazgo_periodo(rango: str, serie_diaria: dict | None) -> dict | None:
    """La variación PROPIA del periodo, que difiere estructuralmente semana vs. mes:

    - semana: el día más fuerte y el más flojo en vistas.
    - mes: la tendencia intra-mes (primera mitad vs. segunda).

    None si no hay serie diaria (la fuente no la expone) o es demasiado corta.
    """
    if not serie_diaria:
        return None
    puntos = serie_diaria.get("puntos") or []
    if len(puntos) < 2:
        return None
    es_mes = rango.startswith("mes") or rango in ("mes", "30d")
    if es_mes:
        return _hallazgo_periodo_mes(puntos)
    return _hallazgo_periodo_semana(puntos)


def _hallazgo_periodo_semana(puntos: list[dict]) -> dict | None:
    """Semana: el día más fuerte y el más flojo en vistas."""
    con_vis = [p for p in puntos if p.get("visualizaciones") is not None]
    if len(con_vis) < 2:
        return None
    fuerte = max(con_vis, key=lambda p: p.get("visualizaciones", 0))
    flojo = min(con_vis, key=lambda p: p.get("visualizaciones", 0))
    if fuerte is flojo or fuerte.get("visualizaciones", 0) == flojo.get("visualizaciones", 0):
        return None
    return _hallazgo(
        "periodo",
        f"El día más fuerte de la semana fue el {_fecha_es(fuerte.get('fecha', ''))} "
        f"({miles(fuerte.get('visualizaciones', 0))} vistas) y el más flojo el "
        f"{_fecha_es(flojo.get('fecha', ''))} ({miles(flojo.get('visualizaciones', 0))}).",
    )


def _hallazgo_periodo_mes(puntos: list[dict]) -> dict | None:
    """Mes: tendencia intra-mes comparando la primera mitad con la segunda."""
    mitad = len(puntos) // 2
    if mitad == 0:
        return None
    primera = sum(p.get("visualizaciones", 0) for p in puntos[:mitad])
    segunda = sum(p.get("visualizaciones", 0) for p in puntos[mitad:])
    if primera <= 0:
        return None
    var = round((segunda - primera) / primera * 100)
    if abs(var) < 10:
        return _hallazgo(
            "periodo",
            "El mes se mantuvo parejo: la segunda mitad rindió parecido a la primera en vistas.",
        )
    direccion = "sube" if var > 0 else "baja"
    tendencia = "de menos a más" if var > 0 else "de más a menos"
    return _hallazgo(
        "periodo",
        f"El mes fue {tendencia}: la segunda mitad {'subió' if var > 0 else 'bajó'} "
        f"{abs(var)}% en vistas frente a la primera.",
        direccion,
    )


def _ensamblar_hallazgos(
    rep: dict,
    movimientos: list[dict],
    piezas: list[dict],
    serie_seguidores: dict | None,
    serie_diaria: dict | None,
    rango: str,
    umbral: float,
) -> list[dict]:
    """Ensambla los hallazgos de todas las dimensiones, jerarquizados.

    Orden de prioridad: vistas (movimientos fuertes) → red → seguidores (señal) → formato
    → periodo → engagement → pieza estrella. Cada dimensión aporta 0..N hallazgos según el
    dato disponible; nunca se rellena con ruido. Se apunta a `HALLAZGOS_OBJETIVO` pero no se
    fuerza: si el periodo no da para tantas dimensiones con dato real, se emiten las que haya.
    """
    total = rep.get("total") or {}
    hallazgos: list[dict] = []
    hallazgos.extend(_hallazgos_vistas(movimientos, umbral))
    for constructor in (
        lambda: _hallazgo_red(rep),
        lambda: _hallazgo_seguidores(serie_seguidores),
        lambda: _hallazgo_formato(piezas),
        lambda: _hallazgo_periodo(rango, serie_diaria),
        lambda: _hallazgo_engagement(total, rep),
    ):
        h = constructor()
        if h is not None:
            hallazgos.append(h)
    # La pieza estrella cierra: solo si ningún hallazgo de vistas ya la lleva (para no
    # repetir la misma pieza) o si aún faltan hallazgos para el objetivo.
    pieza_ya = any(h.get("pieza") for h in hallazgos)
    if not pieza_ya or len(hallazgos) < HALLAZGOS_OBJETIVO:
        estrella = _hallazgo_pieza_estrella(movimientos)
        if estrella is not None and not any(
            h.get("dimension") == "pieza" for h in hallazgos
        ):
            hallazgos.append(estrella)
    return hallazgos


def construir_analisis(
    fuente: FuenteMetricas,
    rango: str = "semana",
    marca: str | None = None,
    historico: Historico | None = None,
    umbral_movimiento_pct: float = UMBRAL_MOVIMIENTO_PCT,
    serie_seguidores: dict | None = None,
    serie_diaria: dict | None = None,
) -> dict:
    """Ensambla la lectura multi-dimensión del periodo + siguiente paso.

    Reúsa el reporte consolidado (totales, variación vs. periodo anterior, mejores piezas
    por marca), el detector de picos y —si se pasan— la serie de seguidores y la serie
    diaria del periodo (las inyecta la fachada `servicio`, que las sanea en un solo sitio;
    sin ellas, esas dimensiones simplemente no emiten hallazgo). NO recalcula métricas.

    Devuelve un dict JSON-serializable con `hallazgos` (jerarquizados) + `siguiente_paso`.
    Propaga `ValueError` (rango inválido) y `CuentaNoEncontrada` (marca fuera de alcance).
    """
    rep = construir_reporte(fuente, rango, top=3, historico=historico)
    nombres = rep.get("nombres") or {}

    movimientos = [
        m for fila in rep.get("cuentas", []) if (m := _movimiento(fila, nombres)) is not None
    ]
    # Ordena por magnitud de variación (lo más llamativo primero); las marcas sin variación
    # comparable (foco de red / sin periodo anterior) van al final, ordenadas por volumen.
    movimientos.sort(
        key=lambda m: (
            m["variacion_vis_pct"] is not None,
            abs(m["variacion_vis_pct"]) if m["variacion_vis_pct"] is not None else m["visualizaciones"],
        ),
        reverse=True,
    )

    # Piezas del periodo (todas, para la dimensión de formato y la pieza estrella): reúsa las
    # `mejores_piezas` que el reporte ya descargó por marca, sin llamadas nuevas.
    piezas: list[dict] = []
    for fila in rep.get("cuentas", []):
        piezas.extend(fila.get("mejores_piezas") or [])

    hallazgos = _ensamblar_hallazgos(
        rep, movimientos, piezas, serie_seguidores, serie_diaria, rango, umbral_movimiento_pct
    )

    lider = _marca_lider(movimientos)

    es_muestra = es_fuente_muestra(rep.get("fuente"))
    analisis: dict = {
        "rango": rango,
        "marca": marca or "",
        "generado": datetime.now(UTC).isoformat(timespec="seconds"),
        "fuente": rep.get("fuente"),
        "es_muestra": es_muestra,
        "total": rep.get("total") or {},
        "hallazgos": hallazgos,
        "cobertura": rep.get("cobertura") or {"completa": True, "cuentas_parciales": []},
        "nombres": nombres,
        "siguiente_paso": _siguiente_paso(lider),
    }
    if es_muestra:
        analisis["aviso"] = AVISO_MUESTRA_TXT
    return analisis


def _siguiente_paso(lider: dict | None) -> dict | None:
    """Sugerencia accionable que cierra el loop hacia la acción.

    Devuelve marca + texto de la sugerencia, o None si no hay una marca líder con pieza
    concreta a la que apuntar. El texto es nuestro lado de la frontera (sugerir); la
    decisión de qué pedir y publicar queda en el equipo.
    """
    if lider is None:
        return None
    pieza = lider.get("pieza") or {}
    plat = pieza.get("plataforma")
    titulo = pieza.get("titulo")
    detalle = f' Tu mejor pieza fue «{titulo}» en {_nombre_red(plat)}.' if titulo and plat else ""
    return {
        "marca_id": lider["marca_id"],
        "marca": lider["marca"],
        "engagement_pct": lider["engagement_pct"],
        "pieza": _pieza_hallazgo(lider.get("pieza")),
        "texto": (
            f"{lider['marca']} es lo que mejor rindió este periodo "
            f"({lider['engagement_pct']}% de engagement).{detalle} "
            "Pídele a Claude copy o un clip en esa línea y dobla la apuesta por lo "
            "que funciona. Qué publicar y qué ajustar, lo decides tú."
        ),
    }


def _icono_direccion(direccion: str) -> str:
    return "🔼" if direccion == "sube" else "🔽" if direccion == "baja" else "▪️"


def render_markdown(analisis: dict) -> str:
    """Redacta el análisis a Markdown: hallazgos + siguiente paso.

    El dictamen va arriba; el detalle después. Si son datos de muestra, antepone el banner.
    Si no hay hallazgos, lo dice con honestidad en vez de forzar una narrativa vacía.
    """
    rango = analisis.get("rango", "")
    out: list[str] = [f"## Análisis del periodo — {rango}"]

    if (aviso := aviso_muestra_md(analisis.get("fuente"))) is not None:
        out.append(aviso + "\n")

    cob = analisis.get("cobertura") or {}
    if cob.get("cuentas_parciales"):
        nombres = analisis.get("nombres") or {}
        parciales = ", ".join(etiqueta_marca(c, nombres) for c in cob["cuentas_parciales"])
        out.append(
            f"> ⚠️ Cobertura parcial en {parciales}: la lectura puede estar incompleta "
            "(los ceros de una plataforma sin datos NO son reales)."
        )

    hallazgos = analisis.get("hallazgos") or []
    if not hallazgos:
        out.append("- Sin datos suficientes para una lectura del periodo.")
    else:
        out.append("**Lo que pasó:**")
        for h in hallazgos:
            linea = f"- {_icono_direccion(h.get('direccion', 'estable'))} {h.get('texto', '')}"
            pieza = h.get("pieza")
            if pieza and pieza.get("titulo"):
                linea += (
                    f" Lo explica «{pieza['titulo']}» en {_nombre_red(pieza.get('plataforma', ''))} "
                    f"({pieza.get('engagement_pct', 0)}% eng)."
                )
            out.append(linea)

    paso = analisis.get("siguiente_paso")
    if paso is not None:
        out.append("")
        out.append(f"**Siguiente paso:** {paso['texto']}")

    return "\n".join(out)
