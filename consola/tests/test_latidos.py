"""Tests de los LATIDOS de daemons: db_latidos (upsert/contadores), la fachada
best-effort `latidos.py` (jamás propaga, throttle de ciclo, fichero de liveness),
la instrumentación de `bucle_gateado` y el endpoint `/api/sistema/daemons`.

Los tests de BD usan el Postgres de pruebas (fixture `entorno`); los de la fachada y el
bucle van con dobles (sin BD): el contrato clave es que un latido NUNCA rompe un barrido.
"""

from __future__ import annotations

import logging

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth, daemon_util, db, latidos

from .conftest import TOKEN_PRUEBA

_ORIGIN = {"Origin": "http://testserver"}
CLAVE = "clave-de-prueba"
_LOG = logging.getLogger("test_latidos")


def _cli_admin() -> TestClient:
    auth.crear_usuario("u", CLAVE, "admin")
    c = TestClient(app_modulo.crear_app(token=TOKEN_PRUEBA))
    r = c.post(
        "/api/auth/login", json={"usuario": "u", "password": CLAVE}, headers=_ORIGIN
    )
    assert r.status_code == 200
    return c


# --------------------------------------------------------------------------- #
# db_latidos: upsert y contadores                                              #
# --------------------------------------------------------------------------- #


def test_latido_ciclo_upsert(entorno):
    db.latido_ciclo("demo", activo=True, intervalo_seg=300.0, tick_seg=60.0)
    db.latido_ciclo("demo", activo=False, intervalo_seg=600.0, tick_seg=60.0)
    (fila,) = [f for f in db.listar_latidos() if f["daemon"] == "demo"]
    assert fila["activo"] is False
    assert fila["intervalo_seg"] == 600.0
    assert fila["visto"]
    # El ciclo NO toca los campos de barrido.
    assert fila["barridos"] == 0
    assert fila["ultimo_barrido"] == ""


def test_latido_barrido_ok_y_error_acumulan(entorno):
    db.latido_barrido("demo", ok=True, intervalo_seg=60.0, tick_seg=60.0, duracion_ms=12)
    db.latido_barrido(
        "demo", ok=False, intervalo_seg=60.0, tick_seg=60.0, duracion_ms=5,
        error_txt="ValueError('x')",
    )
    (fila,) = [f for f in db.listar_latidos() if f["daemon"] == "demo"]
    assert fila["barridos"] == 2
    assert fila["errores"] == 1
    assert fila["ultimo_ok"] and fila["ultimo_error"]
    assert fila["error_txt"] == "ValueError('x')"
    assert fila["duracion_ms"] == 5
    # Un barrido marca el daemon como activo y visto.
    assert fila["activo"] is True
    assert fila["visto"]


def test_error_txt_truncado(entorno):
    db.latido_barrido(
        "demo", ok=False, intervalo_seg=1.0, tick_seg=1.0, error_txt="x" * 5000
    )
    (fila,) = [f for f in db.listar_latidos() if f["daemon"] == "demo"]
    assert len(fila["error_txt"]) == 500


# --------------------------------------------------------------------------- #
# Fachada latidos: best-effort SIN BD + throttle + fichero                     #
# --------------------------------------------------------------------------- #


def test_fachada_no_propaga_sin_bd(monkeypatch):
    # Sin DATABASE_URL ni Postgres: registrar un latido debe ser un no-op silencioso.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    for var in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "POSTGRES_HOST"):
        monkeypatch.delenv(var, raising=False)
    latidos.barrido("x", ok=True, intervalo_seg=1.0, tick_seg=1.0)
    latidos.ciclo("x", activo=True, intervalo_seg=1.0, tick_seg=1.0)


def test_ciclo_throttleado(monkeypatch):
    llamadas: list[str] = []

    def _falso_ciclo(daemon, **kwargs):
        llamadas.append(daemon)

    from keni_consola import db_latidos

    monkeypatch.setattr(db_latidos, "latido_ciclo", _falso_ciclo)
    monkeypatch.setattr(latidos, "_ultimo_ciclo", {})
    latidos.ciclo("t", activo=True, intervalo_seg=1.0, tick_seg=1.0)
    latidos.ciclo("t", activo=True, intervalo_seg=1.0, tick_seg=1.0)  # dentro del throttle
    assert llamadas == ["t"]


def test_fichero_latido(tmp_path, monkeypatch):
    ruta = tmp_path / "latido"
    monkeypatch.setenv(latidos.ENV_FICHERO_LATIDO, str(ruta))
    latidos.tocar_fichero()
    assert ruta.exists()
    assert ruta.read_text().strip().isdigit()


