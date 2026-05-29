"""Tests de la API de coordinacion por turno (ola "coord").

Cubre el CRUD `/api/rota/semana/{lunes}/coordinacion` (GET) y `/api/rota/coordinacion`
(PUT, DELETE):
  - GET vacia cuando no hay coordinaciones; con datos resuelve `coordinador_nombre`.
  - PUT (admin) hace UPSERT por (fecha, franja_id): si ya hay, reemplaza.
  - PUT con usuario sin `puede_coordinar` -> 400 accionable.
  - PUT sin admin -> 403.
  - DELETE (admin) borra y es idempotente.
  - GET trae solo las de la semana pedida (filtro por `lunes`).
  - Independencia: borrar un turno NO toca la coordinacion (la mantiene el admin).
"""

from __future__ import annotations

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth, repos

from .conftest import TOKEN_PRUEBA

_ORIGIN = {"Origin": "http://testserver"}
CLAVE = "clave-de-prueba"
LUNES = "2026-06-08"
FECHA = "2026-06-10"
OTRA_FECHA = "2026-06-11"


def _cli_admin(app) -> TestClient:
    """TestClient autenticado como admin (sesion). Crea un admin si no existe."""
    cli = TestClient(app)
    auth.crear_usuario("elias_admin", CLAVE, "admin")
    r = cli.post(
        "/api/auth/login",
        json={"usuario": "elias_admin", "password": CLAVE},
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    return cli


def _franja_manana(cli: TestClient, lunes: str = LUNES) -> dict:
    """Siembra defaults y devuelve la franja "Mañana" de esa semana."""
    cli.get(f"/api/rota/semana/{lunes}/franjas")
    franjas = cli.get(f"/api/rota/semana/{lunes}/franjas").json()["franjas"]
    return next(f for f in franjas if f["nombre"] == "Mañana")


# --------------------------------------------------------------------------- #
# GET /api/rota/semana/{lunes}/coordinacion                                    #
# --------------------------------------------------------------------------- #


def test_get_coordinacion_vacia(cliente):
    """Semana sin coordinaciones -> lista vacia."""
    r = cliente.get(f"/api/rota/semana/{LUNES}/coordinacion")
    assert r.status_code == 200, r.text
    assert r.json() == {"lunes": LUNES, "coordinacion": []}


def test_get_coordinacion_lunes_invalido_400(cliente):
    r = cliente.get("/api/rota/semana/no-fecha/coordinacion")
    assert r.status_code == 400


def test_get_coordinacion_devuelve_nombre_resuelto(entorno):
    """Tras un PUT, GET incluye `coordinador_nombre` resuelto del equipo completo."""
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    cli = _cli_admin(app)
    coord = auth.crear_usuario("coordi", CLAVE, "editor", puede_coordinar=True)
    franja = _franja_manana(cli)
    cli.put(
        "/api/rota/coordinacion",
        json={
            "lunes": LUNES, "fecha": FECHA, "franja_id": franja["id"],
            "coordinador_id": coord["id"],
        },
        headers=_ORIGIN,
    )
    r = cli.get(f"/api/rota/semana/{LUNES}/coordinacion")
    assert r.status_code == 200
    lista = r.json()["coordinacion"]
    assert len(lista) == 1
    assert lista[0]["fecha"] == FECHA
    assert lista[0]["franja_id"] == franja["id"]
    assert lista[0]["coordinador_id"] == coord["id"]
    assert lista[0]["coordinador_nombre"] == "coordi"


def test_get_coordinacion_solo_de_la_semana_pedida(entorno):
    """GET no incluye coordinaciones de semanas distintas."""
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    cli = _cli_admin(app)
    coord = auth.crear_usuario("c", CLAVE, "editor", puede_coordinar=True)
    franja = _franja_manana(cli)
    # Coordinacion en LUNES.
    cli.put(
        "/api/rota/coordinacion",
        json={
            "lunes": LUNES, "fecha": FECHA, "franja_id": franja["id"],
            "coordinador_id": coord["id"],
        },
        headers=_ORIGIN,
    )
    # Coordinacion en OTRO lunes (semana distinta).
    otro_lunes = "2026-06-15"
    otra_franja = _franja_manana(cli, otro_lunes)
    cli.put(
        "/api/rota/coordinacion",
        json={
            "lunes": otro_lunes, "fecha": "2026-06-17",
            "franja_id": otra_franja["id"], "coordinador_id": coord["id"],
        },
        headers=_ORIGIN,
    )
    r = cli.get(f"/api/rota/semana/{LUNES}/coordinacion")
    lista = r.json()["coordinacion"]
    assert len(lista) == 1
    assert lista[0]["fecha"] == FECHA


# --------------------------------------------------------------------------- #
# PUT /api/rota/coordinacion                                                   #
# --------------------------------------------------------------------------- #


def test_put_coordinacion_admin_asigna(entorno):
    """PUT asigna coordinador en una celda y devuelve el registro."""
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    cli = _cli_admin(app)
    coord = auth.crear_usuario("ele", CLAVE, "editor", puede_coordinar=True)
    franja = _franja_manana(cli)
    r = cli.put(
        "/api/rota/coordinacion",
        json={
            "lunes": LUNES, "fecha": FECHA, "franja_id": franja["id"],
            "coordinador_id": coord["id"],
        },
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["fecha"] == FECHA
    assert cuerpo["franja_id"] == franja["id"]
    assert cuerpo["coordinador_id"] == coord["id"]
    assert cuerpo["coordinador_nombre"] == "ele"


def test_put_coordinacion_upsert_reemplaza(entorno):
    """Segundo PUT en la misma (fecha, franja) reemplaza el coordinador previo."""
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    cli = _cli_admin(app)
    a = auth.crear_usuario("ana", CLAVE, "editor", puede_coordinar=True)
    b = auth.crear_usuario("beto", CLAVE, "editor", puede_coordinar=True)
    franja = _franja_manana(cli)
    cli.put(
        "/api/rota/coordinacion",
        json={
            "lunes": LUNES, "fecha": FECHA, "franja_id": franja["id"],
            "coordinador_id": a["id"],
        },
        headers=_ORIGIN,
    )
    cli.put(
        "/api/rota/coordinacion",
        json={
            "lunes": LUNES, "fecha": FECHA, "franja_id": franja["id"],
            "coordinador_id": b["id"],
        },
        headers=_ORIGIN,
    )
    lista = cli.get(f"/api/rota/semana/{LUNES}/coordinacion").json()["coordinacion"]
    assert len(lista) == 1
    assert lista[0]["coordinador_id"] == b["id"]


def test_put_coordinacion_usuario_sin_flag_400(entorno):
    """PUT con un coordinador_id de un usuario SIN `puede_coordinar=true` -> 400."""
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    cli = _cli_admin(app)
    # Usuario existe pero NO puede coordinar (default False).
    sin_flag = auth.crear_usuario("sinflag", CLAVE, "editor")
    franja = _franja_manana(cli)
    r = cli.put(
        "/api/rota/coordinacion",
        json={
            "lunes": LUNES, "fecha": FECHA, "franja_id": franja["id"],
            "coordinador_id": sin_flag["id"],
        },
        headers=_ORIGIN,
    )
    assert r.status_code == 400, r.text
    assert "puede_coordinar" in r.json()["error"]


def test_put_coordinacion_usuario_inexistente_400(entorno):
    """PUT con un coordinador_id que no existe -> 400."""
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    cli = _cli_admin(app)
    franja = _franja_manana(cli)
    r = cli.put(
        "/api/rota/coordinacion",
        json={
            "lunes": LUNES, "fecha": FECHA, "franja_id": franja["id"],
            "coordinador_id": "no-existe",
        },
        headers=_ORIGIN,
    )
    assert r.status_code == 400


def test_put_coordinacion_sin_admin_403(cliente):
    """El cliente por defecto entra por TOKEN -> NO es admin con sesion -> 403."""
    franja = _franja_manana(cliente)
    coord = auth.crear_usuario("coordi", CLAVE, "editor", puede_coordinar=True)
    r = cliente.put(
        "/api/rota/coordinacion",
        json={
            "lunes": LUNES, "fecha": FECHA, "franja_id": franja["id"],
            "coordinador_id": coord["id"],
        },
    )
    assert r.status_code == 403


def test_put_coordinacion_campos_invalidos_400(entorno):
    """Lunes/fecha/franja_id/coordinador_id faltantes -> 400 individualizados."""
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    cli = _cli_admin(app)
    franja = _franja_manana(cli)
    coord = auth.crear_usuario("c", CLAVE, "editor", puede_coordinar=True)
    # lunes invalido.
    r = cli.put(
        "/api/rota/coordinacion",
        json={
            "lunes": "no-fecha", "fecha": FECHA, "franja_id": franja["id"],
            "coordinador_id": coord["id"],
        },
        headers=_ORIGIN,
    )
    assert r.status_code == 400
    # fecha invalida.
    r = cli.put(
        "/api/rota/coordinacion",
        json={
            "lunes": LUNES, "fecha": "no-fecha", "franja_id": franja["id"],
            "coordinador_id": coord["id"],
        },
        headers=_ORIGIN,
    )
    assert r.status_code == 400
    # franja_id vacia.
    r = cli.put(
        "/api/rota/coordinacion",
        json={
            "lunes": LUNES, "fecha": FECHA, "franja_id": "",
            "coordinador_id": coord["id"],
        },
        headers=_ORIGIN,
    )
    assert r.status_code == 400
    # coordinador_id vacio.
    r = cli.put(
        "/api/rota/coordinacion",
        json={
            "lunes": LUNES, "fecha": FECHA, "franja_id": franja["id"],
            "coordinador_id": "",
        },
        headers=_ORIGIN,
    )
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# DELETE /api/rota/coordinacion                                                #
# --------------------------------------------------------------------------- #


def test_delete_coordinacion_borra(entorno):
    """DELETE borra el registro y la lista de la semana queda sin esa celda."""
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    cli = _cli_admin(app)
    coord = auth.crear_usuario("c", CLAVE, "editor", puede_coordinar=True)
    franja = _franja_manana(cli)
    cli.put(
        "/api/rota/coordinacion",
        json={
            "lunes": LUNES, "fecha": FECHA, "franja_id": franja["id"],
            "coordinador_id": coord["id"],
        },
        headers=_ORIGIN,
    )
    r = cli.request(
        "DELETE",
        "/api/rota/coordinacion",
        json={"fecha": FECHA, "franja_id": franja["id"]},
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    assert r.json()["borrado"] is True
    lista = cli.get(f"/api/rota/semana/{LUNES}/coordinacion").json()["coordinacion"]
    assert lista == []


def test_delete_coordinacion_idempotente(entorno):
    """DELETE de una celda sin coordinacion responde 200 con `borrado=False`."""
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    cli = _cli_admin(app)
    franja = _franja_manana(cli)
    r = cli.request(
        "DELETE",
        "/api/rota/coordinacion",
        json={"fecha": FECHA, "franja_id": franja["id"]},
        headers=_ORIGIN,
    )
    assert r.status_code == 200
    assert r.json()["borrado"] is False


def test_delete_coordinacion_sin_admin_403(cliente):
    """Sin sesion admin -> 403."""
    franja = _franja_manana(cliente)
    r = cliente.request(
        "DELETE",
        "/api/rota/coordinacion",
        json={"fecha": FECHA, "franja_id": franja["id"]},
    )
    assert r.status_code == 403


# --------------------------------------------------------------------------- #
# Independencia: la coordinacion sobrevive a cambios en turnos                 #
# --------------------------------------------------------------------------- #


def test_coordinacion_independiente_de_turnos(entorno):
    """Borrar un turno de CM NO borra la coordinacion asignada a la misma celda."""
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    cli = _cli_admin(app)
    cm = auth.crear_usuario("cmcm", CLAVE, "editor", cobertura=True)
    coord = auth.crear_usuario("cocoord", CLAVE, "editor", puede_coordinar=True)
    franja = _franja_manana(cli)
    # Asigna coordinador a la celda.
    cli.put(
        "/api/rota/coordinacion",
        json={
            "lunes": LUNES, "fecha": FECHA, "franja_id": franja["id"],
            "coordinador_id": coord["id"],
        },
        headers=_ORIGIN,
    )
    # Crea un turno de CM en la misma celda y luego lo borra.
    turno = repos.crear_turno_rota(
        LUNES, FECHA,
        miembro_id=cm["id"], miembro_nombre="cmcm", franja_id=franja["id"],
    )
    cli.delete(f"/api/rota/turnos/{turno['id']}", headers=_ORIGIN)
    # La coordinacion sigue.
    lista = cli.get(f"/api/rota/semana/{LUNES}/coordinacion").json()["coordinacion"]
    assert len(lista) == 1
    assert lista[0]["coordinador_id"] == coord["id"]
