"""Tests del segundo factor PASSKEYS / WebAuthn (MFA), GATEADO por `KENI_CONSOLA_MFA` (def OFF).

QUE SE CUBRE (y que NO):

  - Flag OFF => el login es IDENTICO a hoy (NUNCA se pide segundo factor), aunque el usuario
    tenga una passkey en BD. Esta es la garantia critica del piloto.
  - Generacion de OPCIONES (registro y login): devuelven un challenge bien formado y siembran
    la cookie Fernet correspondiente; el challenge NO se confia desde el cliente.
  - Round-trip de la cookie de CHALLENGE (Fernet, atada al usuario + TTL).
  - Obligatoriedad: global (`KENI_CONSOLA_MFA`), de admins (`KENI_CONSOLA_MFA_ADMIN`) y
    per-usuario (`mfa_requerido`); gracia + reset admin; anti-lockout sin clave.
  - La cookie PRE-AUTH no abre endpoints protegidos.
  - Fail-safe (503) cuando falta `KENI_CONSOLA_MFA_KEY` con el flag ON.
  - NO hay codigos de recuperacion (se retiraron): la recuperacion de cuenta es por reset de MFA
    de un superadmin desde Usuarios.

  - NO se ejercita la verificacion criptografica REAL de una assertion/registration WebAuthn:
    eso exige un autenticador (Face ID / llave) que firme un challenge, imposible en CI sin
    hardware/virtual authenticator. En su lugar, MOCKEAMOS `auth.verificar_registro` /
    `auth.verificar_login` en la FRONTERA y comprobamos el FLUJO alrededor (persistencia de la
    credencial, `mfa_activo`, actualizacion del sign_count y creacion de la sesion real). Lo que
    SI es real: las option builders de py_webauthn (generan un challenge) y el round-trip de la cookie.

Reusa el aislamiento de `entorno` (Postgres de pruebas; se salta si no hay) y las apps con
TOKEN de prueba, igual que `test_auth.py`.
"""

from __future__ import annotations

import json

import pytest
from cryptography.fernet import Fernet
from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth
from keni_consola.api import auth as api_auth

from .conftest import TOKEN_PRUEBA

_ORIGIN = {"Origin": "http://testserver"}
CLAVE = "clave-de-prueba"

# Clave Fernet valida y fija para los tests (NO es un secreto real: es de prueba).
_MFA_KEY = Fernet.generate_key().decode("ascii")


def _app(bootstrap=False):
    return app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=bootstrap)


def _cli(bootstrap=False) -> TestClient:
    return TestClient(_app(bootstrap=bootstrap))


def _login(c: TestClient, usuario: str, password: str):
    return c.post(
        "/api/auth/login", json={"usuario": usuario, "password": password}, headers=_ORIGIN
    )


def _credencial_falsa(usuario_id: str, *, credential_id: str = "cred-1", sign_count: int = 0):
    """Inserta una passkey directamente (sin ceremonia real) para tests de flujo."""
    auth.guardar_credencial_mfa(
        usuario_id,
        credential_id=credential_id,
        public_key="pubkey-b64url",
        sign_count=sign_count,
        transports=json.dumps(["internal"]),
        nombre="Test",
    )


def _registrar_passkey_via_api(c: TestClient, monkeypatch, *, credential_id="cred-1"):
    """Enrola una passkey por la API mockeando la verificacion criptografica en la frontera.

    Devuelve la respuesta de `registro/verificar` (`{ok: true}`).
    """
    # Pedimos opciones (siembra la cookie de challenge real).
    r_op = c.post("/api/auth/mfa/registro/opciones", headers=_ORIGIN)
    assert r_op.status_code == 200, r_op.text
    # Mockeamos SOLO la verificacion WebAuthn (no hay autenticador en CI): devolvemos una
    # credencial valida como si el navegador hubiera respondido bien.
    monkeypatch.setattr(
        api_auth.auth,
        "verificar_registro",
        lambda credential, challenge, rp_id, origenes: {
            "credential_id": credential_id,
            "public_key": "pubkey-b64url",
            "sign_count": 0,
            "transports": json.dumps(["internal"]),
        },
    )
    return c.post(
        "/api/auth/mfa/registro/verificar",
        json={"credential": {"id": credential_id}, "nombre": "Mi llave"},
        headers=_ORIGIN,
    )


# --------------------------------------------------------------------------- #
# 1) Sin clave (maquinaria OFF): el login es IDENTICO a hoy y no hay enrolar    #
# --------------------------------------------------------------------------- #


