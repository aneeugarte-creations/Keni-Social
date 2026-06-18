"""Tests del dominio PURO de la importacion de parrilla (sin tocar DB ni red).

Cubre: extraccion del bloque JSON de la salida de claude (fences, dict envoltorio, prefijos),
validacion estricta contra el contexto RANGO (fecha valida SIN limite de rango, franja por
NOMBRE de slot, miembro/turno que existen, enums), idempotencia por persona y deteccion de
conflictos (turno desaparecido) y la re-validacion de operaciones ya parseadas. Todo
`dominio.parrilla_import`, ni una sola conexion a Postgres.
"""

from __future__ import annotations

from keni_consola.dominio import parrilla_import as pi
from keni_consola.dominio import parrilla_import_job as pij


# Mapa id->nombre de las franjas existentes (de cualquier semana del rango).
_FRANJAS_NOMBRE = {"fr-manana": "Mañana", "fr-tarde": "Tarde"}


def _ctx(*, turnos=None, eventos=None) -> pi.Contexto:
    return pi.Contexto(
        miembros={"u1": "Luis", "u2": "Ana"},
        nombres_franja={"Mañana", "Tarde"},
        turnos=turnos or [],
        franjas_nombre=_FRANJAS_NOMBRE,
        eventos=eventos or [],
    )


# --------------------------------------------------------------------------- #
# Extraccion del bloque JSON                                                  #
# --------------------------------------------------------------------------- #


def test_extrae_lista_cruda():
    assert pi.extraer_bloque_json('[{"tipo": "crear_evento"}]') == [{"tipo": "crear_evento"}]


def test_extrae_dict_envoltorio_operaciones():
    txt = '{"operaciones": [{"tipo": "crear_turno"}]}'
    assert pi.extraer_bloque_json(txt) == [{"tipo": "crear_turno"}]


def test_extrae_de_bloque_cercado_con_prosa_alrededor():
    txt = (
        "Claro, aquí están las operaciones:\n\n"
        '```json\n{"operaciones": [{"tipo": "crear_evento"}]}\n```\n'
        "Espero que te sirva."
    )
    assert pi.extraer_bloque_json(txt) == [{"tipo": "crear_evento"}]


def test_extrae_ultimo_bloque_cuando_hay_varios():
    txt = (
        "```json\n[]\n```\n"
        "pensándolo mejor:\n"
        '```json\n[{"tipo": "crear_turno"}]\n```'
    )
    assert pi.extraer_bloque_json(txt) == [{"tipo": "crear_turno"}]


def test_extrae_none_si_no_hay_json():
    assert pi.extraer_bloque_json("no hay nada estructurado aquí") is None
    assert pi.extraer_bloque_json("") is None


def test_contrato_estricto_solo_acepta_operaciones():
    assert pi.extraer_bloque_json('{"ops": [{"tipo": "crear_evento"}]}') is None
    assert pi.extraer_bloque_json('{"operations": [{"tipo": "crear_evento"}]}') is None
    assert pi.extraer_bloque_json(
        '```json\n{"ops": [{"tipo": "crear_evento"}]}\n```'
    ) is None


# --------------------------------------------------------------------------- #
# crear_evento                                                                #
# --------------------------------------------------------------------------- #


def test_crear_evento_valido():
    txt = (
        '{"operaciones": [{"tipo": "crear_evento", "fecha": "2026-06-03", '
        '"hora": "16:00", "titulo": "Final Liga MX", "prioridad": "alta"}]}'
    )
    validas, errores = pi.parsear_y_validar(txt, _ctx())
    assert errores == []
    assert len(validas) == 1
    assert validas[0]["tipo"] == "crear_evento"
    assert validas[0]["titulo"] == "Final Liga MX"


def test_crear_evento_fecha_en_otra_semana_es_valida():
    txt = '[{"tipo": "crear_evento", "fecha": "2026-06-20", "titulo": "X"}]'
    validas, errores = pi.parsear_y_validar(txt, _ctx())
    assert errores == []
    assert len(validas) == 1


def test_crear_evento_fecha_lejana_es_valida_sin_limite():
    # SIN límite de rango: una fecha lejana (otro año) es válida mientras parsee como ISO.
    txt = '[{"tipo": "crear_evento", "fecha": "2099-01-01", "titulo": "X"}]'
    validas, errores = pi.parsear_y_validar(txt, _ctx())
    assert errores == []
    assert len(validas) == 1


def test_crear_evento_fecha_invalida_es_error():
    txt = '[{"tipo": "crear_evento", "fecha": "no-es-fecha", "titulo": "X"}]'
    validas, errores = pi.parsear_y_validar(txt, _ctx())
    assert validas == []
    assert "Fecha inválida" in errores[0]["error"]


