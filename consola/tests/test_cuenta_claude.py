"""Tests del modulo `cuenta_claude`: PARSERS puros (texto del CLI -> dict). OFFLINE.

No tocan subprocess ni red: solo ejercitan `parsear_estado`, `parsear_uso`, `_limpiar` y la
composicion del argv de login. La parte interactiva (PTY) y los runners (subprocess) se
cubren aparte / en el listener de control.
"""

from __future__ import annotations

from datetime import datetime, timezone

from keni_consola import cuenta_claude as cc

# Reloj fijo para inferir el ano del reset (que el CLI no incluye): mediados de junio 2026.
_AHORA = datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)

# Salida REAL de `claude -p /usage` con login de suscripcion (medidor completo).
_USAGE_COMPLETO = """You are currently using your subscription to power your Claude Code usage

Current session: 26% used · resets Jun 15 at 7:39pm (America/Mexico_City)
Current week (all models): 67% used · resets Jun 17 at 9:59am (America/Mexico_City)
Current week (Sonnet only): 2% used · resets Jun 17 at 9:59am (America/Mexico_City)
"""

# Salida REAL con token de entorno (solo la frase, sin medidor).
_USAGE_SOLO_FRASE = "You are currently using your subscription to power your Claude Code usage"


def test_parsear_uso_medidor_completo():
    r = cc.parsear_uso(_USAGE_COMPLETO, ahora=_AHORA)
    assert r["disponible"] is True
    assert r["mensaje"].startswith("You are currently using")
    medidores = r["medidores"]
    assert [m["pct"] for m in medidores] == [26, 67, 2]
    assert medidores[0]["etiqueta"] == "Current session"
    assert medidores[1]["etiqueta"] == "Current week (all models)"
    assert "Jun 15 at 7:39pm" in medidores[0]["reset"]
    # 7:39pm CDMX (UTC-6) = 01:39 UTC del dia siguiente; el front lo pinta en zona de display.
    assert medidores[0]["reset_iso"] == "2026-06-16T01:39:00Z"


def test_reset_a_iso_zona_utc_y_separador_coma():
    # Forma del CLI con la zona del servidor (UTC) y separador ", " en vez de " at ".
    assert cc._reset_a_iso("Jun 25, 2:39am (UTC)", _AHORA) == "2026-06-25T02:39:00Z"
    assert cc._reset_a_iso("Jul 1 at 1:00pm (UTC)", _AHORA) == "2026-07-01T13:00:00Z"


def test_reset_a_iso_hora_sin_minutos():
    # La ventana SEMANAL resetea en hora redonda y el CLI la imprime sin minutos
    # ("Jul 1, 7am (UTC)"): se interpreta como :00 y rellena reset_iso.
    assert cc._reset_a_iso("Jul 1, 7am (UTC)", _AHORA) == "2026-07-01T07:00:00Z"
    assert cc._reset_a_iso("Jul 1 at 12pm (UTC)", _AHORA) == "2026-07-01T12:00:00Z"
    assert cc._reset_a_iso("Jul 1, 12am (UTC)", _AHORA) == "2026-07-01T00:00:00Z"


def test_parsear_uso_semana_sin_minutos_rellena_reset_iso():
    # Medidor semanal real con hora redonda sin minutos: reset_iso debe quedar relleno (no null).
    salida = "Current week (all models): 67% used · resets Jul 1, 7am (UTC)\n"
    r = cc.parsear_uso(salida, ahora=_AHORA)
    assert r["disponible"] is True
    assert r["medidores"][0]["reset_iso"] == "2026-07-01T07:00:00Z"


def test_reset_a_iso_infiere_vuelta_de_ano():
    # Reset en enero leido a fin de diciembre: el ano que viene (el reset siempre es futuro).
    fin_anio = datetime(2026, 12, 31, 23, 0, tzinfo=timezone.utc)
    assert cc._reset_a_iso("Jan 2 at 6:00am (UTC)", fin_anio) == "2027-01-02T06:00:00Z"


def test_reset_a_iso_intratable_es_none():
    # Sin reset, frase irreconocible o zona desconocida -> None (el front cae a la frase cruda).
    assert cc._reset_a_iso(None, _AHORA) is None
    assert cc._reset_a_iso("en cuanto se pueda", _AHORA) is None
    assert cc._reset_a_iso("Jun 15 at 7:39pm (Marte/Olympus)", _AHORA) is None


def test_parsear_uso_solo_frase_no_disponible():
    r = cc.parsear_uso(_USAGE_SOLO_FRASE)
    assert r["disponible"] is False
    assert r["medidores"] == []
    assert r["mensaje"] == _USAGE_SOLO_FRASE


def test_parsear_uso_tolera_ansi_y_cr():
    # Una TTY mete colores ANSI y \r: el parser debe limpiarlos y aun reconocer el medidor.
    sucio = "\x1b[2mCurrent session: 10% used · resets Jul 1 at 1:00pm (UTC)\x1b[0m\r\n"
    r = cc.parsear_uso(sucio, ahora=_AHORA)
    assert r["disponible"] is True
    assert r["medidores"][0]["pct"] == 10
    assert r["medidores"][0]["reset_iso"] == "2026-07-01T13:00:00Z"


