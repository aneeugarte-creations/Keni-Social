"""Reporte consolidado de todas las marcas/verticales.

Resuelve el trabajo manual de consolidar métricas: recorre todas las cuentas,
arma totales + desglose por marca + mejores piezas + variación, y lo renderiza
en Markdown. Usable como tool del MCP y como CLI (`keni-reporte`) para correr
headless/cron.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .fuentes.base import FuenteMetricas


def construir_reporte(fuente: FuenteMetricas, rango: str = "mes", top: int = 3, historico=None) -> dict:
    """Estructura JSON-serializable con el total y el desglose por marca."""
    cuentas = fuente.cuentas()
    filas: list[dict] = []
    tot_vis = tot_alc = tot_inter = 0

    for c in cuentas:
        r = fuente.resumen(c.id, rango)  # ValueError si el rango es inválido (se propaga)
        if historico is not None:
            historico.aplicar_variacion(r)
            historico.guardar(r)
        mejores = fuente.mejores_piezas(c.id, rango, top)
        filas.append(
            {
                "resumen": r.model_dump(mode="json"),
                "mejores_piezas": [p.model_dump(mode="json") for p in mejores],
            }
        )
        tot_vis += r.visualizaciones
        tot_alc += r.alcance
        tot_inter += r.interacciones

    return {
        "rango": rango,
        "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fuente": fuente.nombre,
        "total": {
            "visualizaciones": tot_vis,
            "alcance": tot_alc,
            "interacciones": tot_inter,
            "engagement_pct": round(tot_inter / tot_vis * 100, 1) if tot_vis else 0.0,
            "cuentas": len(filas),
        },
        "cuentas": filas,
    }


def _signo(pct: float) -> str:
    return f"+{pct}" if pct > 0 else f"{pct}"


def render_markdown(rep: dict) -> str:
    t = rep["total"]
    out: list[str] = []
    out.append(f"# Reporte de redes — {rep['rango']}")
    out.append(f"*Generado {rep['generado']} · fuente: {rep['fuente']}*\n")
    out.append("## Total")
    out.append(f"- **Visualizaciones:** {t['visualizaciones']:,}")
    out.append(f"- **Alcance:** {t['alcance']:,}")
    out.append(f"- **Interacciones:** {t['interacciones']:,}")
    out.append(f"- **Engagement:** {t['engagement_pct']}%")
    out.append(f"- **Cuentas:** {t['cuentas']}\n")

    for fila in rep["cuentas"]:
        r = fila["resumen"]
        var = r.get("variacion_vs_anterior") or {}
        v_vis = var.get("visualizaciones_pct")
        cab = f"## {r['cuenta']}"
        if v_vis is not None:
            cab += f"  ({_signo(v_vis)}% vis vs. anterior)"
        out.append(cab)
        out.append(
            f"- {r['visualizaciones']:,} vis · {r['alcance']:,} alcance · {r['engagement_pct']}% eng"
        )
        if r.get("por_plataforma"):
            out.append("\n| Plataforma | Visualizaciones | Engagement |")
            out.append("|---|---:|---:|")
            for m in r["por_plataforma"]:
                out.append(f"| {m['plataforma']} | {m['visualizaciones']:,} | {m['engagement_pct']}% |")
        if fila["mejores_piezas"]:
            out.append("\n**Mejores piezas:**")
            for p in fila["mejores_piezas"]:
                out.append(f"- [{p['plataforma']}] {p['titulo']} — {p['engagement_pct']}% ({p['visualizaciones']:,} vis)")
        out.append("")

    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="keni-reporte", description="Reporte consolidado de métricas de redes.")
    ap.add_argument("--rango", default="mes", help="semana | mes | 7d | 30d (def: mes)")
    ap.add_argument("--top", type=int, default=3, help="nº de mejores piezas por marca (def: 3)")
    ap.add_argument("--formato", choices=["md", "json"], default="md")
    ap.add_argument("--salida", help="ruta de archivo; si se omite, imprime a stdout")
    args = ap.parse_args(argv)

    from .config import cargar_config, construir_fuente
    from .historico import Historico, historico_activo

    fuente = construir_fuente(cargar_config())
    historico = Historico() if historico_activo() else None
    try:
        rep = construir_reporte(fuente, args.rango, args.top, historico)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    texto = json.dumps(rep, ensure_ascii=False, indent=2) if args.formato == "json" else render_markdown(rep)
    if args.salida:
        Path(args.salida).expanduser().write_text(texto, encoding="utf-8")
        print(f"Reporte escrito en {args.salida}")
    else:
        print(texto)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
