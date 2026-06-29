"""Tests del módulo dominio/traducir.py. OFFLINE: nunca llama a `claude` real.

Cubre:
  - `traducir_items` con ejecutor falso que devuelve JSON válido.
  - Best-effort: fallo del ejecutor -> devuelve originales.
  - Best-effort: JSON inválido -> devuelve originales.
  - Best-effort: ítem faltante en la respuesta -> devuelve el original para ese ítem.
  - Lista vacía -> devuelve lista vacía.
  - Textos largos se truncan en el payload (no en la respuesta final).
  - El Radar EN VIVO solo etiqueta `idioma` (#desacoplo del back) y nunca llama a
    `traducir_items`. La traducción de historias persistidas la hace el daemon de
    ingesta (tests del daemon, no aquí).
"""

from __future__ import annotations

import json

import pytest

from keni_consola.dominio import traducir

# --------------------------------------------------------------------------- #
# Ejecutores falsos                                                             #
# --------------------------------------------------------------------------- #


def _ejecutor_ok(prompt: str, dir_permitido: str) -> str:
    """Ejecutor que extrae los ids del prompt y devuelve traducciones al español."""
    # Extrae el JSON de ítems del prompt para construir una respuesta coherente.
    import re

    # Aísla la lista REAL de ítems (va tras "## Lista de ítems"); el prompt también
    # contiene un ejemplo con corchetes en las instrucciones que confundía al regex.
    cola = prompt.partition("## Lista de ítems")[2] or prompt
    m = re.search(r"\[.*?\]", cola, re.DOTALL)
    if not m:
        return json.dumps({"traducciones": []})
    try:
        items = json.loads(m.group(0))
    except (json.JSONDecodeError, ValueError):
        return json.dumps({"traducciones": []})
    traducciones = [
        {
            "id": it["id"],
            "titulo_es": f"[ES] {it['titulo']}",
            "resumen_es": f"[ES] {it.get('resumen', '')}",
        }
        for it in items
    ]
    return json.dumps({"traducciones": traducciones})


def _ejecutor_falla(prompt: str, dir_permitido: str) -> str:
    raise RuntimeError("Fallo simulado del subproceso claude")


def _ejecutor_json_invalido(prompt: str, dir_permitido: str) -> str:
    return "esto no es JSON para nada"


def _ejecutor_respuesta_parcial(prompt: str, dir_permitido: str) -> str:
    """Solo devuelve traducción para el primer ítem."""
    import re

    # Aísla la lista REAL de ítems (va tras "## Lista de ítems"); el prompt también
    # contiene un ejemplo con corchetes en las instrucciones que confundía al regex.
    cola = prompt.partition("## Lista de ítems")[2] or prompt
    m = re.search(r"\[.*?\]", cola, re.DOTALL)
    if not m:
        return json.dumps({"traducciones": []})
    try:
        items = json.loads(m.group(0))
    except (json.JSONDecodeError, ValueError):
        return json.dumps({"traducciones": []})
    if not items:
        return json.dumps({"traducciones": []})
    primer = items[0]
    return json.dumps({
        "traducciones": [{"id": primer["id"], "titulo_es": "[ES] primero", "resumen_es": ""}]
    })


# --------------------------------------------------------------------------- #
# Casos base                                                                    #
# --------------------------------------------------------------------------- #


def test_lista_vacia_devuelve_lista_vacia():
    assert traducir.traducir_items([], ejecutor=_ejecutor_ok) == []


def test_traduccion_correcta():
    items = [
        {"id": "t1", "titulo": "Breaking news", "resumen": "Summary here"},
        {"id": "t2", "titulo": "Sport update", "resumen": ""},
    ]
    resultado = traducir.traducir_items(items, ejecutor=_ejecutor_ok)
    assert len(resultado) == 2
    ids = {r["id"] for r in resultado}
    assert ids == {"t1", "t2"}
    # El ejecutor fake añade "[ES]" al principio.
    t1 = next(r for r in resultado if r["id"] == "t1")
    assert "[ES]" in t1["titulo_es"]
    assert "titulo_es" in t1
    assert "resumen_es" in t1
    # Traducción REAL -> `ok=True` (el daemon la persistirá como `traducido`).
    assert all(r["ok"] is True for r in resultado)


