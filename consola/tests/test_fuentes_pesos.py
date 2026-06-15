"""Tests PUROS del peso editorial de fuentes (`dominio.fuentes_pesos`). Sin red ni BD.

El peso pondera la corroboración del ranking de historias: potente (2.0) / normal (1.0) /
baja (0.5). Cubre el tier derivado, el seed por host (con subdominios) y la normalización.
"""

from __future__ import annotations

import pytest

from keni_consola.dominio import fuentes_pesos


# --------------------------------------------------------------------------- #
# tier_de_peso                                                                  #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("peso", "tier"),
    [
        (2.0, "potente"),
        (1.5, "potente"),
        (3.0, "potente"),
        (1.0, "normal"),
        (1.4, "normal"),
        (0.7, "normal"),
        (0.6, "baja"),
        (0.5, "baja"),
        (0.1, "baja"),
    ],
)
def test_tier_de_peso_umbrales(peso, tier):
    assert fuentes_pesos.tier_de_peso(peso) == tier


def test_tier_de_peso_no_numerico_cae_a_normal():
    assert fuentes_pesos.tier_de_peso("x") == "normal"  # type: ignore[arg-type]
    assert fuentes_pesos.tier_de_peso(None) == "normal"  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# peso_de_url (seed por host)                                                   #
# --------------------------------------------------------------------------- #


def test_peso_de_url_host_potente():
    assert fuentes_pesos.peso_de_url("https://www.reuters.com/world/x") == fuentes_pesos.PESO_POTENTE
    assert fuentes_pesos.peso_de_url("https://bbc.com/mundo") == fuentes_pesos.PESO_POTENTE


def test_peso_de_url_subdominio_casa_con_el_host_inicial():
    # `feeds.bbc.co.uk` debe casar con la inicial `bbc.co.uk`.
    assert fuentes_pesos.peso_de_url("https://feeds.bbc.co.uk/news/rss.xml") == fuentes_pesos.PESO_POTENTE


def test_peso_de_url_no_casa_por_sufijo_parcial():
    # `notbbc.com` NO es subdominio de `bbc.com`: no debe heredar su peso.
    assert fuentes_pesos.peso_de_url("https://notbbc.com/feed") == fuentes_pesos.PESO_NORMAL


def test_peso_de_url_host_desconocido_es_normal():
    assert fuentes_pesos.peso_de_url("https://blogdesconocido.mx/rss") == fuentes_pesos.PESO_NORMAL


def test_peso_de_url_invalida_o_vacia_es_normal():
    assert fuentes_pesos.peso_de_url("") == fuentes_pesos.PESO_NORMAL
    assert fuentes_pesos.peso_de_url("ftp://reuters.com/x") == fuentes_pesos.PESO_NORMAL


# --------------------------------------------------------------------------- #
# normalizar_peso                                                               #
# --------------------------------------------------------------------------- #


def test_normalizar_peso_clampa_al_rango():
    assert fuentes_pesos.normalizar_peso(99) == fuentes_pesos.PESO_MAX
    assert fuentes_pesos.normalizar_peso(0) == fuentes_pesos.PESO_MIN
    assert fuentes_pesos.normalizar_peso(1.3) == 1.3


def test_normalizar_peso_no_numerico_cae_a_normal():
    assert fuentes_pesos.normalizar_peso("x") == fuentes_pesos.PESO_NORMAL  # type: ignore[arg-type]
    assert fuentes_pesos.normalizar_peso(None) == fuentes_pesos.PESO_NORMAL  # type: ignore[arg-type]
