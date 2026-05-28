"""Tests de la lógica de DOMINIO de la rota (F4 · #144): predicados + utilidades.

Módulo PURO (`keni_consola.rota`): no toca SQLite, red ni la app. Aquí se prueban los
PREDICADOS que la API usa para exigir override en la edición manual de turnos —
la misma persona NO cubre dos sábados seguidos salvo override— y las utilidades de
fechas que sirven al horario/parrilla.
"""

from __future__ import annotations

from keni_consola import rota as r

# Un sábado real para los tests de fechas/predicados.
SAB1 = "2026-05-30"


def _lunes(iso: str) -> str:
    return r.lunes_de_semana_iso(iso)


# --------------------------------------------------------------------------- #
# Utilidades de fechas                                                         #
# --------------------------------------------------------------------------- #


def test_es_sabado():
    assert r.es_sabado(SAB1) is True
    assert r.es_sabado("2026-05-29") is False  # viernes
    assert r.es_sabado("no-es-fecha") is False


def test_lunes_de_semana_normaliza():
    # El sábado 2026-05-30 cae en la semana cuyo lunes es 2026-05-25.
    assert _lunes(SAB1) == "2026-05-25"
    # Dar un lunes devuelve el mismo lunes (idempotente).
    assert _lunes("2026-05-25") == "2026-05-25"


def test_rango_semana():
    inicio, fin = r.rango_semana(_lunes(SAB1))
    assert inicio == "2026-05-25"
    assert fin == "2026-05-31"  # domingo


def test_dias_de_semana():
    dias = r.dias_de_semana(_lunes(SAB1))
    assert len(dias) == 7
    assert dias[0] == "2026-05-25"  # lunes
    assert dias[5] == SAB1  # sábado
    assert dias[6] == "2026-05-31"  # domingo


def test_dias_de_semana_invalida_devuelve_vacio():
    assert r.dias_de_semana("no-fecha") == []


# --------------------------------------------------------------------------- #
# Dataclasses (forma del dominio: la API construye estas instancias)            #
# --------------------------------------------------------------------------- #


def test_dataclasses_son_construibles():
    m = r.Miembro(id="u0", nombre="Ana")
    assert m.id == "u0" and m.nombre == "Ana"
    e = r.Evento("e1", "Partido", SAB1, "16:00", "Clip del gol")
    assert e.fecha == SAB1 and e.contenido == "Clip del gol"
    a = r.Ausencia("u0", "2026-05-25", "2026-05-31", "vacaciones")
    assert a.tipo == "vacaciones"


# --------------------------------------------------------------------------- #
# Predicado: rotación de sábados (lo usa la API para exigir override)          #
# --------------------------------------------------------------------------- #


def test_viola_rotacion_sabado():
    assert r.viola_rotacion_sabado("u0", "u0", override=False) is True
    # Con override explícito, NO viola (cobertura estratégica de Elías).
    assert r.viola_rotacion_sabado("u0", "u0", override=True) is False
    # Persona distinta: no viola.
    assert r.viola_rotacion_sabado("u0", "u1", override=False) is False
    # Sin sábado previo: no viola.
    assert r.viola_rotacion_sabado("", "u0", override=False) is False


def test_viola_rotacion_sabado_trabajo():
    previos = {"u0"}
    # u0 trabajó el sábado previo: ponerlo a trabajar de nuevo (matutino) sin override viola.
    assert r.viola_rotacion_sabado_trabajo(previos, "u0", override=False, franja="matutino") is True
    # Con override, no viola.
    assert r.viola_rotacion_sabado_trabajo(previos, "u0", override=True, franja="matutino") is False
    # Si descansa, no trabaja: no viola.
    assert r.viola_rotacion_sabado_trabajo(previos, "u0", override=False, franja="descanso") is False
    # Otra persona: no viola.
    assert r.viola_rotacion_sabado_trabajo(previos, "u1", override=False, franja="matutino") is False


# --------------------------------------------------------------------------- #
# Predicado: ausencias (lo usa la UI/serialización para marcar "Ausente")       #
# --------------------------------------------------------------------------- #


def test_miembro_ausente_predicado():
    aus = [r.Ausencia("u0", "2026-05-25", "2026-05-27", "baja")]
    assert r.miembro_ausente(aus, "u0", "2026-05-26") is True
    assert r.miembro_ausente(aus, "u0", "2026-05-28") is False  # fuera de rango
    assert r.miembro_ausente(aus, "u1", "2026-05-26") is False  # otro miembro
    assert r.miembro_ausente(aus, "u0", "no-fecha") is False  # fecha rota no rompe


