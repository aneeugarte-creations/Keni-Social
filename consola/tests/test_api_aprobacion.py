"""Tests de la cola de aprobacion de equipo (#9, Fase 3). OFFLINE, DB en tmp.

Cubre el flujo borrador -> en_revision con identidad real (login): quien envia, quien da
los OK (cuatro ojos), la regla de dos personas distintas, el rechazo (vuelta a borrador) y la
cola que lista lo pendiente con quien/cuando.

COLAPSO 2026-06: ya no hay estado de reposo `aprobado`. Cuando la cadena junta sus 2 OK, la
pieza se AUTO-PROGRAMA si hay franja/hueco; si no (como en este entorno OFFLINE sin franjas),
se queda `en_revision` con la cadena ya aprobada. Aquí comprobamos esa lógica de cadena (el
camino "se auto-programa al hueco" vive en `test_auto_programar.py`). Además, el AUTOR puede dar
uno de los dos OK: la única regla es que los dos OK los den DOS personas distintas.

Reusa el aislamiento de `entorno` y los patrones de `test_atribucion` (login real para
sesiones distintas). La auth/CSRF/sesion NO se toca; el acceso por TOKEN de bootstrap
cuenta como mantenimiento (admin) y puede saltarse la regla de cargo (no la de dos personas).
"""

from __future__ import annotations

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth, repos

from .conftest import TOKEN_PRUEBA

_ORIGIN = {"Origin": "http://testserver"}
_CLAVE = "clave-de-prueba-123"
_MARCA = "unotv"


def _app(bootstrap=False):
    return app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=bootstrap)


def _cli_usuario(usuario: str, rol: str = "editor", cargo: str = "") -> TestClient:
    """TestClient con SESION de `usuario` (login real): atribuye al crear/enviar/aprobar."""
    auth.crear_usuario(usuario, _CLAVE, rol, cargo=cargo)
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
    r = cli.post("/api/piezas", json=base, headers=_ORIGIN)
    assert r.status_code == 200, r.text
    return r.json()["pieza"]


def _cadena_aprobada(pid: str) -> bool:
    """True si la cadena de la pieza juntó TODOS sus OK (los niveles humanos en `aprobado`)."""
    niveles = repos.listar_aprobaciones(pid)
    return bool(niveles) and all(n["decision"] == "aprobado" for n in niveles)


# --------------------------------------------------------------------------- #
# Flujo feliz: enviar -> los 2 OK de personas distintas cierran la cadena      #
# --------------------------------------------------------------------------- #


def test_enviar_a_revision_pasa_a_en_revision_con_autor(entorno):
    """Ana crea un borrador y lo envia a revision: pasa a en_revision, atribuido a ana."""
    autora = _cli_usuario("ana")
    pub = _crear_borrador(autora)
    r = autora.post(f"/api/aprobacion/{pub['id']}/enviar-a-revision", headers=_ORIGIN)
    assert r.status_code == 200, r.text
    actualizada = r.json()["pieza"]
    assert actualizada["estado"] == "en_revision"
    assert actualizada["autor_nombre"] == "ana"
    assert actualizada["enviado_a_revision_en"]  # marca de tiempo puesta


def test_dos_ok_de_personas_distintas_cierran_la_cadena(entorno):
    """Ana envia; Beto da el 1er OK (sigue en revision) y Caro el 2o: cadena aprobada.

    La cadena por defecto del flujo "dale el OK" son DOS niveles humanos (Edición +
    Coordinación): hace falta el OK de DOS personas distintas para cerrarla. Sin franja
    configurada la pieza se queda `en_revision` (la cadena ya aprobada espera hueco).
    """
    autora = _cli_usuario("ana")
    pub = _crear_borrador(autora)
    autora.post(f"/api/aprobacion/{pub['id']}/enviar-a-revision", headers=_ORIGIN)

    # 1er OK (Beto): aprueba el nivel "Edición" pero AÚN no basta (falta el 2o OK).
    beto = _cli_usuario("beto")
    r1 = beto.post(f"/api/aprobacion/{pub['id']}/aprobar", headers=_ORIGIN)
    assert r1.status_code == 200, r1.text
    assert r1.json()["pieza"]["estado"] == "en_revision"
    assert not _cadena_aprobada(pub["id"])  # falta el 2o OK

    # 2o OK (Caro, otra persona): cierra la cadena. Sin franja -> sigue en_revision.
    caro = _cli_usuario("caro")
    r2 = caro.post(f"/api/aprobacion/{pub['id']}/aprobar", headers=_ORIGIN)
    assert r2.status_code == 200, r2.text
    aprobada = r2.json()["pieza"]
    assert aprobada["estado"] == "en_revision"
    assert _cadena_aprobada(pub["id"])  # los 2 OK ya están
    assert aprobada["revisor_nombre"] == "caro"
    assert aprobada["revisado_en"]
    # La autoria original se conserva (la envio ana).
    assert aprobada["autor_nombre"] == "ana"


