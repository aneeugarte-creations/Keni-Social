"""Tests de la lógica de DOMINIO de la rota: predicados + utilidades.

Módulo PURO (`keni_consola.rota`): no toca SQLite, red ni la app. Aquí se prueban los
PREDICADOS que la API usa para exigir override en la edición manual de turnos —
la misma persona NO cubre dos sábados seguidos salvo override— las utilidades de
fechas que sirven al horario/parrilla, y el modelo "franjas por semana" (`#XYZ Mundial`)
con solapes, cruce de medianoche y descanso explícito.
"""

from __future__ import annotations

from datetime import date

import pytest

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


def test_pares_semanas_copia_mes_jun_desde_may_2026():
    # Junio 2026 empieza en lunes (semanas 01,08,15,22,29) y se siembra desde mayo, alineado por
    # dia de semana (offset 35d = 5 semanas): las 5 semanas que solapan mayo mapean a las 5 de junio.
    pares = r.pares_semanas_copia_mes("2026-06")
    assert pares == [
        ("2026-04-27", "2026-06-01"),
        ("2026-05-04", "2026-06-08"),
        ("2026-05-11", "2026-06-15"),
        ("2026-05-18", "2026-06-22"),
        ("2026-05-25", "2026-06-29"),
    ]
    # Todos los `a_lunes` son lunes y caen en la rejilla del destino; el offset preserva el dia.
    for de_lunes, a_lunes in pares:
        assert r.lunes_de_semana_iso(de_lunes) == de_lunes
        assert (date.fromisoformat(a_lunes) - date.fromisoformat(de_lunes)).days % 7 == 0


def test_pares_semanas_copia_mes_omite_semanas_sin_equivalente():
    # El origen puede tener mas semanas-solapantes que el destino; las que caen fuera se omiten,
    # y las semanas del destino sin origen no aparecen como `a_lunes`. Cada par es lunes->lunes y
    # el destino siempre solapa el mes pedido.
    inicio, _fin = r.rango_semana(r.lunes_de_semana_iso("2026-03-01"))
    pares = r.pares_semanas_copia_mes("2026-03")
    assert pares  # no vacio
    primer_lunes_mar = r.lunes_de_semana_iso("2026-03-01")
    ultimo_lunes_mar = r.lunes_de_semana_iso("2026-03-31")
    for _de, a_lunes in pares:
        assert primer_lunes_mar <= a_lunes <= ultimo_lunes_mar
    assert inicio == primer_lunes_mar


def test_pares_semanas_copia_mes_entrada_invalida_vacio():
    assert r.pares_semanas_copia_mes("no-mes") == []
    assert r.pares_semanas_copia_mes("2026-13") == []
    assert r.pares_semanas_copia_mes("2026-06-01") == []


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
# `mapear_franja` LEGACY (solo retrocompat de la migracion + tests)            #
# --------------------------------------------------------------------------- #


def test_mapear_franja_limites_legacy():
    """Helper para tests retrocompat: mapea tiempo a franja."""
    assert r.mapear_franja("08:00") == "matutino"
    assert r.mapear_franja("15:59") == "matutino"
    assert r.mapear_franja("16:00") == "vespertino"
    assert r.mapear_franja("23:59") == "vespertino"
    assert r.mapear_franja("00:00") == "descanso"
    assert r.mapear_franja("07:59") == "descanso"


def test_mapear_franja_vacio_o_malformado_lanza():
    with pytest.raises(ValueError):
        r.mapear_franja("")
    with pytest.raises(ValueError):
        r.mapear_franja("no-hora")
    with pytest.raises(ValueError):
        r.mapear_franja("25:00")  # fuera de rango


# --------------------------------------------------------------------------- #
# Modelo NUEVO: `franjas_activas_en` (cobertura de N franjas/semana con solape) #
# --------------------------------------------------------------------------- #
#
# Caso real Mundial mié 10 jun: 3 franjas en la misma semana, con solape:
#   - 09:00-17:00 (Mañana ampliada)
#   - 13:00-21:00 (Pivote, solapa con las otras dos)
#   - 17:00-01:00 (Cobertura nocturna, cruza medianoche)
# La cobertura de un evento es la UNION de las franjas activas a su hora.

LUNES_MUNDIAL = "2026-06-08"


def _f(
    id_: str,
    nombre: str,
    inicio: str,
    fin: str,
    *,
    orden: int = 0,
    es_descanso: bool = False,
) -> dict:
    return {
        "id": id_,
        "lunes": LUNES_MUNDIAL,
        "nombre": nombre,
        "inicio": inicio,
        "fin": fin,
        "orden": orden,
        "es_descanso": es_descanso,
    }


