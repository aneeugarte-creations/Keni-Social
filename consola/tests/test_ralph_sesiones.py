"""Tests de las partes PURAS de `ralph_sesiones`: pool de nombres, parser stream-json y
maquina de estado. Sin subprocess real (esos caminos los cubre la integracion del worker)."""

from __future__ import annotations

import json
import os

from keni_consola import ralph_sesiones as rs


def test_base_escribible_respeta_data_dir(tmp_path, monkeypatch):
    # En el servidor el padre de /repo es la raíz (no escribible): la base debe colgar de
    # KENI_DATA_DIR, no del directorio del repo.
    monkeypatch.setenv("KENI_DATA_DIR", str(tmp_path))
    base = rs._base_escribible("ralph-worktrees", "/repo")
    assert base == str(tmp_path / "ralph-worktrees")
    assert os.path.isdir(base)


def test_dir_trabajo_plano_escribible_bajo_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("KENI_DATA_DIR", str(tmp_path))
    d = rs._dir_trabajo_plano("ziggy")
    assert d.startswith(str(tmp_path))
    assert os.path.isdir(d)


# --------------------------------------------------------------------------- #
# Pool de nombres                                                             #
# --------------------------------------------------------------------------- #


def test_siguiente_nombre_primero_libre():
    assert rs.siguiente_nombre(set()) == rs.POOL_NOMBRES[0]
    assert rs.siguiente_nombre({rs.POOL_NOMBRES[0]}) == rs.POOL_NOMBRES[1]


def test_siguiente_nombre_salta_los_tomados():
    usados = {rs.POOL_NOMBRES[0], rs.POOL_NOMBRES[1]}
    assert rs.siguiente_nombre(usados) == rs.POOL_NOMBRES[2]


def test_siguiente_nombre_sufija_cuando_se_agota_el_pool():
    nombre = rs.siguiente_nombre(set(rs.POOL_NOMBRES))
    assert nombre == f"{rs.POOL_NOMBRES[0]}-2"
    # Y con el primer sufijo tambien tomado, sube el contador.
    nombre2 = rs.siguiente_nombre(set(rs.POOL_NOMBRES) | {f"{rs.POOL_NOMBRES[0]}-2"})
    assert nombre2 == f"{rs.POOL_NOMBRES[0]}-3"


def test_siguiente_nombre_acepta_iterable_no_set():
    # El gestor pasa un generador de nombres en uso, no un set.
    en_uso = (n for n in (rs.POOL_NOMBRES[0],))
    assert rs.siguiente_nombre(en_uso) == rs.POOL_NOMBRES[1]


# --------------------------------------------------------------------------- #
# Linea de entrada stream-json (turno del humano)                            #
# --------------------------------------------------------------------------- #


def test_linea_mensaje_usuario_es_json_valido_con_salto():
    linea = rs.linea_mensaje_usuario("hola mundo")
    assert linea.endswith("\n")
    obj = json.loads(linea)
    assert obj["type"] == "user"
    assert obj["message"]["role"] == "user"
    assert obj["message"]["content"] == [{"type": "text", "text": "hola mundo"}]


def test_linea_mensaje_usuario_preserva_unicode():
    linea = rs.linea_mensaje_usuario("café ñandú")
    # ensure_ascii=False: el acento viaja literal, no escapado.
    assert "café ñandú" in linea
    assert json.loads(linea)["message"]["content"][0]["text"] == "café ñandú"


# --------------------------------------------------------------------------- #
# Maquina de estado pura                                                      #
# --------------------------------------------------------------------------- #


def test_estado_arranque_y_actividad():
    assert rs.estado_para_evento({"type": "system", "subtype": "init"}, rs.ESTADO_IDLE) == rs.ESTADO_ACTIVO
    assert rs.estado_para_evento({"type": "stream_event"}, rs.ESTADO_IDLE) == rs.ESTADO_ACTIVO
    assert rs.estado_para_evento({"type": "assistant"}, rs.ESTADO_ESPERANDO) == rs.ESTADO_ACTIVO


def test_estado_result_ok_pasa_a_esperando():
    ev = {"type": "result", "subtype": "success"}
    assert rs.estado_para_evento(ev, rs.ESTADO_ACTIVO) == rs.ESTADO_ESPERANDO


def test_estado_result_error_pasa_a_error():
    assert rs.estado_para_evento({"type": "result", "is_error": True}, rs.ESTADO_ACTIVO) == rs.ESTADO_ERROR
    assert (
        rs.estado_para_evento({"type": "result", "subtype": "error_max_turns"}, rs.ESTADO_ACTIVO)
        == rs.ESTADO_ERROR
    )


