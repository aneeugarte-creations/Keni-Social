"""Tests de la fuente unica de limites de caracteres por plataforma (H3/E1)."""

from __future__ import annotations

from keni_shared import limites_plataforma


def test_tabla_canonica_tiene_las_cinco_redes_en_orden():
    assert list(limites_plataforma.LIMITES) == ["x", "instagram", "facebook", "tiktok", "youtube"]


def test_valores_canonicos():
    assert limites_plataforma.LIMITES == {
        "x": 280,
        "instagram": 2200,
        "facebook": None,
        "tiktok": 4000,  # caption ampliado 2023-24 (#112)
        "youtube": None,
    }


def test_limite_de():
    assert limites_plataforma.limite_de("x") == 280
    assert limites_plataforma.limite_de("tiktok") == 4000
    assert limites_plataforma.limite_de("facebook") is None
    # red desconocida -> None (defensivo: no inventamos un tope)
    assert limites_plataforma.limite_de("threads") is None


def test_como_lista_respeta_orden():
    lista = limites_plataforma.como_lista()
    assert [r["id"] for r in lista] == ["x", "instagram", "facebook", "tiktok", "youtube"]
    assert lista[0] == {"id": "x", "limite": 280}
