"""Tests de la API del kanban de sugerencias (/api/sugerencias).

El TABLERO y su control (mover, discovery, construir, checkpoint, borrar) son del SUPERADMIN;
el resto del equipo solo crea ideas y ve LAS SUYAS y su spec. Por eso estos tests usan SESIONES
reales (no el token de mantenimiento, que NO es superadmin): `_super()` para el control del
tablero y `_editor()` para la vista acotada por autor. Requiere el Postgres de pruebas (fixture
`entorno`; se salta si no hay). Los disparadores del motor (discovery/construir/checkpoint) se
prueban con la capa de lanzamiento monkeypatcheada (no encolan jobs reales).
"""

from __future__ import annotations

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth, sugerencias

from .conftest import TOKEN_PRUEBA

_ORIGIN = {"Origin": "http://testserver"}
CLAVE = "clave-de-prueba"


def _cli() -> TestClient:
    return TestClient(app_modulo.crear_app(token=TOKEN_PRUEBA))


def _sesion(usuario: str, *, rol: str = "editor", superadmin: bool = False) -> TestClient:
    """Cliente con SESIÓN real (login). `superadmin` da el control del tablero completo."""
    auth.crear_usuario(usuario, CLAVE, rol, superadmin=superadmin)
    c = _cli()
    assert c.post(
        "/api/auth/login", json={"usuario": usuario, "password": CLAVE}, headers=_ORIGIN
    ).status_code == 200
    return c


def _super(usuario: str = "jefa") -> TestClient:
    return _sesion(usuario, rol="admin", superadmin=True)


def _editor(usuario: str = "edi") -> TestClient:
    return _sesion(usuario, rol="editor", superadmin=False)


def _token() -> TestClient:
    c = _cli()
    c.headers.update({"Authorization": f"Bearer {TOKEN_PRUEBA}"})
    return c


def _crear(cli: TestClient, titulo: str = "Idea", **extra) -> str:
    cuerpo = {"titulo": titulo, **extra}
    r = cli.post("/api/sugerencias", json=cuerpo, headers=_ORIGIN)
    assert r.status_code == 200, r.text
    return r.json()["sugerencia"]["id"]


# --------------------------------------------------------------------------- #
# CRUD (superadmin: ve y controla el tablero entero)                          #
# --------------------------------------------------------------------------- #


def test_listar_vacio_y_catalogos(entorno):
    r = _super().get("/api/sugerencias")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["sugerencias"] == []
    assert cuerpo["superadmin"] is True
    assert cuerpo["categorias"] == list(sugerencias.CATEGORIAS)
    assert cuerpo["estados"] == list(sugerencias.ESTADOS)


def test_crear_atribuye_autor_de_la_sesion(entorno):
    cli = _super("jefa")
    r = cli.post(
        "/api/sugerencias",
        json={"titulo": "Exportar métricas", "detalle": "resumen", "categoria": "mejora"},
        headers=_ORIGIN,
    )
    assert r.status_code == 200
    s = r.json()["sugerencia"]
    assert s["titulo"] == "Exportar métricas"
    assert s["categoria"] == "mejora"
    assert s["estado"] == "nueva"
    # El autor (display + id de propiedad) sale de la SESIÓN, no del cuerpo.
    assert s["autor"] == "jefa"
    assert s["autor_id"]
    listado = cli.get("/api/sugerencias").json()["sugerencias"]
    assert listado[0]["id"] == s["id"]


def test_crear_ignora_autor_del_cuerpo(entorno):
    # El cliente no puede suplantar autoría: el `autor` del cuerpo se ignora.
    s = _super("jefa").post(
        "/api/sugerencias", json={"titulo": "x", "autor": "otra-persona"}, headers=_ORIGIN
    ).json()["sugerencia"]
    assert s["autor"] == "jefa"


def test_crear_sin_titulo_400(entorno):
    cli = _super()
    assert cli.post("/api/sugerencias", json={"detalle": "x"}, headers=_ORIGIN).status_code == 400
    assert cli.post("/api/sugerencias", json={"titulo": "   "}, headers=_ORIGIN).status_code == 400


def test_crear_categoria_invalida_400(entorno):
    r = _super().post(
        "/api/sugerencias", json={"titulo": "x", "categoria": "inventada"}, headers=_ORIGIN
    )
    assert r.status_code == 400


