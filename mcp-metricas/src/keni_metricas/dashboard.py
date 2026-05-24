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


def construir_html(rep: dict, picos: dict, nombres: dict[str, str]) -> str:
    """Renderiza el reporte + picos a un unico documento HTML autocontenido."""
    rango = escape(str(rep.get("rango", "")))
    generado = escape(str(rep.get("generado", "")))
    fuente = escape(str(rep.get("fuente", "")))

    tarjetas = "".join(_render_tarjeta(f, nombres) for f in rep.get("cuentas", []))

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dashboard de metricas — {rango}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="envoltura">
<header class="cabecera">
<h1>Dashboard de metricas — {rango}</h1>
<p class="meta">Generado {generado} · fuente: {fuente}</p>
</header>

<h2 class="seccion">Total</h2>
{_render_kpis(rep["total"])}
{_render_cobertura_global(rep)}

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
    return construir_html(rep, picos, nombres)


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
