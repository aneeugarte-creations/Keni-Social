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

from .fuentes.base import FuenteMetricas
from .picos import detectar_picos
from .reporte import construir_reporte

# Etiquetas legibles para los motivos de omision de cobertura.
_MOTIVO_TEXTO = {
    "sin_credenciales": "sin credenciales",
    "presupuesto_agotado": "presupuesto agotado",
    "error_api": "error de API",
}

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


def _miles(n: int | float) -> str:
    """Formatea un entero con separador de miles (estilo es-MX: punto)."""
    try:
        return f"{int(n):,}".replace(",", ".")
    except (TypeError, ValueError):
        return escape(str(n))


def _signo(pct: float) -> str:
    """Devuelve el porcentaje con signo explicito (+/-)."""
    return f"+{pct}" if pct > 0 else f"{pct}"


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
    if not cob or not cob.get("omitidas"):
        return None
    motivo = cob.get("motivo") or {}
    partes = [
        f"{_PLATAFORMA_ETIQUETA.get(p, p)} ({_MOTIVO_TEXTO.get(motivo.get(p, ''), motivo.get(p, '?'))})"
        for p in cob["omitidas"]
    ]
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
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--fondo);
  color: var(--tinta);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  line-height: 1.5;
  font-size: 16px;
}
.envoltura { max-width: 980px; margin: 0 auto; padding: 32px 20px 64px; }
header.cabecera { border-bottom: 2px solid var(--tinta); padding-bottom: 16px; margin-bottom: 24px; }
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
.vacio { color: var(--gris); font-style: italic; }

