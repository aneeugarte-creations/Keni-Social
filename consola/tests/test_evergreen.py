"""Tests del TALLER EVERGREEN / brainstorming: parseo de ideas (PURO) + CRUD de `evergreen_ideas`.

Dos bloques:
  - `parsear_ideas`: dominio PURO (sin BD). Cubre el JSON cercado, el dict envoltorio, el
    saneo (título obligatorio, recortes), la deduplicación y el tope `MAX_IDEAS`.
  - CRUD de `evergreen_ideas` en `db.py` (requiere el Postgres de pruebas, fixture `entorno`; se
    salta si no hay).
"""

from __future__ import annotations

from keni_consola import db
from keni_consola.dominio import evergreen

# --------------------------------------------------------------------------- #
# parsear_ideas — dominio PURO (sin BD)                                        #
# --------------------------------------------------------------------------- #


def test_parsear_ideas_bloque_json_cercado():
    salida = (
        "Aquí tienes algunas ideas:\n\n"
        '```json\n{"ideas": [{"titulo": "Efeméride futbolera", "descripcion": "qué pasó hoy"},'
        ' {"titulo": "Sabías que", "descripcion": ""}]}\n```\n'
    )
    ideas = evergreen.parsear_ideas(salida)
    assert len(ideas) == 2
    assert ideas[0] == {"titulo": "Efeméride futbolera", "descripcion": "qué pasó hoy"}
    assert ideas[1] == {"titulo": "Sabías que", "descripcion": ""}


def test_parsear_ideas_lista_cruda_sin_fence():
    salida = '[{"titulo": "Idea A"}, {"titulo": "Idea B", "descripcion": "x"}]'
    ideas = evergreen.parsear_ideas(salida)
    assert [i["titulo"] for i in ideas] == ["Idea A", "Idea B"]
    # `descripcion` ausente -> "" (no rompe).
    assert ideas[0]["descripcion"] == ""


def test_parsear_ideas_omite_sin_titulo_y_no_dict():
    salida = '{"ideas": [{"descripcion": "sin título"}, "no soy un dict", {"titulo": "  "}]}'
    assert evergreen.parsear_ideas(salida) == []


def test_parsear_ideas_deduplica_por_titulo_case_insensitive():
    salida = '{"ideas": [{"titulo": "Repetida"}, {"titulo": "repetida"}, {"titulo": "Otra"}]}'
    ideas = evergreen.parsear_ideas(salida)
    assert [i["titulo"] for i in ideas] == ["Repetida", "Otra"]


def test_parsear_ideas_tope_max():
    crudas = ", ".join(f'{{"titulo": "Idea {n}"}}' for n in range(evergreen.MAX_IDEAS + 5))
    ideas = evergreen.parsear_ideas('{"ideas": [' + crudas + "]}")
    assert len(ideas) == evergreen.MAX_IDEAS


def test_parsear_ideas_sin_json_devuelve_vacio():
    assert evergreen.parsear_ideas("no hay json aquí") == []
    assert evergreen.parsear_ideas("") == []


# --------------------------------------------------------------------------- #
# CRUD de evergreen_ideas — requiere Postgres de pruebas (fixture `entorno`)       #
# --------------------------------------------------------------------------- #


def test_crear_listar_obtener_evergreen_idea(entorno):
    idea = db.crear_evergreen_idea(
        marca="unotv", titulo="Explicador VAR", descripcion="cómo funciona el VAR",
    )
    assert set(idea) == {
        "id", "marca", "titulo", "descripcion", "estado", "origen",
        "generacion_id", "contenido_id", "creado", "actualizado",
    }
    assert idea["estado"] == "propuesta"
    assert idea["origen"] == "ia"
    assert db.obtener_evergreen_idea(idea["id"])["titulo"] == "Explicador VAR"
    assert any(x["id"] == idea["id"] for x in db.listar_evergreen_ideas())


def test_listar_evergreen_ideas_filtra_marca_y_estado(entorno):
    a = db.crear_evergreen_idea(marca="unotv", titulo="A", estado="propuesta")
    b = db.crear_evergreen_idea(marca="unotv", titulo="B", estado="aprobada")
    db.crear_evergreen_idea(marca="claro", titulo="C", estado="propuesta")

    solo_unotv = {x["id"] for x in db.listar_evergreen_ideas(marca="unotv")}
    assert solo_unotv == {a["id"], b["id"]}

    aprobadas = [x["id"] for x in db.listar_evergreen_ideas(estado="aprobada")]
    assert aprobadas == [b["id"]]


def test_listar_evergreen_ideas_recientes_primero(entorno):
    a = db.crear_evergreen_idea(marca="unotv", titulo="A")
    b = db.crear_evergreen_idea(marca="unotv", titulo="B")
    ids = [x["id"] for x in db.listar_evergreen_ideas()]
    assert ids.index(b["id"]) < ids.index(a["id"])


def test_actualizar_evergreen_idea(entorno):
    idea = db.crear_evergreen_idea(marca="unotv", titulo="X", estado="propuesta")
    edit = db.actualizar_evergreen_idea(
        idea["id"], {"estado": "aprobada", "contenido_id": "pieza123"}
    )
    assert edit["estado"] == "aprobada"
    assert edit["contenido_id"] == "pieza123"
    # Campo NO editable (marca/origen) se ignora, no rompe.
    sin_cambio = db.actualizar_evergreen_idea(idea["id"], {"marca": "claro", "origen": "manual"})
    assert sin_cambio["marca"] == "unotv"
    assert sin_cambio["origen"] == "ia"
    assert db.actualizar_evergreen_idea("noexiste", {"estado": "aprobada"}) is None


def test_borrar_evergreen_idea(entorno):
    idea = db.crear_evergreen_idea(marca="unotv", titulo="Borrame")
    assert db.borrar_evergreen_idea(idea["id"]) is True
    assert db.obtener_evergreen_idea(idea["id"]) is None
    assert db.borrar_evergreen_idea(idea["id"]) is False
