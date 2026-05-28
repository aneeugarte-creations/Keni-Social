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