def test_sin_clave_login_no_pide_mfa_aunque_usuario_tenga_passkey(entorno, monkeypatch):
    """SIN clave de firma la maquinaria esta OFF: aunque una cuenta tenga passkey en BD, el
    login entra directo (no se puede correr la ceremonia). Es el kill-switch del MFA."""
    monkeypatch.delenv("KENI_CONSOLA_MFA_KEY", raising=False)
    monkeypatch.delenv("KENI_CONSOLA_MFA", raising=False)
    u = auth.crear_usuario("ana", CLAVE, "editor")
    _credencial_falsa(u["id"])
    assert auth.obtener_usuario_por_id(u["id"])["mfa_activo"] is True

    c = _cli()
    r = _login(c, "ana", CLAVE)
    assert r.status_code == 200
    cuerpo = r.json()
    assert "mfa_required" not in cuerpo
    assert cuerpo["usuario"]["usuario"] == "ana"
    assert c.get("/api/auth/me", headers=_ORIGIN).status_code == 200


def test_sin_clave_no_expone_endpoints_registro(entorno, monkeypatch):
    """SIN clave, los endpoints de enrolamiento rehusan (404): no se puede firmar el challenge."""
    monkeypatch.delenv("KENI_CONSOLA_MFA_KEY", raising=False)
    monkeypatch.delenv("KENI_CONSOLA_MFA", raising=False)
    auth.crear_usuario("ana", CLAVE, "editor")
    c = _cli()
    _login(c, "ana", CLAVE)
    assert c.post("/api/auth/mfa/registro/opciones", headers=_ORIGIN).status_code == 404
    assert c.get("/api/auth/mfa/credenciales", headers=_ORIGIN).status_code == 404


# --------------------------------------------------------------------------- #
# 1b) Opt-in por usuario: con CLAVE, cualquiera activa su MFA y su login lo exige #
# --------------------------------------------------------------------------- #


def test_opt_in_editor_con_clave_puede_enrolar_sin_flag_global(entorno, monkeypatch):
    """Con clave presente y el flag global OFF, un EDITOR puede inscribir su passkey (opt-in)."""
    monkeypatch.setenv("KENI_CONSOLA_MFA_KEY", _MFA_KEY)
    monkeypatch.delenv("KENI_CONSOLA_MFA", raising=False)
    auth.crear_usuario("ana", CLAVE, "editor")
    c = _cli()
    _login(c, "ana", CLAVE)
    # El enrolamiento esta DISPONIBLE para el editor (no esta forzado, pero puede activarlo).
    assert c.post("/api/auth/mfa/registro/opciones", headers=_ORIGIN).status_code == 200
    assert c.get("/api/auth/mfa/credenciales", headers=_ORIGIN).status_code == 200


def test_opt_in_editor_con_passkey_su_login_eleva_sin_flag_global(entorno, monkeypatch):
    """Un editor que YA activo su MFA (tiene passkey) ve su login EXIGIR el segundo factor,
    aunque el flag global este OFF. La passkey ES la opcion de opt-in."""
    monkeypatch.setenv("KENI_CONSOLA_MFA_KEY", _MFA_KEY)
    monkeypatch.delenv("KENI_CONSOLA_MFA", raising=False)
    u = auth.crear_usuario("ana", CLAVE, "editor")
    _credencial_falsa(u["id"])

    c = _cli()
    r = _login(c, "ana", CLAVE)
    assert r.status_code == 200 and r.json() == {"mfa_required": True}
    assert c.get("/api/auth/me", headers=_ORIGIN).status_code == 401


# --------------------------------------------------------------------------- #
# 2) Flag ON: registro de passkey, flujo y elevacion del login                 #
# --------------------------------------------------------------------------- #


def test_registro_passkey_guarda_credencial_sin_recovery(entorno, monkeypatch):
    monkeypatch.setenv("KENI_CONSOLA_MFA", "1")
    monkeypatch.setenv("KENI_CONSOLA_MFA_KEY", _MFA_KEY)
    u = auth.crear_usuario("ana", CLAVE, "editor")
    c = _cli()
    _login(c, "ana", CLAVE)

    r = _registrar_passkey_via_api(c, monkeypatch)
    assert r.status_code == 200, r.text
    # Ya NO se entregan recovery codes (se retiraron): la respuesta es solo {ok: true}.
    assert r.json() == {"ok": True}
    # La credencial quedo persistida y el flag activo.
    estado = auth.estado_mfa(u["id"])
    assert estado["activo"] is True and estado["num_credenciales"] == 1
    # Listar via API NO expone secretos (solo id/nombre/fechas).
    r_list = c.get("/api/auth/mfa/credenciales", headers=_ORIGIN)
    assert r_list.status_code == 200
    cred = r_list.json()["credenciales"][0]
    assert set(cred) == {"id", "nombre", "creada", "ultimo_uso"}
    assert cred["nombre"] == "Mi llave"


