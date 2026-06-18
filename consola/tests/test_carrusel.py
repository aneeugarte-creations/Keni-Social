"""Carrusel desde un post (`dominio.carrusel`): convierte un post YA redactado en un carrusel.

Parte el copy en titulares de slides (helper PURO de parseo), los hornea como placas de la marca
(seam `_COMPONER_SLIDE` parcheable) y escribe el MISMO `carrusel` JSON en todas las piezas gemelas
del contenido. El lanzamiento compone el prompt (autocontenido) y ENCOLA vía `generar.lanzar`.
"""

from __future__ import annotations

import json

import pytest

from keni_consola import repos
from keni_consola.dominio import carrusel as dom_carrusel
from keni_consola.dominio import copy as dom_copy
from keni_consola.dominio import jobspec

_MARCA = "unotv"


# --------------------------------------------------------------------------- #
# Parseo de la salida — PURO                                                     #
# --------------------------------------------------------------------------- #


def test_parsea_slides_con_valla():
    salida = 'Aquí va:\n```json\n{"slides": [{"titular": "Uno"}, {"titular": "Dos"}]}\n```\n'
    assert dom_carrusel._parsear_slides(salida) == ["Uno", "Dos"]


def test_parsea_slides_desnudo():
    assert dom_carrusel._parsear_slides('{"slides": [{"titular": "Solo"}]}') == ["Solo"]


def test_parseo_basura_devuelve_vacio():
    assert dom_carrusel._parsear_slides("no hay json aquí") == []
    assert dom_carrusel._parsear_slides("") == []
    assert dom_carrusel._parsear_slides('{"slides": "no es lista"}') == []


def test_parseo_descarta_titulares_vacios_y_topa_en_max():
    crudo = json.dumps({"slides": [{"titular": "  "}, {"titular": "Vale"}]})
    assert dom_carrusel._parsear_slides(crudo) == ["Vale"]
    muchos = json.dumps({"slides": [{"titular": f"T{i}"} for i in range(dom_carrusel.MAX_SLIDES + 5)]})
    assert len(dom_carrusel._parsear_slides(muchos)) == dom_carrusel.MAX_SLIDES


# --------------------------------------------------------------------------- #
# jobspec — roundtrip del kind                                                   #
# --------------------------------------------------------------------------- #


def test_jobspec_carrusel_roundtrip():
    spec = jobspec.construir_carrusel(publicacion_id="c1")
    assert spec == {"kind": jobspec.PROC_CARRUSEL, "publicacion_id": "c1"}
    # El worker reconstruye un callback ejecutable a partir del spec serializado.
    proc = jobspec.reconstruir_procesar({"procesar": spec})
    assert callable(proc)


# --------------------------------------------------------------------------- #
# Horneado de slides — seam `_COMPONER_SLIDE` parcheado (sin renderer Node)       #
# --------------------------------------------------------------------------- #


def test_hornear_slides_omite_los_que_no_componen(monkeypatch):
    # El renderer compone "Uno" pero no "Dos" (objeto vacío): "Dos" se omite.
    def fake(marca, titular, foto):
        return {"objeto": f"media-{titular}", "foto": ""} if titular == "Uno" else {"objeto": "", "foto": ""}

    monkeypatch.setattr(dom_copy, "_COMPONER_SLIDE", fake)
    slides = dom_carrusel.hornear_slides(_MARCA, ["Uno", "Dos"])
    assert slides == [{"tipo": "imagen", "objeto": "media-Uno", "titular": "Uno"}]


def test_lanzar_para_pieza_sin_pieza_lanza_error(monkeypatch):
    monkeypatch.setattr(dom_carrusel.repos, "obtener_pieza", lambda _id: None)
    with pytest.raises(dom_carrusel.CarruselError):
        dom_carrusel.lanzar_para_pieza("nope")


# --------------------------------------------------------------------------- #
# Persistencia + lanzamiento — Postgres (fixture `entorno`)                       #
# --------------------------------------------------------------------------- #


