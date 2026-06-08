"""Tests del sistema de GENERACIONES (trabajos de IA en background, seguibles en vivo).

TODO OFFLINE: NUNCA se llama a `claude` ni a un proveedor de imagen real.

Cubre:
  - `AcumuladorStream` en modo PARCIAL (`--include-partial-messages`): texto token a
    token (`text_delta`), turnos por `message_start`, `thinking` ignorado.
  - Store de generaciones (crear/obtener/actualizar/listar) aislado en tmp.
  - Endpoints `GET /api/generaciones` y `GET /api/generaciones/{id}`.
  - El POST a `/api/texto/lanzar` (prompt salida=piezas) con el lanzador por defecto
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

from keni_consola import generaciones, preferencias
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
    # Web NO se veta por defecto: los prompts de investigacion (brief-tendencias /
    # termometro-mundial) usan WebSearch/WebFetch y comparten este constructor de argv.
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
# veta GLOBAL `Bash Write Edit`. Los flujos de QA/verificación y el copy con auto-verificación
# legítimamente PUEDEN leer una fuente para corroborar datos; no se les limita.


def test_no_existe_endurecer_sin_web(entorno):
    # La constante de veto de red por-callsite se RETIRÓ (era dead code tras relajar la
    # política): ya no debe existir en el dominio de generación.
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


def test_argv_flujos_de_generacion_conservan_la_web(entorno, monkeypatch):
    # Los flujos de generación (copy/QA/hashtags/evergreen/sugerencias) NO pasan ya `endurecer`:
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
# argv de claude: --max-turns desde KENI_CLAUDE_MAX_TURNS (#103, F-T-01)        #
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


def test_ejecutar_lanza_en_background_y_queda_ejecutando(entorno):
    """Con el lanzador por defecto (noop) la generacion queda `ejecutando`, sondeable.

    El copy ya no se lanza por el motor de skills (retirado), sino desde la Biblioteca: un
    prompt `salida=piezas` lanzado con redes encola un trabajo de COPY en background.
    """
    from keni_consola import biblioteca

    prompt = biblioteca.crear("Copy desde nota", tipo="prompt", cuerpo="Convierte la nota.")
    ruta = biblioteca._ruta_de_id(prompt.id)
    ruta.write_text(
        ruta.read_text(encoding="utf-8").replace("tipo: prompt", "tipo: prompt\nsalida: piezas"),
        encoding="utf-8",
    )

    cli = _cliente()  # lanzador de generacion por defecto = noop (no claude)
    r = cli.post(
        "/api/texto/lanzar",
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


# --------------------------------------------------------------------------- #
# #137 INTERINO: tope de cola, cancelacion (mata el arbol), log sin tragar      #
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


@pytest.mark.timeout(20)
def test_lanzar_job_claude_rechaza_cuando_la_cola_esta_llena(entorno, monkeypatch):
    """Cola al tope -> `lanzar_job_claude` lanza ColaLlenaError SINCRONAMENTE (-> 429).

    La admision se decide ANTES de arrancar el hilo: con el cupo agotado, el llamante
    recibe la excepcion (que la API traduce a 429) en vez de apilar otro hilo daemon.
    """
    monkeypatch.setenv("KENI_MAX_JOBS", "1")
    monkeypatch.setenv("KENI_MAX_COLA", "0")
    # Saturamos la admision manualmente (1 slot, 0 cola -> tope 1).
    runner.admitir()
    try:
        gid = generaciones.crear({"tipo": "copy", "marca": _MARCA, "etiqueta": "X"})["id"]
        with pytest.raises(runner.ColaLlenaError):
            _LANZAR_CLAUDE_REAL(
                gid, prompt="hola", cwd=entorno, procesar=lambda s, m: {"ok": True}
            )
        # NO se creo ningun hilo de job extra para este gid (no se encolo).
        with generaciones._HANDLES_LOCK:
            assert gid not in generaciones._HANDLES
    finally:
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
    """Si `procesar` revienta, el fallo se LOGUEA con el job-id (#123) y NO se silencia.

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
    """El log del fallo del job lleva el job-id Y el request-id de quien lo lanzo (#123+#137).

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
# #137 API: 429 cuando la cola esta llena + endpoint de cancelacion           #
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
        "/api/hashtags/sugerir",
        json={"texto": "una nota larga para sugerir", "marca": _MARCA},
    )
    assert r.status_code == 429
    assert "Retry-After" in r.headers
    assert "error" in r.json()


def test_endpoint_cancelar_404_si_no_existe(entorno):
    r = _cliente().post("/api/generaciones/noexiste/cancelar")
    assert r.status_code == 404


def test_endpoint_cancelar_sin_job_en_vuelo_devuelve_el_registro(entorno):
    """Cancelar una generacion ya terminada es idempotente: devuelve el registro tal cual."""
    g = generaciones.crear({"tipo": "copy", "marca": _MARCA, "etiqueta": "X"})
    generaciones.actualizar(g["id"], {"estado": generaciones.ESTADO_COMPLETADO})
    r = _cliente().post(f"/api/generaciones/{g['id']}/cancelar")
    assert r.status_code == 200
    assert r.json()["generacion"]["id"] == g["id"]
