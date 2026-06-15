"""Tests del catalogo UNICO de marcas (#82 · H3/E1). Solo datos puros; sin I/O ni red.

Cubre: un solo catalogo (no dos) con 5 marcas (el golf NO es marca, es un
sub-vertical editorial de Claro Sports), traduccion id canonico <-> id_metricas,
y los helpers de la frontera con metricas.

FUENTE UNICA (H3/E1): el catalogo canonico vive en `keni_shared.marcas`;
`keni_consola.marcas` lo REEXPORTA y `keni_metricas` tambien lo importa.
Estos tests verifican via el reexport de la consola (que es como lo usa su codigo)
y que la fuente es UNICA de verdad: un cambio en keni_shared se ve en consola y
en keni_metricas sin tocar espejos.
"""

from __future__ import annotations

from keni_consola import marcas


def test_catalogo_unico_sin_duplicados():
    # UN solo catalogo: cada marca aparece una vez, con id canonico unico.
    ids = marcas.ids()
    assert len(ids) == len(set(ids))
    # El orden de presentacion es estable y conocido (slug-guion como id canonico).
    # Son 5 marcas: el golf NO es marca de primer nivel.
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
    # El golf NO es una marca de primer nivel: es un sub-vertical editorial de
    # Claro Sports. No esta en el catalogo ni en las opciones.
    assert not marcas.es_marca("claro-sports-golf")
    ids_opciones = [mid for mid, _ in marcas.opciones()]
    assert "claro-sports-golf" not in ids_opciones
    # Helper tolerante: id desconocido cae al propio id (no rompe la UI).
    assert marcas.etiqueta_de("claro-sports-golf") == "claro-sports-golf"


def test_es_marca_distingue_id_canonico_de_id_metricas():
    # El id canonico es valido; la forma id_metricas (guion_bajo) NO lo es.
    assert marcas.es_marca("claro-sports")
    assert not marcas.es_marca("claro_sports")
    assert not marcas.es_marca("inexistente")


def test_traduccion_id_canonico_a_id_metricas():
    # La frontera con metricas: id canonico -> id_metricas (guion_bajo).
    assert marcas.id_metricas_de("claro-sports") == "claro_sports"
    assert marcas.id_metricas_de("nacion-gamer") == "nacion_gamer"
    assert marcas.id_metricas_de("piso-15") == "piso_15"
    assert marcas.id_metricas_de("unotv") == "unotv"


def test_id_metricas_cubre_toda_la_fuente_muestra():
    # Todos los ids de la fuente "muestra" de keni_metricas tienen su marca aqui.
    esperados = {
        "unotv",
        "claro_sports",
        "nacion_gamer",
        "piso_15",
        "fundacion",
    }
    assert {m.id_metricas for m in marcas.MARCAS} == esperados


def test_helpers_frontera_metricas():
    # opciones_metricas devuelve (id_metricas, etiqueta), no el id canonico.
    opts = dict(marcas.opciones_metricas())
    assert opts["claro_sports"] == "Claro Sports"
    assert "claro_sports_golf" not in opts  # golf NO es marca
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


# --------------------------------------------------------------------------- #
# H3/E1: la fuente es UNICA e IMPORTABLE (keni_shared), no espejada.            #
# --------------------------------------------------------------------------- #


def test_la_fuente_es_keni_shared_no_un_espejo():
    # `keni_consola.marcas` REEXPORTA `keni_shared.marcas`: es el MISMO objeto, no
    # una copia. Un cambio en keni_shared se refleja en la consola sin tocar nada.
    from keni_shared import marcas as ks_marcas

    assert marcas.MARCAS is ks_marcas.MARCAS
    assert marcas.id_metricas_de is ks_marcas.id_metricas_de


def test_metricas_deriva_de_la_misma_fuente_unica():
    # keni_metricas (muestra) DERIVA sus ids del catalogo de keni_shared, no de un
    # espejo: el conjunto coincide exactamente con el catalogo canonico.
    from keni_metricas.fuentes.muestra import IDS_METRICAS_MARCAS
    from keni_shared import marcas as ks_marcas

    assert IDS_METRICAS_MARCAS == {m.id_metricas for m in ks_marcas.MARCAS}


# --------------------------------------------------------------------------- #
# #102: identidad UNICA de marca cruzando consola <-> metricas <-> skills       #
# --------------------------------------------------------------------------- #
#
# Estos guards convierten "copias independientes que pueden divergir" en
# "referencias verificadas": si alguien renombra/anade una marca en muestra.py,
# marcas.json o las fichas sin tocar el catalogo canonico, el CI lo caza.


def test_muestra_de_metricas_usa_los_mismos_id_metricas():
    # keni_metricas es dependencia de la consola en CI: se puede importar.
    from keni_metricas.fuentes.muestra import (
        IDS_CUENTAS_HERMANAS,
        IDS_METRICAS_MARCAS,
    )

    canonicos = {m.id_metricas for m in marcas.MARCAS}
    # Las marcas editoriales de la muestra son EXACTAMENTE las del catalogo unico.
    assert IDS_METRICAS_MARCAS == canonicos
    # Las cuentas hermanas de Claro Sports NO son marcas del catalogo.
    assert not (IDS_CUENTAS_HERMANAS & canonicos)
