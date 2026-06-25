"""Reporte consolidado de todas las marcas/verticales.

Resuelve el trabajo manual de consolidar métricas: recorre todas las cuentas,
arma totales + desglose por marca + mejores piezas + variación, y lo renderiza
en Markdown. Usable como tool del MCP y como CLI (`keni-reporte`) para correr
headless/cron.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .formato import (
    AVISO_MUESTRA_TXT,
    aviso_muestra_md,
    cifra,
    es_fuente_muestra,
    etiqueta_marca,
    miles,
    partes_cobertura,
    pct,
    signo,
)
from .fuentes.base import FuenteMetricas

# Tope efectivamente "sin límite" para CONTAR todas las piezas del periodo: `mejores_piezas`
# ya descarga todas y trunca a `n`, así que pedir todas no añade llamadas a la API.
_TODAS_LAS_PIEZAS = 100_000

if TYPE_CHECKING:
    from .historico import Historico


def construir_reporte(
    fuente: FuenteMetricas,
    rango: str = "mes",
    top: int = 3,
    historico: Historico | None = None,
) -> dict:
    """Estructura JSON-serializable con el total y el desglose por marca."""
    cuentas = fuente.cuentas()
    filas: list[dict] = []
    tot_vis = tot_inter = tot_piezas = tot_impr = 0
    tot_alc: int | None = None  # se suma solo el alcance medido; None = nadie lo mide
    cuentas_parciales: list[str] = []  # marcas con alguna plataforma omitida
    # Mapa id->nombre legible (mismo origen que el dashboard). El resumen guarda
    # el id crudo; el render lo traduce al NOMBRE legible con este mapa.
    nombres: dict[str, str] = {}

    for c in cuentas:
        nombres[c.id] = c.nombre
        r = fuente.resumen(c.id, rango)  # ValueError si el rango es inválido (se propaga)
        if historico is not None:
            historico.aplicar_variacion(r)
            historico.guardar(r)
        # `mejores_piezas` descarga TODAS las piezas del periodo y solo trunca a `n`; pedir
        # todas (para CONTARLAS) no cuesta una llamada extra a la API. Las top-`top` se
        # quedan para mostrar; el total cuenta cuántas se publicaron.
        todas = fuente.mejores_piezas(c.id, rango, _TODAS_LAS_PIEZAS)
        mejores = todas[:top]
        tot_piezas += len(todas)
        filas.append(
            {
                "resumen": r.model_dump(mode="json"),
                "mejores_piezas": [p.model_dump(mode="json") for p in mejores],
            }
        )
        tot_vis += r.visualizaciones
        tot_impr += r.impresiones
        if r.alcance is not None:
            # solo suma el alcance realmente medido; deja None si nadie lo mide
            tot_alc = (tot_alc or 0) + r.alcance
        tot_inter += r.interacciones
        if r.cobertura is not None and r.cobertura.omitidas:
            cuentas_parciales.append(c.id)

    rep: dict = {
        "rango": rango,
        "generado": datetime.now(UTC).isoformat(timespec="seconds"),
        "fuente": fuente.nombre,
        "total": {
            "visualizaciones": tot_vis,
            "impresiones": tot_impr,
            "alcance": tot_alc,
            "interacciones": tot_inter,
            # engagement global no comparable: el total combina varias plataformas
            # con bases de visualización heterogéneas. El engagement fiable
            # vive por plataforma. None se muestra como "n/d".
            "engagement_pct": None,
            "cuentas": len(filas),
            "piezas": tot_piezas,
        },
        # cobertura global: marcas con datos parciales. Vacio = todas completas.
        # Hace explicito que los totales pueden no incluir todas las plataformas.
        "cobertura": {
            "completa": not cuentas_parciales,
            "cuentas_parciales": cuentas_parciales,
        },
        # mapa id->nombre legible para que el render imprima el NOMBRE de la
        # marca (no el id crudo). No cambia los ids internos del resumen.
        "nombres": nombres,
        "cuentas": filas,
    }
    # Campo `aviso` de PRIMER nivel cuando son datos de muestra: hace que el
    # estado "no es real" viaje en la estructura misma (no solo en `fuente`),
    # asi cualquier consumidor —tool JSON, agente, render— lo ve.
    if es_fuente_muestra(fuente.nombre):
        rep["aviso"] = AVISO_MUESTRA_TXT
    return rep


def _nota_cobertura(cob: dict | None) -> str | None:
    """Nota corta de cobertura para una marca; None si respondio todo (o no aplica)."""
    partes = partes_cobertura(cob)
    if partes is None:
        return None
    return "⚠️ cobertura parcial — sin datos de: " + ", ".join(partes) + " (los ceros NO son datos reales)"


def render_markdown(rep: dict) -> str:
    t = rep["total"]
    nombres = rep.get("nombres") or {}
    out: list[str] = []
    out.append(f"# Reporte de redes — {rep['rango']}")
    # Aviso DESTACADO si son datos de muestra (no solo el campo `fuente`): hace
    # imposible confundir cifras sinteticas con reales.
    if (aviso := aviso_muestra_md(rep.get("fuente"))) is not None:
        out.append(aviso + "\n")
    out.append(f"*Generado {rep['generado']} · fuente: {rep['fuente']}*\n")
    out.append("## Total")
    out.append(f"- **Visualizaciones:** {miles(t['visualizaciones'])}")
    out.append(f"- **Impresiones:** {miles(t.get('impresiones', 0))}")
    out.append(f"- **Alcance:** {cifra(t['alcance'])}")
    out.append(f"- **Interacciones:** {miles(t['interacciones'])}")
    out.append(f"- **Engagement:** {pct(t['engagement_pct'])} (ver por plataforma)")
    out.append(f"- **Piezas:** {miles(t.get('piezas', 0))}")
    out.append(f"- **Cuentas:** {t['cuentas']}")
    cob_global = rep.get("cobertura") or {}
    if cob_global.get("cuentas_parciales"):
        parciales = ", ".join(etiqueta_marca(c, nombres) for c in cob_global["cuentas_parciales"])
        out.append(f"- ⚠️ **Cobertura:** datos parciales en {parciales} (ver detalle por marca)")
    out.append("")

    for fila in rep["cuentas"]:
        r = fila["resumen"]
        var = r.get("variacion_vs_anterior") or {}
        v_vis = var.get("visualizaciones_pct")
        cab = f"## {etiqueta_marca(r['cuenta'], nombres)}"
        if v_vis is not None:
            cab += f"  ({signo(v_vis)}% vis vs. anterior)"
        out.append(cab)
        out.append(
            f"- {miles(r['visualizaciones'])} vis · {cifra(r['alcance'])} alcance · {pct(r['engagement_pct'])} eng"
        )
        if (nota := _nota_cobertura(r.get("cobertura"))) is not None:
            out.append(f"- {nota}")
        if r.get("por_plataforma"):
            out.append("\n| Plataforma | Visualizaciones | Engagement |")
            out.append("|---|---:|---:|")
            for m in r["por_plataforma"]:
                out.append(f"| {m['plataforma']} | {miles(m['visualizaciones'])} | {m['engagement_pct']}% |")
        if fila["mejores_piezas"]:
            out.append("\n**Mejores piezas:**")
            for p in fila["mejores_piezas"]:
                vis = miles(p['visualizaciones'])
                out.append(f"- [{p['plataforma']}] {p['titulo']} — {p['engagement_pct']}% ({vis} vis)")
        out.append("")

    return "\n".join(out)


# Encabezados del CSV (español, claros para una hoja de cálculo). Una fila por
# marca x plataforma + una fila TOTAL por marca + un total global.
CSV_ENCABEZADOS = [
    "marca",
    "plataforma",
    "visualizaciones",
    "impresiones",
    "alcance",
    "interacciones",
    "engagement_pct",
]
# Etiqueta de la columna "plataforma" en las filas de total (por marca y global).
CSV_TOTAL = "TOTAL"


def render_csv(rep: dict) -> str:
    """Serializa el reporte consolidado a CSV bien formado (módulo csv de stdlib).

    Pensado para abrir directo en Excel/Sheets y dejar de juntar números a mano:
    una fila por **marca x plataforma**, una fila **TOTAL** por marca (con
    `plataforma = "TOTAL"`) y una fila de **total global** al final (marca y
    plataforma = "TOTAL"). Usa el mapa `nombres` para imprimir el NOMBRE legible
    de la marca (no el id crudo), igual que el render Markdown.
    """
    nombres = rep.get("nombres") or {}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_ENCABEZADOS)

    for fila in rep["cuentas"]:
        r = fila["resumen"]
        marca = etiqueta_marca(r["cuenta"], nombres)
        for m in r.get("por_plataforma") or []:
            w.writerow(
                [
                    marca,
                    m["plataforma"],
                    m["visualizaciones"],
                    m.get("impresiones", 0),
                    m["alcance"],
                    m["interacciones"],
                    m["engagement_pct"],
                ]
            )
        # total por marca (suma de sus plataformas, ya consolidado en el resumen)
        w.writerow(
            [
                marca,
                CSV_TOTAL,
                r["visualizaciones"],
                r.get("impresiones", 0),
                r["alcance"],
                r["interacciones"],
                r["engagement_pct"],
            ]
        )

    # total global de todas las marcas
    t = rep["total"]
    w.writerow(
        [
            CSV_TOTAL,
            CSV_TOTAL,
            t["visualizaciones"],
            t.get("impresiones", 0),
            t["alcance"],
            t["interacciones"],
            t["engagement_pct"],
        ]
    )

    return buf.getvalue()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="keni-reporte", description="Reporte consolidado de métricas de redes.")
    ap.add_argument("--rango", default="mes", help="semana | mes | 7d | 30d (def: mes)")
    ap.add_argument("--top", type=int, default=3, help="nº de mejores piezas por marca (def: 3)")
    ap.add_argument(
        "--formato",
        choices=["md", "json", "csv"],
        default="md",
        help="md (def) | json | csv (una fila por marca x plataforma + totales, para hoja de cálculo)",
    )
    ap.add_argument("--salida", help="ruta de archivo; si se omite, imprime a stdout")
    ap.add_argument("--picos", action="store_true", help="añade una sección de alertas (picos/anomalías)")
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

    if args.picos:
        from . import picos as picos_mod

        rep["picos"] = picos_mod.detectar_picos(fuente, args.rango, 50, historico)

    if args.formato == "json":
        texto = json.dumps(rep, ensure_ascii=False, indent=2)
    elif args.formato == "csv":
        # csv ignora --picos: es una tabla consolidada para hoja de cálculo, no
        # un documento con secciones (las alertas viven en md/json).
        texto = render_csv(rep)
    else:
        texto = render_markdown(rep)
        if args.picos:
            from . import picos as picos_mod

            texto += "\n\n" + picos_mod.render_markdown(rep["picos"])

    if args.salida:
        destino = Path(args.salida).expanduser()
        if args.formato == "csv":
            # csv ya emite sus propios fin-de-línea (\r\n): newline="" evita que
            # el modo texto los vuelva a traducir y duplique los retornos.
            with destino.open("w", encoding="utf-8", newline="") as fh:
                fh.write(texto)
        else:
            destino.write_text(texto, encoding="utf-8")
        print(f"Reporte escrito en {args.salida}")
    elif args.formato == "csv":
        # el csv ya termina cada fila con su propio salto: lo escribimos tal cual
        # (sin el "\n" extra de print) para no dejar una fila vacia al final.
        sys.stdout.write(texto)
    else:
        print(texto)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
