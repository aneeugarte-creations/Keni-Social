"""Tests de auth multiusuario de la Consola: login/roles/usuarios (#130).

Cubre el CONTRATO de la API contra el que tambien se construye el frontend:
  - login OK/KO (mensaje generico, sin enumeracion), cookie de sesion HttpOnly/Strict.
  - /api/auth/me (con y sin sesion), logout (invalida server-side + borra cookie).
  - cambiar-password (forzado y voluntario; valida la actual y la fuerza minima).
  - CRUD de /api/usuarios SOLO admin (403 para editor), 409 de duplicado.
  - Guardas: ultimo admin (borrar/degradar), auto-borrado.
  - Hashing: nada en texto plano en la BD; expiracion de sesion.
  - Convivencia con el TOKEN de #134 (sigue valiendo para /api).

Todo OFFLINE; reusa el aislamiento de `entorno`. Las apps se crean con `bootstrap`
desactivado salvo donde se prueba el bootstrap; los usuarios se crean a mano o por la API.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth, db

from .conftest import TOKEN_PRUEBA, _cliente

# Origin del propio host del TestClient (pasa el chequeo CSRF en mutaciones).
_ORIGIN = {"Origin": "http://testserver"}

# Contrasenas de PRUEBA, deliberadamente de baja entropia y evidentemente falsas (no
# son secretos): cumplen el minimo de 8 caracteres y nada mas. `CLAVE` es la valida por
# defecto; `CLAVE_NUEVA` se usa donde se compara antes/despues de un cambio o reset.
CLAVE = "clave-de-prueba"
CLAVE_NUEVA = "clave-nueva-test"


def _app(bootstrap=False):
    """App con token de prueba conocido (sin lanzadores reales)."""
    return app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=bootstrap)


def _cli(bootstrap=False) -> TestClient:
    """TestClient SIN credencial por defecto (cada test la aporta como necesita)."""
    return TestClient(_app(bootstrap=bootstrap))


def _login(c: TestClient, usuario: str, password: str):
    """Hace login y deja la cookie de sesion en el cliente; devuelve la respuesta."""
    return c.post(
        "/api/auth/login", json={"usuario": usuario, "password": password}, headers=_ORIGIN
    )


def _crear(usuario: str, password: str, rol: str = "editor", **kw):
    """Crea un usuario directo en la BD (forma de dominio), sin pasar por la API."""
    return auth.crear_usuario(usuario, password, rol, **kw)


# --------------------------------------------------------------------------- #
# 1) Bootstrap del admin inicial                                              #
# --------------------------------------------------------------------------- #


def test_bootstrap_crea_admin_si_no_hay_usuarios(entorno, monkeypatch):
    monkeypatch.setenv("KENI_CONSOLA_ADMIN_PASS", CLAVE)
    assert not auth.hay_usuarios()
    auth.bootstrap_admin()
    assert auth.contar_admins() == 1
    u = auth.autenticar("admin", CLAVE)
    assert u is not None and u["rol"] == "admin" and u["debe_cambiar_password"] is True


def test_bootstrap_es_idempotente(entorno, monkeypatch):
    monkeypatch.setenv("KENI_CONSOLA_ADMIN_PASS", CLAVE)
    auth.bootstrap_admin()
    auth.bootstrap_admin()
    assert auth.contar_admins() == 1


def test_bootstrap_genera_pass_y_la_loguea(entorno, monkeypatch, caplog):
    import logging

    from keni_consola.observabilidad import NOMBRE_LOGGER

    monkeypatch.delenv("KENI_CONSOLA_ADMIN_PASS", raising=False)
    logger = logging.getLogger(NOMBRE_LOGGER)
    previa = logger.propagate
    logger.propagate = True
    try:
        with caplog.at_level(logging.WARNING, logger=NOMBRE_LOGGER):
            auth.bootstrap_admin()
    finally:
        logger.propagate = previa
    assert auth.contar_admins() == 1
    mensajes = "\n".join(r.getMessage() for r in caplog.records if r.name == NOMBRE_LOGGER)
    assert "contrasena=" in mensajes  # se mostro la pass temporal en el log


def test_bootstrap_respeta_admin_user_env(entorno, monkeypatch):
    monkeypatch.setenv("KENI_CONSOLA_ADMIN_USER", "jefe")
    monkeypatch.setenv("KENI_CONSOLA_ADMIN_PASS", CLAVE)
    auth.bootstrap_admin()
    assert auth.autenticar("jefe", CLAVE) is not None


def test_sembrar_equipo_crea_los_16(entorno):
    """El seed deja en la BD los 16 usuarios del organigrama AMX."""
    auth.sembrar_equipo()
    usuarios = {u["usuario"]: u for u in auth.listar_usuarios()}
    assert set(u for u, *_ in auth.EQUIPO_AMX) <= set(usuarios)
    # 10 cubren (community managers + content managers + Elias + Yustine + Jonathan + Jose).
    cubren = [u for u in usuarios.values() if u["cobertura"]]
    assert len(cubren) == 10
    assert usuarios["bernardo"]["rol"] == "admin"
    assert usuarios["bernardo"]["cargo"] == "director"
    assert usuarios["bernardo"]["cobertura"] is False
    assert usuarios["tezcu"]["cargo"] == "community_manager"
    assert usuarios["tezcu"]["cobertura"] is True


def test_sembrar_equipo_es_idempotente(entorno):
    """Re-correr el seed no duplica ni rompe; sigue habiendo 16 + el admin de bootstrap."""
    auth.sembrar_equipo()
    auth.sembrar_equipo()
    usuarios = auth.listar_usuarios()
    bernardos = [u for u in usuarios if u["usuario"] == "bernardo"]
    assert len(bernardos) == 1


def test_sembrar_equipo_sincroniza_cargo_y_cobertura(entorno):
    """Si un usuario ya existe con otros valores, el seed los pone al dia (sin tocar pass)."""
    auth.crear_usuario("tezcu", "Otra-Pass-Fuerte-Lol-1234", "editor")
    auth.sembrar_equipo()
    tezcu = next(u for u in auth.listar_usuarios() if u["usuario"] == "tezcu")
    assert tezcu["cargo"] == "community_manager"
    assert tezcu["cobertura"] is True
    # La pass NO se ha pisado: la del crear_usuario original sigue valiendo.
    assert auth.autenticar("tezcu", "Otra-Pass-Fuerte-Lol-1234") is not None


# --------------------------------------------------------------------------- #
# 2) Login OK / KO                                                            #
# --------------------------------------------------------------------------- #


def test_login_ok_devuelve_usuario_y_cookie(entorno):
    _crear("ana", CLAVE, "admin")
    c = _cli()
    r = _login(c, "ana", CLAVE)
    assert r.status_code == 200
    cuerpo = r.json()["usuario"]
    assert cuerpo["usuario"] == "ana" and cuerpo["rol"] == "admin"
    assert set(cuerpo) == {"id", "usuario", "rol", "debe_cambiar_password"}
    set_cookie = r.headers.get("set-cookie", "").lower()
    assert auth.COOKIE_SESION in set_cookie
    assert "httponly" in set_cookie
    assert "samesite=strict" in set_cookie
    assert "path=/" in set_cookie


def test_login_cookie_sesion_sin_secure_por_defecto(entorno, monkeypatch):
    """Por defecto (local HTTP) la cookie de sesion NO lleva `Secure`."""
    monkeypatch.delenv("KENI_CONSOLA_COOKIE_SECURE", raising=False)
    monkeypatch.delenv("KENI_CONSOLA_HTTPS", raising=False)
    _crear("ana", CLAVE, "admin")
    c = _cli()
    r = _login(c, "ana", CLAVE)
    assert r.status_code == 200
    assert "secure" not in r.headers.get("set-cookie", "").lower()


def test_login_cookie_sesion_con_secure_por_env(entorno, monkeypatch):
    """`KENI_CONSOLA_COOKIE_SECURE=1` marca la cookie de sesion como `Secure`."""
    monkeypatch.setenv("KENI_CONSOLA_COOKIE_SECURE", "1")
    _crear("ana", CLAVE, "admin")
    c = _cli()
    r = _login(c, "ana", CLAVE)
    assert r.status_code == 200
    set_cookie = r.headers.get("set-cookie", "").lower()
    assert auth.COOKIE_SESION in set_cookie
    assert "secure" in set_cookie


def test_login_password_incorrecta_da_401_generico(entorno):
    _crear("ana", CLAVE, "admin")
    c = _cli()
    r = _login(c, "ana", "equivocada")
    assert r.status_code == 401
    assert r.json()["error"] == "Usuario o contraseña incorrectos."


def test_login_usuario_inexistente_mismo_mensaje_que_pass_mala(entorno):
    """Sin enumeracion: usuario inexistente devuelve el MISMO mensaje generico."""
    _crear("ana", CLAVE)
    c = _cli()
    r1 = _login(c, "ana", "equivocada")
    r2 = _login(c, "fantasma", "loquesea")
    assert r1.status_code == r2.status_code == 401
    assert r1.json() == r2.json()


def test_login_sin_campos_da_401_generico(entorno):
    c = _cli()
    r = c.post("/api/auth/login", json={}, headers=_ORIGIN)
    assert r.status_code == 401
    assert r.json()["error"] == "Usuario o contraseña incorrectos."


def test_login_es_publico_pero_exige_origin_propio(entorno):
    """`/api/auth/login` no exige credencial previa, pero un Origin ajeno -> 403 (CSRF)."""
    _crear("ana", CLAVE)
    c = _cli()
    r = c.post(
        "/api/auth/login",
        json={"usuario": "ana", "password": CLAVE},
        headers={"Origin": "https://malicioso.example"},
    )
    assert r.status_code == 403


# --------------------------------------------------------------------------- #
# 3) /api/auth/me                                                             #
# --------------------------------------------------------------------------- #


def test_me_con_sesion_devuelve_usuario(entorno):
    _crear("ana", CLAVE, "editor")
    c = _cli()
    _login(c, "ana", CLAVE)
    r = c.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["usuario"]["usuario"] == "ana"


def test_me_sin_sesion_da_401(entorno):
    """Con el TOKEN (no sesion) /api/auth/me responde 401: no hay usuario asociado."""
    c = _cli()
    r = c.get("/api/auth/me", headers={"Authorization": f"Bearer {TOKEN_PRUEBA}"})
    assert r.status_code == 401


def test_me_sin_ninguna_credencial_da_401(entorno):
    c = _cli()
    r = c.get("/api/auth/me")
    assert r.status_code == 401


def test_me_incluye_creado_y_ultimo_acceso_para_mi_cuenta(entorno):
    """`me` expone `creado` y `ultimo_acceso` (los usa la pagina "Mi cuenta")."""
    _crear("ana", CLAVE, "editor")
    c = _cli()
    _login(c, "ana", CLAVE)
    cuerpo = c.get("/api/auth/me").json()["usuario"]
    assert {"creado", "ultimo_acceso"} <= set(cuerpo)
    # Tras el login el ultimo_acceso queda fijado (no vacio).
    assert cuerpo["ultimo_acceso"]


def test_login_no_filtra_creado_ni_ultimo_acceso(entorno):
    """El login mantiene su forma minima de 4 campos (esos extras solo van por `me`)."""
    _crear("ana", CLAVE, "editor")
    c = _cli()
    cuerpo = _login(c, "ana", CLAVE).json()["usuario"]
    assert set(cuerpo) == {"id", "usuario", "rol", "debe_cambiar_password"}


# --------------------------------------------------------------------------- #
# 4) Logout                                                                   #
# --------------------------------------------------------------------------- #


def test_logout_invalida_sesion_y_borra_cookie(entorno):
    _crear("ana", CLAVE)
    c = _cli()
    _login(c, "ana", CLAVE)
    assert c.get("/api/auth/me").status_code == 200
    r = c.post("/api/auth/logout", headers=_ORIGIN)
    assert r.status_code == 204
    # La cookie se borra (Set-Cookie con expiracion en el pasado o vacia).
    assert auth.COOKIE_SESION in r.headers.get("set-cookie", "")
    # Server-side: la sesion ya no vale (forzamos la cookie vieja y debe fallar).
    assert c.get("/api/auth/me").status_code == 401


def test_logout_invalida_server_side_aunque_se_reuse_la_cookie(entorno):
    _crear("ana", CLAVE)
    c = _cli()
    _login(c, "ana", CLAVE)
    # Capturamos el token de sesion sembrado.
    token_sesion = c.cookies.get(auth.COOKIE_SESION)
    assert token_sesion
    c.post("/api/auth/logout", headers=_ORIGIN)
    # Un cliente nuevo que reusa la MISMA cookie ya no entra (sesion borrada en BD).
    c2 = _cli()
    c2.cookies.set(auth.COOKIE_SESION, token_sesion)
    assert c2.get("/api/auth/me").status_code == 401


# --------------------------------------------------------------------------- #
# 5) Cambiar contrasena (forzado y voluntario)                                #
# --------------------------------------------------------------------------- #


def test_cambiar_password_ok(entorno):
    _crear("ana", CLAVE, debe_cambiar_password=True)
    c = _cli()
    _login(c, "ana", CLAVE)
    r = c.post(
        "/api/auth/cambiar-password",
        json={"password_actual": CLAVE, "password_nueva": CLAVE_NUEVA},
        headers=_ORIGIN,
    )
    assert r.status_code == 204
    # La nueva contrasena vale y la vieja ya no.
    assert auth.autenticar("ana", CLAVE_NUEVA) is not None
    assert auth.autenticar("ana", CLAVE) is None


def test_cambiar_password_limpia_debe_cambiar(entorno):
    _crear("ana", CLAVE, debe_cambiar_password=True)
    c = _cli()
    _login(c, "ana", CLAVE)
    c.post(
        "/api/auth/cambiar-password",
        json={"password_actual": CLAVE, "password_nueva": CLAVE_NUEVA},
        headers=_ORIGIN,
    )
    u = auth.autenticar("ana", CLAVE_NUEVA)
    assert u["debe_cambiar_password"] is False


def test_cambiar_password_actual_incorrecta_da_400(entorno):
    _crear("ana", CLAVE)
    c = _cli()
    _login(c, "ana", CLAVE)
    r = c.post(
        "/api/auth/cambiar-password",
        json={"password_actual": "no-es-esa", "password_nueva": CLAVE_NUEVA},
        headers=_ORIGIN,
    )
    assert r.status_code == 400


def test_cambiar_password_nueva_debil_da_400(entorno):
    _crear("ana", CLAVE)
    c = _cli()
    _login(c, "ana", CLAVE)
    r = c.post(
        "/api/auth/cambiar-password",
        json={"password_actual": CLAVE, "password_nueva": "corta"},
        headers=_ORIGIN,
    )
    assert r.status_code == 400


def test_cambiar_password_sin_sesion_da_401(entorno):
    """Por TOKEN (sin sesion) no se puede cambiar pass: no hay cuenta asociada."""
    c = _cli()
    r = c.post(
        "/api/auth/cambiar-password",
        json={"password_actual": "x", "password_nueva": CLAVE_NUEVA},
        headers={**_ORIGIN, "Authorization": f"Bearer {TOKEN_PRUEBA}"},
    )
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# 6) Gestion de usuarios (SOLO admin)                                         #
# --------------------------------------------------------------------------- #


def test_listar_usuarios_como_admin(entorno):
    _crear("jefa", CLAVE, "admin")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.get("/api/usuarios")
    assert r.status_code == 200
    nombres = {u["usuario"] for u in r.json()["usuarios"]}
    assert "jefa" in nombres
    # NUNCA se exponen salt/hash.
    for u in r.json()["usuarios"]:
        assert set(u) == {"id", "usuario", "rol", "creado", "ultimo_acceso"}


def test_editor_no_puede_listar_usuarios_403(entorno):
    _crear("ed", CLAVE, "editor")
    c = _cli()
    _login(c, "ed", CLAVE)
    r = c.get("/api/usuarios")
    assert r.status_code == 403


def test_crear_usuario_como_admin_201(entorno):
    _crear("jefa", CLAVE, "admin")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.post(
        "/api/usuarios",
        json={"usuario": "nuevo", "password": CLAVE, "rol": "editor"},
        headers=_ORIGIN,
    )
    assert r.status_code == 201
    assert r.json()["usuario"] == "nuevo" and r.json()["rol"] == "editor"
    assert auth.autenticar("nuevo", CLAVE) is not None


def test_crear_usuario_duplicado_da_409(entorno):
    _crear("jefa", CLAVE, "admin")
    _crear("repe", CLAVE, "editor")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.post(
        "/api/usuarios",
        json={"usuario": "repe", "password": CLAVE, "rol": "editor"},
        headers=_ORIGIN,
    )
    assert r.status_code == 409


def test_crear_usuario_rol_invalido_da_400(entorno):
    _crear("jefa", CLAVE, "admin")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.post(
        "/api/usuarios",
        json={"usuario": "x", "password": CLAVE, "rol": "superusuario"},
        headers=_ORIGIN,
    )
    assert r.status_code == 400


def test_crear_usuario_pass_debil_da_400(entorno):
    _crear("jefa", CLAVE, "admin")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.post(
        "/api/usuarios",
        json={"usuario": "x", "password": "corta", "rol": "editor"},
        headers=_ORIGIN,
    )
    assert r.status_code == 400


def test_editor_no_puede_crear_usuario_403(entorno):
    _crear("ed", CLAVE, "editor")
    c = _cli()
    _login(c, "ed", CLAVE)
    r = c.post(
        "/api/usuarios",
        json={"usuario": "x", "password": CLAVE, "rol": "editor"},
        headers=_ORIGIN,
    )
    assert r.status_code == 403


def test_patch_cambia_rol(entorno):
    _crear("jefa", CLAVE, "admin")
    ed = _crear("ed", CLAVE, "editor")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.patch(f"/api/usuarios/{ed['id']}", json={"rol": "admin"}, headers=_ORIGIN)
    assert r.status_code == 200 and r.json()["rol"] == "admin"
    assert auth.contar_admins() == 2


def test_patch_resetea_password_y_fuerza_cambio(entorno):
    _crear("jefa", CLAVE, "admin")
    ed = _crear("ed", CLAVE, "editor")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.patch(
        f"/api/usuarios/{ed['id']}", json={"password": CLAVE_NUEVA}, headers=_ORIGIN
    )
    assert r.status_code == 200
    u = auth.autenticar("ed", CLAVE_NUEVA)
    assert u is not None and u["debe_cambiar_password"] is True


def test_patch_usuario_inexistente_404(entorno):
    _crear("jefa", CLAVE, "admin")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.patch("/api/usuarios/noexiste", json={"rol": "admin"}, headers=_ORIGIN)
    assert r.status_code == 404


def test_delete_usuario(entorno):
    _crear("jefa", CLAVE, "admin")
    ed = _crear("ed", CLAVE, "editor")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.delete(f"/api/usuarios/{ed['id']}", headers=_ORIGIN)
    assert r.status_code == 204
    assert auth.obtener_usuario_por_id(ed["id"]) is None


def test_editor_no_puede_borrar_usuario_403(entorno):
    _crear("jefa", CLAVE, "admin")
    otro = _crear("otro", CLAVE, "editor")
    _crear("ed", CLAVE, "editor")
    c = _cli()
    _login(c, "ed", CLAVE)
    r = c.delete(f"/api/usuarios/{otro['id']}", headers=_ORIGIN)
    assert r.status_code == 403


# --------------------------------------------------------------------------- #
# 7) Guardas de integridad de admins                                          #
# --------------------------------------------------------------------------- #


def test_no_borrar_ultimo_admin(entorno):
    jefa = _crear("jefa", CLAVE, "admin")
    otro_admin = _crear("admin2", CLAVE, "admin")
    c = _cli()
    _login(c, "jefa", CLAVE)
    # Borramos el otro admin -> queda jefa como unico admin.
    assert c.delete(f"/api/usuarios/{otro_admin['id']}", headers=_ORIGIN).status_code == 204
    # Ahora intentar borrar al ultimo admin (jefa misma) falla por DOS guardas; basta 409.
    assert c.delete(f"/api/usuarios/{jefa['id']}", headers=_ORIGIN).status_code == 409
    assert auth.contar_admins() == 1


def test_no_borrarte_a_ti_mismo(entorno):
    jefa = _crear("jefa", CLAVE, "admin")
    _crear("admin2", CLAVE, "admin")  # hay otro admin, no es guarda de ultimo
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.delete(f"/api/usuarios/{jefa['id']}", headers=_ORIGIN)
    assert r.status_code == 409
    assert auth.obtener_usuario_por_id(jefa["id"]) is not None


def test_no_degradar_ultimo_admin_via_patch(entorno):
    jefa = _crear("jefa", CLAVE, "admin")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.patch(f"/api/usuarios/{jefa['id']}", json={"rol": "editor"}, headers=_ORIGIN)
    assert r.status_code == 409
    assert auth.contar_admins() == 1


def test_degradar_admin_si_queda_otro_admin_ok(entorno):
    _crear("jefa", CLAVE, "admin")
    otro = _crear("admin2", CLAVE, "admin")
    c = _cli()
    _login(c, "jefa", CLAVE)
    r = c.patch(f"/api/usuarios/{otro['id']}", json={"rol": "editor"}, headers=_ORIGIN)
    assert r.status_code == 200 and auth.contar_admins() == 1


# --------------------------------------------------------------------------- #
# 8) Hashing: nada en texto plano                                             #
# --------------------------------------------------------------------------- #


def test_password_no_se_guarda_en_texto_plano(entorno):
    _crear("ana", CLAVE, "editor")
    con = db.conectar()
    try:
        fila = con.execute(
            "SELECT salt, hash FROM usuarios WHERE usuario = ?", ("ana",)
        ).fetchone()
    finally:
        con.close()
    # Ni el salt ni el hash contienen la contrasena en claro.
    assert CLAVE not in fila["salt"]
    assert CLAVE not in fila["hash"]
    # El hash es hex de 64 bytes (128 chars), reproducible con el salt.
    assert len(fila["hash"]) == 128
    assert auth.verificar_password(CLAVE, fila["salt"], fila["hash"])
    assert not auth.verificar_password("otra", fila["salt"], fila["hash"])


def test_dos_usuarios_misma_pass_distinto_hash(entorno):
    """Salt por usuario: la misma contrasena produce hashes distintos."""
    _crear("a", CLAVE, "editor")
    _crear("b", CLAVE, "editor")
    con = db.conectar()
    try:
        ha = con.execute("SELECT hash, salt FROM usuarios WHERE usuario='a'").fetchone()
        hb = con.execute("SELECT hash, salt FROM usuarios WHERE usuario='b'").fetchone()
    finally:
        con.close()
    assert ha["salt"] != hb["salt"]
    assert ha["hash"] != hb["hash"]


# --------------------------------------------------------------------------- #
# 9) Sesiones: expiracion                                                     #
# --------------------------------------------------------------------------- #


def test_sesion_expirada_no_vale_y_se_limpia(entorno):
    u = _crear("ana", CLAVE, "editor")
    token = auth.crear_sesion(u["id"])
    assert auth.sesion_valida(token) is not None
    # Forzamos la expiracion en el pasado directamente en la BD.
    con = db.conectar()
    try:
        con.execute(
            "UPDATE sesiones SET expira = ? WHERE token = ?",
            ("2000-01-01T00:00:00+00:00", token),
        )
        con.commit()
    finally:
        con.close()
    assert auth.sesion_valida(token) is None
    # Y la sesion caducada se borro de la BD.
    con = db.conectar()
    try:
        fila = con.execute("SELECT 1 FROM sesiones WHERE token = ?", (token,)).fetchone()
    finally:
        con.close()
    assert fila is None


def test_sesion_renueva_expiracion_con_uso(entorno):
    from datetime import UTC, datetime, timedelta

    u = _crear("ana", CLAVE, "editor")
    token = auth.crear_sesion(u["id"])
    # Adelantamos la expiracion a 2030 para ver que el uso la RECALCULA a ~ahora+12h.
    con = db.conectar()
    try:
        con.execute(
            "UPDATE sesiones SET expira = ? WHERE token = ?",
            ("2030-01-01T00:00:00+00:00", token),
        )
        con.commit()
    finally:
        con.close()
    assert auth.sesion_valida(token) is not None  # uso => renueva (ventana deslizante)
    con = db.conectar()
    try:
        despues = con.execute(
            "SELECT expira FROM sesiones WHERE token = ?", (token,)
        ).fetchone()["expira"]
    finally:
        con.close()
    # Ya NO es la fecha 2030 forzada: el uso la reescribio a ~ahora + horas_sesion().
    assert despues != "2030-01-01T00:00:00+00:00"
    esperada = datetime.now(UTC) + timedelta(hours=auth.horas_sesion())
    obtenida = datetime.fromisoformat(despues)
    assert abs((obtenida - esperada).total_seconds()) < 60


def test_login_expirado_por_intentos_fallidos_bloquea(entorno):
    """Anti fuerza bruta: tras varios fallos, la cuenta queda bloqueada un rato."""
    _crear("ana", CLAVE, "editor")
    for _ in range(auth.MAX_INTENTOS_FALLIDOS):
        assert auth.autenticar("ana", "mala") is None
    # Aun con la contrasena CORRECTA, queda bloqueada justo despues.
    assert auth.autenticar("ana", CLAVE) is None


# --------------------------------------------------------------------------- #
# 10) Convivencia con el token de #134                                        #
# --------------------------------------------------------------------------- #


def test_token_de_bootstrap_sigue_valiendo_para_api(entorno):
    """El TOKEN de #134 sigue autorizando /api sin necesidad de sesion."""
    c = _cli()
    r = c.get("/api/estado", headers={"Authorization": f"Bearer {TOKEN_PRUEBA}"})
    assert r.status_code == 200