def test_segunda_passkey_tambien_sin_recovery(entorno, monkeypatch):
    monkeypatch.setenv("KENI_CONSOLA_MFA", "1")
    monkeypatch.setenv("KENI_CONSOLA_MFA_KEY", _MFA_KEY)
    auth.crear_usuario("ana", CLAVE, "editor")
    c = _cli()
    _login(c, "ana", CLAVE)
    r1 = _registrar_passkey_via_api(c, monkeypatch, credential_id="cred-1")
    r2 = _registrar_passkey_via_api(c, monkeypatch, credential_id="cred-2")
    assert r1.json() == {"ok": True} and r2.json() == {"ok": True}
    assert "recovery_codes" not in r1.json() and "recovery_codes" not in r2.json()


def test_login_eleva_y_opciones_devuelven_challenge(entorno, monkeypatch):
    monkeypatch.setenv("KENI_CONSOLA_MFA", "1")
    monkeypatch.setenv("KENI_CONSOLA_MFA_KEY", _MFA_KEY)
    u = auth.crear_usuario("ana", CLAVE, "editor")
    _credencial_falsa(u["id"])

    c = _cli()
    r = _login(c, "ana", CLAVE)
    assert r.status_code == 200 and r.json() == {"mfa_required": True}
    # Aun NO hay sesion.
    assert c.get("/api/auth/me", headers=_ORIGIN).status_code == 401

    # Las opciones de login traen un challenge bien formado (option builder REAL de py_webauthn)
    # y siembran la cookie de challenge.
    r_op = c.post("/api/auth/mfa/login/opciones", headers=_ORIGIN)
    assert r_op.status_code == 200, r_op.text
    opciones = r_op.json()
    assert isinstance(opciones.get("challenge"), str) and opciones["challenge"]
    assert api_auth.COOKIE_MFA_CHALLENGE_LOGIN in c.cookies


def test_verify_assertion_mockeada_crea_sesion_y_actualiza_sign_count(entorno, monkeypatch):
    monkeypatch.setenv("KENI_CONSOLA_MFA", "1")
    monkeypatch.setenv("KENI_CONSOLA_MFA_KEY", _MFA_KEY)
    u = auth.crear_usuario("ana", CLAVE, "editor")
    _credencial_falsa(u["id"], credential_id="cred-1", sign_count=0)

    c = _cli()
    _login(c, "ana", CLAVE)
    c.post("/api/auth/mfa/login/opciones", headers=_ORIGIN)  # siembra la cookie de challenge

    # Mock de la verificacion criptografica: devuelve un sign_count nuevo (5).
    monkeypatch.setattr(
        api_auth.auth,
        "verificar_login",
        lambda assertion, challenge, credencial, rp_id, origenes: 5,
    )
    rv = c.post(
        "/api/auth/mfa/verify",
        json={"assertion": {"id": "cred-1"}},
        headers=_ORIGIN,
    )
    assert rv.status_code == 200, rv.text
    assert rv.json()["usuario"]["usuario"] == "ana"
    # La sesion real ya sirve.
    assert c.get("/api/auth/me", headers=_ORIGIN).status_code == 200
    # El sign_count se actualizo al valor devuelto por la verificacion.
    cred = auth.credencial_mfa_por_credential_id(u["id"], "cred-1")
    assert cred["sign_count"] == 5 and cred["ultimo_uso"]


def test_verify_sin_cookie_challenge_es_401(entorno, monkeypatch):
    monkeypatch.setenv("KENI_CONSOLA_MFA", "1")
    monkeypatch.setenv("KENI_CONSOLA_MFA_KEY", _MFA_KEY)
    u = auth.crear_usuario("ana", CLAVE, "editor")
    _credencial_falsa(u["id"])
    c = _cli()
    _login(c, "ana", CLAVE)
    # NO pedimos opciones (no hay cookie de challenge): la assertion no puede verificarse.
    monkeypatch.setattr(
        api_auth.auth, "verificar_login", lambda *a, **k: 1  # no deberia llamarse
    )
    rv = c.post("/api/auth/mfa/verify", json={"assertion": {"id": "cred-1"}}, headers=_ORIGIN)
    assert rv.status_code == 401


