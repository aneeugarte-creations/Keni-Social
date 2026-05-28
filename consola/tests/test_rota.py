"""Tests de la lógica de DOMINIO de la rota (F4 · #144): proponedor + reglas.

Módulo PURO (`keni_consola.rota`): no toca SQLite, red ni la app. Aquí se prueba a
fondo el CRITERIO DE ACEPTACIÓN central — la misma persona NO cubre dos sábados
seguidos salvo override — y el reparto/utilidades de fechas.
"""

from __future__ import annotations

from keni_consola import rota as r

# Sábados consecutivos reales: 2026-05-30, 2026-06-06, 2026-06-13, 2026-06-20.
SAB1 = "2026-05-30"
SAB2 = "2026-06-06"
SAB3 = "2026-06-13"


def _equipo(n: int) -> list[r.Miembro]:
    nombres = ["Ana", "Beto", "Caro", "Dani", "Eli"]
    return [r.Miembro(id=f"u{i}", nombre=nombres[i]) for i in range(n)]


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


def test_eventos_de_semana_filtra_y_ordena():
    eventos = [
        r.Evento("e1", "Tarde", SAB1, "18:00", "Clip"),
        r.Evento("e2", "Mañana", SAB1, "09:00", "Resumen"),
        r.Evento("e3", "Otra semana", "2026-06-07", "10:00", "X"),
        r.Evento("e4", "Fecha rota", "no-fecha", "10:00", "X"),
    ]
    dentro = r.eventos_de_semana(eventos, _lunes(SAB1))
    assert [e.id for e in dentro] == ["e2", "e1"]  # ordenado por hora


# --------------------------------------------------------------------------- #
# Proponedor: rotación de sábados (criterio de aceptación)                     #
# --------------------------------------------------------------------------- #


def test_proponer_no_repite_sabado_consecutivo():
    equipo = _equipo(2)
    ev1 = [r.Evento("e1", "Partido", SAB1, "16:00", "Gol")]
    p1 = r.proponer_rota(ev1, equipo, _lunes(SAB1))
    assert p1.sabado_asignado  # alguien quedó en el sábado

    ev2 = [r.Evento("e2", "Partido", SAB2, "16:00", "Gol")]
    p2 = r.proponer_rota(ev2, equipo, _lunes(SAB2), sabado_previo=p1.sabado_asignado)
    assert p2.sabado_asignado != p1.sabado_asignado  # NO repite

    ev3 = [r.Evento("e3", "Partido", SAB3, "16:00", "Gol")]
    p3 = r.proponer_rota(ev3, equipo, _lunes(SAB3), sabado_previo=p2.sabado_asignado)
    assert p3.sabado_asignado != p2.sabado_asignado  # sigue rotando


def test_proponer_rota_es_determinista():
    equipo = _equipo(3)
    ev = [r.Evento("e1", "Partido", SAB1, "16:00", "Gol")]
    a = r.proponer_rota(ev, equipo, _lunes(SAB1))
    b = r.proponer_rota(ev, equipo, _lunes(SAB1))
    assert [(t.evento_id, t.miembro_id) for t in a.turnos] == [
        (t.evento_id, t.miembro_id) for t in b.turnos
    ]


def test_proponer_equipo_de_una_persona_avisa_no_inventa():
    equipo = _equipo(1)
    ev = [r.Evento("e1", "Partido", SAB2, "16:00", "Gol")]
    # El único miembro cubrió el sábado anterior: no se puede rotar.
    p = r.proponer_rota(ev, equipo, _lunes(SAB2), sabado_previo="u0")
    assert p.sabado_asignado == "u0"  # se asigna igual (no hay otro)
    assert p.avisos  # pero AVISA honesto en vez de inventar a alguien


def test_proponer_sin_equipo_no_rompe():
    ev = [r.Evento("e1", "Partido", SAB1, "16:00", "Gol")]
    p = r.proponer_rota(ev, [], _lunes(SAB1))
    assert p.turnos == []
    assert p.avisos  # avisa que no hay equipo


def test_proponer_vincula_evento_y_contenido():
    equipo = _equipo(2)
    ev = [
        r.Evento("e1", "Partido", SAB1, "16:00", "Clip del gol"),
        r.Evento("e2", "Entrevista", "2026-05-26", "10:00", "Frase del DT"),
    ]
    p = r.proponer_rota(ev, equipo, _lunes(SAB1))
    ids = {t.evento_id for t in p.turnos}
    assert ids == {"e1", "e2"}  # cada evento queda vinculado a un turno


