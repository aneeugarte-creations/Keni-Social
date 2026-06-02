"""Tests de la auto-generacion de ARTE (sin DB ni red).

`topics_sin_arte` decide que temas del tablero se auto-ilustran. Es la logica de riesgo
(filtros + dedup + cap); se prueba en aislamiento con dicts en memoria. `prompt_arte` y
`lanzar_para_topic` se cubren con el generador de imagen y los repos PARCHEADOS, asi que
ningun test toca la red ni la base de datos.
"""

from __future__ import annotations

from keni_consola import autogen_arte as aa


def _item(**kw):
    base = {
        "id": "c1",
        "clase": "contenido",
        "estado": "pendiente",
        "marca": "claro-sports",
        "titulo": "Un tema",
        "descripcion": "",
    }
    base.update(kw)
    return base


def _plat(**kw):
    base = {"id": "p1", "copy": "Texto listo", "imagen": ""}
    base.update(kw)
    return base


# --------------------------------------------------------------------------- #
# Seleccion pura: topics_sin_arte                                              #
# --------------------------------------------------------------------------- #


def test_selecciona_tema_con_copy_sin_imagen():
    elegidos = aa.topics_sin_arte(
        [_item()],
        plataformas_por_item={"c1": [_plat()]},
        ya_procesados=set(),
        maximo=3,
    )
    assert [e["id"] for e in elegidos] == ["c1"]


def test_omite_si_no_hay_copy():
    elegidos = aa.topics_sin_arte(
        [_item()],
        plataformas_por_item={"c1": [_plat(copy="")]},
        ya_procesados=set(),
        maximo=3,
    )
    assert elegidos == []


def test_omite_si_ya_tiene_imagen():
    elegidos = aa.topics_sin_arte(
        [_item()],
        plataformas_por_item={"c1": [_plat(imagen="foto.png")]},
        ya_procesados=set(),
        maximo=3,
    )
    assert elegidos == []


def test_omite_si_no_tiene_plataformas():
    elegidos = aa.topics_sin_arte(
        [_item()],
        plataformas_por_item={},
        ya_procesados=set(),
        maximo=3,
    )
    assert elegidos == []


def test_omite_clase_tarea():
    elegidos = aa.topics_sin_arte(
        [_item(clase="tarea")],
        plataformas_por_item={"c1": [_plat()]},
        ya_procesados=set(),
        maximo=3,
    )
    assert elegidos == []


def test_omite_estado_cerrado():
    elegidos = aa.topics_sin_arte(
        [_item(estado="hecha")],
        plataformas_por_item={"c1": [_plat()]},
        ya_procesados=set(),
        maximo=3,
    )
    assert elegidos == []


def test_omite_titulo_vacio():
    elegidos = aa.topics_sin_arte(
        [_item(titulo="   ")],
        plataformas_por_item={"c1": [_plat()]},
        ya_procesados=set(),
        maximo=3,
    )
    assert elegidos == []


def test_dedup_por_id_ya_procesado():
    elegidos = aa.topics_sin_arte(
        [_item(id="c1")],
        plataformas_por_item={"c1": [_plat()]},
        ya_procesados={"c1"},
        maximo=3,
    )
    assert elegidos == []


def test_acepta_si_alguna_plataforma_cumple():
    # Una plataforma ya ilustrada y otra con copy sin imagen: el tema entra.
    elegidos = aa.topics_sin_arte(
        [_item()],
        plataformas_por_item={
            "c1": [_plat(id="p1", imagen="ya.png"), _plat(id="p2", copy="Otro", imagen="")]
        },
        ya_procesados=set(),
        maximo=3,
    )
    assert [e["id"] for e in elegidos] == ["c1"]


def test_respeta_cap_maximo_y_orden():
    items = [_item(id=f"c{i}") for i in range(5)]
    plats = {f"c{i}": [_plat(id=f"p{i}")] for i in range(5)}
    elegidos = aa.topics_sin_arte(
        items, plataformas_por_item=plats, ya_procesados=set(), maximo=2
    )
    assert [e["id"] for e in elegidos] == ["c0", "c1"]


