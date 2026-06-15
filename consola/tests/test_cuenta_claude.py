"""Tests del modulo `cuenta_claude`: PARSERS puros (texto del CLI -> dict). OFFLINE.

No tocan subprocess ni red: solo ejercitan `parsear_estado`, `parsear_uso`, `_limpiar` y la
composicion del argv de login. La parte interactiva (PTY) y los runners (subprocess) se
cubren aparte / en el listener de control.
"""

from __future__ import annotations

from keni_consola import cuenta_claude as cc

# Salida REAL de `claude -p /usage` con login de suscripcion (medidor completo).
_USAGE_COMPLETO = """You are currently using your subscription to power your Claude Code usage

Current session: 26% used · resets Jun 15 at 7:39pm (America/Mexico_City)
Current week (all models): 67% used · resets Jun 17 at 9:59am (America/Mexico_City)
Current week (Sonnet only): 2% used · resets Jun 17 at 9:59am (America/Mexico_City)
"""

# Salida REAL con token de entorno (solo la frase, sin medidor).
_USAGE_SOLO_FRASE = "You are currently using your subscription to power your Claude Code usage"


def test_parsear_uso_medidor_completo():
    r = cc.parsear_uso(_USAGE_COMPLETO)
    assert r["disponible"] is True
    assert r["mensaje"].startswith("You are currently using")
    medidores = r["medidores"]
    assert [m["pct"] for m in medidores] == [26, 67, 2]
    assert medidores[0]["etiqueta"] == "Current session"
    assert medidores[1]["etiqueta"] == "Current week (all models)"
    assert "Jun 15 at 7:39pm" in medidores[0]["reset"]


def test_parsear_uso_solo_frase_no_disponible():
    r = cc.parsear_uso(_USAGE_SOLO_FRASE)
    assert r["disponible"] is False
    assert r["medidores"] == []
    assert r["mensaje"] == _USAGE_SOLO_FRASE


def test_parsear_uso_tolera_ansi_y_cr():
    # Una TTY mete colores ANSI y \r: el parser debe limpiarlos y aun reconocer el medidor.
    sucio = "\x1b[2mCurrent session: 10% used · resets Jul 1 at 1:00pm (UTC)\x1b[0m\r\n"
    r = cc.parsear_uso(sucio)
    assert r["disponible"] is True
    assert r["medidores"][0]["pct"] == 10


def test_parsear_estado_oauth_token():
    r = cc.parsear_estado('{"loggedIn": true, "authMethod": "oauth_token", "apiProvider": "firstParty"}')
    assert r["logueado"] is True
    assert r["metodo"] == "oauth_token"
    assert r["proveedor"] == "firstParty"


def test_parsear_estado_no_json_desconocido():
    r = cc.parsear_estado("not json at all")
    assert r["logueado"] is None
    assert r["metodo"] is None


def test_argv_login_variantes():
    assert cc._argv_login(console=False, email=None, sso=False) == [
        "claude", "auth", "login", "--claudeai",
    ]
    assert cc._argv_login(console=True, email="a@b.com", sso=True) == [
        "claude", "auth", "login", "--console", "--email", "a@b.com", "--sso",
    ]


def test_bearer_persistido_estable_y_compartido(tmp_path):
    # Crea el bearer la primera vez y lo REUSA (mismo valor) en llamadas posteriores: back y
    # daemons, apuntando al mismo /data, comparten el secreto sin configurar nada.
    b1 = cc._bearer_persistido(tmp_path)
    b2 = cc._bearer_persistido(tmp_path)
    assert b1 and b1 == b2
    fichero = tmp_path / cc._FICHERO_BEARER
    assert fichero.read_text().strip() == b1
    # 0600: solo el dueño.
    assert (fichero.stat().st_mode & 0o777) == 0o600


def test_leer_disponible_corta_al_ver_url():
    # REGRESION del timeout: con `hasta`, _leer_disponible devuelve EN CUANTO aparece la URL
    # (claude auth login imprime la URL en <1s pero NO cierra), sin esperar al deadline.
    import os
    import time

    r, w = os.pipe()
    os.write(w, b"Opening browser...\nvisit: https://claude.com/x?code=true&a=1 \nPaste code >")
    t0 = time.monotonic()
    txt = cc._leer_disponible(r, deadline=t0 + 5.0, hasta=cc._RE_URL_COMPLETA)
    transcurrido = time.monotonic() - t0
    os.close(r)
    os.close(w)
    assert transcurrido < 2.0, f"no cortó pronto: {transcurrido}s"
    assert "https://claude.com/x?code=true&a=1" in txt


def test_bearer_efectivo_respeta_override(monkeypatch, tmp_path):
    # Un KENI_CONTROL_BEARER explícito GANA sobre el auto-persistido.
    monkeypatch.setattr(cc, "_bearer_persistido", lambda _dir: "auto")
    monkeypatch.setenv("KENI_CONTROL_BEARER", "explicito")
    assert cc.bearer_efectivo() == "explicito"
    monkeypatch.delenv("KENI_CONTROL_BEARER", raising=False)
    assert cc.bearer_efectivo() == "auto"
