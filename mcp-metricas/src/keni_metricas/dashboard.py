"""Dashboard de metricas como HTML estatico autocontenido.

Cierra la brecha "sin GUI" frente a Metricool sin meter una SPA ni dependencias:
construye el reporte consolidado (`reporte.construir_reporte`) + las alertas
(`picos.detectar_picos`) y los renderiza en UN solo archivo HTML con CSS inline,
SIN JS, SIN CDN, SIN red. Se abre con doble clic y funciona offline con la
fuente `muestra`.

Uso:
    python -m keni_metricas.dashboard --salida dashboard.html [--rango mes] [--top 3]

Estilo Keni: blanco/negro/gris, tipografia del sistema, minimal y legible.
Todo texto de contenido (titulos de piezas, nombres) se escapa para evitar
inyeccion de HTML.
"""

from __future__ import annotations

import argparse
import sys
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING

from . import formato
from .formato import etiqueta_marca, miles, partes_cobertura, signo
from .fuentes.base import FuenteMetricas
from .picos import detectar_picos
from .reporte import construir_reporte

if TYPE_CHECKING:
    from .historico import Historico

# Iconos textuales por plataforma (sin imagenes externas: solo glifos unicode).
_PLATAFORMA_ETIQUETA = {
    "facebook": "Facebook",
    "instagram": "Instagram",
    "x": "X",
    "tiktok": "TikTok",
    "youtube": "YouTube",
}

# Engagement es la metrica north-star del producto. Umbrales (en % de engagement)
# para clasificar cada marca por color. Calibrados contra la realidad del cliente
# (Claro Sports ~2-3% combinado segun estrategia de AMX; noticias muy por debajo;
# gaming/podcast por encima) y los rangos tipicos de engagement en redes sociales:
#   - alto  (good): >= 3.5%  -> audiencia que interactua de forma destacada
#   - medio (ok):   1.5% - 3.5%  -> dentro de lo normal/saludable
#   - bajo  (low):  < 1.5%   -> poca interaccion relativa al alcance
_ENG_UMBRAL_ALTO = 3.5
_ENG_UMBRAL_BAJO = 1.5

# Nº de snapshots historicos a mostrar en la mini-tendencia de engagement por marca.
_ENG_TREND_N = 6


def _clase_engagement(pct: float) -> str:
    """Clase CSS segun el nivel de engagement (north-star)."""
    if pct >= _ENG_UMBRAL_ALTO:
        return "eng-alto"
    if pct < _ENG_UMBRAL_BAJO:
        return "eng-bajo"
    return "eng-medio"


def _etiqueta_engagement(pct: float) -> str:
    """Etiqueta legible del nivel de engagement."""
    if pct >= _ENG_UMBRAL_ALTO:
        return "alto"
    if pct < _ENG_UMBRAL_BAJO:
        return "bajo"
    return "ok"


# Meses abreviados en espanol (es-MX), sin depender del locale del SO (UX-6).
_MESES_ES = (
    "",
    "ene", "feb", "mar", "abr", "may", "jun",
    "jul", "ago", "sep", "oct", "nov", "dic",
)


def _fecha_legible(generado: str) -> str:
    """Convierte la marca ISO (`2026-05-24T17:05:32+00:00`) a "24 may 2026".

    Best-effort: si no parsea, devuelve el texto original tal cual (escapado por
    el llamante). Solo necesitamos los primeros 10 caracteres (AAAA-MM-DD).
    """
    if not generado or len(generado) < 10:
        return generado
    try:
        anio, mes, dia = generado[:10].split("-")
        m = int(mes)
        if not 1 <= m <= 12:
            return generado
        return f"{int(dia)} {_MESES_ES[m]} {anio}"
    except (ValueError, IndexError):
        return generado


def _clase_variacion(pct: float | None) -> str:
    if pct is None:
        return "var-neutra"
    if pct > 0:
        return "var-sube"
    if pct < 0:
        return "var-baja"
    return "var-neutra"


def _nota_cobertura_marca(cob: dict | None) -> str | None:
    """Texto de cobertura parcial para una marca; None si respondio todo."""
    partes = partes_cobertura(cob, _PLATAFORMA_ETIQUETA)
    if partes is None:
        return None
    return "Cobertura parcial: sin datos de " + ", ".join(partes) + ". Los ceros NO son datos reales."


