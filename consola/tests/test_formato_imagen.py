"""Tests de la lógica PURA de formato de imagen (`dominio.formato_imagen`).

Sin I/O ni Pillow: comprueba que `formato_correcto` acepta un aspecto solo si encaja en algún
lienzo que la red admite (matriz `formatos_red`), con tolerancia, y rechaza el resto.
"""

from __future__ import annotations

from keni_consola.dominio import formato_imagen as fi


def test_instagram_acepta_feed_4x5_y_reel_9x16():
    # Instagram admite feed (4:5) y vertical (9:16).
    assert fi.formato_correcto("instagram", 1080, 1350) is True   # 4:5
    assert fi.formato_correcto("instagram", 1080, 1920) is True   # 9:16
    # 1:1 NO está entre los lienzos de instagram -> rechazado.
    assert fi.formato_correcto("instagram", 1080, 1080) is False


def test_x_solo_acepta_horizontal_16x9():
    assert fi.formato_correcto("x", 1600, 900) is True            # 16:9
    assert fi.formato_correcto("x", 1080, 1350) is False          # 4:5 no vale en X


def test_tiktok_solo_vertical():
    assert fi.formato_correcto("tiktok", 1080, 1920) is True      # 9:16
    assert fi.formato_correcto("tiktok", 1080, 1080) is False     # 1:1 no


def test_tolerancia_admite_pocos_pixeles_de_mas():
    # 1086x1350 ~ 0.804, dentro del 6% de 0.8 (4:5): pasa.
    assert fi.formato_correcto("instagram", 1086, 1350) is True
    # 1080x1500 ~ 0.72, fuera del 6% de 0.8 y de 0.5625: no pasa.
    assert fi.formato_correcto("instagram", 1080, 1500) is False


def test_red_sin_matriz_no_exige_formato():
    # `web` no está en la matriz de formatos: cualquier imagen vale.
    assert fi.formato_correcto("web", 800, 173) is True
    assert fi.formato_correcto("desconocida", 123, 456) is True


def test_dimensiones_no_positivas_son_invalidas():
    assert fi.formato_correcto("instagram", 0, 1350) is False
    assert fi.formato_correcto("instagram", 1080, 0) is False
