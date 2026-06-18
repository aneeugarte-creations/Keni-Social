"""Tests del modulo `proveedor_github`: PARSERS puros (texto del CLI -> dict). OFFLINE.

No tocan subprocess ni red: solo ejercitan `parsear_estado` (formas JSON y texto) y
`parsear_inicio` (captura del one-time code / url del device flow). La parte interactiva (PTY)
y los runners (subprocess) se cubren aparte / en el listener de control.
"""

from __future__ import annotations

from keni_consola import proveedor_github as pg


def test_parsear_inicio_extrae_code_y_url_del_device_flow():
    # Salida REAL de `gh auth login --web` SIN tty: imprime el one-time code y la url.
    salida = (
        "! First copy your one-time code: DE45-589C\n"
        "Open this URL to continue in your web browser: https://github.com/login/device\n"
    )
    inicio = pg.parsear_inicio(salida)
    assert inicio["codigo"] == "DE45-589C"
    assert inicio["url"] == "https://github.com/login/device"


def test_codigo_completo_corta_la_lectura_con_salto():
    # El corte de lectura exige el code SEGUIDO de espacio/salto (llegó entero).
    assert pg._RE_CODIGO_COMPLETO.search("one-time code: DE45-589C\n")

# Salida REAL de `gh auth status` con sesion activa (gh 2.x: "account <user>").
_STATUS_LOGUEADO = """github.com
  ✓ Logged in to github.com account octocat (keyring)
  - Active account: true
  - Git operations protocol: https
  - Token: gho_************************************
  - Token scopes: 'gist', 'read:org', 'repo', 'workflow'
"""

# Forma antigua ("as <user>") que aun emiten algunas versiones.
_STATUS_LOGUEADO_VIEJO = "✓ Logged in to github.com as octocat (oauth_token)"

# Sin sesion: gh lo escribe en stderr y sale con codigo != 0.
_STATUS_NO_LOGUEADO = "You are not logged into any GitHub hosts. To log in, run: gh auth login"

# Arranque de `gh auth login --web` (one-time code + prompt de Enter con la url de device).
_INICIO = """! First copy your one-time code: AB12-CD34
Press Enter to open https://github.com/login/device in your browser...
"""

# Variante en la que gh no imprime la url entera (solo "github.com").
_INICIO_SIN_URL = "! First copy your one-time code: WXYZ-7890\nPress Enter to open github.com ...\n"


def test_parsear_estado_texto_logueado():
    r = pg.parsear_estado(_STATUS_LOGUEADO)
    assert r["logueado"] is True
    assert r["usuario"] == "octocat"
    assert r["scopes"] == ["gist", "read:org", "repo", "workflow"]


def test_parsear_estado_texto_logueado_viejo():
    r = pg.parsear_estado(_STATUS_LOGUEADO_VIEJO)
    assert r["logueado"] is True
    assert r["usuario"] == "octocat"


def test_parsear_estado_no_logueado():
    r = pg.parsear_estado(_STATUS_NO_LOGUEADO)
    assert r["logueado"] is False
    assert r["usuario"] is None
    assert r["scopes"] == []


def test_parsear_estado_json_gh_api_user():
    # Forma JSON de `gh api user`: el login viene en el cuerpo.
    r = pg.parsear_estado('{"login": "octocat", "id": 583231, "name": "The Octocat"}')
    assert r["logueado"] is True
    assert r["usuario"] == "octocat"


def test_parsear_estado_desconocido():
    r = pg.parsear_estado("ruido cualquiera sin forma reconocible")
    assert r["logueado"] is None
    assert r["usuario"] is None


def test_parsear_estado_tolera_ansi():
    sucio = "\x1b[0;32m✓\x1b[0m Logged in to github.com account octocat (keyring)\r\n"
    r = pg.parsear_estado(sucio)
    assert r["logueado"] is True
    assert r["usuario"] == "octocat"


def test_parsear_inicio_code_y_url():
    r = pg.parsear_inicio(_INICIO)
    assert r["codigo"] == "AB12-CD34"
    assert r["url"] == "https://github.com/login/device"


def test_parsear_inicio_url_por_defecto():
    # Sin url impresa cae a la constante conocida del device flow.
    r = pg.parsear_inicio(_INICIO_SIN_URL)
    assert r["codigo"] == "WXYZ-7890"
    assert r["url"] == "https://github.com/login/device"


def test_parsear_inicio_sin_code():
    r = pg.parsear_inicio("Logging into github.com ... esperando")
    assert r["codigo"] is None
    assert r["url"] == "https://github.com/login/device"


def test_argv_login_device_flow():
    assert pg._argv_login() == [
        "gh", "auth", "login", "--hostname", "github.com", "--git-protocol", "https", "--web",
    ]