def test_parsear_estado_login_credenciales():
    # Forma REAL del `auth status` con login por credenciales (incluye email/plan/org).
    r = cc.parsear_estado(
        '{"loggedIn": true, "authMethod": "claude.ai", "apiProvider": "firstParty",'
        ' "email": "owner@kenitech.io", "orgName": "Acme", "subscriptionType": "max"}'
    )
    assert r["logueado"] is True
    assert r["metodo"] == "claude.ai"
    assert r["email"] == "owner@kenitech.io"
    assert r["plan"] == "max"
    assert r["org"] == "Acme"


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
    # Con `hasta`, _leer_disponible devuelve EN CUANTO aparece la URL (claude auth login
    # imprime la URL en <1s pero NO cierra), sin esperar al deadline.
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


def test_uso_cachea_y_sirve_ultimo_bueno(monkeypatch, tmp_path):
    # Núcleo del "nunca la frase": una lectura con medidor se cachea; la siguiente, que solo
    # trae la frase, sirve el ÚLTIMO bueno (cacheado:true) en vez de la frase pelada.
    import subprocess

    monkeypatch.setattr(cc, "_dir_cache", lambda: tmp_path)
    monkeypatch.setattr(
        cc, "_ejecutar",
        lambda argv, *, timeout: subprocess.CompletedProcess(argv, 0, _USAGE_COMPLETO, ""),
    )
    r1 = cc.uso()
    assert r1["disponible"] is True and r1["cacheado"] is False
    assert [m["pct"] for m in r1["medidores"]] == [26, 67, 2]

    monkeypatch.setattr(
        cc, "_ejecutar",
        lambda argv, *, timeout: subprocess.CompletedProcess(argv, 0, _USAGE_SOLO_FRASE, ""),
    )
    r2 = cc.uso()
    assert r2["disponible"] is True and r2["cacheado"] is True
    assert [m["pct"] for m in r2["medidores"]] == [26, 67, 2]
    assert r2["actualizado"] == r1["actualizado"]


def test_uso_sin_cache_cae_a_no_disponible(monkeypatch, tmp_path):
    # Sin un buen medidor previo, una lectura solo-frase sí cae a disponible:false (cold start).
    import subprocess

    monkeypatch.setattr(cc, "_dir_cache", lambda: tmp_path)
    monkeypatch.setattr(
        cc, "_ejecutar",
        lambda argv, *, timeout: subprocess.CompletedProcess(argv, 0, _USAGE_SOLO_FRASE, ""),
    )
    r = cc.uso()
    assert r["disponible"] is False and r["medidores"] == []


# --- Selector de cuenta (a|b) -> CLAUDE_CONFIG_DIR ------------------------- #


def test_config_dir_selector_a_es_none(monkeypatch):
    # La cuenta A (def, None, o valor desconocido) NO fuerza config-dir: hereda el del
    # contenedor -> comportamiento IDENTICO al de siempre.
    monkeypatch.setenv("KENI_CLAUDE_CFG_DIR_B", "/data/claude-cfg-b")
    assert cc._config_dir_de("a") is None
    assert cc._config_dir_de(None) is None
    assert cc._config_dir_de("zzz") is None


def test_config_dir_selector_b(monkeypatch):
    # La cuenta B mapea a su config-dir (def /data/claude-cfg-b; env-configurable).
    monkeypatch.delenv("KENI_CLAUDE_CFG_DIR_B", raising=False)
    assert cc._config_dir_de("b") == "/data/claude-cfg-b"
    monkeypatch.setenv("KENI_CLAUDE_CFG_DIR_B", "/data/otro-b")
    assert cc._config_dir_de("B") == "/data/otro-b"  # selector case-insensitive


def test_correr_cuenta_b_inyecta_config_dir(monkeypatch):
    # estado(cuenta="b") corre `claude` con el config-dir de B; la cuenta A NO pasa config_dir.
    import subprocess

    capturado: list[tuple] = []

    def _fake(argv, *, timeout, config_dir=None):
        capturado.append((argv, config_dir))
        return subprocess.CompletedProcess(argv, 0, '{"loggedIn": true}', "")

    monkeypatch.setattr(cc, "_ejecutar", _fake)
    monkeypatch.setenv("KENI_CLAUDE_CFG_DIR_B", "/data/claude-cfg-b")

    cc.estado("a")
    cc.estado("b")
    assert capturado[0][1] is None  # cuenta A: hereda el entorno (idéntico)
    assert capturado[1][1] == "/data/claude-cfg-b"  # cuenta B: su config-dir


