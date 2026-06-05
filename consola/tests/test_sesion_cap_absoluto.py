"""Tests del TOPE ABSOLUTO de vida de una sesion (item LOW: seguridad).

`auth.sesion_valida` desliza `expira = now + horas_sesion()` en cada uso, asi que un token
activo (o robado-pero-usado) nunca caducaba: la columna `creada` se guardaba pero no se
aplicaba. El cap absoluto (`KENI_CONSOLA_SESION_MAX_HORAS`, def 720h = 30 d) RECHAZA y BORRA
una sesion cuya antiguedad desde `creada` supera el tope, AUNQUE se acabe de usar. La ventana
deslizante (idle) sigue intacta.

OFFLINE: Postgres de pruebas (fixture `entorno`); sin red.
"""

from __future__ import annotations

from datetime import timedelta

from keni_consola import auth, db
from keni_consola.auth import _comun

_CLAVE = "clave-de-prueba-123"


def _backdatar_creada(token: str, horas: float) -> None:
    """Retrasa `creada` de una sesion `horas` hacia el pasado (sin tocar `expira`/`ultimo_uso`).

    Simula una sesion VIEJA que se siguio renovando: `expira` permanece en el futuro (deslizante
    vigente), pero `creada` queda lo bastante atras como para que el cap absoluto la mate.
    """
    creada = _comun.ahora() - timedelta(hours=horas)
    con = db.conectar()
    try:
        con.execute(
            "UPDATE sesiones SET creada = ? WHERE token = ?",
            (_comun.iso(creada), token),
        )
        con.commit()
    finally:
        con.close()


def _sesion_existe(token: str) -> bool:
    con = db.conectar()
    try:
        return con.execute(
            "SELECT 1 FROM sesiones WHERE token = ?", (token,)
        ).fetchone() is not None
    finally:
        con.close()


def test_sesion_dentro_del_cap_es_valida(entorno):
    """Una sesion fresca (dentro del cap) valida normalmente."""
    u = auth.crear_usuario("ana", _CLAVE, "editor")
    token = auth.crear_sesion(u["id"])
    actual = auth.sesion_valida(token)
    assert actual is not None
    assert actual["usuario"] == "ana"
    assert _sesion_existe(token)  # sigue viva


def test_sesion_pasado_el_cap_se_rechaza_y_borra(entorno, monkeypatch):
    """Una sesion mas vieja que el cap absoluto se rechaza y se BORRA, aunque `expira` sea futura."""
    # Cap bajo (24h) para no depender del default de 30 d en el test.
    monkeypatch.setenv("KENI_CONSOLA_SESION_MAX_HORAS", "24")
    u = auth.crear_usuario("beto", _CLAVE, "editor")
    token = auth.crear_sesion(u["id"])
    # La sesion se creo hace 48h (> cap de 24h) pero `expira` sigue en el futuro (deslizante).
    _backdatar_creada(token, horas=48)
    assert auth.sesion_valida(token) is None  # rechazada por el cap absoluto
    assert not _sesion_existe(token)  # y borrada (no se reutiliza)


def test_sesion_renovada_sin_pasar_el_cap_sigue_valida(entorno, monkeypatch):
    """Justo por DEBAJO del cap (renovada pero joven) la sesion sigue siendo valida."""
    monkeypatch.setenv("KENI_CONSOLA_SESION_MAX_HORAS", "24")
    u = auth.crear_usuario("caro", _CLAVE, "editor")
    token = auth.crear_sesion(u["id"])
    _backdatar_creada(token, horas=12)  # 12h < cap de 24h
    assert auth.sesion_valida(token) is not None
    assert _sesion_existe(token)


def test_default_cap_generoso_no_corta_sesion_normal(entorno):
    """Sin configurar el cap, el default (720h/30 d) NO corta una sesion de uso normal."""
    # Una sesion de hace 13h (mas que la ventana deslizante de 12h, pero MUY por debajo de 30 d).
    u = auth.crear_usuario("dani", _CLAVE, "editor")
    token = auth.crear_sesion(u["id"])
    _backdatar_creada(token, horas=13)
    assert auth.sesion_valida(token) is not None  # el default generoso no la toca
