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
    equipo = [
        r.Miembro("u_tescu", "Tescu"),
        r.Miembro("u_luis", "Luis"),
        r.Miembro("u_eli", "Elias"),
    ]
    # 6 eventos asignados a Tescu (3 caen en sábado), 0 a Luis, 1 a Elías.
    fechas = {
        "ev1": "2026-05-25",  # lunes
        "ev2": "2026-05-25",
        "ev3": "2026-05-27",
        "ev4": SAB1,  # sábado 2026-05-30
        "ev5": SAB1,
        "ev6": SAB1,
        "ev_eli": "2026-05-26",
    }
    turnos_cobertura = [
        *({"evento_id": eid, "miembro_id": "u_tescu"} for eid in ["ev1", "ev2", "ev3", "ev4", "ev5", "ev6"]),
        {"evento_id": "ev_eli", "miembro_id": "u_eli"},
    ]
    # Horario de trabajo: Tescu trabaja 5 días + 1 descanso; Luis 3 días + 2 descansos.
    turnos_trabajo = [
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
    ]
    carga = r.resumen_carga(equipo, turnos_cobertura, turnos_trabajo, fechas)
    # Ordenado por eventos desc.
    assert [c.nombre for c in carga] == ["Tescu", "Elias", "Luis"]
    tescu = carga[0]
    assert tescu.eventos == 6
    assert tescu.dias_trabajados == 5
    assert tescu.sabado is True  # trabaja sábado y cubre eventos del sábado
    assert tescu.descansos == 1

    luis = next(c for c in carga if c.nombre == "Luis")
    assert luis.eventos == 0
    assert luis.dias_trabajados == 3
    assert luis.sabado is False
    assert luis.descansos == 2

    eli = next(c for c in carga if c.nombre == "Elias")
    assert eli.eventos == 1
    assert eli.dias_trabajados == 0  # sin turnos de trabajo
    assert eli.sabado is False  # el evento es martes


def test_resumen_carga_sabado_solo_por_cobertura():
    """Aunque no esté en horario laboral, si cubre un evento en sábado -> sabado=True."""
    equipo = [r.Miembro("u_tescu", "Tescu")]
    fechas = {"ev1": SAB1}
    cobertura = [{"evento_id": "ev1", "miembro_id": "u_tescu"}]
    trabajo: list[dict] = []
    carga = r.resumen_carga(equipo, cobertura, trabajo, fechas)
    assert carga[0].sabado is True