# --------------------------------------------------------------------------- #
# Best-effort ante fallos                                                       #
# --------------------------------------------------------------------------- #


def test_fallo_ejecutor_devuelve_originales():
    items = [
        {"id": "x1", "titulo": "Original title", "resumen": "Original summary"},
    ]
    resultado = traducir.traducir_items(items, ejecutor=_ejecutor_falla)
    assert len(resultado) == 1
    assert resultado[0]["titulo_es"] == "Original title"
    assert resultado[0]["resumen_es"] == "Original summary"
    # Fallback al original -> `ok=False`: el daemon NO lo persiste, reintenta luego.
    assert resultado[0]["ok"] is False


def test_json_invalido_devuelve_originales():
    items = [{"id": "x2", "titulo": "Hello", "resumen": "World"}]
    resultado = traducir.traducir_items(items, ejecutor=_ejecutor_json_invalido)
    assert resultado[0]["titulo_es"] == "Hello"
    assert resultado[0]["ok"] is False


def test_respuesta_parcial_rellena_con_originales(caplog):
    import logging

    items = [
        {"id": "a", "titulo": "A title", "resumen": "A summary"},
        {"id": "b", "titulo": "B title", "resumen": "B summary"},
    ]
    with caplog.at_level(logging.WARNING, logger="keni_consola.dominio.traducir"):
        resultado = traducir.traducir_items(items, ejecutor=_ejecutor_respuesta_parcial)
    assert len(resultado) == 2
    a_res = next(r for r in resultado if r["id"] == "a")
    b_res = next(r for r in resultado if r["id"] == "b")
    # El primer ítem fue traducido.
    assert a_res["titulo_es"] == "[ES] primero"
    assert a_res["ok"] is True
    # El segundo ítem no llegó en la respuesta -> devuelve original (fallback razonable) con
    # `ok=False`, para que el daemon no lo dé por traducido y reintente.
    assert b_res["titulo_es"] == "B title"
    assert b_res["resumen_es"] == "B summary"
    assert b_res["ok"] is False
    # …pero NO silencioso: queda un WARN con el id y la cuenta de ítems sin traducir.
    avisos = [r.message for r in caplog.records if "sin traducción" in r.message]
    assert avisos and "1 de 2" in avisos[0] and "b" in avisos[0]


def test_respuesta_completa_no_deja_warn_de_faltantes(caplog):
    import logging

    items = [{"id": "t1", "titulo": "Breaking news", "resumen": "Summary"}]
    with caplog.at_level(logging.WARNING, logger="keni_consola.dominio.traducir"):
        traducir.traducir_items(items, ejecutor=_ejecutor_ok)
    assert not [r for r in caplog.records if "sin traducción" in r.message]


# --------------------------------------------------------------------------- #
# Truncado de texto largo (el cap por ítem no rompe la funcionalidad)          #
# --------------------------------------------------------------------------- #


def test_texto_largo_no_rompe():
    titulo_largo = "X" * 2000
    resumen_largo = "Y" * 2000
    items = [{"id": "big", "titulo": titulo_largo, "resumen": resumen_largo}]
    # Con el ejecutor que devuelve "[ES] ..." el resultado debe ser válido.
    resultado = traducir.traducir_items(items, ejecutor=_ejecutor_ok)
    assert len(resultado) == 1
    assert "titulo_es" in resultado[0]


def test_construir_prompt_inserta_items_y_contrato():
    # La plantilla viene de la Prompts (inicial): la lista JSON sustituye al marcador (que
    # NO debe quedar crudo) y se conserva el contrato JSON {"traducciones": [...]}.
    p = traducir._construir_prompt('[{"id":"1","titulo":"Hi"}]')
    assert '[{"id":"1","titulo":"Hi"}]' in p
    assert traducir._MARCA_ITEMS not in p
    assert "traducciones" in p


