"""Punto de entrada del servidor MCP `keni-tablero`.

Transporte por entorno, igual que `keni-metricas`:

- `KENI_MCP_TRANSPORT=stdio` (def): JSON-RPC sobre stdio (local por persona). El logging
  va SIEMPRE a stderr (stdout es el canal JSON-RPC).
- `KENI_MCP_TRANSPORT=http`: streamable-HTTP (`KENI_MCP_HOST`/`KENI_MCP_PORT`, def
  `127.0.0.1:8001` para no chocar con keni-metricas en 8000).

El servidor habla con la Consola por su API HTTP (ver `cliente.py`/`config.py`); no toca
ninguna BD por su cuenta.
"""

from __future__ import annotations

import logging
import os

from mcp.server.fastmcp import FastMCP

from .cliente import ClienteConsola
from .config import cargar_config
from .tools import registrar

log = logging.getLogger("keni_tablero")


def _transporte() -> str:
    return (os.environ.get("KENI_MCP_TRANSPORT") or "stdio").strip().lower()


def crear_servidor() -> FastMCP:
    logging.basicConfig(level=logging.WARNING)  # a stderr; nunca stdout (canal JSON-RPC)
    cfg = cargar_config()
    host = os.environ.get("KENI_MCP_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("KENI_MCP_PORT", "8001"))
    except ValueError:
        port = 8001
    mcp = FastMCP("keni-tablero", host=host, port=port)
    registrar(mcp, ClienteConsola(cfg))
    return mcp


def main() -> None:
    mcp = crear_servidor()
    if _transporte() == "http":
        mcp.run(transport="streamable-http")
    else:
        mcp.run()  # stdio (por defecto)


if __name__ == "__main__":
    main()
