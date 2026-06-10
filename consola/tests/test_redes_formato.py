"""Tests del mapeo FORMATO -> REDES (`redes.redes_de_formato`). PURO: sin red ni BD.

Regla del dueño: una pieza FOTO va a 3 redes (instagram, x, facebook), una pieza VIDEO
a las 5 (instagram, x, facebook, tiktok, youtube) y una pieza CARRUSEL a 2 (instagram,
facebook: las que publican carruseles nativos via Metricool). El flujo automático crea
piezas FOTO; los otros mapeos quedan definidos aquí como fuente única.
"""

from __future__ import annotations

from keni_consola import redes


def test_foto_son_tres_redes():
    """FOTO -> exactamente instagram, x, facebook (en el orden de `REDES`)."""
    assert redes.redes_de_formato(redes.FORMATO_FOTO) == ("x", "instagram", "facebook")


def test_video_son_las_cinco_redes():
    """VIDEO -> las 5 redes canónicas, en el orden de `REDES`."""
    assert redes.redes_de_formato(redes.FORMATO_VIDEO) == (
        "x",
        "instagram",
        "facebook",
        "tiktok",
        "youtube",
    )


def test_foto_es_subconjunto_de_video():
    """FOTO ⊂ VIDEO: las 3 de foto están en las 5 de video."""
    foto = set(redes.redes_de_formato("foto"))
    video = set(redes.redes_de_formato("video"))
    assert foto < video


def test_carrusel_son_instagram_y_facebook():
    """CARRUSEL -> exactamente instagram y facebook (carruseles nativos), en orden de `REDES`."""
    assert redes.redes_de_formato(redes.FORMATO_CARRUSEL) == ("instagram", "facebook")


def test_carrusel_es_subconjunto_de_foto():
    """CARRUSEL ⊂ FOTO: las 2 de carrusel están en las 3 de foto (comparten portada)."""
    assert set(redes.redes_de_formato("carrusel")) < set(redes.redes_de_formato("foto"))


def test_desconocido_y_vacio_caen_a_foto():
    """Vacío / None / formato desconocido -> FOTO (3 redes): default seguro."""
    esperado = redes.redes_de_formato(redes.FORMATO_FOTO)
    assert redes.redes_de_formato("") == esperado
    assert redes.redes_de_formato(None) == esperado
    assert redes.redes_de_formato("collage") == esperado
    assert redes.redes_de_formato("VIDEO ") == redes.redes_de_formato("video")  # normaliza


def test_solo_devuelve_redes_canonicas():
    """Toda red devuelta es una red conocida (`es_red`): el mapeo filtra el catálogo."""
    for fmt in (redes.FORMATO_FOTO, redes.FORMATO_VIDEO, redes.FORMATO_CARRUSEL):
        for r in redes.redes_de_formato(fmt):
            assert redes.es_red(r)


def test_normalizar_formato():
    """`normalizar_formato`: minúsculas + trim; desconocido/vacío -> 'foto'."""
    assert redes.normalizar_formato("Foto") == "foto"
    assert redes.normalizar_formato(" video ") == "video"
    assert redes.normalizar_formato(" Carrusel ") == "carrusel"
    assert redes.normalizar_formato("") == "foto"
    assert redes.normalizar_formato(None) == "foto"
    assert redes.normalizar_formato("nope") == "foto"


def test_etiqueta_formato():
    """`etiqueta_formato`: etiqueta humana para la UI; desconocido -> 'Foto'."""
    assert redes.etiqueta_formato("foto") == "Foto"
    assert redes.etiqueta_formato("video") == "Video"
    assert redes.etiqueta_formato("carrusel") == "Carrusel"
    assert redes.etiqueta_formato("") == "Foto"
    assert redes.etiqueta_formato("otro") == "Foto"