def test_construir_prompt_traduccion_lleva_los_items():
    """El prompt ENCOLADO (job por marca) lleva los ids del lote y el contrato de traducción."""
    p = traducir.construir_prompt_traduccion(
        [{"id": "c1", "titulo": "Foreign", "resumen": "Body"}]
    )
    assert "c1" in p
    assert "traducciones" in p


# --------------------------------------------------------------------------- #
# `construir_procesar_traducir`: post-procesado del JOB (worker), sin BD real   #
# --------------------------------------------------------------------------- #


def test_procesar_traducir_persiste_y_mapea_titulo_original(monkeypatch):
    """El post-procesado parsea la salida del worker y marca cada cluster `traducido` con su
    `titulo_original` (mapeado por id desde el lote)."""
    from keni_consola import repos

    guardados = []
    monkeypatch.setattr(repos, "marcar_cluster_traducido",
                        lambda cid, **kw: guardados.append((cid, kw)) or {"id": cid})
    procesar = traducir.construir_procesar_traducir(
        [{"id": "c1", "titulo": "Foreign one"}, {"id": "c2", "titulo": "Foreign two"}]
    )
    salida = json.dumps({"traducciones": [
        {"id": "c1", "titulo_es": "ES uno", "resumen_es": "R uno"},
        {"id": "c2", "titulo_es": "ES dos", "resumen_es": "R dos"},
    ]})
    res = procesar(salida, None)
    assert res == {"traducidos": 2, "candidatos": 2}
    por_id = dict(guardados)
    assert por_id["c1"]["titulo_es"] == "ES uno"
    assert por_id["c1"]["titulo_original"] == "Foreign one"
    assert por_id["c2"]["resumen_es"] == "R dos"


def test_jobspec_reconstruye_el_procesar_de_traducir(monkeypatch):
    """El worker reconstruye el post-procesado desde el spec (`construir_traducir`)."""
    from keni_consola import repos
    from keni_consola.dominio import jobspec

    guardados = []
    monkeypatch.setattr(repos, "marcar_cluster_traducido",
                        lambda cid, **kw: guardados.append(cid) or {"id": cid})
    spec = jobspec.construir_traducir(
        marca="unotv", originales=[{"id": "c1", "titulo": "Foreign"}]
    )
    procesar = jobspec.reconstruir_procesar({"procesar": spec})
    procesar(json.dumps({"traducciones": [{"id": "c1", "titulo_es": "ES"}]}), None)
    assert guardados == ["c1"]


def test_procesar_traducir_omite_ids_ajenos_y_vacios(monkeypatch):
    """No persiste traducciones de ids fuera del lote ni las que vienen sin `titulo_es` (el cluster
    queda sin marcar -> el limpiador de atascados lo re-abrirá para reintento)."""
    from keni_consola import repos

    guardados = []
    monkeypatch.setattr(repos, "marcar_cluster_traducido",
                        lambda cid, **kw: guardados.append(cid) or {"id": cid})
    procesar = traducir.construir_procesar_traducir([{"id": "c1", "titulo": "Foreign"}])
    salida = json.dumps({"traducciones": [
        {"id": "c1", "titulo_es": ""},            # sin titulo_es -> no se persiste
        {"id": "ajeno", "titulo_es": "ES x"},     # id fuera del lote -> se ignora
    ]})
    res = procesar(salida, None)
    assert res == {"traducidos": 0, "candidatos": 1}
    assert guardados == []


# --------------------------------------------------------------------------- #
# `clusters_extranjeros_sin_traducir` toca la BD REAL (no mock)                 #
# La fixture `cliente` (conftest) aísla el entorno y prepara el esquema de BD.   #
# --------------------------------------------------------------------------- #


