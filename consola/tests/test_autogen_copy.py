"""Tests de la SELECCION pura de la auto-generacion de copy (sin DB ni red).

`topics_pendientes` decide que temas del tablero se auto-generan. Es la logica de riesgo
(filtros + dedup + cap); se prueba en aislamiento con dicts en memoria.
"""

from __future__ import annotations

from keni_consola import autogen_copy as ag


def _item(**kw):
    base = {
        "id": "c1",
        "clase": "contenido",
        "origen": "import-calendario",
        "estado": "pendiente",
        "marca": "claro-sports",
        "titulo": "Un tema",
        "descripcion": "",
    }
    base.update(kw)
    return base


def test_selecciona_tema_de_fuente_con_marca():
    elegidos = ag.topics_pendientes([_item()], ya_generados=set(), maximo=3)
    assert [e["id"] for e in elegidos] == ["c1"]


def test_omite_origen_manual():
    elegidos = ag.topics_pendientes([_item(origen="")], ya_generados=set(), maximo=3)
    assert elegidos == []


def test_omite_clase_tarea():
    elegidos = ag.topics_pendientes([_item(clase="tarea")], ya_generados=set(), maximo=3)
    assert elegidos == []


def test_omite_estado_cerrado():
    elegidos = ag.topics_pendientes([_item(estado="hecha")], ya_generados=set(), maximo=3)
    assert elegidos == []


def test_omite_sin_marca_o_marca_invalida():
    items = [_item(id="a", marca=""), _item(id="b", marca="marca-inventada")]
    assert ag.topics_pendientes(items, ya_generados=set(), maximo=3) == []


def test_omite_titulo_vacio():
    elegidos = ag.topics_pendientes([_item(titulo="   ")], ya_generados=set(), maximo=3)
    assert elegidos == []


def test_dedup_por_id_ya_generado():
    elegidos = ag.topics_pendientes([_item(id="c1")], ya_generados={"c1"}, maximo=3)
    assert elegidos == []


def test_respeta_cap_maximo_y_orden():
    items = [_item(id=f"c{i}") for i in range(5)]
    elegidos = ag.topics_pendientes(items, ya_generados=set(), maximo=2)
    assert [e["id"] for e in elegidos] == ["c0", "c1"]


def test_acepta_todas_las_fuentes_conocidas():
    items = [
        _item(id="imp", origen="import-calendario"),
        _item(id="rad", origen="radar-auto"),
        _item(id="rdr", origen="radar"),
        _item(id="rss", origen="rss"),
    ]
    elegidos = ag.topics_pendientes(items, ya_generados=set(), maximo=10)
    assert {e["id"] for e in elegidos} == {"imp", "rad", "rdr", "rss"}


def test_nota_combina_titulo_y_descripcion():
    nota = ag._nota_de(_item(titulo="Título", descripcion="Por qué importa"))
    assert nota == "Título\n\nPor qué importa"


def test_nota_solo_titulo_si_no_hay_descripcion():
    assert ag._nota_de(_item(titulo="Solo título", descripcion="")) == "Solo título"
