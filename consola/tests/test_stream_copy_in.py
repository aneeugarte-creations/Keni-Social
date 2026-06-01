"""Parseo del copy_in (texto EN imagen) en `dominio.stream.parsear_salida`. PURO (sin DB).

El copy_in viaja en la MISMA pieza que el copy: el bloque ```json final puede traer un
`copy_in` por red, que el parser expone en cada pieza junto a `contenido`/`caracteres`.
"""

from __future__ import annotations

from keni_consola.dominio import stream


def test_parsea_copy_in_de_la_pieza():
    salida = (
        "Texto\n\n```json\n"
        '{"piezas": [{"red": "x", "texto": "Hola X", "copy_in": "TITULAR"}]}\n```'
    )
    piezas = stream.parsear_salida(salida, ["x"])["piezas"]
    assert piezas == [
        {"red": "x", "contenido": "Hola X", "caracteres": len("Hola X"), "copy_in": "TITULAR"}
    ]


def test_copy_in_ausente_es_cadena_vacia():
    salida = '```json\n{"piezas": [{"red": "x", "texto": "Hola X"}]}\n```'
    pieza = stream.parsear_salida(salida, ["x"])["piezas"][0]
    assert pieza["copy_in"] == ""
    # `caracteres` mide SOLO el contenido, no el copy_in.
    assert pieza["caracteres"] == len("Hola X")


def test_copy_in_no_texto_se_ignora():
    # Un copy_in no-string (numero/objeto) degrada a "" sin romper el parseo.
    salida = '```json\n{"piezas": [{"red": "x", "texto": "Hola", "copy_in": 123}]}\n```'
    assert stream.parsear_salida(salida, ["x"])["piezas"][0]["copy_in"] == ""


def test_fallback_por_encabezados_sin_copy_in():
    # Sin bloque JSON, el reparto por encabezados no conoce copy_in: queda "".
    salida = "X\nHola desde X"
    pieza = stream.parsear_salida(salida, ["x"])["piezas"][0]
    assert pieza["copy_in"] == ""
    assert pieza["contenido"] == "Hola desde X"