def _inicializar_cluster_idioma(
    cid, *, idioma, idiomas=None, traducido=0, estado="nuevo", traduccion_encolada=""
):
    from keni_consola import repos

    repos.upsert_noticia_cluster({
        "id": cid,
        "titulo": f"Cluster {cid}",
        "resumen": "r",
        "marca": "unotv",
        "categoria": "internacional",
        "geo": "US",
        "clave": f"t:{cid}",
        "n_items": 1,
        "n_fuentes": 1,
        "idiomas": [idioma] if idiomas is None else idiomas,
        "senal": 10,
        "score": 0.5,
        "breaking": 0,
        "primer_visto": "2026-06-01T00:00:00+00:00",
        "ultimo_visto": "2026-06-05T12:00:00+00:00",
        "estado": estado,
        "idioma": idioma,
        "traducido": traducido,
        "traduccion_encolada": traduccion_encolada,
    })


def test_clusters_extranjeros_sin_traducir_no_revienta_con_like(cliente):  # noqa: ARG001
    """El selector usa `idioma NOT LIKE 'es%%'`: el `%` literal DEBE ir doblado o psycopg casca.

    Este test lo ejercita contra Postgres de verdad (no mocked como los tests del daemon).
    """
    from keni_consola import repos

    _inicializar_cluster_idioma("en1", idioma="en")  # extranjero sin traducir -> candidato
    _inicializar_cluster_idioma("es1", idioma="es")  # español -> excluido por el NOT LIKE 'es%'
    _inicializar_cluster_idioma("en2", idioma="en", traducido=1)  # ya traducido -> excluido
    _inicializar_cluster_idioma("sin", idioma="")  # idioma vacío SIN español -> candidato (Hueco A)
    # Fuente ya en español: el representante llega con `idioma` vacío pero `idiomas=["es"]`.
    # NO debe traducirse (sería español->español); la tropicalización va en la generación de copy.
    _inicializar_cluster_idioma("eses", idioma="", idiomas=["es"])
    # Cluster mixto con español: contiene un titular en español, así que tampoco entra a traducir.
    _inicializar_cluster_idioma("mix", idioma="", idiomas=["en", "es"])

    # Ventana enorme para que el corte temporal no descarte la inicial; min_score bajo.
    candidatos = repos.clusters_extranjeros_sin_traducir(24 * 365 * 100, min_score=0.0, limite=40)
    ids = {c["id"] for c in candidatos}
    assert "en1" in ids
    assert "es1" not in ids  # el `NOT LIKE 'es%'` filtra el español
    assert "en2" not in ids  # ya traducido
    assert "sin" in ids  # idioma vacío sin español entra a la cola: no se cuela en inglés
    assert "eses" not in ids  # fuente en español (idiomas=["es"]) NO se re-traduce es->es
    assert "mix" not in ids  # un cluster con español ya tiene titular en español: no se traduce


def test_traduccion_encolada_excluye_y_se_re_abre_al_expirar(cliente):  # noqa: ARG001
    """IDEMPOTENCIA del encolado: un cluster con `traduccion_encolada` no es candidato; al marcar el
    lote queda excluido; el limpiador de atascados lo re-abre y el éxito limpia la marca."""
    from keni_consola import repos

    _inicializar_cluster_idioma("ena", idioma="en")
    _inicializar_cluster_idioma("enb", idioma="en")
    ventana = 24 * 365 * 100

    def _ids():
        return {c["id"] for c in repos.clusters_extranjeros_sin_traducir(ventana, limite=40)}

    assert {"ena", "enb"} <= _ids()
    # Marcar el lote (al encolar) los saca de la selección: no se re-encolan.
    assert repos.marcar_clusters_traduccion_encolada(["ena", "enb"]) == 2
    assert _ids().isdisjoint({"ena", "enb"})
    # Marcar de nuevo no re-marca (ya están encolados): idempotente.
    assert repos.marcar_clusters_traduccion_encolada(["ena", "enb"]) == 0
    # El limpiador con un umbral FUTURO re-abre los atascados -> vuelven a ser candidatos.
    assert repos.reparar_traduccion_encolada_atascada("2999-01-01T00:00:00") == 2
    assert {"ena", "enb"} <= _ids()
    # Al traducir uno con éxito, se marca `traducido=1` y se limpia la marca (sale de candidatos).
    repos.marcar_clusters_traduccion_encolada(["ena"])
    repos.marcar_cluster_traducido("ena", titulo_es="ES", resumen_es="r", titulo_original="Foreign")
    refrescado = repos.obtener_noticia_cluster("ena")
    assert refrescado["traducido"] is True
    assert refrescado["traduccion_encolada"] == ""
    assert "ena" not in _ids()



