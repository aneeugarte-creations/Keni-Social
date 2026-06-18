"""Tests de la PROMOCIÓN a main (`POST /api/sugerencias/{id}/promover`). Panel ADMIN.

Cubre el cerrojo de rol (solo admin; editor/token -> 403), el gate de estado (`revision`), la
DEGRADACIÓN cuando worker-dev no responde y el REENVÍO al listener de promoción (parcheando
`_llamar_dev`, sin red real ni git). Usa el fixture `entorno` (Postgres) para las sesiones y el
kanban, como el resto de tests de `/api/sistema`.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth, sugerencias
from keni_consola.api import sugerencias as api_sugerencias

from .conftest import TOKEN_PRUEBA

_ORIGIN = {"Origin": "http://testserver"}
CLAVE = "clave-de-prueba"


def _cli() -> TestClient:
    return TestClient(app_modulo.crear_app(token=TOKEN_PRUEBA))


def _cli_como(rol: str) -> TestClient:
    auth.crear_usuario("u", CLAVE, rol)
    c = _cli()
    assert c.post(
        "/api/auth/login", json={"usuario": "u", "password": CLAVE}, headers=_ORIGIN
    ).status_code == 200
    return c


def _cli_token() -> TestClient:
    c = _cli()
    c.headers.update({"Authorization": f"Bearer {TOKEN_PRUEBA}"})
    return c


def _en_revision(titulo: str = "Promovible") -> str:
    """Crea una sugerencia y la lleva hasta `revision` (lista para promover)."""
    s = sugerencias.crear(titulo)
    sugerencias.cambiar_estado(s["id"], "en_cola", campos={"complejidad": "simple"})
    sugerencias.cambiar_estado(s["id"], "building", campos={"fase": "review", "rama": f"dev/sug-{s['id']}"})
    sugerencias.cambiar_estado(s["id"], "revision")
    return s["id"]


# --- Permisos: solo admin -------------------------------------------------- #


def test_editor_no_promueve_403(entorno):
    sid = _en_revision()
    assert _cli_como("editor").post(f"/api/sugerencias/{sid}/promover", json={}, headers=_ORIGIN).status_code == 403


def test_token_mantenimiento_no_promueve_403(entorno):
    sid = _en_revision()
    r = _cli_token().post(f"/api/sugerencias/{sid}/promover", json={}, headers=_ORIGIN)
    assert r.status_code == 403


# --- Gate de estado / existencia (admin) ----------------------------------- #


def test_promover_desde_estado_invalido_400(entorno):
    s = sugerencias.crear("Idea")  # nace en `nueva`: no promovible
    r = _cli_como("admin").post(f"/api/sugerencias/{s['id']}/promover", json={}, headers=_ORIGIN)
    assert r.status_code == 400
    assert r.json()["ok"] is False


def test_promover_inexistente_404(entorno):
    r = _cli_como("admin").post("/api/sugerencias/nope/promover", json={}, headers=_ORIGIN)
    assert r.status_code == 404


# --- Degradación: worker-dev NO contactable -------------------------------- #


def test_promover_worker_dev_caido_degrada(entorno, monkeypatch):
    sid = _en_revision()
    monkeypatch.setattr(
        api_sugerencias, "_llamar_dev",
        lambda metodo, ruta, json=None: (502, {"ok": False, "detalle": "No se pudo contactar worker-dev para promover."}),
    )
    r = _cli_como("admin").post(f"/api/sugerencias/{sid}/promover", json={}, headers=_ORIGIN)
    assert r.status_code == 502
    assert r.json()["ok"] is False
    # No mueve el kanban: sigue en revision.
    assert sugerencias.obtener(sid)["estado"] == "revision"


# --- Reenvío al listener (parcheado): push OK -> hecha ---------------------- #


def test_promover_ok_marca_hecha(entorno, monkeypatch):
    sid = _en_revision()
    capturado: dict = {}

    def _fake(metodo, ruta, json=None):
        capturado["ruta"] = ruta
        capturado["json"] = json
        return 200, {"ok": True, "detalle": "Rama «dev/sug-x» promovida a main.", "rama": "dev/sug-x"}

    monkeypatch.setattr(api_sugerencias, "_llamar_dev", _fake)
    r = _cli_como("admin").post(f"/api/sugerencias/{sid}/promover", json={}, headers=_ORIGIN)
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["ok"] is True
    assert cuerpo["rama"] == "dev/sug-x"
    assert capturado["ruta"] == "/control/dev/promover"
    assert capturado["json"] == {"sugerencia_id": sid}
    # Tras el push real, el kanban queda en `hecha`.
    assert sugerencias.obtener(sid)["estado"] == "hecha"
