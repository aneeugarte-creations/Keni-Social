"""Tests del veredicto de la QA de la FUENTE (`dominio.qa_editorial.parsear_verdicto_fuente`).

PURO (sin Postgres ni claude). El contrato del prompt pide el campo JSON `veredicto` en slug
ASCII ("apta" | "problema"); el parser acepta TAMBIÉN el emoji legado 🟢/🔴 (piezas en vuelo
o un prompt editado en producción aún viejo) y degrada PERMISIVO ante valores basura.
"""

from __future__ import annotations

import json

from keni_consola.dominio import qa_editorial as qa


def _salida(veredicto, *, linea="", hallazgos=None) -> str:
    bloque = {"veredicto": veredicto, "resumen": "una frase", "hallazgos": hallazgos or []}
    cuerpo = f"{linea}\n\n" if linea else ""
    return cuerpo + "```json\n" + json.dumps(bloque, ensure_ascii=False) + "\n```\n"


_HALLAZGO_ERROR = [{"tipo": "dato", "gravedad": "error", "explicacion": "dato inventado"}]


def test_slug_apta_es_no_verificado():
    informe = qa.parsear_verdicto_fuente(_salida("apta"))
    assert informe["verdicto"] == qa.VERDICTO_NO_VERIFICADO


def test_slug_problema_es_problema():
    informe = qa.parsear_verdicto_fuente(_salida("problema"))
    assert informe["verdicto"] == qa.VERDICTO_PROBLEMA


def test_slug_tolera_mayusculas_y_espacios():
    assert qa.parsear_verdicto_fuente(_salida("  Problema "))["verdicto"] == qa.VERDICTO_PROBLEMA
    assert qa.parsear_verdicto_fuente(_salida(" APTA "))["verdicto"] == qa.VERDICTO_NO_VERIFICADO


def test_emoji_legado_verde_y_rojo():
    # Salidas en vuelo (o un prompt viejo en producción) siguen mandando el semáforo en el JSON.
    assert qa.parsear_verdicto_fuente(_salida("🟢", linea="🟢 Fuente apta."))["verdicto"] == qa.VERDICTO_NO_VERIFICADO
    assert qa.parsear_verdicto_fuente(_salida("🔴", linea="🔴 Problema."))["verdicto"] == qa.VERDICTO_PROBLEMA


def test_emoji_rojo_solo_en_json_sin_linea():
    assert qa.parsear_verdicto_fuente(_salida("🔴"))["verdicto"] == qa.VERDICTO_PROBLEMA


def test_valor_basura_degrada_permisivo():
    # Un veredicto irreconocible NO bloquea: permisivo por diseño (la pieza llevará ⚠️).
    informe = qa.parsear_verdicto_fuente(_salida("verde brillante"))
    assert informe["verdicto"] == qa.VERDICTO_NO_VERIFICADO


def test_valor_basura_con_hallazgo_error_sigue_siendo_problema():
    informe = qa.parsear_verdicto_fuente(_salida("???", hallazgos=_HALLAZGO_ERROR))
    assert informe["verdicto"] == qa.VERDICTO_PROBLEMA


def test_slug_apta_con_hallazgo_error_pesa_mas_el_hallazgo():
    informe = qa.parsear_verdicto_fuente(_salida("apta", hallazgos=_HALLAZGO_ERROR))
    assert informe["verdicto"] == qa.VERDICTO_PROBLEMA


def test_slug_del_json_manda_sobre_la_linea_de_semaforo():
    # El JSON es el contrato; la línea 🔴 humana contradictoria no fuerza el bloqueo si el
    # JSON dice "apta" (mismo criterio de prioridad que el resto del parseo del informe).
    informe = qa.parsear_verdicto_fuente(_salida("apta", linea="🔴 ¿seguro?"))
    assert informe["verdicto"] == qa.VERDICTO_NO_VERIFICADO


def test_sin_json_con_linea_roja_es_problema():
    informe = qa.parsear_verdicto_fuente("🔴 Problema de peso.\n\nSin bloque json.")
    assert informe["verdicto"] == qa.VERDICTO_PROBLEMA


def test_sin_nada_es_no_verificado():
    assert qa.parsear_verdicto_fuente("")["verdicto"] == qa.VERDICTO_NO_VERIFICADO
    assert qa.parsear_verdicto_fuente("texto sin estructura")["verdicto"] == qa.VERDICTO_NO_VERIFICADO