def test_nombre_de_sweep_alias():
    def sweep():  # __module__ = tests.test_latidos -> sin alias, nombre corto del modulo
        pass

    assert latidos.nombre_de_sweep(sweep) == "test_latidos"
    assert latidos._ALIAS["_barrido"] == "pipeline"


# --------------------------------------------------------------------------- #
# bucle_gateado instrumentado (dobles, sin BD)                                 #
# --------------------------------------------------------------------------- #


def test_bucle_gateado_registra_barrido_ok_y_error(monkeypatch):
    registros: list[tuple[str, bool, str]] = []

    def _falso_barrido(daemon, *, ok, intervalo_seg, tick_seg, duracion_ms=0, error=""):
        registros.append((daemon, ok, error))

    monkeypatch.setattr(latidos, "barrido", _falso_barrido)
    monkeypatch.setattr(latidos, "ciclo", lambda *a, **k: None)

    daemon_util.bucle_gateado(
        activo_fn=lambda: True,
        intervalo_seg_fn=lambda: 0.0,
        sweep_fn=lambda: None,
        tick_seg=0.001,
        log=_LOG,
        nombre="mi-daemon",
        _max_vueltas=1,
    )

    def explota():
        raise ValueError("boom")

    daemon_util.bucle_gateado(
        activo_fn=lambda: True,
        intervalo_seg_fn=lambda: 0.0,
        sweep_fn=explota,
        tick_seg=0.001,
        log=_LOG,
        nombre="mi-daemon",
        _max_vueltas=1,
    )
    assert registros[0] == ("mi-daemon", True, "")
    assert registros[1][0:2] == ("mi-daemon", False)
    assert "boom" in registros[1][2]


def test_bucle_gateado_apagado_late_como_ciclo(monkeypatch):
    ciclos: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        latidos, "ciclo", lambda d, *, activo, **k: ciclos.append((d, activo))
    )
    monkeypatch.setattr(latidos, "barrido", lambda *a, **k: None)
    daemon_util.bucle_gateado(
        activo_fn=lambda: False,
        intervalo_seg_fn=lambda: 3600.0,
        sweep_fn=lambda: None,
        tick_seg=0.001,
        log=_LOG,
        nombre="apagado",
        _max_vueltas=2,
    )
    assert ciclos == [("apagado", False), ("apagado", False)]


# --------------------------------------------------------------------------- #
# Endpoint /api/sistema/daemons                                                #
# --------------------------------------------------------------------------- #


def test_endpoint_daemons_contrato_y_estados(entorno):
    db.latido_barrido("sano", ok=True, intervalo_seg=60.0, tick_seg=60.0, duracion_ms=10)
    db.latido_barrido(
        "roto", ok=False, intervalo_seg=60.0, tick_seg=60.0, error_txt="RuntimeError('x')"
    )
    db.latido_ciclo("dormido", activo=False, intervalo_seg=3600.0, tick_seg=60.0)
    c = _cli_admin()
    r = c.get("/api/sistema/daemons")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["error"] is None
    por_nombre = {d["daemon"]: d for d in cuerpo["daemons"]}
    assert por_nombre["sano"]["estado"] == "ok"
    assert por_nombre["sano"]["edad_seg"] is not None
    assert por_nombre["roto"]["estado"] == "error"
    assert por_nombre["roto"]["error_txt"] == "RuntimeError('x')"
    assert por_nombre["dormido"]["estado"] == "inactivo"


def test_endpoint_daemons_atrasado(entorno):
    # Un latido con `visto` viejo (mas alla del umbral) debe salir "atrasado".
    db.latido_barrido("zombi", ok=True, intervalo_seg=60.0, tick_seg=60.0)
    from keni_consola._db_comun import _conectar

    con = _conectar()
    try:
        con.execute(
            "UPDATE daemon_latidos SET visto = ? WHERE daemon = ?",
            ("2020-01-01T00:00:00", "zombi"),
        )
        con.commit()
    finally:
        con.close()
    c = _cli_admin()
    r = c.get("/api/sistema/daemons")
    por_nombre = {d["daemon"]: d for d in r.json()["daemons"]}
    assert por_nombre["zombi"]["estado"] == "atrasado"


def test_endpoint_daemons_editor_403(entorno):
    auth.crear_usuario("e", CLAVE, "editor")
    c = TestClient(app_modulo.crear_app(token=TOKEN_PRUEBA))
    assert (
        c.post(
            "/api/auth/login", json={"usuario": "e", "password": CLAVE}, headers=_ORIGIN
        ).status_code
        == 200
    )
    assert c.get("/api/sistema/daemons").status_code == 403