/* --- Engagement: metrica north-star --- */
.ns-hero {
  display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap;
  border: 2px solid var(--tinta); border-radius: 12px;
  padding: 18px 22px; margin: 0 0 18px; background: var(--fondo-suave);
}
.ns-hero .ns-valor { font-size: 2.6rem; font-weight: 700; line-height: 1; letter-spacing: -0.02em; }
.ns-hero .ns-etiqueta { font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--gris); }
.ns-hero .ns-nota { color: var(--gris); font-size: 0.82rem; flex-basis: 100%; }
.ranking { margin: 0; padding: 0; list-style: none; }
.ranking li {
  display: grid; grid-template-columns: 1.6rem 1fr auto auto; align-items: center;
  gap: 10px; padding: 10px 12px; border: 1px solid var(--gris-claro);
  border-radius: 8px; margin-bottom: 8px;
}
.ranking .pos { color: var(--gris); font-size: 0.9rem; font-weight: 600; text-align: right; }
.ranking .marca { font-weight: 600; }
.ranking .pct { font-size: 1.2rem; font-weight: 700; font-variant-numeric: tabular-nums; }
.ranking .barra {
  grid-column: 1 / -1; height: 6px; border-radius: 3px;
  background: var(--gris-claro); overflow: hidden; margin-top: 2px;
}
.ranking .barra span { display: block; height: 100%; border-radius: 3px; }
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
"""


def _render_kpis(total: dict) -> str:
    kpis = [
        ("Visualizaciones", _miles(total["visualizaciones"])),
        ("Alcance", _miles(total["alcance"])),
        ("Interacciones", _miles(total["interacciones"])),
        ("Engagement", f"{total['engagement_pct']}%"),
        ("Cuentas", _miles(total["cuentas"])),
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
    nombre = nombres.get(cuenta_id, cuenta_id)
    var = r.get("variacion_vs_anterior") or {}
    v_vis = var.get("visualizaciones_pct")

    if v_vis is not None:
        var_html = (
            f'<span class="var {_clase_variacion(v_vis)}">{escape(_signo(v_vis))}% vis</span>'
        )
    else:
        var_html = ""

    cifras = (
        '<div class="cifras">'
        f'<div><span class="n">{_miles(r["visualizaciones"])}</span><span class="l">Visualizaciones</span></div>'
        f'<div><span class="n">{_miles(r["alcance"])}</span><span class="l">Alcance</span></div>'
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
            vis = _miles(p["visualizaciones"])
            lis.append(
                f'<li><span class="plat">{escape(plat)}</span> · '
                f'<span class="eng">{eng}%</span> · {vis} vis<br>'
                f'<span class="ttl-pieza">{titulo}</span></li>'
            )
        partes.append(f'<ul class="piezas">{"".join(lis)}</ul>')

    partes.append("</div>")
    return "".join(partes)


def _render_alerta(a: dict) -> str:
    tipo = a.get("tipo")
    if tipo == "pieza_despunta":
        plat = _PLATAFORMA_ETIQUETA.get(a["plataforma"], a["plataforma"])
        return (
            '<li><span class="tag">Pieza que despunta</span>'
            f'<strong>{escape(a["cuenta"])}</strong> · {escape(plat)} · '
            f'&laquo;{escape(a["titulo"])}&raquo; alcanza {escape(str(a["engagement_pct"]))}% de engagement '
            f'({escape(str(a["factor"]))}&times; la media de {escape(str(a["baseline_engagement_pct"]))}%).</li>'
        )
    verbo = "sube" if tipo == "cuenta_alza" else "cae"
    return (
        f'<li><span class="tag">Cuenta que {escape(verbo)}</span>'
        f'<strong>{escape(a["cuenta"])}</strong> {escape(verbo)} {escape(str(a["desviacion_pct"]))}% '
        f'vs. su baseline ({_miles(a["baseline"])} &rarr; {_miles(a["visualizaciones"])} vis).</li>'
    )


def _render_picos(picos: dict) -> str:
    partes = ['<h2 class="seccion">Alertas (picos)</h2>']
    cob = picos.get("cobertura") or {}
    if cob.get("cuentas_parciales"):
        parciales = ", ".join(escape(c) for c in cob["cuentas_parciales"])
        partes.append(
            f'<p class="aviso"><strong>Aviso.</strong> Cobertura parcial en {parciales}: '
            "las alertas pueden estar incompletas.</p>"
        )
    alertas = picos.get("alertas") or []
    if not alertas:
        partes.append('<p class="vacio">Sin anomalias por encima del umbral. Todo dentro de lo normal.</p>')
        return "".join(partes)
    lis = "".join(_render_alerta(a) for a in alertas)
    partes.append(f'<ul class="alertas">{lis}</ul>')
    return "".join(partes)


def _render_cobertura_global(rep: dict) -> str:
    """Aviso de cobertura a nivel reporte. Siempre rinde algo (la nota es obligatoria)."""
    cob = rep.get("cobertura") or {}
    if cob.get("cuentas_parciales"):
        parciales = ", ".join(escape(c) for c in cob["cuentas_parciales"])
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


def _tendencia_engagement(cuenta_id: str, rango: str, historico) -> str:
    """Mini-tendencia de engagement por marca desde el historico.

    Devuelve "" si no hay historico o no hay >= 2 snapshots (sin tendencia que
    mostrar): se omite con elegancia, nunca lanza.
    """
    if historico is None:
        return ""
    try:
        serie = historico.serie(cuenta_id, rango, _ENG_TREND_N)
    except Exception:  # noqa: BLE001 — el historico es best-effort, nunca debe romper el dashboard
        return ""
    if not serie or len(serie) < 2:
        return ""

    engs = [float(p.get("engagement_pct") or 0.0) for p in serie]
    spark = _sparkline(engs)

    encabezados = "".join(
        f"<th>{escape(str(p.get('periodo_hasta', '')))}</th>" for p in serie
    )
    celdas = "".join(
        f'<td class="{_clase_engagement(e)}">{escape(str(e))}%</td>' for e in engs
    )
    delta = round(engs[-1] - engs[0], 1)
    delta_html = (
        f'<span class="var {_clase_variacion(delta)}">{escape(_signo(delta))} pts</span>'
    )

    return (
        '<details class="tendencia">'
        f"<summary>Tendencia de engagement {spark} {delta_html}</summary>"
        "<table>"
        f"<tr><th>Periodo</th>{encabezados}</tr>"
        f"<tr><td>Engagement</td>{celdas}</tr>"
        "</table>"
        "</details>"
    )


def _render_engagement(rep: dict, nombres: dict[str, str], rango: str, historico) -> str:
    """Seccion north-star: engagement global + ranking por marca, color-coded."""
    total = rep.get("total") or {}
    eng_global = total.get("engagement_pct", 0.0)
    clase_global = _clase_engagement(eng_global)

    partes = [
        '<h2 class="seccion">Engagement (north-star)</h2>',
        '<div class="ns-hero">',
        f'<span class="ns-valor {clase_global}">{escape(str(eng_global))}%</span>',
        '<span class="ns-etiqueta">Engagement global<br>'
        f'nivel {escape(_etiqueta_engagement(eng_global))}</span>',
        '<span class="ns-nota">Interacciones / visualizaciones del periodo. '
        f"Umbrales: alto &ge; {_ENG_UMBRAL_ALTO}%, ok {_ENG_UMBRAL_BAJO}–{_ENG_UMBRAL_ALTO}%, "
        f"bajo &lt; {_ENG_UMBRAL_BAJO}%.</span>",
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
        nombre = nombres.get(cuenta_id, cuenta_id)
        eng = r.get("engagement_pct", 0.0)
        clase = _clase_engagement(eng)
        ancho = round(eng / max_eng * 100, 1) if max_eng else 0.0
        tendencia = _tendencia_engagement(cuenta_id, rango, historico)
        lis.append(
            "<li>"
            f'<span class="pos">{pos}</span>'
            f'<span class="marca">{escape(nombre)}</span>'
            f'<span class="nivel {clase}">{escape(_etiqueta_engagement(eng))}</span>'
            f'<span class="pct {clase}">{escape(str(eng))}%</span>'
            f'<span class="barra"><span class="{clase}" style="width: {ancho}%"></span></span>'
            f"{tendencia}"
            "</li>"
        )
    partes.append(f'<ul class="ranking">{"".join(lis)}</ul>')
    return "".join(partes)


def construir_html(
    rep: dict,
    picos: dict,
    nombres: dict[str, str],
    rango: str | None = None,
    historico=None,
) -> str:
    """Renderiza el reporte + picos a un unico documento HTML autocontenido."""
    # rango crudo (para consultar el historico) vs. el escapado (para mostrar).
    rango_serie = rango if rango is not None else rep.get("rango", "")
    rango_txt = escape(str(rep.get("rango", "")))
    generado = escape(str(rep.get("generado", "")))
    fuente = escape(str(rep.get("fuente", "")))

    tarjetas = "".join(_render_tarjeta(f, nombres) for f in rep.get("cuentas", []))
    engagement = _render_engagement(rep, nombres, rango_serie, historico)

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dashboard de metricas — {rango_txt}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="envoltura">
<header class="cabecera">
<h1>Dashboard de metricas — {rango_txt}</h1>
<p class="meta">Generado {generado} · fuente: {fuente}</p>
</header>

<h2 class="seccion">Total</h2>
{_render_kpis(rep["total"])}
{_render_cobertura_global(rep)}

{engagement}

<h2 class="seccion">Por marca</h2>
<div class="tarjetas">
{tarjetas}
</div>

{_render_picos(picos)}

<footer>Keni AI · dashboard de metricas · HTML estatico autocontenido (sin red, sin JS externo).</footer>
</div>
</body>
</html>
"""


