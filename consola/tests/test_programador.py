"""Tests de la API de programación de piezas. OFFLINE, DB en tmp.

Cubre `POST /api/aprobacion/{id}/programar`: solo una pieza `en_revision` (con sus likes)
se puede programar para una fecha futura; pasa a `programado` con su `fecha_programada`.
NO es aprobación ni publicación: solo agenda. La salida a redes la dispara una persona
desde el feed (botón manual, `programador.programar_pieza_metricool`).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import repos

from .conftest import TOKEN_PRUEBA

_ORIGIN = {"Origin": "http://testserver"}
_MARCA = "unotv"


def _cli() -> TestClient:
    """TestClient por token de bootstrap (sin lanzadores reales)."""
    return TestClient(
        app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False),
        headers={"Authorization": f"Bearer {TOKEN_PRUEBA}"},
    )


def _crear(cli: TestClient, estado: str = "en_revision", **campos) -> dict:
    base = {"marca": _MARCA, "red": "x", "titulo": "T", "contenido": "C", "estado": estado}
    base.update(campos)
    r = cli.post("/api/piezas", json=base, headers=_ORIGIN)
    assert r.status_code == 200, r.text
    return r.json()["pieza"]


def _futuro_iso(minutos: int = 60) -> str:
    return (datetime.now() + timedelta(minutes=minutos)).strftime("%Y-%m-%dT%H:%M")


# --------------------------------------------------------------------------- #
# API: programar una pieza en revisión                                          #
# --------------------------------------------------------------------------- #


def test_programar_en_revision_pasa_a_programado(entorno):
    cli = _cli()
    pub = _crear(cli, estado="en_revision")
    fecha = _futuro_iso()
    r = cli.post(f"/api/aprobacion/{pub['id']}/programar", json={"fecha": fecha}, headers=_ORIGIN)
    assert r.status_code == 200, r.text
    prog = r.json()["pieza"]
    assert prog["estado"] == "programado"
    assert prog["fecha_programada"] == fecha
    assert prog["preparado_en"] == ""  # programar no publica


def test_programar_no_en_revision_409(entorno):
    """Solo una pieza en revisión (con sus likes) se puede programar; un borrador da 409."""
    cli = _cli()
    pub = _crear(cli, estado="borrador")
    r = cli.post(
        f"/api/aprobacion/{pub['id']}/programar", json={"fecha": _futuro_iso()}, headers=_ORIGIN
    )
    assert r.status_code == 409
    assert "revisión" in r.json()["error"].lower()


def test_programar_fecha_pasada_400(entorno):
    cli = _cli()
    pub = _crear(cli, estado="en_revision")
    pasado = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
    r = cli.post(f"/api/aprobacion/{pub['id']}/programar", json={"fecha": pasado}, headers=_ORIGIN)
    assert r.status_code == 400
    assert "futura" in r.json()["error"].lower()


def test_programar_fecha_invalida_400(entorno):
    cli = _cli()
    pub = _crear(cli, estado="en_revision")
    r = cli.post(f"/api/aprobacion/{pub['id']}/programar", json={"fecha": "no-es-fecha"}, headers=_ORIGIN)
    assert r.status_code == 400


def test_reprogramar_limpia_preparado_en(entorno):
    """Reprogramar una pieza deja `preparado_en` vacío (no quedó publicada)."""
    cli = _cli()
    pub = _crear(cli, estado="en_revision")
    cli.post(f"/api/aprobacion/{pub['id']}/programar", json={"fecha": _futuro_iso()}, headers=_ORIGIN)
    # Marcamos preparado_en a mano (como si la hubieran tocado) y reprogramamos: se limpia.
    repos.actualizar_pieza(pub["id"], {"preparado_en": "2026-05-27T10:00", "estado": "en_revision"})
    cli.post(f"/api/aprobacion/{pub['id']}/programar", json={"fecha": _futuro_iso(120)}, headers=_ORIGIN)
    assert repos.obtener_pieza(pub["id"])["preparado_en"] == ""
