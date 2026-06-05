"""Lógica PURA de selección del auto-feed (Ola E): umbral, frescura, tope/dedup.

PURO: no toca BD, red ni reloj. `historias_para_feed` y `cupo_restante` se prueban con dicts
de cluster sintéticos y un `es_fresca` inyectado.
"""

from __future__ import annotations

from keni_consola import autofeed_daemon as af


def _cluster(cid, score, *, estado="nuevo", contenido_id="", categoria="", ultimo_visto=""):
    return {
        "id": cid,
        "score": score,
        "estado": estado,
        "contenido_id": contenido_id,
        "categoria": categoria,
        "ultimo_visto": ultimo_visto,
        "marca": "claro-sports",
        "titulo": f"Historia {cid}",
    }


# --------------------------------------------------------------------------- #
# cupo_restante                                                                #
# --------------------------------------------------------------------------- #


def test_cupo_restante_resta_lo_de_hoy():
    assert af.cupo_restante(20, 5) == 15
    assert af.cupo_restante(20, 20) == 0
    assert af.cupo_restante(20, 25) == 0  # nunca negativo
    assert af.cupo_restante(0, 0) == 0


# --------------------------------------------------------------------------- #
# umbral                                                                       #
# --------------------------------------------------------------------------- #


def test_umbral_filtra_los_de_score_bajo():
    clusters = [_cluster("a", 0.9), _cluster("b", 0.4), _cluster("c", 0.6)]
    elegidos = af.historias_para_feed(clusters, umbral=0.5, cupo=10)
    assert [c["id"] for c in elegidos] == ["a", "c"]


def test_umbral_es_inclusivo():
    clusters = [_cluster("a", 0.5)]
    assert len(af.historias_para_feed(clusters, umbral=0.5, cupo=10)) == 1


# --------------------------------------------------------------------------- #
# dedup (estado/contenido_id)                                                  #
# --------------------------------------------------------------------------- #


def test_descarta_no_nuevos_y_ya_draftados():
    clusters = [
        _cluster("a", 0.9),
        _cluster("usada", 0.9, estado="usado"),
        _cluster("descartada", 0.9, estado="descartado"),
        _cluster("ya-draft", 0.9, contenido_id="c123"),
    ]
    elegidos = af.historias_para_feed(clusters, umbral=0.5, cupo=10)
    assert [c["id"] for c in elegidos] == ["a"]


# --------------------------------------------------------------------------- #
# tope (cupo)                                                                  #
# --------------------------------------------------------------------------- #


def test_recorta_al_cupo_conservando_orden():
    clusters = [_cluster(x, 0.9) for x in ("a", "b", "c", "d")]
    elegidos = af.historias_para_feed(clusters, umbral=0.5, cupo=2)
    assert [c["id"] for c in elegidos] == ["a", "b"]


def test_cupo_cero_no_elige_nada():
    clusters = [_cluster("a", 0.9)]
    assert af.historias_para_feed(clusters, umbral=0.5, cupo=0) == []


# --------------------------------------------------------------------------- #
# frescura (es_fresca inyectado)                                              #
# --------------------------------------------------------------------------- #


def test_frescura_descarta_caducas():
    clusters = [_cluster("fresca", 0.9), _cluster("caduca", 0.9)]
    elegidos = af.historias_para_feed(
        clusters,
        umbral=0.5,
        cupo=10,
        es_fresca=lambda c: c["id"] != "caduca",
    )
    assert [c["id"] for c in elegidos] == ["fresca"]


def test_sin_es_fresca_no_filtra_por_frescura():
    clusters = [_cluster("a", 0.9), _cluster("b", 0.9)]
    elegidos = af.historias_para_feed(clusters, umbral=0.5, cupo=10)
    assert [c["id"] for c in elegidos] == ["a", "b"]


def test_combinado_umbral_frescura_cupo():
    clusters = [
        _cluster("alta-fresca", 0.9),
        _cluster("alta-caduca", 0.85),
        _cluster("baja", 0.3),
        _cluster("media-fresca", 0.7),
    ]
    elegidos = af.historias_para_feed(
        clusters,
        umbral=0.5,
        cupo=1,
        es_fresca=lambda c: "caduca" not in c["id"],
    )
    # baja sale por umbral, alta-caduca por frescura; con cupo=1 entra solo la primera válida.
    assert [c["id"] for c in elegidos] == ["alta-fresca"]
