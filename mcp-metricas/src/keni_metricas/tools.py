"""Tools del MCP. Se registran contra una FuenteMetricas (muestra o real)."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .fuentes.base import CuentaNoEncontrada, FuenteMetricas


def registrar(mcp: FastMCP, fuente: FuenteMetricas) -> None:
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
            return fuente.resumen(cuenta, rango).model_dump(mode="json")
        except (CuentaNoEncontrada, ValueError) as e:
            return {"error": str(e)}

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

        return {
            "cuenta": cuenta,
            "a": a.model_dump(mode="json"),
            "b": b.model_dump(mode="json"),
            "diferencia": {
                "visualizaciones_pct": pct(a.visualizaciones, b.visualizaciones),
                "engagement_pp": round(a.engagement_pct - b.engagement_pct, 1),
            },
        }