def test_crear_evento_hora_invalida_es_error():
    txt = '[{"tipo": "crear_evento", "fecha": "2026-06-03", "titulo": "X", "hora": "25:99"}]'
    validas, errores = pi.parsear_y_validar(txt, _ctx())
    assert validas == []
    assert "Hora inválida" in errores[0]["error"]


def test_crear_evento_hora_nula_es_valida():
    txt = '[{"tipo": "crear_evento", "fecha": "2026-06-03", "titulo": "X", "hora": null}]'
    validas, errores = pi.parsear_y_validar(txt, _ctx())
    assert errores == []
    assert validas[0]["hora"] is None


def test_crear_evento_enum_invalido_es_error():
    txt = (
        '[{"tipo": "crear_evento", "fecha": "2026-06-03", "titulo": "X", '
        '"tipo_cobertura": "inventado"}]'
    )
    validas, errores = pi.parsear_y_validar(txt, _ctx())
    assert validas == []
    assert "Tipo de cobertura inválido" in errores[0]["error"]


# --------------------------------------------------------------------------- #
# crear_tarea (modo tareas)                                                   #
# --------------------------------------------------------------------------- #


def test_crear_tarea_valida():
    txt = (
        '{"operaciones": [{"tipo": "crear_tarea", "titulo": "Editar el clip del gol", '
        '"detalle": "subir a IG", "prioridad": "alta", "fecha_objetivo": "2026-06-20"}]}'
    )
    validas, errores = pi.parsear_y_validar(txt, _ctx())
    assert errores == []
    assert len(validas) == 1
    assert validas[0]["tipo"] == "crear_tarea"
    assert validas[0]["titulo"] == "Editar el clip del gol"
    assert validas[0]["fecha_objetivo"] == "2026-06-20"


def test_crear_tarea_sin_fecha_es_valida():
    # Un encargo puede no tener deadline: `fecha_objetivo` es opcional.
    txt = '[{"tipo": "crear_tarea", "titulo": "Revisar el copy del post"}]'
    validas, errores = pi.parsear_y_validar(txt, _ctx())
    assert errores == []
    assert len(validas) == 1
    assert validas[0]["tipo"] == "crear_tarea"


def test_crear_tarea_sin_titulo_es_error():
    txt = '[{"tipo": "crear_tarea", "titulo": "   "}]'
    validas, errores = pi.parsear_y_validar(txt, _ctx())
    assert validas == []
    assert "título" in errores[0]["error"]


def test_crear_tarea_fecha_invalida_es_error():
    txt = '[{"tipo": "crear_tarea", "titulo": "X", "fecha_objetivo": "no-es-fecha"}]'
    validas, errores = pi.parsear_y_validar(txt, _ctx())
    assert validas == []
    assert "Fecha inválida" in errores[0]["error"]


def test_prompt_modo_tareas_pide_crear_tarea_no_eventos():
    p = pij.componer_prompt(
        ctx=_ctx(), texto_documento="editar clip, subir fotos del entreno", modo="tareas"
    )
    assert "crear_tarea" in p
    assert "crear_evento" not in p  # el modo tareas NO mezcla eventos
    assert "editar clip" in p  # el texto fuente queda embebido


def test_prompt_modo_tareas_con_web_identifica_el_evento_pero_emite_crear_tarea():
    # FRASE escrita a mano en la pestaña Tarea (`permitir_web=True`): identifica el evento real con
    # la web (igual que eventos) pero la salida sigue siendo `crear_tarea` con `fecha_objetivo`.
    p = pij.componer_prompt(
        ctx=_ctx(), texto_documento="la velada del año vi", modo="tareas", permitir_web=True
    )
    assert "crear_tarea" in p                  # forma de salida: tarea, no evento
    assert "crear_evento" not in p
    assert "WebSearch" in p                     # identifica/data el evento online
    assert "fecha_objetivo" in p                # la fecha real va en el deadline de la tarea
    assert "la velada del año vi" in p
    # No arrastra el corte de transcripción cerrada que impedía buscar.
    assert "NO abras ni leas ningún fichero ni uses herramientas" not in p


def test_prompt_modo_tareas_sin_web_sigue_siendo_encargo_cerrado():
    # Sin `permitir_web` (documento/enlace transcrito): el modo tareas NO menciona la web.
    p = pij.componer_prompt(
        ctx=_ctx(), texto_documento="editar clip, subir fotos", modo="tareas"
    )
    assert "WebSearch" not in p
    assert "NO abras ni leas ningún fichero ni uses herramientas" in p


