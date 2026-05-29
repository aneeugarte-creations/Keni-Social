"""Tests de la API del TABLERO de contenido unificado (`/api/contenido`).

Cubren el CRUD del padre, las filas por plataforma (estado + checklist), el `vencido`
derivado del deadline, la promocion desde el Radar y las validaciones (marca/red/estado/
responsable). Multiusuario con login real; reusa el aislamiento de `entorno` (Postgres) y
los fakes de `conftest`.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth

from .conftest import TOKEN_PRUEBA

_ORIGIN = {"Origin": "http://testserver"}
_CLAVE = "clave-de-prueba"


def _app():
    return app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)


def _cli(usuario: str = "ana", *, cobertura: bool = True) -> TestClient:
    auth.crear_usuario(usuario, _CLAVE, "editor")
    if cobertura:
        for u in auth.listar_usuarios():
            if u["usuario"] == usuario:
                auth.actualizar_perfil(u["id"], cobertura=True)
    c = TestClient(_app())
    r = c.post("/api/auth/login", json={"usuario": usuario, "password": _CLAVE}, headers=_ORIGIN)
    assert r.status_code == 200
    return c


def _id_usuario(nombre: str) -> str:
    for u in auth.listar_usuarios():
        if u["usuario"] == nombre:
            return u["id"]
    raise AssertionError(f"usuario {nombre!r} no existe")


def test_tablero_vacio_devuelve_catalogos(entorno):
    c = _cli()
    cuerpo = c.get("/api/contenido").json()
    assert cuerpo["contenidos"] == []
    cat = cuerpo["catalogos"]
    assert {"importante", "evergreen", "evento"} <= set(cat["flujos"])
    assert any(r["id"] == "web" for r in cat["redes"])
    assert "ana" in {u["usuario"] for u in cat["usuarios"]}


def test_crear_contenido_con_plataformas(entorno):
    c = _cli()
    r = c.post(
        "/api/contenido",
        json={
            "titulo": "Sismo CDMX",
            "flujo": "importante",
            "prioridad": "alta",
            "redes": ["instagram", "x", "web"],
        },
        headers=_ORIGIN,
    )
    assert r.status_code == 200
    cont = r.json()["contenido"]
    assert cont["titulo"] == "Sismo CDMX"
    assert cont["prioridad"] == "alta"
    assert cont["autor_nombre"] == "ana"
    # Una fila por red, ordenadas por orden canonico (x antes que instagram), web al final.
    assert [p["red"] for p in cont["plataformas"]] == ["x", "instagram", "web"]
    # Checklist por defecto: falta todo.
    assert all(p["falta_copy"] and p["falta_imagen"] for p in cont["plataformas"])


def test_listar_incluye_el_creado(entorno):
    c = _cli()
    c.post("/api/contenido", json={"titulo": "Nota A", "flujo": "evergreen"}, headers=_ORIGIN)
    cuerpo = c.get("/api/contenido?flujo=evergreen").json()
    assert [x["titulo"] for x in cuerpo["contenidos"]] == ["Nota A"]


def test_deadline_vencido_se_marca(entorno):
    c = _cli()
    r = c.post(
        "/api/contenido",
        json={"titulo": "Atrasada", "fecha_entrega": "2000-01-01"},
        headers=_ORIGIN,
    )
    assert r.json()["contenido"]["vencido"] is True


def test_actualizar_plataforma_estado_y_checklist(entorno):
    c = _cli()
    cont = c.post(
        "/api/contenido", json={"titulo": "C", "redes": ["x"]}, headers=_ORIGIN
    ).json()["contenido"]
    plat_id = cont["plataformas"][0]["id"]
    r = c.patch(
        f"/api/contenido/{cont['id']}/plataformas/{plat_id}",
        json={"estado": "aprobado", "falta_copy": False, "copy": "¡Listo!"},
        headers=_ORIGIN,
    )
    assert r.status_code == 200
    plat = r.json()["plataforma"]
    assert plat["estado"] == "aprobado"
    assert plat["falta_copy"] is False
    assert plat["copy"] == "¡Listo!"


def test_estado_plataforma_invalido_se_rechaza(entorno):
    c = _cli()
    cont = c.post(
        "/api/contenido", json={"titulo": "C", "redes": ["x"]}, headers=_ORIGIN
    ).json()["contenido"]
    plat_id = cont["plataformas"][0]["id"]
    r = c.patch(
        f"/api/contenido/{cont['id']}/plataformas/{plat_id}",
        json={"estado": "inventado"},
        headers=_ORIGIN,
    )
    assert r.status_code == 400


def test_agregar_y_borrar_plataforma(entorno):
    c = _cli()
    cont = c.post("/api/contenido", json={"titulo": "C"}, headers=_ORIGIN).json()["contenido"]
    r = c.post(
        f"/api/contenido/{cont['id']}/plataformas", json={"red": "tiktok"}, headers=_ORIGIN
    )
    assert r.status_code == 200
    plat_id = r.json()["plataforma"]["id"]
    assert c.request("DELETE", f"/api/contenido/{cont['id']}/plataformas/{plat_id}").status_code == 200


def test_crear_rechaza_marca_y_red_invalidas(entorno):
    c = _cli()
    assert c.post("/api/contenido", json={"titulo": "X", "marca": "no-existe"}, headers=_ORIGIN).status_code == 400
    assert c.post("/api/contenido", json={"titulo": "X", "redes": ["myspace"]}, headers=_ORIGIN).status_code == 400


def test_crear_sin_titulo_400(entorno):
    c = _cli()
    assert c.post("/api/contenido", json={"flujo": "importante"}, headers=_ORIGIN).status_code == 400


def test_asignar_responsable_real(entorno):
    c = _cli("ana")
    _cli("luis")
    luis = _id_usuario("luis")
    cont = c.post("/api/contenido", json={"titulo": "C"}, headers=_ORIGIN).json()["contenido"]
    r = c.patch(
        f"/api/contenido/{cont['id']}", json={"responsable_id": luis}, headers=_ORIGIN
    )
    assert r.status_code == 200
    assert r.json()["contenido"]["responsable_nombre"] == "luis"


def test_responsable_inexistente_se_rechaza(entorno):
    c = _cli()
    cont = c.post("/api/contenido", json={"titulo": "C"}, headers=_ORIGIN).json()["contenido"]
    r = c.patch(
        f"/api/contenido/{cont['id']}", json={"responsable_id": "fantasma"}, headers=_ORIGIN
    )
    assert r.status_code == 400


def test_desde_radar_crea_importante(entorno):
    c = _cli()
    r = c.post(
        "/api/contenido/desde-radar",
        json={"titulo": "Tendencia: Mundial", "redes": ["x", "instagram"], "prioridad": "alta"},
        headers=_ORIGIN,
    )
    assert r.status_code == 200
    cont = r.json()["contenido"]
    assert cont["flujo"] == "importante"
    assert cont["origen"] == "radar"
    assert cont["prioridad"] == "alta"
    assert len(cont["plataformas"]) == 2


def test_borrar_contenido(entorno):
    c = _cli()
    cont = c.post("/api/contenido", json={"titulo": "C"}, headers=_ORIGIN).json()["contenido"]
    assert c.request("DELETE", f"/api/contenido/{cont['id']}").status_code == 200
    assert c.get("/api/contenido").json()["contenidos"] == []