def test_verify_challenge_manipulado_es_401(entorno, monkeypatch):
    monkeypatch.setenv("KENI_CONSOLA_MFA", "1")
    monkeypatch.setenv("KENI_CONSOLA_MFA_KEY", _MFA_KEY)
    u = auth.crear_usuario("ana", CLAVE, "editor")
    _credencial_falsa(u["id"])
    c = _cli()
    _login(c, "ana", CLAVE)
    c.post("/api/auth/mfa/login/opciones", headers=_ORIGIN)
    # Manipulamos la cookie de challenge: Fernet no la descifra -> se trata como ausente.
    c.cookies.set(api_auth.COOKIE_MFA_CHALLENGE_LOGIN, "valor-corrupto")
    rv = c.post("/api/auth/mfa/verify", json={"assertion": {"id": "cred-1"}}, headers=_ORIGIN)
    assert rv.status_code == 401


# --------------------------------------------------------------------------- #
# 3) Recovery codes RETIRADOS: la vía de `codigo` ya no existe                  #
# --------------------------------------------------------------------------- #


def test_verify_con_codigo_recuperacion_ya_no_funciona(entorno, monkeypatch):
    """Los recovery codes se retiraron: `mfa/verify` con `{codigo}` (sin assertion) -> 400
    (falta la llave). La recuperacion de cuenta es por reset de MFA de un superadmin."""
    monkeypatch.setenv("KENI_CONSOLA_MFA", "1")
    monkeypatch.setenv("KENI_CONSOLA_MFA_KEY", _MFA_KEY)
    u = auth.crear_usuario("ana", CLAVE, "editor")
    _credencial_falsa(u["id"])
    c = _cli()
    _login(c, "ana", CLAVE)  # eleva (tiene passkey)
    rv = c.post("/api/auth/mfa/verify", json={"codigo": "ABCD-EFGH"}, headers=_ORIGIN)
    assert rv.status_code == 400
    assert c.get("/api/auth/me", headers=_ORIGIN).status_code == 401


# --------------------------------------------------------------------------- #
# 4) La cookie PRE-AUTH no abre endpoints protegidos                          #
# --------------------------------------------------------------------------- #


def test_pre_auth_no_alcanza_endpoint_protegido(entorno, monkeypatch):
    monkeypatch.setenv("KENI_CONSOLA_MFA", "1")
    monkeypatch.setenv("KENI_CONSOLA_MFA_KEY", _MFA_KEY)
    u = auth.crear_usuario("ana", CLAVE, "editor")
    _credencial_falsa(u["id"])
    c = _cli()
    r = _login(c, "ana", CLAVE)
    assert r.json() == {"mfa_required": True}
    # El cliente conserva la cookie pre-auth, pero NINGUN /api protegido la acepta.
    assert c.get("/api/auth/me", headers=_ORIGIN).status_code == 401
    assert c.get("/api/estado", headers=_ORIGIN).status_code == 401
    # El enrolamiento (sesion completa) tampoco se alcanza con la pre-auth.
    assert c.get("/api/auth/mfa/credenciales", headers=_ORIGIN).status_code == 401


# --------------------------------------------------------------------------- #
# 5) Borrar passkeys, disable y reset admin                                   #
# --------------------------------------------------------------------------- #


def test_borrar_ultima_passkey_apaga_mfa(entorno, monkeypatch):
    monkeypatch.setenv("KENI_CONSOLA_MFA", "1")
    monkeypatch.setenv("KENI_CONSOLA_MFA_KEY", _MFA_KEY)
    u = auth.crear_usuario("ana", CLAVE, "editor")
    c = _cli()
    _login(c, "ana", CLAVE)
    _registrar_passkey_via_api(c, monkeypatch, credential_id="cred-1")
    cred_id = c.get("/api/auth/mfa/credenciales", headers=_ORIGIN).json()["credenciales"][0]["id"]

    r = c.delete(f"/api/auth/mfa/credenciales/{cred_id}", headers=_ORIGIN)
    assert r.status_code == 204
    # Era la ultima: mfa_activo se apaga.
    assert auth.obtener_usuario_por_id(u["id"])["mfa_activo"] is False


def test_renombrar_passkey(entorno, monkeypatch):
    """CRUD completo de las llaves: el usuario RENOMBRA su propia passkey (PATCH); 404 si no es suya."""
    monkeypatch.setenv("KENI_CONSOLA_MFA", "1")
    monkeypatch.setenv("KENI_CONSOLA_MFA_KEY", _MFA_KEY)
    auth.crear_usuario("ana", CLAVE, "editor")
    c = _cli()
    _login(c, "ana", CLAVE)
    _registrar_passkey_via_api(c, monkeypatch, credential_id="cred-1")
    cred_id = c.get("/api/auth/mfa/credenciales", headers=_ORIGIN).json()["credenciales"][0]["id"]

    r = c.patch(
        f"/api/auth/mfa/credenciales/{cred_id}",
        json={"nombre": "iPhone de Ana"},
        headers=_ORIGIN,
    )
    assert r.status_code == 204
    cred = c.get("/api/auth/mfa/credenciales", headers=_ORIGIN).json()["credenciales"][0]
    assert cred["nombre"] == "iPhone de Ana"

    # Credencial inexistente -> 404 (no se renombra nada ajeno).
    assert (
        c.patch(
            "/api/auth/mfa/credenciales/no-existe", json={"nombre": "x"}, headers=_ORIGIN
        ).status_code
        == 404
    )