# --------------------------------------------------------------------------- #
# Métricas del ejecutor síncrono (acumulador por hilo, para la actividad IA)    #
# --------------------------------------------------------------------------- #


def test_metricas_de_envelope_extrae_y_tolera():
    """Extrae tokens/coste/duración/turnos del envelope de `claude -p --output-format json`;
    campos ausentes o ilegibles se omiten; sin nada útil devuelve None."""
    envelope = {
        "result": "ok",
        "total_cost_usd": 0.0123,
        "duration_ms": 4200,
        "num_turns": 2,
        "usage": {"input_tokens": 100, "output_tokens": 40},
    }
    m = traducir._metricas_de_envelope(envelope)
    assert m == {
        "tokens_in": 100, "tokens_out": 40,
        "total_cost_usd": 0.0123, "duration_ms": 4200, "num_turns": 2,
    }
    assert traducir._metricas_de_envelope({"result": "ok"}) is None
    assert traducir._metricas_de_envelope({"usage": {"input_tokens": "raro"}}) is None
    assert traducir._metricas_de_envelope("no-dict") is None


def test_metricas_de_envelope_capta_cache_y_modelo_de_model_usage():
    """Con `modelUsage`: tokens y CACHÉ se SUMAN por modelo (no del `usage` de sesión, que en
    multi-modelo solo refleja el último turno) y `modelo` sale de las claves de `modelUsage`."""
    envelope = {
        "result": "ok",
        "total_cost_usd": 0.14,
        "usage": {"input_tokens": 2, "output_tokens": 6},  # sesión: solo el último turno
        "modelUsage": {
            "claude-haiku-4-5-20251001": {
                "inputTokens": 1000, "outputTokens": 200,
                "cacheReadInputTokens": 5000, "cacheCreationInputTokens": 100,
            },
            "claude-sonnet-4-6": {
                "inputTokens": 3000, "outputTokens": 900,
                "cacheReadInputTokens": 18000, "cacheCreationInputTokens": 2000,
            },
        },
    }
    m = traducir._metricas_de_envelope(envelope)
    assert m["tokens_in"] == 4000 and m["tokens_out"] == 1100
    assert m["cache_read"] == 23000 and m["cache_creation"] == 2100
    assert m["modelo"] == "claude-haiku-4-5-20251001, claude-sonnet-4-6"
    assert m["total_cost_usd"] == pytest.approx(0.14)


def test_metricas_de_envelope_cache_y_modelo_de_usage_y_model():
    """Sin `modelUsage`: la caché sale del `usage` agregado y `modelo` del campo `model`."""
    m = traducir._metricas_de_envelope({
        "usage": {"input_tokens": 100, "output_tokens": 40,
                  "cache_read_input_tokens": 7000, "cache_creation_input_tokens": 300},
        "model": "claude-sonnet-4-6",
    })
    assert m["cache_read"] == 7000 and m["cache_creation"] == 300
    assert m["modelo"] == "claude-sonnet-4-6"


# --------------------------------------------------------------------------- #
# Ejecutor real: argv (acotado no-agéntico vs. comportamiento por defecto)      #
# --------------------------------------------------------------------------- #


class _ResClaude:
    """Doble del resultado de `subprocess.run` (envelope JSON mínimo de `claude -p`)."""

    returncode = 0
    stdout = '{"result": "ok"}'
    stderr = ""


