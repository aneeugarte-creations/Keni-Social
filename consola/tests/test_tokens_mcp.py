"""Tests de los helpers de tokens del MCP por identidad (`auth.tokens_mcp`).

Cubre el ciclo de vida: emitir, validar (devuelve el usuario + refresca uso), caducar
(`expira`), revocar (`revocado`) y listar sin el secreto.

OFFLINE: Postgres de pruebas (fixture `entorno`); sin red.
"""

from __future__ import annotations

from keni_consola import auth

_PASS = "contraseña-larga-de-prueba-123"


def _crear_usuario(nombre: str = "dueno-mcp") -> str:
    """Crea (idempotente) un usuario y devuelve su id."""
    existe = auth.autenticar(nombre, _PASS)
    if existe is not None:
        return existe["id"]
    return auth.crear_usuario(nombre, _PASS, rol="admin", debe_cambiar_password=False)["id"]


def test_crear_y_validar_devuelve_el_usuario(entorno):
    """Un token recién emitido valida y devuelve la forma pública de su dueño."""
    uid = _crear_usuario()
    token = auth.crear_token_mcp(uid, "Claude Code de prueba")
    usuario = auth.token_mcp_valido(token)
    assert usuario is not None
    assert usuario["id"] == uid
    assert usuario["usuario"] == "dueno-mcp"
    assert usuario["rol"] == "admin"


def test_validar_refresca_ultimo_uso(entorno):
    """Validar marca `ultimo_uso` (de None a un instante) sin tocar la caducidad."""
    uid = _crear_usuario("dueno-uso")
    token = auth.crear_token_mcp(uid, "uso")
    # Recién creado: aún sin usar.
    assert auth.listar_tokens_mcp(uid)[0]["ultimo_uso"] is None
    assert auth.token_mcp_valido(token) is not None
    assert auth.listar_tokens_mcp(uid)[0]["ultimo_uso"] is not None


def test_token_inexistente_no_valida(entorno):
    """Un valor que no es ningún token devuelve None (no revienta)."""
    assert auth.token_mcp_valido("no-soy-un-token") is None
    assert auth.token_mcp_valido("") is None


def test_token_caducado_no_valida(entorno):
    """Un token con `expira` en el pasado no valida (caducidad absoluta, no deslizante)."""
    uid = _crear_usuario("dueno-caduco")
    # expira en HORAS; -1 => caducó hace una hora.
    token = auth.crear_token_mcp(uid, "caduco", expira=-1)
    assert auth.token_mcp_valido(token) is None


def test_token_sin_caducidad_valida(entorno):
    """`expira=None` => el token no caduca."""
    uid = _crear_usuario("dueno-eterno")
    token = auth.crear_token_mcp(uid, "eterno", expira=None)
    assert auth.token_mcp_valido(token) is not None


def test_revocar_invalida_el_token(entorno):
    """Revocar un token lo deja inválido; revocar es idempotente y reporta existencia."""
    uid = _crear_usuario("dueno-revoca")
    token = auth.crear_token_mcp(uid, "revoca")
    assert auth.token_mcp_valido(token) is not None
    assert auth.revocar_token_mcp(token) is True
    assert auth.token_mcp_valido(token) is None
    # Idempotente: el token sigue existiendo (revocado), así que devuelve True de nuevo.
    assert auth.revocar_token_mcp(token) is True
    # Un valor inexistente: False.
    assert auth.revocar_token_mcp("no-existe") is False
    assert auth.revocar_token_mcp("") is False


def test_listar_omite_el_secreto_y_refleja_revocado(entorno):
    """`listar_tokens_mcp` devuelve los tokens del usuario SIN el valor, con su estado."""
    uid = _crear_usuario("dueno-lista")
    t1 = auth.crear_token_mcp(uid, "uno")
    auth.crear_token_mcp(uid, "dos")
    tokens = auth.listar_tokens_mcp(uid)
    assert {t["etiqueta"] for t in tokens} == {"uno", "dos"}
    # Nunca expone el secreto.
    assert all("token" not in t for t in tokens)
    assert all(t["revocado"] is False for t in tokens)
    auth.revocar_token_mcp(t1)
    revocado = next(t for t in auth.listar_tokens_mcp(uid) if t["etiqueta"] == "uno")
    assert revocado["revocado"] is True


def test_listar_expone_id_opaco_y_no_el_secreto(entorno):
    """Cada item del listado trae un `id` opaco (no el secreto) para poder revocarlo."""
    uid = _crear_usuario("dueno-id")
    token = auth.crear_token_mcp(uid, "con-id")
    item = auth.listar_tokens_mcp(uid)[0]
    assert isinstance(item["id"], str) and item["id"]
    # El `id` opaco NUNCA es el valor del token.
    assert item["id"] != token


def test_revocar_de_usuario_por_id(entorno):
    """`revocar_token_mcp_de_usuario` revoca por `id`, idempotente, y solo del propio dueño."""
    a = _crear_usuario("dueno-id-a")
    b = _crear_usuario("dueno-id-b")
    token_a = auth.crear_token_mcp(a, "de-a")
    id_a = auth.listar_tokens_mcp(a)[0]["id"]
    # Otra persona NO puede revocar el token ajeno (no es suyo): False y sigue válido.
    assert auth.revocar_token_mcp_de_usuario(b, id_a) is False
    assert auth.token_mcp_valido(token_a) is not None
    # El dueño sí: revoca, invalida y es idempotente.
    assert auth.revocar_token_mcp_de_usuario(a, id_a) is True
    assert auth.token_mcp_valido(token_a) is None
    assert auth.revocar_token_mcp_de_usuario(a, id_a) is True
    # Un `id` inexistente o vacío: False.
    assert auth.revocar_token_mcp_de_usuario(a, "no-existe") is False
    assert auth.revocar_token_mcp_de_usuario(a, "") is False


def test_listar_es_por_usuario(entorno):
    """Cada usuario solo ve SUS tokens."""
    a = _crear_usuario("dueno-a")
    b = _crear_usuario("dueno-b")
    auth.crear_token_mcp(a, "de-a")
    assert [t["etiqueta"] for t in auth.listar_tokens_mcp(a)] == ["de-a"]
    assert auth.listar_tokens_mcp(b) == []
