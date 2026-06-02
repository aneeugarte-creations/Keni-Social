"""Tests de la matriz `red -> formatos de imagen` (Fase 3). PURO: sin red, BD ni Pillow."""

from __future__ import annotations

from keni_consola import formatos_red, redes
from keni_consola.dominio import estudio_imagen


def test_claves_de_lienzo_coinciden_con_el_motor():
    """Las claves de lienzo de la matriz son EXACTAMENTE las del Estudio (misma identidad)."""
    assert set(formatos_red.LIENZOS) == set(estudio_imagen.FORMATOS)
    # Y el aspecto de cada lienzo coincide con el del dominio (no se redefine la verdad).
    for k, aspecto in formatos_red.ASPECTOS.items():
        assert aspecto == estudio_imagen.ASPECTOS[k]


def test_matriz_cubre_las_redes_canonicas():
    """Toda red de la matriz es una red canonica conocida (`redes.es_red`)."""
    for red in formatos_red.MATRIZ:
        assert redes.es_red(red), f"red desconocida en la matriz: {red}"


def test_instagram_tiene_feed_y_vertical():
    lienzos = formatos_red.lienzos_de("instagram")
    assert "feed" in lienzos  # post 4:5
    assert "vertical" in lienzos  # reel 9:16


def test_x_es_horizontal():
    assert formatos_red.lienzos_de("x") == ["horizontal"]  # 16:9


def test_tiktok_y_youtube_son_verticales():
    assert formatos_red.lienzos_de("tiktok") == ["vertical"]
    assert formatos_red.lienzos_de("youtube") == ["vertical"]


def test_lienzos_de_red_desconocida_es_vacio():
    assert formatos_red.lienzos_de("myspace") == []


def test_lienzos_de_sin_duplicados_y_en_orden():
    """Una red que repite lienzo entre tipos lo lista una sola vez, en orden de aparicion."""
    lienzos = formatos_red.lienzos_de("instagram")
    assert lienzos == ["feed", "vertical"]  # post (feed) antes que reel (vertical)
    assert len(lienzos) == len(set(lienzos))


def test_lienzos_canonicos_son_los_tres_o_cuatro_que_cubren_todo():
    """El set MAXIMO son los lienzos distintos usados por alguna red (3-4 canonicos)."""
    canon = formatos_red.lienzos_canonicos()
    assert set(canon) == {"feed", "vertical", "cuadrado", "horizontal"}
    # En orden de `LIENZOS`.
    assert canon == [k for k in formatos_red.LIENZOS if k in set(canon)]


def test_redes_que_usan_vertical():
    """Reel/short/tiktok: IG, FB, TikTok y YouTube usan el lienzo vertical 9:16."""
    redes_vert = formatos_red.redes_que_usan("vertical")
    assert "instagram" in redes_vert
    assert "tiktok" in redes_vert
    assert "youtube" in redes_vert
    assert "facebook" in redes_vert
    assert "x" not in redes_vert  # X solo horizontal


def test_como_lista_serializa_para_la_ui():
    data = formatos_red.como_lista()
    assert any(r["red"] == "instagram" for r in data)
    ig = next(r for r in data if r["red"] == "instagram")
    tipos = {f["tipo"] for f in ig["formatos"]}
    assert {"post", "reel"} <= tipos
    feed = next(f for f in ig["formatos"] if f["lienzo"] == "feed")
    assert feed["aspecto"] == "4:5"
    assert "x" in feed["tamano"]  # "AxB"


def test_formatosalida_propiedades():
    f = formatos_red.formatos_de("x")[0]
    assert f.tipo == "post"
    assert f.lienzo == "horizontal"
    assert f.aspecto == "16:9"
    assert f.tamano == formatos_red.LIENZOS["horizontal"]


def test_es_lienzo():
    assert formatos_red.es_lienzo("feed")
    assert not formatos_red.es_lienzo("panoramico")