def test_miembro_ausente_rango_inclusivo():
    aus = [r.Ausencia("u0", "2026-05-25", "2026-05-27", "vacaciones")]
    # Los extremos del rango sí cuentan (inclusivo).
    assert r.miembro_ausente(aus, "u0", "2026-05-25") is True
    assert r.miembro_ausente(aus, "u0", "2026-05-27") is True


# --------------------------------------------------------------------------- #
# Asignación flexible: mapeo hora -> franja (la API la usa para "asignar de golpe") #
# --------------------------------------------------------------------------- #


def test_mapear_franja_limites():
    # Defaults vigentes (#185): matutino 08:00 inclusive ... 16:00 EXCLUSIVO;
    # vespertino 16:00 inclusive ... 24:00 EXCLUSIVO; descanso lo demas.
    assert r.mapear_franja("08:00") == "matutino"
    assert r.mapear_franja("15:59") == "matutino"
    assert r.mapear_franja("16:00") == "vespertino"
    assert r.mapear_franja("23:59") == "vespertino"
    # Descanso (madrugada antes de matutino).
    assert r.mapear_franja("00:00") == "descanso"
    assert r.mapear_franja("07:59") == "descanso"


def test_mapear_franja_rangos_custom():
    # Cuando el admin cambia las franjas desde /api/rota/config/franjas, el dominio
    # acepta los rangos por kwargs y reclasifica los eventos. Comprobamos los rangos
    # del piloto original (06-14 / 14-22).
    cfg = dict(
        matutino_inicio="06:00",
        matutino_fin="14:00",
        vespertino_inicio="14:00",
        vespertino_fin="22:00",
    )
    assert r.mapear_franja("06:00", **cfg) == "matutino"
    assert r.mapear_franja("13:59", **cfg) == "matutino"
    assert r.mapear_franja("14:00", **cfg) == "vespertino"
    assert r.mapear_franja("21:59", **cfg) == "vespertino"
    assert r.mapear_franja("22:00", **cfg) == "descanso"
    assert r.mapear_franja("05:59", **cfg) == "descanso"


def test_mapear_franja_rango_se_queda_con_el_inicio():
    # El Excel guarda a veces rangos como "16:00–18:00" / "16:00-18:00".
    assert r.mapear_franja("16:00-18:00") == "vespertino"
    assert r.mapear_franja("08:30–10:00") == "matutino"


def test_mapear_franja_vacio_o_malformado_lanza():
    import pytest

    with pytest.raises(ValueError):
        r.mapear_franja("")
    with pytest.raises(ValueError):
        r.mapear_franja("no-hora")
    with pytest.raises(ValueError):
        r.mapear_franja("25:00")  # fuera de rango


# --------------------------------------------------------------------------- #
# Resumen de carga por miembro (panel "Carga del equipo")                       #
# --------------------------------------------------------------------------- #