_CSS = """
:root {
  --tinta: #111;
  --gris: #666;
  --gris-claro: #e6e6e6;
  --fondo: #fff;
  --fondo-suave: #fafafa;
  --sube: #1a7f37;
  --baja: #b42318;
  --aviso-fondo: #fff8e1;
  --aviso-borde: #e0b500;
  --aviso-tinta: #7a5b00;
  /* Marca Keni: acento corporativo para branding (UX-2). */
  --marca: #ff5a1f;
  --marca-2: #1f6dff;
  --base-font: 16px;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--fondo);
  color: var(--tinta);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  line-height: 1.5;
  font-size: var(--base-font);
}
/* UX-8: modo presentacion (--presentacion) sube la escala tipografica para sala proyectada. */
body.presentacion { --base-font: 20px; }
body.presentacion .envoltura { max-width: 1120px; }
body.presentacion header.cabecera h1 { font-size: 1.9rem; }
body.presentacion .ns-hero .ns-valor { font-size: 3.2rem; }
.envoltura { max-width: 980px; margin: 0 auto; padding: 32px 20px 64px; }
header.cabecera {
  border-top: 4px solid var(--marca);
  border-bottom: 2px solid var(--tinta);
  padding: 14px 0 16px; margin-bottom: 24px;
}
header.cabecera .eyebrow {
  display: inline-block; margin: 0 0 6px;
  font-size: 0.72rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.12em; color: var(--marca);
}
header.cabecera .eyebrow .sep { color: var(--gris-claro); margin: 0 4px; font-weight: 400; }
header.cabecera h1 { font-size: 1.6rem; margin: 0 0 4px; letter-spacing: -0.01em; }
.meta { color: var(--gris); font-size: 0.85rem; }
.totales { display: flex; flex-wrap: wrap; gap: 12px; margin: 20px 0; }
.totales .kpi {
  flex: 1 1 150px; border: 1px solid var(--gris-claro); border-radius: 8px;
  padding: 14px 16px; background: var(--fondo-suave);
}
.kpi .etiqueta { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--gris); }
.kpi .valor { font-size: 1.5rem; font-weight: 600; margin-top: 2px; }
h2.seccion { font-size: 1.15rem; margin: 36px 0 14px; padding-bottom: 6px; border-bottom: 1px solid var(--gris-claro); }
.tarjetas { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.tarjeta { border: 1px solid var(--gris-claro); border-radius: 10px; padding: 16px 18px; }
.tarjeta h3 {
  margin: 0 0 8px; font-size: 1.05rem; display: flex;
  justify-content: space-between; align-items: baseline; gap: 8px;
}
.tarjeta .nombre { font-weight: 600; }
.tarjeta .cifras { display: flex; gap: 16px; flex-wrap: wrap; margin: 8px 0; }
.tarjeta .cifras div { font-size: 0.85rem; }
.tarjeta .cifras .n { font-size: 1.05rem; font-weight: 600; display: block; }
.tarjeta .cifras .l { color: var(--gris); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.03em; }
.var { font-size: 0.8rem; font-weight: 600; white-space: nowrap; }
.var-sube { color: var(--sube); }
.var-baja { color: var(--baja); }
.var-neutra { color: var(--gris); }
.piezas { margin: 10px 0 0; padding: 0; list-style: none; }
.piezas li { font-size: 0.82rem; padding: 4px 0; border-top: 1px solid var(--gris-claro); }
.piezas .plat { color: var(--gris); font-size: 0.72rem; text-transform: uppercase; }
.piezas .eng { font-weight: 600; }
.piezas .ttl-pieza {
  color: var(--gris); margin-left: 60px; font-weight: 600;
  text-transform: uppercase; font-size: 0.72rem; letter-spacing: 0.03em;
}
.aviso {
  background: var(--aviso-fondo); border: 1px solid var(--aviso-borde); color: var(--aviso-tinta);
  border-radius: 8px; padding: 10px 14px; font-size: 0.82rem; margin: 8px 0 0;
}
.aviso strong { color: var(--aviso-tinta); }
.alertas { margin: 0; padding: 0; list-style: none; }
.alertas li {
  border: 1px solid var(--gris-claro); border-radius: 8px;
  padding: 10px 14px; margin-bottom: 8px; font-size: 0.9rem;
}
.alertas .tag {
  font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.04em;
  color: var(--gris); display: block;
}
/* UX-1: el resto de alertas vive plegado para no enterrar el cierre. */
.alertas-resto { margin: 8px 0 0; }
.alertas-resto > summary {
  cursor: pointer; color: var(--gris); font-size: 0.85rem; font-weight: 600;
  padding: 6px 0;
}
.alertas-resto[open] > summary { margin-bottom: 4px; }
.alertas-resto .alertas { margin-top: 8px; }
.vacio { color: var(--gris); font-style: italic; }

/* --- Callout pieza estrella global (UX-7) --- */
.estrella {
  display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap;
  border: 1px solid var(--gris-claro); border-left: 4px solid var(--marca);
  border-radius: 8px; background: var(--fondo-suave);
  padding: 12px 16px; margin: 20px 0 0; font-size: 0.95rem;
}
.estrella .e-titulo {
  font-weight: 700; text-transform: uppercase; letter-spacing: 0.03em;
  font-size: 0.78rem; color: var(--marca);
}
/* UX-10: aclara el criterio del callout sin gritar (no es el "más importante"). */
.estrella .e-criterio {
  font-weight: 600; text-transform: none; letter-spacing: 0;
  color: var(--gris);
}
.estrella .e-marca { font-weight: 700; }
.estrella .e-plat { color: var(--gris); }
.estrella .e-pct { font-weight: 700; font-variant-numeric: tabular-nums; }
.estrella .e-pieza { color: var(--gris); font-size: 0.85rem; flex-basis: 100%; }

/* --- Engagement: metrica north-star --- */
.ns-hero {
  display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap;
  border: 2px solid var(--tinta); border-radius: 12px;
  padding: 18px 22px; margin: 0 0 18px; background: var(--fondo-suave);
}
.ns-hero .ns-valor { font-size: 2.6rem; font-weight: 700; line-height: 1; letter-spacing: -0.02em; }
.ns-hero .ns-etiqueta { font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--gris); }
/* UX-5: leyenda del north-star como chips de color, no como frase larga. */
.ns-leyenda { display: flex; gap: 8px; flex-wrap: wrap; flex-basis: 100%; margin-top: 4px; }
.ns-leyenda .chip {
  font-size: 0.72rem; font-weight: 700; padding: 3px 10px; border-radius: 999px;
  white-space: nowrap;
}
.ranking { margin: 0; padding: 0; list-style: none; }
.ranking li {
  display: grid; grid-template-columns: 1.6rem 1fr auto auto; align-items: center;
  gap: 10px; padding: 10px 12px; border: 1px solid var(--gris-claro);
  border-radius: 8px; margin-bottom: 8px;
}
.ranking .pos { color: var(--gris); font-size: 0.9rem; font-weight: 600; text-align: right; }
.ranking .marca { font-weight: 600; }
.ranking .marca .marca-spark { margin-left: 8px; color: var(--gris); }
.ranking .pct { font-size: 1.2rem; font-weight: 700; font-variant-numeric: tabular-nums; }
/* UX-10: barras mas altas y con el % visible dentro/al lado. */
.ranking .barra {
  grid-column: 1 / -1; height: 18px; border-radius: 4px;
  background: var(--gris-claro); overflow: hidden; margin-top: 4px;
  position: relative;
}
.ranking .barra span.relleno { display: block; height: 100%; border-radius: 4px; min-width: 2px; }
.ranking .barra .barra-pct {
  position: absolute; top: 0; left: 8px; height: 100%;
  display: flex; align-items: center;
  font-size: 0.72rem; font-weight: 700; color: var(--tinta);
  font-variant-numeric: tabular-nums;
}
.nivel {
  font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.04em;
  font-weight: 700; padding: 2px 8px; border-radius: 999px; white-space: nowrap;
}
.eng-alto { color: var(--sube); }
.eng-medio { color: var(--aviso-tinta); }
.eng-bajo { color: var(--baja); }
.nivel.eng-alto { background: #e7f6ec; }
.nivel.eng-medio { background: var(--aviso-fondo); }
.nivel.eng-bajo { background: #fbeaea; }
.barra .eng-alto { background: var(--sube); }
.barra .eng-medio { background: var(--aviso-borde); }
.barra .eng-bajo { background: var(--baja); }
.tendencia { margin: 10px 0 0; }
.tendencia summary {
  cursor: pointer; color: var(--gris); font-size: 0.78rem;
  text-transform: uppercase; letter-spacing: 0.03em;
}
.tendencia table { border-collapse: collapse; margin: 8px 0 0; font-size: 0.8rem; width: 100%; }
.tendencia th, .tendencia td {
  text-align: right; padding: 3px 8px; border-bottom: 1px solid var(--gris-claro);
  font-variant-numeric: tabular-nums;
}
.tendencia th:first-child, .tendencia td:first-child { text-align: left; color: var(--gris); }
.spark { font-variant-numeric: tabular-nums; letter-spacing: 1px; }
.spark .pip { display: inline-block; }
footer {
  margin-top: 48px; color: var(--gris); font-size: 0.75rem;
  border-top: 1px solid var(--gris-claro); padding-top: 12px;
}
/* UX-12: pie con leyenda de niveles/iconos como referencia rapida (tier-2). */
footer .leyenda {
  display: flex; gap: 8px; flex-wrap: wrap; align-items: center;
  margin: 0 0 8px;
}
footer .leyenda .et { font-weight: 600; color: var(--tinta); }
footer .leyenda .chip {
  font-size: 0.7rem; font-weight: 700; padding: 2px 9px; border-radius: 999px;
  white-space: nowrap;
}

/* ===========================================================================
   UX-9: impresion / "Guardar como PDF" del navegador.
   El dashboard ya es autocontenido (sin red/JS); aqui solo lo preparamos para
   que la copia en papel/PDF salga limpia: <details> abiertos para no esconder
   info, fondos clave forzados, sin cortes feos a media tarjeta, una pagina
   coherente. NO introduce recursos externos.
   =========================================================================== */
@media print {
  /* Forzamos la impresion de fondos/colores: si no, Chrome los descarta y los
     chips de nivel y el hero quedan en blanco e ilegibles. */
  * {
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }
  @page { margin: 14mm; }
  body {
    /* color de fondo blanco puro y escala estable para una pagina coherente. */
    background: #fff;
    font-size: 12px;
  }
  /* el modo presentacion no aporta en papel: volvemos a la escala normal. */
  body.presentacion { --base-font: 16px; }
  .envoltura { max-width: none; padding: 0; margin: 0; }
  body.presentacion .envoltura { max-width: none; }

  /* <details> SIEMPRE abiertos al imprimir (alertas plegadas, tablas de
     tendencia): el PDF no debe esconder informacion tras un triangulo. */
  details { display: block; }
  details > * { display: revert; }
  details[open] > *, details > * { display: revert; }
  /* el triangulo/summary interactivo no aporta en papel: lo neutralizamos
     visualmente como un subtitulo, sin cursor de "clic". */
  summary { cursor: default; list-style: none; }
  summary::-webkit-details-marker { display: none; }

  /* evitar cortes feos a media tarjeta/seccion/alerta entre paginas. */
  .kpi, .tarjeta, .estrella, .ns-hero, .alertas li, .ranking li,
  .tendencia table, footer {
    break-inside: avoid;
    page-break-inside: avoid;
  }
  h2.seccion { break-after: avoid; page-break-after: avoid; }

  /* bordes mas marcados: en papel el gris muy claro casi no se ve. */
  .kpi, .tarjeta, .alertas li, .ranking li { border-color: #999; }
  header.cabecera { border-bottom-color: #000; }

  /* el ranking en una sola columna imprime mejor que el grid de tarjetas. */
  .tarjetas { display: block; }
  .tarjetas .tarjeta { margin-bottom: 12px; }
}
"""


