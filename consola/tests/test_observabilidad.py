"""Tests del nucleo de observabilidad (issue #123).

Cubre:
  (a) el manejador central convierte una `Exception` no controlada en la forma JSON
      estandar `{"error", "tipo"}` con status 500, SIN filtrar el mensaje/stack real;
  (b) el middleware de peticiones loguea UNA linea con metodo, ruta, estado y ms,
      y NO incluye la query string (privacidad);
  (c) el helper `error()` devuelve la forma de error estandar del proyecto.

Reusa el catalogo de skills falso y el aislamiento en tmp via la fixture `entorno`.
Para ejercitar el manejador montamos un modulo de api temporal que LANZA (mismo
patron `zz...` que usa test_app.py), y un TestClient con raise_server_exceptions=False
para poder leer la respuesta 500 (en vez de re-lanzar la excepcion).
"""

from __future__ import annotations

import importlib
import logging
import sys
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from keni_consola import api
from keni_consola import app as app_modulo
from keni_consola.observabilidad import (
    ENV_NIVEL,
    NOMBRE_LOGGER,
    configurar_logging,
    error,
)

from .conftest import TOKEN_PRUEBA


def _cli_obs(**kwargs) -> TestClient:
    """TestClient con token de sesion (#134) fijo + auth por defecto, igual que conftest."""
    return TestClient(
        app_modulo.crear_app(token=TOKEN_PRUEBA),
        headers={"Authorization": f"Bearer {TOKEN_PRUEBA}"},
        **kwargs,
    )


@pytest.fixture
def modulo_api_que_lanza():
    """Suelta un modulo api/ temporal con un endpoint que LANZA (y lo limpia)."""
    dir_api = Path(api.__file__).parent
    modulo = dir_api / "zzlanza.py"
    modulo.write_text(
        "from starlette.responses import JSONResponse\n"
        "from starlette.routing import Route\n"
        "\n"
        "async def _ep(request):\n"
        "    raise RuntimeError('detalle interno secreto que NO debe filtrarse')\n"
        "\n"
        "async def _ok(request):\n"
        "    return JSONResponse({'ok': True})\n"
        "\n"
        "RUTAS = [Route('/api/zzlanza', _ep), Route('/api/zzok', _ok)]\n",
        encoding="utf-8",
    )
    importlib.invalidate_caches()
    api.descubrir(refresco=True)
    try:
        yield
    finally:
        modulo.unlink(missing_ok=True)
        sys.modules.pop("keni_consola.api.zzlanza", None)
        api.descubrir(refresco=True)


# --------------------------------------------------------------------------- #
# (a) Manejador central de excepciones                                         #
# --------------------------------------------------------------------------- #


def test_excepcion_no_controlada_da_500_json_estandar(entorno, modulo_api_que_lanza):
    """Un endpoint que lanza -> 500 con `{"error", "tipo"}`, sin filtrar el detalle."""
    cliente = _cli_obs(raise_server_exceptions=False)
    r = cliente.get("/api/zzlanza")
    assert r.status_code == 500
    cuerpo = r.json()
    assert set(cuerpo) == {"error", "tipo"}
    assert cuerpo["tipo"] == "RuntimeError"
    # El mensaje al cliente es generico: NO filtra el detalle interno ni el stack.
    assert "detalle interno secreto" not in r.text
    assert "Traceback" not in r.text


def test_excepcion_no_controlada_loguea_traceback_en_servidor(
    entorno, modulo_api_que_lanza, caplog
):
    """El servidor SI registra el error con traceback (auditable en beta)."""
    cliente = _cli_obs(raise_server_exceptions=False)
    with caplog.at_level(logging.ERROR, logger=NOMBRE_LOGGER):
        cliente.get("/api/zzlanza")
    registros = [r for r in caplog.records if r.name == NOMBRE_LOGGER]
    assert registros, "se esperaba al menos un log de error del paquete"
    # El traceback (con el detalle real) vive SOLO en el log del servidor.
    texto = "\n".join(r.getMessage() + (r.exc_text or "") for r in registros)
    assert "Excepcion no controlada" in texto
    # exc_info adjunto => el detalle real esta disponible para auditar server-side.
    assert any(r.exc_info for r in registros)


def test_endpoint_que_no_lanza_no_se_ve_afectado(entorno, modulo_api_que_lanza):
    """El manejador es aditivo: un endpoint normal responde como siempre."""
    cliente = _cli_obs()
    r = cliente.get("/api/zzok")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


# --------------------------------------------------------------------------- #
# (b) Middleware de registro de peticiones                                     #
# --------------------------------------------------------------------------- #


def test_middleware_loguea_una_linea_por_peticion(cliente, caplog):
    """Una peticion produce una linea con metodo, ruta, estado y duracion en ms."""
    logger_pet = f"{NOMBRE_LOGGER}.peticiones"
    with caplog.at_level(logging.INFO, logger=logger_pet):
        r = cliente.get("/api/estado")
    assert r.status_code == 200
    lineas = [rec.getMessage() for rec in caplog.records if rec.name == logger_pet]
    assert lineas, "el middleware deberia loguear al menos una linea"
    linea = lineas[-1]
    assert "GET" in linea
    assert "/api/estado" in linea
    assert "200" in linea
    assert "ms" in linea


def test_middleware_no_loguea_la_query_string(cliente, caplog):
    """PRIVACIDAD: la query string (posible secreto) NO aparece en el log."""
    logger_pet = f"{NOMBRE_LOGGER}.peticiones"
    with caplog.at_level(logging.INFO, logger=logger_pet):
        cliente.get("/api/estado?token=supersecreto123")
    lineas = [rec.getMessage() for rec in caplog.records if rec.name == logger_pet]
    assert lineas
    todo = "\n".join(lineas)
    assert "supersecreto123" not in todo
    assert "token" not in todo
    # La ruta (sin query) si esta presente.
    assert "/api/estado" in todo


# --------------------------------------------------------------------------- #
# (c) Helper error()                                                           #
# --------------------------------------------------------------------------- #


def test_error_helper_forma_estandar():
    """`error()` devuelve `{"error": <mensaje>}` con el status pedido (def 400)."""
    import json

    r = error("Falta la marca.")
    assert r.status_code == 400
    assert json.loads(bytes(r.body)) == {"error": "Falta la marca."}

    r2 = error("No encontrado.", status=404)
    assert r2.status_code == 404
    assert json.loads(bytes(r2.body)) == {"error": "No encontrado."}


# --------------------------------------------------------------------------- #
# configurar_logging() + nivel por env var                                     #
# --------------------------------------------------------------------------- #


def test_configurar_logging_respeta_env(monkeypatch):
    """`KENI_CONSOLA_LOG_LEVEL` fija el nivel; un valor invalido cae a INFO."""
    monkeypatch.setenv(ENV_NIVEL, "DEBUG")
    logger = configurar_logging()
    assert logger.level == logging.DEBUG

    monkeypatch.setenv(ENV_NIVEL, "valor-invalido")
    logger = configurar_logging()
    assert logger.level == logging.INFO
