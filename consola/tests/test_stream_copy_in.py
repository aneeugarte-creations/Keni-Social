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


# --------------------------------------------------------------------------- #
# Copy UNIFICADO (`parsear_salida_unificada`): UN copy + copy_in para TODAS    #
# --------------------------------------------------------------------------- #


def test_unificada_replica_el_mismo_copy_y_copy_in_a_todas_las_redes():
    # Un solo objeto {texto, copy_in} se emite IGUAL para cada red pedida (incluida X, que así
    # nunca queda sin copy_in).
    salida = (
        "Veredicto\n\n```json\n"
        '{"texto": "Mismo copy", "copy_in": "TITULAR"}\n```'
    )
    piezas = stream.parsear_salida_unificada(salida, ["x", "instagram", "facebook", "tiktok"])["piezas"]
    assert [p["red"] for p in piezas] == ["x", "instagram", "facebook", "tiktok"]
    assert all(p["contenido"] == "Mismo copy" for p in piezas)
    assert all(p["copy_in"] == "TITULAR" for p in piezas)
    # X (la primera) trae copy_in como las demás (regresión del copy_in vacío de X).
    assert piezas[0] == {"red": "x", "contenido": "Mismo copy", "caracteres": len("Mismo copy"), "copy_in": "TITULAR"}


def test_unificada_tolera_la_forma_vieja_piezas():
    # Resiliencia: si el modelo emite el array `piezas`, se toma la PRIMERA con texto y se
    # replica a todas las redes pedidas.
    salida = '```json\n{"piezas": [{"red": "x", "texto": "Hola", "copy_in": "T"}]}\n```'
    piezas = stream.parsear_salida_unificada(salida, ["x", "instagram"])["piezas"]
    assert [p["contenido"] for p in piezas] == ["Hola", "Hola"]
    assert [p["copy_in"] for p in piezas] == ["T", "T"]


def test_unificada_sin_json_cae_al_texto_limpio():
    # Sin bloque JSON, el copy es el texto limpio entero, replicado a todas las redes.
    piezas = stream.parsear_salida_unificada("Copy suelto sin json", ["x", "tiktok"])["piezas"]
    assert all(p["contenido"] == "Copy suelto sin json" for p in piezas)
    assert all(p["copy_in"] == "" for p in piezas)
