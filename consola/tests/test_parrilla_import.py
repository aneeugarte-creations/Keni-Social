"""Tests del dominio PURO de la importacion de parrilla (sin tocar DB ni red).

Cubre: extraccion del bloque JSON de la salida de claude (fences, dict envoltorio, prefijos),
validacion estricta contra el contexto RANGO (fechas dentro de la ventana temporal, franja por
NOMBRE de slot, miembro/turno que existen, enums), deteccion de conflictos (celda ocupada por
slot / turno desaparecido) y la re-validacion de operaciones ya parseadas. Todo
`dominio.parrilla_import`, ni una sola conexion a Postgres.
"""

from __future__ import annotations

from keni_consola.dominio import parrilla_import as pi


# Mapa id->nombre de las franjas existentes (de cualquier semana del rango).
_FRANJAS_NOMBRE = {"fr-manana": "Mañana", "fr-tarde": "Tarde"}


# Ventana FIJA (no atada a "hoy") para que los tests sean deterministas en CI.
_VENTANA = ("2026-01-01", "2027-12-31")


def _ctx(*, turnos=None) -> pi.Contexto:
    return pi.Contexto(
        miembros={"u1": "Luis", "u2": "Ana"},
        nombres_franja={"Mañana", "Tarde"},
        turnos=turnos or [],
        franjas_nombre=_FRANJAS_NOMBRE,
        ventana=_VENTANA,
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
    # El modelo RANGO ya no exige una sola semana: una fecha en otra semana del año es válida.
    txt = '[{"tipo": "crear_evento", "fecha": "2026-06-20", "titulo": "X"}]'
    validas, errores = pi.parsear_y_validar(txt, _ctx())
    assert errores == []
    assert len(validas) == 1


def test_crear_evento_fecha_fuera_de_ventana_es_error():
    # Una fecha absurda (lejísimos) cae fuera de la ventana temporal y se rechaza.
    txt = '[{"tipo": "crear_evento", "fecha": "2099-01-01", "titulo": "X"}]'
    validas, errores = pi.parsear_y_validar(txt, _ctx())
    assert validas == []
    assert len(errores) == 1
    assert "fuera del rango" in errores[0]["error"]


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


def test_crear_turno_franja_inexistente_es_error():
    txt = (
        '[{"tipo": "crear_turno", "fecha": "2026-06-02", "franja": "Madrugada", '
        '"miembro_id": "u1"}]'
    )
    validas, errores = pi.parsear_y_validar(txt, _ctx())
    assert validas == []
    assert "no es un slot válido" in errores[0]["error"]


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


def test_conflicto_crear_turno_celda_ocupada():
    # La celda se identifica por (fecha, NOMBRE de franja): el turno existente usa franja_id
    # "fr-manana" que resuelve a "Mañana"; la op nueva referencia el slot por nombre.
    ctx = _ctx(turnos=[_turno(tid="t1", fecha="2026-06-02", franja="fr-manana", miembro="u1")])
    op = {"tipo": "crear_turno", "fecha": "2026-06-02", "franja": "Mañana", "miembro_id": "u2"}
    info = pi.calcular_conflicto(op, ctx)
    assert info["conflicto"] is True
    assert info["ocupada_por"] == "u1"


def test_sin_conflicto_crear_turno_celda_libre():
    ctx = _ctx(turnos=[_turno(tid="t1", fecha="2026-06-02", franja="fr-manana")])
    op = {"tipo": "crear_turno", "fecha": "2026-06-03", "franja": "Tarde", "miembro_id": "u2"}
    info = pi.calcular_conflicto(op, ctx)
    assert info["conflicto"] is False


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


# --------------------------------------------------------------------------- #
# Re-validacion de operaciones ya parseadas (camino /aplicar)                 #
# --------------------------------------------------------------------------- #


def test_validar_operaciones_re_chequea_contra_contexto_vivo():
    ops = [
        {"tipo": "crear_turno", "fecha": "2026-06-02", "franja": "Mañana", "miembro_id": "u1"},
        # Esta era valida cuando se generó pero el miembro ya no está en el roster vivo.
        {"tipo": "crear_turno", "fecha": "2026-06-02", "franja": "Mañana", "miembro_id": "u9"},
    ]
    validas, errores = pi.validar_operaciones(ops, _ctx())
    assert len(validas) == 1
    assert len(errores) == 1
    assert errores[0]["indice"] == 1


def test_tope_de_operaciones_recorta():
    ops = [{"tipo": "crear_evento"} for _ in range(pi.MAX_OPERACIONES + 50)]
    # Todas inválidas (sin fecha/titulo) pero el punto es que no procesa más de MAX.
    validas, errores = pi.parsear_y_validar(__import__("json").dumps(ops), _ctx())
    assert len(validas) + len(errores) <= pi.MAX_OPERACIONES