def test_estado_error_es_terminal():
    assert rs.estado_para_evento({"type": "result", "subtype": "success"}, rs.ESTADO_ERROR) == rs.ESTADO_ERROR
    assert rs.estado_para_evento({"type": "stream_event"}, rs.ESTADO_ERROR) == rs.ESTADO_ERROR


def test_estado_evento_irrelevante_conserva():
    assert rs.estado_para_evento({"type": "otra_cosa"}, rs.ESTADO_ESPERANDO) == rs.ESTADO_ESPERANDO


# --------------------------------------------------------------------------- #
# ParserRalph                                                                 #
# --------------------------------------------------------------------------- #


def _delta_texto(texto: str) -> str:
    return json.dumps(
        {"type": "stream_event", "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": texto}}}
    )


def test_parser_text_delta_emite_mensaje_y_pone_activo():
    p = rs.ParserRalph()
    eventos = p.procesar_linea(_delta_texto("Hola"))
    tipos = [e["tipo"] for e in eventos]
    assert "mensaje" in tipos
    # Clave `delta` (contrato del front), no `texto`: el front anexa `data.delta`.
    assert {"tipo": "mensaje", "delta": "Hola"} in eventos
    # Primer delta tambien dispara el cambio de estado a activo.
    assert {"tipo": "estado", "estado": rs.ESTADO_ACTIVO} in eventos
    assert p.estado == rs.ESTADO_ACTIVO
    assert p.texto == "Hola"


def test_parser_acumula_texto_del_turno():
    p = rs.ParserRalph()
    p.procesar_linea(_delta_texto("Hola "))
    p.procesar_linea(_delta_texto("mundo"))
    assert p.texto == "Hola mundo"


def test_parser_result_ok_emite_estado_esperando():
    p = rs.ParserRalph()
    p.procesar_linea(_delta_texto("x"))  # -> activo
    eventos = p.procesar_linea(json.dumps({"type": "result", "subtype": "success"}))
    assert {"tipo": "estado", "estado": rs.ESTADO_ESPERANDO} in eventos
    assert p.estado == rs.ESTADO_ESPERANDO


def test_parser_cierre_de_turno_emite_fin_antes_del_estado():
    # Un turno con texto, al cerrar (result ok), emite `mensaje` con fin:true ANTES del estado:
    # el front cierra la burbuja en curso y luego pasa a esperando.
    p = rs.ParserRalph()
    p.procesar_linea(_delta_texto("respuesta"))  # -> activo, hubo texto
    eventos = p.procesar_linea(json.dumps({"type": "result", "subtype": "success"}))
    fin = next(e for e in eventos if e.get("fin"))
    assert fin["tipo"] == "mensaje" and fin["delta"] == ""
    # El fin precede al cambio de estado (orden de cierre limpio).
    assert eventos.index(fin) < eventos.index(
        {"tipo": "estado", "estado": rs.ESTADO_ESPERANDO}
    )


def test_parser_turno_sin_texto_no_emite_fin():
    # Un turno que no produjo texto del asistente (solo herramientas) no abre burbuja: sin fin.
    p = rs.ParserRalph()
    p.procesar_linea(json.dumps({"type": "system", "subtype": "init"}))  # -> activo, sin texto
    eventos = p.procesar_linea(json.dumps({"type": "result", "subtype": "success"}))
    assert all(e["tipo"] != "mensaje" for e in eventos)
    assert {"tipo": "estado", "estado": rs.ESTADO_ESPERANDO} in eventos


def test_parser_cierre_por_error_emite_fin_si_hubo_texto():
    p = rs.ParserRalph()
    p.procesar_linea(_delta_texto("a medias"))  # -> activo, con texto
    eventos = p.procesar_linea(json.dumps({"type": "result", "is_error": True}))
    fin = next(e for e in eventos if e.get("fin"))
    assert fin["tipo"] == "mensaje" and fin["delta"] == ""
    assert {"tipo": "estado", "estado": rs.ESTADO_ERROR} in eventos


