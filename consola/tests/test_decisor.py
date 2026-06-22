"""Decisor de formato (foto vs carrusel): parseo, persistencia del camino y split de Redactar.

Cubre la etapa PREVIA a Redactar (`dominio.decisor`) y el branch por `camino` que se extrajo del
prompt de Redactar (`dominio.generar.instruccion_copy_unico`). El gate del barrido y el modelo Haiku
se validan en el servidor; aquí van las unidades puras + la persistencia del camino (fixture DB).
"""

from __future__ import annotations

import json

from keni_consola import repos
from keni_consola.dominio import decisor as dom_decisor
from keni_consola.dominio import generar, jobspec

_MARCA = "claro-sports"


# --------------------------------------------------------------------------- #
# Parseo del camino                                                            #
# --------------------------------------------------------------------------- #


def test_parsear_camino_valla_y_desnudo():
    assert dom_decisor.parsear_camino('```json\n{"camino": "carrusel"}\n```') == "carrusel"
    assert dom_decisor.parsear_camino('{"camino": "foto"}') == "foto"
    # Tolera texto alrededor (razonamiento antes del json).
    assert dom_decisor.parsear_camino('Creo que es panel.\n{"camino":"carrusel"}') == "carrusel"


def test_parsear_camino_basura_cae_a_foto():
    # Ante cualquier salida ilegible o camino desconocido, formato conservador: foto.
    assert dom_decisor.parsear_camino("no hay json aquí") == "foto"
    assert dom_decisor.parsear_camino("") == "foto"
    assert dom_decisor.parsear_camino('{"camino": "video"}') == "foto"
    assert dom_decisor.parsear_camino('{"otra": "cosa"}') == "foto"


def test_jobspec_decisor_roundtrip():
    spec = jobspec.construir_decisor(publicacion_id="t1")
    assert spec == {"kind": jobspec.PROC_DECISOR, "publicacion_id": "t1"}
    # El worker reconstruye un callable desde el spec (sin estado extra).
    proc = jobspec.reconstruir_procesar({"procesar": spec})
    assert callable(proc)


# --------------------------------------------------------------------------- #
# Split de Redactar: el camino dirige el bloque de formato                      #
# --------------------------------------------------------------------------- #


def test_instruccion_camino_carrusel_arma_panel():
    instr = generar.instruccion_copy_unico(
        ["instagram", "facebook"], n_notas=3,
        fotos_notas=[{"titulo": "Nota A", "imagen": "u"}], camino="carrusel",
    )
    # Directiva imperativa de panel (no decisión): pide tipo carrusel + slides.
    assert "PRODUCE un CARRUSEL" in instr
    assert '"tipo": "carrusel"' in instr
    assert '"slides"' in instr
    # Ya NO ofrece elegir post (la decisión la tomó el Decisor).
    assert "Ante la duda" not in instr


def test_instruccion_camino_foto_fija_post():
    instr = generar.instruccion_copy_unico(["instagram", "facebook"], n_notas=3, camino="foto")
    assert "El formato YA está decidido" in instr
    assert '"tipo": "post"' in instr
    # Camino foto: NO arma el panel de carrusel (aunque haya 2+ notas, lo decidió el Decisor).
    assert "PRODUCE un CARRUSEL" not in instr
    assert '"slides": [' not in instr


def test_instruccion_sin_camino_mantiene_decision_vieja():
    # Sin Decisor (camino=""): comportamiento de hoy. Con 1 nota, sugerencia simple post|carrusel.
    instr = generar.instruccion_copy_unico(["facebook"])
    assert "DECIDE además el `tipo`" in instr
    assert "Ante la duda" in instr


# --------------------------------------------------------------------------- #
# Persistencia del camino en copy_pendiente — Postgres (fixture `entorno`)        #
# --------------------------------------------------------------------------- #


def test_aplicar_camino_escribe_en_copy_pendiente(entorno):
    tema = repos.crear_publicacion(clase="contenido", titulo="Tema", marca=_MARCA)
    repos.actualizar_publicacion(
        tema["id"], {"copy_pendiente": json.dumps({"nota": "x", "n_notas": 2})}
    )
    assert dom_decisor.aplicar_camino(tema["id"], "carrusel") == "carrusel"
    pend = json.loads(repos.obtener_publicacion(tema["id"])["copy_pendiente"])
    assert pend["camino"] == "carrusel"
    # No pisa el resto del pendiente.
    assert pend["nota"] == "x" and pend["n_notas"] == 2


def test_aplicar_camino_no_resucita_pendiente_limpio(entorno):
    # Si el copy ya se generó y limpió copy_pendiente, el camino tardío NO lo resucita.
    tema = repos.crear_publicacion(clase="contenido", titulo="Tema", marca=_MARCA)
    assert dom_decisor.aplicar_camino(tema["id"], "carrusel") == "carrusel"
    assert (repos.obtener_publicacion(tema["id"]).get("copy_pendiente") or "") == ""
