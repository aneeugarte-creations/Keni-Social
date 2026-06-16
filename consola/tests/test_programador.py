"""Tests del programador de piezas (#9, Fase 3). OFFLINE, DB en tmp.

Cubre las dos mitades del scheduling:
  1) La API `POST /api/aprobacion/{id}/programar`: solo una pieza `en_revision` (con sus likes), fecha futura.
  2) El programador del servidor (`programador.preparar_vencidas`): al vencer la fecha,
     la pieza se PREPARA en dry-run (estampa `preparado_en`) y NO se publica (sigue en
     `programado`, nunca pasa a `publicado`). El posteo real (vía Metricool) esta GATED
     por `KENI_PUBLICAR_REAL`.

El barrido es una funcion PURA con `ahora` inyectado: se testea sin hilo ni reloj real.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import programador, repos
from keni_consola.programador import piezas_vencidas, preparar_vencidas

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
# API: programar una pieza en revisión                                           #
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
    assert prog["preparado_en"] == ""  # aun no vencio: NO preparada


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


# --------------------------------------------------------------------------- #
# Barrido del programador: prepara en dry-run, NO publica                     #
# --------------------------------------------------------------------------- #


def test_piezas_vencidas_pura(entorno):
    """`piezas_vencidas` selecciona solo las programadas vencidas y aun sin preparar."""
    ahora = datetime(2026, 5, 27, 12, 0)
    vencida = {"id": "a", "estado": "programado", "fecha_programada": "2026-05-27T11:00", "preparado_en": ""}
    futura = {"id": "b", "estado": "programado", "fecha_programada": "2026-05-27T13:00", "preparado_en": ""}
    ya_prep = {
        "id": "c", "estado": "programado",
        "fecha_programada": "2026-05-27T10:00", "preparado_en": "2026-05-27T10:01",
    }
    otro_estado = {"id": "d", "estado": "en_revision", "fecha_programada": "2026-05-27T10:00", "preparado_en": ""}
    sin_fecha = {"id": "e", "estado": "programado", "fecha_programada": "", "preparado_en": ""}
    vencidas = piezas_vencidas([vencida, futura, ya_prep, otro_estado, sin_fecha], ahora)
    assert [p["id"] for p in vencidas] == ["a"]


def test_preparar_vencidas_marca_dry_run_sin_publicar(entorno):
    """Al vencer, la pieza se prepara (preparado_en) y SIGUE en programado: NO se publica."""
    cli = _cli()
    pub = _crear(cli, estado="programado", fecha_programada=_futuro_iso(-30))  # ya pasada
    # `_crear` no admite fecha pasada por la API de aprobacion; aqui la pusimos directa
    # en el alta (la API de piezas no valida que sea futura), simulando una pieza
    # cuya hora ya llego.
    futuro_pasado = (datetime.now() - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M")
    repos.actualizar_pieza(pub["id"], {"fecha_programada": futuro_pasado})

    preparadas = preparar_vencidas(datetime.now())
    assert preparadas == 1

    actualizada = repos.obtener_pieza(pub["id"])
    assert actualizada["estado"] == "programado"  # NO publicado (gating KENI_PUBLICAR_REAL)
    assert actualizada["preparado_en"]  # marca dry-run puesta


def test_preparar_vencidas_idempotente(entorno):
    """Un segundo barrido no vuelve a preparar lo ya preparado (no re-cuenta)."""
    cli = _cli()
    pub = _crear(cli, estado="programado")
    pasado = (datetime.now() - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M")
    repos.actualizar_pieza(pub["id"], {"fecha_programada": pasado})
    assert preparar_vencidas(datetime.now()) == 1
    assert preparar_vencidas(datetime.now()) == 0  # ya preparada


def test_preparar_no_toca_futuras(entorno):
    """Una pieza programada para el futuro NO se prepara todavia."""
    cli = _cli()
    pub = _crear(cli, estado="en_revision")
    cli.post(f"/api/aprobacion/{pub['id']}/programar", json={"fecha": _futuro_iso(120)}, headers=_ORIGIN)
    assert preparar_vencidas(datetime.now()) == 0
    assert repos.obtener_pieza(pub["id"])["preparado_en"] == ""


def test_reprogramar_limpia_la_marca_dry_run(entorno):
    """Reprogramar una pieza vuelve a dejar preparado_en vacio (re-arranca)."""
    cli = _cli()
    pub = _crear(cli, estado="programado")
    pasado = (datetime.now() - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M")
    repos.actualizar_pieza(pub["id"], {"fecha_programada": pasado})
    preparar_vencidas(datetime.now())
    assert repos.obtener_pieza(pub["id"])["preparado_en"]

    # Volvemos a en_revision y reprogramamos a futuro: la marca dry-run se limpia.
    repos.actualizar_pieza(pub["id"], {"estado": "en_revision"})
    cli.post(f"/api/aprobacion/{pub['id']}/programar", json={"fecha": _futuro_iso()}, headers=_ORIGIN)
    assert repos.obtener_pieza(pub["id"])["preparado_en"] == ""


def test_intervalo_configurable_por_entorno(entorno, monkeypatch):
    monkeypatch.setenv("KENI_PROGRAMADOR_INTERVALO_SEGUNDOS", "5")
    assert programador._intervalo_segundos() == 5.0
