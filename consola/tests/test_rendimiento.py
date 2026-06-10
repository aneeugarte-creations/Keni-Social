"""Tests del agregador de latencias `rendimiento.py` y su endpoint del panel Sistema.

El agregador es EN MEMORIA y best-effort: normaliza rutas (ids colapsados), mantiene una
ventana deslizante por ruta y calcula percentiles. El endpoint es solo-admin y sirve el
snapshot tal cual. El registro real lo hace `RegistroPeticiones` en cada peticion, asi
que el test del endpoint tambien cubre la integracion (las propias llamadas del test
aparecen en el resumen).
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth, rendimiento

from .conftest import TOKEN_PRUEBA

_ORIGIN = {"Origin": "http://testserver"}
CLAVE = "clave-de-prueba"


@pytest.fixture(autouse=True)
def _agregador_limpio():
    rendimiento.reiniciar()
    yield
    rendimiento.reiniciar()


# --------------------------------------------------------------------------- #
# Normalizacion de rutas                                                       #
# --------------------------------------------------------------------------- #


def test_normalizar_colapsa_ids():
    assert rendimiento.normalizar_ruta("/api/contenido/0a1b2c3d4e5f") == "/api/contenido/{id}"
    assert rendimiento.normalizar_ruta("/api/piezas/12345/comentarios") == "/api/piezas/{id}/comentarios"
    assert (
        rendimiento.normalizar_ruta(
            "/api/x/123e4567-e89b-12d3-a456-426614174000"
        )
        == "/api/x/{id}"
    )


def test_normalizar_respeta_segmentos_de_verbo():
    assert rendimiento.normalizar_ruta("/api/sistema/recursos") == "/api/sistema/recursos"
    assert rendimiento.normalizar_ruta("/healthz") == "/healthz"


# --------------------------------------------------------------------------- #
# Registro + resumen                                                           #
# --------------------------------------------------------------------------- #


def test_registrar_y_percentiles():
    for ms in [10.0, 20.0, 30.0, 40.0, 100.0]:
        rendimiento.registrar("GET", "/api/x", 200, ms)
    rendimiento.registrar("GET", "/api/x", 500, 999.0)
    (fila,) = [f for f in rendimiento.resumen()["rutas"] if f["ruta"] == "GET /api/x"]
    assert fila["n"] == 6
    assert fila["err_5xx"] == 1
    assert fila["max_ms"] == 999.0
    assert fila["ultimo_ms"] == 999.0
    assert 20.0 <= fila["p50_ms"] <= 40.0
    assert fila["p95_ms"] >= 100.0


def test_ventana_deslizante_acotada():
    for i in range(1000):
        rendimiento.registrar("GET", "/api/y", 200, float(i))
    (fila,) = [f for f in rendimiento.resumen()["rutas"] if f["ruta"] == "GET /api/y"]
    assert fila["n"] == 1000  # contador total
    # Percentiles solo sobre la ventana (las ultimas 256): el p50 queda en la cola alta.
    assert fila["p50_ms"] > 700


def test_tope_de_rutas_desborda_a_otras():
    for i in range(rendimiento._MAX_RUTAS + 10):
        rendimiento.registrar("GET", f"/api/ruta-{chr(97 + i % 26)}{i}", 200, 1.0)
    resumen = rendimiento.resumen()
    assert len(resumen["rutas"]) <= rendimiento._MAX_RUTAS + 1
    assert any(f["ruta"] == "(otras)" for f in resumen["rutas"])


def test_registrar_jamas_lanza():
    rendimiento.registrar(None, None, None, None)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Endpoint /api/sistema/rendimiento (integra RegistroPeticiones)               #
# --------------------------------------------------------------------------- #


def test_endpoint_contrato_e_integracion(entorno):
    auth.crear_usuario("u", CLAVE, "admin")
    c = TestClient(app_modulo.crear_app(token=TOKEN_PRUEBA))
    assert (
        c.post(
            "/api/auth/login", json={"usuario": "u", "password": CLAVE}, headers=_ORIGIN
        ).status_code
        == 200
    )
    c.get("/healthz")
    r = c.get("/api/sistema/rendimiento")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["desde"]
    rutas = {f["ruta"] for f in cuerpo["rutas"]}
    # Las peticiones de ESTE test ya pasaron por RegistroPeticiones -> aparecen aqui.
    assert "GET /healthz" in rutas
    assert "POST /api/auth/login" in rutas


def test_endpoint_editor_403(entorno):
    auth.crear_usuario("e", CLAVE, "editor")
    c = TestClient(app_modulo.crear_app(token=TOKEN_PRUEBA))
    assert (
        c.post(
            "/api/auth/login", json={"usuario": "e", "password": CLAVE}, headers=_ORIGIN
        ).status_code
        == 200
    )
    assert c.get("/api/sistema/rendimiento").status_code == 403
