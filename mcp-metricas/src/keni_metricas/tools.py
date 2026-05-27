"""Tools del MCP. Se registran contra una FuenteMetricas (muestra o real)."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .fuentes.base import CuentaNoEncontrada, FuenteMetricas
from .historico import Historico


def registrar(mcp: FastMCP, fuente: FuenteMetricas, historico: Historico | None = None) -> None:
    @mcp.tool()
    def listar_cuentas() -> dict:
        """Lista las cuentas/marcas de redes disponibles (UnoTV, Claro Sports, etc.)
        y sus plataformas. Usala primero para saber que se puede consultar."""
        return {
            "cuentas": [c.model_dump(mode="json") for c in fuente.cuentas()],
            "fuente": fuente.nombre,
        }

    @mcp.tool()
    def metricas_resumen(cuenta: str, rango: str = "semana") -> dict:
        """Resumen de metricas de una cuenta para un rango ('semana', 'mes', '7d' o
        '30d'): visualizaciones, alcance, engagement y variacion vs. el periodo
        anterior, con desglose por plataforma. Responde '¿como van mis metricas?'."""
        try:
            r = fuente.resumen(cuenta, rango)
        except (CuentaNoEncontrada, ValueError) as e:
            return {"error": str(e)}
        if historico is not None:
            historico.aplicar_variacion(r)  # variacion REAL si hay periodo anterior
            historico.guardar(r)
        return r.model_dump(mode="json")

    @mcp.tool()
    def mejores_piezas(cuenta: str, rango: str = "semana", n: int = 3) -> dict:
        """Las N piezas (publicaciones) con mejor desempeno de una cuenta en el rango,
        ordenadas por engagement. Util para '¿que contenido funciono mejor?'."""
        n = max(1, min(int(n), 10))
        try:
            piezas = fuente.mejores_piezas(cuenta, rango, n)
        except (CuentaNoEncontrada, ValueError) as e:
            return {"error": str(e)}
        return {
            "cuenta": cuenta,
            "rango": rango,
            "n": n,
            "piezas": [p.model_dump(mode="json") for p in piezas],
            "fuente": fuente.nombre,
        }

    @mcp.tool()
    def comparar_periodos(cuenta: str, rango_a: str = "semana", rango_b: str = "mes") -> dict:
        """Compara las metricas de una cuenta entre dos rangos (p. ej. 'semana' vs 'mes')."""
        try:
            a = fuente.resumen(cuenta, rango_a)
            b = fuente.resumen(cuenta, rango_b)
        except (CuentaNoEncontrada, ValueError) as e:
            return {"error": str(e)}

        def pct(x: int, y: int) -> float:
            return round((x - y) / y * 100, 1) if y else 0.0

        diferencia: dict = {
            "visualizaciones_pct": pct(a.visualizaciones, b.visualizaciones),
        }
        # delta de engagement en PUNTOS. Misma clave que historico.variacion y
        # variacion_vs_anterior del esquema: una sola convencion en todo el MCP.
        # Si alguno de los engagement es None (no comparable entre plataformas,
        # #138) no hay delta defendible: se omite la clave.
        if a.engagement_pct is not None and b.engagement_pct is not None:
            diferencia["engagement_pct"] = round(a.engagement_pct - b.engagement_pct, 1)

        return {
            "cuenta": cuenta,
            "a": a.model_dump(mode="json"),
            "b": b.model_dump(mode="json"),
            "diferencia": diferencia,
        }

    @mcp.tool()
    def tendencia_historica(cuenta: str, rango: str = "semana", n: int = 8) -> dict:
        """Evolucion historica de una cuenta: las ultimas n lecturas guardadas
        (visualizaciones y engagement por periodo). Util para ver si una cuenta
        sube o baja en el tiempo. Requiere haber consultado metricas_resumen antes."""
        if historico is None:
            return {"error": "El historico no esta activado (KENI_METRICAS_HISTORICO=0)."}
        n = max(1, min(int(n), 52))
        puntos = historico.serie(cuenta, rango, n)
        if not puntos:
            return {
                "cuenta": cuenta,
                "rango": rango,
                "puntos": [],
                "nota": "Aun no hay historico para esta cuenta/rango. Consulta metricas_resumen y vuelve mas tarde.",
            }
        return {"cuenta": cuenta, "rango": rango, "puntos": puntos}

    @mcp.tool()
    def reporte_consolidado(rango: str = "mes", top: int = 3) -> dict:
        """Reporte de TODAS las marcas/verticales en un rango: total + desglose por
        marca + mejores piezas + variacion. Es el informe periodico consolidado
        (lo que antes se hacia a mano). 'rango': semana|mes|7d|30d."""
        from .reporte import construir_reporte

        top = max(1, min(int(top), 10))
        try:
            return construir_reporte(fuente, rango, top, historico)
        except ValueError as e:
            return {"error": str(e)}

    @mcp.tool()
    def picos(rango: str = "semana", umbral_pct: int = 50) -> dict:
        """Alerta proactiva de anomalías: marca piezas que despuntan muy por encima
        del engagement medio de su cuenta, y cuentas que se desvían de su baseline
        histórico (>= umbral_pct). Responde '¿qué debería estar mirando AHORA?'."""
        from .picos import detectar_picos

        try:
            return detectar_picos(fuente, rango, max(1, int(umbral_pct)), historico)
        except (CuentaNoEncontrada, ValueError) as e:
            return {"error": str(e)}