# --------------------------------------------------------------------------- #
# crear_turno                                                                 #
# --------------------------------------------------------------------------- #


def test_crear_turno_valido():
    txt = (
        '[{"tipo": "crear_turno", "fecha": "2026-06-02", "franja": "Mañana", '
        '"miembro_id": "u1"}]'
    )
    validas, errores = pi.parsear_y_validar(txt, _ctx())
    assert errores == []
    assert validas[0]["miembro_id"] == "u1"
    assert validas[0]["franja"] == "Mañana"


def test_crear_turno_franja_normaliza_mayusculas_espacios():
    # El nombre de slot se compara case/space-insensitive.
    txt = (
        '[{"tipo": "crear_turno", "fecha": "2026-06-02", "franja": "  mañana ", '
        '"miembro_id": "u1"}]'
    )
    validas, errores = pi.parsear_y_validar(txt, _ctx())
    assert errores == []
    assert len(validas) == 1


def test_crear_turno_franja_nueva_es_valida_y_acepta_horario():
    # PERMISIVO: una franja que no está en la plantilla (p.ej. "Madrugada", o una 3ª franja del
    # día) es válida; se crea al aplicar. Acepta horario opcional de la franja.
    txt = (
        '[{"tipo": "crear_turno", "fecha": "2026-06-02", "franja": "Madrugada", '
        '"franja_inicio": "00:00", "franja_fin": "06:00", "miembro_id": "u1"}]'
    )
    validas, errores = pi.parsear_y_validar(txt, _ctx())
    assert errores == []
    assert len(validas) == 1
    assert validas[0]["franja"] == "Madrugada"
    assert validas[0]["franja_inicio"] == "00:00"


def test_crear_turno_miembro_inventado_es_error():
    txt = (
        '[{"tipo": "crear_turno", "fecha": "2026-06-02", "franja": "Mañana", '
        '"miembro_id": "fantasma"}]'
    )
    validas, errores = pi.parsear_y_validar(txt, _ctx())
    assert validas == []
    assert "no existe en el equipo" in errores[0]["error"]


# --------------------------------------------------------------------------- #
# modificar_turno                                                             #
# --------------------------------------------------------------------------- #


def _turno(tid="t1", fecha="2026-06-02", franja="fr-manana", miembro="u1", estado="propuesto"):
    return {
        "id": tid, "fecha": fecha, "franja_id": franja, "miembro_id": miembro,
        "miembro_nombre": "Luis", "estado": estado, "override": False,
        "motivo": "", "nota_relevo": "",
    }


def test_modificar_turno_valido():
    txt = '[{"tipo": "modificar_turno", "turno_id": "t1", "cambios": {"miembro_id": "u2"}}]'
    validas, errores = pi.parsear_y_validar(txt, _ctx(turnos=[_turno()]))
    assert errores == []
    assert validas[0]["cambios"]["miembro_id"] == "u2"


def test_modificar_turno_inexistente_es_error():
    txt = '[{"tipo": "modificar_turno", "turno_id": "nope", "cambios": {"estado": "aprobado"}}]'
    validas, errores = pi.parsear_y_validar(txt, _ctx(turnos=[_turno()]))
    assert validas == []
    assert "ya no existe" in errores[0]["error"]


def test_modificar_turno_devuelve_franja_por_nombre():
    # `actual.franja` se expone como NOMBRE de slot (resuelto via franjas_nombre), no como id.
    ctx = _ctx(turnos=[_turno(tid="t1", franja="fr-manana")])
    op = {"tipo": "modificar_turno", "turno_id": "t1", "cambios": {"estado": "aprobado"}}
    info = pi.calcular_conflicto(op, ctx)
    assert info["actual"]["franja"] == "Mañana"


def test_modificar_turno_estado_invalido_es_error():
    txt = '[{"tipo": "modificar_turno", "turno_id": "t1", "cambios": {"estado": "raro"}}]'
    validas, errores = pi.parsear_y_validar(txt, _ctx(turnos=[_turno()]))
    assert validas == []
    assert "Estado inválido" in errores[0]["error"]


def test_modificar_turno_sin_cambios_es_error():
    txt = '[{"tipo": "modificar_turno", "turno_id": "t1", "cambios": {}}]'
    validas, errores = pi.parsear_y_validar(txt, _ctx(turnos=[_turno()]))
    assert validas == []
    assert "ningún cambio" in errores[0]["error"]


# --------------------------------------------------------------------------- #
# Esquema / discriminador                                                     #
# --------------------------------------------------------------------------- #


def test_tipo_desconocido_es_error_de_esquema():
    txt = '[{"tipo": "borrar_todo"}]'
    validas, errores = pi.parsear_y_validar(txt, _ctx())
    assert validas == []
    assert len(errores) == 1