def test_fichero_cache_uso_por_cuenta():
    # La cuenta A conserva el nombre histórico; la B usa un sufijo (no pisa el de A).
    assert cc._fichero_cache_uso("a") == "usage-cache.json"
    assert cc._fichero_cache_uso(None) == "usage-cache.json"
    assert cc._fichero_cache_uso("b") == "usage-cache-b.json"


def test_uso_cuenta_b_cachea_aparte(monkeypatch, tmp_path):
    # uso(cuenta="b") persiste su cache en el fichero de B sin tocar el de A.
    import subprocess

    monkeypatch.setattr(cc, "_dir_cache", lambda: tmp_path)
    monkeypatch.setattr(
        cc, "_ejecutar",
        lambda argv, *, timeout, config_dir=None: subprocess.CompletedProcess(
            argv, 0, _USAGE_COMPLETO, ""
        ),
    )
    r = cc.uso(cuenta="b")
    assert r["disponible"] is True
    assert (tmp_path / "usage-cache-b.json").exists()
    assert not (tmp_path / "usage-cache.json").exists()


# --------------------------------------------------------------------------- #
# Caducidad de la credencial (lo que decide si la cuenta puede generar)        #
# --------------------------------------------------------------------------- #


def _creds(expira: datetime, *, refresh: bool = True) -> dict:
    """Blob de credenciales como el que persiste `claude` (solo los campos que se miran)."""
    oauth = {"expiresAt": int(expira.timestamp() * 1000), "accessToken": "no-se-mira"}
    if refresh:
        oauth["refreshToken"] = "tampoco-se-mira"
    return {"claudeAiOauth": oauth}


def test_parsear_caducidad_credencial_viva():
    viva = _creds(_AHORA.replace(hour=20))
    r = cc.parsear_caducidad(viva, _AHORA)
    assert r["conocida"] is True and r["caducada"] is False
    assert r["tiene_refresh"] is True
    assert r["segundos_restantes"] == 8 * 3600
    # NUNCA se filtra el token: solo la caducidad y si hay refresh.
    assert "accessToken" not in r and "refreshToken" not in r


def test_parsear_caducidad_credencial_muerta_y_sin_refresh():
    """El caso que paró la generación: token caducado y SIN refresh (no se renueva solo)."""
    muerta = _creds(_AHORA.replace(hour=11), refresh=False)
    r = cc.parsear_caducidad(muerta, _AHORA)
    assert r["caducada"] is True
    assert r["tiene_refresh"] is False
    assert r["segundos_restantes"] == -3600


def test_parsear_caducidad_sin_dato_no_afirma_nada():
    # Sin `expiresAt` no hay referencia temporal: `conocida=False` para no avisar en falso.
    for entrada in (None, {}, {"claudeAiOauth": {}}, {"claudeAiOauth": {"expiresAt": "ayer"}}):
        assert cc.parsear_caducidad(entrada, _AHORA)["conocida"] is False


def test_caducidad_lee_el_fichero_de_la_cuenta(monkeypatch, tmp_path):
    import json

    (tmp_path / ".credentials.json").write_text(
        json.dumps(_creds(_AHORA.replace(hour=20))), encoding="utf-8"
    )
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    assert cc.caducidad("a", _AHORA)["caducada"] is False


def test_caducidad_sin_fichero_es_best_effort(monkeypatch, tmp_path):
    # Fichero ausente/ilegible: no lanza y no afirma nada (es vigilancia, no camino critico).
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    assert cc.caducidad("a", _AHORA)["conocida"] is False


def test_estado_adjunta_la_caducidad_de_la_credencial(monkeypatch, tmp_path):
    """`estado()` no se queda en `loggedIn`: dice tambien si esa sesion todavia sirve.

    El CLI responde `loggedIn: true` mientras haya credenciales guardadas, aunque el token este
    muerto y cada `claude -p` falle con un 401. El panel necesita las dos cosas.
    """
    import json
    import subprocess

    (tmp_path / ".credentials.json").write_text(
        json.dumps(_creds(_AHORA.replace(hour=11), refresh=False)), encoding="utf-8"
    )
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(
        cc, "_correr",
        lambda argv, *, timeout, cuenta=None: subprocess.CompletedProcess(
            argv, 0, '{"loggedIn": true, "authMethod": "claude.ai"}', ""
        ),
    )
    r = cc.estado("a")
    assert r["logueado"] is True  # el CLI insiste en que hay sesion...
    assert r["caducidad"]["caducada"] is True  # ...pero no sirve
    assert r["caducidad"]["tiene_refresh"] is False


def test_estado_sin_cli_sigue_trayendo_caducidad(monkeypatch, tmp_path):
    # Aun sin `claude` en la maquina, la credencial se lee del fichero: el panel no se queda mudo.
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))

    def _sin_cli(argv, *, timeout, cuenta=None):
        raise FileNotFoundError(argv[0])

    monkeypatch.setattr(cc, "_correr", _sin_cli)
    r = cc.estado("a")
    assert r["logueado"] is None and r["error"] == "claude no disponible"
    assert r["caducidad"]["conocida"] is False
