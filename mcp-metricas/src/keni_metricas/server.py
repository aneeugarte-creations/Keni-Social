"""Punto de entrada del servidor MCP `keni-metricas` (transporte stdio)."""

from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

from .config import cargar_config, construir_fuente
from .historico import Historico, historico_activo
from .tools import registrar


def crear_servidor() -> FastMCP:
    # logging a stderr (NUNCA stdout: stdout es el canal JSON-RPC del MCP)
    logging.basicConfig(level=logging.WARNING)
    fuente = construir_fuente(cargar_config())
    historico = Historico() if historico_activo() else None
    mcp = FastMCP("keni-metricas")
    registrar(mcp, fuente, historico)
    return mcp


def main() -> None:
    crear_servidor().run()


if __name__ == "__main__":
    main()
