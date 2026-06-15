"""Análisis diario con narrativa: la capa "qué cambió y por qué" (F6 / #146).

Los datos ya existen (`comparar_periodos` + `picos` + `mejores_piezas` los dan);
lo que falta es la LECTURA: sobre las métricas de un periodo, una narrativa corta
y accionable de qué subió/bajó, qué pieza(s) lo explican y cuál es el siguiente
paso. No es un cálculo nuevo de métricas: ENSAMBLA lo que ya producen el reporte
consolidado y el detector de picos, y lo redacta.

Frontera (UX-roadmap §0, spec del coordinador de redes §0): keni-social CONSOLIDA y SUGIERE; la
interpretación final y la decisión de qué cambiar quedan en el equipo. Por eso la
narrativa NO atribuye causas de coyuntura externas (eso lo pone el humano): se
limita a "este número se movió y esta pieza lo acompaña", más una sugerencia de
loop a la acción ("pide copy/clip de lo que rinde").

Honestidad (issue #131): si la fuente es de muestra, el análisis lo MARCA en la
estructura misma (`es_muestra`/`aviso`) y en el render, para que sea imposible
confundir cifras sintéticas con reales. Si una marca no tiene engagement
comparable (#138) o el reporte viene vacío, degrada sin inventar.
"""

from __future__ import annotations

from datetime import UTC, datetime
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

# Umbral (en puntos %) a partir del cual una variación de visualizaciones se
# considera un "movimiento" digno de narrar. Por debajo es ruido: un día a día
# con ±2% no es noticia. Calibrado conservador para no gritar por cualquier cosa
# (principio UX #5: señal sobre ruido).
UMBRAL_MOVIMIENTO_PCT = 5.0

# Cuántos movimientos (marcas) describir como máximo en el resumen. El resto se
# colapsa en una línea (mismo criterio que picos/dashboard: top-N + resto).
MAX_MOVIMIENTOS = 3


def _variacion_vis(resumen: dict) -> float | None:
    """Variación de visualizaciones vs. el periodo anterior, o None si no la hay.

    Sale de `variacion_vs_anterior` del resumen, que el reporte rellena con el
    histórico (variación REAL) o con el modelo de la fuente (muestra). None si la
    clave no está (sin periodo anterior comparable): no se inventa un 0.
    """
    var = resumen.get("variacion_vs_anterior") or {}
    v = var.get("visualizaciones_pct")
    return float(v) if v is not None else None


def _pieza_estrella_marca(fila: dict) -> dict | None:
    """La pieza de mejor engagement de una marca (la que "explica" su movimiento).

    Toma las `mejores_piezas` que el reporte ya ordenó por engagement y devuelve
    la primera, o None si la marca no tiene piezas. No re-ordena ni recalcula: es
    el mismo criterio que el callout estrella del dashboard.
    """
    piezas = fila.get("mejores_piezas") or []
    return piezas[0] if piezas else None


def _movimiento(fila: dict, nombres: dict[str, str]) -> dict | None:
    """Movimiento narrable de UNA marca, o None si no hay variación que contar.

    Empaqueta la marca, su variación de visualizaciones, su engagement y la pieza
    estrella que acompaña el movimiento. La dirección (sube/baja/estable) se
    deriva del signo de la variación. La pieza solo se incluye si existe.
    """
    resumen = fila.get("resumen") or {}
    var = _variacion_vis(resumen)
    if var is None:
        return None
    cuenta_id = resumen.get("cuenta", "")
    pieza = _pieza_estrella_marca(fila)
    return {
        "marca_id": cuenta_id,
        "marca": etiqueta_marca(cuenta_id, nombres),
        "variacion_vis_pct": var,
        "direccion": "sube" if var > 0 else "baja" if var < 0 else "estable",
        "visualizaciones": resumen.get("visualizaciones", 0),
        "engagement_pct": resumen.get("engagement_pct"),
        "pieza": pieza,
    }