def _capturar_argv(monkeypatch):
    """Parchea `shutil.which`/`subprocess.run` y devuelve un dict donde queda el argv capturado."""
    capturado: dict[str, list[str]] = {}
    monkeypatch.setattr(traducir.shutil, "which", lambda _cmd: "/usr/bin/claude")
    monkeypatch.setattr(
        traducir.subprocess, "run",
        lambda argv, **_kw: capturado.update(argv=argv) or _ResClaude(),
    )
    return capturado


def test_ejecutar_claude_json_no_agentico_limita_turnos_y_omite_add_dir(monkeypatch):
    """`max_turns`/`sin_tools` acotan la llamada: `--max-turns 1` y SIN `--add-dir` (sin filesystem)."""
    capturado = _capturar_argv(monkeypatch)
    salida = traducir._ejecutar_claude_json(
        "P", "/tmp/x", modelo="sonnet", max_turns=1, sin_tools=True
    )
    argv = capturado["argv"]
    assert "--max-turns" in argv and argv[argv.index("--max-turns") + 1] == "1"
    assert "--add-dir" not in argv
    assert "/tmp/x" not in argv
    assert salida == "ok"


def test_ejecutar_claude_json_por_defecto_conserva_add_dir_y_sin_tope_de_turnos(monkeypatch):
    """Sin los parámetros nuevos (otros llamantes) el argv es el de siempre: `--add-dir`, sin tope."""
    capturado = _capturar_argv(monkeypatch)
    traducir._ejecutar_claude_json("P", "/tmp/x", modelo="haiku")
    argv = capturado["argv"]
    assert "--add-dir" in argv and argv[argv.index("--add-dir") + 1] == "/tmp/x"
    assert "--max-turns" not in argv


def test_argv_sin_json_schema_no_lleva_el_flag():
    """`construir_argv_claude_json` sin esquema NO añade `--json-schema` (comportamiento intacto)."""
    import json as _json

    argv = traducir.construir_argv_claude_json("P", "/tmp/x", "haiku")
    assert "--json-schema" not in argv
    # El path inline excluye las secciones dinámicas (def ON) igual que el worker, para que el
    # prefijo del system prompt sea byte-idéntico entre llamadas y se LEA caché en vez de re-escribirla.
    assert "--exclude-dynamic-system-prompt-sections" in argv
    _ = _json  # silencia el linter si no se usa abajo


def test_argv_con_json_schema_serializa_y_sube_turnos():
    """Con esquema añade `--json-schema <json>` y, si el tope era <2, lo sube a 2 (turno extra)."""
    import json as _json

    esquema = {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}
    argv = traducir.construir_argv_claude_json("P", "/tmp/x", "haiku", max_turns=1, json_schema=esquema)
    assert "--json-schema" in argv
    serializado = argv[argv.index("--json-schema") + 1]
    assert _json.loads(serializado) == esquema
    # El tope de 1 no ahoga la validación: sube a 2.
    assert argv[argv.index("--max-turns") + 1] == "2"


def test_ejecutar_estructurado_devuelve_structured_output(monkeypatch):
    """`_ejecutar_claude_json_estructurado` devuelve `(result, structured_output)` del envelope."""
    capturado = _capturar_argv(monkeypatch)

    class _Res:
        returncode = 0
        stdout = '{"result": "texto", "structured_output": {"marca": "unotv"}}'
        stderr = ""

    monkeypatch.setattr(traducir.subprocess, "run", lambda argv, **_kw: capturado.update(argv=argv) or _Res())
    texto, estructurado = traducir._ejecutar_claude_json_estructurado(
        "P", "/tmp/x", "haiku", json_schema={"type": "object"}
    )
    assert texto == "texto"
    assert estructurado == {"marca": "unotv"}
    assert "--json-schema" in capturado["argv"]


# --------------------------------------------------------------------------- #
# `traducir_items` con salida estructurada (--json-schema) vs. fallback         #
# --------------------------------------------------------------------------- #


