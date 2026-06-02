"""Tests de la cola de aprobacion de equipo (#9, Fase 3). OFFLINE, DB en tmp.

Cubre el flujo borrador -> en_revision -> aprobado, con identidad real (login):
quien envia, quien aprueba (otro par de ojos), la regla de equipo (no auto-aprobar),
el rechazo (vuelta a borrador) y la cola que lista lo pendiente con quien/cuando.

Reusa el aislamiento de `entorno` y los patrones de `test_atribucion` (login real para
sesiones distintas). La auth/CSRF/sesion NO se toca; el acceso por TOKEN de bootstrap
cuenta como mantenimiento (admin) y puede saltarse la regla de "otro par de ojos".
"""

from __future__ import annotations

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth

from .conftest import TOKEN_PRUEBA

_ORIGIN = {"Origin": "http://testserver"}
_CLAVE = "clave-de-prueba-123"
_MARCA = "unotv"


def _app(bootstrap=False):
    return app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=bootstrap)


def _cli_usuario(usuario: str, rol: str = "editor") -> TestClient:
    """TestClient con SESION de `usuario` (login real): atribuye al crear/enviar/aprobar."""
    auth.crear_usuario(usuario, _CLAVE, rol)
    c = TestClient(_app())
    r = c.post("/api/auth/login", json={"usuario": usuario, "password": _CLAVE}, headers=_ORIGIN)
    assert r.status_code == 200
    return c


def _cli_token() -> TestClient:
    """TestClient autenticado por el TOKEN de bootstrap (mantenimiento, sin usuario)."""
    return TestClient(_app(), headers={"Authorization": f"Bearer {TOKEN_PRUEBA}"})


def _crear_borrador(cli: TestClient, **campos) -> dict:
    base = {"marca": _MARCA, "red": "x", "titulo": "T", "contenido": "C"}
    base.update(campos)
    r = cli.post("/api/publicaciones", json=base, headers=_ORIGIN)
    assert r.status_code == 200, r.text
    return r.json()["publicacion"]


# --------------------------------------------------------------------------- #
# Flujo feliz: enviar -> aprobar por OTRA persona                             #
# --------------------------------------------------------------------------- #


def test_enviar_a_revision_pasa_a_en_revision_con_autor(entorno):
    """Ana crea un borrador y lo envia a revision: pasa a en_revision, atribuido a ana."""
    autora = _cli_usuario("ana")
    pub = _crear_borrador(autora)
    r = autora.post(f"/api/aprobacion/{pub['id']}/enviar-a-revision", headers=_ORIGIN)
    assert r.status_code == 200, r.text
    actualizada = r.json()["publicacion"]
    assert actualizada["estado"] == "en_revision"
    assert actualizada["autor_nombre"] == "ana"
    assert actualizada["enviado_a_revision_en"]  # marca de tiempo puesta


def test_aprobar_por_otra_persona_pasa_a_aprobado_con_revisor(entorno):
    """Ana envia; Beto (otra cuenta) aprueba: pasa a aprobado y se registra a Beto."""
    autora = _cli_usuario("ana")
    pub = _crear_borrador(autora)
    autora.post(f"/api/aprobacion/{pub['id']}/enviar-a-revision", headers=_ORIGIN)

    revisor = _cli_usuario("beto")
    r = revisor.post(f"/api/aprobacion/{pub['id']}/aprobar", headers=_ORIGIN)
    assert r.status_code == 200, r.text
    aprobada = r.json()["publicacion"]
    assert aprobada["estado"] == "aprobado"
    assert aprobada["revisor_nombre"] == "beto"
    assert aprobada["revisado_en"]
    # La autoria original se conserva (la envio ana).
    assert aprobada["autor_nombre"] == "ana"


# --------------------------------------------------------------------------- #
# Regla de equipo: no auto-aprobar (otro par de ojos)                         #
# --------------------------------------------------------------------------- #


def test_autor_no_puede_aprobar_su_propia_pieza_409(entorno):
    """La misma cuenta que envio NO puede aprobar (separacion de funciones)."""
    autora = _cli_usuario("ana")
    pub = _crear_borrador(autora)
    autora.post(f"/api/aprobacion/{pub['id']}/enviar-a-revision", headers=_ORIGIN)
    r = autora.post(f"/api/aprobacion/{pub['id']}/aprobar", headers=_ORIGIN)
    assert r.status_code == 409
    assert "tu propia pieza" in r.json()["error"].lower()
    # Sigue en revision (no se aprobo).
    assert autora.get(f"/api/publicaciones/{pub['id']}").json()["publicacion"]["estado"] == "en_revision"