def _render_kpis(total: dict) -> str:
    kpis = [
        ("Visualizaciones", miles(total["visualizaciones"])),
        ("Alcance", miles(total["alcance"])),
        ("Interacciones", miles(total["interacciones"])),
        ("Engagement", f"{total['engagement_pct']}%"),
        ("Cuentas", miles(total["cuentas"])),
    ]
    items = "".join(
        f'<div class="kpi"><div class="etiqueta">{escape(et)}</div>'
        f'<div class="valor">{escape(val)}</div></div>'
        for et, val in kpis
    )
    return f'<div class="totales">{items}</div>'


def _render_tarjeta(fila: dict, nombres: dict[str, str]) -> str:
    r = fila["resumen"]
    cuenta_id = r["cuenta"]
    nombre = etiqueta_marca(cuenta_id, nombres)
    var = r.get("variacion_vs_anterior") or {}
    v_vis = var.get("visualizaciones_pct")

    if v_vis is not None:
        var_html = (
            f'<span class="var {_clase_variacion(v_vis)}">{escape(signo(v_vis))}% vis</span>'
        )
    else:
        var_html = ""

    cifras = (
        '<div class="cifras">'
        f'<div><span class="n">{miles(r["visualizaciones"])}</span><span class="l">Visualizaciones</span></div>'
        f'<div><span class="n">{miles(r["alcance"])}</span><span class="l">Alcance</span></div>'
        f'<div><span class="n">{escape(str(r["engagement_pct"]))}%</span><span class="l">Engagement</span></div>'
        "</div>"
    )

    partes = [
        '<div class="tarjeta">',
        f'<h3><span class="nombre">{escape(nombre)}</span>{var_html}</h3>',
        cifras,
    ]

    nota = _nota_cobertura_marca(r.get("cobertura"))
    if nota is not None:
        partes.append(f'<p class="aviso"><strong>Aviso.</strong> {escape(nota)}</p>')

    piezas = fila.get("mejores_piezas") or []
    if piezas:
        lis = []
        for p in piezas:
            plat = _PLATAFORMA_ETIQUETA.get(p["plataforma"], p["plataforma"])
            titulo = escape(p["titulo"])
            eng = escape(str(p["engagement_pct"]))
            vis = miles(p["visualizaciones"])
            lis.append(
                f'<li><span class="plat">{escape(plat)}</span> · '
                f'<span class="eng">{eng}%</span> · {vis} vis<br>'
                f'<span class="ttl-pieza">{titulo}</span></li>'
            )
        partes.append(f'<ul class="piezas">{"".join(lis)}</ul>')

    partes.append("</div>")
    return "".join(partes)


