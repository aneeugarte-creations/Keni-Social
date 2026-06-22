"""Tests del TALLER EVERGREEN / brainstorming: parseo de ideas (PURO) + CRUD de `evergreen_ideas`.

Dos bloques:
  - `parsear_ideas`: dominio PURO (sin BD). Cubre el JSON cercado, el dict envoltorio, el
    reparación (título obligatorio, recortes), la deduplicación y el tope `MAX_IDEAS`.
  - CRUD de `evergreen_ideas` en `db.py` (requiere el Postgres de pruebas, fixture `entorno`; se
    salta si no hay).
"""

from __future__ import annotations

from keni_consola import db
from keni_consola.dominio import idear

# --------------------------------------------------------------------------- #
# parsear_ideas — dominio PURO (sin BD)                                        #
# --------------------------------------------------------------------------- #


def test_parsear_ideas_bloque_json_cercado():
    salida = (
        "Aquí tienes algunas ideas:\n\n"
        '```json\n{"ideas": [{"titulo": "Efeméride futbolera", "descripcion": "qué pasó hoy"},'
        ' {"titulo": "Sabías que", "descripcion": ""}]}\n```\n'
    )
    ideas = idear.parsear_ideas(salida)
    assert len(ideas) == 2
    assert ideas[0] == {"titulo": "Efeméride futbolera", "descripcion": "qué pasó hoy"}
    assert ideas[1] == {"titulo": "Sabías que", "descripcion": ""}


def test_parsear_ideas_lista_cruda_sin_fence():
    salida = '[{"titulo": "Idea A"}, {"titulo": "Idea B", "descripcion": "x"}]'
    ideas = idear.parsear_ideas(salida)
    assert [i["titulo"] for i in ideas] == ["Idea A", "Idea B"]
    # `descripcion` ausente -> "" (no rompe).
    assert ideas[0]["descripcion"] == ""


def test_parsear_ideas_omite_sin_titulo_y_no_dict():
    salida = '{"ideas": [{"descripcion": "sin título"}, "no soy un dict", {"titulo": "  "}]}'
    assert idear.parsear_ideas(salida) == []


def test_parsear_ideas_deduplica_por_titulo_case_insensitive():
    salida = '{"ideas": [{"titulo": "Repetida"}, {"titulo": "repetida"}, {"titulo": "Otra"}]}'
    ideas = idear.parsear_ideas(salida)
    assert [i["titulo"] for i in ideas] == ["Repetida", "Otra"]


def test_parsear_ideas_tope_max():
    crudas = ", ".join(f'{{"titulo": "Idea {n}"}}' for n in range(idear.MAX_IDEAS + 5))
    ideas = idear.parsear_ideas('{"ideas": [' + crudas + "]}")
    assert len(ideas) == idear.MAX_IDEAS


def test_parsear_ideas_sin_json_devuelve_vacio():
    assert idear.parsear_ideas("no hay json aquí") == []
    assert idear.parsear_ideas("") == []


# --------------------------------------------------------------------------- #
# CRUD de evergreen_ideas — requiere Postgres de pruebas (fixture `entorno`)       #
# --------------------------------------------------------------------------- #


def test_crear_listar_obtener_evergreen_idea(entorno):
    idea = db.crear_evergreen_idea(
        marca="unotv", titulo="Explicador VAR", descripcion="cómo funciona el VAR",
    )
    assert set(idea) == {
        "id", "marca", "titulo", "descripcion", "estado", "origen",
        "generacion_id", "publicacion_id", "creado", "actualizado",
    }
    assert idea["estado"] == "propuesta"
    assert idea["origen"] == "ia"
    assert db.obtener_evergreen_idea(idea["id"])["titulo"] == "Explicador VAR"
    assert any(x["id"] == idea["id"] for x in db.listar_evergreen_ideas())