def test_admin_reset_mfa_limpia_y_login_deja_de_elevar(entorno, monkeypatch):
    monkeypatch.setenv("KENI_CONSOLA_MFA", "1")
    monkeypatch.setenv("KENI_CONSOLA_MFA_KEY", _MFA_KEY)
    # Quien resetea es SUPERADMIN (gestionar usuarios lo exige). Con clave presente y passkey
    # propia, su login pediria segundo factor; por eso vamos directo a su sesion real abajo.
    admin = auth.crear_usuario("jefe", CLAVE, "admin", superadmin=True)
    _credencial_falsa(admin["id"], credential_id="cred-jefe")
    victima = auth.crear_usuario("ana", CLAVE, "editor")
    _credencial_falsa(victima["id"])

    c_admin = _cli()
    # Con passkey, el login pediria segundo factor; vamos directo a la sesion real del admin.
    c_admin.cookies.set(auth.COOKIE_SESION, auth.crear_sesion(admin["id"]))
    r = c_admin.patch(
        f"/api/usuarios/{victima['id']}", json={"mfa_reset": True}, headers=_ORIGIN
    )
    assert r.status_code == 200
    # Sin passkeys: el login de Ana ya NO eleva.
    c2 = _cli()
    rl = _login(c2, "ana", CLAVE)
    assert rl.status_code == 200 and "mfa_required" not in rl.json()
    assert c2.get("/api/auth/me", headers=_ORIGIN).status_code == 200
    assert admin["rol"] == "admin"


# --------------------------------------------------------------------------- #
# 6) Fail-safe: flag ON pero falta KENI_CONSOLA_MFA_KEY                        #
# --------------------------------------------------------------------------- #


def test_failsafe_registro_opciones_rehusa_sin_clave(entorno, monkeypatch):
    monkeypatch.setenv("KENI_CONSOLA_MFA", "1")
    monkeypatch.delenv("KENI_CONSOLA_MFA_KEY", raising=False)
    auth.crear_usuario("ana", CLAVE, "editor")
    c = _cli()
    _login(c, "ana", CLAVE)
    # Sin clave de firma, no se puede recordar el challenge -> 503 (fail-safe).
    r = c.post("/api/auth/mfa/registro/opciones", headers=_ORIGIN)
    assert r.status_code == 503


def test_failsafe_login_rechaza_si_mfa_activo_pero_falta_clave(entorno, monkeypatch):
    # Con passkey activa pero sin clave, el login no puede emitir la pre-auth -> 503.
    monkeypatch.setenv("KENI_CONSOLA_MFA", "1")
    u = auth.crear_usuario("ana", CLAVE, "editor")
    _credencial_falsa(u["id"])
    monkeypatch.delenv("KENI_CONSOLA_MFA_KEY", raising=False)

    c = _cli()
    r = _login(c, "ana", CLAVE)
    assert r.status_code == 503
    assert c.get("/api/auth/me", headers=_ORIGIN).status_code == 401


# --------------------------------------------------------------------------- #
# 7) Unit: round-trip de la cookie de challenge                                 #
# --------------------------------------------------------------------------- #


def test_unit_cookie_challenge_round_trip(monkeypatch):
    """La cookie de challenge se firma con la clave MFA y solo se lee para el MISMO usuario."""
    monkeypatch.setenv("KENI_CONSOLA_MFA_KEY", _MFA_KEY)
    token = api_auth._emitir_token_challenge("reto-b64url", "u1")
    assert token is not None
    # Mismo usuario -> recupera el challenge.
    assert api_auth._leer_token_challenge(token, "u1") == "reto-b64url"
    # OTRO usuario -> None (el challenge esta atado al usuario de la ceremonia).
    assert api_auth._leer_token_challenge(token, "u2") is None
    # Token corrupto -> None.
    assert api_auth._leer_token_challenge("basura", "u1") is None


def test_unit_failsafe_sin_clave_no_emite_token():
    """Sin clave Fernet, emitir el token de challenge devuelve None (fail-safe), no revienta."""
    with pytest.raises(auth.MfaNoDisponible):
        auth.cifrador(None)