def _marca_lider(movimientos: list[dict]) -> dict | None:
    """La marca con mayor engagement entre las que tienen pieza estrella (para el
    siguiente paso). None si ninguna tiene engagement comparable ni pieza.

    El loop a la acción apunta a "dobla la apuesta por lo que rinde": lo que rinde
    es engagement alto + una pieza concreta que pedirle a Claude que reproduzca.
    """
    candidatos = [
        m for m in movimientos if m.get("engagement_pct") is not None and m.get("pieza")
    ]
    if not candidatos:
        return None
    return max(candidatos, key=lambda m: m["engagement_pct"])


def construir_analisis(
    fuente: FuenteMetricas,
    rango: str = "semana",
    marca: str | None = None,
    historico: Historico | None = None,
    umbral_movimiento_pct: float = UMBRAL_MOVIMIENTO_PCT,
) -> dict:
    """Ensambla la narrativa "qué cambió y por qué" + siguiente paso.

    Reutiliza el reporte consolidado (totales, variación vs. periodo anterior y
    mejores piezas por marca) y el detector de picos (piezas que despuntan), y los
    ordena en una lectura: movimientos del periodo, la(s) pieza(s) que los
    explican y una sugerencia accionable. NO recalcula métricas.

    Devuelve un dict JSON-serializable; `render_markdown` lo redacta. Propaga
    `ValueError` (rango inválido) y `CuentaNoEncontrada` (marca fuera de alcance),
    igual que el reporte.
    """
    rep = construir_reporte(fuente, rango, top=3, historico=historico)
    nombres = rep.get("nombres") or {}

    # Movimientos por marca, ordenados por magnitud absoluta de variación (lo más
    # llamativo primero), descartando las que no tienen variación comparable.
    movimientos = [
        m for fila in rep.get("cuentas", []) if (m := _movimiento(fila, nombres)) is not None
    ]
    movimientos.sort(key=lambda m: abs(m["variacion_vis_pct"]), reverse=True)

    # Sólo cuentan como "movimiento del periodo" los que superan el umbral; el
    # resto es estable y no se narra individualmente (señal sobre ruido).
    destacados = [m for m in movimientos if abs(m["variacion_vis_pct"]) >= umbral_movimiento_pct]
    visibles = destacados[:MAX_MOVIMIENTOS]
    n_resto = max(len(destacados) - len(visibles), 0)
    # Marcas que se movieron poco (por debajo del umbral): se mencionan en bloque.
    n_estables = len(movimientos) - len(destacados)

    # Piezas que despuntan (engagement muy por encima de la media de su cuenta):
    # son las que "explican el pico". Best-effort: si el detector falla, seguimos
    # con el resto del análisis (la narrativa no debe romperse por los picos).
    try:
        rep_picos = detectar_picos(fuente, rango, 50, historico)
        despuntes = [a for a in rep_picos.get("alertas", []) if a.get("tipo") == "pieza_despunta"]
    except Exception:  # noqa: BLE001 -- picos es complementario, nunca obligatorio
        despuntes = []

    lider = _marca_lider(movimientos)

    es_muestra = es_fuente_muestra(rep.get("fuente"))
    analisis: dict = {
        "rango": rango,
        "marca": marca or "",
        "generado": datetime.now(UTC).isoformat(timespec="seconds"),
        "fuente": rep.get("fuente"),
        "es_muestra": es_muestra,
        "total": rep.get("total") or {},
        "movimientos": visibles,
        "movimientos_resto": n_resto,
        "marcas_estables": n_estables,
        "piezas_despuntan": despuntes[:MAX_MOVIMIENTOS],
        # cobertura: si alguna marca tuvo datos parciales, la lectura puede estar
        # incompleta (los ceros de una plataforma omitida no son datos reales).
        "cobertura": rep.get("cobertura") or {"completa": True, "cuentas_parciales": []},
        "nombres": nombres,
        # siguiente_paso: el loop a la acción (UX-roadmap #11). None si no hay una
        # marca líder clara (sin engagement comparable ni piezas): no se inventa.
        "siguiente_paso": _siguiente_paso(lider),
    }
    # Aviso de PRIMER nivel cuando son datos de muestra: que el estado "no es real"
    # viaje en la estructura misma, no sólo en `fuente` (issue #131).
    if es_muestra:
        analisis["aviso"] = AVISO_MUESTRA_TXT
    return analisis


