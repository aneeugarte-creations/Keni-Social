"""Tests de la API Limites (/api/limites) y de la fuente unica de los topes.

#112: los limites de caracteres por red viven SOLO en `limites_plataforma`; el
endpoint los expone y `redes.py` los consume sin redefinirlos. OFFLINE, sin red.
"""

from __future__ import annotations

from keni_consola import limites_plataforma, redes


def test_limites_endpoint_orden_y_forma(cliente):
    datos = cliente.get("/api/limites").json()
    assert "limites" in datos
    ids = [r["id"] for r in datos["limites"]]
    # mismo orden fijo que el catalogo de redes
    assert ids == ["x", "instagram", "facebook", "tiktok", "youtube"]
    por_id = {r["id"]: r for r in datos["limites"]}
    assert por_id["x"] == {"id": "x", "nombre": "X", "limite": 280}
    assert por_id["instagram"]["limite"] == 2200
    assert por_id["facebook"]["limite"] is None
    assert por_id["tiktok"]["limite"] == 4000  # caption ampliado 2023-24 (#112)
    assert por_id["youtube"]["limite"] is None


def test_redes_consume_la_fuente_unica_de_limites():
    # `redes.REDES.limite` NO se redefine: es exactamente `limites_plataforma`.
    for r in redes.REDES:
        assert r.limite == limites_plataforma.limite_de(r.id)


def test_tiktok_reconciliado_a_4000():
    # La divergencia de #112 (meta.ts=2200 vs plataformas.md "2200/4000") se
    # reconcilia al maximo tecnico actual: 4000.
    assert limites_plataforma.limite_de("tiktok") == 4000


def test_limite_de_red_desconocida_es_none():
    assert limites_plataforma.limite_de("threads") is None