# --------------------------------------------------------------------------- #
# 8) MFA EXIGIDO POR EL ADMIN (per-usuario, flag `mfa_requerido`)              #
# --------------------------------------------------------------------------- #
#
# El admin marca a una persona `mfa_requerido` desde Usuarios. Con clave de firma presente,
# su login la FUERZA a inscribir passkey (gracia + `debe_inscribir_mfa`) antes de operar; si
# ya tiene passkey, el login exige el segundo factor. El rol es irrelevante: es por persona.
# Sin clave NO se fuerza nada (red ANTI-LOCKOUT).


def test_usuario_con_passkey_eleva_con_clave(entorno, monkeypatch):
    """Cualquier usuario con passkey + clave ve su login EXIGIR el segundo factor (da igual el rol)."""
    monkeypatch.delenv("KENI_CONSOLA_MFA", raising=False)
    monkeypatch.setenv("KENI_CONSOLA_MFA_KEY", _MFA_KEY)
    u = auth.crear_usuario("ana", CLAVE, "editor")
    _credencial_falsa(u["id"])

    c = _cli()
    r = _login(c, "ana", CLAVE)
    assert r.status_code == 200 and r.json() == {"mfa_required": True}
    assert c.get("/api/auth/me", headers=_ORIGIN).status_code == 401


def test_mfa_requerido_sin_passkey_entra_en_gracia(entorno, monkeypatch):
    """Persona con `mfa_requerido` + clave y SIN passkey: no se bloquea el login (no lockout);
    entra marcada `debe_inscribir_mfa` y el enrolamiento esta disponible para inscribirse."""
    monkeypatch.delenv("KENI_CONSOLA_MFA", raising=False)
    monkeypatch.setenv("KENI_CONSOLA_MFA_KEY", _MFA_KEY)
    auth.crear_usuario("ana", CLAVE, "editor", mfa_requerido=True)

    c = _cli()
    r = _login(c, "ana", CLAVE)
    assert r.status_code == 200
    cuerpo = r.json()
    assert "mfa_required" not in cuerpo  # NO se bloquea el login
    assert cuerpo["usuario"]["debe_inscribir_mfa"] is True
    me = c.get("/api/auth/me", headers=_ORIGIN)
    assert me.status_code == 200 and me.json()["usuario"]["debe_inscribir_mfa"] is True
    assert c.post("/api/auth/mfa/registro/opciones", headers=_ORIGIN).status_code == 200


def test_sin_mfa_requerido_no_se_fuerza(entorno, monkeypatch):
    """Sin `mfa_requerido` no se obliga a nadie: con clave presente entra directo y sin
    `debe_inscribir_mfa` (el enrolamiento sigue disponible, pero no forzado)."""
    monkeypatch.delenv("KENI_CONSOLA_MFA", raising=False)
    monkeypatch.setenv("KENI_CONSOLA_MFA_KEY", _MFA_KEY)
    auth.crear_usuario("ana", CLAVE, "editor")

    c = _cli()
    r = _login(c, "ana", CLAVE)
    assert r.status_code == 200
    assert "mfa_required" not in r.json()
    assert r.json()["usuario"].get("debe_inscribir_mfa") in (None, False)
    assert c.get("/api/auth/me", headers=_ORIGIN).json()["usuario"]["debe_inscribir_mfa"] is False


def test_mfa_requerido_sin_clave_no_se_fuerza_no_hay_lockout(entorno, monkeypatch):
    """ANTI-LOCKOUT: `mfa_requerido` ON pero SIN clave de firma -> el login entra como hoy
    (sin elevar, sin marcar inscripcion). Sin clave no se puede inscribir ni verificar."""
    monkeypatch.delenv("KENI_CONSOLA_MFA", raising=False)
    monkeypatch.delenv("KENI_CONSOLA_MFA_KEY", raising=False)
    auth.crear_usuario("ana", CLAVE, "editor", mfa_requerido=True)

    c = _cli()
    r = _login(c, "ana", CLAVE)
    assert r.status_code == 200
    assert "mfa_required" not in r.json()
    assert r.json()["usuario"].get("debe_inscribir_mfa") in (None, False)
    me = c.get("/api/auth/me", headers=_ORIGIN)
    assert me.status_code == 200 and me.json()["usuario"]["debe_inscribir_mfa"] is False


# --------------------------------------------------------------------------- #
# 8b) OBLIGATORIEDAD de ADMINS (`..._MFA_ADMIN`) y el global como ACCIÓN MASIVA              #
# --------------------------------------------------------------------------- #