def _ejecutor_estructurado_ok(prompt: str, dir_permitido: str):
    """Ejecutor que devuelve `(texto, structured_output)` con el array `traducciones`.

    El texto libre es BASURA a propósito: si el resultado es correcto, prueba que se usó la
    salida estructurada y NO el parse del texto.
    """
    import re

    cola = prompt.partition("## Lista de ítems")[2] or prompt
    m = re.search(r"\[.*?\]", cola, re.DOTALL)
    items = json.loads(m.group(0)) if m else []
    traducciones = [
        {"id": it["id"], "titulo_es": f"[SO] {it['titulo']}", "resumen_es": ""}
        for it in items
    ]
    return ("basura no parseable", {"traducciones": traducciones})


def test_traducir_items_usa_structured_output():
    """Si el ejecutor devuelve `(texto, {"traducciones": [...]})` se usan las del structured."""
    items = [{"id": "s1", "titulo": "Hello world", "resumen": "x"}]
    resultado = traducir.traducir_items(items, ejecutor=_ejecutor_estructurado_ok)
    assert len(resultado) == 1
    assert resultado[0]["titulo_es"] == "[SO] Hello world"
    assert resultado[0]["ok"] is True


def test_traducir_items_fallback_a_texto_cuando_str():
    """Ejecutor que devuelve solo `str` con JSON parseable -> fallback a `_extraer_traducciones`."""
    items = [{"id": "t1", "titulo": "Breaking news", "resumen": "Summary"}]
    resultado = traducir.traducir_items(items, ejecutor=_ejecutor_ok)
    assert resultado[0]["titulo_es"] == "[ES] Breaking news"
    assert resultado[0]["ok"] is True


def test_traducir_items_tupla_sin_structured_cae_al_texto():
    """`(texto, None)`: sin structured válido, parsea el texto libre (camino histórico)."""

    def _ej(prompt: str, dir_permitido: str):
        return (_ejecutor_ok(prompt, dir_permitido), None)

    items = [{"id": "t1", "titulo": "Breaking news", "resumen": "Summary"}]
    resultado = traducir.traducir_items(items, ejecutor=_ej)
    assert resultado[0]["titulo_es"] == "[ES] Breaking news"
    assert resultado[0]["ok"] is True


def test_traducir_items_structured_invalido_cae_a_originales():
    """structured sin la clave `traducciones` y texto no-JSON -> originales con `ok=False`."""

    def _ej(prompt: str, dir_permitido: str):
        return ("texto no json", {"otra_clave": 123})

    items = [{"id": "x1", "titulo": "Original", "resumen": "Summary"}]
    resultado = traducir.traducir_items(items, ejecutor=_ej)
    assert resultado[0]["titulo_es"] == "Original"
    assert resultado[0]["ok"] is False


def test_acumulador_de_metricas_suma_y_resetea():
    """Las llamadas SUMAN en el acumulador del hilo; `tomar_metricas_acumuladas` devuelve la
    suma y RESETEA (la siguiente toma sin llamadas es None)."""
    traducir.tomar_metricas_acumuladas()  # limpia restos de otros tests del hilo
    traducir._acumular_metricas({"tokens_in": 10, "total_cost_usd": 0.01})
    traducir._acumular_metricas({"tokens_in": 5, "tokens_out": 7, "total_cost_usd": 0.02})
    traducir._acumular_metricas(None)  # no-op
    tomadas = traducir.tomar_metricas_acumuladas()
    assert tomadas["tokens_in"] == 15
    assert tomadas["tokens_out"] == 7
    assert tomadas["total_cost_usd"] == pytest.approx(0.03)
    assert traducir.tomar_metricas_acumuladas() is None


def test_acumulador_une_modelo_sin_sumarlo():
    """Los numéricos se suman; `modelo` (texto) se UNE sin duplicar (no se concatena/suma)."""
    traducir.tomar_metricas_acumuladas()  # limpia restos del hilo
    traducir._acumular_metricas({"tokens_in": 3, "modelo": "haiku"})
    traducir._acumular_metricas({"tokens_in": 4, "modelo": "haiku, sonnet"})
    tomadas = traducir.tomar_metricas_acumuladas()
    assert tomadas["tokens_in"] == 7
    assert tomadas["modelo"] == "haiku, sonnet"