def _render_alerta(a: dict, nombres: dict[str, str]) -> str:
    # nombre legible de la marca (mismo criterio que el resto del dashboard);
    # cae al id crudo solo si la fuente no lo trae.
    marca = escape(etiqueta_marca(a["cuenta"], nombres))
    tipo = a.get("tipo")
    if tipo == "pieza_despunta":
        plat = _PLATAFORMA_ETIQUETA.get(a["plataforma"], a["plataforma"])
        return (
            '<li><span class="tag">Pieza que despunta</span>'
            f"<strong>{marca}</strong> · {escape(plat)} · "
            f'&laquo;{escape(a["titulo"])}&raquo; alcanza {escape(str(a["engagement_pct"]))}% de engagement '
            f'({escape(str(a["factor"]))}&times; la media de {escape(str(a["baseline_engagement_pct"]))}%).</li>'
        )
    verbo = "sube" if tipo == "cuenta_alza" else "cae"
    return (
        f'<li><span class="tag">Cuenta que {escape(verbo)}</span>'
        f'<strong>{marca}</strong> {escape(verbo)} {escape(str(a["desviacion_pct"]))}% '
        f'vs. su baseline ({miles(a["baseline"])} &rarr; {miles(a["visualizaciones"])} vis).</li>'
    )


def _render_picos(picos: dict, nombres: dict[str, str]) -> str:
    partes = ['<h2 class="seccion">Alertas (picos)</h2>']
    cob = picos.get("cobertura") or {}
    if cob.get("cuentas_parciales"):
        parciales = ", ".join(
            escape(etiqueta_marca(c, nombres)) for c in cob["cuentas_parciales"]
        )
        partes.append(
            f'<p class="aviso"><strong>Aviso.</strong> Cobertura parcial en {parciales}: '
            "las alertas pueden estar incompletas.</p>"
        )
    alertas = picos.get("alertas") or []
    if not alertas:
        partes.append('<p class="vacio">Sin anomalias por encima del umbral. Todo dentro de lo normal.</p>')
        return "".join(partes)

    # UX-1: muestra solo las primeras alertas y pliega el resto para no
    # enterrar el cierre de la pantalla en una demo compartida. Mismo criterio
    # top-N (`formato.PICOS_VISIBLES`/`particionar_picos`) que el reporte/digest.
    visibles, n_resto = formato.particionar_picos(alertas)
    resto = alertas[len(visibles):]
    lis = "".join(_render_alerta(a, nombres) for a in visibles)
    partes.append(f'<ul class="alertas">{lis}</ul>')
    if n_resto:
        lis_resto = "".join(_render_alerta(a, nombres) for a in resto)
        partes.append(
            '<details class="alertas-resto">'
            f"<summary>Ver todas las alertas ({len(alertas)})</summary>"
            f'<ul class="alertas">{lis_resto}</ul>'
            "</details>"
        )
    return "".join(partes)