def test_flag_global_ya_no_fuerza_en_runtime(entorno, monkeypatch):
    """El flag global `KENI_CONSOLA_MFA` dejó de ser un override: con él a 1 + clave, un editor
    SIN `mfa_requerido` per-usuario NO se fuerza (el global es ahora una acción masiva que marca
    la columna; el enforcement depende del flag individual)."""
    monkeypatch.setenv("KENI_CONSOLA_MFA", "1")
    monkeypatch.setenv("KENI_CONSOLA_MFA_KEY", _MFA_KEY)
    auth.crear_usuario("ana", CLAVE, "editor")  # sin mfa_requerido, sin passkey

    c = _cli()
    r = _login(c, "ana", CLAVE)
    assert r.status_code == 200 and "mfa_required" not in r.json()
    assert r.json()["usuario"].get("debe_inscribir_mfa") in (None, False)
    assert c.get("/api/auth/me", headers=_ORIGIN).json()["usuario"]["debe_inscribir_mfa"] is False


def test_admin_obligatorio_por_defecto_obliga_admins_no_editores(entorno, monkeypatch):
    """Con el global OFF pero `KENI_CONSOLA_MFA_ADMIN` por defecto (ON) + clave: un ADMIN sin
    passkey entra en gracia; un EDITOR en la misma situacion NO se fuerza."""
    monkeypatch.delenv("KENI_CONSOLA_MFA", raising=False)
    monkeypatch.delenv("KENI_CONSOLA_MFA_ADMIN", raising=False)  # default ON
    monkeypatch.setenv("KENI_CONSOLA_MFA_KEY", _MFA_KEY)
    auth.crear_usuario("jefe", CLAVE, "admin")
    auth.crear_usuario("ed", CLAVE, "editor")

    c = _cli()
    r_admin = _login(c, "jefe", CLAVE)
    assert r_admin.status_code == 200 and r_admin.json()["usuario"]["debe_inscribir_mfa"] is True

    c2 = _cli()
    r_ed = _login(c2, "ed", CLAVE)
    assert r_ed.status_code == 200
    assert r_ed.json()["usuario"].get("debe_inscribir_mfa") in (None, False)


def test_mfa_admin_off_no_obliga_admin(entorno, monkeypatch):
    """Valvula de escape: `KENI_CONSOLA_MFA_ADMIN=0` (+ global OFF) -> un admin sin passkey NO
    se fuerza (el enrolamiento sigue disponible, pero no obligado)."""
    monkeypatch.delenv("KENI_CONSOLA_MFA", raising=False)
    monkeypatch.setenv("KENI_CONSOLA_MFA_ADMIN", "0")
    monkeypatch.setenv("KENI_CONSOLA_MFA_KEY", _MFA_KEY)
    auth.crear_usuario("jefe", CLAVE, "admin")

    c = _cli()
    r = _login(c, "jefe", CLAVE)
    assert r.status_code == 200
    assert r.json()["usuario"].get("debe_inscribir_mfa") in (None, False)


# --------------------------------------------------------------------------- #
# Hard-block: a quien se le EXIGE passkey y no la tiene no GESTIONA usuarios    #
# --------------------------------------------------------------------------- #


def test_superadmin_con_mfa_requerido_sin_passkey_no_gestiona(entorno, monkeypatch):
    """Superadmin con `mfa_requerido` + clave y SIN passkey: el login lo deja en gracia, pero
    gestionar usuarios queda CERRADO (403 `mfa_inscripcion_requerida`) hasta inscribir la llave."""
    monkeypatch.delenv("KENI_CONSOLA_MFA", raising=False)
    monkeypatch.setenv("KENI_CONSOLA_MFA_KEY", _MFA_KEY)
    auth.crear_usuario("jefa", CLAVE, "admin", superadmin=True, mfa_requerido=True)

    c = _cli()
    r = _login(c, "jefa", CLAVE)
    assert r.status_code == 200
    assert r.json()["usuario"]["debe_inscribir_mfa"] is True  # entra en gracia

    bloqueada = c.post(
        "/api/usuarios",
        json={"usuario": "nuevo", "password": CLAVE, "rol": "editor"},
        headers=_ORIGIN,
    )
    assert bloqueada.status_code == 403
    assert bloqueada.json()["codigo"] == "mfa_inscripcion_requerida"


def test_superadmin_con_passkey_si_gestiona(entorno, monkeypatch):
    """Con passkey ya inscrita, el superadmin recupera la gestion (el hard-block solo aplica
    MIENTRAS no haya segundo factor)."""
    monkeypatch.delenv("KENI_CONSOLA_MFA", raising=False)
    monkeypatch.setenv("KENI_CONSOLA_MFA_KEY", _MFA_KEY)
    jefa = auth.crear_usuario("jefa", CLAVE, "admin", superadmin=True, mfa_requerido=True)
    _credencial_falsa(jefa["id"])  # ya tiene passkey -> mfa_activo

    c = _cli()
    # Con passkey, el login pide segundo factor; para el test vamos directo a la sesion real.
    token = auth.crear_sesion(jefa["id"])
    c.cookies.set(auth.COOKIE_SESION, token)
    r = c.post(
        "/api/usuarios",
        json={"usuario": "nuevo", "password": CLAVE, "rol": "editor"},
        headers=_ORIGIN,
    )
    assert r.status_code == 201


