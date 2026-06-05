"""Tests del segundo factor TOTP (MFA), GATEADO por `KENI_CONSOLA_MFA` (def OFF).

Cubre el CONTRATO contra el que se construye el frontend y, sobre todo, la garantia critica
del piloto: con el flag OFF el login es IDENTICO a hoy (nunca se pide segundo factor). Tambien:
enrolar -> activar -> el siguiente login pide codigo -> codigo correcto entra / incorrecto 401 /
recovery de un solo uso; la cookie pre-auth NO abre endpoints protegidos; el reset admin limpia
el MFA; y el fail-safe cuando falta `KENI_CONSOLA_MFA_KEY`.

Reusa el aislamiento de `entorno` (Postgres de pruebas; se salta si no hay) y las apps con
TOKEN de prueba, igual que `test_auth.py`.
"""

from __future__ import annotations

import pyotp
import pytest
from cryptography.fernet import Fernet
from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth

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


def _activar_mfa_para(c: TestClient, usuario_id: str) -> tuple[str, list[str]]:
    """Enrola+activa el MFA del usuario logueado en `c`. Devuelve `(secreto, recovery_codes)`."""
    r_setup = c.post("/api/auth/mfa/setup", headers=_ORIGIN)
    assert r_setup.status_code == 200, r_setup.text
    secreto = r_setup.json()["secret"]
    codigo = pyotp.TOTP(secreto).now()
    r_act = c.post("/api/auth/mfa/activate", json={"codigo": codigo}, headers=_ORIGIN)
    assert r_act.status_code == 200, r_act.text
    return secreto, r_act.json()["recovery_codes"]


# --------------------------------------------------------------------------- #
# 1) Flag OFF: el login es IDENTICO a hoy (NUNCA pide segundo factor)          #
# --------------------------------------------------------------------------- #


def test_flag_off_login_no_pide_mfa_aunque_usuario_tenga_mfa_activo(entorno, monkeypatch):
    # MFA key presente pero flag OFF (lo que hace `entorno` por defecto).
    monkeypatch.setenv("KENI_CONSOLA_MFA_KEY", _MFA_KEY)
    monkeypatch.delenv("KENI_CONSOLA_MFA", raising=False)
    u = auth.crear_usuario("ana", CLAVE, "editor")
    # Forzamos mfa_activo en BD aunque el flag este OFF.
    monkeypatch.setenv("KENI_CONSOLA_MFA", "1")
    c = _cli()
    _login(c, "ana", CLAVE)
    _activar_mfa_para(c, u["id"])
    c.post("/api/auth/logout", headers=_ORIGIN)
    monkeypatch.setenv("KENI_CONSOLA_MFA", "0")  # flag OFF de nuevo

    c2 = _cli()
    r = _login(c2, "ana", CLAVE)
    assert r.status_code == 200
    cuerpo = r.json()
    # Con el flag OFF, el login devuelve la sesion directamente (sin mfa_required).
    assert "mfa_required" not in cuerpo
    assert cuerpo["usuario"]["usuario"] == "ana"
    # Y la sesion ya sirve para /api/auth/me.
    assert c2.get("/api/auth/me", headers=_ORIGIN).status_code == 200


def test_flag_off_no_expone_endpoints_mfa_setup(entorno, monkeypatch):
    monkeypatch.setenv("KENI_CONSOLA_MFA_KEY", _MFA_KEY)
    monkeypatch.delenv("KENI_CONSOLA_MFA", raising=False)
    auth.crear_usuario("ana", CLAVE, "editor")
    c = _cli()
    _login(c, "ana", CLAVE)
    # setup/activate rehusan (404) con el flag OFF.
    assert c.post("/api/auth/mfa/setup", headers=_ORIGIN).status_code == 404


# --------------------------------------------------------------------------- #
# 2) Flag ON: enrolar -> activar -> el login eleva al segundo factor           #
# --------------------------------------------------------------------------- #


def test_enrolar_activar_y_login_pide_codigo(entorno, monkeypatch):
    monkeypatch.setenv("KENI_CONSOLA_MFA", "1")
    monkeypatch.setenv("KENI_CONSOLA_MFA_KEY", _MFA_KEY)
    u = auth.crear_usuario("ana", CLAVE, "editor")

    c = _cli()
    _login(c, "ana", CLAVE)  # sin MFA activo todavia => sesion directa
    secreto, recovery = _activar_mfa_para(c, u["id"])
    assert len(recovery) == auth.NUM_CODIGOS_RECUPERACION
    c.post("/api/auth/logout", headers=_ORIGIN)

    # Proximo login: ahora SI eleva.
    c2 = _cli()
    r = _login(c2, "ana", CLAVE)
    assert r.status_code == 200
    assert r.json() == {"mfa_required": True}
    # Aun NO hay sesion: /api/auth/me debe dar 401.
    assert c2.get("/api/auth/me", headers=_ORIGIN).status_code == 401

    # Codigo TOTP correcto -> entra.
    codigo = pyotp.TOTP(secreto).now()
    rv = c2.post("/api/auth/mfa/verify", json={"codigo": codigo}, headers=_ORIGIN)
    assert rv.status_code == 200
    assert rv.json()["usuario"]["usuario"] == "ana"
    assert c2.get("/api/auth/me", headers=_ORIGIN).status_code == 200