def test_resumen_carga_basico():
    """Cobertura DERIVADA: para cada evento, los miembros con turno en su franja+fecha lo cubren.

    Con franjas defaults (#185): matutino 08-16, vespertino 16-24.
    """
    equipo = [
        r.Miembro("u_tescu", "Tescu"),
        r.Miembro("u_luis", "Luis"),
        r.Miembro("u_eli", "Elias"),
    ]
    # 6 eventos por la tarde (16:00 → franja vespertino) y 1 por la mañana (10:00 →
    # matutino). Cobertura derivada por (fecha, franja).
    eventos = [
        {"id": "ev1", "fecha": "2026-05-25", "hora": "16:00"},  # lunes vespertino
        {"id": "ev2", "fecha": "2026-05-25", "hora": "18:00"},
        {"id": "ev3", "fecha": "2026-05-27", "hora": "16:00"},
        {"id": "ev4", "fecha": SAB1, "hora": "16:00"},
        {"id": "ev5", "fecha": SAB1, "hora": "18:00"},
        {"id": "ev6", "fecha": SAB1, "hora": "20:00"},
        {"id": "ev_eli_matutino", "fecha": "2026-05-26", "hora": "10:00"},  # martes matutino
    ]
    # Turnos: Tescu vespertino lun-vie + sabado vespertino (cubre todos los vespertinos),
    # 1 descanso. Luis matutino mar (cubre ev_eli), pero Tescu no tiene matutino el martes.
    # Para que ev_eli lo cubra Elias, sembramos turno matutino el martes para Elias.
    turnos = [
        {"miembro_id": "u_tescu", "fecha": "2026-05-25", "franja": "vespertino"},
        {"miembro_id": "u_tescu", "fecha": "2026-05-26", "franja": "vespertino"},
        {"miembro_id": "u_tescu", "fecha": "2026-05-27", "franja": "vespertino"},
        {"miembro_id": "u_tescu", "fecha": "2026-05-28", "franja": "descanso"},
        {"miembro_id": "u_tescu", "fecha": "2026-05-29", "franja": "vespertino"},
        {"miembro_id": "u_tescu", "fecha": SAB1, "franja": "vespertino"},
        {"miembro_id": "u_luis", "fecha": "2026-05-25", "franja": "matutino"},
        {"miembro_id": "u_luis", "fecha": "2026-05-26", "franja": "matutino"},
        {"miembro_id": "u_luis", "fecha": "2026-05-27", "franja": "descanso"},
        {"miembro_id": "u_luis", "fecha": "2026-05-28", "franja": "descanso"},
        {"miembro_id": "u_luis", "fecha": "2026-05-29", "franja": "matutino"},
        # Elias trabaja matutino el martes -> cubre ev_eli_matutino (10:00).
        {"miembro_id": "u_eli", "fecha": "2026-05-26", "franja": "matutino"},
    ]
    carga = r.resumen_carga(equipo, turnos, eventos)
    # Ordenado por eventos desc: Tescu (6) > Luis (1, cubre ev_eli? NO, ese es martes matutino y
    # Luis tambien tiene matutino el martes) -> Luis cubre ev_eli, igual que Elias.
    tescu = next(c for c in carga if c.nombre == "Tescu")
    luis = next(c for c in carga if c.nombre == "Luis")
    eli = next(c for c in carga if c.nombre == "Elias")
    assert tescu.eventos == 6  # los 6 vespertinos
    assert tescu.dias_trabajados == 5
    assert tescu.sabado is True  # trabaja sábado y cubre eventos del sábado
    assert tescu.descansos == 1

    assert luis.dias_trabajados == 3
    assert luis.sabado is False
    assert luis.descansos == 2
    # Tanto Luis como Elias tienen matutino el martes -> ambos cubren ev_eli_matutino.
    assert luis.eventos == 1
    assert eli.eventos == 1
    assert eli.dias_trabajados == 1
    assert eli.sabado is False


def test_resumen_carga_sabado_solo_por_cobertura():
    """Aunque no esté en horario laboral, si su turno cubre un evento en sábado -> sabado=True."""
    equipo = [r.Miembro("u_tescu", "Tescu")]
    eventos = [{"id": "ev1", "fecha": SAB1, "hora": "16:00"}]
    turnos = [{"miembro_id": "u_tescu", "fecha": SAB1, "franja": "vespertino"}]
    carga = r.resumen_carga(equipo, turnos, eventos)
    assert carga[0].sabado is True
    assert carga[0].eventos == 1


def test_cobertura_de_evento_derivada():
    """Para un evento, devuelve los turnos cuyo (fecha, franja) cuadra con su hora."""
    evento = {"id": "ev1", "fecha": "2026-05-30", "hora": "16:00"}
    turnos = [
        {"id": "t1", "miembro_id": "u1", "fecha": "2026-05-30", "franja": "vespertino"},
        {"id": "t2", "miembro_id": "u2", "fecha": "2026-05-30", "franja": "matutino"},
        # mismo dia, distinto miembro, misma franja -> tambien cubre.
        {"id": "t3", "miembro_id": "u3", "fecha": "2026-05-30", "franja": "vespertino"},
        # otra fecha -> no cubre.
        {"id": "t4", "miembro_id": "u4", "fecha": "2026-05-31", "franja": "vespertino"},
    ]
    cob = r.cobertura_de_evento(evento, turnos)
    ids = {t["id"] for t in cob}
    assert ids == {"t1", "t3"}


def test_cobertura_de_evento_hora_invalida_vacia():
    """Si la hora del evento no parsea o cae en descanso, no hay cobertura."""
    evento_sin_hora = {"id": "x", "fecha": "2026-05-30", "hora": ""}
    turnos = [{"miembro_id": "u1", "fecha": "2026-05-30", "franja": "matutino"}]
    assert r.cobertura_de_evento(evento_sin_hora, turnos) == []
    evento_madrugada = {"id": "x", "fecha": "2026-05-30", "hora": "03:00"}
    assert r.cobertura_de_evento(evento_madrugada, turnos) == []