def _render_cobertura_global(rep: dict, nombres: dict[str, str]) -> str:
    """Aviso de cobertura a nivel reporte. Siempre rinde algo (la nota es obligatoria)."""
    cob = rep.get("cobertura") or {}
    if cob.get("cuentas_parciales"):
        # C3: nombre legible de la marca (no el id crudo), igual que el resto del
        # dashboard; el escape protege HTML porque alimenta el documento.
        parciales = ", ".join(
            escape(etiqueta_marca(c, nombres)) for c in cob["cuentas_parciales"]
        )
        return (
            f'<p class="aviso"><strong>Cobertura parcial.</strong> Datos incompletos en {parciales} '
            "(ver detalle por marca). Los ceros de una plataforma omitida NO son datos reales.</p>"
        )
    return (
        '<p class="aviso"><strong>Cobertura completa.</strong> '
        "Todas las plataformas configuradas respondieron en este periodo.</p>"
    )


# Caracteres de bloque para la mini-sparkline (de menor a mayor, sin imagenes/JS).
_SPARK = "▁▂▃▄▅▆▇█"


def _sparkline(valores: list[float]) -> str:
    """Sparkline de bloques unicode a partir de una serie de valores."""
    if not valores:
        return ""
    lo, hi = min(valores), max(valores)
    span = hi - lo
    pips = []
    for v in valores:
        if span == 0:
            idx = len(_SPARK) // 2  # todos iguales: bloque medio
        else:
            idx = round((v - lo) / span * (len(_SPARK) - 1))
        pips.append(f'<span class="pip">{_SPARK[idx]}</span>')
    return f'<span class="spark">{"".join(pips)}</span>'