def test_admin_puede_aprobar_su_propia_pieza(entorno):
    """Un admin SI puede aprobar su propia pieza (desatasco)."""
    admin = _cli_usuario("jefa", rol="admin")
    pub = _crear_borrador(admin)
    admin.post(f"/api/aprobacion/{pub['id']}/enviar-a-revision", headers=_ORIGIN)
    r = admin.post(f"/api/aprobacion/{pub['id']}/aprobar", headers=_ORIGIN)
    assert r.status_code == 200, r.text
    assert r.json()["publicacion"]["estado"] == "aprobado"


def test_token_de_mantenimiento_puede_aprobar(entorno):
    """El acceso por token (sin usuario) es mantenimiento: puede aprobar (admin)."""
    autora = _cli_usuario("ana")
    pub = _crear_borrador(autora)
    autora.post(f"/api/aprobacion/{pub['id']}/enviar-a-revision", headers=_ORIGIN)
    mantenimiento = _cli_token()
    r = mantenimiento.post(f"/api/aprobacion/{pub['id']}/aprobar", headers=_ORIGIN)
    assert r.status_code == 200, r.text
    assert r.json()["publicacion"]["estado"] == "aprobado"


# --------------------------------------------------------------------------- #
# Rechazo: vuelve a borrador                                                  #
# --------------------------------------------------------------------------- #


def test_rechazar_devuelve_a_borrador(entorno):
    """Beto rechaza la pieza en revision de ana: vuelve a borrador, con el revisor."""
    autora = _cli_usuario("ana")
    pub = _crear_borrador(autora)
    autora.post(f"/api/aprobacion/{pub['id']}/enviar-a-revision", headers=_ORIGIN)
    revisor = _cli_usuario("beto")
    r = revisor.post(f"/api/aprobacion/{pub['id']}/rechazar", headers=_ORIGIN)
    assert r.status_code == 200, r.text
    rechazada = r.json()["publicacion"]
    assert rechazada["estado"] == "borrador"
    assert rechazada["revisor_nombre"] == "beto"


# --------------------------------------------------------------------------- #
# Transiciones invalidas                                                      #
# --------------------------------------------------------------------------- #


def test_no_se_puede_aprobar_un_borrador(entorno):
    """Aprobar una pieza que NO esta en revision -> 409."""
    autora = _cli_usuario("ana")
    pub = _crear_borrador(autora)
    revisor = _cli_usuario("beto")
    r = revisor.post(f"/api/aprobacion/{pub['id']}/aprobar", headers=_ORIGIN)
    assert r.status_code == 409
    assert "revisión" in r.json()["error"].lower()


def test_no_se_puede_enviar_a_revision_lo_ya_aprobado(entorno):
    """Solo un borrador entra a revision; una pieza ya aprobada no."""
    mantenimiento = _cli_token()
    pub = _crear_borrador(mantenimiento, estado="aprobado")
    r = mantenimiento.post(f"/api/aprobacion/{pub['id']}/enviar-a-revision", headers=_ORIGIN)
    assert r.status_code == 409


def test_transicion_pieza_inexistente_404(entorno):
    mantenimiento = _cli_token()
    r = mantenimiento.post("/api/aprobacion/nopiezaxxx/aprobar", headers=_ORIGIN)
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# La cola lista lo pendiente con quien/cuando                                 #
# --------------------------------------------------------------------------- #


def test_cola_lista_pendientes_con_quien_y_cuando(entorno):
    """La cola muestra solo las piezas en revision, con autor y marca de tiempo."""
    autora = _cli_usuario("ana")
    p1 = _crear_borrador(autora, titulo="Primera")
    p2 = _crear_borrador(autora, titulo="Segunda")
    _crear_borrador(autora, titulo="Se queda en borrador")  # no entra a la cola
    autora.post(f"/api/aprobacion/{p1['id']}/enviar-a-revision", headers=_ORIGIN)
    autora.post(f"/api/aprobacion/{p2['id']}/enviar-a-revision", headers=_ORIGIN)

    datos = autora.get("/api/aprobacion/cola").json()
    assert datos["total"] == 2
    titulos = {item["titulo"] for item in datos["cola"]}
    assert titulos == {"Primera", "Segunda"}
    for item in datos["cola"]:
        assert item["estado"] == "en_revision"
        assert item["autor_nombre"] == "ana"
        assert item["enviado_a_revision_en"]