def test_enviar_a_revision_monta_los_dos_niveles_de_ok(entorno):
    """Mandar a revisión crea la cadena por defecto: dos OK (Edición + Coordinación)."""
    autora = _cli_usuario("ana")
    pub = _crear_borrador(autora)
    autora.post(f"/api/aprobacion/{pub['id']}/enviar-a-revision", headers=_ORIGIN)
    niveles = repos.listar_aprobaciones(pub["id"])
    etiquetas = [n["etiqueta"] for n in sorted(niveles, key=lambda n: n["nivel"])]
    assert etiquetas == ["Edición", "Coordinación"]
    assert all(n["decision"] == "pendiente" for n in niveles)


def test_misma_persona_no_puede_dar_los_dos_ok(entorno):
    """Quien ya dio un OK no puede dar el otro: el 2o OK lo da OTRA persona (409)."""
    autora = _cli_usuario("ana")
    pub = _crear_borrador(autora)
    autora.post(f"/api/aprobacion/{pub['id']}/enviar-a-revision", headers=_ORIGIN)
    beto = _cli_usuario("beto")
    assert beto.post(f"/api/aprobacion/{pub['id']}/aprobar", headers=_ORIGIN).status_code == 200
    # Beto intenta dar también el 2o OK (nivel Coordinación): bloqueado.
    r = beto.post(f"/api/aprobacion/{pub['id']}/aprobar", headers=_ORIGIN)
    assert r.status_code == 409
    assert "otra persona" in r.json()["error"].lower()
    assert autora.get(f"/api/piezas/{pub['id']}").json()["pieza"]["estado"] == "en_revision"


# --------------------------------------------------------------------------- #
# El AUTOR puede dar uno de los dos OK (cuatro ojos = dos personas distintas)  #
# --------------------------------------------------------------------------- #


def test_autor_puede_dar_un_ok_pero_no_los_dos(entorno):
    """El autor SÍ da uno de los OK; el otro lo da otra persona (la regla es DOS personas)."""
    autora = _cli_usuario("ana")
    pub = _crear_borrador(autora)
    autora.post(f"/api/aprobacion/{pub['id']}/enviar-a-revision", headers=_ORIGIN)
    # 1er OK: la propia autora (ya permitido: cualquiera, incluido el autor).
    r1 = autora.post(f"/api/aprobacion/{pub['id']}/aprobar", headers=_ORIGIN)
    assert r1.status_code == 200, r1.text
    assert r1.json()["pieza"]["estado"] == "en_revision"
    # La autora NO puede dar también el 2o OK (misma persona): 409.
    r2 = autora.post(f"/api/aprobacion/{pub['id']}/aprobar", headers=_ORIGIN)
    assert r2.status_code == 409
    assert "otra persona" in r2.json()["error"].lower()
    # Otra persona cierra la cadena.
    beto = _cli_usuario("beto")
    r3 = beto.post(f"/api/aprobacion/{pub['id']}/aprobar", headers=_ORIGIN)
    assert r3.status_code == 200, r3.text
    assert _cadena_aprobada(pub["id"])


# --------------------------------------------------------------------------- #
# Reset de aprobaciones al EDITAR el contenido (como reescribir un PR aprobado) #
# --------------------------------------------------------------------------- #