def _tendencia_engagement(
    cuenta_id: str, rango: str, historico: Historico | None
) -> tuple[str, str]:
    """Mini-tendencia de engagement por marca desde el historico (UX-3).

    Devuelve la tupla `(spark_inline, tabla_detalle)`:
      - `spark_inline`: sparkline + delta, SIEMPRE visible en la linea del ranking.
      - `tabla_detalle`: la tabla periodo-por-periodo, plegada en un <details>.
    Ambos son "" si no hay historico o no hay >= 2 snapshots (sin tendencia que
    mostrar): se omite con elegancia, nunca lanza.
    """
    if historico is None:
        return "", ""
    try:
        serie = historico.serie(cuenta_id, rango, _ENG_TREND_N)
    except Exception:  # noqa: BLE001 — el historico es best-effort, nunca debe romper el dashboard
        return "", ""
    if not serie or len(serie) < 2:
        return "", ""

    engs = [float(p.get("engagement_pct") or 0.0) for p in serie]
    spark = _sparkline(engs)
    delta = round(engs[-1] - engs[0], 1)
    delta_html = (
        f'<span class="var {_clase_variacion(delta)}">{escape(signo(delta))} pts</span>'
    )

    # UX-3: el sparkline va inline en la linea del ranking (siempre visible).
    spark_inline = f'<span class="marca-spark">{spark} {delta_html}</span>'

    encabezados = "".join(
        f"<th>{escape(str(p.get('periodo_hasta', '')))}</th>" for p in serie
    )
    celdas = "".join(
        f'<td class="{_clase_engagement(e)}">{escape(str(e))}%</td>' for e in engs
    )
    # UX-3: la tabla detallada queda dentro del desplegable.
    tabla_detalle = (
        '<details class="tendencia">'
        "<summary>Tendencia de engagement (detalle)</summary>"
        "<table>"
        f"<tr><th>Periodo</th>{encabezados}</tr>"
        f"<tr><td>Engagement</td>{celdas}</tr>"
        "</table>"
        "</details>"
    )
    return spark_inline, tabla_detalle


