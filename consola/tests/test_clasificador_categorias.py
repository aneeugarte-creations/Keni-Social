"""Tests del clasificador de líneas/orígenes (funciones puras, sin BD)."""

from __future__ import annotations

from keni_consola.dominio import clasificador_categorias as cl


def _et(id_: str, keywords: str) -> dict[str, str]:
    return {"id": id_, "keywords": keywords}


CATEGORIAS = [
    _et("futbol", "futbol,gol,liga mx,el tri"),
    _et("beisbol", "beisbol,home run,mlb"),
    _et("f1", "formula 1,gran premio,checo perez"),
]


def test_clasifica_por_keyword_simple():
    assert cl.clasificar("Gran gol del Tri en la Liga MX", CATEGORIAS) == "futbol"
    assert cl.clasificar("Home run decisivo en la MLB", CATEGORIAS) == "beisbol"


def test_insensible_a_acentos_y_mayusculas():
    # 'Fórmula 1' / 'Pérez' con acentos y mayúsculas deben casar 'formula 1' / 'checo perez'
    assert cl.clasificar("FÓRMULA 1: Checo Pérez sube al podio", CATEGORIAS) == "f1"


def test_sin_match_devuelve_none():
    assert cl.clasificar("Noticia de política internacional", CATEGORIAS) is None
    assert cl.clasificar("", CATEGORIAS) is None


def test_gana_la_de_mas_coincidencias():
    texto = "Gol y otro gol: la Liga MX y el Tri encienden el futbol"  # 4 de 'futbol'
    assert cl.clasificar(texto, CATEGORIAS) == "futbol"


def test_limite_de_palabra_evita_falsos_positivos():
    # 'gol' no debe casar dentro de 'golfista' (límite de palabra)
    solo_gol = [_et("futbol", "gol")]
    assert cl.clasificar("El golfista ganó el torneo", solo_gol) is None


def test_origen_por_defecto_es_el_sin_keywords():
    origenes = [
        _et("interno", ""),
        _et("externa", "presidencia,comercial"),
    ]
    assert cl.origen_por_defecto(origenes) == "interno"


def test_origen_por_defecto_vacio():
    assert cl.origen_por_defecto([]) is None


def test_contar_coincidencias():
    et = _et("futbol", "futbol,gol,liga mx")
    assert cl.contar_coincidencias("gol en la liga mx, gran futbol", et) == 3
    assert cl.contar_coincidencias("nada que ver", et) == 0
