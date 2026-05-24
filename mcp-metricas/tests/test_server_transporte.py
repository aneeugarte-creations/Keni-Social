"""Selección de transporte en server.main() según KENI_MCP_TRANSPORT.

No se vincula ningún puerto real: se parchea FastMCP.run para capturar cómo se
invoca, y crear_servidor para no tocar config/red.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import keni_metricas.server as server


def _servidor_falso() -> MagicMock:
    mcp = MagicMock()
    return mcp


def test_transporte_por_defecto_es_stdio(monkeypatch):
    monkeypatch.delenv("KENI_MCP_TRANSPORT", raising=False)
    assert server._transporte() == "stdio"


def test_transporte_http_desde_entorno(monkeypatch):
    monkeypatch.setenv("KENI_MCP_TRANSPORT", "HTTP")  # se normaliza
    assert server._transporte() == "http"


def test_main_stdio_usa_run_sin_args(monkeypatch):
    monkeypatch.delenv("KENI_MCP_TRANSPORT", raising=False)
    mcp = _servidor_falso()
    with patch.object(server, "crear_servidor", return_value=mcp):
        server.main()
    mcp.run.assert_called_once_with()  # stdio: run() sin transporte


def test_main_http_usa_streamable_http(monkeypatch):
    monkeypatch.setenv("KENI_MCP_TRANSPORT", "http")
    mcp = _servidor_falso()
    with patch.object(server, "crear_servidor", return_value=mcp):
        server.main()
    mcp.run.assert_called_once_with(transport="streamable-http")


def test_crear_servidor_fija_host_y_puerto(monkeypatch):
    monkeypatch.setenv("KENI_MCP_HOST", "0.0.0.0")
    monkeypatch.setenv("KENI_MCP_PORT", "9123")
    capturado = {}

    class FakeFastMCP:
        def __init__(self, name, host="127.0.0.1", port=8000):
            capturado["name"] = name
            capturado["host"] = host
            capturado["port"] = port

    with (
        patch.object(server, "FastMCP", FakeFastMCP),
        patch.object(server, "construir_fuente", return_value=MagicMock()),
        patch.object(server, "cargar_config", return_value=MagicMock()),
        patch.object(server, "historico_activo", return_value=False),
        patch.object(server, "registrar"),
    ):
        server.crear_servidor()

    assert capturado["host"] == "0.0.0.0"
    assert capturado["port"] == 9123


def test_crear_servidor_puerto_invalido_cae_a_8000(monkeypatch):
    monkeypatch.delenv("KENI_MCP_HOST", raising=False)
    monkeypatch.setenv("KENI_MCP_PORT", "no-es-numero")
    capturado = {}

    class FakeFastMCP:
        def __init__(self, name, host="127.0.0.1", port=8000):
            capturado["host"] = host
            capturado["port"] = port

    with (
        patch.object(server, "FastMCP", FakeFastMCP),
        patch.object(server, "construir_fuente", return_value=MagicMock()),
        patch.object(server, "cargar_config", return_value=MagicMock()),
        patch.object(server, "historico_activo", return_value=False),
        patch.object(server, "registrar"),
    ):
        server.crear_servidor()

    assert capturado["host"] == "127.0.0.1"
    assert capturado["port"] == 8000  # fallback ante valor inválido
