"""Tests del catalogo UNICO de marcas (#82). Solo datos puros; sin I/O ni red.

Cubre: un solo catalogo (no dos), golf visible con id canonico, traduccion
id canonico <-> id_metricas, y los helpers de la frontera con metricas.
"""

from __future__ import annotations

from keni_consola import marcas


def test_catalogo_unico_sin_duplicados():
    # UN solo catalogo: cada marca aparece una vez, con id canonico unico.
    ids = marcas.ids()
    assert len(ids) == len(set(ids))
    # El orden de presentacion es estable y conocido (slug-guion como id canonico).
    assert ids == [
        "unotv",
        "claro-sports",
        "claro-sports-golf",
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


def test_golf_es_marca_visible():
    # Golf YA es una marca de pleno derecho con id canonico (antes invisible).
    assert marcas.es_marca("claro-sports-golf")
    assert ("claro-sports-golf", "Claro Sports Golf") in marcas.opciones()
    assert marcas.etiqueta_de("claro-sports-golf") == "Claro Sports Golf"


def test_es_marca_distingue_id_canonico_de_id_metricas():
    # El id canonico es valido; la forma id_metricas (guion_bajo) NO lo es.
    assert marcas.es_marca("claro-sports")
    assert not marcas.es_marca("claro_sports")
    assert not marcas.es_marca("inexistente")


def test_traduccion_id_canonico_a_id_metricas():
    # La frontera con metricas: id canonico -> id_metricas (guion_bajo).
    assert marcas.id_metricas_de("claro-sports") == "claro_sports"
    assert marcas.id_metricas_de("claro-sports-golf") == "claro_sports_golf"
    assert marcas.id_metricas_de("nacion-gamer") == "nacion_gamer"
    assert marcas.id_metricas_de("piso-15") == "piso_15"
    assert marcas.id_metricas_de("unotv") == "unotv"


def test_id_metricas_cubre_toda_la_fuente_muestra():
    # Todos los ids de la fuente "muestra" de keni_metricas tienen su marca aqui.
    esperados = {
        "unotv",
        "claro_sports",
        "claro_sports_golf",
        "nacion_gamer",
        "piso_15",
        "fundacion",
    }
    assert {m.id_metricas for m in marcas.MARCAS} == esperados


def test_helpers_frontera_metricas():
    # opciones_metricas devuelve (id_metricas, etiqueta), no el id canonico.
    opts = dict(marcas.opciones_metricas())
    assert opts["claro_sports"] == "Claro Sports"
    assert opts["claro_sports_golf"] == "Claro Sports Golf"
    assert "claro-sports" not in opts  # nunca el id canonico en esta frontera
    # Resolucion de etiqueta y de Marca por id_metricas.
    assert marcas.etiqueta_por_id_metricas("nacion_gamer") == "Nación Gamer"
    m = marcas.marca_por_id_metricas("piso_15")
    assert m is not None
    assert m.id == "piso-15"  # devuelve la Marca, cuyo id es el canonico


def test_caidas_a_id_cuando_desconocido():
    # Helpers tolerantes: id desconocido cae al propio id (no rompen la UI).
    assert marcas.etiqueta_de("zzz") == "zzz"
    assert marcas.etiqueta_por_id_metricas("zzz") == "zzz"
    assert marcas.id_metricas_de("zzz") == "zzz"
    assert marcas.marca_de("zzz") is None
    assert marcas.marca_por_id_metricas("zzz") is None
