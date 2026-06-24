"""Tests del catalogo UNICO de marcas. Solo datos puros; sin I/O ni red.

keni_shared es la fuente canonica: un solo catalogo con 5 marcas (el golf NO es
marca, es un sub-vertical editorial de Claro Sports), traduccion id canonico <->
id_metricas, y los helpers de la frontera con metricas. Los guards cruzados que
anclan consola/metricas/skills a este catalogo viven en sus respectivos paquetes.
"""

from __future__ import annotations

from keni_shared import marcas


def test_catalogo_unico_sin_duplicados():
    ids = marcas.ids()
    assert len(ids) == len(set(ids))
    assert ids == [
        "unotv",
        "claro-sports",
        "nacion-gamer",
        "piso-15",
        "fundacion",
    ]


def test_opciones_son_id_canonico_y_etiqueta_humana():
    opts = dict(marcas.opciones())
    assert opts["unotv"] == "UnoTV"
    assert opts["claro-sports"] == "Claro Sports"
    assert opts["nacion-gamer"] == "Nación Gamer"  # etiqueta con acentos
    assert opts["fundacion"] == "Fundación"


def test_golf_no_es_marca():
    assert not marcas.es_marca("claro-sports-golf")
    ids_opciones = [mid for mid, _ in marcas.opciones()]
    assert "claro-sports-golf" not in ids_opciones
    assert marcas.etiqueta_de("claro-sports-golf") == "claro-sports-golf"


def test_es_marca_distingue_id_canonico_de_id_metricas():
    assert marcas.es_marca("claro-sports")
    assert not marcas.es_marca("claro_sports")
    assert not marcas.es_marca("inexistente")


def test_traduccion_id_canonico_a_id_metricas():
    assert marcas.id_metricas_de("claro-sports") == "claro_sports"
    assert marcas.id_metricas_de("nacion-gamer") == "nacion_gamer"
    assert marcas.id_metricas_de("piso-15") == "piso_15"
    assert marcas.id_metricas_de("unotv") == "unotv"


def test_helpers_frontera_metricas():
    opts = dict(marcas.opciones_metricas())
    assert opts["claro_sports"] == "Claro Sports"
    assert "claro_sports_golf" not in opts
    assert "claro-sports" not in opts
    assert marcas.etiqueta_por_id_metricas("nacion_gamer") == "Nación Gamer"
    m = marcas.marca_por_id_metricas("piso_15")
    assert m is not None
    assert m.id == "piso-15"


def test_caidas_a_id_cuando_desconocido():
    assert marcas.etiqueta_de("zzz") == "zzz"
    assert marcas.etiqueta_por_id_metricas("zzz") == "zzz"
    assert marcas.id_metricas_de("zzz") == "zzz"
    assert marcas.marca_de("zzz") is None
    assert marcas.marca_por_id_metricas("zzz") is None


def test_tipo_separa_noticias_de_contenido_propio():
    # Las 3 del piloto que pasan por investigación vs las 2 de contenido propio.
    assert marcas.noticias() == ["unotv", "claro-sports", "nacion-gamer"]
    assert marcas.es_noticias("unotv")
    assert marcas.es_noticias("claro-sports")
    assert not marcas.es_noticias("piso-15")
    assert not marcas.es_noticias("fundacion")
    # `tipo` viaja en el catálogo.
    assert marcas.marca_de("unotv").tipo == "noticias"
    assert marcas.marca_de("piso-15").tipo == "propio"


def test_etiqueta_investigacion_por_marca():
    # El panel de investigación se llama "Noticias" por defecto, pero cada marca puede renombrarlo
    # (la Fundación lo llama "Curiosidades" en la semilla).
    assert marcas.marca_de("unotv").etiqueta_investigacion == "Noticias"
    assert marcas.marca_de("fundacion").etiqueta_investigacion == "Curiosidades"


def test_likes_aprobacion_por_marca():
    # Por defecto una pieza necesita 2 OK ("cuatro ojos"). La Fundación la opera una sola
    # persona, así que la semilla baja su umbral a 1 (un único OK la programa).
    assert marcas.likes_aprobacion_de("unotv") == 2
    assert marcas.likes_aprobacion_de("fundacion") == 1
    # Marca desconocida: cae al defecto razonable de 2.
    assert marcas.likes_aprobacion_de("zzz") == 2


def test_es_noticias_falso_para_marca_desconocida():
    assert not marcas.es_noticias("zzz")