def _crear_contenido(reds: list[str], copy: str) -> tuple[str, list[str]]:
    tema = repos.crear_publicacion(clase="contenido", titulo="Tema", marca=_MARCA)
    ids = [repos.crear_pieza_fila(publicacion_id=tema["id"], red=r, copy=copy)["id"] for r in reds]
    return tema["id"], ids


def test_aplicar_carrusel_escribe_identico_en_todas_las_gemelas(entorno, monkeypatch):
    monkeypatch.setattr(
        dom_copy, "_COMPONER_SLIDE",
        lambda marca, titular, foto: {"objeto": f"media-{titular}", "foto": ""},
    )
    pid, ids = _crear_contenido(["instagram", "x"], "Cuerpo del post")
    slides = dom_carrusel.aplicar_carrusel(pid, ["Idea uno", "Idea dos"])
    assert [s["titular"] for s in slides] == ["Idea uno", "Idea dos"]
    # GEMELO: las dos piezas del contenido llevan EXACTAMENTE el mismo carrusel.
    listas = [json.loads(repos.obtener_pieza(i)["carrusel"]) for i in ids]
    assert listas[0] == listas[1] == slides


def test_aplicar_carrusel_vacio_si_no_compone_ningun_slide(entorno, monkeypatch):
    monkeypatch.setattr(dom_copy, "_COMPONER_SLIDE", lambda marca, titular, foto: {"objeto": "", "foto": ""})
    pid, ids = _crear_contenido(["instagram"], "Cuerpo del post")
    assert dom_carrusel.aplicar_carrusel(pid, ["Idea"]) == []
    # Sin slides componibles el campo carrusel queda intacto (sugerencia de formato).
    assert (repos.obtener_pieza(ids[0])["carrusel"] or "") == ""


def test_aplicar_carrusel_ignora_programado_y_publicado(entorno, monkeypatch):
    monkeypatch.setattr(
        dom_copy, "_COMPONER_SLIDE",
        lambda marca, titular, foto: {"objeto": f"media-{titular}", "foto": ""},
    )
    pid, ids = _crear_contenido(["instagram"], "Cuerpo del post")
    repos.transicionar_estado_pieza(ids[0], "borrador", "en_revision")
    repos.transicionar_estado_pieza(ids[0], "en_revision", "programado")
    assert dom_carrusel.aplicar_carrusel(pid, ["Idea"]) == []


def test_lanzar_para_pieza_compone_el_prompt_y_encola(entorno, monkeypatch):
    captura: dict = {}

    def fake_lanzar(**kw):
        captura.update(kw)
        return {"id": "g1", "estado": "ejecutando"}

    monkeypatch.setattr(dom_carrusel.generar, "lanzar", fake_lanzar)
    pid, ids = _crear_contenido(["instagram", "x"], "Un sensor cuántico rescata señales del universo")
    repos.actualizar_pieza(ids[0], {"copy_in": "UN SENSOR CUÁNTICO"})

    gen = dom_carrusel.lanzar_para_pieza(ids[0])
    assert gen == {"id": "g1", "estado": "ejecutando"}
    assert captura["tipo"] == "carrusel"
    assert captura["marca"] == _MARCA
    assert captura["clave_idem"] == f"carrusel:{pid}"
    assert captura["publicacion_id"] == pid
    assert captura["procesar_spec"] == {"kind": jobspec.PROC_CARRUSEL, "publicacion_id": pid}
    # El copy y el titular de portada viajan DENTRO del prompt (autocontenido).
    assert "Un sensor cuántico rescata señales del universo" in captura["prompt"]
    assert "UN SENSOR CUÁNTICO" in captura["prompt"]
    # Run READ-ONLY: veta escritura/red.
    assert "Write" in captura["endurecer"]["disallowed_tools"]


def test_lanzar_para_pieza_sin_copy_lanza_error(entorno):
    _pid, ids = _crear_contenido(["instagram"], "")
    with pytest.raises(dom_carrusel.CarruselError):
        dom_carrusel.lanzar_para_pieza(ids[0])
