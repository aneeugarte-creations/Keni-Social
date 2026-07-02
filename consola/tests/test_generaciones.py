"""Tests del sistema de GENERACIONES (trabajos de IA en background, seguibles en vivo).

TODO OFFLINE: NUNCA se llama a `claude` ni a un proveedor de imagen real.

Cubre:
  - `AcumuladorStream` en modo PARCIAL (`--include-partial-messages`): texto token a
    token (`text_delta`), turnos por `message_start`, `thinking` ignorado.
  - Store de generaciones (crear/obtener/actualizar/listar) aislado en tmp.
  - Endpoints `GET /api/generaciones` y `GET /api/generaciones/{id}`.
  - El POST a `/api/prompts/lanzar` (prompt salida=piezas) con el lanzador por defecto
    (noop) deja la generacion en `ejecutando` (no bloquea, sin resultado todavia) y sondeable.
  - El lanzador de imagen completa la generacion con su `resultado`.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path

import pytest

from keni_consola import generaciones, media, preferencias, repos
from keni_consola.dominio import runner, stream

from .conftest import _cliente

# Referencia GENUINA al lanzador de claude real (los tests de cancelacion/log lo usan).
# Otros tests crean la app con un lanzador FAKE inyectado (crear_app reasigna el atributo
# de modulo), que persistiria; aqui invocamos el REAL por esta referencia capturada.
_LANZAR_CLAUDE_REAL = generaciones.lanzar_job_claude

_MARCA = "unotv"

# Referencia GENUINA al lanzador de imagen real: otros tests crean la app con un lanzador
# FAKE inyectado (crear_app reasigna el atributo de modulo), que persistiria. Los tests que
# ejercitan el lanzador REAL lo invocan por esta referencia capturada al importar.
_LANZAR_IMAGEN_REAL = generaciones.lanzar_job_imagen


# --------------------------------------------------------------------------- #
# argv de claude: --effort segun preferencias                                 #
# --------------------------------------------------------------------------- #


def test_argv_sin_esfuerzo_no_pasa_effort(entorno):
    argv = generaciones._argv_claude("hola")
    assert "--effort" not in argv
    # Sigue siendo un comando de streaming valido.
    assert argv[:2] == ["claude", "-p"]
    assert "--include-partial-messages" in argv


def test_argv_con_esfuerzo_pasa_effort(entorno):
    preferencias.guardar_esfuerzo("high")
    argv = generaciones._argv_claude("hola")
    i = argv.index("--effort")
    assert argv[i + 1] == "high"


def test_argv_add_dir_para_dirs_permitidos(entorno):
    argv = generaciones._argv_claude("hola", [Path("/tmp/x")])
    # `--add-dir` y la ruta deben ir CONSECUTIVOS (par flag+valor).
    i = argv.index("--add-dir")
    assert argv[i + 1] == "/tmp/x"


def test_argv_sin_dirs_no_anade_add_dir(entorno):
    # Retrocompat: la firma de un solo argumento NO debe meter `--add-dir`.
    argv = generaciones._argv_claude("hola")
    assert "--add-dir" not in argv


def test_argv_incluye_skip_permissions_por_defecto(entorno, monkeypatch):
    # Headless (-p): sin --dangerously-skip-permissions `claude` se cuelga al usar una tool
    # (WebFetch/Read), no hay forma de aprobar el permiso. NO es el flag de skills. Por defecto va.
    monkeypatch.delenv("KENI_CLAUDE_SKIP_PERMISSIONS", raising=False)
    assert "--dangerously-skip-permissions" in generaciones._argv_claude("hola")


def test_argv_skip_permissions_desactivable_por_env(entorno, monkeypatch):
    monkeypatch.setenv("KENI_CLAUDE_SKIP_PERMISSIONS", "0")
    assert "--dangerously-skip-permissions" not in generaciones._argv_claude("hola")


def test_argv_veta_bash_por_defecto(entorno, monkeypatch):
    # Defensa en profundidad anti prompt-injection EN LA RUTA VIVA del worker
    # (`generaciones._argv_claude`): por defecto se veta `Bash` (ejecucion de comandos /
    # exfiltracion de secretos), que ningun flujo de generacion necesita.
    monkeypatch.delenv("KENI_CLAUDE_DISALLOWED_TOOLS", raising=False)
    argv = generaciones._argv_claude("hola")
    assert "--disallowed-tools" in argv
    i = argv.index("--disallowed-tools")
    assert "Bash" in argv[i + 1 :]


def test_argv_veta_write_y_edit_por_defecto(entorno, monkeypatch):
    # Endurecimiento: ningun flujo de generacion escribe ficheros (la salida es texto que
    # parsea el post-procesado), asi que ademas de Bash se vetan Write/Edit por defecto.
    monkeypatch.delenv("KENI_CLAUDE_DISALLOWED_TOOLS", raising=False)
    argv = generaciones._argv_claude("hola")
    i = argv.index("--disallowed-tools")
    assert {"Bash", "Write", "Edit"} <= set(argv[i + 1 :])


def test_argv_no_veta_web_por_defecto(entorno, monkeypatch):
    # Web NO se veta por defecto: el prompt de investigacion (brief-tendencias)
    # usa WebSearch/WebFetch y comparte este constructor de argv.
    monkeypatch.delenv("KENI_CLAUDE_DISALLOWED_TOOLS", raising=False)
    argv = generaciones._argv_claude("hola")
    assert "WebFetch" not in argv
    assert "WebSearch" not in argv


def test_argv_disallowed_tools_endurecible_por_env(entorno, monkeypatch):
    # Un operador puede endurecer el veto (p.ej. tambien Web) por entorno.
    monkeypatch.setenv("KENI_CLAUDE_DISALLOWED_TOOLS", "Bash WebFetch WebSearch")
    argv = generaciones._argv_claude("hola")
    i = argv.index("--disallowed-tools")
    assert {"Bash", "WebFetch", "WebSearch"} <= set(argv[i + 1 :])


# --------------------------------------------------------------------------- #
# Política de RED (WebFetch/WebSearch) por flujo — revisada (regla del dueño)   #
# --------------------------------------------------------------------------- #
#
# El eje de riesgo NO es "copy vs investigación", sino la forma de la SALIDA: un flujo de
# SALIDA ESTRUCTURADA (la digiere el software; al usuario solo se le muestra el resultado
# FINAL renderizado) contiene la exfiltración por el canal de salida aunque ingiera material
# no confiable. Sería ALTO riesgo solo un flujo donde el USUARIO controla el prompt LIBREMENTE
# *y* la salida CRUDA se le devuelve VERBATIM; NINGÚN flujo de generación cumple ese par (todos
# parsean la salida a artefactos). Por eso NINGÚN flujo veta la web por-callsite: queda solo la
# veta GLOBAL `Bash Write Edit`. Los flujos de verificación/verificación y el copy con auto-verificación
# legítimamente PUEDEN leer una fuente para corroborar datos; no se les limita.


def test_no_existe_endurecer_sin_web(entorno):
    from keni_consola.dominio import generar as gen_dom

    assert not hasattr(gen_dom, "ENDURECER_SIN_WEB")


def test_argv_un_endurecer_de_red_seguiria_uniendose_a_lo_global(entorno, monkeypatch):
    # INVARIANTE del constructor de argv (no de un flujo): SI algún job pasara un `endurecer`
    # con veto de red, debe UNIRSE (no reemplazar) a la veta global `Bash Write Edit`. Esto lo
    # usa hoy el job READ-ONLY de importación de parrilla (fuera de este endurecimiento).
    monkeypatch.delenv("KENI_CLAUDE_DISALLOWED_TOOLS", raising=False)
    argv = generaciones._argv_claude(
        "hola", endurecer={"disallowed_tools": ["WebFetch", "WebSearch"]}
    )
    i = argv.index("--disallowed-tools")
    vetadas = set(argv[i + 1 :])
    assert {"Bash", "Write", "Edit", "WebFetch", "WebSearch"} <= vetadas


def test_argv_sin_tools_emite_tools_vacio_y_sin_disallowed(entorno, monkeypatch):
    # Una etapa JSON-in/JSON-out sin herramientas (Decisor/Hashtags/Traducir) pasa
    # `endurecer["sin_tools"]=True`: el run va con `--tools ""` (cero tools, no expone esquema
    # alguno) y NO emite `--disallowed-tools` (no hay nada que vetar) ni `--add-dir`.
    monkeypatch.delenv("KENI_CLAUDE_DISALLOWED_TOOLS", raising=False)
    argv = generaciones._argv_claude(
        "hola",
        [Path("/tmp/x")],
        endurecer={"sin_tools": True, "disallowed_tools": ["WebFetch"]},
    )
    assert "--tools" in argv and argv[argv.index("--tools") + 1] == ""
    assert "--disallowed-tools" not in argv
    assert "--add-dir" not in argv


def test_argv_flujos_de_generacion_conservan_la_web(entorno, monkeypatch):
    # Los flujos de generación (copy/verificación/hashtags/evergreen/sugerencias) NO pasan ya `endurecer`:
    # comparten este constructor de argv SIN veto de red, así que la web sigue disponible
    # (Bash/Write/Edit vetadas por defecto, Web NO).
    monkeypatch.delenv("KENI_CLAUDE_DISALLOWED_TOOLS", raising=False)
    argv = generaciones._argv_claude("hola")
    i = argv.index("--disallowed-tools")
    vetadas = set(argv[i + 1 :])
    assert {"Bash", "Write", "Edit"} <= vetadas
    assert "WebFetch" not in vetadas
    assert "WebSearch" not in vetadas


# --------------------------------------------------------------------------- #
# argv de claude: --max-turns desde KENI_CLAUDE_MAX_TURNS                       #
# --------------------------------------------------------------------------- #


def test_argv_sin_max_turns_no_pasa_la_bandera(entorno, monkeypatch):
    # Sin el env (caso por defecto del piloto), no se topa por turnos.
    monkeypatch.delenv("KENI_CLAUDE_MAX_TURNS", raising=False)
    argv = generaciones._argv_claude("hola")
    assert "--max-turns" not in argv


def test_argv_con_max_turns_pasa_la_bandera_al_subproceso(entorno, monkeypatch):
    # El env valido llega al COMANDO `claude -p` como `--max-turns <n>` (par flag+valor).
    monkeypatch.setenv("KENI_CLAUDE_MAX_TURNS", "8")
    argv = generaciones._argv_claude("hola")
    i = argv.index("--max-turns")
    assert argv[i + 1] == "8"
    # Sigue siendo un comando de streaming valido.
    assert argv[:2] == ["claude", "-p"]


def test_argv_max_turns_invalido_o_cero_se_ignora(entorno, monkeypatch):
    # Tolerante: no numerico o <= 0 no debe meter la bandera (sin tope de turnos).
    monkeypatch.setenv("KENI_CLAUDE_MAX_TURNS", "no-numero")
    assert "--max-turns" not in generaciones._argv_claude("hola")
    monkeypatch.setenv("KENI_CLAUDE_MAX_TURNS", "0")
    assert "--max-turns" not in generaciones._argv_claude("hola")
    monkeypatch.setenv("KENI_CLAUDE_MAX_TURNS", "-3")
    assert "--max-turns" not in generaciones._argv_claude("hola")


# --------------------------------------------------------------------------- #
# Entorno del subproceso: transporta la clave de imagen del ALMACEN (secretos) #
# --------------------------------------------------------------------------- #


def test_entorno_generacion_inyecta_clave_de_imagen_del_almacen(entorno, monkeypatch):
    # secretos.toml es la unica fuente; la skill (plugin) la recibe por variable de entorno.
    from keni_consola import secretos

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    secretos.guardar_clave_imagen("openai", "sk-almacen")
    env = generaciones._entorno_generacion()
    assert env["OPENAI_API_KEY"] == "sk-almacen"


def test_entorno_generacion_mapea_proveedor_a_su_variable(entorno, monkeypatch):
    from keni_consola import secretos

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    secretos.guardar_clave_imagen("gemini", "g-almacen")
    env = generaciones._entorno_generacion()
    assert env["GEMINI_API_KEY"] == "g-almacen"
    assert "OPENAI_API_KEY" not in env  # no inventa otras variables


def test_entorno_generacion_mapea_openrouter(entorno, monkeypatch):
    from keni_consola import secretos

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    secretos.guardar_clave_imagen("openrouter", "sk-or-almacen")
    env = generaciones._entorno_generacion()
    assert env["OPENROUTER_API_KEY"] == "sk-or-almacen"


def test_entorno_generacion_no_pisa_una_variable_ya_puesta(entorno, monkeypatch):
    from keni_consola import secretos

    monkeypatch.setenv("OPENAI_API_KEY", "sk-del-entorno")
    secretos.guardar_clave_imagen("openai", "sk-almacen")
    env = generaciones._entorno_generacion()
    assert env["OPENAI_API_KEY"] == "sk-del-entorno"  # prioridad de lo ya presente


def test_entorno_generacion_sin_clave_no_anade_nada(entorno, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    env = generaciones._entorno_generacion()  # almacen vacio (entorno aislado en tmp)
    assert "OPENAI_API_KEY" not in env
    assert "GEMINI_API_KEY" not in env


def test_entorno_generacion_scrub_secretos_de_infra(entorno, monkeypatch):
    # Los secretos de INFRA (Postgres/S3/Garage/Metricool) NO deben viajar al subproceso
    # `claude -p`: defensa contra exfiltracion si el modelo es prompt-injectado. PERO el
    # token de Claude y PATH SI deben conservarse (la generacion los necesita).
    monkeypatch.setenv("S3_SECRET_KEY", "s3-secreto")
    monkeypatch.setenv("S3_ACCESS_KEY", "s3-acceso")
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pass@db/keni")
    monkeypatch.setenv("POSTGRES_PASSWORD", "pg-secreto")
    monkeypatch.setenv("GARAGE_ADMIN_TOKEN", "garage-secreto")
    monkeypatch.setenv("METRICOOL_TOKEN", "mc-secreto")
    monkeypatch.setenv("MC_USER_ID", "123")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "claude-token")
    env = generaciones._entorno_generacion()
    # Secretos de infra: AUSENTES.
    for fuera in (
        "S3_SECRET_KEY", "S3_ACCESS_KEY", "DATABASE_URL", "POSTGRES_PASSWORD",
        "GARAGE_ADMIN_TOKEN", "METRICOOL_TOKEN", "MC_USER_ID",
    ):
        assert fuera not in env, fuera
    # Lo que la generacion necesita: PRESENTE.
    assert env.get("CLAUDE_CODE_OAUTH_TOKEN") == "claude-token"
    assert "PATH" in env


# --------------------------------------------------------------------------- #
# AcumuladorStream: streaming token a token (eventos `stream_event`)          #
# --------------------------------------------------------------------------- #


def _se(event: dict) -> str:
    """Serializa un `stream_event` NDJSON (modo --include-partial-messages)."""
    return json.dumps({"type": "stream_event", "event": event})


def test_acumulador_streaming_texto_token_a_token():
    acc = stream.AcumuladorStream()
    acc.procesar_linea(_se({"type": "message_start", "message": {"model": "claude-haiku-4-5"}}))
    # thinking NO debe acumularse en el texto del copy.
    acc.procesar_linea(_se({"type": "content_block_delta", "index": 0,
                            "delta": {"type": "thinking_delta", "thinking": "pensando..."}}))
    acc.procesar_linea(_se({"type": "content_block_delta", "index": 1,
                            "delta": {"type": "text_delta", "text": "Hola "}}))
    acc.procesar_linea(_se({"type": "content_block_delta", "index": 1,
                            "delta": {"type": "text_delta", "text": "mundo"}}))
    acc.procesar_linea(_se({"type": "message_delta",
                            "usage": {"input_tokens": 10, "output_tokens": 5}}))

    assert acc.iniciado is True
    assert acc.texto == "Hola mundo"  # solo el texto, no el thinking
    assert "pensando" not in acc.texto
    assert acc.turnos == 1  # un solo message_start
    assert acc.modelo == "claude-haiku-4-5"
    parc = acc.metricas_parciales()
    assert parc is not None and parc.tokens_out == 5


def test_acumulador_fase_avanza_razonando_generando_completado():
    """La fase (en que ETAPA va) avanza con el stream: razonando → generando → completado.

    - Antes de arrancar: "" (aun nada).
    - Tras `message_start` y solo thinking: razonando (no hay texto VISIBLE todavia).
    - Tras el primer `text_delta`: generando (escribiendo el copy).
    - Tras el `result`: completado (terminal).
    """
    acc = stream.AcumuladorStream()
    assert acc.fase() == ""  # aun no arranco
    acc.procesar_linea(_se({"type": "message_start", "message": {}}))
    acc.procesar_linea(_se({"type": "content_block_delta", "index": 0,
                            "delta": {"type": "thinking_delta", "thinking": "pensando..."}}))
    assert acc.fase() == stream.FASE_RAZONANDO  # thinking NO es texto visible
    acc.procesar_linea(_se({"type": "content_block_delta", "index": 1,
                            "delta": {"type": "text_delta", "text": "Hola"}}))
    assert acc.fase() == stream.FASE_GENERANDO
    acc.procesar_linea(json.dumps({"type": "result", "subtype": "success", "result": "Hola",
                                   "usage": {"input_tokens": 1, "output_tokens": 1}}))
    assert acc.fase() == stream.FASE_COMPLETADO


def test_acumulador_parcial_no_recuenta_turnos_desde_assistant():
    """En modo parcial los turnos los cuenta `message_start`; un `assistant` posterior
    (que el CLI tambien emite) NO debe sumar otro turno."""
    acc = stream.AcumuladorStream()
    acc.procesar_linea(_se({"type": "message_start", "message": {}}))
    acc.procesar_linea(_se({"type": "content_block_delta", "index": 0,
                            "delta": {"type": "text_delta", "text": "ok"}}))
    acc.procesar_linea(json.dumps({"type": "assistant",
                                   "message": {"usage": {"input_tokens": 9, "output_tokens": 9}}}))
    assert acc.turnos == 1  # no 2


def test_acumulador_refusal_en_message_delta_marca_error_terminal():
    """Un `stop_reason: "refusal"` en el `message_delta` marca el run en error (no exito vacio)."""
    acc = stream.AcumuladorStream()
    acc.procesar_linea(_se({"type": "message_start", "message": {}}))
    acc.procesar_linea(_se({"type": "message_delta", "delta": {"stop_reason": "refusal"},
                            "usage": {"input_tokens": 3, "output_tokens": 0}}))
    assert acc.stop_reason == "refusal"
    assert acc.error is True
    assert "refusal" in acc.mensaje_error.lower() or "rehus" in acc.mensaje_error.lower()


def test_acumulador_refusal_en_assistant_marca_error():
    """Sin parciales, el `stop_reason` del `assistant.message` tambien dispara el error."""
    acc = stream.AcumuladorStream()
    acc.procesar_linea(json.dumps({"type": "assistant",
                                   "message": {"stop_reason": "refusal",
                                               "usage": {"input_tokens": 1, "output_tokens": 0}}}))
    assert acc.error is True


def test_acumulador_stop_reason_normal_no_marca_error():
    """`stop_reason: end_turn` (o ausente) no es rechazo: sin regresion."""
    acc = stream.AcumuladorStream()
    acc.procesar_linea(_se({"type": "message_start", "message": {}}))
    acc.procesar_linea(_se({"type": "content_block_delta", "index": 0,
                            "delta": {"type": "text_delta", "text": "ok"}}))
    acc.procesar_linea(_se({"type": "message_delta", "delta": {"stop_reason": "end_turn"},
                            "usage": {"input_tokens": 1, "output_tokens": 1}}))
    acc.procesar_linea(json.dumps({"type": "result", "subtype": "success", "result": "ok",
                                   "usage": {"input_tokens": 1, "output_tokens": 1}}))
    assert acc.error is False
    assert acc.stop_reason == "end_turn"
    assert acc.texto == "ok"


# --------------------------------------------------------------------------- #
# Store de generaciones                                                       #
# --------------------------------------------------------------------------- #


def test_store_crear_obtener_actualizar_listar(entorno):
    g = generaciones.crear({"tipo": "copy", "marca": _MARCA, "etiqueta": "Copy desde nota"})
    gid = g["id"]
    assert g["estado"] == "ejecutando"
    assert g["fecha_inicio"]
    assert g["resultado"] is None

    leido = generaciones.obtener(gid)
    assert leido is not None and leido["etiqueta"] == "Copy desde nota"

    generaciones.actualizar(gid, {"estado": "completado", "salida": "hey",
                                  "resultado": {"piezas": [{"red": "x"}]}})
    g2 = generaciones.obtener(gid)
    assert g2["estado"] == "completado"
    assert g2["salida"] == "hey"
    assert g2["resultado"] == {"piezas": [{"red": "x"}]}

    assert any(x["id"] == gid for x in generaciones.listar())
    assert generaciones.obtener("noexiste") is None


def test_listar_pagina_por_indice_sin_parsear_yaml(entorno, monkeypatch):
    """`listar`/`contar` paginan por el INDICE en Postgres, sin escanear los YAML.

    El detalle pesado (prompt/razonamiento) NO viaja en el listado: solo `obtener` (que lee el
    YAML) lo expone. Comprobamos ademas que el camino del listado NO toca `_todas_ordenadas`
    (el escaneo+parse de todos los YAML), que es justo lo que el indice elimina.
    """
    from keni_consola.generaciones import _almacen

    ids = []
    for i in range(3):
        g = generaciones.crear({"tipo": "copy", "marca": _MARCA, "etiqueta": f"G{i}"})
        # El prompt es el cuerpo PESADO: solo debe verse en el detalle, no en el listado.
        generaciones.actualizar(g["id"], {"prompt": "P" * 5000, "razonamiento": "R" * 5000})
        ids.append(g["id"])

    llamadas = {"n": 0}
    real = _almacen._todas_ordenadas
    monkeypatch.setattr(
        _almacen, "_todas_ordenadas",
        lambda: (llamadas.__setitem__("n", llamadas["n"] + 1), real())[1],
    )

    listado = generaciones.listar(limite=None)
    assert llamadas["n"] == 0, "el listado no debe escanear los YAML (pagina por el indice)"
    en_lista = {g["id"] for g in listado}
    assert set(ids) <= en_lista
    # El cuerpo pesado NO viaja en el listado...
    g0 = next(g for g in listado if g["id"] == ids[0])
    assert "prompt" not in g0 and "razonamiento" not in g0
    # ...pero el DETALLE (obtener, que lee el YAML) sí lo trae.
    detalle = generaciones.obtener(ids[0])
    assert detalle["prompt"] == "P" * 5000
    # Conteo por el indice; orden recientes primero por (fecha_inicio, id) DESC — el MISMO
    # criterio que el escaneo YAML previo (a igual fecha_inicio, desempata el id DESC).
    assert generaciones.contar() >= 3
    orden = [g["id"] for g in listado if g["id"] in ids]
    esperado = sorted(ids, key=lambda i: (generaciones.obtener(i)["fecha_inicio"], i), reverse=True)
    assert orden == esperado
    # Filtro por marca via indice.
    assert {g["id"] for g in generaciones.listar(limite=None, marca=_MARCA)} >= set(ids)
    assert generaciones.listar(limite=None, marca="otra-marca-inexistente") == []


def test_listar_backfill_desde_yaml_si_indice_vacio(entorno):
    """Backfill perezoso: con YAML preexistentes y el indice VACIO, `listar` lo repuebla.

    Simula el primer uso tras el deploy (indice recien creado, YAML ya en disco): se purga el
    indice a mano y el siguiente `listar` lo reconstruye desde los YAML (idempotente).
    """
    from keni_consola import db_jobs

    ids = [
        generaciones.crear({"tipo": "copy", "marca": _MARCA, "etiqueta": f"B{i}"})["id"]
        for i in range(3)
    ]
    # Purga el indice (los YAML siguen en disco): estado "primer uso tras deploy".
    con = db_jobs._conectar()
    try:
        con.execute("DELETE FROM generaciones_indice")
        con.commit()
    finally:
        con.close()
    assert db_jobs.indice_generaciones_vacio() is True
    # El listado dispara el backfill desde los YAML y vuelve a verlos todos.
    en_lista = {g["id"] for g in generaciones.listar(limite=None)}
    assert set(ids) <= en_lista
    assert db_jobs.indice_generaciones_vacio() is False


def test_store_fase_se_persiste_y_legado_cae_a_vacio(entorno):
    """`fase` se persiste y se expone; un registro legado (sin fase) la trae como "".

    Migracion suave del esquema: anadir `fase` no rompe registros viejos (default "").
    """
    g = generaciones.crear({"tipo": "copy", "marca": _MARCA, "etiqueta": "X"})
    # Recien creado, sin avance todavia: la fase es "" (no se ha escrito ningun token).
    assert g["fase"] == ""
    generaciones.actualizar(g["id"], {"fase": generaciones.FASE_GENERANDO})
    assert generaciones.obtener(g["id"])["fase"] == generaciones.FASE_GENERANDO
    # Un registro legado (escrito sin `fase`) sigue funcionando: la fase cae a "".
    g2 = generaciones.crear({"tipo": "copy", "marca": _MARCA, "etiqueta": "Legado"})
    assert generaciones.obtener(g2["id"])["fase"] == ""


def test_store_id_invalido_no_escapa(entorno):
    # Un id con separadores / .. no debe resolver (anti-traversal).
    assert generaciones.obtener("../secreto") is None
    assert generaciones.obtener("a/b") is None


# --------------------------------------------------------------------------- #
# Endpoints de sondeo                                                         #
# --------------------------------------------------------------------------- #


def test_get_generacion_404_si_no_existe(entorno):
    r = _cliente().get("/api/generaciones/noexiste")
    assert r.status_code == 404


def test_get_y_listar_generaciones(entorno):
    g = generaciones.crear({"tipo": "copy", "marca": _MARCA, "etiqueta": "X"})
    cli = _cliente()
    r = cli.get(f"/api/generaciones/{g['id']}")
    assert r.status_code == 200
    assert r.json()["generacion"]["id"] == g["id"]
    lista = cli.get("/api/generaciones").json()["generaciones"]
    assert any(x["id"] == g["id"] for x in lista)


def test_stream_404_si_no_existe(entorno):
    r = _cliente().get("/api/generaciones/noexiste/stream")
    assert r.status_code == 404


def test_stream_emite_estado_y_terminal_para_generacion_terminada(entorno):
    """El SSE de una generacion YA terminal emite `estado` + `terminal` y CIERRA solo.

    Con el TestClient se puede leer el cuerpo entero porque el generador acaba en la
    primera vuelta (estado terminal): no hay bucle vivo que cuelgue el test.
    """
    g = generaciones.crear({"tipo": "copy", "marca": _MARCA, "etiqueta": "X"})
    generaciones.actualizar(
        g["id"],
        {
            "estado": generaciones.ESTADO_COMPLETADO,
            "salida": "hola mundo",
            "fecha_fin": generaciones.ahora_iso(),
        },
    )
    cli = _cliente()
    with cli.stream("GET", f"/api/generaciones/{g['id']}/stream") as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        assert r.headers["cache-control"] == "no-cache"
        assert r.headers["x-accel-buffering"] == "no"
        cuerpo = "".join(r.iter_text())
    # Primero la instantanea (`estado`), luego el cierre (`terminal`); ambos llevan
    # la generacion completa con la MISMA forma JSON que `GET /api/generaciones/{id}`.
    assert cuerpo.index("event: estado") < cuerpo.index("event: terminal")
    assert '"estado": "completado"' in cuerpo
    assert '"salida": "hola mundo"' in cuerpo
    assert f'"id": "{g["id"]}"' in cuerpo


def test_stream_error_tambien_es_terminal(entorno):
    """Una generacion en `error` (cancelada/timeout) tambien cierra el stream con `terminal`."""
    g = generaciones.crear({"tipo": "copy", "marca": _MARCA, "etiqueta": "X"})
    generaciones.actualizar(
        g["id"],
        {
            "estado": generaciones.ESTADO_ERROR,
            "motivo": generaciones.MOTIVO_CANCELADO,
            "error": "Cancelada por el usuario.",
            "fecha_fin": generaciones.ahora_iso(),
        },
    )
    with _cliente().stream("GET", f"/api/generaciones/{g['id']}/stream") as r:
        assert r.status_code == 200
        cuerpo = "".join(r.iter_text())
    assert "event: terminal" in cuerpo
    assert '"motivo": "cancelado"' in cuerpo


def test_ejecutar_lanza_en_background_y_queda_ejecutando(entorno):
    """Con el lanzador por defecto (noop) la generacion queda `ejecutando`, sondeable.

    El copy ya no se lanza por el motor de skills (retirado), sino desde la Texto: un
    prompt `salida=piezas` lanzado con redes encola un trabajo de COPY en background.
    """
    from keni_consola import libprompts

    prompt = libprompts.crear("Copy desde nota", tipo="prompt", cuerpo="Convierte la nota.")
    ruta = libprompts._ruta_de_id(prompt.id)
    ruta.write_text(
        ruta.read_text(encoding="utf-8").replace("tipo: prompt", "tipo: prompt\nsalida: piezas"),
        encoding="utf-8",
    )

    cli = _cliente()  # lanzador de generacion por defecto = noop (no claude)
    r = cli.post(
        "/api/prompts/lanzar",
        json={"prompt_id": prompt.id, "marca": _MARCA, "redes": ["x"],
              "target": {"tipo": "contenido", "valor": "una nota"}},
    )
    assert r.status_code == 200
    gen = r.json()["generacion"]
    assert gen["tipo"] == "copy"
    assert gen["estado"] == "ejecutando"
    assert gen["resultado"] is None
    # Sondeable por su id.
    r2 = cli.get(f"/api/generaciones/{gen['id']}")
    assert r2.status_code == 200
    assert r2.json()["generacion"]["estado"] == "ejecutando"


# --------------------------------------------------------------------------- #
# Lanzador de imagen (background, sin red)                                    #
# --------------------------------------------------------------------------- #


def test_lanzar_job_imagen_completa(entorno):
    gid = generaciones.crear({"tipo": "imagen", "marca": "", "etiqueta": "Imagen"})["id"]
    _LANZAR_IMAGEN_REAL(
        gid, generar=lambda: {"id": "x.png", "url": "/api/media/x.png"}
    )
    # El handle se suelta DESPUES de fijar el estado terminal; si sigue, lo esperamos.
    with generaciones._HANDLES_LOCK:
        handle = generaciones._HANDLES.get(gid)
    if handle is not None:
        handle["hilo"].join(timeout=5)
    g = generaciones.obtener(gid)
    assert g["estado"] == "completado"
    assert g["resultado"] == {"id": "x.png", "url": "/api/media/x.png"}


def test_lanzar_job_imagen_error(entorno):
    gid = generaciones.crear({"tipo": "imagen", "marca": "", "etiqueta": "Imagen"})["id"]

    def _falla() -> dict:
        raise RuntimeError("proveedor caído")

    _LANZAR_IMAGEN_REAL(gid, generar=_falla)
    with generaciones._HANDLES_LOCK:
        handle = generaciones._HANDLES.get(gid)
    if handle is not None:
        handle["hilo"].join(timeout=5)
    g = generaciones.obtener(gid)
    assert g["estado"] == "error"
    assert "proveedor" in g["error"].lower()


def _esperar_fin(gid: str) -> None:
    """Espera a que el hilo del job termine (suelta el handle tras el estado terminal)."""
    with generaciones._HANDLES_LOCK:
        handle = generaciones._HANDLES.get(gid)
    if handle is not None:
        handle["hilo"].join(timeout=5)


def test_lanzar_job_imagen_autocataloga_arte_ia(entorno):
    """Una imagen GENERADA por IA (objeto en `generadas/`) se cataloga sola en la galería de
    artes (GLOBAL, tipo='ia') para poder reutilizarla en otros posts/redes."""
    clave = media.guardar_bytes(b"\x89PNG-fake-bytes", ext="png")  # -> generadas/<uuid>.png
    assert clave.startswith("generadas/")
    gid = generaciones.crear({"tipo": "imagen", "marca": "", "etiqueta": "Imagen · Neymar"})["id"]
    _LANZAR_IMAGEN_REAL(gid, generar=lambda: {"id": clave, "url": f"/api/media/{clave}"})
    _esperar_fin(gid)

    assert generaciones.obtener(gid)["estado"] == "completado"
    artes = repos.listar_media_catalogo()
    nuevo = [a for a in artes if a["objeto"].endswith(clave.split("/", 1)[-1])]
    assert len(nuevo) == 1
    arte = nuevo[0]
    assert arte["objeto"].startswith("artes/")  # promovido a la carpeta reusable
    assert arte["tipo"] == "ia"
    assert arte["marca"] == ""  # GLOBAL: visible desde la galería de cualquier marca
    assert arte["titulo"] == "Imagen · Neymar"
    # El `generadas/` original NO se borra (promover COPIA): la pieza que lo use sigue intacta.
    assert media.leer_media(clave) is not None


def test_lanzar_job_imagen_no_cataloga_render(entorno):
    """Un resultado determinista (recorte/composite en `render/`, o una key plana) NO entra en
    la galería: solo se catalogan las imágenes GENERATIVAS (`generadas/`)."""
    gid = generaciones.crear({"tipo": "imagen", "marca": "", "etiqueta": "Editar · recortar"})["id"]
    _LANZAR_IMAGEN_REAL(gid, generar=lambda: {"id": "render/abc.png", "url": "/api/media/render/abc.png"})
    _esperar_fin(gid)
    assert generaciones.obtener(gid)["estado"] == "completado"
    assert repos.listar_media_catalogo() == []


# --------------------------------------------------------------------------- #
# INTERINO: tope de cola, cancelacion (mata el arbol), log sin tragar          #
# --------------------------------------------------------------------------- #


def _vivo(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _esperar_terminal(gid: str, timeout: float = 8.0) -> str:
    """Espera a que la generacion `gid` alcance un estado TERMINAL (no `ejecutando`).

    Mas robusto que mirar el handle: el handle se registra DENTRO del slot (puede tardar)
    y se suelta tras fijar el estado, asi que esperar el estado terminal evita carreras.
    """
    fin = time.monotonic() + timeout
    while time.monotonic() < fin:
        g = generaciones.obtener(gid)
        if g is not None and g["estado"] != generaciones.ESTADO_EJECUTANDO:
            return g["estado"]
        time.sleep(0.05)
    return (generaciones.obtener(gid) or {}).get("estado", "")


def _fake_lanzar_factory_por_intento(scripts: list[list[str]], llamadas: dict):
    """`runner.lanzar_proc` fake que emite un guion NDJSON DISTINTO por llamada (reintentos)."""
    import subprocess as _sp

    def _fake(argv, *, cwd, env=None):  # noqa: ANN001
        i = llamadas["n"]
        llamadas["n"] = i + 1
        lineas = scripts[min(i, len(scripts) - 1)]
        guion = "import sys\n" + "".join(f"print({ln!r}, flush=True)\n" for ln in lineas)
        return _sp.Popen(
            [sys.executable, "-c", guion], cwd=cwd, stdout=_sp.PIPE, stderr=_sp.DEVNULL,
            text=True, bufsize=1, start_new_session=True,
        )

    return _fake


_OK_START = '{"type": "stream_event", "event": {"type": "message_start", "message": {}}}'
_OK_RESULT = (
    '{"type": "result", "subtype": "success", "result": "#uno", '
    '"usage": {"input_tokens": 1, "output_tokens": 1}}'
)
_ERR_TRANSITORIO = (
    '{"type": "result", "subtype": "error", "is_error": true, '
    '"result": "overloaded: the server is overloaded, please try again"}'
)
_ERR_CONTENIDO = (
    '{"type": "result", "subtype": "error", "is_error": true, '
    '"result": "el contenido solicitado viola la politica de uso"}'
)


@pytest.mark.timeout(30)
@pytest.mark.skipif(os.name != "posix", reason="subproceso real")
def test_reintenta_fallo_transitorio_y_completa(entorno, monkeypatch):
    """Un 529/overloaded se REINTENTA con backoff y el job acaba COMPLETADO (no error directo)."""
    from keni_consola.generaciones import _lanzadores

    monkeypatch.setattr(generaciones.shutil, "which", lambda _n: "/usr/bin/claude")
    monkeypatch.setattr(_lanzadores, "_BACKOFF_BASE_S", 0.01)  # sin esperar de verdad
    llamadas = {"n": 0}
    # 1er intento: error transitorio (overloaded). 2do: exito.
    monkeypatch.setattr(
        generaciones.runner, "lanzar_proc",
        _fake_lanzar_factory_por_intento([[_ERR_TRANSITORIO], [_OK_START, _OK_RESULT]], llamadas),
    )
    gid = generaciones.crear({"tipo": "prompt", "marca": _MARCA, "etiqueta": "X"})["id"]
    _LANZAR_CLAUDE_REAL(gid, prompt="p", cwd=entorno, procesar=lambda s, m: {"ok": True})
    assert _esperar_terminal(gid, timeout=15) == generaciones.ESTADO_COMPLETADO
    assert llamadas["n"] == 2, "debio reintentar UNA vez tras el fallo transitorio"


@pytest.mark.timeout(30)
@pytest.mark.skipif(os.name != "posix", reason="subproceso real")
def test_no_reintenta_error_de_contenido(entorno, monkeypatch):
    """Un error de MODELO/CONTENIDO (no transitorio) va a error SIN reintentar (no cambiaria)."""
    from keni_consola.generaciones import _lanzadores

    monkeypatch.setattr(generaciones.shutil, "which", lambda _n: "/usr/bin/claude")
    monkeypatch.setattr(_lanzadores, "_BACKOFF_BASE_S", 0.01)
    llamadas = {"n": 0}
    monkeypatch.setattr(
        generaciones.runner, "lanzar_proc",
        _fake_lanzar_factory_por_intento([[_ERR_CONTENIDO]], llamadas),
    )
    gid = generaciones.crear({"tipo": "prompt", "marca": _MARCA, "etiqueta": "X"})["id"]
    _LANZAR_CLAUDE_REAL(gid, prompt="p", cwd=entorno, procesar=lambda s, m: {"ok": True})
    assert _esperar_terminal(gid, timeout=15) == generaciones.ESTADO_ERROR
    assert llamadas["n"] == 1, "un error de contenido no debe reintentarse"


@pytest.mark.timeout(30)
@pytest.mark.skipif(os.name != "posix", reason="subproceso real")
def test_reintento_respeta_el_tope(entorno, monkeypatch):
    """Tras agotar `KENI_GEN_REINTENTOS` intentos extra de transitorios, queda en error."""
    from keni_consola.generaciones import _lanzadores

    monkeypatch.setenv("KENI_GEN_REINTENTOS", "2")
    monkeypatch.setattr(generaciones.shutil, "which", lambda _n: "/usr/bin/claude")
    monkeypatch.setattr(_lanzadores, "_BACKOFF_BASE_S", 0.01)
    llamadas = {"n": 0}
    # SIEMPRE transitorio: nunca completa; se topa en 1 + 2 reintentos = 3 invocaciones.
    monkeypatch.setattr(
        generaciones.runner, "lanzar_proc",
        _fake_lanzar_factory_por_intento([[_ERR_TRANSITORIO]], llamadas),
    )
    gid = generaciones.crear({"tipo": "prompt", "marca": _MARCA, "etiqueta": "X"})["id"]
    _LANZAR_CLAUDE_REAL(gid, prompt="p", cwd=entorno, procesar=lambda s, m: {"ok": True})
    assert _esperar_terminal(gid, timeout=15) == generaciones.ESTADO_ERROR
    assert llamadas["n"] == 3, "1 intento + 2 reintentos (tope KENI_GEN_REINTENTOS)"


@pytest.mark.timeout(30)
@pytest.mark.skipif(os.name != "posix", reason="subproceso real")
def test_post_procesado_corre_con_fase_guardando_sellada(entorno, monkeypatch):
    """El finalizador sella fase `guardando` ANTES de correr `procesar` (y `completado` despues).

    Ese marcador durable es el que permite al re-reclamo de la cola (`db_jobs.reclamar_job`)
    distinguir un worker muerto DURANTE claude (re-ejecutable) de uno muerto GUARDANDO el
    resultado (no re-ejecutable: los borradores pudieron crearse).
    """
    monkeypatch.setattr(generaciones.shutil, "which", lambda _n: "/usr/bin/claude")
    llamadas = {"n": 0}
    monkeypatch.setattr(
        generaciones.runner, "lanzar_proc",
        _fake_lanzar_factory_por_intento([[_OK_START, _OK_RESULT]], llamadas),
    )
    gid = generaciones.crear({"tipo": "prompt", "marca": _MARCA, "etiqueta": "X"})["id"]
    fases_en_procesar: list[str] = []

    def _procesar(_salida, _metricas):  # noqa: ANN001
        fases_en_procesar.append((generaciones.obtener(gid) or {}).get("fase", ""))
        return {"ok": True}

    _LANZAR_CLAUDE_REAL(gid, prompt="p", cwd=entorno, procesar=_procesar)
    assert _esperar_terminal(gid, timeout=15) == generaciones.ESTADO_COMPLETADO
    assert fases_en_procesar == [generaciones.FASE_GUARDANDO]
    assert generaciones.obtener(gid)["fase"] == generaciones.FASE_COMPLETADO


@pytest.mark.timeout(30)
@pytest.mark.skipif(os.name != "posix", reason="subproceso real")
def test_lanzar_job_claude_no_rechaza_por_tope_de_cola(entorno, monkeypatch):
    """La cola NO tiene tope (R-NO-LIMIT): `lanzar_job_claude` admite aunque ya haya muchos en proceso.

    Antes la admision rechazaba con `ColaLlenaError` al pasar `max_jobs+max_cola`. Hoy nada se
    rechaza por tamano de cola: con varios cupos ya admitidos, lanzar otro job se ADMITE (arranca
    su hilo) y completa, en vez de reventar.
    """
    monkeypatch.setenv("KENI_MAX_JOBS", "1")
    monkeypatch.setattr(generaciones.shutil, "which", lambda _n: "/usr/bin/claude")
    monkeypatch.setattr(
        generaciones.runner, "lanzar_proc",
        _fake_lanzar_factory_por_intento([[_OK_START, _OK_RESULT]], {"n": 0}),
    )
    # Saturamos la admision a mano muy por encima de la concurrencia: la cola no tiene tope.
    for _ in range(5):
        runner.admitir()
    try:
        gid = generaciones.crear({"tipo": "prompt", "marca": _MARCA, "etiqueta": "X"})["id"]
        # NO debe lanzar ColaLlenaError: la cola no tiene tope; el job arranca y completa.
        _LANZAR_CLAUDE_REAL(gid, prompt="hola", cwd=entorno, procesar=lambda s, m: {"ok": True})
        assert _esperar_terminal(gid, timeout=15) == generaciones.ESTADO_COMPLETADO
    finally:
        for _ in range(5):
            runner.liberar_admision()


@pytest.mark.timeout(30)
@pytest.mark.skipif(os.name != "posix", reason="grupos de procesos POSIX")
def test_cancelar_mata_el_arbol_y_marca_cancelado(entorno, monkeypatch):
    """`cancelar` mata el ARBOL del subproceso y deja el registro en `cancelado`.

    Sustituimos `runner.lanzar_proc` por uno que arranca un arbol REAL (padre python +
    hijo que duerme, en su propio grupo) que emite una linea NDJSON y se queda vivo.
    Cancelamos: el arbol debe morir (incluido el hijo) y el estado quedar terminal."""
    monkeypatch.setattr(generaciones.shutil, "which", lambda _n: "/usr/bin/claude")

    pids: dict[str, int] = {}
    # El padre imprime el PID del hijo, emite una linea NDJSON valida y se queda vivo.
    guion = (
        "import subprocess, sys, time\n"
        "h = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)'])\n"
        "sys.stderr.write(str(h.pid) + '\\n'); sys.stderr.flush()\n"
        '''print('{"type": "stream_event", "event": {"type": "message_start", "message": {}}}', flush=True)\n'''
        "time.sleep(300)\n"
    )

    import subprocess as _sp

    def _fake_lanzar(argv, *, cwd, env=None):  # noqa: ANN001
        proc = _sp.Popen(
            [sys.executable, "-c", guion],
            cwd=cwd,
            stdout=_sp.PIPE,
            stderr=_sp.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        pids["hijo"] = int(proc.stderr.readline().strip())
        return proc

    monkeypatch.setattr(generaciones.runner, "lanzar_proc", _fake_lanzar)

    gid = generaciones.crear({"tipo": "copy", "marca": _MARCA, "etiqueta": "Cancelable"})["id"]
    _LANZAR_CLAUDE_REAL(gid, prompt="hola", cwd=entorno, procesar=lambda s, m: {"ok": True})

    # Esperamos a que el proceso este registrado en el handle.
    fin = time.monotonic() + 5
    while time.monotonic() < fin and "hijo" not in pids:
        time.sleep(0.05)
    assert "hijo" in pids and _vivo(pids["hijo"]), "el hijo deberia estar vivo antes de cancelar"

    assert generaciones.cancelar(gid) is True
    assert _esperar_terminal(gid) == generaciones.ESTADO_ERROR

    # El arbol (incluido el hijo) debe haber muerto.
    for _ in range(50):
        if not _vivo(pids["hijo"]):
            break
        time.sleep(0.1)
    assert not _vivo(pids["hijo"]), "cancelar debio matar el arbol entero (incluido el hijo)"

    g = generaciones.obtener(gid)
    assert g["estado"] == generaciones.ESTADO_ERROR
    assert g["motivo"] == generaciones.MOTIVO_CANCELADO


@pytest.mark.timeout(30)
@pytest.mark.skipif(os.name != "posix", reason="subproceso real")
def test_excepcion_en_hilo_de_post_procesado_se_loggea_no_se_traga(entorno, monkeypatch, caplog):
    """Si `procesar` revienta, el fallo se LOGUEA con el job-id y NO se silencia.

    Antes era `except Exception: pass` opaco. Ahora deja traza correlacionable al job y
    el registro queda en `error` (mensaje claro, sin traceback al cliente).
    """
    monkeypatch.setattr(generaciones.shutil, "which", lambda _n: "/usr/bin/claude")

    import subprocess as _sp

    # Subproceso que emite un stream COMPLETO (terminado) para que corra `procesar`.
    lineas = [
        '{"type": "stream_event", "event": {"type": "message_start", "message": {}}}',
        '{"type": "stream_event", "event": {"type": "content_block_delta", "index": 0, '
        '"delta": {"type": "text_delta", "text": "hola"}}}',
        '{"type": "result", "subtype": "success", "result": "hola", '
        '"usage": {"input_tokens": 1, "output_tokens": 1}}',
    ]
    guion = "import sys\n" + "".join(f"print({ln!r}, flush=True)\n" for ln in lineas)

    def _fake_lanzar(argv, *, cwd, env=None):  # noqa: ANN001
        return _sp.Popen(
            [sys.executable, "-c", guion],
            cwd=cwd, stdout=_sp.PIPE, stderr=_sp.DEVNULL, text=True, bufsize=1,
            start_new_session=True,
        )

    monkeypatch.setattr(generaciones.runner, "lanzar_proc", _fake_lanzar)

    def _procesar_revienta(_salida, _metricas):  # noqa: ANN001
        raise RuntimeError("el post-procesado fallo a proposito")

    gid = generaciones.crear({"tipo": "copy", "marca": _MARCA, "etiqueta": "Falla"})["id"]
    with caplog.at_level(logging.ERROR, logger="keni_consola.generaciones"):
        _LANZAR_CLAUDE_REAL(gid, prompt="hola", cwd=entorno, procesar=_procesar_revienta)
        assert _esperar_terminal(gid) == generaciones.ESTADO_ERROR

    g = generaciones.obtener(gid)
    assert g["estado"] == generaciones.ESTADO_ERROR
    assert "no se pudo procesar" in g["error"].lower()
    # El fallo NO se trago: hay un log de ERROR correlacionado al job-id.
    correlacionados = [r for r in caplog.records if gid in r.getMessage()]
    assert correlacionados, "el fallo del post-procesado debe loguearse con el job-id"


def test_fallo_del_job_se_correlaciona_con_el_request_id(entorno, monkeypatch, caplog):
    """El log del fallo del job lleva el job-id Y el request-id de quien lo lanzo.

    `lanzar_job_claude` captura `request_id_actual()` al lanzarse (sincronicamente, dentro
    de la peticion); el hilo corre fuera de ese contexto, asi que el id viaja en el mensaje
    de log. Asi un fallo del trabajo se rastrea hasta la peticion HTTP que lo origino.
    """
    from keni_consola import observabilidad

    monkeypatch.setattr(generaciones.shutil, "which", lambda _n: "/usr/bin/claude")

    import subprocess as _sp

    lineas = [
        '{"type": "stream_event", "event": {"type": "message_start", "message": {}}}',
        '{"type": "result", "subtype": "success", "result": "hola", '
        '"usage": {"input_tokens": 1, "output_tokens": 1}}',
    ]
    guion = "import sys\n" + "".join(f"print({ln!r}, flush=True)\n" for ln in lineas)

    def _fake_lanzar(argv, *, cwd, env=None):  # noqa: ANN001
        return _sp.Popen(
            [sys.executable, "-c", guion],
            cwd=cwd, stdout=_sp.PIPE, stderr=_sp.DEVNULL, text=True, bufsize=1,
            start_new_session=True,
        )

    monkeypatch.setattr(generaciones.runner, "lanzar_proc", _fake_lanzar)

    def _procesar_revienta(_salida, _metricas):  # noqa: ANN001
        raise RuntimeError("falla a proposito")

    gid = generaciones.crear({"tipo": "copy", "marca": _MARCA, "etiqueta": "Req"})["id"]
    # Simulamos el contexto de peticion: fijamos un request-id como lo haria el middleware.
    token = observabilidad.fijar_request_id("rid-job-123")
    try:
        with caplog.at_level(logging.ERROR, logger="keni_consola.generaciones"):
            _LANZAR_CLAUDE_REAL(gid, prompt="hola", cwd=entorno, procesar=_procesar_revienta)
            assert _esperar_terminal(gid) == generaciones.ESTADO_ERROR
    finally:
        observabilidad.restaurar_request_id(token)

    correlacionados = [r for r in caplog.records if gid in r.getMessage() and "rid-job-123" in r.getMessage()]
    assert correlacionados, "el log del job debe llevar el job-id Y el request-id"


# --------------------------------------------------------------------------- #
# API: 429 cuando la cola esta llena + endpoint de cancelacion                #
# --------------------------------------------------------------------------- #


def test_endpoint_responde_429_si_la_cola_esta_llena(entorno):
    """Un endpoint que lanza claude responde 429 (no 500) cuando la cola esta al tope.

    Inyectamos un lanzador que SIEMPRE lanza ColaLlenaError; el manejador central de la
    app lo traduce a 429 + Retry-After (backpressure), en vez de un error generico.
    """
    def _lanzador_cola_llena(gen_id, *, prompt, cwd, procesar, dir_temporal=None):  # noqa: ANN001
        raise runner.ColaLlenaError("La cola de generaciones está llena.")

    cli = _cliente(lanzar_generacion=_lanzador_cola_llena)
    r = cli.post(
        "/api/evergreen/proponer",
        json={"marca": _MARCA},
    )
    assert r.status_code == 429
    assert "Retry-After" in r.headers
    assert "error" in r.json()


def test_cola_llena_no_deja_cadaver_en_actividad(entorno, monkeypatch):
    """Un lanzamiento rechazado por la admisión (cola llena/presupuesto/pausa) NO deja un
    registro en error: el `claude -p` nunca ocurrió y el tick del pipeline reintenta cada
    pocos segundos — dejarlo mintaba un "fallo" nuevo por intento y llenaba la Actividad
    de cadáveres (la avalancha de 'Verificar · Error' del piloto)."""
    from keni_consola.dominio import generar as gen_dom
    from keni_consola.dominio import jobspec

    def _encolar_lleno(gen_id, **_kw):  # noqa: ANN001
        raise runner.ColaLlenaError("La cola de generaciones está llena.")

    monkeypatch.setattr(generaciones, "encolar_job_claude", _encolar_lleno)
    antes = generaciones.contar()
    with pytest.raises(runner.ColaLlenaError):
        gen_dom.lanzar(
            tipo="pipeline", titulo="Verificar de la fuente", marca=_MARCA, prompt="p",
            procesar=lambda salida, metricas: {}, procesar_spec=jobspec.construir_prompt_lib(),
        )
    # El registro del intento se BORRÓ: la Actividad queda limpia (mismo conteo que antes).
    assert generaciones.contar() == antes
    assert all(
        g.get("motivo") != generaciones.MOTIVO_COLA_LLENA for g in generaciones.listar(limite=None)
    )


def test_lanzar_estampa_el_carril_de_la_cuenta_de_la_marca(entorno, monkeypatch):
    """El copy se rutea al carril de la cuenta de su marca: así lo reclama el worker que monta
    sus credenciales (claro-sports -> A, unotv -> B). Sin marca cae a `inferencia`."""
    from keni_consola.dominio import generar as gen_dom
    from keni_consola.dominio import jobspec

    capturado: dict = {}

    def _captura(gen_id, **kw):  # noqa: ANN001
        capturado["spec"] = kw.get("spec")

    monkeypatch.setattr(generaciones, "encolar_job_claude", _captura)

    def _lanzar(marca: str, titulo: str) -> str:
        gen_dom.lanzar(
            tipo="pipeline", titulo=titulo, marca=marca, prompt=f"p-{titulo}",
            procesar=lambda salida, metricas: {}, procesar_spec=jobspec.construir_prompt_lib(),
        )
        return capturado["spec"]["carril"]

    assert _lanzar("claro-sports", "a") == jobspec.CARRIL_CUENTA_A
    assert _lanzar("unotv", "b") == jobspec.CARRIL_CUENTA_B
    assert _lanzar("", "sin") == jobspec.CARRIL_INFERENCIA


def test_lanzar_manual_es_prioridad_manual_aunque_el_tipo_sea_de_fondo(entorno, monkeypatch):
    """Un lanzamiento que dispara una PERSONA (`manual=True`, p. ej. "Empujar al feed") va con
    prioridad MANUAL aunque use un `tipo` de fondo: así no lo corta el nivel SOLO_MANUAL del
    presupuesto ni cede el paso. Sin `manual`, el mismo tipo es trabajo de fondo."""
    from keni_consola.dominio import generar as gen_dom
    from keni_consola.dominio import jobspec

    capturado: dict = {}

    def _captura(gen_id, **kw):  # noqa: ANN001
        capturado["spec"] = kw.get("spec")

    monkeypatch.setattr(generaciones, "encolar_job_claude", _captura)

    def _prioridad(*, manual: bool, titulo: str) -> int:
        gen_dom.lanzar(
            tipo="pipeline", titulo=titulo, marca="unotv", prompt=f"p-{titulo}", manual=manual,
            procesar=lambda salida, metricas: {}, procesar_spec=jobspec.construir_prompt_lib(),
        )
        return jobspec.prioridad(capturado["spec"])

    assert _prioridad(manual=True, titulo="m") == jobspec.PRIORIDAD_MANUAL
    assert _prioridad(manual=False, titulo="f") < jobspec.PRIORIDAD_MANUAL


def test_endpoint_cancelar_404_si_no_existe(entorno):
    r = _cliente().post("/api/generaciones/noexiste/cancelar")
    assert r.status_code == 404


def test_endpoint_cancelar_sin_job_en_proceso_devuelve_el_registro(entorno):
    """Cancelar una generacion ya terminada es idempotente: devuelve el registro tal cual."""
    g = generaciones.crear({"tipo": "copy", "marca": _MARCA, "etiqueta": "X"})
    generaciones.actualizar(g["id"], {"estado": generaciones.ESTADO_COMPLETADO})
    r = _cliente().post(f"/api/generaciones/{g['id']}/cancelar")
    assert r.status_code == 200
    assert r.json()["generacion"]["id"] == g["id"]


# --------------------------------------------------------------------------- #
# Proceso de la maquina (ADR 0011): sello + deduccion                          #
# --------------------------------------------------------------------------- #


def test_proceso_se_sella_y_persiste(entorno):
    """El campo `proceso` se guarda y sobrevive al round-trip (obtener)."""
    g = generaciones.crear({
        "tipo": "pipeline", "marca": _MARCA, "etiqueta": "Verificar · X",
        "proceso": generaciones.PROCESO_INVESTIGACION,
    })
    leido = generaciones.obtener(g["id"])
    assert leido["proceso"] == generaciones.PROCESO_INVESTIGACION
    assert generaciones.proceso_de(leido) == generaciones.PROCESO_INVESTIGACION


def test_proceso_de_deduce_sin_sello():
    """Sin campo `proceso` (registros previos), se deduce de tipo/etiqueta. Funcion pura."""
    inv, prod = generaciones.PROCESO_INVESTIGACION, generaciones.PROCESO_PRODUCCION
    # Marcadores de etapa: ADMITIR/VERIFICAR -> investigacion; REDACTAR/ILUSTRAR -> produccion.
    assert generaciones.proceso_de({"tipo": "pipeline_etapa", "etiqueta": "VERIFICAR · verificación"}) == inv
    assert generaciones.proceso_de({"tipo": "pipeline_etapa", "etiqueta": "ADMITIR · ingesta"}) == inv
    assert generaciones.proceso_de({"tipo": "pipeline_etapa", "etiqueta": "REDACTAR · copy"}) == prod
    # Generacion real `pipeline`: la verificación ("Verificar · ...") es investigacion; el resto, no.
    assert generaciones.proceso_de({"tipo": "pipeline", "etiqueta": "Verificar · t"}) == inv
    assert generaciones.proceso_de({"tipo": "pipeline", "etiqueta": "Titular · UnoTV"}) == prod
    # Trabajo de produccion (copy/imagen/manual) y lo desconocido -> produccion.
    assert generaciones.proceso_de({"tipo": "copy", "etiqueta": "Copy"}) == prod
    assert generaciones.proceso_de({}) == prod
    # El sello SIEMPRE manda sobre la deduccion.
    assert generaciones.proceso_de({"tipo": "copy", "proceso": inv}) == inv


# --------------------------------------------------------------------------- #
# argv de claude: --exclude-dynamic-system-prompt-sections (M5, def ON)         #
# --------------------------------------------------------------------------- #


def test_argv_excluye_secciones_dinamicas_por_defecto(entorno, monkeypatch):
    # El copy no pasa --system-prompt: por defecto excluimos las secciones dinamicas.
    monkeypatch.delenv("KENI_CLAUDE_EXCLUDE_DYNAMIC_SECTIONS", raising=False)
    assert "--exclude-dynamic-system-prompt-sections" in generaciones._argv_claude("hola")


def test_argv_secciones_dinamicas_reactivables_por_env(entorno, monkeypatch):
    # Un valor falsy apaga el flag (vuelven las secciones dinamicas).
    monkeypatch.setenv("KENI_CLAUDE_EXCLUDE_DYNAMIC_SECTIONS", "0")
    assert "--exclude-dynamic-system-prompt-sections" not in generaciones._argv_claude("hola")


# --------------------------------------------------------------------------- #
# argv de claude: --system-prompt (linea editorial estable del copy)            #
# --------------------------------------------------------------------------- #


def test_argv_sin_system_prompt_por_defecto(entorno):
    # Sin `endurecer["system_prompt"]` no se añade la flag (flujos que no separan el system).
    assert "--system-prompt" not in generaciones._argv_claude("hola")


def test_argv_system_prompt_desde_endurecer(entorno):
    # El copy pasa la linea editorial estable via `endurecer["system_prompt"]` -> `--system-prompt`.
    argv = generaciones._argv_claude("hola", endurecer={"system_prompt": "LINEA EDITORIAL"})
    assert "--system-prompt" in argv
    assert argv[argv.index("--system-prompt") + 1] == "LINEA EDITORIAL"


def test_argv_system_prompt_vacio_no_añade_flag(entorno):
    # "" / ausente = no se añade (se comporta como antes).
    assert "--system-prompt" not in generaciones._argv_claude("hola", endurecer={"system_prompt": ""})


# --------------------------------------------------------------------------- #
# argv de claude: --no-session-persistence (M4, def: SI añadir la flag)         #
# --------------------------------------------------------------------------- #


def test_argv_no_persiste_sesion_por_defecto(entorno, monkeypatch):
    # El copy es one-shot: por defecto NO persistimos la sesion (se añade la flag).
    monkeypatch.delenv("KENI_CLAUDE_SESSION_PERSISTENCE", raising=False)
    assert "--no-session-persistence" in generaciones._argv_claude("hola")


def test_argv_persistencia_de_sesion_reactivable_por_env(entorno, monkeypatch):
    # Un valor truthy reactiva la persistencia (NO se añade la flag).
    monkeypatch.setenv("KENI_CLAUDE_SESSION_PERSISTENCE", "1")
    assert "--no-session-persistence" not in generaciones._argv_claude("hola")


# --------------------------------------------------------------------------- #
# argv de claude: --fallback-model (M1)                                        #
# --------------------------------------------------------------------------- #


def test_argv_sin_fallback_no_pasa_la_bandera(entorno, monkeypatch):
    # Sin el env (caso por defecto), no se pasa --fallback-model.
    monkeypatch.delenv("KENI_CLAUDE_FALLBACK_MODEL", raising=False)
    assert "--fallback-model" not in generaciones._argv_claude("hola")


def test_argv_con_fallback_pasa_la_lista_en_un_solo_flag(entorno, monkeypatch):
    # El CLI acepta varios modelos en UN solo --fallback-model <lista> (CSV normalizado).
    monkeypatch.setenv("KENI_CLAUDE_FALLBACK_MODEL", "claude-sonnet-4-6, claude-haiku-4")
    argv = generaciones._argv_claude("hola")
    i = argv.index("--fallback-model")
    assert argv[i + 1] == "claude-sonnet-4-6,claude-haiku-4"


def test_argv_fallback_omitido_si_el_job_fija_modelo(entorno, monkeypatch):
    # Si el job fija su propio --model (p.ej. Haiku para parsing), se respeta su eleccion:
    # el fallback GLOBAL NO se añade.
    monkeypatch.setenv("KENI_CLAUDE_FALLBACK_MODEL", "claude-sonnet-4-6")
    argv = generaciones._argv_claude("hola", endurecer={"modelo": "claude-haiku-4"})
    assert "--fallback-model" not in argv
    i = argv.index("--model")
    assert argv[i + 1] == "claude-haiku-4"


# --------------------------------------------------------------------------- #
# Clasificacion: un idle-kill cuenta como fallo TRANSITORIO (M2)                #
# --------------------------------------------------------------------------- #


def test_es_fallo_transitorio_clasifica_un_idle_kill_como_transitorio():
    # Al matar por idle, returncode != 0 (-9 = SIGKILL) y el acumulador NO esta terminado:
    # `_es_fallo_transitorio` debe devolver True (la CLI murio sin entregar result -> reintentable).
    from keni_consola.dominio import stream
    from keni_consola.generaciones._lanzadores import _es_fallo_transitorio

    acumulador = stream.AcumuladorStream()  # ni terminado ni error: el stream se corto
    assert _es_fallo_transitorio(acumulador, -9) is True
    # Un cierre limpio (returncode 0) sin result NO es transitorio.
    assert _es_fallo_transitorio(acumulador, 0) is False
