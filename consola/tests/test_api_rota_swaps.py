"""Tests de la API de swaps de turno (HTTP, vía TestClient). Todo OFFLINE (#175).

Flujo: A (sesion) crea una solicitud para B; B acepta/rechaza; admin aprueba (que
EJECUTA el swap en `rota_turnos_trabajo`) o rechaza; A puede cancelar mientras no sea
terminal. Cubre permisos por estado, validaciones de entrada, el caso 409 cuando los
turnos han cambiado entre el "aceptado" y el "aprobar", y el flujo completo end-to-end.

Las ausencias REALES (vacaciones/baja) viven en SAP, NO aqui: el endpoint exige que los
turnos existan en `rota_turnos_trabajo` (es decir, que Elias haya propuesto/aprobado el
horario antes), si no devuelve 400 con motivo accionable.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth, repos

from .conftest import TOKEN_PRUEBA, _cliente

_ORIGIN = {"Origin": "http://testserver"}
CLAVE = "clave-de-prueba"
LUNES = "2026-05-25"
DIA_A = "2026-05-25"  # lunes
DIA_B = "2026-05-26"  # martes


# --------------------------------------------------------------------------- #
# Helpers de fixtures                                                          #
# --------------------------------------------------------------------------- #


def _cli_de(app, usuario: str) -> TestClient:
    """TestClient autenticado por SESION con el usuario `usuario` (clave fija CLAVE)."""
    cli = TestClient(app)
    r = cli.post(
        "/api/auth/login",
        json={"usuario": usuario, "password": CLAVE},
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    return cli


def _crear_horario(app, equipo: list[dict]) -> None:
    """Siembra turnos de trabajo en LUNES para los dos primeros miembros (ana, beto).

    Antes la consola PROPONIA reparto automatico; ahora Elias asigna a mano, asi que los
    tests siembran directo via `repos.crear_turno_rota`. Sembramos a cada miembro
    su turno en DIA_A y DIA_B (franjas distintas por persona para no solaparse): asi
    cualquier `_payload_swap(X, Y)` con X, Y en (ana, beto) — incluido `(ana, ana)` que
    se usa en los tests de "consigo mismo" / "destinatario inexistente" — encuentra los
    turnos en BD antes de tirar la peticion al endpoint.
    """
    del app  # ya no se usa: sembramos directo en BD.
    primero, segundo = equipo[0], equipo[1]
    for dia in (DIA_A, DIA_B):
        repos.crear_turno_rota(
            LUNES,
            dia,
            miembro_id=primero["id"],
            miembro_nombre=primero["usuario"],
            franja="matutino",
        )
        repos.crear_turno_rota(
            LUNES,
            dia,
            miembro_id=segundo["id"],
            miembro_nombre=segundo["usuario"],
            franja="vespertino",
        )


def _turno_de(app, miembro_id: str, fecha: str, franjas: tuple[str, ...]) -> dict:
    """Busca un turno de trabajo del miembro en esa fecha (cualquiera de `franjas`) en BD."""
    del app  # ya no se usa: leemos directo de BD.
    for t in repos.listar_turnos_rota(semana=LUNES):
        if t["miembro_id"] == miembro_id and t["fecha"] == fecha and t["franja"] in franjas:
            return t
    raise AssertionError(
        f"no encuentro turno del miembro {miembro_id} en {fecha} (franjas={franjas})"
    )


def _setup_basico(entorno) -> tuple:
    """App + dos miembros (ana, beto) con sesion y horario propuesto.

    Devuelve `(app, ana, beto, cli_ana, cli_beto)`. `ana` es solicitante por defecto.
    """
    app = app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)
    ana = auth.crear_usuario("ana", CLAVE, "editor")
    beto = auth.crear_usuario("beto", CLAVE, "editor")
    _crear_horario(app, [ana, beto])
    cli_ana = _cli_de(app, "ana")
    cli_beto = _cli_de(app, "beto")
    return app, ana, beto, cli_ana, cli_beto


def _setup_con_admin(entorno) -> tuple:
    """Igual que `_setup_basico` pero anade una admin (elias) con sesion."""
    app, ana, beto, cli_ana, cli_beto = _setup_basico(entorno)
    auth.crear_usuario("elias", CLAVE, "admin")
    cli_admin = _cli_de(app, "elias")
    return app, ana, beto, cli_ana, cli_beto, cli_admin


def _payload_swap(ana: dict, beto: dict, app) -> dict:
    """Cuerpo de un swap A(ana) <-> B(beto): toma franjas REALES del horario."""
    ta = _turno_de(app, ana["id"], DIA_A, ("matutino", "vespertino"))
    tb = _turno_de(app, beto["id"], DIA_B, ("matutino", "vespertino"))
    return {
        "destinatario_id": beto["id"],
        "fecha_a": ta["fecha"],
        "franja_a": ta["franja"],
        "fecha_b": tb["fecha"],
        "franja_b": tb["franja"],
        "motivo": "Cita médica",
    }


# --------------------------------------------------------------------------- #
# Crear (POST /api/rota/swaps)                                                 #
# --------------------------------------------------------------------------- #


def test_crear_swap_basico(entorno):
    app, ana, beto, cli_ana, _ = _setup_basico(entorno)
    cuerpo = _payload_swap(ana, beto, app)
    r = cli_ana.post("/api/rota/swaps", json=cuerpo, headers=_ORIGIN)
    assert r.status_code == 201, r.text
    swap = r.json()["swap"]
    assert swap["estado"] == "propuesto"
    assert swap["solicitante_id"] == ana["id"]
    assert swap["destinatario_id"] == beto["id"]
    assert swap["motivo"] == "Cita médica"


def test_crear_swap_sin_sesion_401(entorno):
    """Sin sesion no se puede solicitar (el solicitante es la sesion, no el cliente)."""
    _setup_basico(entorno)
    # El cliente por defecto entra por el token de mantenimiento (sin usuario).
    cli = _cliente()
    r = cli.post(
        "/api/rota/swaps",
        json={
            "destinatario_id": "x",
            "fecha_a": DIA_A,
            "franja_a": "matutino",
            "fecha_b": DIA_B,
            "franja_b": "vespertino",
        },
    )
    assert r.status_code == 401


def test_crear_swap_consigo_mismo_400(entorno):
    app, ana, _, cli_ana, _ = _setup_basico(entorno)
    cuerpo = _payload_swap(ana, ana, app)  # mismo id para A y B
    cuerpo["destinatario_id"] = ana["id"]
    r = cli_ana.post("/api/rota/swaps", json=cuerpo, headers=_ORIGIN)
    assert r.status_code == 400


def test_crear_swap_destinatario_inexistente_400(entorno):
    app, ana, _, cli_ana, _ = _setup_basico(entorno)
    cuerpo = _payload_swap(ana, ana, app)
    cuerpo["destinatario_id"] = "no-existe"
    r = cli_ana.post("/api/rota/swaps", json=cuerpo, headers=_ORIGIN)
    assert r.status_code == 400


def test_crear_swap_fechas_invalidas_400(entorno):
    app, ana, beto, cli_ana, _ = _setup_basico(entorno)
    cuerpo = _payload_swap(ana, beto, app)
    cuerpo["fecha_a"] = "no-fecha"
    r = cli_ana.post("/api/rota/swaps", json=cuerpo, headers=_ORIGIN)
    assert r.status_code == 400


def test_crear_swap_franja_invalida_400(entorno):
    app, ana, beto, cli_ana, _ = _setup_basico(entorno)
    cuerpo = _payload_swap(ana, beto, app)
    cuerpo["franja_b"] = "nocturno"
    r = cli_ana.post("/api/rota/swaps", json=cuerpo, headers=_ORIGIN)
    assert r.status_code == 400


def test_crear_swap_sin_turno_en_horario_400(entorno):
    """Si no existe un turno real del solicitante en (fecha_a, franja_a) -> 400 accionable."""
    app, ana, beto, cli_ana, _ = _setup_basico(entorno)
    cuerpo = _payload_swap(ana, beto, app)
    # Cambiamos la franja a una en la que ana NO trabaja ese dia (su turno es la otra).
    cuerpo["franja_a"] = (
        "vespertino" if cuerpo["franja_a"] == "matutino" else "matutino"
    )
    # Pero forzamos que la nueva franja apunte al turno del OTRO miembro (no de ana).
    # Si el turno alterno de ana ese dia es matutino/vespertino, escogemos descanso (que
    # nunca existe para ana ese dia con 2 miembros).
    cuerpo["franja_a"] = "descanso"
    r = cli_ana.post("/api/rota/swaps", json=cuerpo, headers=_ORIGIN)
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Listar (GET /api/rota/swaps)                                                  #
# --------------------------------------------------------------------------- #


def test_listar_swaps_filtra_mio(entorno):
    """`?mio=true` con sesion devuelve swaps en los que el usuario es A o B."""
    app, ana, beto, cli_ana, cli_beto = _setup_basico(entorno)
    cuerpo = _payload_swap(ana, beto, app)
    cli_ana.post("/api/rota/swaps", json=cuerpo, headers=_ORIGIN)
    # Ambos lo ven en su "mio" (ana es solicitante; beto es destinatario).
    assert len(cli_ana.get("/api/rota/swaps?mio=true").json()["swaps"]) == 1
    assert len(cli_beto.get("/api/rota/swaps?mio=true").json()["swaps"]) == 1
    # Una tercera persona NO lo ve en su "mio".
    auth.crear_usuario("caro", CLAVE, "editor")
    cli_caro = _cli_de(app, "caro")
    assert cli_caro.get("/api/rota/swaps?mio=true").json()["swaps"] == []


def test_listar_swaps_filtra_estado(entorno):
    app, ana, beto, cli_ana, _ = _setup_basico(entorno)
    cli_ana.post("/api/rota/swaps", json=_payload_swap(ana, beto, app), headers=_ORIGIN)
    r = cli_ana.get("/api/rota/swaps?estado=propuesto")
    assert r.status_code == 200
    assert len(r.json()["swaps"]) == 1
    assert cli_ana.get("/api/rota/swaps?estado=aplicado").json()["swaps"] == []


# --------------------------------------------------------------------------- #
# Aceptar (POST /api/rota/swaps/{id}/aceptar)                                  #
# --------------------------------------------------------------------------- #


def test_aceptar_swap_por_destinatario(entorno):
    app, ana, beto, cli_ana, cli_beto = _setup_basico(entorno)
    r = cli_ana.post(
        "/api/rota/swaps", json=_payload_swap(ana, beto, app), headers=_ORIGIN
    )
    swap_id = r.json()["swap"]["id"]
    ra = cli_beto.post(
        f"/api/rota/swaps/{swap_id}/aceptar",
        json={"respuesta": "Sin problema, yo te cubro."},
        headers=_ORIGIN,
    )
    assert ra.status_code == 200, ra.text
    swap = ra.json()["swap"]
    assert swap["estado"] == "aceptado"
    assert swap["respuesta_destinatario"] == "Sin problema, yo te cubro."
    assert swap["decidido_destinatario"]  # timestamp sellado


def test_aceptar_swap_por_otro_403(entorno):
    """Solo el destinatario puede aceptar (ni el solicitante ni un tercero)."""
    app, ana, beto, cli_ana, _ = _setup_basico(entorno)
    r = cli_ana.post(
        "/api/rota/swaps", json=_payload_swap(ana, beto, app), headers=_ORIGIN
    )
    swap_id = r.json()["swap"]["id"]
    # El solicitante NO puede aceptar su propio swap.
    rb = cli_ana.post(f"/api/rota/swaps/{swap_id}/aceptar", headers=_ORIGIN)
    assert rb.status_code == 403


def test_aceptar_swap_dos_veces_409(entorno):
    """Una segunda aceptacion (ya `aceptado`) -> 409 (transicion invalida)."""
    app, ana, beto, cli_ana, cli_beto = _setup_basico(entorno)
    r = cli_ana.post(
        "/api/rota/swaps", json=_payload_swap(ana, beto, app), headers=_ORIGIN
    )
    swap_id = r.json()["swap"]["id"]
    cli_beto.post(f"/api/rota/swaps/{swap_id}/aceptar", headers=_ORIGIN)
    r2 = cli_beto.post(f"/api/rota/swaps/{swap_id}/aceptar", headers=_ORIGIN)
    assert r2.status_code == 409


# --------------------------------------------------------------------------- #
# Rechazar destinatario (POST /api/rota/swaps/{id}/rechazar)                   #
# --------------------------------------------------------------------------- #


def test_rechazar_swap_destinatario(entorno):
    app, ana, beto, cli_ana, cli_beto = _setup_basico(entorno)
    r = cli_ana.post(
        "/api/rota/swaps", json=_payload_swap(ana, beto, app), headers=_ORIGIN
    )
    swap_id = r.json()["swap"]["id"]
    rb = cli_beto.post(
        f"/api/rota/swaps/{swap_id}/rechazar",
        json={"respuesta": "No puedo, tengo lo del médico."},
        headers=_ORIGIN,
    )
    assert rb.status_code == 200, rb.text
    assert rb.json()["swap"]["estado"] == "rechazado"


# --------------------------------------------------------------------------- #
# Aprobar admin (POST /api/rota/swaps/{id}/aprobar): ejecuta el swap           #
# --------------------------------------------------------------------------- #


def test_aprobar_swap_aplica_intercambio(entorno):
    """El admin aprueba un `aceptado` -> swap pasa a `aplicado` Y los miembros se
    intercambian en `rota_turnos_trabajo` (efecto observable)."""
    app, ana, beto, cli_ana, cli_beto, cli_admin = _setup_con_admin(entorno)
    cuerpo = _payload_swap(ana, beto, app)
    r = cli_ana.post("/api/rota/swaps", json=cuerpo, headers=_ORIGIN)
    swap_id = r.json()["swap"]["id"]
    cli_beto.post(f"/api/rota/swaps/{swap_id}/aceptar", headers=_ORIGIN)

    ra = cli_admin.post(
        f"/api/rota/swaps/{swap_id}/aprobar",
        json={"respuesta": "Aprobado, ojo con el relevo."},
        headers=_ORIGIN,
    )
    assert ra.status_code == 200, ra.text
    swap = ra.json()["swap"]
    assert swap["estado"] == "aplicado"
    assert swap["aplicado"]
    assert swap["decidido_admin"]
    assert swap["respuesta_admin"] == "Aprobado, ojo con el relevo."

    # Efecto en `rota_turnos_trabajo`: la franja de A pasa a B y viceversa.
    token_cli = TestClient(app, headers={"Authorization": f"Bearer {TOKEN_PRUEBA}"})
    turnos = token_cli.get(f"/api/rota/turnos?lunes={LUNES}").json()["turnos"]
    # En (fecha_a, franja_a) ahora trabaja B; en (fecha_b, franja_b) ahora A.
    en_a = next(
        t for t in turnos if t["fecha"] == cuerpo["fecha_a"] and t["franja"] == cuerpo["franja_a"]
    )
    en_b = next(
        t for t in turnos if t["fecha"] == cuerpo["fecha_b"] and t["franja"] == cuerpo["franja_b"]
    )
    assert en_a["miembro_id"] == beto["id"]
    assert en_b["miembro_id"] == ana["id"]


def test_aprobar_swap_sin_aceptar_409(entorno):
    """Aprobar un `propuesto` (sin aceptar) -> 409 (transicion invalida)."""
    app, ana, beto, cli_ana, _, cli_admin = _setup_con_admin(entorno)
    r = cli_ana.post(
        "/api/rota/swaps", json=_payload_swap(ana, beto, app), headers=_ORIGIN
    )
    swap_id = r.json()["swap"]["id"]
    ra = cli_admin.post(f"/api/rota/swaps/{swap_id}/aprobar", headers=_ORIGIN)
    assert ra.status_code == 409


def test_aprobar_swap_no_admin_403(entorno):
    """Un editor NO puede aprobar (ni el destinatario que acepto)."""
    app, ana, beto, cli_ana, cli_beto = _setup_basico(entorno)
    r = cli_ana.post(
        "/api/rota/swaps", json=_payload_swap(ana, beto, app), headers=_ORIGIN
    )
    swap_id = r.json()["swap"]["id"]
    cli_beto.post(f"/api/rota/swaps/{swap_id}/aceptar", headers=_ORIGIN)
    ra = cli_beto.post(f"/api/rota/swaps/{swap_id}/aprobar", headers=_ORIGIN)
    assert ra.status_code == 403


def test_aprobar_swap_turnos_cambiados_409_con_detalle(entorno):
    """Si entre `aceptado` y `aprobar` los turnos han cambiado a mano, 409 con detalle.

    Simula que el admin reasigna el turno de A a una TERCERA persona via PATCH y
    luego intenta aprobar el swap original -> 409 con `detalle.esperado` y
    `detalle.actual` mostrando la divergencia. Nada se aplica.
    """
    app, ana, beto, cli_ana, cli_beto, cli_admin = _setup_con_admin(entorno)
    caro = auth.crear_usuario("caro", CLAVE, "editor")
    cuerpo = _payload_swap(ana, beto, app)
    r = cli_ana.post("/api/rota/swaps", json=cuerpo, headers=_ORIGIN)
    swap_id = r.json()["swap"]["id"]
    cli_beto.post(f"/api/rota/swaps/{swap_id}/aceptar", headers=_ORIGIN)

    # El admin reasigna el turno de ana (fecha_a, franja_a) a caro (via PATCH directo).
    token_cli = TestClient(app, headers={"Authorization": f"Bearer {TOKEN_PRUEBA}"})
    turnos = token_cli.get(f"/api/rota/turnos?lunes={LUNES}").json()["turnos"]
    turno_a = next(
        t for t in turnos if t["fecha"] == cuerpo["fecha_a"] and t["franja"] == cuerpo["franja_a"]
    )
    pr = token_cli.patch(
        f"/api/rota/turnos/{turno_a['id']}",
        json={"miembro_id": caro["id"]},
    )
    assert pr.status_code == 200, pr.text

    # Ahora aprobar el swap original -> 409 (la franja A ya no la cubre ana).
    ra = cli_admin.post(f"/api/rota/swaps/{swap_id}/aprobar", headers=_ORIGIN)
    assert ra.status_code == 409, ra.text
    payload = ra.json()
    assert payload["error"]
    detalle = payload["detalle"]
    assert detalle["esperado"]["a"]["miembro_id"] == ana["id"]
    assert detalle["actual"]["a"]["miembro_id"] == caro["id"]

    # El swap NO cambio de estado (sigue aceptado), nadie se intercambio.
    swap = repos.obtener_swap_turno(swap_id)
    assert swap["estado"] == "aceptado"


# --------------------------------------------------------------------------- #
# Rechazar admin (POST /api/rota/swaps/{id}/rechazar-admin)                    #
# --------------------------------------------------------------------------- #


def test_rechazar_swap_admin(entorno):
    app, ana, beto, cli_ana, cli_beto, cli_admin = _setup_con_admin(entorno)
    r = cli_ana.post(
        "/api/rota/swaps", json=_payload_swap(ana, beto, app), headers=_ORIGIN
    )
    swap_id = r.json()["swap"]["id"]
    cli_beto.post(f"/api/rota/swaps/{swap_id}/aceptar", headers=_ORIGIN)
    ra = cli_admin.post(
        f"/api/rota/swaps/{swap_id}/rechazar-admin",
        json={"respuesta": "Ese día no, necesitamos a Beto en transmisión."},
        headers=_ORIGIN,
    )
    assert ra.status_code == 200, ra.text
    assert ra.json()["swap"]["estado"] == "rechazado_admin"


def test_rechazar_admin_sin_aceptar_409(entorno):
    app, ana, beto, cli_ana, _, cli_admin = _setup_con_admin(entorno)
    r = cli_ana.post(
        "/api/rota/swaps", json=_payload_swap(ana, beto, app), headers=_ORIGIN
    )
    swap_id = r.json()["swap"]["id"]
    ra = cli_admin.post(f"/api/rota/swaps/{swap_id}/rechazar-admin", headers=_ORIGIN)
    assert ra.status_code == 409


def test_rechazar_admin_no_admin_403(entorno):
    app, ana, beto, cli_ana, cli_beto = _setup_basico(entorno)
    r = cli_ana.post(
        "/api/rota/swaps", json=_payload_swap(ana, beto, app), headers=_ORIGIN
    )
    swap_id = r.json()["swap"]["id"]
    cli_beto.post(f"/api/rota/swaps/{swap_id}/aceptar", headers=_ORIGIN)
    ra = cli_beto.post(f"/api/rota/swaps/{swap_id}/rechazar-admin", headers=_ORIGIN)
    assert ra.status_code == 403


# --------------------------------------------------------------------------- #
# Cancelar (POST /api/rota/swaps/{id}/cancelar)                                 #
# --------------------------------------------------------------------------- #


def test_cancelar_swap_solicitante(entorno):
    app, ana, beto, cli_ana, _ = _setup_basico(entorno)
    r = cli_ana.post(
        "/api/rota/swaps", json=_payload_swap(ana, beto, app), headers=_ORIGIN
    )
    swap_id = r.json()["swap"]["id"]
    rc = cli_ana.post(f"/api/rota/swaps/{swap_id}/cancelar", headers=_ORIGIN)
    assert rc.status_code == 200, rc.text
    assert rc.json()["swap"]["estado"] == "cancelado"


def test_cancelar_swap_aceptado_aun_se_puede(entorno):
    """Cancelar es valido en `propuesto` Y en `aceptado` (no es terminal aun)."""
    app, ana, beto, cli_ana, cli_beto = _setup_basico(entorno)
    r = cli_ana.post(
        "/api/rota/swaps", json=_payload_swap(ana, beto, app), headers=_ORIGIN
    )
    swap_id = r.json()["swap"]["id"]
    cli_beto.post(f"/api/rota/swaps/{swap_id}/aceptar", headers=_ORIGIN)
    rc = cli_ana.post(f"/api/rota/swaps/{swap_id}/cancelar", headers=_ORIGIN)
    assert rc.status_code == 200, rc.text
    assert rc.json()["swap"]["estado"] == "cancelado"


def test_cancelar_swap_por_otro_403(entorno):
    app, ana, beto, cli_ana, cli_beto = _setup_basico(entorno)
    r = cli_ana.post(
        "/api/rota/swaps", json=_payload_swap(ana, beto, app), headers=_ORIGIN
    )
    swap_id = r.json()["swap"]["id"]
    rc = cli_beto.post(f"/api/rota/swaps/{swap_id}/cancelar", headers=_ORIGIN)
    assert rc.status_code == 403


def test_cancelar_swap_rechazado_409(entorno):
    """Cancelar uno terminal (`rechazado`) -> 409 (transicion invalida)."""
    app, ana, beto, cli_ana, cli_beto = _setup_basico(entorno)
    r = cli_ana.post(
        "/api/rota/swaps", json=_payload_swap(ana, beto, app), headers=_ORIGIN
    )
    swap_id = r.json()["swap"]["id"]
    cli_beto.post(f"/api/rota/swaps/{swap_id}/rechazar", headers=_ORIGIN)
    rc = cli_ana.post(f"/api/rota/swaps/{swap_id}/cancelar", headers=_ORIGIN)
    assert rc.status_code == 409


# --------------------------------------------------------------------------- #
# Robustez: id inexistente                                                     #
# --------------------------------------------------------------------------- #


def test_aceptar_swap_inexistente_404(entorno):
    app, _, _, _, cli_beto = _setup_basico(entorno)
    r = cli_beto.post("/api/rota/swaps/no-existe/aceptar", headers=_ORIGIN)
    assert r.status_code == 404
