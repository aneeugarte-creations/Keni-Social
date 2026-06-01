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
    """Suelta un modulo api/ temporal con un endpoint que LANZA (y lo limpia).

    El nombre del modulo y sus rutas son UNICOS por worker de xdist: la suite corre con
    `-n auto` y todos los workers comparten el dir `api/` del paquete. Con un nombre fijo
    (`zzlanza.py`), el teardown de un worker borraba el modulo que otro acababa de escribir
    -> ese otro recibia 404 en vez de 500 (flake intermitente en CI). Por eso el fichero y
    las rutas se sufijan con `PYTEST_XDIST_WORKER` y el fixture YIELDEA las rutas para que
    los tests no las hardcodeen.
    """
    import os

    dir_api = Path(api.__file__).parent
    sufijo = os.environ.get("PYTEST_XDIST_WORKER", "principal")
    nombre = f"zzlanza_{sufijo}"
    modulo = dir_api / f"{nombre}.py"
    ruta_lanza = f"/api/{nombre}"
    ruta_ok = f"/api/{nombre}_ok"
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
        f"RUTAS = [Route('{ruta_lanza}', _ep), Route('{ruta_ok}', _ok)]\n",
        encoding="utf-8",
    )
    importlib.invalidate_caches()
    api.descubrir(refresco=True)
    try:
        yield {"lanza": ruta_lanza, "ok": ruta_ok}
    finally:
        modulo.unlink(missing_ok=True)
        sys.modules.pop(f"keni_consola.api.{nombre}", None)
        api.descubrir(refresco=True)


# --------------------------------------------------------------------------- #
# (a) Manejador central de excepciones                                         #
# --------------------------------------------------------------------------- #


def test_excepcion_no_controlada_da_500_json_estandar(entorno, modulo_api_que_lanza):
    """Un endpoint que lanza -> 500 con `{"error", "tipo", "request_id"}`, sin filtrar.

    El cuerpo lleva el id de correlacion (#123): un usuario que reporta el fallo da ese
    id y casa 1:1 con la traza del servidor. `error` sigue siendo el mensaje generico y
    `tipo` el nombre de la clase; NUNCA el detalle interno ni el stack.
    """
    cliente = _cli_obs(raise_server_exceptions=False)
    r = cliente.get(modulo_api_que_lanza["lanza"])
    assert r.status_code == 500
    cuerpo = r.json()
    assert set(cuerpo) == {"error", "tipo", "request_id"}
    assert cuerpo["tipo"] == "RuntimeError"
    assert cuerpo["request_id"], "el 500 debe llevar un id de correlacion no vacio"
    # El id del cuerpo casa con la cabecera X-Request-ID de la respuesta.
    assert r.headers.get("x-request-id") == cuerpo["request_id"]
    # El mensaje al cliente es generico: NO filtra el detalle interno ni el stack.
    assert "detalle interno secreto" not in r.text
    assert "Traceback" not in r.text


def test_excepcion_no_controlada_loguea_traceback_en_servidor(
    entorno, modulo_api_que_lanza, caplog
):
    """El servidor SI registra el error con traceback (auditable en beta)."""
    cliente = _cli_obs(raise_server_exceptions=False)
    with caplog.at_level(logging.ERROR, logger=NOMBRE_LOGGER):
        cliente.get(modulo_api_que_lanza["lanza"])
    registros = [r for r in caplog.records if r.name == NOMBRE_LOGGER]
    assert registros, "se esperaba al menos un log de error del paquete"
    # El traceback (con el detalle real) vive SOLO en el log del servidor.
    texto = "\n".join(r.getMessage() + (r.exc_text or "") for r in registros)
    assert "Excepcion no controlada" in texto
    # exc_info adjunto => el detalle real esta disponible para auditar server-side.
    assert any(r.exc_info for r in registros)


def test_excepcion_loguea_y_responde_el_mismo_request_id(
    entorno, modulo_api_que_lanza, caplog
):
    """CORRELACION (#123): el id del cuerpo/cabecera 500 casa con el id del LOG.

    Un fallo se loguea UNA vez con un id de correlacion usable, y ese mismo id viaja al
    cliente: dado el id que reporta el usuario, se localiza la traza exacta del servidor.
    """
    logger_pet = f"{NOMBRE_LOGGER}.peticiones"
    cliente = _cli_obs(raise_server_exceptions=False)
    with caplog.at_level(logging.INFO):
        r = cliente.get(modulo_api_que_lanza["lanza"])
    rid = r.json()["request_id"]
    assert rid and r.headers.get("x-request-id") == rid
    # El log de ERROR del manejador central incluye ese mismo id entre corchetes.
    errores = [rec for rec in caplog.records if rec.name == NOMBRE_LOGGER and rec.levelno >= logging.ERROR]
    assert any(f"[{rid}]" in rec.getMessage() for rec in errores), (
        "el log del 500 debe llevar el mismo request_id que la respuesta"
    )
    # La linea del middleware de peticiones tambien lleva el id (correlacion de punta a punta).
    lineas_pet = [rec.getMessage() for rec in caplog.records if rec.name == logger_pet]
    assert any(f"[{rid}]" in linea for linea in lineas_pet)


