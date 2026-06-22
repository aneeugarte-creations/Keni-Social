"""Tests del TALLER EVERGREEN / brainstorming: parseo de ideas (PURO) + CRUD de `evergreen_ideas`.

Dos bloques:
  - `parsear_ideas`: dominio PURO (sin BD). Cubre el JSON cercado, el dict envoltorio, el
    reparación (título obligatorio, recortes), la deduplicación y el tope `MAX_IDEAS`.
  - CRUD de `evergreen_ideas` en `db.py` (requiere el Postgres de pruebas, fixture `entorno`; se
    salta si no hay).
"""

from __future__ import annotations

import json

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
# Aprobar una idea LANZA su investigación                                      #
# --------------------------------------------------------------------------- #


def test_aprobar_lanza_investigacion(cliente, monkeypatch):
    """PATCH {estado:'aprobada'} lanza la investigación y devuelve la generación; idea queda aprobada."""
    from keni_consola import repos
    from keni_consola.pipeline_contenido import _investigar_evergreen as inv

    lanzadas: list[str] = []

    def fake_lanzar(idea, *, autor):
        lanzadas.append(idea["id"])
        return {"id": "gen-x", "estado": "ejecutando"}

    monkeypatch.setattr(inv, "lanzar_investigar_idea", fake_lanzar)

    idea = repos.crear_evergreen_idea(
        marca="unotv", titulo="Explicador VAR", descripcion="cómo funciona", estado="propuesta"
    )
    r = cliente.patch(f"/api/evergreen/ideas/{idea['id']}", json={"estado": "aprobada"})
    assert r.status_code == 200, r.text
    datos = r.json()
    assert datos["idea"]["estado"] == "aprobada"
    assert datos["generacion"]["id"] == "gen-x"
    assert lanzadas == [idea["id"]]


def test_editar_texto_no_relanza(cliente, monkeypatch):
    """Editar texto (PATCH sin `estado`) de una idea aprobada NO relanza la investigación."""
    from keni_consola import repos
    from keni_consola.pipeline_contenido import _investigar_evergreen as inv

    lanzadas: list[str] = []
    monkeypatch.setattr(
        inv, "lanzar_investigar_idea",
        lambda idea, *, autor: lanzadas.append(idea["id"]) or {"id": "gen-x"},
    )
    idea = repos.crear_evergreen_idea(
        marca="unotv", titulo="X", descripcion="y", estado="aprobada"
    )
    r = cliente.patch(f"/api/evergreen/ideas/{idea['id']}", json={"descripcion": "z"})
    assert r.status_code == 200, r.text
    assert "generacion" not in r.json()
    assert lanzadas == []


def test_reaprobar_sin_tema_reintenta(cliente, monkeypatch):
    """Re-aprobar una idea aprobada SIN tema (reintento tras un fallo) relanza la investigación."""
    from keni_consola import repos
    from keni_consola.pipeline_contenido import _investigar_evergreen as inv

    lanzadas: list[str] = []
    monkeypatch.setattr(
        inv, "lanzar_investigar_idea",
        lambda idea, *, autor: lanzadas.append(idea["id"]) or {"id": "gen-x", "estado": "ejecutando"},
    )
    idea = repos.crear_evergreen_idea(
        marca="unotv", titulo="X", descripcion="y", estado="aprobada"
    )
    r = cliente.patch(f"/api/evergreen/ideas/{idea['id']}", json={"estado": "aprobada"})
    assert r.status_code == 200, r.text
    assert r.json()["generacion"]["id"] == "gen-x"
    assert lanzadas == [idea["id"]]


# --------------------------------------------------------------------------- #
# Post-procesado de la investigación: viable crea tema recogible por producción #
# --------------------------------------------------------------------------- #

_SALIDA_VIABLE = (
    "🟢 Hay material verificado suficiente.\n\n"
    "Brief: la efeméride es real.\n\n"
    '```json\n{"viable": true, "material": "hechos verificados sobre el tema",'
    ' "fuentes": ["https://fuente-1", "https://fuente-2"]}\n```\n'
)
_SALIDA_NO_VIABLE = (
    "🟡 Material flojo, no corroborable.\n\n"
    '```json\n{"viable": false, "material": "", "fuentes": []}\n```\n'
)


def test_investigar_viable_crea_tema_recogible_por_produccion(entorno):
    """Una investigación VIABLE crea un tema verificado del pipeline que producción recoge."""
    from keni_consola import repos
    from keni_consola.pipeline_contenido import _investigar_evergreen as inv
    from keni_consola.pipeline_contenido import _redactar

    idea = repos.crear_evergreen_idea(
        marca="unotv", titulo="Efeméride futbolera", descripcion="qué pasó", estado="aprobada"
    )
    procesar = inv.construir_procesar_investigar_evergreen(
        idea["id"], "unotv", "Efeméride futbolera", None
    )
    resultado = procesar(_SALIDA_VIABLE, None)
    assert resultado["viable"] is True
    tema_id = resultado["publicacion_id"]

    tema = repos.obtener_publicacion(tema_id)
    assert tema["origen"] == "pipeline"
    assert tema["flujo"] == "evergreen"
    assert tema["verificacion_fuente"] == "verificado"
    assert tema["descripcion"] == "hechos verificados sobre el tema"
    # El material viaja en `copy_pendiente` (la NOTA) para que producción lo redacte sin re-investigar.
    pend = json.loads(tema["copy_pendiente"])
    assert pend["nota"] == "hechos verificados sobre el tema"

    # La idea queda `generada` y enlazada al tema.
    idea2 = repos.obtener_evergreen_idea(idea["id"])
    assert idea2["estado"] == "generada"
    assert idea2["publicacion_id"] == tema_id

    # Producción lo recoge igual que una historia verificada (verificado + copy_pendiente + sin copy).
    ids = {t["id"] for t in _redactar.temas_para_redactar("unotv")}
    assert tema_id in ids


def test_investigar_no_viable_no_crea_tema(entorno):
    """Una investigación NO VIABLE no crea tema; la idea sigue `aprobada` (reintentable)."""
    from keni_consola import repos
    from keni_consola.pipeline_contenido import _investigar_evergreen as inv

    idea = repos.crear_evergreen_idea(
        marca="unotv", titulo="Tema flojo", descripcion="poco", estado="aprobada"
    )
    antes = {p["id"] for p in repos.listar_publicacion(marca="unotv")}
    procesar = inv.construir_procesar_investigar_evergreen(
        idea["id"], "unotv", "Tema flojo", None
    )
    resultado = procesar(_SALIDA_NO_VIABLE, None)
    assert resultado == {"viable": False, "piezas": []}

    despues = {p["id"] for p in repos.listar_publicacion(marca="unotv")}
    assert despues == antes  # no nació ningún tema
    assert repos.obtener_evergreen_idea(idea["id"])["estado"] == "aprobada"


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