def test_crear_categoria_vacia_usa_defecto(entorno):
    r = _super().post(
        "/api/sugerencias", json={"titulo": "x", "categoria": ""}, headers=_ORIGIN
    )
    assert r.status_code == 200
    assert r.json()["sugerencia"]["categoria"] == sugerencias.CATEGORIA_DEFECTO


def test_patch_estado_valido(entorno):
    cli = _super()
    sid = _crear(cli)
    r = cli.patch(f"/api/sugerencias/{sid}", json={"estado": "discovery"}, headers=_ORIGIN)
    assert r.status_code == 200
    assert r.json()["sugerencia"]["estado"] == "discovery"


def test_patch_estado_transicion_invalida_400(entorno):
    cli = _super()
    sid = _crear(cli)
    # nueva -> hecha no es una transición permitida.
    assert cli.patch(
        f"/api/sugerencias/{sid}", json={"estado": "hecha"}, headers=_ORIGIN
    ).status_code == 400


def test_patch_estado_desconocido_400(entorno):
    cli = _super()
    sid = _crear(cli)
    assert cli.patch(
        f"/api/sugerencias/{sid}", json={"estado": "zzz"}, headers=_ORIGIN
    ).status_code == 400


def test_patch_texto(entorno):
    cli = _super()
    sid = _crear(cli)
    r = cli.patch(
        f"/api/sugerencias/{sid}", json={"titulo": "Otra", "categoria": "bug"}, headers=_ORIGIN
    )
    assert r.status_code == 200
    s = r.json()["sugerencia"]
    assert s["titulo"] == "Otra"
    assert s["categoria"] == "bug"


def test_patch_inexistente_404(entorno):
    assert _super().patch(
        "/api/sugerencias/nope", json={"estado": "discovery"}, headers=_ORIGIN
    ).status_code == 404


def test_descartar_desde_nueva(entorno):
    cli = _super()
    sid = _crear(cli)
    r = cli.patch(f"/api/sugerencias/{sid}", json={"estado": "descartada"}, headers=_ORIGIN)
    assert r.status_code == 200
    assert r.json()["sugerencia"]["estado"] == "descartada"


def test_revivir_descartada(entorno):
    # Una descartada vuelve a `nueva` (revivir): transición válida del tablero.
    cli = _super()
    sid = _crear(cli)
    cli.patch(f"/api/sugerencias/{sid}", json={"estado": "descartada"}, headers=_ORIGIN)
    r = cli.patch(f"/api/sugerencias/{sid}", json={"estado": "nueva"}, headers=_ORIGIN)
    assert r.status_code == 200
    assert r.json()["sugerencia"]["estado"] == "nueva"


def test_borrar(entorno):
    cli = _super()
    sid = _crear(cli, "Borrable")
    r = cli.delete(f"/api/sugerencias/{sid}", headers=_ORIGIN)
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    ids = [s["id"] for s in cli.get("/api/sugerencias").json()["sugerencias"]]
    assert sid not in ids


def test_borrar_descartada(entorno):
    # El superadmin puede limpiar una descartada del tablero.
    cli = _super()
    sid = _crear(cli)
    cli.patch(f"/api/sugerencias/{sid}", json={"estado": "descartada"}, headers=_ORIGIN)
    assert cli.delete(f"/api/sugerencias/{sid}", headers=_ORIGIN).status_code == 200


def test_borrar_inexistente_404(entorno):
    assert _super().delete("/api/sugerencias/nope", headers=_ORIGIN).status_code == 404


# --------------------------------------------------------------------------- #
# Propiedad / rol: el tablero es del superadmin; el resto solo ve LO SUYO      #
# --------------------------------------------------------------------------- #


def test_editor_solo_ve_sus_ideas(entorno):
    sup = _super("jefa")
    edi = _editor("edi")
    mia = _crear(edi, "Mía")
    _crear(sup, "Ajena")
    ids = [s["id"] for s in edi.get("/api/sugerencias").json()["sugerencias"]]
    assert ids == [mia]


def test_listar_marca_no_superadmin(entorno):
    assert _editor().get("/api/sugerencias").json()["superadmin"] is False


