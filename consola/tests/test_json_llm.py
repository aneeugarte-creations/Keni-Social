"""Tests del extractor compartido de JSON de salidas de modelo (`dominio.json_llm`).

PURO: sin red, sin claude, sin Postgres. Cubre la cadena completa: JSON desnudo, bloques
```json (incluido el ÚLTIMO cuando hay varios), prosa antes/después, malformado, tipo
inesperado, dict envoltorio con claves, y el helper de truncado.
"""

from __future__ import annotations

import json
import logging

from keni_consola.dominio import json_llm

# --------------------------------------------------------------------------- #
# extraer_json                                                                  #
# --------------------------------------------------------------------------- #


def test_json_desnudo_dict_y_lista():
    assert json_llm.extraer_json('{"a": 1}') == {"a": 1}
    assert json_llm.extraer_json("[1, 2, 3]") == [1, 2, 3]


def test_fence_json_simple():
    assert json_llm.extraer_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_fence_sin_etiqueta_y_mayusculas():
    assert json_llm.extraer_json('```\n{"a": 1}\n```') == {"a": 1}
    assert json_llm.extraer_json('```JSON\n{"a": 1}\n```') == {"a": 1}


def test_ultimo_fence_gana_cuando_hay_varios():
    # El modelo a veces razona con un bloque previo y cierra con el JSON bueno.
    texto = (
        "Primero pensé esto:\n```json\n{\"borrador\": true}\n```\n"
        "Pero lo correcto es:\n```json\n{\"final\": true}\n```\n"
    )
    assert json_llm.extraer_json(texto) == {"final": True}


def test_prosa_antes_y_despues_sin_fences():
    texto = 'Claro, aquí está el resultado: {"items": [{"titulo": "X"}]} ¡Espero que sirva!'
    assert json_llm.extraer_json(texto) == {"items": [{"titulo": "X"}]}


def test_prosa_antes_devuelve_el_envoltorio_no_un_fragmento_interno():
    # El bloque balanceado debe ser el EXTERIOR aunque contenga objetos anidados.
    texto = 'Resultado: {"items": [{"titulo": "A"}, {"titulo": "B"}]}'
    data = json_llm.extraer_json(texto)
    assert data == {"items": [{"titulo": "A"}, {"titulo": "B"}]}


def test_braces_espurios_en_la_prosa_no_confunden():
    texto = "pensando {esto no es json... al final:\n" '{"ok": [1, 2]}'
    assert json_llm.extraer_json(texto) == {"ok": [1, 2]}


def test_malformado_devuelve_none():
    assert json_llm.extraer_json("lo siento, no encontré nada") is None
    assert json_llm.extraer_json('{"roto": [1, 2') is None
    assert json_llm.extraer_json("") is None
    assert json_llm.extraer_json("   ") is None


def test_tipo_inesperado_devuelve_none():
    # Un escalar JSON válido no es dict/list: no cuela.
    assert json_llm.extraer_json("42") is None
    assert json_llm.extraer_json('"texto"') is None
    # Y si se exige un tipo concreto, el otro no vale.
    assert json_llm.extraer_json('{"a": 1}', esperado=list) is None
    assert json_llm.extraer_json("[1]", esperado=dict) is None
    assert json_llm.extraer_json("[1]", esperado=list) == [1]


# --------------------------------------------------------------------------- #
# extraer_lista                                                                 #
# --------------------------------------------------------------------------- #


def test_extraer_lista_cruda_y_envoltorio():
    assert json_llm.extraer_lista('[{"x": 1}]') == [{"x": 1}]
    assert json_llm.extraer_lista('{"items": [{"x": 1}]}', claves=("items",)) == [{"x": 1}]


def test_extraer_lista_envoltorio_sin_clave_aceptada_es_none():
    # Contrato estricto: un dict con OTRA clave no cuela (p.ej. "ops" tras fijar "operaciones").
    assert json_llm.extraer_lista('{"ops": [1]}', claves=("operaciones",)) is None
    assert json_llm.extraer_lista('{"a": 1}') is None


def test_extraer_lista_fence_con_prosa():
    texto = "Aquí van:\n```json\n{\"grupos\": [[\"1\", \"2\"]]}\n```\nFin."
    assert json_llm.extraer_lista(texto, claves=("grupos",)) == [["1", "2"]]


def test_extraer_lista_lista_vacia_es_lista_no_none():
    assert json_llm.extraer_lista("```json\n[]\n```") == []


def test_extraer_lista_cae_a_fence_anterior_si_el_ultimo_no_trae_la_clave():
    texto = (
        '```json\n{"operaciones": [{"tipo": "crear_evento"}]}\n```\n'
        "nota final:\n```json\n{\"resumen\": \"ok\"}\n```"
    )
    assert json_llm.extraer_lista(texto, claves=("operaciones",)) == [{"tipo": "crear_evento"}]


def test_extraer_lista_grande_directa():
    datos = [{"i": i} for i in range(3000)]
    assert json_llm.extraer_lista(json.dumps(datos)) == datos


# --------------------------------------------------------------------------- #
# truncar                                                                       #
# --------------------------------------------------------------------------- #


def test_truncar_no_recorta_bajo_limite():
    assert json_llm.truncar("hola", 10) == ("hola", False)
    assert json_llm.truncar("", 5) == ("", False)
    assert json_llm.truncar("abcde", 5) == ("abcde", False)


def test_truncar_recorta_y_avisa():
    assert json_llm.truncar("abcdef", 3) == ("abc", True)


def test_truncar_avisando_deja_warn(caplog):
    log = logging.getLogger("keni_consola.dominio.json_llm")
    with caplog.at_level(logging.WARNING, logger=log.name):
        valor, fue = json_llm.truncar_avisando("x" * 20, 5, campo="titulo", log=log)
    assert (valor, fue) == ("x" * 5, True)
    assert any("titulo" in r.message and "20" in r.message and "5" in r.message for r in caplog.records)


def test_truncar_avisando_sin_recorte_no_avisa(caplog):
    log = logging.getLogger("keni_consola.dominio.json_llm")
    with caplog.at_level(logging.WARNING, logger=log.name):
        valor, fue = json_llm.truncar_avisando("ok", 5, campo="titulo", log=log)
    assert (valor, fue) == ("ok", False)
    assert not caplog.records