def test_token_bootstrap_crea_primer_admin_con_bd_vacia(entorno):
    """#150: con la BD VACIA, el token de mantenimiento SI puede crear el PRIMER admin.

    Es el unico camino admin que conserva el token: bootstrap de recuperacion. No es poder
    admin general (ver los tests de abajo): en cuanto hay usuarios, el token deja de poder.
    """
    c = _cli()
    assert not auth.hay_usuarios()
    h = {**_ORIGIN, "Authorization": f"Bearer {TOKEN_PRUEBA}"}
    r = c.post(
        "/api/usuarios",
        json={"usuario": "primero", "password": CLAVE, "rol": "admin"},
        headers=h,
    )
    assert r.status_code == 201
    assert r.json()["rol"] == "admin"
    assert auth.contar_admins() == 1


def test_token_bootstrap_solo_admin_no_editor(entorno):
    """#150: el bootstrap por token SOLO crea admin; un editor con BD vacia -> 403.

    Sembrar un editor con la BD vacia dejaria la consola sin admin (y sin recuperacion).
    """
    c = _cli()
    h = {**_ORIGIN, "Authorization": f"Bearer {TOKEN_PRUEBA}"}
    r = c.post(
        "/api/usuarios",
        json={"usuario": "ed", "password": CLAVE, "rol": "editor"},
        headers=h,
    )
    assert r.status_code == 403
    assert not auth.hay_usuarios()


