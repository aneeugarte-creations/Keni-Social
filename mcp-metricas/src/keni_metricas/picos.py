"""Detección de picos: alerta proactiva de anomalías.

A diferencia del análisis bajo petición (resumen, reporte), esto mira solo y marca
lo que se sale de lo normal, para no tener que vigilar dashboards:
- **piezas que despuntan:** engagement muy por encima de la media de su cuenta.
- **cuentas que se desvían:** visualizaciones muy por encima/debajo de su baseline
  histórico (requiere histórico con ≥2 periodos previos).
"""

from __future__ import annotations

from datetime import UTC, datetime

from .formato import etiqueta_marca, linea_resto_picos, miles, particionar_picos
from .fuentes.base import FuenteMetricas
from .historico import Historico


def detectar_picos(
    fuente: FuenteMetricas,
    rango: str = "semana",
    umbral_pct: int = 50,
    historico: Historico | None = None,
) -> dict:
    alertas: list[dict] = []
    cuentas_parciales: list[str] = []  # marcas con cobertura incompleta al detectar picos
    # Mapa id->nombre legible (mismo origen que usa el dashboard). Las alertas
    # guardan el id crudo; el render lo traduce a nombre legible con este mapa.
    nombres: dict[str, str] = {}

    for c in fuente.cuentas():
        nombres[c.id] = c.nombre
        r = fuente.resumen(c.id, rango)
        if r.cobertura is not None and r.cobertura.omitidas:
            cuentas_parciales.append(c.id)

        # 1) piezas que despuntan vs. el engagement medio de la cuenta
        if r.engagement_pct > 0:
            for p in fuente.mejores_piezas(c.id, rango, 5):
                factor = p.engagement_pct / r.engagement_pct
                if (factor - 1) * 100 >= umbral_pct:
                    alertas.append(
                        {
                            "tipo": "pieza_despunta",
                            "cuenta": c.id,
                            "plataforma": p.plataforma.value,
                            "titulo": p.titulo,
                            "engagement_pct": p.engagement_pct,
                            "baseline_engagement_pct": r.engagement_pct,
                            "factor": round(factor, 1),
                            "url": p.url,
                        }
                    )

        # 2) cuenta vs. baseline histórico (sólo si hay historia previa suficiente)
        if historico is not None:
            previos = [
                s for s in historico.serie(c.id, rango, 8) if s["periodo_hasta"] < r.periodo.hasta.isoformat()
            ]
            if len(previos) >= 2:
                base = sum(s["visualizaciones"] for s in previos) / len(previos)
                if base > 0:
                    desv = (r.visualizaciones - base) / base * 100
                    if abs(desv) >= umbral_pct:
                        alertas.append(
                            {
                                "tipo": "cuenta_alza" if desv > 0 else "cuenta_caida",
                                "cuenta": c.id,
                                "visualizaciones": r.visualizaciones,
                                "baseline": int(base),
                                "desviacion_pct": round(desv, 1),
                            }
                        )

    def _magnitud(a: dict) -> float:
        # Ranking unico: ambos tipos de alerta se normalizan al MISMO eje, un
        # "factor sobre baseline" (1.0 = igual al baseline; cuanto mayor, mas
        # anomalo). Asi piezas y cuentas son comparables en una sola lista.
        #   - pieza_despunta: `factor` = engagement / engagement_medio (p.ej. 1.5
        #     = 50% por encima de la media de la cuenta).
        #   - cuenta_alza/cuenta_caida: 1 + |desviacion_pct|/100 (p.ej. una caida
        #     o alza del 60% => 1.6). El valor absoluto trata alza y caida con la
        #     misma severidad: lo que ordena es cuanto se aleja del baseline, no
        #     la direccion.
        if "factor" in a:
            return a["factor"]
        return 1 + abs(a.get("desviacion_pct", 0)) / 100

    alertas.sort(key=_magnitud, reverse=True)
    return {
        "rango": rango,
        "umbral_pct": umbral_pct,
        "generado": datetime.now(UTC).isoformat(timespec="seconds"),
        "alertas": alertas,
        # mapa id->nombre legible para que el render (markdown/digest) imprima el
        # NOMBRE de la marca, no el id crudo. No cambia los ids internos.
        "nombres": nombres,
        # cobertura: si alguna marca tuvo datos parciales, las alertas (y la ausencia
        # de ellas) pueden estar incompletas. Vacio = se evaluo todo.
        "cobertura": {
            "completa": not cuentas_parciales,
            "cuentas_parciales": cuentas_parciales,
        },
    }


def _render_alerta(a: dict, nombres: dict) -> str:
    """Linea Markdown de UNA alerta, con el NOMBRE legible de la marca."""
    marca = etiqueta_marca(a["cuenta"], nombres)
    if a["tipo"] == "pieza_despunta":
        return (
            f"- 🔼 **{marca}** · [{a['plataforma']}] \"{a['titulo']}\" despunta a "
            f"{a['engagement_pct']}% ({a['factor']}× la media de {a['baseline_engagement_pct']}%)"
        )
    icono = "📈" if a["tipo"] == "cuenta_alza" else "📉"
    verbo = "sube" if a["tipo"] == "cuenta_alza" else "cae"
    base, vis = miles(a['baseline']), miles(a['visualizaciones'])
    return f"- {icono} **{marca}** {verbo} {a['desviacion_pct']}% vs. su baseline ({base} → {vis})"


def render_markdown(rep: dict) -> str:
    out = [f"## Alertas (picos, umbral {rep['umbral_pct']}%)"]
    nombres = rep.get("nombres") or {}
    cob = rep.get("cobertura") or {}
    if cob.get("cuentas_parciales"):
        # Cobertura tambien con NOMBRE legible (consistente con el resto del CLI).
        parciales = ", ".join(etiqueta_marca(c, nombres) for c in cob["cuentas_parciales"])
        out.append(f"> ⚠️ Cobertura parcial en {parciales}: las alertas pueden estar incompletas.")
    if not rep["alertas"]:
        out.append("- Sin anomalías por encima del umbral. Todo dentro de lo normal.")
        return "\n".join(out)
    # top-N por magnitud (ya vienen ordenadas) + resto colapsado en una linea,
    # mismo criterio que el dashboard para no volcar ~24 alertas planas.
    visibles, n_resto = particionar_picos(rep["alertas"])
    for a in visibles:
        out.append(_render_alerta(a, nombres))
    if (linea := linea_resto_picos(n_resto)) is not None:
        out.append(f"- {linea}")
    return "\n".join(out)