def test_crear_evergreen_idea_origen_aportacion(entorno):
    # Las aportaciones "Idea del equipo" e "Interno AMX" viven en el MISMO banco que la IA,
    # distinguidas por `origen` ('idea'/'interna'). Una aportación interna lleva su nota larga
    # en `descripcion` y nace en 'propuesta', igual que el resto.
    idea = db.crear_evergreen_idea(
        marca="unotv",
        titulo="Brief de programa",
        descripcion="material interno pegado por el equipo",
        origen="interna",
    )
    assert idea["origen"] == "interna"
    assert idea["estado"] == "propuesta"
    leida = db.obtener_evergreen_idea(idea["id"])
    assert leida["origen"] == "interna"
    assert leida["descripcion"] == "material interno pegado por el equipo"


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
        idea["id"], {"estado": "aprobada", "publicacion_id": "pieza123"}
    )
    assert edit["estado"] == "aprobada"
    assert edit["publicacion_id"] == "pieza123"
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


# --------------------------------------------------------------------------- #
# Generar pieza desde una idea: terminal feliz `generada`                      #
# --------------------------------------------------------------------------- #


def test_generar_pieza_sella_la_idea_como_generada(cliente, monkeypatch):
    """POST /generar crea la pieza y deja la idea en `generada` + enlazada: sale del flujo
    activo del taller (sin botones de Generar/Descartar; cajón histórico)."""
    from keni_consola import repos
    from keni_consola.api import idear as api_evergreen

    monkeypatch.setattr(
        api_evergreen.gen_dom, "lanzar_copy", lambda **kw: {"id": "gen-stub"}
    )
    idea = repos.crear_evergreen_idea(
        marca="unotv", titulo="Explicador RFC", descripcion="guía", estado="aprobada"
    )
    r = cliente.post(f"/api/evergreen/ideas/{idea['id']}/generar", json={})
    assert r.status_code == 200, r.text
    datos = r.json()
    assert datos["idea"]["estado"] == "generada"
    assert datos["idea"]["publicacion_id"]
    # La pieza nace evergreen con su LÍNEA del plan persistida (cuenta y hereda horarios).
    cont = repos.obtener_publicacion(datos["idea"]["publicacion_id"])
    assert cont["flujo"] == "evergreen" and cont["categoria"] == "evergreen"
    # Una idea ya generada NO se puede volver a generar (no está `aprobada`).
    assert cliente.post(
        f"/api/evergreen/ideas/{idea['id']}/generar", json={}
    ).status_code == 400


def test_generar_pieza_borra_pieza_si_lanzar_revienta(cliente, monkeypatch):
    """Si `lanzar_copy` revienta, la pieza NO queda huérfana y la idea sigue aprobada."""
    from keni_consola import repos
    from keni_consola.api import idear as api_evergreen

    creadas: list[str] = []
    orig_crear = repos.crear_publicacion

    def crear_spy(**kw):
        pieza = orig_crear(**kw)
        creadas.append(pieza["id"])
        return pieza

    monkeypatch.setattr(api_evergreen.repos, "crear_publicacion", crear_spy)

    def explota(**kw):
        raise RuntimeError("boom al lanzar")

    monkeypatch.setattr(api_evergreen.gen_dom, "lanzar_copy", explota)

    idea = repos.crear_evergreen_idea(
        marca="unotv", titulo="X", descripcion="y", estado="aprobada"
    )
    r = cliente.post(f"/api/evergreen/ideas/{idea['id']}/generar", json={})
    assert r.status_code == 500, r.text
    # La idea sigue aprobada y sin enlazar: se puede reintentar.
    idea2 = repos.obtener_evergreen_idea(idea["id"])
    assert idea2["estado"] == "aprobada"
    assert not idea2.get("publicacion_id")
    # La pieza creada NO quedó huérfana.
    assert creadas and repos.obtener_publicacion(creadas[0]) is None


