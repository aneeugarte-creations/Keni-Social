"""Biblioteca de hashtags por marca (`keni_consola.hashtags_biblioteca`).

El POOL de candidatos de la etapa `sugerir_hashtags`, sacado del historial (umbral >= 20 usos).
Tests PUROS: cargan los JSON semilla versionados, sin tocar BD.
"""

from __future__ import annotations

import keni_consola.hashtags_biblioteca as hb

# Cuántos sugerir por red, según `med.sql` sobre el historial anual (mediana entre quienes
# etiquetan; 0 donde la red apenas usa hashtags).
_CONTEO_ESPERADO = {
    "claro-sports": {"facebook": 1, "instagram": 5, "youtube": 0, "tiktok": 5},
    "unotv": {"facebook": 5, "instagram": 5, "tiktok": 5},
}


def test_candidatos_no_vacios_y_normalizados():
    for marca in ("claro-sports", "unotv"):
        cands = hb.candidatos(marca)
        assert cands, f"{marca} sin candidatos"
        # Todos en minúscula y SIN '#': lo que la etapa compara contra la salida de la IA.
        assert all(c == c.lower() and not c.startswith("#") for c in cands)
        # Sin duplicados.
        assert len(cands) == len(set(cands))


def test_hashtags_pasan_el_umbral():
    for marca in ("claro-sports", "unotv"):
        biblio = hb.biblioteca(marca)
        umbral = biblio["umbral"]
        assert umbral == 20
        assert all(h["n"] >= umbral for h in biblio["hashtags"])
        # Ordenados por frecuencia descendente.
        ns = [h["n"] for h in biblio["hashtags"]]
        assert ns == sorted(ns, reverse=True)


def test_conteo_por_red():
    for marca, esperado in _CONTEO_ESPERADO.items():
        for red, n in esperado.items():
            assert hb.cantidad_sugerida(marca, red) == n, (marca, red)


def test_red_desconocida_usa_el_defecto():
    # 'x' (Twitter) no está en la foto histórica de estas marcas: cae al default global.
    assert hb.cantidad_sugerida("unotv", "x") == hb.CANTIDAD_DEFECTO


def test_fijos_son_la_firma_de_la_marca_y_estan_en_el_pool():
    # La firma (nombre/portal) que va casi en cada post: la etapa la inyecta siempre.
    fijos = {
        "unotv": ["unotv", "portalunotv"],
        "claro-sports": ["portalclarosports"],
    }
    for marca, esperado in fijos.items():
        assert hb.fijos(marca) == esperado, marca
        # Cada fijo está en el pool de candidatos (si no, la etapa nunca lo añadiría).
        pool = set(hb.candidatos(marca))
        assert all(f in pool for f in hb.fijos(marca)), marca


def test_marca_sin_biblioteca_no_sugiere():
    assert hb.candidatos("marca-inexistente") == []
    assert hb.fijos("marca-inexistente") == []
    assert hb.cantidad_sugerida("marca-inexistente", "instagram") == 0