def test_editor_obtiene_la_suya_no_la_ajena(entorno):
    sup = _super("jefa")
    edi = _editor("edi")
    mia = _crear(edi, "Mía")
    ajena = _crear(sup, "Ajena")
    assert edi.get(f"/api/sugerencias/{mia}").status_code == 200
    # Una ajena es, para el editor, inexistente (no se filtra que exista).
    assert edi.get(f"/api/sugerencias/{ajena}").status_code == 404


def test_editor_edita_el_texto_de_su_idea(entorno):
    edi = _editor()
    sid = _crear(edi, "Mía")
    r = edi.patch(f"/api/sugerencias/{sid}", json={"titulo": "Mía v2"}, headers=_ORIGIN)
    assert r.status_code == 200
    assert r.json()["sugerencia"]["titulo"] == "Mía v2"


def test_editor_no_mueve_estado_403(entorno):
    edi = _editor()
    sid = _crear(edi, "Mía")
    r = edi.patch(f"/api/sugerencias/{sid}", json={"estado": "discovery"}, headers=_ORIGIN)
    assert r.status_code == 403


def test_editor_no_toca_idea_ajena_404(entorno):
    sup = _super("jefa")
    edi = _editor("edi")
    ajena = _crear(sup, "Ajena")
    assert edi.patch(
        f"/api/sugerencias/{ajena}", json={"titulo": "hack"}, headers=_ORIGIN
    ).status_code == 404


def test_editor_no_borra_403(entorno):
    edi = _editor()
    sid = _crear(edi, "Mía")
    assert edi.delete(f"/api/sugerencias/{sid}", headers=_ORIGIN).status_code == 403


def test_editor_no_lanza_discovery_403(entorno):
    edi = _editor()
    sid = _crear(edi, "Mía")
    assert edi.post(
        f"/api/sugerencias/{sid}/discovery", json={}, headers=_ORIGIN
    ).status_code == 403


def test_editor_no_construye_403(entorno):
    edi = _editor()
    sid = _crear(edi, "Mía")
    assert edi.post(
        f"/api/sugerencias/{sid}/construir", json={}, headers=_ORIGIN
    ).status_code == 403


# --------------------------------------------------------------------------- #
# Disparadores del motor (superadmin; lanzamiento monkeypatcheado)            #
# --------------------------------------------------------------------------- #


def test_discovery_encola(entorno, monkeypatch):
    cli = _super()
    sid = _crear(cli)
    monkeypatch.setattr(sugerencias, "lanzar_discovery", lambda _id: {"id": "gen-x"})
    r = cli.post(f"/api/sugerencias/{sid}/discovery", json={}, headers=_ORIGIN)
    assert r.status_code == 200
    assert r.json()["generacion"]["id"] == "gen-x"


def test_discovery_inexistente_404(entorno, monkeypatch):
    monkeypatch.setattr(sugerencias, "lanzar_discovery", lambda _id: None)
    assert _super().post(
        "/api/sugerencias/nope/discovery", json={}, headers=_ORIGIN
    ).status_code == 404


def test_construir_encola(entorno, monkeypatch):
    cli = _super()
    sid = _crear(cli)
    capturado = {}

    def fake(_id, *, complejidad=""):
        capturado["complejidad"] = complejidad
        return {"id": "gen-y"}

    monkeypatch.setattr(sugerencias, "lanzar_construir", fake)
    r = cli.post(
        f"/api/sugerencias/{sid}/construir", json={"complejidad": "simple"}, headers=_ORIGIN
    )
    assert r.status_code == 200
    assert r.json()["generacion"]["id"] == "gen-y"
    assert capturado["complejidad"] == "simple"


def test_checkpoint_accion_invalida_400(entorno):
    cli = _super()
    sid = _crear(cli)
    assert cli.post(
        f"/api/sugerencias/{sid}/checkpoint", json={"accion": "zzz"}, headers=_ORIGIN
    ).status_code == 400


def test_checkpoint_cancelar_descarta(entorno):
    cli = _super()
    sid = _crear(cli)
    r = cli.post(
        f"/api/sugerencias/{sid}/checkpoint", json={"accion": "cancelar"}, headers=_ORIGIN
    )
    assert r.status_code == 200
    assert r.json()["sugerencia"]["estado"] == "descartada"


# La PROMOCIÓN a main es superadmin-gated y proxea a worker-dev: se prueba en
# `test_api_sugerencias_promover.py` (cerrojo de rol, proxy parcheado, transición de kanban).
