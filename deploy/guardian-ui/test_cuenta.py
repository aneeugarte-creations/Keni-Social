"""Tests de los parsers PUROS de cuenta.py (sin subprocess). Stdlib puro."""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cuenta  # noqa: E402

AHORA = datetime(2026, 6, 28, 12, 0, 0, tzinfo=timezone.utc)


def test_parsear_estado_logueado():
    crudo = '{"loggedIn": true, "authMethod": "claudeai", "apiProvider": "firstParty", "email": "ops@kenitech.io", "subscriptionType": "max", "orgName": "Keni"}'
    e = cuenta.parsear_estado(crudo)
    assert e["logueado"] is True
    assert e["metodo"] == "claudeai"
    assert e["email"] == "ops@kenitech.io"
    assert e["plan"] == "max"
    assert e["org"] == "Keni"


def test_parsear_estado_no_json():
    e = cuenta.parsear_estado("not logged in\n")
    assert e["logueado"] is None
    assert "not logged in" in e["crudo"]


def test_parsear_uso_con_medidores():
    salida = (
        "You are currently using Claude.\n"
        "Current session: 26% used · resets Jun 28 at 5:00pm (UTC)\n"
        "Current week (all models): 88% used · resets Jul 1, 7am (UTC)\n"
    )
    u = cuenta.parsear_uso(salida, ahora=AHORA)
    assert u["disponible"] is True
    assert len(u["medidores"]) == 2
    semana = u["medidores"][1]
    assert semana["pct"] == 88
    assert semana["reset_iso"] == "2026-07-01T07:00:00Z"


def test_parsear_uso_solo_frase():
    u = cuenta.parsear_uso("You are currently using an API key.\n")
    assert u["disponible"] is False
    assert u["medidores"] == []


def test_reset_a_iso():
    assert cuenta._reset_a_iso("Jul 1, 7am (UTC)", ahora=AHORA) == "2026-07-01T07:00:00Z"
    assert cuenta._reset_a_iso("Jun 28 at 5:39pm (UTC)", ahora=AHORA) == "2026-06-28T17:39:00Z"
    assert cuenta._reset_a_iso("frase rara", ahora=AHORA) is None
    assert cuenta._reset_a_iso(None) is None


def test_argv_login():
    assert cuenta._argv_login(console=False, email=None, sso=False) == ["claude", "auth", "login", "--claudeai"]
    assert cuenta._argv_login(console=True, email="a@b.c", sso=True) == [
        "claude", "auth", "login", "--console", "--email", "a@b.c", "--sso",
    ]