def _siguiente_paso(lider: dict | None) -> dict | None:
    """Sugerencia accionable que cierra el loop hacia la acción (UX-roadmap #11).

    Devuelve marca + texto de la sugerencia, o None si no hay una marca líder con
    pieza concreta a la que apuntar. El texto es nuestro lado de la frontera
    (sugerir); la decisión de qué pedir y publicar queda en el equipo.
    """
    if lider is None:
        return None
    pieza = lider.get("pieza") or {}
    plat = pieza.get("plataforma")
    titulo = pieza.get("titulo")
    detalle = f' Tu mejor pieza fue «{titulo}» en {plat}.' if titulo and plat else ""
    return {
        "marca_id": lider["marca_id"],
        "marca": lider["marca"],
        "engagement_pct": lider["engagement_pct"],
        "pieza": lider.get("pieza"),
        "texto": (
            f"{lider['marca']} es lo que mejor rindió este periodo "
            f"({lider['engagement_pct']}% de engagement).{detalle} "
            "Pídele a Claude copy o un clip en esa línea y dobla la apuesta por lo "
            "que funciona. Qué publicar y qué ajustar, lo decides tú."
        ),
    }


def _frase_movimiento(m: dict) -> str:
    """Una línea Markdown que narra el movimiento de una marca + su pieza estrella."""
    flecha = "🔼" if m["direccion"] == "sube" else "🔽" if m["direccion"] == "baja" else "▪️"
    verbo = "subió" if m["direccion"] == "sube" else "bajó" if m["direccion"] == "baja" else "estable"
    var = signo(m["variacion_vis_pct"])
    vis = miles(m["visualizaciones"])
    linea = f"- {flecha} **{m['marca']}** {verbo} {var}% en visualizaciones ({vis} vistas"
    if m.get("engagement_pct") is not None:
        linea += f", {m['engagement_pct']}% eng"
    linea += ")."
    pieza = m.get("pieza")
    if pieza:
        linea += (
            f" Lo explica «{pieza.get('titulo', '')}» en {pieza.get('plataforma', '')} "
            f"({pieza.get('engagement_pct', 0)}% eng)."
        )
    return linea


def render_markdown(analisis: dict) -> str:
    """Redacta el análisis a Markdown: lectura corta + piezas + siguiente paso.

    El veredicto/lectura va arriba; el detalle después (principio UX #1). Si son
    datos de muestra, antepone el banner (issue #131). Si no hay movimientos que
    narrar, lo dice con honestidad en vez de forzar una narrativa vacía.
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

    movimientos = analisis.get("movimientos") or []
    if not movimientos:
        # Degradación honesta: sin movimientos por encima del umbral no se narra
        # un pico que no existe.
        estables = analisis.get("marcas_estables", 0)
        if estables:
            out.append(
                f"- Sin movimientos destacados: las {estables} marcas se mantuvieron "
                "estables vs. el periodo anterior (variación por debajo del umbral)."
            )
        else:
            out.append("- Sin datos suficientes para una lectura del periodo.")
    else:
        out.append("**Lo que se movió:**")
        for m in movimientos:
            out.append(_frase_movimiento(m))
        if (resto := analisis.get("movimientos_resto", 0)) > 0:
            plural = "marca más" if resto == 1 else "marcas más"
            out.append(f"- … y {resto} {plural} con movimiento (ordenadas por magnitud).")
        if (estables := analisis.get("marcas_estables", 0)) > 0:
            plural = "marca se mantuvo estable" if estables == 1 else "marcas se mantuvieron estables"
            out.append(f"- El resto: {estables} {plural}.")

    paso = analisis.get("siguiente_paso")
    if paso is not None:
        out.append("")
        out.append(f"**Siguiente paso:** {paso['texto']}")

    return "\n".join(out)