def generar_dashboard(
    fuente: FuenteMetricas,
    rango: str = "mes",
    top: int = 3,
    historico=None,
    umbral_picos: int = 50,
) -> str:
    """Construye el reporte + picos desde la fuente y devuelve el HTML completo."""
    rep = construir_reporte(fuente, rango, top, historico)
    picos = detectar_picos(fuente, rango, umbral_picos, historico)
    nombres = {c.id: c.nombre for c in fuente.cuentas()}
    return construir_html(rep, picos, nombres, rango, historico)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m keni_metricas.dashboard",
        description="Dashboard de metricas de redes como HTML estatico autocontenido.",
    )
    ap.add_argument("--salida", default="dashboard.html", help="ruta del archivo HTML (def: dashboard.html)")
    ap.add_argument("--rango", default="mes", help="semana | mes | 7d | 30d (def: mes)")
    ap.add_argument("--top", type=int, default=3, help="nº de mejores piezas por marca (def: 3)")
    ap.add_argument("--umbral-picos", type=int, default=50, help="umbral %% para alertas de picos (def: 50)")
    args = ap.parse_args(argv)

    from .config import cargar_config, construir_fuente
    from .historico import Historico, historico_activo

    fuente = construir_fuente(cargar_config())
    historico = Historico() if historico_activo() else None
    try:
        html = generar_dashboard(fuente, args.rango, args.top, historico, args.umbral_picos)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    Path(args.salida).expanduser().write_text(html, encoding="utf-8")
    print(f"Dashboard escrito en {args.salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
