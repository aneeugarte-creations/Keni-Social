"""Producción del día (`GET /api/produccion/dia`): embudo de 24 h + colas. OFFLINE, DB tmp.

Cubre la forma del contrato, la clasificación del embudo por la pieza MÁS AVANZADA del
tema, el filtro por marca y la validación de marca. Las piezas se crean por el API (como
en producción) y se mueven de estado por repos.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth, repos

from .conftest import TOKEN_PRUEBA

_ORIGIN = {"Origin": "http://testserver"}
_CLAVE = "clave-de-prueba-123"


def _cli() -> TestClient:
    auth.crear_usuario("ana", _CLAVE, "editor")
    c = TestClient(app_modulo.crear_app(token=TOKEN_PRUEBA))
    r = c.post("/api/auth/login", json={"usuario": "ana", "password": _CLAVE}, headers=_ORIGIN)
    assert r.status_code == 200
    return c


def _crear(cli: TestClient, **campos) -> dict:
    base = {"marca": "unotv", "red": "x", "titulo": "T", "contenido": "C"}
    base.update(campos)
    r = cli.post("/api/publicaciones", json=base, headers=_ORIGIN)
    assert r.status_code == 200, r.text
    return r.json()["publicacion"]


def test_produccion_dia_contrato_y_embudo(entorno):
    """El embudo cuenta TEMAS por su pieza más avanzada; el contrato trae las 4 vistas."""
    cli = _cli()
    _crear(cli, titulo="Borrador con copy")  # copy sin avanzar -> en_borrador
    prog = _crear(cli, titulo="Programada")
    repos.actualizar_publicacion(prog["id"], {"fecha_programada": "2030-01-01T10:00"})
    repos.transicionar_estado_publicacion(prog["id"], "borrador", "programado", {})

    r = cli.get("/api/produccion/dia?marca=unotv")
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["marca"] == "unotv"
    assert data["ventana"]["desde"] < data["ventana"]["hasta"]
    emb = data["embudo"]
    assert emb["total"] == 2
    assert emb["en_borrador"] == 1
    assert emb["programado"] == 1
    # Las 4 vistas del contrato presentes.
    assert {"dia", "plan"} <= set(data["objetivo"])
    assert {"pendientes", "en_curso"} <= set(data["cola_generacion"])
    assert [p["id"] for p in data["programacion"]["programadas"]] == [prog["id"]]
    assert data["programacion"]["programadas"][0]["fecha_programada"] == "2030-01-01T10:00"
    # Detalle por tema, más recientes primero, con su estado del embudo.
    assert len(data["piezas"]) == 2
    assert {p["estado"] for p in data["piezas"]} == {"en_borrador", "programado"}
    # Sin etiquetas de vertical asignadas, caen al cajón "(sin vertical)".
    assert data["por_vertical"][0]["vertical"] == "(sin vertical)"
    assert data["por_vertical"][0]["total"] == 2


def test_produccion_dia_lineas_del_plan(entorno, monkeypatch):
    """`por_categoria` (monitor de líneas): GENERADOS y PUBLICADOS vs objetivo por categoría.

    El conteo lee `contenido.categoria` (persistida al promover/usar/reciclar): estable
    aunque el GC del pool borre el cluster de origen.
    """
    monkeypatch.setenv("KENI_PLAN_DIA::unotv", "mx:4,breaking:2")
    cli = _cli()
    # Dos generados de mx; uno llega a PUBLICADO.
    repos.crear_contenido(clase="contenido", titulo="Nacional 1", marca="unotv", categoria="mx")
    publicado = repos.crear_contenido(
        clase="contenido", titulo="Nacional 2", marca="unotv", categoria="mx"
    )
    repos.crear_contenido_plataforma(
        contenido_id=publicado["id"], red="x", copy="C", estado="publicado"
    )
    # Una manual sin categoría: fuera del plan (no cuenta en ninguna línea).
    _crear(cli, titulo="Manual sin línea")

    data = _cli().get("/api/produccion/dia?marca=unotv").json()

    lineas = {l["categoria"]: l for l in data["por_categoria"]}
    assert lineas["mx"]["generados"] == 2 and lineas["mx"]["publicados"] == 1
    assert lineas["mx"]["objetivo"] == 4
    assert lineas["breaking"]["generados"] == 0 and lineas["breaking"]["objetivo"] == 2


def test_produccion_dia_filtra_por_marca(entorno):
    cli = _cli()
    _crear(cli, marca="unotv", titulo="De UnoTV")
    _crear(cli, marca="claro-sports", titulo="De Claro")

    r = cli.get("/api/produccion/dia?marca=claro-sports")
    assert r.status_code == 200
    assert r.json()["embudo"]["total"] == 1
    # Sin marca: todas.
    r = cli.get("/api/produccion/dia")
    assert r.status_code == 200
    assert r.json()["embudo"]["total"] == 2


def test_produccion_dia_marca_invalida_400(entorno):
    cli = _cli()
    assert cli.get("/api/produccion/dia?marca=no-existe").status_code == 400
