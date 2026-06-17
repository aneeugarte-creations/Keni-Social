"""Tests del veredicto de la verificación de la FUENTE (`dominio.verificar_fuente.parsear_verificacion_fuente`).

PURO (sin Postgres ni claude). El contrato del prompt pide el campo JSON `veredicto` en slug ASCII
("verificado" | "requiere_humano" | "rechazado"); el parser acepta TAMBIÉN el semáforo 🟢/🟡/🔴.
Es FAIL-CLOSED de 3 niveles: solo una verificación POSITIVA (`verificado`/🟢, sin hallazgo de peso)
pasa; solo un problema de PESO (`rechazado`/🔴 o un hallazgo `error`) rechaza; cualquier otra cosa
—`requiere_humano`/🟡, vacío, malformado, timeout, slug irreconocible— cae a `requiere_humano`.
"""

from __future__ import annotations

import json

from keni_consola.dominio import verificar_fuente as verificar


def _salida(veredicto, *, linea="", hallazgos=None) -> str:
    bloque = {"veredicto": veredicto, "resumen": "una frase", "hallazgos": hallazgos or []}
    cuerpo = f"{linea}\n\n" if linea else ""
    return cuerpo + "```json\n" + json.dumps(bloque, ensure_ascii=False) + "\n```\n"


_HALLAZGO_ERROR = [{"tipo": "dato", "gravedad": "error", "explicacion": "dato inventado"}]


def test_slug_verificado():
    assert verificar.parsear_verificacion_fuente(_salida("verificado"))["verificacion_fuente"] == verificar.VERIFICACION_VERIFICADO


def test_slug_rechazado():
    assert verificar.parsear_verificacion_fuente(_salida("rechazado"))["verificacion_fuente"] == verificar.VERIFICACION_RECHAZADO


def test_slug_requiere_humano():
    assert verificar.parsear_verificacion_fuente(_salida("requiere_humano"))["verificacion_fuente"] == verificar.VERIFICACION_REQUIERE_HUMANO


def test_slug_tolera_mayusculas_y_espacios():
    assert verificar.parsear_verificacion_fuente(_salida(" VERIFICADO "))["verificacion_fuente"] == verificar.VERIFICACION_VERIFICADO
    assert verificar.parsear_verificacion_fuente(_salida("  Rechazado "))["verificacion_fuente"] == verificar.VERIFICACION_RECHAZADO


def test_emoji_semaforo():
    # El semáforo en el campo `veredicto` del JSON mapea a los tres niveles.
    assert verificar.parsear_verificacion_fuente(_salida("🟢", linea="🟢 Confirmada."))["verificacion_fuente"] == verificar.VERIFICACION_VERIFICADO
    assert verificar.parsear_verificacion_fuente(_salida("🟡"))["verificacion_fuente"] == verificar.VERIFICACION_REQUIERE_HUMANO
    assert verificar.parsear_verificacion_fuente(_salida("🔴"))["verificacion_fuente"] == verificar.VERIFICACION_RECHAZADO


def test_hallazgo_error_fuerza_rechazado():
    # Un hallazgo de gravedad `error` (algo de peso) rechaza AUNQUE el veredicto diga "verificado".
    informe = verificar.parsear_verificacion_fuente(_salida("verificado", hallazgos=_HALLAZGO_ERROR))
    assert informe["verificacion_fuente"] == verificar.VERIFICACION_RECHAZADO


def test_slug_del_json_manda_sobre_la_linea_de_semaforo():
    # El JSON es el contrato; una línea 🔴 humana contradictoria no fuerza el rechazo si el JSON
    # dice "verificado" (mismo criterio de prioridad que el resto del parseo del informe).
    informe = verificar.parsear_verificacion_fuente(_salida("verificado", linea="🔴 ¿seguro?"))
    assert informe["verificacion_fuente"] == verificar.VERIFICACION_VERIFICADO


def test_fail_closed_a_requiere_humano():
    # Sin verificación positiva NI rechazo claro -> requiere_humano (la IA no pudo confirmar):
    # slug irreconocible, salida vacía o sin estructura (incl. timeout). NO se rechaza ni se verifica.
    assert verificar.parsear_verificacion_fuente(_salida("verde brillante"))["verificacion_fuente"] == verificar.VERIFICACION_REQUIERE_HUMANO
    assert verificar.parsear_verificacion_fuente("")["verificacion_fuente"] == verificar.VERIFICACION_REQUIERE_HUMANO
    assert verificar.parsear_verificacion_fuente("texto sin estructura")["verificacion_fuente"] == verificar.VERIFICACION_REQUIERE_HUMANO


def test_sin_json_con_linea_roja_es_requiere_humano():
    # 🔴 solo en la prosa, sin bloque json: el contrato es el JSON, así que sin él no hay rechazo
    # claro -> requiere_humano (fail-closed, no se auto-produce).
    informe = verificar.parsear_verificacion_fuente("🔴 Problema de peso.\n\nSin bloque json.")
    assert informe["verificacion_fuente"] == verificar.VERIFICACION_REQUIERE_HUMANO


def test_hallazgo_error_sin_slug_es_rechazado():
    # Sin veredicto reconocible pero con un hallazgo de PESO: rechazado (el peso manda sobre el fail-closed).
    informe = verificar.parsear_verificacion_fuente(_salida("???", hallazgos=_HALLAZGO_ERROR))
    assert informe["verificacion_fuente"] == verificar.VERIFICACION_RECHAZADO
