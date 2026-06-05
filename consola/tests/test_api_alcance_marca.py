"""Aislamiento multimarca por-id (cierre ADR 0003): un editor acotado a la marca A no

toca recursos de la marca B, ni por id (IDOR) ni en los listados; un admin (sin
restriccion) conserva acceso TOTAL. Cubre el helper central `permisos.rechazo_pieza` a
traves de los handlers reales de contenido / publicaciones / aprobacion / green / metricas.

Patron de auth (igual que test_api_rota / test_api_conexiones_permisos): se crea el usuario
con `auth.crear_usuario(..., marcas=[...])` y se entra por SESION (cookie de login). El
ADMIN entra por sesion admin (sin marcas => sin restriccion). Las creaciones de datos se
hacen con el TOKEN de mantenimiento (sin restriccion) para sembrar piezas de AMBAS marcas.

Requiere Postgres de pruebas (fixture `entorno`): si no hay, SE SALTA (consistente con la
suite). Marca de scope CI: app_operacion (toca publicaciones/aprobacion).
"""

from __future__ import annotations

import pytest

from keni_consola import app as app_modulo
from keni_consola import auth
from starlette.testclient import TestClient

from .conftest import TOKEN_PRUEBA

pytestmark = pytest.mark.app_operacion

_ORIGIN = {"Origin": "http://testserver"}
CLAVE = "clave-de-prueba-123456"
MARCA_A = "unotv"
MARCA_B = "claro-sports"


def _app():
    return app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)


def _token_cli(app) -> TestClient:
    """Cliente que entra SOLO por el token de mantenimiento: SIN restriccion de marca (siembra)."""
    return TestClient(app, headers={"Authorization": f"Bearer {TOKEN_PRUEBA}"})


def _login_cli(app, usuario: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"usuario": usuario, "password": CLAVE}, headers=_ORIGIN)
    assert r.status_code == 200, r.text
    return c


def _editor_de_marca(app, nombre: str, marca: str) -> TestClient:
    auth.crear_usuario(nombre, CLAVE, "editor", marcas=[marca])
    return _login_cli(app, nombre)


def _admin_cli(app, nombre: str = "jefa") -> TestClient:
    # Admin SIN marcas => `marcas_visibles` None => sin restriccion (acceso total).
    auth.crear_usuario(nombre, CLAVE, "admin")
    return _login_cli(app, nombre)


def _crear_contenido(cli: TestClient, marca: str, titulo: str) -> dict:
    r = cli.post("/api/contenido", json={"titulo": titulo, "marca": marca}, headers=_ORIGIN)
    assert r.status_code == 200, r.text
    return r.json()["contenido"]