def test_endpoint_que_no_lanza_no_se_ve_afectado(entorno, modulo_api_que_lanza):
    """El manejador es aditivo: un endpoint normal responde como siempre."""
    cliente = _cli_obs()
    r = cliente.get(modulo_api_que_lanza["ok"])
    assert r.status_code == 200
    assert r.json() == {"ok": True}


# --------------------------------------------------------------------------- #
# (b) Middleware de registro de peticiones                                     #
# --------------------------------------------------------------------------- #


def test_middleware_loguea_una_linea_por_peticion(cliente, caplog):
    """Una peticion produce una linea con id de correlacion, metodo, ruta, estado y ms."""
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
    # El id de correlacion va entre corchetes al inicio y casa con la cabecera.
    rid = r.headers.get("x-request-id")
    assert rid, "la respuesta debe llevar la cabecera X-Request-ID"
    assert f"[{rid}]" in linea


def test_request_id_en_estado_de_la_peticion(entorno, modulo_api_que_lanza):
    """El middleware deja el id en `request.state.request_id` (lo leen los handlers)."""
    import importlib

    # Endpoint que DEVUELVE el request_id que ve en request.state (prueba la disponibilidad).
    dir_api = Path(api.__file__).parent
    modulo = dir_api / "zzrid.py"
    modulo.write_text(
        "from starlette.responses import JSONResponse\n"
        "from starlette.routing import Route\n"
        "async def _ep(request):\n"
        "    return JSONResponse({'visto': getattr(request.state, 'request_id', None)})\n"
        "RUTAS = [Route('/api/zzrid', _ep)]\n",
        encoding="utf-8",
    )
    importlib.invalidate_caches()
    api.descubrir(refresco=True)
    try:
        cliente = _cli_obs()
        r = cliente.get("/api/zzrid")
        assert r.status_code == 200
        assert r.json()["visto"] == r.headers.get("x-request-id")
    finally:
        modulo.unlink(missing_ok=True)
        sys.modules.pop("keni_consola.api.zzrid", None)
        api.descubrir(refresco=True)


def test_request_id_entrante_se_reusa(cliente):
    """Si el cliente/proxy manda X-Request-ID, se reusa (encadena trazas)."""
    r = cliente.get("/api/estado", headers={"X-Request-ID": "trace-abc123"})
    assert r.headers.get("x-request-id") == "trace-abc123"


def test_request_id_entrante_invalido_se_sustituye(cliente):
    """Un X-Request-ID con caracteres raros se descarta y se genera uno limpio."""
    r = cliente.get("/api/estado", headers={"X-Request-ID": "no validos!! <script>"})
    rid = r.headers.get("x-request-id")
    assert rid and all(c.isalnum() or c in "-_" for c in rid)
    assert "<" not in rid and " " not in rid


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
    """`error()` devuelve `{"error": <mensaje>}` con el status pedido (def 400).

    FUERA de una peticion (sin id de correlacion en contexto) no añade `request_id`:
    la forma minima es identica a las ~250 respuestas en linea que reemplaza.
    """
    import json

    r = error("Falta la marca.")
    assert r.status_code == 400
    assert json.loads(bytes(r.body)) == {"error": "Falta la marca."}

    r2 = error("No encontrado.", status=404)
    assert r2.status_code == 404
    assert json.loads(bytes(r2.body)) == {"error": "No encontrado."}


def test_error_helper_incluye_request_id_en_contexto():
    """DENTRO de una peticion, `error()` añade el id de correlacion (clave aditiva)."""
    import json

    from keni_consola.observabilidad import fijar_request_id, restaurar_request_id

    token = fijar_request_id("rid-de-prueba")
    try:
        cuerpo = json.loads(bytes(error("Falta la marca.").body))
    finally:
        restaurar_request_id(token)
    assert cuerpo == {"error": "Falta la marca.", "request_id": "rid-de-prueba"}


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
