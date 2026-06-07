"""Tests de los helpers PUROS de similitud (extraídos del antiguo Radar v1).

Antes vivían en `keni_consola.radar` (retirado); ahora en `dominio.similitud`, donde
los reutiliza el clustering del pool. Cubre normalización, sin-acentos y clave fuzzy
con sinónimos.
"""

from __future__ import annotations

from keni_consola.dominio import similitud as sim


def test_normalizar_clave_minusculas_sin_signos():
    assert sim.normalizar_clave("  ¡Gol, GOL!  ") == "gol gol"


def test_sin_acentos():
    assert sim.sin_acentos("Selección México") == "Seleccion Mexico"


def test_clave_fuzzy_colapsa_sinonimos():
    # "el Tri" y "Selección Mexicana" comparten clave fuzzy.
    assert sim.clave_fuzzy("el Tri") == sim.clave_fuzzy("seleccion mexicana")


def test_clave_fuzzy_cdmx_variantes():
    base = sim.clave_fuzzy("partido en CDMX")
    assert base == sim.clave_fuzzy("partido en ciudad de mexico")
    assert base == sim.clave_fuzzy("partido en DF")


def test_clave_fuzzy_determinista_y_sin_acentos():
    assert sim.clave_fuzzy("Fútbol VS Rival") == sim.clave_fuzzy("futbol versus rival")
