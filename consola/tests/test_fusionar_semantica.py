"""Tests de la fusión semántica de historias (`dominio.fusionar_semantica` + `paso_fusionar_semantica`).

OFFLINE: nunca llama a `claude` (ejecutor falso). Cubre el PARSEO/validación de grupos (puro) y la
FUSIÓN end-to-end en el daemon (Postgres): reasigna items a la canónica, borra las absorbidas y
recalcula n_fuentes/score. La fusión está gateada por `KENI_PIPELINE_FUSIONAR`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from keni_consola import recolectar_daemon, repos
from keni_consola.dominio import fusionar_semantica
from keni_consola.recolectar_daemon import _comun

# Timestamp RECIENTE: `paso_fusionar_semantica` solo mira historias dentro de la ventana de
# agrupar (`KENI_CLUSTER_VENTANA_H`, 72h), así que se siembran "ahora".
_AHORA = datetime.now(UTC).isoformat()


@pytest.fixture(autouse=True)
def _reset_throttle_fusionar():
    """Resetea el throttle y la huella globales de `paso_fusionar_semantica` antes/después de cada
    test: así ni una pasada sellada por otro test la hace salir por el throttle, ni una huella
    previa la hace saltar por skip-if-unchanged."""
    _comun._ultimo_fusionar = 0.0
    _comun._ultima_huella_fusionar = None
    yield
    _comun._ultimo_fusionar = 0.0
    _comun._ultima_huella_fusionar = None


def _ej(grupos):
    def run(_prompt, _carpeta):
        return json.dumps({"grupos": grupos})
    return run


def _ej_familias(salida):
    """Ejecutor falso para macro-eventos: devuelve `salida` tal cual (str o dict serializable)."""
    def run(_prompt, _carpeta):
        return salida if isinstance(salida, str) else json.dumps(salida)
    return run


# --------------------------------------------------------------------------- #
# proponer_fusiones (puro)                                                      #
# --------------------------------------------------------------------------- #


def test_proponer_fusiones_valida_disjunta_y_subset():
    clusters = [{"id": "a", "titulo": "X"}, {"id": "b", "titulo": "Y"}, {"id": "c", "titulo": "Z"}]
    # b reaparece en el 2º grupo (se ignora: ya usado); 'zzz' no existe (se filtra).
    grupos = fusionar_semantica.proponer_fusiones(clusters, ejecutor=_ej([["a", "b"], ["b", "c"], ["a", "zzz"]]))
    assert grupos == [["a", "b"]]


def test_proponer_fusiones_menos_de_dos_historias():
    assert fusionar_semantica.proponer_fusiones([{"id": "a", "titulo": "X"}], ejecutor=_ej([["a", "b"]])) == []


def test_proponer_fusiones_fallo_haiku_no_funde():
    def revienta(_p, _c):
        raise RuntimeError("claude caído")
    clusters = [{"id": "a", "titulo": "X"}, {"id": "b", "titulo": "Y"}]
    assert fusionar_semantica.proponer_fusiones(clusters, ejecutor=revienta) == []


def test_verificacion_descarta_grupo_no_confirmado():
    """SEGUNDA PASADA: un grupo propuesto que el verificador rechaza NO se funde.

    Regresión del cluster "Shakira + alerta de la embajada" (10-jun): la primera pasada
    agrupó por TEMA (todo «Mundial»), infló la corroboración y el pool enseñó una historia
    «Corroborada · 2 fuentes» con fuentes que no hablaban de lo mismo. El verificador
    re-pregunta con SOLO esas historias y, si no son el mismo hecho, fuera."""
    llamadas = {"n": 0}

    def ej(_p, _c):
        llamadas["n"] += 1
        if llamadas["n"] == 1:  # propuesta: agrupa por tema (mal)
            return json.dumps({"grupos": [["shakira", "embajada"]]})
        return json.dumps({"grupos": []})  # verificación: no son el mismo evento

    clusters = [
        {"id": "shakira", "titulo": "A qué hora cantará Shakira en la inauguración"},
        {"id": "embajada", "titulo": "Embajada de EU alerta sobre la seguridad"},
    ]
    assert fusionar_semantica.proponer_fusiones(clusters, ejecutor=ej) == []
    assert llamadas["n"] == 2  # propuesta + verificación


def test_verificacion_puede_partir_un_grupo():
    """El verificador puede devolver un SUBGRUPO: se funde solo lo confirmado."""
    llamadas = {"n": 0}

    def ej(_p, _c):
        llamadas["n"] += 1
        if llamadas["n"] == 1:
            return json.dumps({"grupos": [["a", "b", "c"]]})
        return json.dumps({"grupos": [["a", "b"]]})  # c no era el mismo evento

    clusters = [
        {"id": "a", "titulo": "Sismo de 6.1 sacude CDMX"},
        {"id": "b", "titulo": "Tiembla en la Ciudad de México: 6.1"},
        {"id": "c", "titulo": "Protección Civil presenta su plan anual"},
    ]
    assert fusionar_semantica.proponer_fusiones(clusters, ejecutor=ej) == [["a", "b"]]


def test_verificacion_fallida_descarta_el_grupo():
    """Si la LLAMADA de verificación revienta, el grupo se descarta (conservador)."""
    llamadas = {"n": 0}

    def ej(_p, _c):
        llamadas["n"] += 1
        if llamadas["n"] == 1:
            return json.dumps({"grupos": [["a", "b"]]})
        raise RuntimeError("claude caído")

    clusters = [{"id": "a", "titulo": "X largo para fuzzy"}, {"id": "b", "titulo": "Y largo tambien"}]
    assert fusionar_semantica.proponer_fusiones(clusters, ejecutor=ej) == []


def test_extraer_grupos_tolera_fences():
    out = fusionar_semantica._extraer_grupos('```json\n{"grupos": [["1","2"], ["3"]]}\n```')
    assert out == [["1", "2"]]  # grupos de <2 se descartan


# --------------------------------------------------------------------------- #
# proponer_macro_eventos (puro)                                                 #
# --------------------------------------------------------------------------- #


def test_proponer_macro_eventos_agrupa_familia():
    """Tres historias DISTINTAS del mismo gran evento se etiquetan como una familia."""
    clusters = [
        {"id": "hotmic", "titulo": "Micrófono abierto capta a un líder en el G7"},
        {"id": "iran", "titulo": "El G7 endurece su postura sobre Irán"},
        {"id": "comercio", "titulo": "Acuerdo comercial en la cumbre del G7"},
    ]
    salida = {"familias": [{"tema": "Cumbre del G7", "ids": ["hotmic", "iran", "comercio"]}]}
    familias = fusionar_semantica.proponer_macro_eventos(clusters, ejecutor=_ej_familias(salida))
    assert familias == [{"tema": "Cumbre del G7", "ids": ["hotmic", "iran", "comercio"]}]


def test_proponer_macro_eventos_ignora_familia_de_uno():
    """Una familia con un solo id válido (y los ids inexistentes se filtran) se descarta."""
    clusters = [{"id": "a", "titulo": "X"}, {"id": "b", "titulo": "Y"}]
    salida = {"familias": [
        {"tema": "Evento de uno", "ids": ["a", "a"]},      # un solo id distinto -> fuera
        {"tema": "Inexistentes", "ids": ["zzz", "www"]},   # ningún id válido -> fuera
    ]}
    assert fusionar_semantica.proponer_macro_eventos(clusters, ejecutor=_ej_familias(salida)) == []


def test_proponer_macro_eventos_json_invalido_devuelve_vacio():
    """Salida no parseable de Haiku -> [] (best-effort)."""
    clusters = [{"id": "a", "titulo": "X"}, {"id": "b", "titulo": "Y"}]
    assert fusionar_semantica.proponer_macro_eventos(clusters, ejecutor=_ej_familias("no soy json")) == []


def test_proponer_macro_eventos_reutiliza_tema_macro_existente():
    """El payload lleva el `tema_macro` ACTUAL de cada cluster y la familia REUTILIZA esa etiqueta.

    Evita que Haiku etiquete el mismo evento con sinónimos ("Mundial 2026" vs "Copa del Mundo
    2026") y parta la familia. El ejecutor falso lee el payload del prompt, toma el `tema_macro`
    no vacío que ya existe y lo devuelve verbatim como `tema`; se verifica que se propaga."""
    clusters = [
        {"id": "x", "titulo": "México define su sede para el torneo", "tema_macro": "Mundial 2026"},
        {"id": "y", "titulo": "Venta de boletos para el gran evento", "tema_macro": ""},
    ]

    def ej(prompt, _carpeta):
        # El payload (lista JSON de historias) viene embebido en el prompt; cada item trae su
        # `tema_macro`. Reutilizamos la etiqueta existente como tema de la familia. El payload es la
        # PRIMERA estructura JSON del prompt; `raw_decode` la lee y descarta el contrato de salida
        # (que trae sus propios `[...]` de ejemplo) que viene detrás.
        items, _ = json.JSONDecoder().raw_decode(prompt[prompt.index("["):])
        existente = next((it["tema_macro"] for it in items if it.get("tema_macro")), "")
        assert all("tema_macro" in it for it in items)  # el payload SIEMPRE lleva la etiqueta
        return json.dumps({"familias": [{"tema": existente, "ids": ["x", "y"]}]})

    familias = fusionar_semantica.proponer_macro_eventos(clusters, ejecutor=ej)
    assert familias == [{"tema": "Mundial 2026", "ids": ["x", "y"]}]


# --------------------------------------------------------------------------- #
# proponer_subtemas (puro)                                                      #
# --------------------------------------------------------------------------- #


def _ej_subtemas(salida):
    def run(_prompt, _carpeta):
        return salida if isinstance(salida, str) else json.dumps(salida)
    return run


def test_proponer_subtemas_parte_el_evento_en_facetas():
    """Un macro-evento se parte en subtemas DISJUNTOS; un concierto no va con los partidos."""
    clusters = [
        {"id": "p1", "titulo": "México vence a Sudáfrica en el debut"},
        {"id": "p2", "titulo": "Argentina golea a Argelia"},
        {"id": "show", "titulo": "Concierto en la inauguración del torneo"},
    ]
    salida = {"subtemas": [
        {"subtema": "Partidos", "ids": ["p1", "p2"]},
        {"subtema": "Espectáculo", "ids": ["show"]},
    ]}
    subtemas = fusionar_semantica.proponer_subtemas(clusters, ejecutor=_ej_subtemas(salida))
    assert subtemas == [
        {"subtema": "Partidos", "ids": ["p1", "p2"]},
        {"subtema": "Espectáculo", "ids": ["show"]},
    ]


def test_proponer_subtemas_disjuntos_y_solo_ids_validos():
    """Un id repetido entre subtemas se queda en el primero; los inexistentes se filtran."""
    clusters = [{"id": "a", "titulo": "X"}, {"id": "b", "titulo": "Y"}]
    salida = {"subtemas": [
        {"subtema": "Uno", "ids": ["a", "b"]},
        {"subtema": "Dos", "ids": ["b", "zzz"]},  # b ya usado, zzz no existe -> subtema vacío, fuera
    ]}
    assert fusionar_semantica.proponer_subtemas(clusters, ejecutor=_ej_subtemas(salida)) == [
        {"subtema": "Uno", "ids": ["a", "b"]},
    ]


def test_proponer_subtemas_menos_de_dos_o_json_invalido():
    uno = [{"id": "a", "titulo": "X"}]
    assert fusionar_semantica.proponer_subtemas(uno, ejecutor=_ej_subtemas({"subtemas": []})) == []
    dos = [{"id": "a", "titulo": "X"}, {"id": "b", "titulo": "Y"}]
    assert fusionar_semantica.proponer_subtemas(dos, ejecutor=_ej_subtemas("no soy json")) == []


# --------------------------------------------------------------------------- #
# paso_fusionar_semantica (end-to-end, Postgres)                                  #
# --------------------------------------------------------------------------- #


def _inicializar(cid, *, marca="unotv", n_fuentes=1, score=0.3, fuente_id="f", url="https://e.com/x"):
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
    monkeypatch.setenv("KENI_PIPELINE_FUSIONAR", "1")
    # c1 (2 fuentes) es la canónica; c2 (1 fuente) se absorbe. Fuentes distintas -> n_fuentes 2.
    _inicializar("c1", n_fuentes=2, score=0.6, fuente_id="medioA", url="https://a.com/1")
    _inicializar("c2", n_fuentes=1, score=0.2, fuente_id="medioB", url="https://b.com/1")

    res = recolectar_daemon.paso_fusionar_semantica(ejecutor=_ej([["c1", "c2"]]))

    assert res["grupos"] == 1 and res["fusionadas"] == 1
    assert repos.obtener_noticia_cluster("c2") is None          # absorbida -> borrada
    canon = repos.obtener_noticia_cluster("c1")
    assert canon is not None                                     # canónica sobrevive
    assert len(repos.items_de_cluster("c1")) == 2                # ambos items reasignados


def test_paso_fusion_gateado_off_no_hace_nada(entorno, monkeypatch):
    # Def ON: para apagar hay que fijarlo EXPLÍCITO a "0" (no basta con no setearlo).
    monkeypatch.setenv("KENI_PIPELINE_FUSIONAR", "0")
    _inicializar("c1")
    _inicializar("c2")
    res = recolectar_daemon.paso_fusionar_semantica(ejecutor=_ej([["c1", "c2"]]))
    assert res == {"grupos": 0, "fusionadas": 0}
    assert repos.obtener_noticia_cluster("c2") is not None       # nada se fundió


# --------------------------------------------------------------------------- #
# Payload mínimo (solo titulares) + ejecutor no-agéntico                        #
# --------------------------------------------------------------------------- #


def test_proponer_fusiones_payload_solo_id_y_titulo():
    """El payload a Haiku lleva solo `id`+`titulo` (sin `resumen`): clasificación inline barata."""
    clusters = [
        {"id": "a", "titulo": "Titular A", "resumen": "Resumen largo A"},
        {"id": "b", "titulo": "Titular B", "resumen": "Resumen largo B"},
    ]
    capt: dict[str, list[dict]] = {}

    def ej(prompt, _carpeta):
        items, _ = json.JSONDecoder().raw_decode(prompt[prompt.index("["):])
        capt["items"] = items
        return json.dumps({"grupos": []})

    fusionar_semantica.proponer_fusiones(clusters, ejecutor=ej)
    assert capt["items"] == [{"id": "a", "titulo": "Titular A"}, {"id": "b", "titulo": "Titular B"}]
    assert all("resumen" not in it for it in capt["items"])


def test_proponer_macro_eventos_payload_conserva_tema_macro_sin_resumen():
    """El payload de macro-evento mantiene `tema_macro` (lo reutiliza el modelo) pero NO `resumen`."""
    clusters = [
        {"id": "a", "titulo": "T A", "resumen": "R A", "tema_macro": "Mundial 2026"},
        {"id": "b", "titulo": "T B", "resumen": "R B", "tema_macro": ""},
    ]
    capt: dict[str, list[dict]] = {}

    def ej(prompt, _carpeta):
        items, _ = json.JSONDecoder().raw_decode(prompt[prompt.index("["):])
        capt["items"] = items
        return json.dumps({"familias": []})

    fusionar_semantica.proponer_macro_eventos(clusters, ejecutor=ej)
    assert all("resumen" not in it for it in capt["items"])
    assert all("tema_macro" in it for it in capt["items"])
    assert {it["id"] for it in capt["items"]} == {"a", "b"}


def test_ejecutar_haiku_es_no_agentico(monkeypatch):
    """El ejecutor real de la fusión acota la llamada: `max_turns=1` y `sin_tools=True`."""
    from keni_consola.dominio import traducir

    capt: dict[str, object] = {}
    monkeypatch.setattr(
        traducir, "_ejecutar_claude_json",
        lambda prompt, carpeta, **kw: capt.update(kw) or '{"grupos": []}',
    )
    fusionar_semantica._ejecutar_haiku("P", "/tmp/x")
    assert capt.get("max_turns") == 1
    assert capt.get("sin_tools") is True


def test_construir_prompt_inserta_historias_y_contrato():
    # La plantilla viene de la Prompts (inicial): la lista JSON sustituye al marcador (que NO
    # debe quedar crudo) y se conserva el contrato JSON {"grupos": [...]}.
    p = fusionar_semantica._construir_prompt('[{"id":"a"}]')
    assert '[{"id":"a"}]' in p
    assert fusionar_semantica._MARCA_HISTORIAS not in p
    assert "grupos" in p
