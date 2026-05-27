"""Selección de transporte en server.main() según KENI_MCP_TRANSPORT.

No se vincula ningún puerto real: se parchea FastMCP.run para capturar cómo se
invoca, y crear_servidor para no tocar config/red.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

import keni_metricas.server as server
from keni_metricas.fuentes.muestra import FuenteMuestra


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


# --- registro real de las 8 tools ------------------------------------------

TOOLS_ESPERADAS = {
    "listar_cuentas",
    "metricas_resumen",
    "mejores_piezas",
    "comparar_periodos",
    "tendencia_historica",
    "reporte_consolidado",
    "picos",
    "analisis_diario",
}


def _tools_registradas(mcp) -> set[str]:
    """Nombres de las tools registradas en un FastMCP (API async list_tools)."""
    import asyncio

    return {t.name for t in asyncio.run(mcp.list_tools())}


def test_crear_servidor_registra_las_ocho_tools(monkeypatch):
    """crear_servidor construye un FastMCP REAL con las 8 tools registradas.

    No se parchea `registrar`: se verifica el efecto observable (las tools
    quedan disponibles). Se usa la fuente de muestra para no tocar red/credenciales.
    """
    monkeypatch.delenv("KENI_MCP_TRANSPORT", raising=False)
    with (
        patch.object(server, "construir_fuente", return_value=FuenteMuestra()),
        patch.object(server, "cargar_config", return_value=MagicMock()),
        patch.object(server, "historico_activo", return_value=False),
    ):
        mcp = server.crear_servidor()

    assert _tools_registradas(mcp) == TOOLS_ESPERADAS


def test_crear_servidor_registra_tools_con_historico_activo(monkeypatch):
    """Con historico activo se siguen registrando las mismas 8 tools."""
    monkeypatch.delenv("KENI_MCP_TRANSPORT", raising=False)
    with (
        patch.object(server, "construir_fuente", return_value=FuenteMuestra()),
        patch.object(server, "cargar_config", return_value=MagicMock()),
        patch.object(server, "historico_activo", return_value=True),
        patch.object(server, "Historico", return_value=MagicMock()),
    ):
        mcp = server.crear_servidor()

    assert _tools_registradas(mcp) == TOOLS_ESPERADAS


def test_main_construye_servidor_real_y_arranca_stdio(monkeypatch):
    """main() en stdio: construye el servidor REAL (8 tools) y llama run() sin args.

    Se parchea solo el arranque del transporte (FastMCP.run) para no abrir stdio,
    pero NO se parchea la construccion: se observa que el servidor real queda con
    las 8 tools antes de arrancar.
    """
    monkeypatch.delenv("KENI_MCP_TRANSPORT", raising=False)
    capturado = {}

    def _run(self, *a, **k):
        capturado["args"] = a
        capturado["kwargs"] = k
        capturado["tools"] = _tools_registradas(self)

    with (
        patch.object(server, "construir_fuente", return_value=FuenteMuestra()),
        patch.object(server, "cargar_config", return_value=MagicMock()),
        patch.object(server, "historico_activo", return_value=False),
        patch.object(server.FastMCP, "run", _run),
    ):
        server.main()

    assert capturado["args"] == ()
    assert capturado["kwargs"] == {}
    assert capturado["tools"] == TOOLS_ESPERADAS


def test_main_http_construye_servidor_real_streamable(monkeypatch):
    """main() en HTTP: construye el servidor REAL y arranca streamable-http."""
    monkeypatch.setenv("KENI_MCP_TRANSPORT", "http")
    capturado = {}

    def _run(self, *a, **k):
        capturado["kwargs"] = k
        capturado["tools"] = _tools_registradas(self)

    with (
        patch.object(server, "construir_fuente", return_value=FuenteMuestra()),
        patch.object(server, "cargar_config", return_value=MagicMock()),
        patch.object(server, "historico_activo", return_value=False),
        patch.object(server.FastMCP, "run", _run),
    ):
        server.main()

    assert capturado["kwargs"] == {"transport": "streamable-http"}
    assert capturado["tools"] == TOOLS_ESPERADAS


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


def test_log_a_archivo_ruta_inaccesible_no_tumba_arranque(monkeypatch, tmp_path, caplog):
    """Si abrir el archivo de log falla (OSError), se avisa y NO se tumba el arranque."""
    ruta = tmp_path / "metricas.log"
    monkeypatch.setenv("KENI_METRICAS_LOG", str(ruta))
    _limpiar_handlers_archivo()

    def _falla(*a, **k):
        raise OSError("permiso denegado (simulado)")

    try:
        with (
            patch.object(logging, "FileHandler", _falla),
            caplog.at_level(logging.WARNING, logger="keni_metricas"),
        ):
            # no debe propagar la excepcion
            server._configurar_logging()
        log = logging.getLogger("keni_metricas")
        # no quedo ningun FileHandler colgado
        assert not any(isinstance(h, logging.FileHandler) for h in log.handlers)
        # se emitio un aviso (sin afirmar el texto exacto)
        assert any(r.levelno == logging.WARNING for r in caplog.records)
    finally:
        _limpiar_handlers_archivo()


@pytest.mark.parametrize("valor", ["", "   "])
def test_log_a_archivo_env_vacia_no_activa(monkeypatch, valor):
    """KENI_METRICAS_LOG vacia o con solo espacios no activa el handler de archivo."""
    monkeypatch.setenv("KENI_METRICAS_LOG", valor)
    _limpiar_handlers_archivo()
    server._configurar_logging()
    log = logging.getLogger("keni_metricas")
    assert not any(isinstance(h, logging.FileHandler) for h in log.handlers)
