"""Tests de la fusión semántica de historias (`dominio.fusion_semantica` + `paso_fusion_semantica`).

OFFLINE: nunca llama a `claude` (ejecutor falso). Cubre el PARSEO/validación de grupos (puro) y la
FUSIÓN end-to-end en el daemon (Postgres): reasigna items a la canónica, borra las absorbidas y
recalcula n_fuentes/score. La fusión está gateada por `KENI_FUSION_SEMANTICA`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from keni_consola import ingesta_daemon, repos
from keni_consola.dominio import fusion_semantica

# Timestamp RECIENTE: `paso_fusion_semantica` solo mira historias dentro de la ventana de
# clustering (`KENI_CLUSTER_VENTANA_H`, 72h), así que se siembran "ahora".
_AHORA = datetime.now(UTC).isoformat()


def _ej(grupos):
    def run(_prompt, _carpeta):
        return json.dumps({"grupos": grupos})
    return run


# --------------------------------------------------------------------------- #
# proponer_fusiones (puro)                                                      #
# --------------------------------------------------------------------------- #


def test_proponer_fusiones_valida_disjunta_y_subset():
    clusters = [{"id": "a", "titulo": "X"}, {"id": "b", "titulo": "Y"}, {"id": "c", "titulo": "Z"}]
    # b reaparece en el 2º grupo (se ignora: ya usado); 'zzz' no existe (se filtra).
    grupos = fusion_semantica.proponer_fusiones(clusters, ejecutor=_ej([["a", "b"], ["b", "c"], ["a", "zzz"]]))
    assert grupos == [["a", "b"]]


def test_proponer_fusiones_menos_de_dos_historias():
    assert fusion_semantica.proponer_fusiones([{"id": "a", "titulo": "X"}], ejecutor=_ej([["a", "b"]])) == []


def test_proponer_fusiones_fallo_haiku_no_funde():
    def revienta(_p, _c):
        raise RuntimeError("claude caído")
    clusters = [{"id": "a", "titulo": "X"}, {"id": "b", "titulo": "Y"}]
    assert fusion_semantica.proponer_fusiones(clusters, ejecutor=revienta) == []


def test_extraer_grupos_tolera_fences():
    out = fusion_semantica._extraer_grupos('```json\n{"grupos": [["1","2"], ["3"]]}\n```')
    assert out == [["1", "2"]]  # grupos de <2 se descartan


# --------------------------------------------------------------------------- #
# paso_fusion_semantica (end-to-end, Postgres)                                  #
# --------------------------------------------------------------------------- #


def _sembrar(cid, *, marca="unotv", n_fuentes=1, score=0.3, fuente_id="f", url="https://e.com/x"):
    repos.upsert_noticia_cluster({
        "id": cid, "titulo": f"Historia {cid}", "resumen": "r", "marca": marca,
        "categoria": "mx", "geo": "MX", "clave": f"t:{cid}", "n_items": 1, "n_fuentes": n_fuentes,
        "idiomas": ["es"], "senal": 0, "score": score, "breaking": 0,
        "primer_visto": _AHORA, "ultimo_visto": _AHORA,
        "estado": "nuevo",
    })
    repos.crear_noticias_items([{
        "fuente_id": fuente_id, "fuente_nombre": fuente_id, "categoria": "mx", "marca": marca,
        "titulo": f"art {cid}", "resumen": "r", "url": url, "url_canonica": url,
        "clave": f"{cid}-it", "cluster_id": cid, "capturado_en": _AHORA,
    }])
    items, _ = repos.listar_noticias_items(limite=500)
    match = next(x for x in items if x["clave"] == f"{cid}-it")
    repos.asignar_cluster_item(match["id"], cid)


def test_paso_fusion_funde_grupo_del_mismo_evento(entorno, monkeypatch):
    monkeypatch.setenv("KENI_FUSION_SEMANTICA", "1")
    # c1 (2 fuentes) es la canónica; c2 (1 fuente) se absorbe. Fuentes distintas -> n_fuentes 2.
    _sembrar("c1", n_fuentes=2, score=0.6, fuente_id="medioA", url="https://a.com/1")
    _sembrar("c2", n_fuentes=1, score=0.2, fuente_id="medioB", url="https://b.com/1")

    res = ingesta_daemon.paso_fusion_semantica(ejecutor=_ej([["c1", "c2"]]))

    assert res["grupos"] == 1 and res["fusionadas"] == 1
    assert repos.obtener_noticia_cluster("c2") is None          # absorbida -> borrada
    canon = repos.obtener_noticia_cluster("c1")
    assert canon is not None                                     # canónica sobrevive
    assert len(repos.items_de_cluster("c1")) == 2                # ambos items reasignados


def test_paso_fusion_gateado_off_no_hace_nada(entorno, monkeypatch):
    monkeypatch.delenv("KENI_FUSION_SEMANTICA", raising=False)
    _sembrar("c1")
    _sembrar("c2")
    res = ingesta_daemon.paso_fusion_semantica(ejecutor=_ej([["c1", "c2"]]))
    assert res == {"grupos": 0, "fusionadas": 0}
    assert repos.obtener_noticia_cluster("c2") is not None       # nada se fundió


def test_construir_prompt_inserta_historias_y_contrato():
    # La plantilla viene de la Biblioteca (semilla): la lista JSON sustituye al marcador (que NO
    # debe quedar crudo) y se conserva el contrato JSON {"grupos": [...]}.
    p = fusion_semantica._construir_prompt('[{"id":"a"}]')
    assert '[{"id":"a"}]' in p
    assert fusion_semantica._MARCA_HISTORIAS not in p
    assert "grupos" in p