def _render_engagement(
    rep: dict, nombres: dict[str, str], rango: str, historico: Historico | None
) -> str:
    """Seccion north-star: engagement global + ranking por marca, color-coded."""
    total = rep.get("total") or {}
    eng_global = total.get("engagement_pct", 0.0)
    clase_global = _clase_engagement(eng_global)

    # UX-5: leyenda del north-star como chips de color (no como frase larga gris).
    leyenda = (
        '<div class="ns-leyenda">'
        f'<span class="chip nivel eng-alto">alto &ge; {_ENG_UMBRAL_ALTO}%</span>'
        f'<span class="chip nivel eng-medio">ok {_ENG_UMBRAL_BAJO}–{_ENG_UMBRAL_ALTO}%</span>'
        f'<span class="chip nivel eng-bajo">bajo &lt; {_ENG_UMBRAL_BAJO}%</span>'
        "</div>"
    )

    partes = [
        '<h2 class="seccion">Engagement (north-star)</h2>',
        '<div class="ns-hero">',
        f'<span class="ns-valor {clase_global}">{escape(str(eng_global))}%</span>',
        '<span class="ns-etiqueta">Engagement global<br>'
        f'nivel {escape(_etiqueta_engagement(eng_global))}</span>',
        leyenda,
        "</div>",
    ]

    # Ranking por marca, ordenado por engagement descendente.
    filas = rep.get("cuentas") or []
    ordenadas = sorted(
        filas,
        key=lambda f: f["resumen"].get("engagement_pct", 0.0),
        reverse=True,
    )
    if not ordenadas:
        partes.append('<p class="vacio">Sin marcas en el periodo.</p>')
        return "".join(partes)

    max_eng = max((f["resumen"].get("engagement_pct", 0.0) for f in ordenadas), default=0.0)

    lis = []
    for pos, fila in enumerate(ordenadas, start=1):
        r = fila["resumen"]
        cuenta_id = r["cuenta"]
        nombre = etiqueta_marca(cuenta_id, nombres)
        eng = r.get("engagement_pct", 0.0)
        clase = _clase_engagement(eng)
        ancho = round(eng / max_eng * 100, 1) if max_eng else 0.0
        # UX-3: sparkline inline (siempre visible) + tabla detallada plegada.
        spark_inline, tabla_detalle = _tendencia_engagement(cuenta_id, rango, historico)
        lis.append(
            "<li>"
            f'<span class="pos">{pos}</span>'
            f'<span class="marca">{escape(nombre)}{spark_inline}</span>'
            f'<span class="nivel {clase}">{escape(_etiqueta_engagement(eng))}</span>'
            f'<span class="pct {clase}">{escape(str(eng))}%</span>'
            # UX-10: barra mas alta con el % visible dentro.
            f'<span class="barra">'
            f'<span class="relleno {clase}" style="width: {ancho}%"></span>'
            f'<span class="barra-pct">{escape(str(eng))}%</span>'
            f"</span>"
            f"{tabla_detalle}"
            "</li>"
        )
    partes.append(f'<ul class="ranking">{"".join(lis)}</ul>')
    return "".join(partes)


def _pieza_estrella(rep: dict) -> tuple[dict, str] | None:
    """Pieza con mayor engagement de todas las marcas (callout estrella, UX-7).

    Devuelve (pieza, cuenta_id) o None si no hay piezas en el reporte.
    """
    mejor: dict | None = None
    mejor_cuenta = ""
    for fila in rep.get("cuentas", []):
        cuenta_id = fila.get("resumen", {}).get("cuenta", "")
        for p in fila.get("mejores_piezas") or []:
            eng = p.get("engagement_pct") or 0.0
            if mejor is None or eng > (mejor.get("engagement_pct") or 0.0):
                mejor = p
                mejor_cuenta = cuenta_id
    if mejor is None:
        return None
    return mejor, mejor_cuenta


def _render_estrella(rep: dict, nombres: dict[str, str]) -> str:
    """Callout superior con la pieza que mas rompio del periodo (UX-7)."""
    estrella = _pieza_estrella(rep)
    if estrella is None:
        return ""
    pieza, cuenta_id = estrella
    marca = escape(etiqueta_marca(cuenta_id, nombres))
    plat = escape(_PLATAFORMA_ETIQUETA.get(pieza["plataforma"], pieza["plataforma"]))
    eng = escape(str(pieza.get("engagement_pct", 0.0)))
    titulo = escape(str(pieza.get("titulo", "")))
    return (
        '<div class="estrella">'
        '<span class="e-titulo">🔥 Lo que más rompió este mes '
        '<span class="e-criterio">(mayor engagement %)</span></span> '
        f'<span class="e-marca">{marca}</span> · '
        f'<span class="e-plat">{plat}</span> · '
        f'<span class="e-pct">{eng}%</span>'
        f'<span class="e-pieza">«{titulo}»</span>'
        "</div>"
    )