def test_editar_contenido_con_ok_humano_resetea_a_borrador_y_limpia_cadena(entorno):
    """Editar el CONTENIDO de una pieza con un OK humano la devuelve a borrador y borra la cadena."""
    autora = _cli_usuario("ana")
    pub = _crear_borrador(autora)
    autora.post(f"/api/aprobacion/{pub['id']}/enviar-a-revision", headers=_ORIGIN)
    beto = _cli_usuario("beto")
    assert beto.post(f"/api/aprobacion/{pub['id']}/aprobar", headers=_ORIGIN).status_code == 200
    # Hay un OK humano (Edición de beto); editar el contenido lo invalida -> vuelve a borrador.
    r = autora.put(
        f"/api/piezas/{pub['id']}", json={"contenido": "Cuerpo reescrito"}, headers=_ORIGIN
    )
    assert r.status_code == 200, r.text
    assert r.json()["pieza"]["estado"] == "borrador"
    # La cadena queda LIMPIA: las aprobaciones previas dejan de existir.
    assert repos.listar_aprobaciones(pub["id"]) == []


def test_editar_en_revision_sin_ok_humano_no_resetea(entorno):
    """Sin OK humano que perder, editar NO churnea: la pieza sigue en revisión."""
    autora = _cli_usuario("ana")
    pub = _crear_borrador(autora)
    autora.post(f"/api/aprobacion/{pub['id']}/enviar-a-revision", headers=_ORIGIN)
    r = autora.put(
        f"/api/piezas/{pub['id']}", json={"contenido": "Solo retoque"}, headers=_ORIGIN
    )
    assert r.status_code == 200, r.text
    assert r.json()["pieza"]["estado"] == "en_revision"


# --------------------------------------------------------------------------- #
# Override: admin / coordinador fuerza la aprobación (se salta la cadena)      #
# --------------------------------------------------------------------------- #


def test_admin_fuerza_aprobacion_saltando_la_cadena(entorno):
    """Un admin fuerza: la pieza en revisión cierra su cadena sin el segundo par de ojos.

    Sin franja la pieza se queda `en_revision`, pero la cadena queda aprobada (el override
    selló todos los niveles); el camino "se auto-programa" lo cubre `test_auto_programar.py`.
    """
    autora = _cli_usuario("ana")
    pub = _crear_borrador(autora)
    autora.post(f"/api/aprobacion/{pub['id']}/enviar-a-revision", headers=_ORIGIN)
    admin = _cli_usuario("jefa", rol="admin")
    r = admin.post(f"/api/aprobacion/{pub['id']}/forzar", headers=_ORIGIN)
    assert r.status_code == 200, r.text
    assert r.json()["pieza"]["estado"] == "en_revision"
    assert _cadena_aprobada(pub["id"])


def test_coordinador_puede_forzar(entorno):
    """Un coordinador (cargo `coordinador_redes`) también puede forzar la aprobación."""
    autora = _cli_usuario("ana")
    pub = _crear_borrador(autora)
    autora.post(f"/api/aprobacion/{pub['id']}/enviar-a-revision", headers=_ORIGIN)
    coord = _cli_usuario("elias", rol="editor", cargo="coordinador_redes")
    r = coord.post(f"/api/aprobacion/{pub['id']}/forzar", headers=_ORIGIN)
    assert r.status_code == 200, r.text
    assert _cadena_aprobada(pub["id"])


def test_editor_normal_no_puede_forzar_403(entorno):
    """Un editor sin cargo de coordinación NO puede forzar (403): no se salta la cadena."""
    autora = _cli_usuario("ana")
    pub = _crear_borrador(autora)
    autora.post(f"/api/aprobacion/{pub['id']}/enviar-a-revision", headers=_ORIGIN)
    beto = _cli_usuario("beto")  # editor, sin cargo
    r = beto.post(f"/api/aprobacion/{pub['id']}/forzar", headers=_ORIGIN)
    assert r.status_code == 403
    assert autora.get(f"/api/piezas/{pub['id']}").json()["pieza"]["estado"] == "en_revision"


def test_forzar_solo_en_revision_409(entorno):
    """Forzar una pieza que NO está en revisión (borrador) responde 409."""
    admin = _cli_usuario("jefa", rol="admin")
    pub = _crear_borrador(admin)
    r = admin.post(f"/api/aprobacion/{pub['id']}/forzar", headers=_ORIGIN)
    assert r.status_code == 409


# --------------------------------------------------------------------------- #
# Regla de equipo: dos personas distintas (ni el admin firma los dos OK)       #
# --------------------------------------------------------------------------- #