def test_campo_extra_se_rechaza():
    txt = (
        '[{"tipo": "crear_turno", "fecha": "2026-06-02", "franja": "Mañana", '
        '"miembro_id": "u1", "borrar_db": true}]'
    )
    validas, errores = pi.parsear_y_validar(txt, _ctx())
    assert validas == []
    assert len(errores) == 1


def test_operacion_no_objeto_es_error_sin_romper_el_resto():
    txt = '["soy una cadena", {"tipo": "crear_turno", "fecha": "2026-06-02", ' \
        '"franja": "Mañana", "miembro_id": "u1"}]'
    validas, errores = pi.parsear_y_validar(txt, _ctx())
    assert len(validas) == 1
    assert len(errores) == 1
    assert errores[0]["indice"] == 0


def test_sin_json_devuelve_error_indice_cero():
    validas, errores = pi.parsear_y_validar("nada útil", _ctx())
    assert validas == []
    assert errores[0]["indice"] == 0


# --------------------------------------------------------------------------- #
# Conflictos                                                                  #
# --------------------------------------------------------------------------- #


def test_otra_persona_en_franja_ocupada_no_es_conflicto():
    # Una franja de tiempo (Mañana/Tarde/Noche) lleva VARIAS personas: dar de alta a OTRA persona
    # en una franja que ya ocupa u1 es alta nueva, no conflicto ni idempotencia.
    ctx = _ctx(turnos=[_turno(tid="t1", fecha="2026-06-02", franja="fr-manana", miembro="u1")])
    op = {"tipo": "crear_turno", "fecha": "2026-06-02", "franja": "Mañana", "miembro_id": "u2"}
    info = pi.calcular_conflicto(op, ctx)
    assert info["conflicto"] is False
    assert info["ya_existe"] is False


def test_ya_existe_crear_turno_misma_persona_no_es_conflicto():
    # La MISMA persona ya tiene ese (fecha, franja): «ya está», ni conflicto ni alta. Es lo que
    # evita el muro de rojos al re-subir una parrilla sobre una semana ya hecha.
    ctx = _ctx(turnos=[_turno(tid="t1", fecha="2026-06-02", franja="fr-manana", miembro="u1")])
    op = {"tipo": "crear_turno", "fecha": "2026-06-02", "franja": "Mañana", "miembro_id": "u1"}
    info = pi.calcular_conflicto(op, ctx)
    assert info["ya_existe"] is True
    assert info["conflicto"] is False


def test_ya_existe_crear_turno_no_lo_tapa_otro_ocupante_de_la_misma_franja():
    # La franja tiene a u1 Y a u2: aunque el mapa de celda guarde uno solo, la idempotencia mira
    # el conjunto por PERSONA, así que u2 (que SÍ está) sale «ya está», no conflicto.
    ctx = _ctx(
        turnos=[
            _turno(tid="t1", fecha="2026-06-02", franja="fr-manana", miembro="u1"),
            _turno(tid="t2", fecha="2026-06-02", franja="fr-manana", miembro="u2"),
        ]
    )
    op = {"tipo": "crear_turno", "fecha": "2026-06-02", "franja": "Mañana", "miembro_id": "u2"}
    info = pi.calcular_conflicto(op, ctx)
    assert info["ya_existe"] is True
    assert info["conflicto"] is False


def test_sin_conflicto_crear_turno_celda_libre():
    ctx = _ctx(turnos=[_turno(tid="t1", fecha="2026-06-02", franja="fr-manana")])
    op = {"tipo": "crear_turno", "fecha": "2026-06-03", "franja": "Tarde", "miembro_id": "u2"}
    info = pi.calcular_conflicto(op, ctx)
    assert info["conflicto"] is False
    assert info["ya_existe"] is False


def test_conflicto_modificar_turno_desaparecido():
    ctx = _ctx(turnos=[])
    op = {"tipo": "modificar_turno", "turno_id": "t-fantasma", "cambios": {"estado": "aprobado"}}
    info = pi.calcular_conflicto(op, ctx)
    assert info["conflicto"] is True
    assert info["actual"] is None


def test_modificar_turno_devuelve_valores_actuales():
    ctx = _ctx(turnos=[_turno(tid="t1", miembro="u1", estado="propuesto")])
    op = {"tipo": "modificar_turno", "turno_id": "t1", "cambios": {"estado": "aprobado"}}
    info = pi.calcular_conflicto(op, ctx)
    assert info["conflicto"] is False
    assert info["actual"]["miembro_id"] == "u1"
    assert info["actual"]["estado"] == "propuesto"


