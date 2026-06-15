"""Tests del vocabulario semilla por marca (`relevancia_marca`) — PUROS, sin DB ni red.

No fijan la lista palabra a palabra (es semilla editable), sino las PROPIEDADES que el
ranking y el listón necesitan: cobertura mínima por marca del piloto, normalización
(minúsculas, sin acentos) y desambiguación (nombres genéricos solo como frase).
"""

from __future__ import annotations

import unicodedata

from keni_consola import relevancia_marca
from keni_consola.dominio import agrupar

_MARCAS_PILOTO = ("unotv", "claro-sports", "nacion-gamer")


def test_marcas_del_piloto_tienen_vocabulario_amplio():
    """El listón exige encaje por vocabulario: una semilla raquítica mata el feed."""
    for marca in _MARCAS_PILOTO:
        assert len(relevancia_marca.palabras_de_marca(marca)) >= 80, marca


def test_vocabulario_normalizado_minusculas_sin_acentos():
    for marca in _MARCAS_PILOTO + ("piso-15", "fundacion"):
        for termino in relevancia_marca.palabras_de_marca(marca):
            assert termino == termino.lower(), termino
            sin_acentos = "".join(
                c for c in unicodedata.normalize("NFD", termino)
                if unicodedata.category(c) != "Mn"
            )
            assert termino == sin_acentos, termino


def test_sin_marca_o_desconocida_devuelve_vacio():
    assert relevancia_marca.palabras_de_marca(None) == frozenset()
    assert relevancia_marca.palabras_de_marca("") == frozenset()
    assert relevancia_marca.palabras_de_marca("no-existe") == frozenset()


def test_titulares_reales_casan_su_marca():
    """Titulares típicos de cada agenda puntúan relevancia > 0 con su propio vocabulario."""
    casos = {
        "unotv": "Sismo de 6.1 sacude la CDMX; activan protocolo de protección civil",
        "claro-sports": "Liga MX: América vence a Chivas en el clásico nacional",
        "nacion-gamer": "Nintendo anuncia nuevo Zelda para Switch en el Direct",
    }
    for marca, titulo in casos.items():
        pal = relevancia_marca.palabras_de_marca(marca)
        s = agrupar._relevancia_marca({"titulo": titulo, "resumen": ""}, pal)
        assert s > 0.0, (marca, titulo)


def test_nombres_genericos_solo_casan_como_frase():
    """'león'/'santos' a secas no son del vocabulario deportivo: solo su forma de club.

    Un cluster SIN marca se asigna por vocabulario: un token genérico arrastraría
    noticias de León (la ciudad) o de un santo a Claro Sports.
    """
    pal = relevancia_marca.palabras_de_marca("claro-sports")
    assert "leon" not in pal and "santos" not in pal
    assert "club leon" in pal and "santos laguna" in pal
    ciudad = agrupar._relevancia_marca(
        {"titulo": "Inauguran hospital en Leon, Guanajuato", "resumen": ""}, pal
    )
    club = agrupar._relevancia_marca(
        {"titulo": "Club Leon gana en la jornada 5", "resumen": ""}, pal
    )
    assert ciudad == 0.0
    assert club > 0.0