def test_parser_multiturno_separa_turnos_con_fin():
    # Flujo multi-turno reproducido desde el buffer: cada turno debe ser su propia burbuja.
    # Turno 1, turno 2 -> dos `fin` y la secuencia de estados activo/esperando por turno.
    p = rs.ParserRalph()
    secuencia: list[dict] = []
    # Turno 1.
    secuencia += p.procesar_linea(_delta_texto("turno uno"))
    secuencia += p.procesar_linea(json.dumps({"type": "result", "subtype": "success"}))
    # Turno 2 (el humano ya escribio; claude vuelve a emitir).
    secuencia += p.procesar_linea(_delta_texto("turno dos"))
    secuencia += p.procesar_linea(json.dumps({"type": "result", "subtype": "success"}))

    fines = [e for e in secuencia if e.get("fin")]
    assert len(fines) == 2  # un cierre por turno con texto
    deltas = [e["delta"] for e in secuencia if e["tipo"] == "mensaje" and not e.get("fin")]
    assert deltas == ["turno uno", "turno dos"]
    estados = [e["estado"] for e in secuencia if e["tipo"] == "estado"]
    assert estados == [
        rs.ESTADO_ACTIVO,
        rs.ESTADO_ESPERANDO,
        rs.ESTADO_ACTIVO,
        rs.ESTADO_ESPERANDO,
    ]
    assert p.estado == rs.ESTADO_ESPERANDO


def test_parser_nuevo_turno_reinicia_texto():
    p = rs.ParserRalph()
    p.procesar_linea(_delta_texto("primero"))
    # El cierre del turno (result) limpia el acumulador; el siguiente turno arranca en blanco.
    p.procesar_linea(json.dumps({"type": "result", "subtype": "success"}))
    p.procesar_linea(json.dumps({"type": "system", "subtype": "init"}))
    assert p.estado == rs.ESTADO_ACTIVO
    assert p.texto == ""


def test_parser_result_error_marca_error():
    p = rs.ParserRalph()
    eventos = p.procesar_linea(json.dumps({"type": "result", "is_error": True}))
    assert {"tipo": "estado", "estado": rs.ESTADO_ERROR} in eventos
    assert p.estado == rs.ESTADO_ERROR


def test_parser_ignora_basura_y_lineas_vacias():
    p = rs.ParserRalph()
    assert p.procesar_linea("") == []
    assert p.procesar_linea("   ") == []
    assert p.procesar_linea("no es json") == []
    assert p.procesar_linea(json.dumps([1, 2, 3])) == []  # no es un objeto
    assert p.estado == rs.ESTADO_IDLE


def test_parser_thinking_no_se_difunde():
    p = rs.ParserRalph()
    linea = json.dumps(
        {"type": "stream_event", "event": {"type": "content_block_delta", "delta": {"type": "thinking_delta", "thinking": "mmm"}}}
    )
    eventos = p.procesar_linea(linea)
    # El thinking mueve el estado a activo pero NO emite un evento `mensaje`.
    assert all(e["tipo"] != "mensaje" for e in eventos)
    assert p.estado == rs.ESTADO_ACTIVO


# --------------------------------------------------------------------------- #
# argv del subprocess (composicion pura)                                      #
# --------------------------------------------------------------------------- #


def test_construir_argv_flags_clave():
    argv = rs.construir_argv("opus")
    assert argv[0] == "claude"
    assert "-p" in argv
    assert "--input-format" in argv and "stream-json" in argv
    assert "--output-format" in argv
    assert "--include-partial-messages" in argv
    assert "--dangerously-skip-permissions" in argv
    assert argv[argv.index("--model") + 1] == "opus"


def test_construir_argv_modelo_por_defecto_cuando_vacio():
    argv = rs.construir_argv("")
    assert argv[argv.index("--model") + 1] == rs.MODELO_DEF


def test_construir_argv_operativo_veta_fs_y_engancha_mcp():
    # El Ralph operativo NO toca el filesystem y usa el MCP de la app.
    argv = rs.construir_argv("opus", rs.TIPO_OPERATIVO, mcp_config="/tmp/keni.json")
    assert "--disallowed-tools" in argv
    assert {"Bash", "Edit", "Write"} <= set(argv)
    assert argv[argv.index("--mcp-config") + 1] == "/tmp/keni.json"
    assert "--strict-mcp-config" in argv


def test_construir_argv_dev_sin_restricciones():
    # El Ralph de desarrollo trabaja sin sandbox sobre el repo (sin vetos ni MCP).
    argv = rs.construir_argv("opus", rs.TIPO_DEV)
    assert "--disallowed-tools" not in argv
    assert "--mcp-config" not in argv


def test_construir_argv_resume_antepone_resume():
    # `--resume <id>` va justo tras `-p` para reanudar una sesion guardada con memoria intacta.
    argv = rs.construir_argv("opus", resume="sess-1")
    assert argv[:4] == ["claude", "-p", "--resume", "sess-1"]


def test_construir_argv_sin_resume_no_lo_incluye():
    assert "--resume" not in rs.construir_argv("opus")


# --------------------------------------------------------------------------- #
# Captura de session_id y texto completo del turno (reanudacion/persistencia) #
# --------------------------------------------------------------------------- #


