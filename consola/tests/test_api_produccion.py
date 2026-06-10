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
    """`por_categoria` (monitor de líneas): producido vs objetivo por categoría del plan."""
    monkeypatch.setenv("KENI_PLAN_DIA::unotv", "mx:4,breaking:2")
    cli = _cli()
    pieza = _crear(cli, titulo="Nacional promovida")
    plat = repos.obtener_contenido_plataforma(pieza["id"])
    repos.upsert_noticia_cluster({
        "id": "cl-prod", "titulo": "Nacional promovida", "resumen": "", "marca": "unotv",
        "categoria": "mx", "geo": "MX", "clave": "t:cl-prod", "n_items": 1, "n_fuentes": 2,
        "idiomas": ["es"], "senal": 0, "score": 0.7, "breaking": 0,
        "primer_visto": "2026-06-01T00:00:00", "ultimo_visto": "2026-06-01T00:00:00",
        "estado": "usado", "verificacion": "corroborada",
    })
    repos.actualizar_noticia_cluster("cl-prod", contenido_id=plat["contenido_id"])

    data = _cli().get("/api/produccion/dia?marca=unotv").json()

    lineas = {l["categoria"]: l for l in data["por_categoria"]}
    assert lineas["mx"]["producido"] == 1 and lineas["mx"]["objetivo"] == 4
    assert lineas["breaking"]["producido"] == 0 and lineas["breaking"]["objetivo"] == 2


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
