"""Punto de entrada del servidor MCP `keni-metricas`.

Transporte seleccionable por entorno:

- `KENI_MCP_TRANSPORT=stdio` (por defecto): JSON-RPC sobre stdio. Modo local
  por persona (cada quien con sus credenciales). stdout es el canal JSON-RPC,
  por eso el logging va SIEMPRE a stderr.
- `KENI_MCP_TRANSPORT=http`: streamable-HTTP. Mitad "hosted" de la arquitectura
  hibrida: Keni hospeda el MCP de metricas con tokens System User (no caducan).
  Host/puerto por entorno (`KENI_MCP_HOST` def. `127.0.0.1`, `KENI_MCP_PORT`
  def. `8000`). Ver docs/despliegue-hosted.md.
"""

from __future__ import annotations

import logging
import os

from mcp.server.fastmcp import FastMCP

from .config import cargar_config, construir_fuente
from .historico import Historico, historico_activo
from .tools import registrar


def _transporte() -> str:
    """Transporte activo, normalizado: `stdio` (def.) | `http`."""
    return (os.environ.get("KENI_MCP_TRANSPORT") or "stdio").strip().lower()


def crear_servidor() -> FastMCP:
    # logging a stderr (NUNCA stdout: stdout es el canal JSON-RPC del MCP)
    logging.basicConfig(level=logging.WARNING)
    fuente = construir_fuente(cargar_config())
    historico = Historico() if historico_activo() else None
    # En HTTP, host/puerto se fijan en la construccion del servidor (FastMCP los
    # lee de sus Settings, no del .run()).
    host = os.environ.get("KENI_MCP_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("KENI_MCP_PORT", "8000"))
    except ValueError:
        port = 8000
    mcp = FastMCP("keni-metricas", host=host, port=port)
    registrar(mcp, fuente, historico)
    return mcp


def main() -> None:
    mcp = crear_servidor()
    if _transporte() == "http":
        # streamable-HTTP: la pila ASGI (uvicorn/starlette) viene incluida con
        # el SDK `mcp`; no requiere dependencias extra. El endpoint MCP queda en
        # `/mcp`. La autenticacion bearer se resuelve por delante (reverse proxy)
        # o configurando `auth`/`token_verifier`; ver docs/despliegue-hosted.md.
        mcp.run(transport="streamable-http")
    else:
        mcp.run()  # stdio (por defecto)


if __name__ == "__main__":
    main()