def construir_html(
    rep: dict,
    picos: dict,
    nombres: dict[str, str],
    rango: str | None = None,
    historico: Historico | None = None,
    presentacion: bool = False,
) -> str:
    """Renderiza el reporte + picos a un unico documento HTML autocontenido."""
    # rango crudo (para consultar el historico) vs. el escapado (para mostrar).
    rango_serie = rango if rango is not None else rep.get("rango", "")
    rango_txt = escape(str(rep.get("rango", "")))
    # UX-6: fecha legible es-MX ("24 may 2026") en vez del ISO crudo.
    generado = escape(_fecha_legible(str(rep.get("generado", ""))))
    fuente = escape(str(rep.get("fuente", "")))

    tarjetas = "".join(_render_tarjeta(f, nombres) for f in rep.get("cuentas", []))
    engagement = _render_engagement(rep, nombres, rango_serie, historico)
    estrella = _render_estrella(rep, nombres)
    body_clase = " presentacion" if presentacion else ""
    # UX-12: umbrales para la leyenda del pie (misma fuente de verdad que el hero).
    alto = _ENG_UMBRAL_ALTO
    bajo = _ENG_UMBRAL_BAJO

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dashboard de metricas — {rango_txt}</title>
<style>{_CSS}</style>
</head>
<body class="raiz{body_clase}">
<div class="envoltura">
<header class="cabecera">
<span class="eyebrow">KENI AI <span class="sep">·</span> AMX Contenido</span>
<h1>Dashboard de metricas — {rango_txt}</h1>
<p class="meta">Generado {generado} · fuente: {fuente}</p>
</header>

<h2 class="seccion">Total</h2>
{_render_kpis(rep["total"])}
{_render_cobertura_global(rep, nombres)}
{estrella}

{engagement}

<h2 class="seccion">Por marca</h2>
<div class="tarjetas">
{tarjetas}
</div>

{_render_picos(picos, nombres)}

<footer>
<div class="leyenda"><span class="et">Niveles de engagement:</span>\
<span class="chip nivel eng-alto">alto &ge; {alto}%</span>\
<span class="chip nivel eng-medio">ok {bajo}–{alto}%</span>\
<span class="chip nivel eng-bajo">bajo &lt; {bajo}%</span>\
<span>· 🔥 pieza con mayor engagement del periodo</span></div>
Generado en tu máquina · datos de muestra · sin red. \
Keni AI · dashboard de metricas · HTML estatico autocontenido (sin JS externo).</footer>
</div>
</body>
</html>
"""


def generar_dashboard(
    fuente: FuenteMetricas,
    rango: str = "mes",
    top: int = 3,
    historico: Historico | None = None,
    umbral_picos: int = 50,
    presentacion: bool = False,
) -> str:
    """Construye el reporte + picos desde la fuente y devuelve el HTML completo."""
    rep = construir_reporte(fuente, rango, top, historico)
    picos = detectar_picos(fuente, rango, umbral_picos, historico)
    nombres = {c.id: c.nombre for c in fuente.cuentas()}
    return construir_html(rep, picos, nombres, rango, historico, presentacion)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m keni_metricas.dashboard",
        description="Dashboard de metricas de redes como HTML estatico autocontenido.",
    )
    ap.add_argument("--salida", default="dashboard.html", help="ruta del archivo HTML (def: dashboard.html)")
    ap.add_argument("--rango", default="mes", help="semana | mes | 7d | 30d (def: mes)")
    ap.add_argument("--top", type=int, default=3, help="nº de mejores piezas por marca (def: 3)")
    ap.add_argument("--umbral-picos", type=int, default=50, help="umbral %% para alertas de picos (def: 50)")
    ap.add_argument(
        "--presentacion",
        action="store_true",
        help="sube la escala tipografica para sala proyectada (def: desactivado)",
    )
    args = ap.parse_args(argv)

    from .config import cargar_config, construir_fuente
    from .historico import Historico, historico_activo

    fuente = construir_fuente(cargar_config())
    historico = Historico() if historico_activo() else None
    try:
        html = generar_dashboard(
            fuente, args.rango, args.top, historico, args.umbral_picos, args.presentacion
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    Path(args.salida).expanduser().write_text(html, encoding="utf-8")
    print(f"Dashboard escrito en {args.salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
