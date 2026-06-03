"""Tests de la lógica PURA de dedup de contenido (`dominio.dedup`)."""

from __future__ import annotations

from keni_consola.dominio import dedup


def test_clave_normaliza_acentos_mayusculas_y_puntuacion():
    assert dedup.clave("¡Increíble  remontada!") == "increible remontada"
    assert dedup.clave("¡Increíble, REMONTADA!") == dedup.clave("increible remontada")


def test_clave_vacia_si_no_hay_tokens():
    assert dedup.clave("") == ""
    assert dedup.clave("   ") == ""
    assert dedup.clave("¿?¡!···") == ""


def test_es_duplicado_casa_mismo_titulo_normalizado():
    claves = {dedup.clave("Gol de último minuto")}
    assert dedup.es_duplicado("¡GOL de Último minuto!", claves) is True
    assert dedup.es_duplicado("Otra noticia distinta", claves) is False


def test_titulo_vacio_nunca_es_duplicado():
    # Una clave vacía no debe casar aunque "" esté en el conjunto (no hay con qué comparar).
    assert dedup.es_duplicado("", {""}) is False
    assert dedup.es_duplicado("   ", set()) is False
