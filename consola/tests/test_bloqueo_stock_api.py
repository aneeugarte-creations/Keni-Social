"""El bloqueo de stock sin licencia cubre TODOS los caminos a publicar (API). OFFLINE, DB en tmp.

Una pieza con foto de stock sin autorizar (`imagen_origen='stock'`, `imagen_autorizada=0`) no
puede pasar a `programado`/`publicado` ni por el PUT de pieza ni por el PATCH de plataforma (el
camino del MCP tablero). Al autorizarla, el mismo PATCH ya pasa.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import repos

from .conftest import TOKEN_PRUEBA

_ORIGIN = {"Origin": "http://testserver"}


def _cli() -> TestClient:
    app = app_modulo.crear_app(token=TOKEN_PRUEBA)
    return TestClient(app, headers={"Authorization": f"Bearer {TOKEN_PRUEBA}"})


def _crear_borrador(cli: TestClient) -> dict:
    r = cli.post(
        "/api/piezas",
        json={"marca": "unotv", "red": "x", "titulo": "T", "contenido": "C"},
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    return r.json()["pieza"]


def _marcar_stock(pieza_id: str, *, autorizada: bool = False) -> None:
    repos.actualizar_pieza_fila(
        pieza_id,
        {
            "foto": "stock123.jpg",
            "imagen": "",
            "falta_imagen": not autorizada,
            "imagen_origen": "stock",
            "imagen_proveedor": "pexels",
            "imagen_autorizada": autorizada,
        },
    )


def test_put_pieza_a_programado_se_bloquea_si_stock_sin_autorizar(entorno):
    cli = _cli()
    pieza = _crear_borrador(cli)
    _marcar_stock(pieza["id"], autorizada=False)
    r = cli.put(
        f"/api/piezas/{pieza['id']}",
        json={"estado": "programado"},
        headers=_ORIGIN,
    )
    assert r.status_code == 409, r.text
    assert "SIN LICENCIA" in r.json().get("error", "")


def test_patch_plataforma_a_programado_se_bloquea_si_stock_sin_autorizar(entorno):
    cli = _cli()
    pieza = _crear_borrador(cli)
    _marcar_stock(pieza["id"], autorizada=False)
    r = cli.patch(
        f"/api/publicaciones/{pieza['publicacion_id']}/plataformas/{pieza['id']}",
        json={"estado": "programado"},
        headers=_ORIGIN,
    )
    assert r.status_code == 409, r.text
    assert "SIN LICENCIA" in r.json().get("error", "")


def test_patch_plataforma_a_programado_pasa_tras_autorizar(entorno):
    cli = _cli()
    pieza = _crear_borrador(cli)
    _marcar_stock(pieza["id"], autorizada=True)
    r = cli.patch(
        f"/api/publicaciones/{pieza['publicacion_id']}/plataformas/{pieza['id']}",
        json={"estado": "programado", "fecha_programada": "2030-01-01T10:00"},
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    assert r.json()["plataforma"]["estado"] == "programado"


def test_elegir_foto_propia_limpia_el_stock_heredado(entorno):
    """Poner una foto PROPIA (galería/subida) por el PATCH limpia el SIN LICENCIA de la stock anterior."""
    cli = _cli()
    pieza = _crear_borrador(cli)
    _marcar_stock(pieza["id"], autorizada=False)  # tenía una stock sin autorizar
    # El usuario elige una foto de la galería (key propia distinta) por el PATCH de plataforma.
    r = cli.patch(
        f"/api/publicaciones/{pieza['publicacion_id']}/plataformas/{pieza['id']}",
        json={"foto": "originales/propia.jpg"},
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    fila = repos.obtener_pieza_fila(pieza["id"])
    assert fila["foto"] == "originales/propia.jpg"
    # El metadato de stock heredado queda limpio => ya no es SIN LICENCIA.
    assert fila["imagen_origen"] == ""
    assert fila["imagen_proveedor"] == ""
    assert fila["imagen_autorizada"] in (False, 0)
    # Y ahora SÍ puede programarse (sin el bloqueo de stock).
    r2 = cli.patch(
        f"/api/publicaciones/{pieza['publicacion_id']}/plataformas/{pieza['id']}",
        json={"estado": "programado", "fecha_programada": "2030-01-01T10:00"},
        headers=_ORIGIN,
    )
    assert r2.status_code == 200, r2.text


def test_reenviar_la_misma_foto_no_altera_la_licencia(entorno):
    """Reenviar la MISMA foto (sin cambiarla) NO toca el metadato de stock (no pisa el badge)."""
    cli = _cli()
    pieza = _crear_borrador(cli)
    _marcar_stock(pieza["id"], autorizada=False)
    r = cli.patch(
        f"/api/publicaciones/{pieza['publicacion_id']}/plataformas/{pieza['id']}",
        json={"foto": "stock123.jpg", "copy": "edito el copy"},
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    fila = repos.obtener_pieza_fila(pieza["id"])
    assert fila["imagen_origen"] == "stock"  # intacto: la foto no cambió