def _crear_publicacion(cli: TestClient, marca: str, titulo: str) -> dict:
    r = cli.post(
        "/api/publicaciones",
        json={"titulo": titulo, "marca": marca, "red": "instagram", "contenido": "x"},
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    return r.json()["publicacion"]


# --------------------------------------------------------------------------- #
# (a) IDOR por marca: editor de A -> 404 sobre una pieza/publicacion de B       #
# --------------------------------------------------------------------------- #


def test_editor_no_ve_detalle_publicacion_de_otra_marca(entorno):
    app = _app()
    siembra = _token_cli(app)
    pub_b = _crear_publicacion(siembra, MARCA_B, "de claro")
    editor_a = _editor_de_marca(app, "ed_a", MARCA_A)
    r = editor_a.get(f"/api/publicaciones/{pub_b['id']}")
    assert r.status_code == 404, r.text


def test_editor_no_edita_publicacion_de_otra_marca(entorno):
    app = _app()
    siembra = _token_cli(app)
    pub_b = _crear_publicacion(siembra, MARCA_B, "de claro")
    editor_a = _editor_de_marca(app, "ed_a", MARCA_A)
    r = editor_a.put(
        f"/api/publicaciones/{pub_b['id']}", json={"titulo": "secuestrada"}, headers=_ORIGIN
    )
    assert r.status_code == 404, r.text


def test_editor_no_borra_publicacion_de_otra_marca(entorno):
    app = _app()
    siembra = _token_cli(app)
    pub_b = _crear_publicacion(siembra, MARCA_B, "de claro")
    editor_a = _editor_de_marca(app, "ed_a", MARCA_A)
    r = editor_a.delete(f"/api/publicaciones/{pub_b['id']}", headers=_ORIGIN)
    assert r.status_code == 404, r.text


def test_editor_no_edita_contenido_de_otra_marca(entorno):
    app = _app()
    siembra = _token_cli(app)
    cont_b = _crear_contenido(siembra, MARCA_B, "tablero claro")
    editor_a = _editor_de_marca(app, "ed_a", MARCA_A)
    r = editor_a.patch(
        f"/api/contenido/{cont_b['id']}", json={"titulo": "robado"}, headers=_ORIGIN
    )
    assert r.status_code == 404, r.text


def test_editor_no_borra_contenido_de_otra_marca(entorno):
    app = _app()
    siembra = _token_cli(app)
    cont_b = _crear_contenido(siembra, MARCA_B, "tablero claro")
    editor_a = _editor_de_marca(app, "ed_a", MARCA_A)
    r = editor_a.delete(f"/api/contenido/{cont_b['id']}", headers=_ORIGIN)
    assert r.status_code == 404, r.text


def test_editor_no_aprueba_publicacion_de_otra_marca(entorno):
    app = _app()
    siembra = _token_cli(app)
    pub_b = _crear_publicacion(siembra, MARCA_B, "de claro")
    # Mandar a revision (por el token, sin restriccion) para que tenga cadena.
    r = siembra.post(
        f"/api/aprobacion/{pub_b['id']}/enviar-a-revision", json={}, headers=_ORIGIN
    )
    assert r.status_code == 200, r.text
    editor_a = _editor_de_marca(app, "ed_a", MARCA_A)
    r = editor_a.post(f"/api/aprobacion/{pub_b['id']}/aprobar", json={}, headers=_ORIGIN)
    assert r.status_code == 404, r.text


# --------------------------------------------------------------------------- #
# (b) Admin (sin restriccion) conserva acceso TOTAL                            #
# --------------------------------------------------------------------------- #


def test_admin_ve_y_edita_cualquier_marca(entorno):
    app = _app()
    siembra = _token_cli(app)
    pub_b = _crear_publicacion(siembra, MARCA_B, "de claro")
    admin = _admin_cli(app)
    r = admin.get(f"/api/publicaciones/{pub_b['id']}")
    assert r.status_code == 200, r.text
    r = admin.put(
        f"/api/publicaciones/{pub_b['id']}", json={"titulo": "editada por admin"}, headers=_ORIGIN
    )
    assert r.status_code == 200, r.text


def test_editor_si_accede_a_su_propia_marca(entorno):
    # Control negativo: el editor de A SI puede con una pieza de A (no se sobre-restringe).
    app = _app()
    siembra = _token_cli(app)
    pub_a = _crear_publicacion(siembra, MARCA_A, "de unotv")
    editor_a = _editor_de_marca(app, "ed_a", MARCA_A)
    r = editor_a.get(f"/api/publicaciones/{pub_a['id']}")
    assert r.status_code == 200, r.text
    r = editor_a.put(
        f"/api/publicaciones/{pub_a['id']}", json={"titulo": "ok"}, headers=_ORIGIN
    )
    assert r.status_code == 200, r.text


# --------------------------------------------------------------------------- #
# (c) Listados: una sesion acotada NO ve filas de la marca B                    #
# --------------------------------------------------------------------------- #


def test_listar_publicaciones_acota_a_marca_del_editor(entorno):
    app = _app()
    siembra = _token_cli(app)
    pub_a = _crear_publicacion(siembra, MARCA_A, "de unotv")
    pub_b = _crear_publicacion(siembra, MARCA_B, "de claro")
    editor_a = _editor_de_marca(app, "ed_a", MARCA_A)
    r = editor_a.get("/api/publicaciones")
    assert r.status_code == 200, r.text
    ids = {p["id"] for p in r.json()["publicaciones"]}
    assert pub_a["id"] in ids
    assert pub_b["id"] not in ids


def test_listar_contenido_acota_a_marca_del_editor(entorno):
    app = _app()
    siembra = _token_cli(app)
    cont_a = _crear_contenido(siembra, MARCA_A, "tablero unotv")
    cont_b = _crear_contenido(siembra, MARCA_B, "tablero claro")
    editor_a = _editor_de_marca(app, "ed_a", MARCA_A)
    r = editor_a.get("/api/contenido")
    assert r.status_code == 200, r.text
    ids = {c["id"] for c in r.json()["contenidos"]}
    assert cont_a["id"] in ids
    assert cont_b["id"] not in ids


def test_cola_aprobacion_acota_a_marca_del_editor(entorno):
    app = _app()
    siembra = _token_cli(app)
    pub_a = _crear_publicacion(siembra, MARCA_A, "de unotv")
    pub_b = _crear_publicacion(siembra, MARCA_B, "de claro")
    for pid in (pub_a["id"], pub_b["id"]):
        r = siembra.post(f"/api/aprobacion/{pid}/enviar-a-revision", json={}, headers=_ORIGIN)
        assert r.status_code == 200, r.text
    editor_a = _editor_de_marca(app, "ed_a", MARCA_A)
    r = editor_a.get("/api/aprobacion/cola")
    assert r.status_code == 200, r.text
    ids = {p["id"] for p in r.json()["cola"]}
    assert pub_a["id"] in ids
    assert pub_b["id"] not in ids


def test_admin_ve_ambas_marcas_en_listado(entorno):
    app = _app()
    siembra = _token_cli(app)
    pub_a = _crear_publicacion(siembra, MARCA_A, "de unotv")
    pub_b = _crear_publicacion(siembra, MARCA_B, "de claro")
    admin = _admin_cli(app)
    r = admin.get("/api/publicaciones")
    assert r.status_code == 200, r.text
    ids = {p["id"] for p in r.json()["publicaciones"]}
    assert {pub_a["id"], pub_b["id"]} <= ids


# --------------------------------------------------------------------------- #
# (d) Reasignacion de marca a una fuera de alcance -> rechazada                 #
# --------------------------------------------------------------------------- #


def test_editor_no_reasigna_contenido_a_marca_fuera_de_alcance(entorno):
    app = _app()
    siembra = _token_cli(app)
    cont_a = _crear_contenido(siembra, MARCA_A, "mio")
    editor_a = _editor_de_marca(app, "ed_a", MARCA_A)
    # Intentar mover la pieza propia (A) HACIA la marca B (fuera de alcance) -> 403.
    r = editor_a.patch(
        f"/api/contenido/{cont_a['id']}", json={"marca": MARCA_B}, headers=_ORIGIN
    )
    assert r.status_code == 403, r.text


def test_admin_si_reasigna_marca(entorno):
    app = _app()
    siembra = _token_cli(app)
    cont_a = _crear_contenido(siembra, MARCA_A, "mio")
    admin = _admin_cli(app)
    r = admin.patch(
        f"/api/contenido/{cont_a['id']}", json={"marca": MARCA_B}, headers=_ORIGIN
    )
    assert r.status_code == 200, r.text
    assert r.json()["contenido"]["marca"] == MARCA_B


# --------------------------------------------------------------------------- #
# Metricas: una sesion acotada nunca recibe el agregado all-brands             #
# --------------------------------------------------------------------------- #


def test_metricas_reporte_rechaza_marca_ajena(entorno):
    app = _app()
    # Editor de A pide explicitamente el reporte de la marca B (id_metricas) -> 404.
    editor_a = _editor_de_marca(app, "ed_a", MARCA_A)
    r = editor_a.get("/api/metricas/reporte", params={"marca": "claro_sports"})
    assert r.status_code == 404, r.text


def test_metricas_opciones_solo_marca_del_editor(entorno):
    app = _app()
    editor_a = _editor_de_marca(app, "ed_a", MARCA_A)
    r = editor_a.get("/api/metricas/opciones")
    assert r.status_code == 200, r.text
    ids = {m["id"] for m in r.json()["marcas"]}
    assert ids == {"unotv"}  # solo su marca (id_metricas de unotv == "unotv")


def test_metricas_admin_ve_todas_las_marcas(entorno):
    app = _app()
    admin = _admin_cli(app)
    r = admin.get("/api/metricas/opciones")
    assert r.status_code == 200, r.text
    ids = {m["id"] for m in r.json()["marcas"]}
    assert {"unotv", "claro_sports"} <= ids