def test_proponer_reparte_equilibrado():
    equipo = _equipo(2)
    ev = [
        r.Evento(f"e{i}", "Ev", f"2026-05-{25 + i}", "10:00", "X") for i in range(4)
    ]
    p = r.proponer_rota(ev, equipo, _lunes("2026-05-25"))
    carga: dict[str, int] = {}
    for t in p.turnos:
        carga[t.miembro_id] = carga.get(t.miembro_id, 0) + 1
    # 4 eventos / 2 personas => 2 y 2 (reparto equilibrado).
    assert sorted(carga.values()) == [2, 2]


# --------------------------------------------------------------------------- #
# Predicado de la regla (lo usa la API para exigir override)                   #
# --------------------------------------------------------------------------- #


def test_viola_rotacion_sabado():
    assert r.viola_rotacion_sabado("u0", "u0", override=False) is True
    # Con override explícito, NO viola (cobertura estratégica de Elías).
    assert r.viola_rotacion_sabado("u0", "u0", override=True) is False
    # Persona distinta: no viola.
    assert r.viola_rotacion_sabado("u0", "u1", override=False) is False
    # Sin sábado previo: no viola.
    assert r.viola_rotacion_sabado("", "u0", override=False) is False


# --------------------------------------------------------------------------- #
# Gestión de turnos: horario de TRABAJO (proponer_horario)                      #
# --------------------------------------------------------------------------- #


def _franjas_por_dia(p: r.PropuestaHorario, fecha: str) -> list[str]:
    return [t.franja for t in p.turnos if t.fecha == fecha]


def test_proponer_horario_cubre_manana_y_tarde_cada_dia():
    equipo = _equipo(3)
    p = r.proponer_horario(equipo, _lunes(SAB1))
    for fecha in r.dias_de_semana(_lunes(SAB1)):
        franjas = _franjas_por_dia(p, fecha)
        assert franjas.count("matutino") >= 1
        assert franjas.count("vespertino") >= 1
        # Con 3 personas, cada día queda 1 en descanso.
        assert franjas.count("descanso") >= 1


def test_proponer_horario_excluye_a_quien_esta_ausente():
    equipo = _equipo(3)
    # u0 (Ana) de vacaciones toda la semana del SAB1.
    ausencias = [r.Ausencia("u0", "2026-05-25", "2026-05-31", "vacaciones")]
    p = r.proponer_horario(equipo, _lunes(SAB1), ausencias=ausencias)
    asignados = {t.miembro_id for t in p.turnos}
    assert "u0" not in asignados  # nunca se asigna al ausente


def test_miembro_ausente_predicado():
    aus = [r.Ausencia("u0", "2026-05-25", "2026-05-27", "baja")]
    assert r.miembro_ausente(aus, "u0", "2026-05-26") is True
    assert r.miembro_ausente(aus, "u0", "2026-05-28") is False  # fuera de rango
    assert r.miembro_ausente(aus, "u1", "2026-05-26") is False  # otro miembro
    assert r.miembro_ausente(aus, "u0", "no-fecha") is False  # fecha rota no rompe


def test_proponer_horario_no_repite_sabado_de_trabajo_consecutivo():
    equipo = _equipo(3)
    # Quien trabajó el sábado previo no entra a trabajar este sábado.
    p = r.proponer_horario(equipo, _lunes(SAB1))
    sab1_fecha = SAB1
    trabajan_sab1 = {
        t.miembro_id for t in p.turnos if t.fecha == sab1_fecha and t.franja in ("matutino", "vespertino")
    }
    p2 = r.proponer_horario(equipo, _lunes(SAB2), sabados_previos=trabajan_sab1)
    trabajan_sab2 = {
        t.miembro_id for t in p2.turnos if t.fecha == SAB2 and t.franja in ("matutino", "vespertino")
    }
    assert trabajan_sab1.isdisjoint(trabajan_sab2)  # nadie repite sábado de trabajo


def test_proponer_horario_es_determinista():
    equipo = _equipo(4)
    a = r.proponer_horario(equipo, _lunes(SAB1))
    b = r.proponer_horario(equipo, _lunes(SAB1))
    assert [(t.fecha, t.miembro_id, t.franja) for t in a.turnos] == [
        (t.fecha, t.miembro_id, t.franja) for t in b.turnos
    ]


def test_proponer_horario_equipo_pequeno_avisa():
    equipo = _equipo(1)
    p = r.proponer_horario(equipo, _lunes(SAB1))
    # Con una sola persona no se puede cubrir mañana Y tarde: avisa, no inventa.
    assert p.avisos
    # Aun así propone (la única persona cubre la mañana cada día).
    assert all(t.franja == "matutino" for t in p.turnos)


def test_proponer_horario_sin_equipo_no_rompe():
    p = r.proponer_horario([], _lunes(SAB1))
    assert p.turnos == []
    assert p.avisos


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
