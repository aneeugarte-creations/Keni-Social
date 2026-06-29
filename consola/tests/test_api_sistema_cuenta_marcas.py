"""Tests del reparto de MARCAS por cuenta de Claude (`/api/sistema/cuenta-marcas`).

Solo admin/superadmin lo leen y editan (gobierna el gasto de toda la operación); editor y token de
mantenimiento -> 403. Cubre la FORMA del mapa, mover una marca a la otra cuenta y limpiar el
override (vuelve a su reparto por defecto). El override se persiste en el store aislado del test.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth

from .conftest import TOKEN_PRUEBA

_ORIGIN = {"Origin": "http://testserver"}
CLAVE = "clave-de-prueba"


def _cli() -> TestClient:
    return TestClient(app_modulo.crear_app(token=TOKEN_PRUEBA))


def _cli_como(rol: str, *, superadmin: bool = False) -> TestClient:
    auth.crear_usuario("u", CLAVE, rol, superadmin=superadmin)
    c = _cli()
    assert c.post(
        "/api/auth/login", json={"usuario": "u", "password": CLAVE}, headers=_ORIGIN
    ).status_code == 200
    return c


def _marcas(cuerpo: dict) -> dict:
    """Indexa el mapa `{marcas:[...]}` por id de marca."""
    return {m["id"]: m for m in cuerpo["marcas"]}


# --- Acotamiento por rol --------------------------------------------------- #


def test_editor_no_puede_ver_el_reparto(entorno):
    assert _cli_como("editor").get("/api/sistema/cuenta-marcas").status_code == 403


def test_token_mantenimiento_no_puede_ver_el_reparto(entorno):
    c = _cli()
    c.headers.update({"Authorization": f"Bearer {TOKEN_PRUEBA}"})
    assert c.get("/api/sistema/cuenta-marcas").status_code == 403


# --- Lectura del mapa ------------------------------------------------------- #


def test_admin_ve_el_mapa_por_defecto(entorno):
    r = _cli_como("admin").get("/api/sistema/cuenta-marcas")
    assert r.status_code == 200
    cuerpo = r.json()
    assert [c["cuenta"] for c in cuerpo["cuentas"]] == ["a", "b"]
    assert cuerpo["defecto"] == "a"
    marcas = _marcas(cuerpo)
    # Reparto por defecto del piloto, y todas heredadas (sin override).
    assert marcas["claro-sports"]["cuenta"] == "a"
    assert marcas["unotv"]["cuenta"] == "b"
    assert marcas["unotv"]["por_defecto"] is True
    assert set(marcas["unotv"]) == {"id", "nombre", "cuenta", "por_defecto"}


# --- Edición --------------------------------------------------------------- #


def test_admin_mueve_una_marca_a_la_otra_cuenta(entorno):
    c = _cli_como("admin", superadmin=True)
    r = c.post("/api/sistema/cuenta-marcas", json={"marca": "unotv", "cuenta": "a"}, headers=_ORIGIN)
    assert r.status_code == 200
    unotv = _marcas(r.json())["unotv"]
    assert unotv["cuenta"] == "a"
    assert unotv["por_defecto"] is False
    # Persistido: un GET nuevo lo refleja.
    assert _marcas(c.get("/api/sistema/cuenta-marcas").json())["unotv"]["cuenta"] == "a"


def test_admin_limpia_el_override(entorno):
    c = _cli_como("admin", superadmin=True)
    c.post("/api/sistema/cuenta-marcas", json={"marca": "unotv", "cuenta": "a"}, headers=_ORIGIN)
    r = c.post("/api/sistema/cuenta-marcas", json={"marca": "unotv", "cuenta": ""}, headers=_ORIGIN)
    assert r.status_code == 200
    unotv = _marcas(r.json())["unotv"]
    assert unotv["cuenta"] == "b"  # vuelve a su reparto por defecto
    assert unotv["por_defecto"] is True


def test_marca_o_cuenta_invalida_da_400(entorno):
    c = _cli_como("admin", superadmin=True)
    assert c.post(
        "/api/sistema/cuenta-marcas", json={"marca": "noexiste", "cuenta": "a"}, headers=_ORIGIN
    ).status_code == 400
    assert c.post(
        "/api/sistema/cuenta-marcas", json={"marca": "unotv", "cuenta": "zzz"}, headers=_ORIGIN
    ).status_code == 400