# --------------------------------------------------------------------------- #
# 9) Login PASSWORDLESS por passkey (credencial descubrible, sin contraseña)    #
# --------------------------------------------------------------------------- #


def test_passkey_login_abre_sesion(entorno, monkeypatch):
    """Con clave y una passkey registrada, el login passwordless abre la sesion directamente:
    opciones (sin usuario) -> assertion -> sesion. Mockeamos solo la verificacion criptografica."""
    monkeypatch.setenv("KENI_CONSOLA_MFA_KEY", _MFA_KEY)
    u = auth.crear_usuario("ana", CLAVE, "editor")
    _credencial_falsa(u["id"], credential_id="cred-1", sign_count=0)

    c = _cli()
    r_op = c.post("/api/auth/passkey/opciones", headers=_ORIGIN)
    assert r_op.status_code == 200, r_op.text
    assert api_auth.COOKIE_MFA_CHALLENGE_PASSKEY in c.cookies
    # La credencial se localiza GLOBALMENTE por su id (no hay usuario previo).
    monkeypatch.setattr(api_auth.auth, "verificar_login", lambda *a, **k: 3)
    rv = c.post("/api/auth/passkey/verify", json={"assertion": {"id": "cred-1"}}, headers=_ORIGIN)
    assert rv.status_code == 200, rv.text
    assert rv.json()["usuario"]["usuario"] == "ana"
    # La sesion real ya sirve.
    assert c.get("/api/auth/me", headers=_ORIGIN).status_code == 200


def test_passkey_verify_exige_user_verification(entorno, monkeypatch):
    """El verify passwordless pide user-verification a py_webauthn (la passkey vale por dos
    factores). Comprobamos que se le pasa `require_user_verification=True`."""
    monkeypatch.setenv("KENI_CONSOLA_MFA_KEY", _MFA_KEY)
    u = auth.crear_usuario("ana", CLAVE, "editor")
    _credencial_falsa(u["id"], credential_id="cred-1")
    c = _cli()
    c.post("/api/auth/passkey/opciones", headers=_ORIGIN)
    visto = {}
    monkeypatch.setattr(
        api_auth.auth,
        "verificar_login",
        lambda *a, **k: visto.update(k) or 1,
    )
    c.post("/api/auth/passkey/verify", json={"assertion": {"id": "cred-1"}}, headers=_ORIGIN)
    assert visto.get("require_user_verification") is True


def test_passkey_verify_credencial_desconocida_401(entorno, monkeypatch):
    """Una assertion cuyo credential_id no existe en BD -> 401 (no abre sesion)."""
    monkeypatch.setenv("KENI_CONSOLA_MFA_KEY", _MFA_KEY)
    auth.crear_usuario("ana", CLAVE, "editor")  # sin passkey
    c = _cli()
    c.post("/api/auth/passkey/opciones", headers=_ORIGIN)
    rv = c.post("/api/auth/passkey/verify", json={"assertion": {"id": "no-existe"}}, headers=_ORIGIN)
    assert rv.status_code == 401
    assert c.get("/api/auth/me", headers=_ORIGIN).status_code == 401


def test_passkey_verify_sin_challenge_401(entorno, monkeypatch):
    """Sin la cookie de challenge passwordless (no se pidieron opciones) -> 401."""
    monkeypatch.setenv("KENI_CONSOLA_MFA_KEY", _MFA_KEY)
    u = auth.crear_usuario("ana", CLAVE, "editor")
    _credencial_falsa(u["id"], credential_id="cred-1")
    c = _cli()
    rv = c.post("/api/auth/passkey/verify", json={"assertion": {"id": "cred-1"}}, headers=_ORIGIN)
    assert rv.status_code == 401


def test_passkey_opciones_sin_clave_503(entorno, monkeypatch):
    """Sin clave de firma la maquinaria esta off: las opciones passwordless rehusan (503)."""
    monkeypatch.delenv("KENI_CONSOLA_MFA_KEY", raising=False)
    monkeypatch.delenv("KENI_CONSOLA_MFA", raising=False)
    c = _cli()
    assert c.post("/api/auth/passkey/opciones", headers=_ORIGIN).status_code == 503
