"""Tests de la fusión semántica de historias (`dominio.fusionar_semantica` + `paso_fusionar_semantica`).

OFFLINE: nunca llama a `claude` (ejecutor falso). En UNA pasada `proponer_fusiones` devuelve
`Fusiones(grupos, familias)`: `grupos` (mismo hecho, a fundir, verificados) y `familias` (mismo gran
evento, a etiquetar). Cubre el PARSEO/validación (puro) y la FUSIÓN end-to-end en el daemon
(Postgres). Gateado por `KENI_PIPELINE_FUSIONAR`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from keni_consola import repos
from keni_consola.dominio import fusionar_semantica

# Timestamp RECIENTE: las historias se siembran "ahora" (dentro de la ventana de agrupar, 72h).
_AHORA = datetime.now(UTC).isoformat()


def _ej(grupos):
    """Ejecutor falso: la pasada de propuesta devuelve `{"grupos": ...}` (sin familias)."""
    def run(_prompt, _carpeta):
        return json.dumps({"grupos": grupos})
    return run


def _ej_salida(salida):
    """Ejecutor falso que devuelve `salida` tal cual (str o dict serializable). Para probar el
    parseo de `familias`/`subtemas` desde la respuesta del LLM."""
    def run(_prompt, _carpeta):
        return salida if isinstance(salida, str) else json.dumps(salida)
    return run


# --------------------------------------------------------------------------- #
# proponer_fusiones — GRUPOS (puro)                                             #
# --------------------------------------------------------------------------- #


def test_proponer_fusiones_valida_disjunta_y_subset():
    clusters = [{"id": "a", "titulo": "X"}, {"id": "b", "titulo": "Y"}, {"id": "c", "titulo": "Z"}]
    # b reaparece en el 2º grupo (se ignora: ya usado); 'zzz' no existe (se filtra).
    res = fusionar_semantica.proponer_fusiones(clusters, ejecutor=_ej([["a", "b"], ["b", "c"], ["a", "zzz"]]))
    assert res.grupos == [["a", "b"]]
    assert res.familias == []


def test_proponer_fusiones_menos_de_dos_historias():
    res = fusionar_semantica.proponer_fusiones([{"id": "a", "titulo": "X"}], ejecutor=_ej([["a", "b"]]))
    assert res.grupos == [] and res.familias == []


def test_proponer_fusiones_fallo_haiku_no_funde():
    def revienta(_p, _c):
        raise RuntimeError("claude caído")
    clusters = [{"id": "a", "titulo": "X"}, {"id": "b", "titulo": "Y"}]
    res = fusionar_semantica.proponer_fusiones(clusters, ejecutor=revienta)
    assert res.grupos == [] and res.familias == []


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
    assert fusionar_semantica.proponer_fusiones(clusters, ejecutor=ej).grupos == []
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
    assert fusionar_semantica.proponer_fusiones(clusters, ejecutor=ej).grupos == [["a", "b"]]


def test_verificacion_fallida_descarta_el_grupo():
    """Si la LLAMADA de verificación revienta, el grupo se descarta (conservador)."""
    llamadas = {"n": 0}

    def ej(_p, _c):
        llamadas["n"] += 1
        if llamadas["n"] == 1:
            return json.dumps({"grupos": [["a", "b"]]})
        raise RuntimeError("claude caído")

    clusters = [{"id": "a", "titulo": "X largo para fuzzy"}, {"id": "b", "titulo": "Y largo tambien"}]
    assert fusionar_semantica.proponer_fusiones(clusters, ejecutor=ej).grupos == []


def test_extraer_grupos_tolera_fences():
    out = fusionar_semantica._extraer_grupos('```json\n{"grupos": [["1","2"], ["3"]]}\n```')
    assert out == [["1", "2"]]  # grupos de <2 se descartan


# --------------------------------------------------------------------------- #
# proponer_fusiones — FAMILIAS (mismo gran evento, en la MISMA pasada)          #
# --------------------------------------------------------------------------- #


def test_proponer_fusiones_agrupa_familia():
    """Tres historias DISTINTAS del mismo gran evento salen como una familia (no se funden)."""
    clusters = [
        {"id": "hotmic", "titulo": "Micrófono abierto capta a un líder en el G7"},
        {"id": "iran", "titulo": "El G7 endurece su postura sobre Irán"},
        {"id": "comercio", "titulo": "Acuerdo comercial en la cumbre del G7"},
    ]
    salida = {"grupos": [], "familias": [{"tema": "Cumbre del G7", "ids": ["hotmic", "iran", "comercio"]}]}
    res = fusionar_semantica.proponer_fusiones(clusters, ejecutor=_ej_salida(salida))
    assert res.grupos == []
    assert res.familias == [{"tema": "Cumbre del G7", "ids": ["hotmic", "iran", "comercio"]}]


def test_proponer_fusiones_ignora_familia_de_uno():
    """Una familia con un solo id válido (y los ids inexistentes se filtran) se descarta."""
    clusters = [{"id": "a", "titulo": "X"}, {"id": "b", "titulo": "Y"}]
    salida = {"familias": [
        {"tema": "Evento de uno", "ids": ["a", "a"]},      # un solo id distinto -> fuera
        {"tema": "Inexistentes", "ids": ["zzz", "www"]},   # ningún id válido -> fuera
    ]}
    assert fusionar_semantica.proponer_fusiones(clusters, ejecutor=_ej_salida(salida)).familias == []


def test_proponer_fusiones_familias_json_invalido_devuelve_vacio():
    """Salida no parseable -> grupos y familias vacías (best-effort)."""
    clusters = [{"id": "a", "titulo": "X"}, {"id": "b", "titulo": "Y"}]
    res = fusionar_semantica.proponer_fusiones(clusters, ejecutor=_ej_salida("no soy json"))
    assert res.grupos == [] and res.familias == []


def test_proponer_fusiones_familia_reutiliza_tema_macro_existente():
    """El payload lleva el `tema_macro` ACTUAL de cada cluster y la familia REUTILIZA esa etiqueta.

    Evita que el modelo etiquete el mismo evento con sinónimos ("Mundial 2026" vs "Copa del Mundo
    2026") y parta la familia. El ejecutor falso lee el payload del prompt, toma el `tema_macro`
    no vacío que ya existe y lo devuelve verbatim como `tema`; se verifica que se propaga."""
    clusters = [
        {"id": "x", "titulo": "México define su sede para el torneo", "tema_macro": "Mundial 2026"},
        {"id": "y", "titulo": "Venta de boletos para el gran evento", "tema_macro": ""},
    ]

    def ej(prompt, _carpeta):
        # El payload (lista JSON de historias) viene embebido en el prompt; cada item trae su
        # `tema_macro`. El payload es la PRIMERA estructura JSON del prompt; `raw_decode` la lee.
        items, _ = json.JSONDecoder().raw_decode(prompt[prompt.index("["):])
        existente = next((it["tema_macro"] for it in items if it.get("tema_macro")), "")
        assert all("tema_macro" in it for it in items)  # el payload SIEMPRE lleva la etiqueta
        return json.dumps({"grupos": [], "familias": [{"tema": existente, "ids": ["x", "y"]}]})

    res = fusionar_semantica.proponer_fusiones(clusters, ejecutor=ej)
    assert res.familias == [{"tema": "Mundial 2026", "ids": ["x", "y"]}]


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
# fusionar_marca (executor del JOB, end-to-end, Postgres)                         #
# --------------------------------------------------------------------------- #


def _inicializar(cid, *, marca="unotv", n_fuentes=1, score=0.3, fuente_id="f", url="https://e.com/x",
                 titulo=None):
    repos.upsert_noticia_cluster({
        "id": cid, "titulo": titulo or f"Historia {cid}", "resumen": "r", "marca": marca,
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


def _recientes(marca="unotv"):
    """Las historias `nuevo` recientes de la marca, como las pasaría el barrido en el spec del job."""
    return [c for c in repos.clusters_recientes(72) if (c.get("marca") or "") == marca]


def test_fusionar_marca_funde_grupo_del_mismo_evento(entorno):
    """El executor del job (`fusionar_marca`) FUNDE el grupo del mismo hecho a partir de la salida de
    la pasada principal (la verificación se confirma con el ejecutor inyectado). Postgres (CI)."""
    # c1 (2 fuentes) es la canónica; c2 (1 fuente) se absorbe. Fuentes distintas -> n_fuentes 2.
    _inicializar("c1", n_fuentes=2, score=0.6, fuente_id="medioA", url="https://a.com/1")
    _inicializar("c2", n_fuentes=1, score=0.2, fuente_id="medioB", url="https://b.com/1")

    salida = json.dumps({"grupos": [["c1", "c2"]]})
    res = fusionar_semantica.fusionar_marca(
        "unotv", _recientes(), salida_principal=salida, ejecutor=_ej([["c1", "c2"]]),
    )

    assert res["grupos"] == 1 and res["fusionadas"] == 1
    assert repos.obtener_noticia_cluster("c2") is None          # absorbida -> borrada
    canon = repos.obtener_noticia_cluster("c1")
    assert canon is not None                                     # canónica sobrevive
    assert len(repos.items_de_cluster("c1")) == 2                # ambos items reasignados


def test_fusionar_marca_solo_facetea_familias_con_subtema_pendiente(entorno, monkeypatch):
    """El executor etiqueta las familias y el subtema solo se re-propone para la familia que tiene un
    cluster sin subtema; la familia ya faceteada se omite (`_falta_subtema`). Postgres (CI)."""
    for cid in ("c1", "c2", "c3", "c4"):
        _inicializar(cid)
    # Familia A: ya etiquetada y faceteada (estable, no debe re-faceterarse).
    repos.marcar_clusters_tema_macro(["c1", "c2"], "Mundial 2026")
    repos.marcar_clusters_subtema(["c1", "c2"], "Partidos")
    # c3, c4: nuevos, sin tema_macro ni subtema.

    salida = json.dumps({"grupos": [], "familias": [
        {"tema": "Mundial 2026", "ids": ["c1", "c2"]},
        {"tema": "Elecciones 2026", "ids": ["c3", "c4"]},
    ]})
    faceteadas: list[list[str]] = []

    def fake_subtemas(familia, **_kw):
        faceteadas.append(sorted(str(c["id"]) for c in familia))
        return []

    monkeypatch.setattr(fusionar_semantica, "proponer_subtemas", fake_subtemas)

    fusionar_semantica.fusionar_marca("unotv", _recientes(), salida_principal=salida, ejecutor=_ej([]))
    assert faceteadas == [["c3", "c4"]]  # la familia ya faceteada [c1, c2] no se reenvía al LLM


def test_fusionar_marca_ancla_familias_por_agenda(entorno, monkeypatch):
    """Sin LLM: las historias que nombran el partido de la AGENDA heredan su título como
    `tema_macro`, aunque la propuesta de fusiones venga vacía. Las que no casan, no. Postgres (CI)."""
    hoy = datetime.now(UTC).date().isoformat()
    monkeypatch.setattr(fusionar_semantica, "_eventos_de_marca",
                        lambda _marca, _ahora: [{"titulo": "Portugal vs Uzbekistán", "fecha": hoy}])
    _inicializar("c1", titulo="Portugal golea a Uzbekistán con doblete de Cristiano")
    _inicializar("c2", titulo="¿Dónde ver Portugal vs Uzbekistán hoy? horario y canal")
    _inicializar("c3", titulo="Tormenta inunda la ciudad y deja apagones")  # no casa la agenda

    fusionar_semantica.fusionar_marca(
        "unotv", _recientes(), salida_principal='{"grupos": []}', ejecutor=_ej([]),
    )

    assert (repos.obtener_noticia_cluster("c1") or {}).get("tema_macro") == "Portugal vs Uzbekistán"
    assert (repos.obtener_noticia_cluster("c2") or {}).get("tema_macro") == "Portugal vs Uzbekistán"
    assert (repos.obtener_noticia_cluster("c3") or {}).get("tema_macro") == ""


def test_fusionar_marca_ancla_manda_sobre_reaglomerado_de_haiku(entorno, monkeypatch):
    """Una familia ya anclada a la agenda (nivel partido) NO se re-etiqueta por una familia más
    gruesa que proponga el LLM («Mundial 2026»): la agenda es la verdad. Postgres (CI)."""
    hoy = datetime.now(UTC).date().isoformat()
    monkeypatch.setattr(fusionar_semantica, "_eventos_de_marca",
                        lambda _marca, _ahora: [{"titulo": "Portugal vs Uzbekistán", "fecha": hoy}])
    _inicializar("c1", titulo="Portugal golea a Uzbekistán")
    _inicializar("c2", titulo="Portugal vs Uzbekistán: dónde ver hoy")

    salida = json.dumps({"grupos": [], "familias": [{"tema": "Mundial 2026", "ids": ["c1", "c2"]}]})
    fusionar_semantica.fusionar_marca("unotv", _recientes(), salida_principal=salida, ejecutor=_ej([]))

    assert (repos.obtener_noticia_cluster("c1") or {}).get("tema_macro") == "Portugal vs Uzbekistán"
    assert (repos.obtener_noticia_cluster("c2") or {}).get("tema_macro") == "Portugal vs Uzbekistán"


def test_fusionar_marca_menos_de_dos_no_hace_nada(entorno):
    """Con <2 historias no hay nada que fundir (el executor sale temprano)."""
    _inicializar("c1")
    res = fusionar_semantica.fusionar_marca(
        "unotv", _recientes(), salida_principal='{"grupos": []}', ejecutor=_ej([]),
    )
    assert res == {"grupos": 0, "fusionadas": 0, "familias": 0, "anclas": 0}


def test_construir_procesar_fusionar_limpia_el_marcador(entorno, monkeypatch):
    """El callback del worker funde y, pase lo que pase, LIMPIA el marcador de fusión en curso."""
    _inicializar("c1", n_fuentes=2, score=0.6, fuente_id="medioA", url="https://a.com/1")
    _inicializar("c2", n_fuentes=1, score=0.2, fuente_id="medioB", url="https://b.com/1")
    limpiados: list[str] = []
    monkeypatch.setattr(fusionar_semantica, "limpiar_fusion_encolada", lambda m: limpiados.append(m))
    monkeypatch.setattr(fusionar_semantica, "procesar_fusiones",
                        lambda *a, **k: fusionar_semantica.Fusiones([["c1", "c2"]], []))

    procesar = fusionar_semantica.construir_procesar_fusionar("unotv", _recientes())
    res = procesar(json.dumps({"grupos": [["c1", "c2"]]}), None)

    assert res["grupos"] == 1 and res["fusionadas"] == 1
    assert limpiados == ["unotv"]
    assert repos.obtener_noticia_cluster("c2") is None


def test_fusionar_marca_invoca_callbacks_por_subllamada(entorno):
    """`fusionar_marca` invoca `al_ejecutar` por cada grupo COTEJADO y `al_ejecutar_subtema` por cada
    familia faceteada: así el job sella el gasto de esas sub-llamadas bajo «Cotejar» / «Subtema»."""
    _inicializar("c1", n_fuentes=2, score=0.6, fuente_id="medioA", url="https://a.com/1")
    _inicializar("c2", n_fuentes=1, score=0.2, fuente_id="medioB", url="https://b.com/1")
    _inicializar("c3", fuente_id="medioC", url="https://c.com/1")
    _inicializar("c4", fuente_id="medioD", url="https://d.com/1")
    cotejos: list[str] = []
    subtemas: list[str] = []

    # Un solo ejecutor sirve a ambas sub-llamadas: la verificación lee «grupos» (confirma c1+c2) y el
    # reparto de subtemas lee «subtemas» (una faceta con c3+c4) de la MISMA respuesta.
    def ej(_prompt, _carpeta):
        return json.dumps({"grupos": [["c1", "c2"]], "subtemas": [{"subtema": "General", "ids": ["c3", "c4"]}]})

    salida = json.dumps({"grupos": [["c1", "c2"]], "familias": [{"tema": "Elecciones 2026", "ids": ["c3", "c4"]}]})
    fusionar_semantica.fusionar_marca(
        "unotv", _recientes(), salida_principal=salida, ejecutor=ej,
        al_ejecutar=lambda _p, s: cotejos.append(s),
        al_ejecutar_subtema=lambda _p, s: subtemas.append(s),
    )
    assert len(cotejos) == 1   # un grupo cotejado
    assert len(subtemas) == 1  # una familia faceteada


# --------------------------------------------------------------------------- #
# Payload (id + titulo + tema_macro, sin resumen) + ejecutor no-agéntico         #
# --------------------------------------------------------------------------- #


def test_proponer_fusiones_payload_id_titulo_tema_macro_sin_resumen():
    """El payload lleva `id`, `titulo` y `tema_macro` (que reutilizan las familias), nunca `resumen`."""
    clusters = [
        {"id": "a", "titulo": "Titular A", "resumen": "Resumen largo A", "tema_macro": "Mundial 2026"},
        {"id": "b", "titulo": "Titular B", "resumen": "Resumen largo B"},
    ]
    capt: dict[str, list[dict]] = {}

    def ej(prompt, _carpeta):
        items, _ = json.JSONDecoder().raw_decode(prompt[prompt.index("["):])
        capt["items"] = items
        return json.dumps({"grupos": [], "familias": []})

    fusionar_semantica.proponer_fusiones(clusters, ejecutor=ej)
    assert capt["items"] == [
        {"id": "a", "titulo": "Titular A", "tema_macro": "Mundial 2026"},
        {"id": "b", "titulo": "Titular B", "tema_macro": ""},
    ]
    assert all("resumen" not in it for it in capt["items"])


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
    # debe quedar crudo) y se conserva el contrato JSON {"grupos": [...], "familias": [...]}.
    p = fusionar_semantica._construir_prompt('[{"id":"a"}]')
    assert '[{"id":"a"}]' in p
    assert fusionar_semantica._MARCA_HISTORIAS not in p
    assert "grupos" in p and "familias" in p


# --------------------------------------------------------------------------- #
# Frescura del lote (`_fresco_para_fusion`): solo lo VIVO entra al LLM (puro)    #
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# Marcador PERSISTIDO "fusión en curso" por marca (idempotencia del encolado)    #
# --------------------------------------------------------------------------- #


def test_marcador_en_curso_y_reapertura_por_ttl(monkeypatch, tmp_path):
    """`marcar_fusion_encolada` sella la marca EN CURSO; `fusion_en_curso` es True dentro del TTL y
    False cuando el sello caduca (job atascado: se re-encola). `limpiar` la re-abre."""
    monkeypatch.setattr(fusionar_semantica, "_ruta_encolado", lambda: tmp_path / "fusion_encolada.json")
    ahora = datetime.now(UTC)
    fusionar_semantica.marcar_fusion_encolada("unotv", ahora=ahora)

    assert fusionar_semantica.fusion_en_curso("unotv", ahora=ahora, ttl_min=30) is True
    # Sello más viejo que el TTL -> atascado, NO bloquea (reapertura).
    viejo = ahora + timedelta(minutes=31)
    assert fusionar_semantica.fusion_en_curso("unotv", ahora=viejo, ttl_min=30) is False
    # Otra marca nunca está en curso; tampoco la marca vacía.
    assert fusionar_semantica.fusion_en_curso("claro-sports", ahora=ahora, ttl_min=30) is False
    assert fusionar_semantica.fusion_en_curso("", ahora=ahora, ttl_min=30) is False

    fusionar_semantica.limpiar_fusion_encolada("unotv")
    assert fusionar_semantica.fusion_en_curso("unotv", ahora=ahora, ttl_min=30) is False


def test_marcador_corrupto_no_bloquea(monkeypatch, tmp_path):
    """Un sello ilegible no bloquea (se re-encola): `fusion_en_curso` cae a False."""
    ruta = tmp_path / "fusion_encolada.json"
    monkeypatch.setattr(fusionar_semantica, "_ruta_encolado", lambda: ruta)
    ruta.write_text(json.dumps({"unotv": "no-es-fecha"}), encoding="utf-8")
    assert fusionar_semantica.fusion_en_curso("unotv", ahora=datetime.now(UTC), ttl_min=30) is False


def test_fresco_para_fusion_excluye_lo_rancio_e_incluye_lo_vivo():
    """Un cluster sin actividad dentro de la ventana de fusión NO entra al lote (ya se digirió)."""
    from keni_consola.recolectar_daemon.pasos.fusionar_semantica import _fresco_para_fusion

    ahora = datetime.now(UTC)
    corte = ahora - timedelta(hours=48)
    vivo = {"ultimo_visto": (ahora - timedelta(hours=10)).isoformat()}
    rancio = {"ultimo_visto": (ahora - timedelta(hours=60)).isoformat()}
    assert _fresco_para_fusion(vivo, corte) is True
    assert _fresco_para_fusion(rancio, corte) is False


def test_fresco_para_fusion_tolera_canon_sin_offset_y_marca_ilegible():
    """`fromisoformat` lee el canon de `iso_utc` (naive=UTC); marca vacía/ilegible -> conservador (se procesa)."""
    from keni_consola.recolectar_daemon.pasos.fusionar_semantica import _fresco_para_fusion
    from keni_consola.tiempo import iso_utc

    ahora = datetime.now(UTC)
    corte = ahora - timedelta(hours=48)
    vivo_naive = {"ultimo_visto": iso_utc(ahora - timedelta(hours=1))}  # sin offset (naive)
    assert _fresco_para_fusion(vivo_naive, corte) is True
    assert _fresco_para_fusion({"ultimo_visto": "basura"}, corte) is True  # ilegible -> no excluye
    assert _fresco_para_fusion({}, corte) is True  # sin marca -> no excluye
