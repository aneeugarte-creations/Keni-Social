"""Tests del endpoint de LECTURA del uso de las cuentas (`GET /api/sistema/uso`).

Cualquier usuario AUTENTICADO lo consulta, pero solo recibe LAS CUENTAS DE SUS MARCAS (suelo de
autorización): admin/superadmin ven ambas; un editor la(s) cuenta(s) de sus marcas; un editor sin
marcas (o el token de mantenimiento, sin usuario) no recibe ninguna. Cubre ese acotamiento por
usuario y la FORMA del contrato por cuenta (cold start -> desconectada+`alerta_roja`, al 100%
semanal, operación normal). El endpoint solo LEE la tabla: se siembra con `repos.guardar_uso_cuenta`.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth, repos

from .conftest import TOKEN_PRUEBA

_ORIGIN = {"Origin": "http://testserver"}
CLAVE = "clave-de-prueba"

# Campos del contrato de CADA cuenta del payload (lo que consume el indicador del sidebar).
_CAMPOS_CUENTA = {
    "cuenta", "etiqueta", "marcas", "conectada", "semana_pct", "sesion_5h_pct", "sonnet_pct",
    "reset_semana_iso", "reset_semana_txt", "actualizado_ts", "al_100", "alerta_roja", "dia",
}


def _cli() -> TestClient:
    return TestClient(app_modulo.crear_app(token=TOKEN_PRUEBA))


def _cli_como(rol: str, *, marcas: list[str] | None = None, superadmin: bool = False) -> TestClient:
    auth.crear_usuario("u", CLAVE, rol, marcas=marcas, superadmin=superadmin)
    c = _cli()
    assert c.post(
        "/api/auth/login", json={"usuario": "u", "password": CLAVE}, headers=_ORIGIN
    ).status_code == 200
    return c


def _cuentas(cuerpo: dict) -> dict:
    """Indexa el payload `{cuentas:[...]}` por id de cuenta."""
    return {c["cuenta"]: c for c in cuerpo["cuentas"]}


# --- Acotamiento por usuario ----------------------------------------------- #


def test_token_mantenimiento_sin_usuario_no_ve_cuentas(entorno):
    c = _cli()
    c.headers.update({"Authorization": f"Bearer {TOKEN_PRUEBA}"})
    r = c.get("/api/sistema/uso")
    assert r.status_code == 200
    assert r.json() == {"cuentas": []}


def test_editor_sin_marcas_no_ve_cuentas(entorno):
    r = _cli_como("editor").get("/api/sistema/uso")
    assert r.status_code == 200
    assert r.json() == {"cuentas": []}


def test_editor_unotv_solo_ve_cuenta_b(entorno):
    repos.guardar_uso_cuenta(cuenta="b", conectada=True, semana_pct=80, sesion_5h_pct=5,
                             sonnet_pct=2, dia_utc="2026-06-14")
    cuentas = _cuentas(_cli_como("editor", marcas=["unotv"]).get("/api/sistema/uso").json())
    assert set(cuentas) == {"b"}
    b = cuentas["b"]
    assert set(b) == _CAMPOS_CUENTA
    assert "unotv" in b["marcas"]
    assert b["semana_pct"] == 80 and b["conectada"] is True
    # `dia` (cupo del dia del limite que primero se agota) -> barra «24h» del indicador.
    assert set(b["dia"]) == {"consumo_pct", "umbral_pct", "limite", "pausado"}


def test_editor_claro_solo_ve_cuenta_a(entorno):
    cuentas = _cuentas(_cli_como("editor", marcas=["claro-sports"]).get("/api/sistema/uso").json())
    assert set(cuentas) == {"a"}
    assert "claro-sports" in cuentas["a"]["marcas"]


def test_editor_ambas_marcas_ve_ambas_cuentas(entorno):
    cuentas = _cuentas(
        _cli_como("editor", marcas=["unotv", "claro-sports"]).get("/api/sistema/uso").json()
    )
    assert set(cuentas) == {"a", "b"}


def test_admin_ve_ambas_cuentas(entorno):
    cuentas = _cuentas(_cli_como("admin").get("/api/sistema/uso").json())
    assert set(cuentas) == {"a", "b"}


def test_superadmin_ve_ambas_cuentas(entorno):
    # El flag superadmin da la vista completa aunque el rol no sea admin.
    cuentas = _cuentas(
        _cli_como("editor", superadmin=True).get("/api/sistema/uso").json()
    )
    assert set(cuentas) == {"a", "b"}


# --- Forma + alerta_roja por cuenta ---------------------------------------- #


def test_cold_start_cuenta_desconectada_alerta_roja(entorno):
    # admin ve ambas; sin muestreo, cada cuenta va desconectada con alerta_roja.
    cuentas = _cuentas(_cli_como("admin").get("/api/sistema/uso").json())
    for c in ("a", "b"):
        assert cuentas[c]["conectada"] is False
        assert cuentas[c]["semana_pct"] is None
        assert cuentas[c]["al_100"] is False
        assert cuentas[c]["alerta_roja"] is True


def test_semana_al_100_alerta_roja(entorno):
    repos.guardar_uso_cuenta(
        cuenta="a", conectada=True, semana_pct=100, sesion_5h_pct=40, sonnet_pct=12,
        reset_semana_iso="2026-07-01T07:00:00Z", reset_semana_txt="Jul 1, 7am (UTC)",
        actualizado_ts=1750000000.0, dia_utc="2026-06-14",
    )
    a = _cuentas(_cli_como("editor", marcas=["claro-sports"]).get("/api/sistema/uso").json())["a"]
    assert a["conectada"] is True and a["semana_pct"] == 100
    assert a["al_100"] is True and a["alerta_roja"] is True
    assert a["reset_semana_iso"] == "2026-07-01T07:00:00Z"


def test_operacion_normal_sin_alerta(entorno):
    repos.guardar_uso_cuenta(
        cuenta="a", conectada=True, semana_pct=42, sesion_5h_pct=10, sonnet_pct=3,
        actualizado_ts=1750000000.0, dia_utc="2026-06-14",
    )
    a = _cuentas(_cli_como("editor", marcas=["claro-sports"]).get("/api/sistema/uso").json())["a"]
    assert a["conectada"] is True and a["semana_pct"] == 42
    assert a["al_100"] is False and a["alerta_roja"] is False
    # resets vacíos se normalizan a null.
    assert a["reset_semana_iso"] is None and a["reset_semana_txt"] is None
