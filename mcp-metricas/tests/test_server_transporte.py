"""Selección de transporte en server.main() según KENI_MCP_TRANSPORT.

No se vincula ningún puerto real: se parchea FastMCP.run para capturar cómo se
invoca, y crear_servidor para no tocar config/red.
"""

from __future__ import annotations

import logging
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


# --- Logging opcional a archivo (KENI_METRICAS_LOG) -------------------------


def _limpiar_handlers_archivo() -> None:
    log = logging.getLogger("keni_metricas")
    for h in list(log.handlers):
        if isinstance(h, logging.FileHandler):
            log.removeHandler(h)
            h.close()


def test_log_a_archivo_desactivado_por_defecto(monkeypatch):
    monkeypatch.delenv("KENI_METRICAS_LOG", raising=False)
    _limpiar_handlers_archivo()
    server._configurar_logging()
    log = logging.getLogger("keni_metricas")
    assert not any(isinstance(h, logging.FileHandler) for h in log.handlers)


def test_log_a_archivo_activado_por_env(monkeypatch, tmp_path):
    ruta = tmp_path / "sub" / "metricas.log"  # el dir padre no existe aun
    monkeypatch.setenv("KENI_METRICAS_LOG", str(ruta))
    _limpiar_handlers_archivo()
    try:
        server._configurar_logging()
        log = logging.getLogger("keni_metricas")
        handlers = [h for h in log.handlers if isinstance(h, logging.FileHandler)]
        assert len(handlers) == 1
        log.warning("aviso de prueba %s", "sin-secreto")
        handlers[0].flush()
        contenido = ruta.read_text(encoding="utf-8")
        assert "aviso de prueba sin-secreto" in contenido
        # idempotente: segunda llamada no duplica el handler
        server._configurar_logging()
        assert len([h for h in log.handlers if isinstance(h, logging.FileHandler)]) == 1
    finally:
        _limpiar_handlers_archivo()