def test_parser_captura_session_id_de_system_init():
    p = rs.ParserRalph()
    p.procesar_linea(json.dumps({"type": "system", "subtype": "init", "session_id": "sess-xyz"}))
    assert p.session_id == "sess-xyz"


def test_parser_fin_incluye_texto_completo_del_turno():
    # El evento de cierre `fin` lleva el texto completo del turno en la clave extra `completo`
    # (la usa el gestor para guardar la transcripcion; el front la ignora).
    p = rs.ParserRalph()
    p.procesar_linea(_delta_texto("Hola "))
    p.procesar_linea(_delta_texto("mundo"))
    eventos = p.procesar_linea(json.dumps({"type": "result", "subtype": "success"}))
    fin = next(e for e in eventos if e.get("fin"))
    assert fin["completo"] == "Hola mundo"
    assert fin["delta"] == ""


# --------------------------------------------------------------------------- #
# Persistencia: round-trip a disco y restauracion como DORMIDO                 #
# --------------------------------------------------------------------------- #


def test_persistencia_round_trip_restaura_dormido(tmp_path, monkeypatch):
    monkeypatch.setenv("KENI_DATA_DIR", str(tmp_path))
    g1 = rs.GestorRalph()
    sesion = rs.SesionRalph(
        id="abc",
        nombre="ziggy",
        modelo="opus",
        creado=123.0,
        tipo=rs.TIPO_OPERATIVO,
        session_id="sess-1",
        usuario_id="u1",
        transcripcion=[
            {"autor": "tu", "texto": "hola"},
            {"autor": "ralph", "texto": "que tal"},
        ],
    )
    g1._sesiones[sesion.id] = sesion
    g1._guardar()

    # Otro gestor sobre el MISMO KENI_DATA_DIR restaura la sesion al construirse.
    g2 = rs.GestorRalph()
    rest = g2.obtener("abc")
    assert rest is not None
    assert rest.estado == rs.ESTADO_DORMIDO
    assert rest.proc is None
    assert rest.session_id == "sess-1"
    assert rest.usuario_id == "u1"
    assert rest.transcripcion == sesion.transcripcion
    # La transcripcion se siembra en `eventos` para que el SSE reproduzca el historial.
    assert {"tipo": "mensaje", "autor": "tu", "delta": "hola"} in rest.eventos
    assert {"tipo": "mensaje", "autor": "ralph", "delta": "que tal"} in rest.eventos
    assert rest.eventos[-1] == {"tipo": "estado", "estado": rs.ESTADO_DORMIDO}
    # info() informa el estado dormido al front.
    assert rest.info()["estado"] == rs.ESTADO_DORMIDO


def test_persistencia_omite_sesiones_sin_session_id(tmp_path, monkeypatch):
    # Sin session_id no es resumible: no se persiste (no habria como reanudarla).
    monkeypatch.setenv("KENI_DATA_DIR", str(tmp_path))
    g1 = rs.GestorRalph()
    s = rs.SesionRalph(id="x", nombre="nova", modelo="opus", creado=1.0)
    g1._sesiones[s.id] = s
    g1._guardar()
    g2 = rs.GestorRalph()
    assert g2.obtener("x") is None


def test_kill_borra_la_entrada_persistida(tmp_path, monkeypatch):
    # Borrar el agente desde el front (kill) debe eliminar su entrada del JSON persistido.
    monkeypatch.setenv("KENI_DATA_DIR", str(tmp_path))
    g = rs.GestorRalph()
    s = rs.SesionRalph(id="r1", nombre="ziggy", modelo="opus", creado=0.0, tipo=rs.TIPO_OPERATIVO)
    s.session_id = "sess-1"  # con session_id -> se persiste
    g._sesiones["r1"] = s
    g._guardar()
    datos = json.load(open(rs._ruta_estado(), encoding="utf-8"))
    assert [r["id"] for r in datos["sesiones"]] == ["r1"]
    g.kill("r1")
    datos = json.load(open(rs._ruta_estado(), encoding="utf-8"))
    assert datos["sesiones"] == []


def test_construir_argv_inyecta_persona_dev():
    argv = rs.construir_argv("opus", rs.TIPO_DEV, system_extra=rs._PERSONA_DEV)
    assert "--append-system-prompt" in argv
    assert "promover-main.sh" in argv[argv.index("--append-system-prompt") + 1]


def test_persona_dev_cubre_rol_y_flujo():
    # Sabe quién es (app + bugs/simple), deriva lo complejo a Sugerencias y conoce el promover.
    assert "promover-main.sh" in rs._PERSONA_DEV
    assert "Sugerencias" in rs._PERSONA_DEV