def test_token_no_crea_usuarios_si_ya_hay(entorno):
    """#150: con usuarios YA en la BD, el token NO puede crear cuentas (no es admin) -> 403."""
    _crear("jefa", CLAVE, "admin")
    c = _cli()
    h = {**_ORIGIN, "Authorization": f"Bearer {TOKEN_PRUEBA}"}
    r = c.post(
        "/api/usuarios",
        json={"usuario": "colado", "password": CLAVE, "rol": "admin"},
        headers=h,
    )
    assert r.status_code == 403
    assert auth.autenticar("colado", CLAVE) is None


def test_token_no_lista_usuarios(entorno):
    """#150: GET /api/usuarios por el token (sin sesion admin real) -> 403 (no es admin)."""
    _crear("jefa", CLAVE, "admin")
    c = _cli()
    r = c.get("/api/usuarios", headers={"Authorization": f"Bearer {TOKEN_PRUEBA}"})
    assert r.status_code == 403


def test_token_no_modifica_usuarios(entorno):
    """#150: PATCH /api/usuarios/{id} por el token -> 403 (no puede tocar cuentas)."""
    _crear("jefa", CLAVE, "admin")
    ed = _crear("ed", CLAVE, "editor")
    c = _cli()
    h = {**_ORIGIN, "Authorization": f"Bearer {TOKEN_PRUEBA}"}
    r = c.patch(f"/api/usuarios/{ed['id']}", json={"rol": "admin"}, headers=h)
    assert r.status_code == 403
    # No cambio nada: sigue siendo editor.
    assert auth.obtener_usuario_por_id(ed["id"])["rol"] == "editor"