def test_codigo_incorrecto_es_401(entorno, monkeypatch):
    monkeypatch.setenv("KENI_CONSOLA_MFA", "1")
    monkeypatch.setenv("KENI_CONSOLA_MFA_KEY", _MFA_KEY)
    u = auth.crear_usuario("ana", CLAVE, "editor")
    c = _cli()
    _login(c, "ana", CLAVE)
    _activar_mfa_para(c, u["id"])
    c.post("/api/auth/logout", headers=_ORIGIN)

    c2 = _cli()
    _login(c2, "ana", CLAVE)
    rv = c2.post("/api/auth/mfa/verify", json={"codigo": "000000"}, headers=_ORIGIN)
    assert rv.status_code == 401
    assert c2.get("/api/auth/me", headers=_ORIGIN).status_code == 401


def test_recovery_code_funciona_una_sola_vez(entorno, monkeypatch):
    monkeypatch.setenv("KENI_CONSOLA_MFA", "1")
    monkeypatch.setenv("KENI_CONSOLA_MFA_KEY", _MFA_KEY)
    u = auth.crear_usuario("ana", CLAVE, "editor")
    c = _cli()
    _login(c, "ana", CLAVE)
    _secreto, recovery = _activar_mfa_para(c, u["id"])
    c.post("/api/auth/logout", headers=_ORIGIN)
    codigo_recovery = recovery[0]

    # 1er uso: entra.
    c2 = _cli()
    _login(c2, "ana", CLAVE)
    rv = c2.post("/api/auth/mfa/verify", json={"codigo": codigo_recovery}, headers=_ORIGIN)
    assert rv.status_code == 200
    c2.post("/api/auth/logout", headers=_ORIGIN)

    # 2o uso del MISMO recovery: rechazado (un solo uso).
    c3 = _cli()
    _login(c3, "ana", CLAVE)
    rv2 = c3.post("/api/auth/mfa/verify", json={"codigo": codigo_recovery}, headers=_ORIGIN)
    assert rv2.status_code == 401


# --------------------------------------------------------------------------- #
# 3) La cookie PRE-AUTH no abre endpoints protegidos                          #
# --------------------------------------------------------------------------- #


def test_pre_auth_no_alcanza_endpoint_protegido(entorno, monkeypatch):
    monkeypatch.setenv("KENI_CONSOLA_MFA", "1")
    monkeypatch.setenv("KENI_CONSOLA_MFA_KEY", _MFA_KEY)
    u = auth.crear_usuario("ana", CLAVE, "editor")
    c = _cli()
    _login(c, "ana", CLAVE)
    _activar_mfa_para(c, u["id"])
    c.post("/api/auth/logout", headers=_ORIGIN)

    c2 = _cli()
    r = _login(c2, "ana", CLAVE)
    assert r.json() == {"mfa_required": True}
    # El cliente conserva la cookie pre-auth, pero NINGUN /api protegido la acepta.
    assert c2.get("/api/auth/me", headers=_ORIGIN).status_code == 401
    # Un endpoint cualquiera protegido tampoco (estado).
    assert c2.get("/api/estado", headers=_ORIGIN).status_code == 401


# --------------------------------------------------------------------------- #
# 4) Reset admin limpia el MFA (recuperacion de cuenta)                       #
# --------------------------------------------------------------------------- #


def test_admin_reset_mfa_limpia_y_login_deja_de_pedir_codigo(entorno, monkeypatch):
    monkeypatch.setenv("KENI_CONSOLA_MFA", "1")
    monkeypatch.setenv("KENI_CONSOLA_MFA_KEY", _MFA_KEY)
    admin = auth.crear_usuario("jefe", CLAVE, "admin")
    victima = auth.crear_usuario("ana", CLAVE, "editor")

    # Ana enrola su MFA.
    c_ana = _cli()
    _login(c_ana, "ana", CLAVE)
    _activar_mfa_para(c_ana, victima["id"])
    c_ana.post("/api/auth/logout", headers=_ORIGIN)

    # El admin resetea el MFA de Ana.
    c_admin = _cli()
    _login(c_admin, "jefe", CLAVE)
    r = c_admin.patch(
        f"/api/usuarios/{victima['id']}", json={"mfa_reset": True}, headers=_ORIGIN
    )
    assert r.status_code == 200

    # Ahora el login de Ana ya NO eleva (vuelve a entrar con solo user/pass).
    c2 = _cli()
    rl = _login(c2, "ana", CLAVE)
    assert rl.status_code == 200
    assert "mfa_required" not in rl.json()
    assert c2.get("/api/auth/me", headers=_ORIGIN).status_code == 200
    assert admin["rol"] == "admin"