def test_crear_evento_nunca_conflictua():
    info = pi.calcular_conflicto({"tipo": "crear_evento", "fecha": "2026-06-02", "titulo": "X"}, _ctx())
    assert info["conflicto"] is False
    assert info["ya_existe"] is False


def test_ya_existe_crear_evento_mismo_fecha_hora_titulo():
    # Mismo (fecha, hora, título) ya en el calendario -> «ya está», se omitirá al aplicar.
    ctx = _ctx(eventos=[{"fecha": "2026-06-02", "hora": "10:00", "titulo": "España vs Cabo Verde"}])
    op = {"tipo": "crear_evento", "fecha": "2026-06-02", "hora": "10:00", "titulo": "España vs Cabo Verde"}
    info = pi.calcular_conflicto(op, ctx)
    assert info["ya_existe"] is True
    assert info["conflicto"] is False


def test_ya_existe_crear_evento_normaliza_espacios_y_mayusculas():
    # «mismo nombre» tolera diferencias de espaciado/mayúsculas y de espacios en la hora.
    ctx = _ctx(eventos=[{"fecha": "2026-06-02", "hora": "10:00", "titulo": "España vs Cabo Verde"}])
    op = {"tipo": "crear_evento", "fecha": "2026-06-02", "hora": " 10:00 ", "titulo": "  españa   VS Cabo Verde "}
    assert pi.calcular_conflicto(op, ctx)["ya_existe"] is True


def test_ya_existe_crear_evento_ignora_puntuacion_y_acentos():
    # Variaciones MENORES (punto, acentos, guion, mayúsculas) no deben duplicar: es el mismo.
    ctx = _ctx(eventos=[{"fecha": "2026-06-02", "hora": "10:00", "titulo": "España vs. Cabo Verde"}])
    for titulo in ("espana vs cabo verde", "ESPAÑA VS. CABO-VERDE", "  España   vs   Cabo Verde "):
        op = {"tipo": "crear_evento", "fecha": "2026-06-02", "hora": "10:00", "titulo": titulo}
        assert pi.calcular_conflicto(op, ctx)["ya_existe"] is True, titulo


def test_crear_evento_titulo_distinto_no_es_idempotente():
    ctx = _ctx(eventos=[{"fecha": "2026-06-02", "hora": "10:00", "titulo": "España vs Cabo Verde"}])
    op = {"tipo": "crear_evento", "fecha": "2026-06-02", "hora": "10:00", "titulo": "Portugal vs RD Congo"}
    assert pi.calcular_conflicto(op, ctx)["ya_existe"] is False


def test_crear_evento_misma_hora_distinto_dia_no_es_idempotente():
    ctx = _ctx(eventos=[{"fecha": "2026-06-02", "hora": "10:00", "titulo": "España vs Cabo Verde"}])
    op = {"tipo": "crear_evento", "fecha": "2026-06-09", "hora": "10:00", "titulo": "España vs Cabo Verde"}
    assert pi.calcular_conflicto(op, ctx)["ya_existe"] is False


# --------------------------------------------------------------------------- #
# Re-validacion de operaciones ya parseadas (camino /aplicar)                 #
# --------------------------------------------------------------------------- #


def test_validar_operaciones_re_chequea_contra_contexto_vivo():
    ops = [
        {"tipo": "crear_turno", "fecha": "2026-06-02", "franja": "Mañana", "miembro_id": "u1"},
        {"tipo": "crear_turno", "fecha": "2026-06-02", "franja": "Mañana", "miembro_id": "u9"},
    ]
    validas, errores = pi.validar_operaciones(ops, _ctx())
    assert len(validas) == 1
    assert len(errores) == 1
    assert errores[0]["indice"] == 1


def test_sin_tope_de_operaciones_procesa_todas():
    # SIN límite de cantidad: se procesan TODAS las operaciones (un documento puede traer
    # un periodo largo). Aquí 3000 válidas se devuelven enteras, sin recorte.
    ops = [
        {"tipo": "crear_evento", "fecha": "2026-06-20", "titulo": f"E{i}"}
        for i in range(3000)
    ]
    validas, errores = pi.parsear_y_validar(__import__("json").dumps(ops), _ctx())
    assert errores == []
    assert len(validas) == 3000


def test_dedup_operaciones_exactamente_iguales():
    # Dos operaciones IDÉNTICAS (misma fecha+título) se colapsan a una (red de seguridad
    # ante duplicados literales, p.ej. una fila repetida en dos hojas del Excel).
    txt = (
        '[{"tipo": "crear_evento", "fecha": "2026-06-01", "titulo": "Final Liga MX"},'
        ' {"tipo": "crear_evento", "fecha": "2026-06-01", "titulo": "Final Liga MX"}]'
    )
    validas, errores = pi.parsear_y_validar(txt, _ctx())
    assert errores == []
    assert len(validas) == 1