def test_admin_no_puede_dar_los_dos_ok_el_mismo(entorno):
    """Ni el admin da los DOS OK: el segundo par de ojos no vale si es la misma persona.

    El admin desatasca otras reglas (cargo), pero NO puede firmar ambos OK: el 1er OK pasa; el
    2o (mismo admin) lo bloquea (409). El 2o lo da OTRA persona y cierra la cadena.
    """
    admin = _cli_usuario("jefa", rol="admin")
    pub = _crear_borrador(admin)
    admin.post(f"/api/aprobacion/{pub['id']}/enviar-a-revision", headers=_ORIGIN)
    # 1er OK (admin sobre su propia pieza): permitido, sigue en revisión.
    assert admin.post(f"/api/aprobacion/{pub['id']}/aprobar", headers=_ORIGIN).status_code == 200
    # 2o OK (mismo admin): bloqueado, hace falta otra persona.
    r = admin.post(f"/api/aprobacion/{pub['id']}/aprobar", headers=_ORIGIN)
    assert r.status_code == 409
    assert "otra persona" in r.json()["error"].lower()
    assert admin.get(f"/api/piezas/{pub['id']}").json()["pieza"]["estado"] == "en_revision"
    # Otra persona (otro admin distinto) sí cierra la cadena.
    jefe2 = _cli_usuario("jefe2", rol="admin")
    r2 = jefe2.post(f"/api/aprobacion/{pub['id']}/aprobar", headers=_ORIGIN)
    assert r2.status_code == 200, r2.text
    assert _cadena_aprobada(pub["id"])


def test_token_de_mantenimiento_puede_aprobar(entorno):
    """El acceso por token (sin usuario) es mantenimiento: da ambos OK (admin)."""
    autora = _cli_usuario("ana")
    pub = _crear_borrador(autora)
    autora.post(f"/api/aprobacion/{pub['id']}/enviar-a-revision", headers=_ORIGIN)
    mantenimiento = _cli_token()
    assert mantenimiento.post(f"/api/aprobacion/{pub['id']}/aprobar", headers=_ORIGIN).status_code == 200
    r = mantenimiento.post(f"/api/aprobacion/{pub['id']}/aprobar", headers=_ORIGIN)
    assert r.status_code == 200, r.text
    assert _cadena_aprobada(pub["id"])


# --------------------------------------------------------------------------- #
# Dislike: un solo rechazo NO basta; dos (de dos personas) vuelven a borrador  #
# --------------------------------------------------------------------------- #


def test_un_dislike_no_devuelve_a_borrador(entorno):
    """Un solo dislike (Beto) NO devuelve a borrador: la pieza sigue en revisión (falta el 2º)."""
    autora = _cli_usuario("ana")
    pub = _crear_borrador(autora)
    autora.post(f"/api/aprobacion/{pub['id']}/enviar-a-revision", headers=_ORIGIN)
    beto = _cli_usuario("beto")
    r = beto.post(f"/api/aprobacion/{pub['id']}/rechazar", headers=_ORIGIN)
    assert r.status_code == 200, r.text
    assert r.json()["pieza"]["estado"] == "en_revision"


def test_dos_dislikes_de_personas_distintas_devuelven_a_borrador(entorno):
    """Dos dislikes (Beto + Caro) alcanzan el umbral: la pieza vuelve a borrador, con el revisor."""
    autora = _cli_usuario("ana")
    pub = _crear_borrador(autora)
    autora.post(f"/api/aprobacion/{pub['id']}/enviar-a-revision", headers=_ORIGIN)
    beto = _cli_usuario("beto")
    assert beto.post(f"/api/aprobacion/{pub['id']}/rechazar", headers=_ORIGIN).status_code == 200
    caro = _cli_usuario("caro")
    r = caro.post(f"/api/aprobacion/{pub['id']}/rechazar", headers=_ORIGIN)
    assert r.status_code == 200, r.text
    rechazada = r.json()["pieza"]
    assert rechazada["estado"] == "borrador"
    assert rechazada["revisor_nombre"] == "caro"


