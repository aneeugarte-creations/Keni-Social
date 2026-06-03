"""Tests de la lógica PURA de formato de imagen (`dominio.formato_imagen`).

Sin I/O ni Pillow: `formato_correcto` acepta una imagen si su aspecto es uno de los lienzos
CANÓNICOS de social (9:16, 4:5, 1:1, 16:9), independientemente de la red (el equipo cruza
formatos), con tolerancia; y rechaza aspectos raros (banners, thumbnails apaisados).
"""

from __future__ import annotations

import pytest

from keni_consola.dominio import formato_imagen as fi


@pytest.mark.parametrize(
    "ancho,alto",
    [
        (1080, 1920),  # 9:16 vertical
        (1080, 1350),  # 4:5  feed (lo que el equipo postea de hecho)
        (1080, 1080),  # 1:1  cuadrado
        (1600, 900),   # 16:9 horizontal
    ],
)
def test_acepta_cualquier_lienzo_canonico_en_cualquier_red(ancho, alto):
    # El mismo tamaño vale para CUALQUIER red: no se ata el formato a la red.
    for red in ("instagram", "facebook", "x", "tiktok", "youtube", "web"):
        assert fi.formato_correcto(red, ancho, alto) is True


def test_tolerancia_admite_pocos_pixeles_de_mas():
    assert fi.formato_correcto("instagram", 1086, 1350) is True   # ~0.804 ≈ 4:5
    assert fi.formato_correcto("x", 1280, 718) is True            # ~1.783 ≈ 16:9


def test_rechaza_aspectos_no_canonicos():
    assert fi.formato_correcto("facebook", 1200, 628) is False    # 1.91:1 (link card)
    assert fi.formato_correcto("instagram", 1080, 1500) is False  # 0.72, fuera de 4:5 y 1:1
    assert fi.formato_correcto("x", 1500, 500) is False           # 3:1 banner


def test_dimensiones_no_positivas_son_invalidas():
    assert fi.formato_correcto("instagram", 0, 1350) is False
    assert fi.formato_correcto("instagram", 1080, 0) is False