def test_no_dedup_eventos_distintos_misma_fecha():
    # Eventos DISTINTOS en la misma fecha (títulos diferentes) NO se deduplican: el dedup
    # solo quita repetidos LITERALES, no fusiona operaciones distintas.
    txt = (
        '[{"tipo": "crear_evento", "fecha": "2026-06-01", "titulo": "A"},'
        ' {"tipo": "crear_evento", "fecha": "2026-06-01", "titulo": "B"}]'
    )
    validas, errores = pi.parsear_y_validar(txt, _ctx())
    assert errores == []
    assert len(validas) == 2


# --------------------------------------------------------------------------- #
# componer_prompt: plantilla editable (Prompts) + fragmentos calculados     #
# --------------------------------------------------------------------------- #


def test_componer_prompt_inserta_fragmentos_ambos_modos():
    # La plantilla viene de la Prompts (inicial); roster, esquema y la fuente/cola se insertan
    # en sus marcadores, que NO deben quedar crudos. Modo TEXTO: el documento va embebido al final.
    p_txt = pij.componer_prompt(ctx=_ctx(), texto_documento="### HOJA: A\nfila")
    assert "Luis" in p_txt and "Ana" in p_txt          # roster (miembros)
    assert "### HOJA: A" in p_txt                        # documento embebido en la cola
    assert '"operaciones"' in p_txt                      # esquema/contrato JSON
    assert "{{" not in p_txt                              # todos los marcadores sustituidos
    # Encuadre GENÉRICO inyectado por código: anula el corte «si no es una parrilla, vacío» de las
    # plantillas viejas del store (un solo evento — cartelera/nota/frase — también cuenta).
    assert "UN SOLO evento" in p_txt
    assert "NO sea una parrilla de turnos" in p_txt      # recordatorio final tras el documento
    # Modo RUTA: claude lee el fichero; aparece la ruta y NO hay documento embebido.
    p_ruta = pij.componer_prompt(ctx=_ctx(), ruta_doc="/tmp/rota.pdf")
    assert "/tmp/rota.pdf" in p_ruta
    assert "{{" not in p_ruta
    assert "UN SOLO evento" in p_ruta                     # el encuadre va en ambos modos


def test_componer_prompt_ancla_la_fecha_de_hoy_cuando_se_pasa():
    # Con `hoy`, el prompt ancla las fechas relativas/sin año (notas, frases sueltas). Sin `hoy`,
    # no aparece la frase de anclaje (los documentos de parrilla traen fechas explícitas).
    con = pij.componer_prompt(ctx=_ctx(), texto_documento="fila", hoy="2026-06-15")
    assert "2026-06-15" in con and "Hoy es 2026-06-15" in con
    sin = pij.componer_prompt(ctx=_ctx(), texto_documento="fila")
    assert "Hoy es" not in sin


def test_componer_prompt_frase_con_web_pide_identificar_y_datar():
    # FRASE escrita a mano (`permitir_web=True`): el texto es el NOMBRE de un evento sin fecha; el
    # prompt debe pedir BUSCARLO en la web y datarlo, NO tratarlo como una transcripción cerrada.
    p = pij.componer_prompt(
        ctx=_ctx(), texto_documento="la velada del año vi", permitir_web=True
    )
    assert "WebSearch" in p                       # se habilita y se nombra la búsqueda web
    assert "WebFetch" in p                        # un ENLACE se lee con WebFetch (fallback de 403)
    assert "FRASE O ENLACE A IDENTIFICAR" in p    # etiquetado como frase/enlace, no documento
    assert "la velada del año vi" in p            # la frase del usuario queda embebida
    # NO debe arrastrar el corte de transcripción cerrada que impedía buscar.
    assert "NO abras ni leas ningún fichero ni uses herramientas" not in p
    assert "{{" not in p                          # todos los marcadores sustituidos


def test_componer_prompt_sin_web_trata_el_texto_como_transcripcion_cerrada():
    # Sin `permitir_web` (enlace ya extraído / documento transcrito): comportamiento previo intacto
    # — trabaja solo con el texto, sin herramientas; no menciona la búsqueda web.
    p = pij.componer_prompt(ctx=_ctx(), texto_documento="### HOJA: A\nfila")
    assert "WebSearch" not in p
    assert "FRASE O ENLACE A IDENTIFICAR" not in p
    assert "No uses herramientas" in p