# --------------------------------------------------------------------------- #
# 5) Fail-safe: flag ON pero falta KENI_CONSOLA_MFA_KEY                        #
# --------------------------------------------------------------------------- #


def test_failsafe_setup_rehusa_sin_clave(entorno, monkeypatch):
    monkeypatch.setenv("KENI_CONSOLA_MFA", "1")
    monkeypatch.delenv("KENI_CONSOLA_MFA_KEY", raising=False)
    auth.crear_usuario("ana", CLAVE, "editor")
    c = _cli()
    _login(c, "ana", CLAVE)
    # Sin clave de cifrado, el enrolamiento REHUSA (503): nunca se guarda el secreto en claro.
    r = c.post("/api/auth/mfa/setup", headers=_ORIGIN)
    assert r.status_code == 503
    # Y en BD el usuario sigue sin secreto.
    u = auth.obtener_usuario_por_id(c.get("/api/auth/me", headers=_ORIGIN).json()["usuario"]["id"])
    assert u["mfa_activo"] is False


def test_failsafe_login_rechaza_si_mfa_activo_pero_falta_clave(entorno, monkeypatch):
    # Enrolamos CON clave, luego la quitamos: el login no puede verificar -> 503 (no se cuela).
    monkeypatch.setenv("KENI_CONSOLA_MFA", "1")
    monkeypatch.setenv("KENI_CONSOLA_MFA_KEY", _MFA_KEY)
    u = auth.crear_usuario("ana", CLAVE, "editor")
    c = _cli()
    _login(c, "ana", CLAVE)
    _activar_mfa_para(c, u["id"])
    c.post("/api/auth/logout", headers=_ORIGIN)

    monkeypatch.delenv("KENI_CONSOLA_MFA_KEY", raising=False)
    c2 = _cli()
    r = _login(c2, "ana", CLAVE)
    assert r.status_code == 503
    assert c2.get("/api/auth/me", headers=_ORIGIN).status_code == 401


# --------------------------------------------------------------------------- #
# 6) Unit: el secreto se guarda CIFRADO (nunca en claro)                       #
# --------------------------------------------------------------------------- #


def test_secreto_se_guarda_cifrado_en_bd(entorno, monkeypatch):
    monkeypatch.setenv("KENI_CONSOLA_MFA", "1")
    monkeypatch.setenv("KENI_CONSOLA_MFA_KEY", _MFA_KEY)
    u = auth.crear_usuario("ana", CLAVE, "editor")
    c = _cli()
    _login(c, "ana", CLAVE)
    secreto, _ = _activar_mfa_para(c, u["id"])
    estado = auth.estado_mfa(u["id"])
    assert estado is not None and estado["activo"] is True
    # El secreto en claro NO aparece tal cual en la columna; lo cifrado SI descifra a el.
    assert secreto not in estado["secret_cifrado"]
    assert auth.descifrar_secreto(estado["secret_cifrado"], _MFA_KEY) == secreto


def test_mfa_unit_cifrado_recovery_y_totp():
    """Unit de la capa cripto (sin BD): cifrado round-trip, TOTP y recovery de un solo uso."""
    secreto = auth.generar_secreto()
    cifrado = auth.cifrar_secreto(secreto, _MFA_KEY)
    assert auth.descifrar_secreto(cifrado, _MFA_KEY) == secreto
    # Sin clave -> rehusa (fail-safe), no devuelve claro.
    with pytest.raises(auth.MfaNoDisponible):
        auth.cifrar_secreto(secreto, None)

    assert auth.verificar_totp(secreto, pyotp.TOTP(secreto).now()) is True
    assert auth.verificar_totp(secreto, "000000") is False

    codigos = auth.generar_codigos_recuperacion()
    hash_json = auth.hashear_codigos_recuperacion(codigos)
    ok, restantes = auth.verificar_codigo_recuperacion(codigos[0], hash_json)
    assert ok is True
    # Consumido: el mismo codigo ya no vale contra la lista restante.
    ok2, _ = auth.verificar_codigo_recuperacion(codigos[0], restantes)
    assert ok2 is False