def test_generar_pieza_no_sella_si_lanzamiento_reflejo_error(cliente, monkeypatch):
    """Si el lanzamiento vuelve con el registro YA en error, la idea no se sella y la pieza se borra."""
    from keni_consola import generaciones, repos
    from keni_consola.api import idear as api_evergreen

    creadas: list[str] = []
    orig_crear = repos.crear_publicacion

    def crear_spy(**kw):
        pieza = orig_crear(**kw)
        creadas.append(pieza["id"])
        return pieza

    monkeypatch.setattr(api_evergreen.repos, "crear_publicacion", crear_spy)
    monkeypatch.setattr(
        api_evergreen.gen_dom,
        "lanzar_copy",
        lambda **kw: {"id": "gen-x", "estado": generaciones.ESTADO_ERROR, "error": "cola llena"},
    )

    idea = repos.crear_evergreen_idea(
        marca="unotv", titulo="X", descripcion="y", estado="aprobada"
    )
    r = cliente.post(f"/api/evergreen/ideas/{idea['id']}/generar", json={})
    assert r.status_code == 200, r.text
    assert r.json()["generacion"]["estado"] == generaciones.ESTADO_ERROR
    idea2 = repos.obtener_evergreen_idea(idea["id"])
    assert idea2["estado"] == "aprobada"
    assert not idea2.get("publicacion_id")
    assert creadas and repos.obtener_publicacion(creadas[0]) is None


def test_reconstruir_al_fallar_sin_acciones_es_none():
    """Sin `al_fallar` (o con acciones vacías), no hay limpieza: el resto de jobs no se tocan."""
    from keni_consola.dominio import jobspec

    assert jobspec.reconstruir_al_fallar({}) is None
    assert jobspec.reconstruir_al_fallar({"al_fallar": {}}) is None
    assert (
        jobspec.reconstruir_al_fallar(
            {"al_fallar": {"borrar_publicacion": "", "revertir_idea_evergreen": ""}}
        )
        is None
    )


def test_reconstruir_al_fallar_borra_pieza_y_revierte_idea(entorno):
    """La limpieza `al_fallar` borra la pieza desechable y revierte la idea a aprobada."""
    from keni_consola import repos
    from keni_consola.dominio import jobspec

    idea = repos.crear_evergreen_idea(
        marca="unotv", titulo="X", descripcion="y", estado="aprobada"
    )
    pieza = repos.crear_publicacion(
        clase="contenido", flujo="evergreen", titulo="X", marca="unotv", origen="evergreen"
    )
    repos.actualizar_evergreen_idea(
        idea["id"], {"estado": "generada", "publicacion_id": pieza["id"]}
    )

    limpiar = jobspec.reconstruir_al_fallar(
        {"al_fallar": {"borrar_publicacion": pieza["id"], "revertir_idea_evergreen": idea["id"]}}
    )
    assert limpiar is not None
    limpiar()

    assert repos.obtener_publicacion(pieza["id"]) is None
    idea2 = repos.obtener_evergreen_idea(idea["id"])
    assert idea2["estado"] == "aprobada"
    assert not idea2.get("publicacion_id")


def test_worker_limpia_al_fallar_solo_en_error(entorno, monkeypatch):
    """El worker ejecuta la limpieza `al_fallar` SOLO si el job terminó en error."""
    from keni_consola import generaciones, repos, worker

    idea = repos.crear_evergreen_idea(
        marca="unotv", titulo="X", descripcion="y", estado="aprobada"
    )
    pieza = repos.crear_publicacion(
        clase="contenido", flujo="evergreen", titulo="X", marca="unotv", origen="evergreen"
    )
    repos.actualizar_evergreen_idea(
        idea["id"], {"estado": "generada", "publicacion_id": pieza["id"]}
    )
    spec = {
        "al_fallar": {"borrar_publicacion": pieza["id"], "revertir_idea_evergreen": idea["id"]}
    }

    # Terminó COMPLETADO: no toca nada.
    monkeypatch.setattr(
        worker.generaciones, "obtener", lambda _gid: {"estado": generaciones.ESTADO_COMPLETADO}
    )
    worker._limpiar_si_fallo("gen-x", spec)
    assert repos.obtener_publicacion(pieza["id"]) is not None
    assert repos.obtener_evergreen_idea(idea["id"])["estado"] == "generada"

    # Terminó en ERROR: borra la pieza y revierte la idea.
    monkeypatch.setattr(
        worker.generaciones, "obtener", lambda _gid: {"estado": generaciones.ESTADO_ERROR}
    )
    worker._limpiar_si_fallo("gen-x", spec)
    assert repos.obtener_publicacion(pieza["id"]) is None
    assert repos.obtener_evergreen_idea(idea["id"])["estado"] == "aprobada"