def test_token_no_borra_usuarios(entorno):
    """#150: DELETE /api/usuarios/{id} por el token -> 403 (no puede borrar cuentas)."""
    _crear("jefa", CLAVE, "admin")
    ed = _crear("ed", CLAVE, "editor")
    c = _cli()
    r = c.delete(
        f"/api/usuarios/{ed['id']}",
        headers={**_ORIGIN, "Authorization": f"Bearer {TOKEN_PRUEBA}"},
    )
    assert r.status_code == 403
    assert auth.obtener_usuario_por_id(ed["id"]) is not None


def test_admin_real_si_gestiona_usuarios(entorno):
    """#150: un admin REAL (sesion) SIGUE gestionando usuarios (no se rompe el flujo normal)."""
    _crear("jefa", CLAVE, "admin")
    c = _cli()
    _login(c, "jefa", CLAVE)
    assert c.get("/api/usuarios").status_code == 200
    r = c.post(
        "/api/usuarios",
        json={"usuario": "nuevo", "password": CLAVE, "rol": "editor"},
        headers=_ORIGIN,
    )
    assert r.status_code == 201


def test_sesion_autoriza_api_sin_token(entorno):
    """Una sesion valida autoriza /api aunque NO se mande el token de #134."""
    _crear("ana", CLAVE, "editor")
    c = _cli()
    _login(c, "ana", CLAVE)
    r = c.get("/api/estado")  # sin Authorization: solo la cookie de sesion
    assert r.status_code == 200


def test_api_sin_sesion_ni_token_da_401(entorno):
    c = _cli()
    assert c.get("/api/estado").status_code == 401


# --------------------------------------------------------------------------- #
# 11) Integridad de la tabla usuarios                                         #
# --------------------------------------------------------------------------- #


def test_usuario_unico_a_nivel_db(entorno):
    assert _crear("ana", CLAVE) is not None
    # Crear el mismo nombre otra vez devuelve None (UNIQUE), sin lanzar.
    assert _crear("ana", CLAVE_NUEVA) is None


def test_app_con_bootstrap_crea_admin(entorno, monkeypatch):
    monkeypatch.setenv("KENI_CONSOLA_ADMIN_PASS", CLAVE)
    c = _cli(bootstrap=True)
    r = _login(c, "admin", CLAVE)
    assert r.status_code == 200 and r.json()["usuario"]["rol"] == "admin"


def test_cliente_conftest_no_arranca_bootstrap(entorno):
    """El `_cliente` de conftest no crea usuarios (via token); la tabla queda vacia."""
    _cliente()  # crea la app con bootstrap=False
    assert not auth.hay_usuarios()