def test_deshacer_quita_el_ok_y_vuelve_a_revision(entorno):
    """Beto da su OK y luego lo RETIRA (deshacer): su nivel vuelve a pendiente, pieza en revisión."""
    autora = _cli_usuario("ana")
    pub = _crear_borrador(autora)
    autora.post(f"/api/aprobacion/{pub['id']}/enviar-a-revision", headers=_ORIGIN)
    beto = _cli_usuario("beto")
    assert beto.post(f"/api/aprobacion/{pub['id']}/aprobar", headers=_ORIGIN).status_code == 200
    # Beto retira su OK: su nivel vuelve a pendiente (sin decisor) y no queda ningún OK humano.
    r = beto.post(f"/api/aprobacion/{pub['id']}/deshacer", headers=_ORIGIN)
    assert r.status_code == 200, r.text
    assert r.json()["pieza"]["estado"] == "en_revision"
    niveles = repos.listar_aprobaciones(pub["id"])
    assert all(n["decision"] == "pendiente" and not n["decisor_id"] for n in niveles)


def test_deshacer_dislike_tras_like_y_remarcar(entorno):
    """Toggle del feed: Beto da OK, lo quita (deshacer) y luego marca dislike sobre el mismo nivel."""
    autora = _cli_usuario("ana")
    pub = _crear_borrador(autora)
    autora.post(f"/api/aprobacion/{pub['id']}/enviar-a-revision", headers=_ORIGIN)
    beto = _cli_usuario("beto")
    assert beto.post(f"/api/aprobacion/{pub['id']}/aprobar", headers=_ORIGIN).status_code == 200
    assert beto.post(f"/api/aprobacion/{pub['id']}/deshacer", headers=_ORIGIN).status_code == 200
    # Ya sin su OK, Beto marca un dislike: válido (un solo dislike no rechaza todavía).
    r = beto.post(f"/api/aprobacion/{pub['id']}/rechazar", headers=_ORIGIN)
    assert r.status_code == 200, r.text
    assert r.json()["pieza"]["estado"] == "en_revision"


def test_deshacer_sin_decision_propia_da_409(entorno):
    """Deshacer sin haber decidido nada en la pieza responde 409 (no hay qué retirar)."""
    autora = _cli_usuario("ana")
    pub = _crear_borrador(autora)
    autora.post(f"/api/aprobacion/{pub['id']}/enviar-a-revision", headers=_ORIGIN)
    beto = _cli_usuario("beto")
    r = beto.post(f"/api/aprobacion/{pub['id']}/deshacer", headers=_ORIGIN)
    assert r.status_code == 409


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


def test_no_se_puede_enviar_a_revision_lo_no_borrador(entorno):
    """Solo un borrador entra a revision; una pieza ya programada no."""
    mantenimiento = _cli_token()
    pub = _crear_borrador(mantenimiento, estado="programado")
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
    """Una pieza `en_revision` SIN cadena (atajo) se programa sin exigir el minimo."""
    mantenimiento = _cli_token()
    pub = _crear_borrador(mantenimiento, estado="en_revision")
    from datetime import datetime, timedelta

    fecha = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
    r = mantenimiento.post(
        f"/api/aprobacion/{pub['id']}/programar", json={"fecha": fecha}, headers=_ORIGIN
    )
    assert r.status_code == 200, r.text


def test_programar_bloquea_si_faltan_aprobaciones_para_el_minimo(entorno, monkeypatch):
    """Con KENI_MIN_APROBACIONES=3 y los dos OK (2 firmas), programar da 409 «2 de 3»."""
    monkeypatch.setenv("KENI_MIN_APROBACIONES", "3")
    autora = _cli_usuario("ana")
    pub = _crear_borrador(autora)
    autora.post(f"/api/aprobacion/{pub['id']}/enviar-a-revision", headers=_ORIGIN)
    # Los dos OK (Beto + Caro) cierran la cadena con 2 firmas, pero el mínimo pide 3.
    _cli_usuario("beto").post(f"/api/aprobacion/{pub['id']}/aprobar", headers=_ORIGIN)
    caro = _cli_usuario("caro")
    caro.post(f"/api/aprobacion/{pub['id']}/aprobar", headers=_ORIGIN)
    from datetime import datetime, timedelta

    fecha = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
    r = caro.post(
        f"/api/aprobacion/{pub['id']}/programar", json={"fecha": fecha}, headers=_ORIGIN
    )
    assert r.status_code == 409
    assert "2 de 3" in r.json()["error"]