def test_endurecer_permitir_web_habilita_busqueda_y_sube_esfuerzo():
    # Camino de FRASE: NO veta WebSearch/WebFetch (hay que identificar el evento online) y sube el
    # esfuerzo a `medium` (ya no es transcripción mecánica). Bash/Write/Edit SIGUEN vetados.
    e = pij._endurecer(lee_fichero=False, permitir_web=True)
    vetadas = e["disallowed_tools"]
    assert "WebSearch" not in vetadas and "WebFetch" not in vetadas
    assert "Bash" in vetadas and "Write" in vetadas
    assert e["esfuerzo"] == "medium"


def test_endurecer_por_defecto_veta_la_web_y_es_mecanico():
    # Documento/enlace: la web sigue vetada y el run es mecánico (`low`), como antes.
    e = pij._endurecer(lee_fichero=False)
    assert "WebSearch" in e["disallowed_tools"] and "WebFetch" in e["disallowed_tools"]
    assert e["esfuerzo"] == "low"


# --------------------------------------------------------------------------- #
# Modo `turnos`: mapeo horario -> franja del equipo                           #
# --------------------------------------------------------------------------- #

# Plantilla de franjas del equipo (las MISMAS de la marca): mañana, tarde y una nocturna, para
# probar que un turno que cruza medianoche cae en la franja correcta.
_PLANTILLA = [
    {"nombre": "Mañana", "inicio": "08:00", "fin": "16:00"},
    {"nombre": "Tarde", "inicio": "16:00", "fin": "22:00"},
    {"nombre": "Noche", "inicio": "22:00", "fin": "02:00"},
]


def test_mapear_franja_inicio_en_manana():
    # LUIS 8AM-4PM -> Mañana (solapa entera con 08:00-16:00).
    assert pi.mapear_franja_por_solape(_PLANTILLA, "08:00", "16:00") == "Mañana"


def test_mapear_franja_por_mayor_solape_no_por_inicio():
    # MARIANA 2PM-10PM empieza en banda de Mañana (14:00<16:00) pero solapa MÁS con Tarde.
    assert pi.mapear_franja_por_solape(_PLANTILLA, "14:00", "22:00") == "Tarde"


def test_mapear_franja_turno_que_cruza_medianoche():
    # TEZCU 4PM-12AM (16:00-00:00) -> Tarde (16:00-22:00 solapa 6h, Noche 22:00-00:00 solapa 2h).
    assert pi.mapear_franja_por_solape(_PLANTILLA, "16:00", "00:00") == "Tarde"
    # ROGER 5PM-1AM (17:00-01:00): Tarde 17:00-22:00=5h, Noche 22:00-01:00=3h -> Tarde.
    assert pi.mapear_franja_por_solape(_PLANTILLA, "17:00", "01:00") == "Tarde"
    # Un turno nocturno puro 22:00-02:00 cae en Noche.
    assert pi.mapear_franja_por_solape(_PLANTILLA, "22:00", "02:00") == "Noche"


def test_mapear_franja_sin_horas_validas_devuelve_none():
    assert pi.mapear_franja_por_solape(_PLANTILLA, "", "") is None
    assert pi.mapear_franja_por_solape(_PLANTILLA, "no-es-hora", "16:00") is None


def test_canonicaliza_turno_con_nombre_de_persona_a_la_franja_real():
    # El bug: claude emitió la COLUMNA (persona) como franja, con el horario de la persona.
    # La canonicalización lo mete en la franja del equipo cuyo horario más solapa.
    ops = [
        {
            "tipo": "crear_turno",
            "fecha": "2026-06-15",
            "franja": "TEZCU",  # nombre de persona/columna, NO una franja
            "franja_inicio": "16:00",
            "franja_fin": "00:00",
            "miembro_id": "u1",
        }
    ]
    out = pi.canonicalizar_franjas_turnos(ops, _PLANTILLA)
    assert out[0]["franja"] == "Tarde"
    # Solo se reescribe el NOMBRE: el horario trabajado se respeta (ya es HH:MM válido; pisarlo
    # con el canónico podría meter un "24:00" que la re-validación del aplicar rechazaría).
    assert out[0]["franja_inicio"] == "16:00"
    assert out[0]["franja_fin"] == "00:00"


def test_canonicaliza_el_horario_manda_sobre_la_etiqueta_del_modelo():
    # MARIANA jueves: COORD MAT 10AM-6PM. El modelo la etiquetó «Tarde» (su franja habitual), pero
    # 10:00-18:00 solapa más con Mañana (6h) que con Tarde (2h): el HORARIO manda -> Mañana.
    ops = [
        {
            "tipo": "crear_turno",
            "fecha": "2026-06-18",
            "franja": "Tarde",  # etiqueta equivocada del modelo
            "franja_inicio": "10:00",
            "franja_fin": "18:00",
            "miembro_id": "u1",
        }
    ]
    out = pi.canonicalizar_franjas_turnos(ops, _PLANTILLA)
    assert out[0]["franja"] == "Mañana"
    # El horario trabajado se respeta tal cual (no se pisa con el canónico de la franja).
    assert out[0]["franja_inicio"] == "10:00"
    assert out[0]["franja_fin"] == "18:00"


