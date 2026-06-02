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


def test_acepta_alta_creativa_del_equipo():
    """`origen='equipo'` AUTO-GENERA SIEMPRE (Fase 1 / Flujo A): el alta creativa del equipo
    entra al pipeline igual que una fuente externa. Es la INVERSION del plan §2 (antes el alta
    manual quedaba fuera). Distinto del alta tecleada legada (`origen=''`), que sigue excluida.
    """
    elegidos = ag.topics_pendientes(
        [_item(id="eq", origen="equipo")], ya_generados=set(), maximo=3
    )
    assert [e["id"] for e in elegidos] == ["eq"]


def test_origenes_topic_deriva_del_modulo_neutro():
    """`ORIGENES_TOPIC` es la fuente UNICA `estados.ORIGENES_AUTOGEN` e incluye `equipo`,
    pero NUNCA el alta tecleada legada (`origen=''`)."""
    from keni_consola import estados

    assert ag.ORIGENES_TOPIC == frozenset(estados.ORIGENES_AUTOGEN)
    assert estados.ORIGEN_EQUIPO in ag.ORIGENES_TOPIC
    assert "" not in ag.ORIGENES_TOPIC


def test_orden_por_defecto_conserva_entrada():
    """Sin `etiquetas_por_item`/`hoy`, conserva el orden del tablero (prioridad+fecha)."""
    items = [_item(id="a"), _item(id="b"), _item(id="c")]
    elegidos = ag.topics_pendientes(items, ya_generados=set(), maximo=3)
    assert [e["id"] for e in elegidos] == ["a", "b", "c"]


def test_score_ordena_la_cola_de_trabajo_antes_del_cap():
    """Flujo C: el SCORE ordena que se auto-genera PRIMERO. Con cap=1 entra el de mayor score
    (compromiso), aunque NO sea el primero en orden de entrada."""
    from datetime import date

    items = [
        _item(id="normal", prioridad="baja"),
        _item(id="must", prioridad="baja"),
    ]
    etiquetas = {"must": ["compromiso"]}  # compromiso DOMINA el score
    elegidos = ag.topics_pendientes(
        items, ya_generados=set(), maximo=1, etiquetas_por_item=etiquetas, hoy=date(2026, 6, 1)
    )
    assert [e["id"] for e in elegidos] == ["must"]


def test_score_no_consume_a_E_solo_ordena():
    """El wrapper solo CONSUME `ordenar_por_score`; no toca la firma de `score_contenido`
    (compatible con que el Flujo E la enriquezca). Sin etiquetas relevantes, el orden lo dicta
    la prioridad base, no se rompe la seleccion."""
    from datetime import date

    items = [_item(id="baja", prioridad="baja"), _item(id="alta", prioridad="alta")]
    elegidos = ag.topics_pendientes(
        items, ya_generados=set(), maximo=2, etiquetas_por_item={}, hoy=date(2026, 6, 1)
    )
    assert [e["id"] for e in elegidos] == ["alta", "baja"]


def test_nota_combina_titulo_y_descripcion():
    nota = ag._nota_de(_item(titulo="Título", descripcion="Por qué importa"))
    assert nota == "Título\n\nPor qué importa"


def test_nota_solo_titulo_si_no_hay_descripcion():
    assert ag._nota_de(_item(titulo="Solo título", descripcion="")) == "Solo título"


def test_lanzar_para_topic_pasa_contenido_id_del_tema(monkeypatch):
    """PURO (sin DB): el daemon pasa el `contenido_id` del tema para NIDAR el borrador.

    Aisla `lanzar_para_topic` mockeando todo lo que toca DB/red/`claude`: solo verifica que
    el `contenido_id` que viaja al lanzador NEUTRO (`dominio.generar.lanzar_copy`) es el id
    del propio tema (lista viva: el borrador cuelga del tema, no es contenido suelto).
    """
    capturado: dict = {}

    def fake_lanzar(**kw):
        capturado.update(kw)
        return {"id": "gen-1"}

    monkeypatch.setattr(ag.dom_generar, "lanzar_copy", fake_lanzar)
    monkeypatch.setattr(ag, "_redes_de", lambda item: ["x"])
    monkeypatch.setattr(ag, "_id_etiqueta_autogen", lambda **k: "")  # sin etiqueta: best-effort

    gen = ag.lanzar_para_topic(_item(id="tema-42"))
    assert gen == {"id": "gen-1"}
    assert capturado["contenido_id"] == "tema-42"
    assert capturado["marca"] == "claro-sports"
    assert capturado["redes_ids"] == ["x"]
