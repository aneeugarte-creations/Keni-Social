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


def test_unificada_texto_corto_va_a_la_red_estrecha_y_el_largo_a_las_anchas():
    # La red cuyo tope NO admite el largo recibe `texto_corto`; las más anchas, el copy COMPLETO.
    # Un copy >2200 se condensa solo para Instagram (2200); X (25000) y Facebook (sin tope) usan el largo.
    largo = "L" * 2300  # supera el límite de Instagram (2200), no el de X (25000) ni Facebook
    salida = '```json\n{"texto": "' + largo + '", "texto_corto": "Versión breve", "copy_in": "T"}\n```'
    piezas = stream.parsear_salida_unificada(salida, ["x", "instagram", "facebook"])["piezas"]
    por_red = {p["red"]: p["contenido"] for p in piezas}
    assert por_red["instagram"] == "Versión breve"
    assert por_red["x"] == largo
    assert por_red["facebook"] == largo
    # Todas comparten el mismo copy_in.
    assert all(p["copy_in"] == "T" for p in piezas)


def test_unificada_texto_corto_se_ignora_si_el_largo_cabe():
    # Si el copy completo cabe en X, NO se usa la versión corta (todas iguales).
    salida = '```json\n{"texto": "Cabe en X", "texto_corto": "Más corto aún", "copy_in": ""}\n```'
    piezas = stream.parsear_salida_unificada(salida, ["x", "instagram"])["piezas"]
    assert all(p["contenido"] == "Cabe en X" for p in piezas)


def test_unificada_sin_texto_corto_el_largo_no_se_trunca():
    # Sin `texto_corto`, todas las redes heredan el copy largo TAL CUAL (el parser no trunca; si
    # alguna lo excediera, lo cribaría después la validación de longitud). Comportamiento previo intacto.
    largo = "L" * 400
    salida = '```json\n{"texto": "' + largo + '", "copy_in": ""}\n```'
    piezas = stream.parsear_salida_unificada(salida, ["x", "instagram"])["piezas"]
    assert all(p["contenido"] == largo for p in piezas)


def test_unificada_tipo_carrusel_se_lee_del_json():
    # DOS tipos de output (pipeline): el modelo declara `tipo` y el parser lo expone.
    salida = '```json\n{"texto": "Copy", "copy_in": "T", "tipo": "carrusel"}\n```'
    assert stream.parsear_salida_unificada(salida, ["x"])["tipo"] == "carrusel"


def test_unificada_tipo_defecto_es_post():
    # Sin `tipo` (o sin JSON), el output es un post normal: nunca un carrusel por accidente.
    salida = '```json\n{"texto": "Copy", "copy_in": ""}\n```'
    assert stream.parsear_salida_unificada(salida, ["x"])["tipo"] == "post"
    assert stream.parsear_salida_unificada("Texto suelto sin json", ["x"])["tipo"] == "post"


def test_unificada_tipo_desconocido_cae_a_post():
    # Par CERRADO post|carrusel: cualquier otro valor (o tipo no-string) cae a "post".
    salida = '```json\n{"texto": "Copy", "copy_in": "", "tipo": "video"}\n```'
    assert stream.parsear_salida_unificada(salida, ["x"])["tipo"] == "post"
    salida2 = '```json\n{"texto": "Copy", "copy_in": "", "tipo": 3}\n```'
    assert stream.parsear_salida_unificada(salida2, ["x"])["tipo"] == "post"


def test_unificada_slides_se_sanean_y_exponen():
    # Carrusel EDITORIAL: cada slide trae su titular (texto de placa, sin emojis) y el
    # NÚMERO de la foto del catálogo (0 = sin foto). Valores raros se sanean.
    salida = (
        '```json\n{"texto": "Copy", "copy_in": "PANEL", "tipo": "carrusel", '
        '"slides": ['
        '{"titular": "Concierto A 🔥", "foto": 1}, '
        '{"titular": "Concierto B", "foto": 0}, '
        '{"titular": "Concierto C", "foto": "dos"}, '
        '{"titular": "   ", "foto": 2}, '
        '{"titular": "Concierto D", "foto": -3}]}\n```'
    )
    res = stream.parsear_salida_unificada(salida, ["x"])
    assert res["tipo"] == "carrusel"
    # El slide sin titular útil se omite; emojis fuera (es texto de placa); fotos raras -> 0.
    assert res["slides"] == [
        {"titular": "Concierto A", "foto": 1},
        {"titular": "Concierto B", "foto": 0},
        {"titular": "Concierto C", "foto": 0},
        {"titular": "Concierto D", "foto": 0},
    ]


