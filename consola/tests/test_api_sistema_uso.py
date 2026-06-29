"""Tests del endpoint de LECTURA del uso de la cuenta (`GET /api/sistema/uso`). Panel ADMIN.

Cubre el cerrojo de rol (solo admin) y la FORMA del contrato en los casos clave del indicador:
sin snapshot (cold start -> desconectada, `alerta_roja`), al 100% semanal (`al_100` + `alerta_roja`)
y operación normal (sin alerta). El endpoint solo LEE la tabla (no ejecuta `claude`): se siembra
con `repos.guardar_uso_cuenta`.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth, repos

from .conftest import TOKEN_PRUEBA

_ORIGIN = {"Origin": "http://testserver"}
CLAVE = "clave-de-prueba"

_FORMA = {
    "conectada", "semana_pct", "sesion_5h_pct", "sonnet_pct",
    "reset_semana_iso", "reset_semana_txt", "actualizado_ts", "al_100", "alerta_roja",
}


def _cli() -> TestClient:
    return TestClient(app_modulo.crear_app(token=TOKEN_PRUEBA))


def _cli_como(rol: str) -> TestClient:
    auth.crear_usuario("u", CLAVE, rol)
    c = _cli()
    assert c.post(
        "/api/auth/login", json={"usuario": "u", "password": CLAVE}, headers=_ORIGIN
    ).status_code == 200
    return c


# --- Permisos: solo admin -------------------------------------------------- #


def test_editor_no_ve_uso_403(entorno):
    assert _cli_como("editor").get("/api/sistema/uso").status_code == 403


def test_token_mantenimiento_no_es_admin_403(entorno):
    c = _cli()
    c.headers.update({"Authorization": f"Bearer {TOKEN_PRUEBA}"})
    assert c.get("/api/sistema/uso").status_code == 403


# --- Forma + alerta_roja --------------------------------------------------- #


def test_sin_cuenta_alerta_roja(entorno):
    # Cold start: nunca se muestreó -> desconectada, pcts nulos, alerta_roja por desconexión.
    r = _cli_como("admin").get("/api/sistema/uso")
    assert r.status_code == 200
    cuerpo = r.json()
    assert set(cuerpo) == _FORMA
    assert cuerpo["conectada"] is False
    assert cuerpo["semana_pct"] is None
    assert cuerpo["al_100"] is False
    assert cuerpo["alerta_roja"] is True


def test_semana_al_100_alerta_roja(entorno):
    repos.guardar_uso_cuenta(
        conectada=True, semana_pct=100, sesion_5h_pct=40, sonnet_pct=12,
        reset_semana_iso="2026-07-01T07:00:00Z", reset_semana_txt="Jul 1, 7am (UTC)",
        actualizado_ts=1750000000.0, dia_utc="2026-06-14",
    )
    cuerpo = _cli_como("admin").get("/api/sistema/uso").json()
    assert cuerpo["conectada"] is True
    assert cuerpo["semana_pct"] == 100
    assert cuerpo["al_100"] is True
    assert cuerpo["alerta_roja"] is True
    assert cuerpo["reset_semana_iso"] == "2026-07-01T07:00:00Z"


def test_operacion_normal_sin_alerta(entorno):
    repos.guardar_uso_cuenta(
        conectada=True, semana_pct=42, sesion_5h_pct=10, sonnet_pct=3,
        actualizado_ts=1750000000.0, dia_utc="2026-06-14",
    )
    cuerpo = _cli_como("admin").get("/api/sistema/uso").json()
    assert cuerpo["conectada"] is True
    assert cuerpo["semana_pct"] == 42
    assert cuerpo["al_100"] is False
    assert cuerpo["alerta_roja"] is False
    # resets vacíos se normalizan a null.
    assert cuerpo["reset_semana_iso"] is None
    assert cuerpo["reset_semana_txt"] is None