def test_canonicaliza_corrige_casing_cuando_no_hay_horario_usable():
    # Sin franja_inicio/fin no hay nada que mapear por solape: cae en la etiqueta del modelo y
    # solo corrige su casing (si ya es una franja real de la plantilla).
    ops = [{"tipo": "crear_turno", "fecha": "2026-06-15", "franja": "tarde", "miembro_id": "u1"}]
    out = pi.canonicalizar_franjas_turnos(ops, _PLANTILLA)
    assert out[0]["franja"] == "Tarde"


def test_canonicaliza_no_toca_eventos_ni_plantilla_vacia():
    ops = [{"tipo": "crear_evento", "fecha": "2026-06-15", "titulo": "Partido"}]
    assert pi.canonicalizar_franjas_turnos(ops, _PLANTILLA) == ops
    turno = [{"tipo": "crear_turno", "fecha": "2026-06-15", "franja": "TEZCU", "miembro_id": "u1"}]
    # Sin plantilla no hay a qué mapear: se deja como vino (no se inventa nada).
    assert pi.canonicalizar_franjas_turnos(turno, []) == turno


# --------------------------------------------------------------------------- #
# Resolucion de miembro por nombre (rescata ids mal transcritos por el modelo) #
# --------------------------------------------------------------------------- #


def test_resuelve_miembro_por_nombre_cuando_el_id_no_existe():
    # El modelo transcribió mal el id opaco, pero leyó bien el nombre «LUIS» -> se resuelve a u1.
    op = {
        "tipo": "crear_turno", "fecha": "2026-06-15", "franja": "Mañana",
        "miembro_id": "id-inventado", "miembro_nombre": "LUIS",
    }
    validas, errores = pi.validar_operaciones([op], _ctx())
    assert errores == []
    assert validas[0]["miembro_id"] == "u1"


def test_resuelve_miembro_cuando_el_id_trae_el_nombre():
    # El modelo puso el NOMBRE en miembro_id (sin miembro_nombre) -> también se resuelve.
    op = {"tipo": "crear_turno", "fecha": "2026-06-15", "franja": "Mañana", "miembro_id": "ana"}
    validas, errores = pi.validar_operaciones([op], _ctx())
    assert errores == []
    assert validas[0]["miembro_id"] == "u2"


def test_no_resuelve_a_quien_no_es_del_roster():
    # Un nombre que no es de nadie: no se inventa -> error de validación (no se cuela un turno).
    op = {
        "tipo": "crear_turno", "fecha": "2026-06-15", "franja": "Mañana",
        "miembro_id": "x", "miembro_nombre": "Pedro",
    }
    validas, errores = pi.validar_operaciones([op], _ctx())
    assert validas == []
    assert "no existe en el equipo" in errores[0]["error"]


# --------------------------------------------------------------------------- #
# Modo `turnos`: prompt                                                       #
# --------------------------------------------------------------------------- #


def test_prompt_modo_turnos_lista_franjas_con_horario_y_solo_turnos():
    p = pij.componer_prompt(
        ctx=_ctx(),
        texto_documento="TEZCU 4PM-12AM | LUIS 8AM-4PM",
        modo="turnos",
        franjas_marca=_PLANTILLA,
    )
    # Emite SOLO turnos (nada de eventos/tareas).
    assert "crear_turno" in p
    assert "crear_evento" not in p
    assert "crear_tarea" not in p
    # Lista las franjas del equipo CON su horario (para que el modelo mapee por solape).
    assert "Mañana" in p and "08:00" in p and "Tarde" in p and "Noche" in p
    # Le explica que las cabeceras son personas/roles, NO franjas (el corazón del arreglo).
    assert "NO es una franja" in p
    # Embebe el roster y el documento.
    assert "Luis" in p
    assert "TEZCU 4PM-12AM" in p


def test_prompt_modo_turnos_sin_franjas_marca_cae_a_nombres_por_defecto():
    # Marca sin plantilla: el prompt sigue funcionando con los nombres por defecto (sin horario).
    p = pij.componer_prompt(
        ctx=_ctx(), texto_documento="LUIS 8AM-4PM", modo="turnos", franjas_marca=None
    )
    assert "crear_turno" in p
    assert "Mañana" in p and "Tarde" in p