def test_score_ordena_que_se_ilustra_primero_antes_del_cap():
    """Flujo C: el SCORE ordena el arte (que se ilustra PRIMERO). Con cap=1 entra el de mayor
    score (compromiso), no el primero en orden de entrada."""
    from datetime import date

    items = [_item(id="normal", prioridad="baja"), _item(id="must", prioridad="baja")]
    plats = {"normal": [_plat(id="pn")], "must": [_plat(id="pm")]}
    elegidos = aa.topics_sin_arte(
        items,
        plataformas_por_item=plats,
        ya_procesados=set(),
        maximo=1,
        etiquetas_por_item={"must": ["compromiso"]},
        hoy=date(2026, 6, 1),
    )
    assert [e["id"] for e in elegidos] == ["must"]


def test_orden_por_defecto_conserva_entrada():
    """Sin `etiquetas_por_item`/`hoy`, conserva el orden del tablero."""
    items = [_item(id="a"), _item(id="b")]
    plats = {"a": [_plat(id="pa")], "b": [_plat(id="pb")]}
    elegidos = aa.topics_sin_arte(
        items, plataformas_por_item=plats, ya_procesados=set(), maximo=3
    )
    assert [e["id"] for e in elegidos] == ["a", "b"]


# --------------------------------------------------------------------------- #
# prompt_arte                                                                  #
# --------------------------------------------------------------------------- #


def test_prompt_incluye_titulo_y_descripcion():
    prompt = aa.prompt_arte(_item(titulo="Final de copa", descripcion="Juega Mexico"))
    assert "Final de copa" in prompt
    assert "Juega Mexico" in prompt
    assert "sin texto incrustado" in prompt.lower()


def test_prompt_vacio_si_no_hay_titulo():
    assert aa.prompt_arte(_item(titulo="", descripcion="")) == ""


# --------------------------------------------------------------------------- #
# lanzar_para_topic: generador y repos PARCHEADOS (sin red ni DB)             #
# --------------------------------------------------------------------------- #


def test_lanzar_para_topic_adjunta_imagen(monkeypatch):
    monkeypatch.setattr(aa.media, "proveedor_configurado", lambda: True)
    monkeypatch.setattr(
        aa.repos, "listar_contenido_plataforma", lambda cid: [_plat(id="p1")]
    )
    monkeypatch.setattr(aa.media, "guardar_bytes", lambda datos, ext="png": "arte.png")
    cambios = {}

    def _actualizar(pid, campos):
        cambios["pid"] = pid
        cambios["campos"] = campos
        return {"id": pid, **campos}

    monkeypatch.setattr(aa.repos, "actualizar_contenido_plataforma", _actualizar)
    monkeypatch.setattr(aa.repos, "listar_etiquetas", lambda: [])
    monkeypatch.setattr(
        aa.repos, "crear_etiqueta", lambda *, nombre: {"id": "et1", "nombre": nombre}
    )
    asignadas = []
    monkeypatch.setattr(
        aa.repos, "asignar_etiqueta", lambda cid, eid: asignadas.append((cid, eid))
    )

    res = aa.lanzar_para_topic(_item(), generar=lambda prompt: b"PNGBYTES")

    assert res == {"contenido_id": "c1", "plataforma_id": "p1", "imagen": "arte.png"}
    assert cambios["pid"] == "p1"
    assert cambios["campos"] == {"imagen": "arte.png", "falta_imagen": False}
    assert asignadas == [("c1", "et1")]


def test_lanzar_para_topic_sin_proveedor_no_genera(monkeypatch):
    monkeypatch.setattr(aa.media, "proveedor_configurado", lambda: False)
    llamado = []
    res = aa.lanzar_para_topic(
        _item(), generar=lambda prompt: llamado.append(prompt) or b"x"
    )
    assert res is None
    assert llamado == []


def test_lanzar_para_topic_sin_plataforma_candidata(monkeypatch):
    monkeypatch.setattr(aa.media, "proveedor_configurado", lambda: True)
    monkeypatch.setattr(
        aa.repos,
        "listar_contenido_plataforma",
        lambda cid: [_plat(imagen="ya.png")],
    )
    res = aa.lanzar_para_topic(_item(), generar=lambda prompt: b"x")
    assert res is None
