"""Tests de la fuente unica de limites de caracteres por plataforma."""

from __future__ import annotations

from keni_shared import limites_plataforma


def test_tabla_canonica_tiene_las_cinco_redes_en_orden():
    assert list(limites_plataforma.LIMITES) == ["x", "instagram", "facebook", "tiktok", "youtube"]


def test_valores_canonicos():
    assert limites_plataforma.LIMITES == {
        "x": 25000,  # X Premium
        "instagram": 2200,
        "facebook": None,
        "tiktok": 4000,  # maximo tecnico del caption
        "youtube": None,
    }


def test_limite_de():
    assert limites_plataforma.limite_de("x") == 25000
    assert limites_plataforma.limite_de("tiktok") == 4000
    assert limites_plataforma.limite_de("facebook") is None
    # red desconocida -> None (defensivo: no inventamos un tope)
    assert limites_plataforma.limite_de("threads") is None


def test_como_lista_respeta_orden():
    lista = limites_plataforma.como_lista()
    assert [r["id"] for r in lista] == ["x", "instagram", "facebook", "tiktok", "youtube"]
    assert lista[0] == {"id": "x", "limite": 25000}


def test_video_specs_cubren_las_cinco_redes_en_orden():
    assert list(limites_plataforma.VIDEO_SPECS) == [
        "x", "instagram", "facebook", "tiktok", "youtube"
    ]


def test_video_specs_de():
    spec = limites_plataforma.video_specs_de("tiktok")
    assert spec is not None
    # Specs INFORMATIVAS: deben traer los tres campos basicos.
    assert set(spec) == {"duracion_s", "max_mb", "aspecto"}
    # red desconocida -> None (defensivo, igual que los limites de caracteres).
    assert limites_plataforma.video_specs_de("threads") is None


def test_video_specs_como_lista_respeta_orden():
    lista = limites_plataforma.video_specs_como_lista()
    assert [r["id"] for r in lista] == ["x", "instagram", "facebook", "tiktok", "youtube"]
    assert lista[0]["id"] == "x"
    assert "aspecto" in lista[0]