def test_programar_pasa_con_los_dos_ok(entorno, monkeypatch):
    """KENI_MIN_APROBACIONES=2: los dos OK (de dos personas) bastan para programar a mano."""
    monkeypatch.setenv("KENI_MIN_APROBACIONES", "2")
    autora = _cli_usuario("ana")
    pub = _crear_borrador(autora)
    autora.post(f"/api/aprobacion/{pub['id']}/enviar-a-revision", headers=_ORIGIN)
    _cli_usuario("beto").post(f"/api/aprobacion/{pub['id']}/aprobar", headers=_ORIGIN)
    caro = _cli_usuario("caro")
    caro.post(f"/api/aprobacion/{pub['id']}/aprobar", headers=_ORIGIN)
    from datetime import datetime, timedelta

    fecha = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
    r = caro.post(
        f"/api/aprobacion/{pub['id']}/programar", json={"fecha": fecha}, headers=_ORIGIN
    )
    assert r.status_code == 200, r.text
    assert r.json()["pieza"]["estado"] == "programado"


# --------------------------------------------------------------------------- #
# Gate B: comentarios sin resolver bloquean programar (item B)                 #
# --------------------------------------------------------------------------- #


def test_comentario_sin_resolver_bloquea_programar(entorno, monkeypatch):
    """Un comentario abierto en el item da 409 al programar, aunque la pieza esté lista."""
    monkeypatch.setenv("KENI_MIN_APROBACIONES", "0")  # aislar el gate B del gate A
    autora = _cli_usuario("ana")
    pub = _crear_borrador(autora, estado="en_revision")
    # El contenido padre de la pieza (su publicacion_id) recibe un comentario abierto.
    plat = repos.obtener_pieza_fila(pub["id"])
    publicacion_id = plat["publicacion_id"]
    autora.post(
        f"/api/publicaciones/{publicacion_id}/comentarios",
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


# --------------------------------------------------------------------------- #
# TOCTOU: la transicion de estado va GUARDADA (CAS); un segundo intento -> 409 #
# --------------------------------------------------------------------------- #


def test_segundo_enviar_a_revision_da_409_sin_duplicar_cadena(entorno):
    """Un segundo enviar-a-revision sobre una pieza YA en revision da 409 y no monta otra cadena.

    Espeja el doble-click: dos envios secuenciales del mismo borrador. El primero transiciona
    borrador->en_revision (CAS) y monta la cadena; el segundo ya no esta en `borrador`, asi que
    el CAS no aplica -> 409, y NO crea una segunda cadena (no se duplican niveles).
    """
    autora = _cli_usuario("ana")
    pub = _crear_borrador(autora)
    r1 = autora.post(f"/api/aprobacion/{pub['id']}/enviar-a-revision", headers=_ORIGIN)
    assert r1.status_code == 200, r1.text
    cadena_1 = repos.listar_aprobaciones(pub["id"])
    assert len(cadena_1) >= 1  # se montó una cadena

    r2 = autora.post(f"/api/aprobacion/{pub['id']}/enviar-a-revision", headers=_ORIGIN)
    assert r2.status_code == 409  # el estado cambió: no se reenvía
    # La cadena NO se duplicó: mismos niveles (mismos ids) que tras el primer envío.
    cadena_2 = repos.listar_aprobaciones(pub["id"])
    assert [n["id"] for n in cadena_2] == [n["id"] for n in cadena_1]


def test_segundo_programar_da_409_si_ya_no_esta_en_revision(entorno, monkeypatch):
    """Programar dos veces: el primero mueve en_revision->programado (CAS); el segundo da 409.

    Tras programar, la pieza ya no esta `en_revision`; el CAS de la transicion no aplica y el
    segundo intento recibe 409 ("el estado cambió"), sin re-escribir la fecha.
    """
    monkeypatch.setenv("KENI_MIN_APROBACIONES", "0")  # aislar del gate A
    from datetime import datetime, timedelta

    autora = _cli_usuario("ana")
    pub = _crear_borrador(autora, estado="en_revision")
    fecha = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")

    r1 = autora.post(
        f"/api/aprobacion/{pub['id']}/programar", json={"fecha": fecha}, headers=_ORIGIN
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["pieza"]["estado"] == "programado"

    r2 = autora.post(
        f"/api/aprobacion/{pub['id']}/programar", json={"fecha": fecha}, headers=_ORIGIN
    )
    assert r2.status_code == 409  # ya no está en revisión: el CAS no aplica


# --------------------------------------------------------------------------- #
# «Adelante»: botón único del hilo que zanja la objeción y empuja la pieza      #
# --------------------------------------------------------------------------- #


def test_adelante_sobre_veto_ia_lo_zanja_y_lo_puede_cualquiera(entorno, monkeypatch):
    """«Adelante» (cualquiera del equipo, SIN cargo de coordinación) cierra la objeción de la
    Crítica IA: marca su comentario resuelto y voltea el veto a aprobado, sin tocar los OK
    humanos. Sin franja la pieza se queda `en_revision` (programada=False), pero desbloqueada."""
    from keni_consola import config
    from keni_consola.dominio import colaboracion, critica_ia

    monkeypatch.setattr(config, "critica_ia_activa", lambda: True)
    monkeypatch.setattr(critica_ia, "lanzar_para_publicacion", lambda *a, **k: None)

    autora = _cli_usuario("ana")
    beto = _cli_usuario("beto")
    caro = _cli_usuario("caro")
    pub = _crear_borrador(autora)
    autora.post(f"/api/aprobacion/{pub['id']}/enviar-a-revision", headers=_ORIGIN)
    # Los 2 OK humanos (dos personas) dejan SOLO el nivel «Crítica IA» pendiente.
    assert beto.post(f"/api/aprobacion/{pub['id']}/aprobar", headers=_ORIGIN).status_code == 200
    assert caro.post(f"/api/aprobacion/{pub['id']}/aprobar", headers=_ORIGIN).status_code == 200
    # La IA RECHAZA: deja dislike en su nivel + un comentario sin resolver (gate B) que frena.
    critica_ia.aplicar_revision(
        pub["id"],
        {
            "veredicto": "rechaza",
            "comentario": "La imagen es sintética; cámbiala por una foto real.",
            "problemas": [],
        },
    )
    plat = repos.obtener_pieza_fila(pub["id"])
    assert repos.comentarios_sin_resolver(plat["publicacion_id"], pub["id"]) >= 1
    coment = repos.listar_comentarios(plat["publicacion_id"])[0]
    assert coment["autor_id"] == colaboracion.DECISOR_CRITICA_ID

    # Un EDITOR normal (sin cargo) pulsa «Adelante» sobre el comentario de la IA.
    deno = _cli_usuario("deno")
    r = deno.post(f"/api/comentarios/{coment['id']}/adelante", headers=_ORIGIN)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["comentario"]["resuelto"] is True
    assert "programada" in cuerpo  # el front decide el aviso según salga o no a su hueco
    # El veto se volteó a aprobado y el gate B quedó limpio: la pieza está desbloqueada.
    ia = colaboracion.nivel_critica_ia(repos.listar_aprobaciones(pub["id"]))
    assert ia["decision"] == "aprobado"
    assert repos.comentarios_sin_resolver(plat["publicacion_id"], pub["id"]) == 0


def test_adelante_sobre_comentario_humano_solo_lo_resuelve(entorno):
    """«Adelante» sobre un comentario humano normal lo marca resuelto (no toca la cadena); sin los
    2 OK no programa, pero deja el hilo cerrado. Mismo botón, mismo gesto, cualquiera lo pulsa."""
    autora = _cli_usuario("ana")
    beto = _cli_usuario("beto")
    pub = _crear_borrador(autora)
    autora.post(f"/api/aprobacion/{pub['id']}/enviar-a-revision", headers=_ORIGIN)
    plat = repos.obtener_pieza_fila(pub["id"])
    r = beto.post(
        f"/api/publicaciones/{plat['publicacion_id']}/comentarios",
        json={"texto": "Revisa el copy", "pieza_id": pub["id"]},
        headers=_ORIGIN,
    )
    assert r.status_code == 201, r.text
    coment_id = r.json()["comentario"]["id"]

    ra = autora.post(f"/api/comentarios/{coment_id}/adelante", headers=_ORIGIN)
    assert ra.status_code == 200, ra.text
    assert ra.json()["comentario"]["resuelto"] is True
    assert ra.json()["programada"] is False


def test_adelante_comentario_inexistente_404(entorno):
    """Sobre un comentario que ya no existe: 404 limpio (sin tocar nada)."""
    autora = _cli_usuario("ana")
    r = autora.post("/api/comentarios/no-existe/adelante", headers=_ORIGIN)
    assert r.status_code == 404
