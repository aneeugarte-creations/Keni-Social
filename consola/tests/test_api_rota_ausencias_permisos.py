"""Frontera de permisos de AUSENCIAS — modelo dueño-o-admin (auditoría Turnos jun-2026).

El agujero era que cualquier editor autenticado mutaba la ausencia de OTRO por API
directa. Ahora: un editor gestiona SOLO LO SUYO; un admin, la de cualquiera; nadie toca
la de otro. (El token de mantenimiento conserva acceso pleno: cubierto por
`test_api_rota.py::test_ausencias_crud`, que opera con el cliente del token.)
"""

from __future__ import annotations

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth

from .conftest import TOKEN_PRUEBA

_ORIGIN = {"Origin": "http://testserver"}
CLAVE = "clave-de-prueba"
DESDE = "2026-05-25"
HASTA = "2026-05-31"


def _login(app, usuario: str) -> TestClient:
    cli = TestClient(app)
    r = cli.post(
        "/api/auth/login",
        json={"usuario": usuario, "password": CLAVE},
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    return cli


def _setup(entorno):
    """App + ana/beto (editores) + elias (admin), cada uno con su sesión."""
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    ana = auth.crear_usuario("ana", CLAVE, "editor")
    beto = auth.crear_usuario("beto", CLAVE, "editor")
    elias = auth.crear_usuario("elias", CLAVE, "admin")
    return (
        app, ana, beto, elias,
        _login(app, "ana"), _login(app, "beto"), _login(app, "elias"),
    )


def _crear(cli: TestClient, miembro_id: str, **extra):
    cuerpo = {"miembro_id": miembro_id, "desde": DESDE, "hasta": HASTA, "tipo": "vacaciones"}
    cuerpo.update(extra)
    return cli.post("/api/rota/ausencias", json=cuerpo, headers=_ORIGIN)


# --------------------------------------------------------------------------- #
# Crear                                                                        #
# --------------------------------------------------------------------------- #


def test_editor_crea_su_propia_ausencia(entorno):
    _app, ana, _beto, _elias, cli_ana, _cb, _ce = _setup(entorno)
    assert _crear(cli_ana, ana["id"]).status_code == 201


def test_editor_no_crea_ausencia_de_otro_403(entorno):
    _app, _ana, beto, _elias, cli_ana, _cb, _ce = _setup(entorno)
    assert _crear(cli_ana, beto["id"]).status_code == 403


def test_admin_crea_ausencia_de_cualquiera(entorno):
    _app, ana, _beto, _elias, _ca, _cb, cli_elias = _setup(entorno)
    assert _crear(cli_elias, ana["id"]).status_code == 201


# --------------------------------------------------------------------------- #
# Editar / borrar                                                             #
# --------------------------------------------------------------------------- #


def test_editor_no_edita_ni_borra_ausencia_de_otro_403(entorno):
    _app, _ana, beto, _elias, cli_ana, cli_beto, _ce = _setup(entorno)
    a = _crear(cli_beto, beto["id"]).json()["ausencia"]
    patch = cli_ana.patch(
        f"/api/rota/ausencias/{a['id']}", json={"tipo": "baja"}, headers=_ORIGIN
    )
    assert patch.status_code == 403
    assert cli_ana.delete(f"/api/rota/ausencias/{a['id']}", headers=_ORIGIN).status_code == 403


def test_editor_edita_y_borra_la_suya(entorno):
    _app, ana, _beto, _elias, cli_ana, _cb, _ce = _setup(entorno)
    a = _crear(cli_ana, ana["id"]).json()["ausencia"]
    patch = cli_ana.patch(
        f"/api/rota/ausencias/{a['id']}", json={"tipo": "baja"}, headers=_ORIGIN
    )
    assert patch.status_code == 200, patch.text
    assert cli_ana.delete(f"/api/rota/ausencias/{a['id']}", headers=_ORIGIN).status_code == 200


def test_admin_edita_y_borra_la_de_cualquiera(entorno):
    _app, ana, _beto, _elias, cli_ana, _cb, cli_elias = _setup(entorno)
    a = _crear(cli_ana, ana["id"]).json()["ausencia"]
    patch = cli_elias.patch(
        f"/api/rota/ausencias/{a['id']}", json={"tipo": "baja"}, headers=_ORIGIN
    )
    assert patch.status_code == 200, patch.text
    assert cli_elias.delete(f"/api/rota/ausencias/{a['id']}", headers=_ORIGIN).status_code == 200