def test_cola_vacia_cuando_no_hay_nada_en_revision(entorno):
    autora = _cli_usuario("ana")
    _crear_borrador(autora)
    datos = autora.get("/api/aprobacion/cola").json()
    assert datos == {"cola": [], "total": 0}


# --------------------------------------------------------------------------- #
# Gate A: minimo de aprobaciones para programar (item A)                       #
# --------------------------------------------------------------------------- #


def test_programar_sin_cadena_no_aplica_el_minimo(entorno):
    """Una pieza `aprobado` SIN cadena (atajo) se programa sin exigir el minimo."""
    mantenimiento = _cli_token()
    pub = _crear_borrador(mantenimiento, estado="aprobado")
    from datetime import datetime, timedelta

    fecha = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
    r = mantenimiento.post(
        f"/api/aprobacion/{pub['id']}/programar", json={"fecha": fecha}, headers=_ORIGIN
    )
    assert r.status_code == 200, r.text


def test_programar_con_cadena_simple_bloquea_por_minimo(entorno, monkeypatch):
    """Con KENI_MIN_APROBACIONES=2 y una cadena simple (1 firma), programar da 409 «1 de 2»."""
    monkeypatch.setenv("KENI_MIN_APROBACIONES", "2")
    autora = _cli_usuario("ana")
    pub = _crear_borrador(autora)
    autora.post(f"/api/aprobacion/{pub['id']}/enviar-a-revision", headers=_ORIGIN)
    revisor = _cli_usuario("beto")
    revisor.post(f"/api/aprobacion/{pub['id']}/aprobar", headers=_ORIGIN)  # 1 firma
    from datetime import datetime, timedelta

    fecha = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
    r = revisor.post(
        f"/api/aprobacion/{pub['id']}/programar", json={"fecha": fecha}, headers=_ORIGIN
    )
    assert r.status_code == 409
    assert "1 de 2" in r.json()["error"]


def test_programar_con_minimo_uno_pasa_con_una_firma(entorno, monkeypatch):
    """KENI_MIN_APROBACIONES=1: una sola firma (cadena simple) basta para programar."""
    monkeypatch.setenv("KENI_MIN_APROBACIONES", "1")
    autora = _cli_usuario("ana")
    pub = _crear_borrador(autora)
    autora.post(f"/api/aprobacion/{pub['id']}/enviar-a-revision", headers=_ORIGIN)
    revisor = _cli_usuario("beto")
    revisor.post(f"/api/aprobacion/{pub['id']}/aprobar", headers=_ORIGIN)
    from datetime import datetime, timedelta

    fecha = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
    r = revisor.post(
        f"/api/aprobacion/{pub['id']}/programar", json={"fecha": fecha}, headers=_ORIGIN
    )
    assert r.status_code == 200, r.text


# --------------------------------------------------------------------------- #
# Gate B: comentarios sin resolver bloquean programar (item B)                 #
# --------------------------------------------------------------------------- #


def test_comentario_sin_resolver_bloquea_programar(entorno, monkeypatch):
    """Un comentario abierto en el item da 409 al programar, aunque la pieza este aprobada."""
    monkeypatch.setenv("KENI_MIN_APROBACIONES", "0")  # aislar el gate B del gate A
    autora = _cli_usuario("ana")
    pub = _crear_borrador(autora, estado="aprobado")
    # El contenido padre de la publicacion (su contenido_id) recibe un comentario abierto.
    from keni_consola import repos

    plat = repos.obtener_contenido_plataforma(pub["id"])
    contenido_id = plat["contenido_id"]
    autora.post(
        f"/api/contenido/{contenido_id}/comentarios",
        json={"texto": "Revisar el dato de la fecha"},
        headers=_ORIGIN,
    )
    from datetime import datetime, timedelta

    fecha = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
    r = autora.post(
        f"/api/aprobacion/{pub['id']}/programar", json={"fecha": fecha}, headers=_ORIGIN
    )
    assert r.status_code == 409
    assert "sin resolver" in r.json()["error"].lower()
