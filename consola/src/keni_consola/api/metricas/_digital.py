"""Reporte "Métricas Digitales": matriz mensual por plataforma + comparativa.

Reproduce el Excel mensual que el equipo entrega a su dirección: por cada red, una
serie de los últimos 13 meses de cada métrica y, a la derecha, la comparativa de los
dos últimos meses CON DATOS (delta absoluto + % de variación). Lo serializa al CSV que
abre nativo en Excel (delimitador ';', números en formato europeo `1.234.567` / `7,15%`).

Estas funciones son PURAS (sin I/O): el endpoint (`export.py`) trae los datos del cache
de métricas, los reduce a `{red: {mes_token: {metrica: valor|None}}}` y se los pasa. Así
el layout se prueba offline sin tocar Postgres ni la fuente externa.

Lo que el sistema NO tiene (monetización USD de Facebook/YouTube, impresiones y horas de
reproducción de YouTube) sale como celda VACÍA: el equipo la rellena de otra fuente, igual
que hoy. Las claves `clave=None` marcan esas filas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

# Orden y etiqueta de cabecera de cada plataforma, como en el Excel del cliente.
PLATAFORMAS: tuple[tuple[str, str], ...] = (
    ("tiktok", "TIKTOK"),
    ("instagram", "INSTAGRAM"),
    ("facebook", "FACEBOOK"),
    ("x", "X"),
    ("youtube", "YOUTUBE"),
)

# Nombres de mes en español (índice 1..12), en mayúsculas como la cabecera del Excel.
_MESES_ES: tuple[str, ...] = (
    "",
    "ENERO",
    "FEBRERO",
    "MARZO",
    "ABRIL",
    "MAYO",
    "JUNIO",
    "JULIO",
    "AGOSTO",
    "SEPTIEMBRE",
    "OCTUBRE",
    "NOVIEMBRE",
    "DICIEMBRE",
)

# Métricas que el sistema SÍ provee por (red, mes). Las filas con `clave=None` (monetización,
# impresiones/horas de YouTube) no existen en la fuente y se emiten vacías.
_CLAVES_METRICA: frozenset[str] = frozenset(
    {
        "seguidores",
        "visualizaciones",
        "alcance",
        "interacciones",
        "engagement_pct",
        "likes",
        "comentarios",
        "compartidos",
        "video_views",
    }
)


@dataclass(frozen=True)
class Renglon:
    """Una fila del bloque de una plataforma.

    `clave` es la métrica de origen (None = la fuente no la tiene → celda vacía). `pct`
    marca el engagement: se formatea como porcentaje y su delta es en puntos.
    """

    etiqueta: str
    clave: str | None
    pct: bool = False


# Filas por plataforma, en orden, con la etiqueta tal cual la usa el equipo. Las etiquetas
# de engagement se unifican a "Engagement Rate" (el Excel mezclaba mayúsculas). El "Alcance"
# de X mapea a visualizaciones (impresiones): X no expone alcance de usuarios únicos.
RENGLONES: dict[str, tuple[Renglon, ...]] = {
    "tiktok": (
        Renglon("Seguidores", "seguidores"),
        Renglon("Views/Alcance", "visualizaciones"),
        Renglon("Interacciones", "interacciones"),
        Renglon("Engagement Rate", "engagement_pct", pct=True),
        Renglon("Me Gusta", "likes"),
        Renglon("Compartidos", "compartidos"),
        Renglon("Comentarios", "comentarios"),
    ),
    "instagram": (
        Renglon("Seguidores", "seguidores"),
        Renglon("Visualizaciones", "visualizaciones"),
        Renglon("Interacciones", "interacciones"),
        Renglon("Engagement Rate", "engagement_pct", pct=True),
        Renglon("Views Reels", "video_views"),
    ),
    "facebook": (
        Renglon("Seguidores", "seguidores"),
        Renglon("Alcance", "alcance"),
        Renglon("Interacciones", "interacciones"),
        Renglon("Engagement Rate", "engagement_pct", pct=True),
        Renglon("Reproducciones", "video_views"),
        Renglon("Monetización USD", None),
    ),
    "x": (
        Renglon("Seguidores", "seguidores"),
        Renglon("Alcance", "visualizaciones"),
        Renglon("Interacciones", "interacciones"),
        Renglon("Engagement Rate", "engagement_pct", pct=True),
        Renglon("Retuits", "compartidos"),
        Renglon("Me Gusta", "likes"),
    ),
    "youtube": (
        Renglon("Vistas", "visualizaciones"),
        Renglon("Suscriptores", "seguidores"),
        Renglon("Impresiones", None),
        Renglon("Tiempo de reproducción (horas)", None),
        Renglon("Monetización USD", None),
    ),
}

# Columnas a la derecha de la serie: un separador en blanco + el bloque de comparativa.
VENTANA_MESES = 13


def meses_ventana(ref: date, n: int = VENTANA_MESES) -> list[tuple[str, str, int, int]]:
    """Los `n` meses naturales que terminan en el mes de `ref`, del más viejo al más nuevo.

    Devuelve `(token, etiqueta, anio, mes)` por mes; `token` es el `mes:AAAA-MM` que entiende
    la fachada de métricas y `etiqueta` el nombre del mes en mayúsculas para la cabecera.
    """
    salida: list[tuple[str, str, int, int]] = []
    anio, mes = ref.year, ref.month
    # Retrocedemos n-1 meses desde ref y avanzamos hacia delante para quedar en orden.
    total = anio * 12 + (mes - 1) - (n - 1)
    for i in range(n):
        idx = total + i
        a, m = divmod(idx, 12)
        m += 1
        salida.append((f"mes:{a:04d}-{m:02d}", _MESES_ES[m], a, m))
    return salida


def _fmt_entero(n: float) -> str:
    """Entero en formato europeo: `2305158` → `2.305.158` (negativos con signo)."""
    entero = int(round(n))
    s = f"{abs(entero):,}".replace(",", ".")
    return f"-{s}" if entero < 0 else s


def _fmt_pct(v: float, decimales: int = 2) -> str:
    """Porcentaje europeo: `7.15` → `7,15%`."""
    return f"{v:.{decimales}f}".replace(".", ",") + "%"


def _fmt_valor(valor: float | None, pct: bool) -> str:
    """Una celda de la serie: vacía si no hay dato, formateada según sea conteo o %."""
    if valor is None:
        return ""
    return _fmt_pct(valor) if pct else _fmt_entero(valor)


def _comparativa(a: float | None, b: float | None, pct: bool) -> tuple[str, str]:
    """`(Diferencia, %)` entre el mes A y el B de una métrica.

    Conteos: diferencia absoluta (`b-a`) y variación relativa `(b-a)/a`. Engagement (`pct`):
    diferencia en puntos (`b-a`, ya en %) y variación relativa de la propia tasa. Sin alguno
    de los dos valores, o con A=0 (relativa indefinida), la celda correspondiente va vacía.
    """
    if a is None or b is None:
        return "", ""
    delta = b - a
    diferencia = _fmt_pct(delta) if pct else _fmt_entero(delta)
    porcentaje = _fmt_pct((delta / a) * 100, 1) if a else ""
    return diferencia, porcentaje


def _meses_con_datos(datos_red: dict, tokens: list[str]) -> list[str]:
    """Tokens (en orden) cuyo mes tiene datos para la red (entrada no nula)."""
    return [t for t in tokens if datos_red.get(t) is not None]


def construir_lineas_digital(
    datos: dict[str, dict[str, dict[str, float | None] | None]],
    meses: list[tuple[str, str, int, int]],
) -> list[list[str]]:
    """Arma las filas (listas de celdas) del reporte completo, una plataforma tras otra.

    `datos[red][token]` es el dict de métricas de ese mes (o None si la red no tuvo datos
    ese mes). `meses` es la ventana de `meses_ventana`. Entre bloques de plataforma va una
    fila en blanco, como en el Excel original.
    """
    tokens = [t for t, _, _, _ in meses]
    etiquetas_mes = [e for _, e, _, _ in meses]
    filas: list[list[str]] = []

    for indice, (red, etiqueta_red) in enumerate(PLATAFORMAS):
        if indice:
            filas.append([])  # fila en blanco entre plataformas
        datos_red = datos.get(red) or {}
        con_datos = _meses_con_datos(datos_red, tokens)
        tok_a, tok_b = (con_datos[-2], con_datos[-1]) if len(con_datos) >= 2 else (None, None)
        etq_a = etiquetas_mes[tokens.index(tok_a)] if tok_a else ""
        etq_b = etiquetas_mes[tokens.index(tok_b)] if tok_b else ""

        # Cabecera de la plataforma: nombre + 13 meses + separador + bloque de comparativa.
        filas.append(
            [etiqueta_red, *etiquetas_mes, "", "", etq_a, etq_b, "Diferencia", "%"]
        )

        for ren in RENGLONES[red]:
            serie = [
                _fmt_valor((datos_red.get(t) or {}).get(ren.clave) if ren.clave else None, ren.pct)
                for t in tokens
            ]
            val_a = (datos_red.get(tok_a) or {}).get(ren.clave) if (ren.clave and tok_a) else None
            val_b = (datos_red.get(tok_b) or {}).get(ren.clave) if (ren.clave and tok_b) else None
            diferencia, porcentaje = _comparativa(val_a, val_b, ren.pct)
            filas.append(
                [
                    ren.etiqueta,
                    *serie,
                    "",
                    ren.etiqueta,
                    _fmt_valor(val_a, ren.pct),
                    _fmt_valor(val_b, ren.pct),
                    diferencia,
                    porcentaje,
                ]
            )
    return filas


def render_csv_digital(
    datos: dict[str, dict[str, dict[str, float | None] | None]],
    meses: list[tuple[str, str, int, int]],
) -> str:
    """Serializa el reporte a CSV `;` (sin comillas: ninguna celda contiene el separador)."""
    filas = construir_lineas_digital(datos, meses)
    return "\n".join(";".join(celda) for celda in filas) + "\n"


# --------------------------------------------------------------------------- #
# Adaptadores: del dict crudo del cache de métricas a `{red: {mes: métricas}}` #
# --------------------------------------------------------------------------- #
#
# El reporte (`construir_reporte`) da por red visualizaciones/alcance/interacciones/
# engagement; el desglose, los granulares (likes/comentarios/compartidos/video_views);
# la serie de seguidores, el stock absoluto a fin de mes. Son funciones PURAS sobre los
# dicts ya descargados, así la fusión se prueba sin Postgres ni la fuente externa.


def por_red_reporte(rep: dict) -> dict[str, dict[str, float | None]]:
    """`{red: {visualizaciones, alcance, interacciones, engagement_pct}}` del reporte de un mes.

    El reporte trae UNA marca (la pedida), así que hay una entrada de `por_plataforma` por
    red: se toma su valor tal cual lo calculó el sistema (sin recomputar el engagement).
    """
    out: dict[str, dict[str, float | None]] = {}
    for fila in rep.get("cuentas", []) or []:
        resumen = fila.get("resumen") or {}
        for p in resumen.get("por_plataforma", []) or []:
            red = p.get("plataforma")
            if red:
                out[red] = {
                    "visualizaciones": p.get("visualizaciones"),
                    "alcance": p.get("alcance"),
                    "interacciones": p.get("interacciones"),
                    "engagement_pct": p.get("engagement_pct"),
                }
    return out


def por_red_desglose(des: dict) -> dict[str, dict[str, int]]:
    """`{red: {likes, comentarios, compartidos, video_views}}` del desglose de un mes."""
    out: dict[str, dict[str, int]] = {}
    for celda in des.get("celdas", []) or []:
        red = celda.get("red")
        if not red:
            continue
        acc = out.setdefault(
            red, {"likes": 0, "comentarios": 0, "compartidos": 0, "video_views": 0}
        )
        for clave in acc:
            acc[clave] += int(celda.get(clave, 0) or 0)
    return out


def seguidores_por_mes(seg: dict) -> dict[str, dict[str, int]]:
    """`{'AAAA-MM': {red: seguidores}}` tomando el ÚLTIMO punto de cada mes (stock a fin de mes).

    La serie es un stock diario: el valor a fin de mes es el del último día con dato de ese
    mes. Un mes sin puntos no aparece (queda vacío en el reporte).
    """
    ultimo: dict[str, tuple[str, dict[str, int]]] = {}
    for punto in seg.get("puntos", []) or []:
        fecha = str(punto.get("fecha", ""))[:10]
        if len(fecha) < 7:
            continue
        ym = fecha[:7]
        previo = ultimo.get(ym)
        if previo is None or fecha >= previo[0]:
            ultimo[ym] = (fecha, dict(punto.get("por_red") or {}))
    return {ym: por_red for ym, (_, por_red) in ultimo.items()}


def ensamblar_datos(
    tokens: list[str],
    reportes: list[dict],
    desgloses: list[dict],
    seg: dict,
) -> dict[str, dict[str, dict[str, float | None] | None]]:
    """Funde las tres fuentes en `{red: {mes_token: métricas|None}}` para el serializador.

    `reportes[i]`/`desgloses[i]` son los del mes `tokens[i]` (`mes:AAAA-MM`). Una red sin
    NINGUNA señal ese mes (ni reporte, ni desglose, ni seguidores) queda `None` → mes vacío.
    """
    seg_mes = seguidores_por_mes(seg)
    datos: dict[str, dict[str, dict[str, float | None] | None]] = {
        red: {} for red, _ in PLATAFORMAS
    }
    for i, token in enumerate(tokens):
        ym = token[4:]  # 'mes:AAAA-MM' → 'AAAA-MM'
        rep_red = por_red_reporte(reportes[i])
        des_red = por_red_desglose(desgloses[i])
        seg_red = seg_mes.get(ym, {})
        for red, _ in PLATAFORMAS:
            rr = rep_red.get(red)
            dr = des_red.get(red)
            sg = seg_red.get(red)
            if rr is None and dr is None and sg is None:
                datos[red][token] = None
                continue
            datos[red][token] = {
                "seguidores": sg,
                "visualizaciones": rr.get("visualizaciones") if rr else None,
                "alcance": rr.get("alcance") if rr else None,
                "interacciones": rr.get("interacciones") if rr else None,
                "engagement_pct": rr.get("engagement_pct") if rr else None,
                "likes": dr.get("likes") if dr else None,
                "comentarios": dr.get("comentarios") if dr else None,
                "compartidos": dr.get("compartidos") if dr else None,
                "video_views": dr.get("video_views") if dr else None,
            }
    return datos
