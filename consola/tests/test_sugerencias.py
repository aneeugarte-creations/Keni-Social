"""Tests del dominio de sugerencias: máquina de estados (PURA) + CRUD/transiciones (Postgres).

Dos bloques:
  - máquina de estados: `transicion_valida` (PURO, sin BD).
  - CRUD + transiciones + post-procesado de jobs dev (requiere el Postgres de pruebas,
    fixture `entorno`; se salta si no hay).
"""

from __future__ import annotations

import pytest

from keni_consola import sugerencias

# --------------------------------------------------------------------------- #
# Máquina de estados — PURA                                                    #
# --------------------------------------------------------------------------- #


def test_transiciones_felices():
    assert sugerencias.transicion_valida("nueva", "discovery")
    assert sugerencias.transicion_valida("nueva", "en_cola")  # atajo simple
    assert sugerencias.transicion_valida("discovery", "en_cola")
    assert sugerencias.transicion_valida("en_cola", "building")
    assert sugerencias.transicion_valida("building", "revision")
    assert sugerencias.transicion_valida("building", "fallida")
    assert sugerencias.transicion_valida("revision", "hecha")
    assert sugerencias.transicion_valida("fallida", "en_cola")  # reintento


def test_descartar_desde_cualquier_estado():
    for estado in sugerencias.ESTADOS:
        assert sugerencias.transicion_valida(estado, "descartada")


def test_transiciones_invalidas():
    assert not sugerencias.transicion_valida("nueva", "hecha")
    assert not sugerencias.transicion_valida("nueva", "building")
    assert not sugerencias.transicion_valida("hecha", "building")
    assert not sugerencias.transicion_valida("en_cola", "inventado")


# --------------------------------------------------------------------------- #
# CRUD + transiciones — requiere Postgres (fixture `entorno`)                  #
# --------------------------------------------------------------------------- #


def test_crear_obtener_listar(entorno):
    s = sugerencias.crear("Idea A", detalle="detalle", categoria="mejora", autor="ane")
    assert s["estado"] == "nueva"
    assert s["categoria"] == "mejora"
    assert s["coste_usd"] == 0.0
    assert sugerencias.obtener(s["id"])["titulo"] == "Idea A"
    assert any(x["id"] == s["id"] for x in sugerencias.listar())


def test_crear_titulo_vacio_lanza(entorno):
    with pytest.raises(ValueError):
        sugerencias.crear("   ")


def test_crear_categoria_invalida_cae_a_defecto(entorno):
    s = sugerencias.crear("X", categoria="inventada")
    assert s["categoria"] == sugerencias.CATEGORIA_DEFECTO


def test_cambiar_estado_valido(entorno):
    s = sugerencias.crear("X")
    movida = sugerencias.cambiar_estado(s["id"], "discovery")
    assert movida["estado"] == "discovery"


def test_cambiar_estado_invalido_lanza(entorno):
    s = sugerencias.crear("X")
    with pytest.raises(sugerencias.TransicionInvalida):
        sugerencias.cambiar_estado(s["id"], "hecha")


def test_cambiar_estado_inexistente_devuelve_none(entorno):
    assert sugerencias.cambiar_estado("noexiste", "discovery") is None


def test_editar_texto(entorno):
    s = sugerencias.crear("X")
    edit = sugerencias.editar(s["id"], {"titulo": "Y", "detalle": "Z", "categoria": "bug"})
    assert edit["titulo"] == "Y"
    assert edit["detalle"] == "Z"
    assert edit["categoria"] == "bug"


def test_editar_titulo_vacio_lanza(entorno):
    s = sugerencias.crear("X")
    with pytest.raises(ValueError):
        sugerencias.editar(s["id"], {"titulo": "  "})


def test_borrar(entorno):
    s = sugerencias.crear("Borrame")
    assert sugerencias.borrar(s["id"]) is True
    assert sugerencias.obtener(s["id"]) is None
    assert sugerencias.borrar(s["id"]) is False


def test_actualizar_avance_no_cambia_estado(entorno):
    s = sugerencias.crear("X")
    sugerencias.cambiar_estado(s["id"], "discovery")
    actualizada = sugerencias.actualizar_avance(
        s["id"], {"spec": "el spec", "complejidad": "complex", "estado": "hecha"}
    )
    # `estado` se ignora en actualizar_avance (no cambia de estado por esa vía).
    assert actualizada["estado"] == "discovery"
    assert actualizada["spec"] == "el spec"
    assert actualizada["complejidad"] == "complex"


# --------------------------------------------------------------------------- #
# Post-procesado de jobs dev (callbacks que reconstruye `jobspec`)            #
# --------------------------------------------------------------------------- #


def test_procesar_dev_discovery_deja_en_cola(entorno):
    s = sugerencias.crear("X")
    sugerencias.cambiar_estado(s["id"], "discovery")
    procesar = sugerencias.construir_procesar_dev_discovery(sugerencia_id=s["id"])
    resumen = procesar("# SPEC\nhacer algo\ncomplejidad: simple", None)
    assert resumen["complejidad"] == "simple"
    actual = sugerencias.obtener(s["id"])
    assert actual["estado"] == "en_cola"
    assert actual["complejidad"] == "simple"
    assert "hacer algo" in actual["spec"]


def test_procesar_dev_fase_checkpoint_va_a_revision(entorno):
    s = sugerencias.crear("X")
    # Llevar a building con complejidad simple (pipeline build→review; review es checkpoint).
    sugerencias.cambiar_estado(s["id"], "en_cola", campos={"complejidad": "simple"})
    sugerencias.cambiar_estado(s["id"], "building")
    procesar = sugerencias.construir_procesar_dev_fase(sugerencia_id=s["id"], fase="review")
    procesar("revisado", None)
    actual = sugerencias.obtener(s["id"])
    assert actual["estado"] == "revision"
    assert actual["fase"] == "review"


def test_procesar_dev_fase_intermedia_sigue_en_building(entorno):
    s = sugerencias.crear("X")
    sugerencias.cambiar_estado(s["id"], "en_cola", campos={"complejidad": "standard"})
    sugerencias.cambiar_estado(s["id"], "building")
    procesar = sugerencias.construir_procesar_dev_fase(sugerencia_id=s["id"], fase="analyze")
    procesar("analizado", None)
    actual = sugerencias.obtener(s["id"])
    assert actual["estado"] == "building"  # analyze no es checkpoint: sigue el pipeline