def test_franjas_activas_una_franja():
    franjas = [_f("a", "Mañana", "08:00", "16:00", orden=0)]
    assert [f["id"] for f in r.franjas_activas_en("10:00", franjas)] == ["a"]
    # En el limite inferior (inclusivo).
    assert [f["id"] for f in r.franjas_activas_en("08:00", franjas)] == ["a"]
    # En el limite superior (exclusivo).
    assert r.franjas_activas_en("16:00", franjas) == []


def test_franjas_activas_dos_solapadas():
    franjas = [
        _f("a", "Mañana", "08:00", "16:00", orden=0),
        _f("b", "Tarde", "13:00", "21:00", orden=1),
    ]
    # A las 14:00 estan activas las dos.
    activas = r.franjas_activas_en("14:00", franjas)
    assert [f["id"] for f in activas] == ["a", "b"]
    # A las 08:30 solo la primera.
    assert [f["id"] for f in r.franjas_activas_en("08:30", franjas)] == ["a"]
    # A las 18:00 solo la segunda.
    assert [f["id"] for f in r.franjas_activas_en("18:00", franjas)] == ["b"]


def test_franjas_activas_tres_solapadas_caso_mundial():
    """Mundial mié 10 jun: 3 franjas; a las 14:00, 2 activas (09-17 y 13-21)."""
    franjas = [
        _f("m", "Mañana", "09:00", "17:00", orden=0),
        _f("t", "Tarde", "13:00", "21:00", orden=1),
        _f("n", "Noche", "17:00", "01:00", orden=2),  # cruza medianoche
    ]
    # A las 14:00, dos activas: Mañana y Tarde (Noche aun no empieza).
    activas_14 = r.franjas_activas_en("14:00", franjas)
    assert [f["id"] for f in activas_14] == ["m", "t"]
    # A las 18:00, dos activas: Tarde y Noche (Mañana ya terminó).
    activas_18 = r.franjas_activas_en("18:00", franjas)
    assert [f["id"] for f in activas_18] == ["t", "n"]
    # A las 22:00, solo Noche.
    assert [f["id"] for f in r.franjas_activas_en("22:00", franjas)] == ["n"]


def test_franjas_activas_cruzan_medianoche():
    franjas = [_f("n", "Noche", "17:00", "01:00", orden=2)]
    # Antes de medianoche.
    assert [f["id"] for f in r.franjas_activas_en("18:00", franjas)] == ["n"]
    assert [f["id"] for f in r.franjas_activas_en("23:59", franjas)] == ["n"]
    # Despues de medianoche, antes del fin.
    assert [f["id"] for f in r.franjas_activas_en("00:30", franjas)] == ["n"]
    # En el limite (exclusivo).
    assert r.franjas_activas_en("01:00", franjas) == []
    # Mucho mas tarde: fuera.
    assert r.franjas_activas_en("02:00", franjas) == []
    # Antes del inicio: fuera.
    assert r.franjas_activas_en("16:30", franjas) == []


def test_franjas_descanso_se_excluye():
    """Una franja `es_descanso=true` nunca esta activa en `franjas_activas_en`. Un turno en
    esa franja NO cubre eventos (descanso explicito)."""
    franjas = [
        _f("a", "Mañana", "08:00", "16:00", orden=0),
        _f("d", "Descanso", "00:00", "00:00", orden=999, es_descanso=True),
    ]
    activas = r.franjas_activas_en("10:00", franjas)
    assert [f["id"] for f in activas] == ["a"]
    # A cualquier hora la descanso queda fuera: incluso si los rangos del descanso fueran
    # 24h, `es_descanso=true` lo excluye igualmente.
    franjas_d = [_f("d", "Descanso", "00:00", "00:00", orden=999, es_descanso=True)]
    assert r.franjas_activas_en("10:00", franjas_d) == []


def test_franjas_activas_hora_invalida_devuelve_vacio():
    franjas = [_f("a", "Mañana", "08:00", "16:00", orden=0)]
    assert r.franjas_activas_en("", franjas) == []
    assert r.franjas_activas_en("no-hora", franjas) == []


# --------------------------------------------------------------------------- #
# Cobertura derivada del evento usando franjas por semana (UNION)              #
# --------------------------------------------------------------------------- #


def test_cobertura_de_evento_basica():
    """Un evento a las 14:00 con 3 personas en 3 franjas solapadas (Mañana 09-17, Tarde
    13-21, Noche 17-01): a esa hora hay 2 franjas activas; la UNION de turnos en esas
    franjas son los cubridores."""
    franjas = [
        _f("m", "Mañana", "09:00", "17:00", orden=0),
        _f("t", "Tarde", "13:00", "21:00", orden=1),
        _f("n", "Noche", "17:00", "01:00", orden=2),
    ]
    evento = {"id": "ev", "fecha": "2026-06-10", "hora": "14:00"}
    turnos = [
        {"id": "T1", "fecha": "2026-06-10", "franja_id": "m", "miembro_id": "u_a"},
        {"id": "T2", "fecha": "2026-06-10", "franja_id": "t", "miembro_id": "u_b"},
        {"id": "T3", "fecha": "2026-06-10", "franja_id": "n", "miembro_id": "u_c"},
    ]
    cob = r.cobertura_de_evento(evento, turnos, franjas)
    ids = {t["id"] for t in cob}
    # u_a (m) y u_b (t): los que tienen turno en una franja activa a las 14:00.
    assert ids == {"T1", "T2"}


