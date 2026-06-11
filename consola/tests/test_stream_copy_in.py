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


def test_unificada_contenido_conserva_emojis_y_copy_in_no():
    # Misma politica de emojis que `parsear_salida`: contenido tal cual, placa limpia.
    salida = '```json\n{"texto": "¡GOLAZO! 🔥⚽", "copy_in": "GOLAZO 🔥"}\n```'
    piezas = stream.parsear_salida_unificada(salida, ["x", "instagram"])["piezas"]
    assert all(p["contenido"] == "¡GOLAZO! 🔥⚽" for p in piezas)
    assert all(p["copy_in"] == "GOLAZO" for p in piezas)


def test_unificada_texto_corto_va_a_x_y_el_largo_a_ig_fb():
    # X (límite 280) recibe `texto_corto`; Instagram/Facebook reciben el copy COMPLETO.
    largo = "L" * 400  # supera el límite de X (280), no el de Instagram (2200)
    salida = '```json\n{"texto": "' + largo + '", "texto_corto": "Versión breve", "copy_in": "T"}\n```'
    piezas = stream.parsear_salida_unificada(salida, ["x", "instagram", "facebook"])["piezas"]
    por_red = {p["red"]: p["contenido"] for p in piezas}
    assert por_red["x"] == "Versión breve"
    assert por_red["instagram"] == largo
    assert por_red["facebook"] == largo
    # Todas comparten el mismo copy_in.
    assert all(p["copy_in"] == "T" for p in piezas)


def test_unificada_texto_corto_se_ignora_si_el_largo_cabe():
    # Si el copy completo cabe en X, NO se usa la versión corta (todas iguales).
    salida = '```json\n{"texto": "Cabe en X", "texto_corto": "Más corto aún", "copy_in": ""}\n```'
    piezas = stream.parsear_salida_unificada(salida, ["x", "instagram"])["piezas"]
    assert all(p["contenido"] == "Cabe en X" for p in piezas)


def test_unificada_sin_texto_corto_el_largo_no_se_trunca():
    # Sin `texto_corto`, X hereda el copy largo TAL CUAL (la validación de longitud lo cribará
    # después; el parser no trunca). Comportamiento previo intacto.
    largo = "L" * 400
    salida = '```json\n{"texto": "' + largo + '", "copy_in": ""}\n```'
    piezas = stream.parsear_salida_unificada(salida, ["x", "instagram"])["piezas"]
    assert all(p["contenido"] == largo for p in piezas)


# --------------------------------------------------------------------------- #
# Politica de emojis del parseo (vive en prompt + editorial, no en limpieza)   #
# --------------------------------------------------------------------------- #


def test_contenido_conserva_emojis_y_copy_in_no():
    # La politica de emojis vive en el prompt + editorial (Claro Sports los lleva):
    # el parser NO los borra del contenido. El copy_in (placa) va SIEMPRE limpio.
    salida = (
        "Doc\n\n```json\n"
        '{"piezas": [{"red": "instagram", "texto": "¡GOLAZO! 🔥⚽", "copy_in": "GOLAZO 🔥"}]}\n```'
    )
    pieza = stream.parsear_salida(salida, ["instagram"])["piezas"][0]
    assert pieza["contenido"] == "¡GOLAZO! 🔥⚽"
    assert pieza["caracteres"] == len("¡GOLAZO! 🔥⚽")
    assert pieza["copy_in"] == "GOLAZO"


def test_resultado_conserva_emojis():
    salida = "Resumen con emoji 🔥\n\n```json\n{\"piezas\": []}\n```"
    assert stream.parsear_salida(salida, ["x"])["resultado"] == "Resumen con emoji 🔥"