def test_unificada_slides_vacios_con_tipo_post():
    # Con tipo=post los slides NO se exponen aunque el modelo los emita por error.
    salida = (
        '```json\n{"texto": "Copy", "copy_in": "", "tipo": "post", '
        '"slides": [{"titular": "X", "foto": 1}]}\n```'
    )
    res = stream.parsear_salida_unificada(salida, ["x"])
    assert res["tipo"] == "post"
    assert res["slides"] == []


def test_unificada_slides_respetan_el_tope():
    # Tope de 9 slides (10 nativas de IG/FB menos la portada).
    slides = ", ".join(f'{{"titular": "Nota {i}", "foto": 0}}' for i in range(12))
    salida = (
        '```json\n{"texto": "Copy", "copy_in": "P", "tipo": "carrusel", '
        f'"slides": [{slides}]}}\n```'
    )
    assert len(stream.parsear_salida_unificada(salida, ["x"])["slides"]) == 9


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


# --------------------------------------------------------------------------- #
# Reparación tolerante: comillas SIN ESCAPAR dentro de un valor (cita textual)  #
# --------------------------------------------------------------------------- #


def test_unificada_repara_comillas_sin_escapar_en_texto():
    # El modelo dejó la cita «"Los mexicanos..."» SIN escapar -> json.loads falla. El parser la
    # RECUPERA: copy_in correcto y contenido = el `texto` (con su cita), no la salida cruda.
    salida = (
        "REVISAR ANTES DE PUBLICAR\n\nAuto-verificación: bla.\n\n```json\n"
        '{"texto": "Salma tomó el centro. Expresó orgullo. "Los mexicanos estamos honrados", '
        'declaró Hayek, según Infobae.", "copy_in": "SALMA EN LA INAUGURACIÓN"}\n```'
    )
    pieza = stream.parsear_salida_unificada(salida, ["instagram"])["piezas"][0]
    assert pieza["copy_in"] == "SALMA EN LA INAUGURACIÓN"
    assert pieza["contenido"].startswith("Salma tomó el centro.")
    assert '"Los mexicanos estamos honrados"' in pieza["contenido"]
    # NO se vuelca la salida cruda (preámbulo/auto-verificación) al caption.
    assert "REVISAR ANTES DE PUBLICAR" not in pieza["contenido"]
    assert "```json" not in pieza["contenido"]


def test_unificada_repara_con_texto_corto_y_recupera_todas_las_claves():
    salida = (
        '```json\n{"texto": "Largo con "comillas" internas aquí.", '
        '"texto_corto": "Corto "citado" también.", "copy_in": "PLACA"}\n```'
    )
    res = stream.parsear_salida_unificada(salida, ["instagram", "x"])
    ig = next(p for p in res["piezas"] if p["red"] == "instagram")
    assert ig["copy_in"] == "PLACA"
    assert ig["contenido"] == 'Largo con "comillas" internas aquí.'


def test_unificada_reparada_no_arma_carrusel_por_accidente():
    # Aunque el JSON roto trajera `tipo: carrusel`, la reparación NO recupera slides: degrada a post.
    salida = (
        '```json\n{"texto": "Copy con "cita" rota.", "copy_in": "T", "tipo": "carrusel", '
        '"slides": [{"titular": "A", "foto": 1}]}\n```'
    )
    res = stream.parsear_salida_unificada(salida, ["instagram"])
    assert res["piezas"][0]["contenido"] == 'Copy con "cita" rota.'
    # Sin slides recuperables, no se arma carrusel (tipo se recupera pero slides queda vacío).
    assert res["slides"] == []


def test_unificada_irreparable_cae_al_texto_plano():
    # Un bloque json sin `texto` recuperable conserva el fallback de siempre (texto limpio entero).
    salida = "Contenido plano útil.\n\n```json\n{roto sin comillas ni texto}\n```"
    pieza = stream.parsear_salida_unificada(salida, ["x"])["piezas"][0]
    assert "Contenido plano útil." in pieza["contenido"]
    assert pieza["copy_in"] == ""