def test_cobertura_de_evento_descanso_no_cubre():
    """Una persona X con turno en la franja Descanso NO cubre eventos de ese dia."""
    franjas = [
        _f("m", "Mañana", "08:00", "16:00", orden=0),
        _f("d", "Descanso", "00:00", "00:00", orden=999, es_descanso=True),
    ]
    evento = {"id": "ev", "fecha": "2026-06-10", "hora": "10:00"}
    turnos = [
        {"id": "T_X_descanso", "fecha": "2026-06-10", "franja_id": "d", "miembro_id": "u_x"},
        {"id": "T_Y_mañana", "fecha": "2026-06-10", "franja_id": "m", "miembro_id": "u_y"},
    ]
    cob = r.cobertura_de_evento(evento, turnos, franjas)
    ids = {t["id"] for t in cob}
    # Solo u_y (Mañana). u_x descansa: no aparece.
    assert ids == {"T_Y_mañana"}


def test_cobertura_de_evento_hora_invalida_o_madrugada():
    """Sin hora o hora fuera de toda franja -> sin cobertura."""
    franjas = [_f("m", "Mañana", "08:00", "16:00", orden=0)]
    turnos = [{"id": "T1", "fecha": "2026-06-10", "franja_id": "m", "miembro_id": "u_a"}]
    assert r.cobertura_de_evento({"fecha": "2026-06-10", "hora": ""}, turnos, franjas) == []
    assert r.cobertura_de_evento({"fecha": "2026-06-10", "hora": "03:00"}, turnos, franjas) == []


def test_cobertura_de_evento_sin_franjas_no_cubre():
    """Sin franjas vivas, no hay cobertura honesta (no asumimos franjas implicitas)."""
    evento = {"id": "ev", "fecha": "2026-06-10", "hora": "14:00"}
    turnos = [{"id": "T1", "fecha": "2026-06-10", "franja_id": "x", "miembro_id": "u_a"}]
    assert r.cobertura_de_evento(evento, turnos, []) == []
    assert r.cobertura_de_evento(evento, turnos, None) == []


# --------------------------------------------------------------------------- #
# Resumen de carga (panel "Carga del equipo")                                   #
# --------------------------------------------------------------------------- #


def test_resumen_carga_basico_con_franjas_por_semana():
    """Cobertura DERIVADA usando franjas vivas de la semana. `dias_trabajados` cuenta dias
    con turno (cualquier franja); `descansos` = dias del rango sin turno (descanso
    implicito por ausencia de turno; la franja "Descanso" tambien cuenta como turno y
    NO suma a `descansos`)."""
    lunes = "2026-05-25"
    franjas = [
        {
            "id": "m",
            "lunes": lunes,
            "nombre": "Mañana",
            "inicio": "08:00",
            "fin": "16:00",
            "orden": 0,
            "es_descanso": False,
        },
        {
            "id": "v",
            "lunes": lunes,
            "nombre": "Tarde",
            "inicio": "16:00",
            "fin": "24:00",
            "orden": 1,
            "es_descanso": False,
        },
    ]
    equipo = [
        r.Miembro("u_tescu", "Tescu"),
        r.Miembro("u_luis", "Luis"),
    ]
    eventos = [
        {"id": "ev1", "fecha": lunes, "hora": "16:00"},  # vespertino
        {"id": "ev2", "fecha": SAB1, "hora": "16:00"},
    ]
    turnos = [
        {"miembro_id": "u_tescu", "fecha": lunes, "franja_id": "v"},
        {"miembro_id": "u_tescu", "fecha": SAB1, "franja_id": "v"},
        {"miembro_id": "u_luis", "fecha": lunes, "franja_id": "m"},
    ]
    carga = r.resumen_carga(equipo, turnos, eventos, franjas, lunes_iso=lunes)
    tescu = next(c for c in carga if c.nombre == "Tescu")
    luis = next(c for c in carga if c.nombre == "Luis")
    assert tescu.eventos == 2  # cubre ev1 y ev2
    assert tescu.dias_trabajados == 2
    assert tescu.sabado is True
    assert tescu.descansos == 5  # 7 - 2
    assert luis.eventos == 0  # matutino, ev1 es a las 16 = vespertino
    assert luis.dias_trabajados == 1
    assert luis.descansos == 6
