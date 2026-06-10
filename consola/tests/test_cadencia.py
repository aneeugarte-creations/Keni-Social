"""Tests del dominio PURO de cadencia (margen entre posts). OFFLINE, sin BD ni reloj real."""

from __future__ import annotations

from datetime import datetime

from keni_consola.dominio import cadencia as c


def _cad(**extra):
    base = {
        "marca": "",
        "red": "",
        "margen_min": 60,
        "hora_inicio": "08:00",
        "hora_fin": "22:00",
        "dias": [0, 1, 2, 3, 4, 5, 6],
        "activo": True,
    }
    base.update(extra)
    return base


# --- validación ---------------------------------------------------------------


def test_cadencia_valida():
    assert c.cadencia_valida(_cad())
    assert not c.cadencia_valida(_cad(margen_min=0))
    # fin<inicio = ventana NOCTURNA (cruza la medianoche): VÁLIDA (operación CDMX sobre UTC).
    assert c.cadencia_valida(_cad(hora_inicio="22:00", hora_fin="08:00"))
    assert not c.cadencia_valida(_cad(hora_inicio="08:00", hora_fin="08:00"))  # fin==inicio
    assert not c.cadencia_valida(_cad(dias=[]))
    assert not c.cadencia_valida(_cad(hora_inicio="24:00"))  # hora inválida


# --- próximo hueco ------------------------------------------------------------


def test_primer_hueco_es_el_inicio_de_ventana():
    # Martes 09 jun 2026 a las 06:00; ventana 08:00-22:00, margen 60.
    ahora = datetime(2026, 6, 9, 6, 0)
    assert c.proximo_hueco_cadencia(_cad(margen_min=60), ahora, set()) == "2026-06-09T08:00"


def test_apila_por_margen_evitando_ocupados():
    ahora = datetime(2026, 6, 9, 6, 0)
    ocupados = {"2026-06-09T08:00", "2026-06-09T09:00"}
    # Margen 60 → el siguiente libre es 10:00.
    assert c.proximo_hueco_cadencia(_cad(margen_min=60), ahora, ocupados) == "2026-06-09T10:00"


def test_rueda_al_dia_siguiente_cuando_se_llena():
    ahora = datetime(2026, 6, 9, 6, 0)
    # Ventana 08:00-10:00, margen 60 → huecos 08,09,10 ese día. Si están ocupados, rueda a mañana.
    cad = _cad(margen_min=60, hora_inicio="08:00", hora_fin="10:00")
    ocupados = {"2026-06-09T08:00", "2026-06-09T09:00", "2026-06-09T10:00"}
    assert c.proximo_hueco_cadencia(cad, ahora, ocupados) == "2026-06-10T08:00"


def test_respeta_dias_activos():
    # Martes 06:00, pero la cadencia solo aplica miércoles(2) y viernes(4).
    ahora = datetime(2026, 6, 9, 6, 0)  # martes
    cad = _cad(dias=[2, 4])
    assert c.proximo_hueco_cadencia(cad, ahora, set()) == "2026-06-10T08:00"  # miércoles 10


def test_solo_futuro():
    # 13:30 del martes: los huecos 08..13 ya pasaron; el primero futuro es 14:00 (margen 60).
    ahora = datetime(2026, 6, 9, 13, 30)
    assert c.proximo_hueco_cadencia(_cad(margen_min=60), ahora, set()) == "2026-06-09T14:00"


def test_invalida_devuelve_none():
    ahora = datetime(2026, 6, 9, 6, 0)
    assert c.proximo_hueco_cadencia(_cad(margen_min=0), ahora, set()) is None


# --- ventana nocturna (cruza la medianoche) -----------------------------------


def test_nocturna_hueco_tras_medianoche_pertenece_a_la_ventana_de_ayer():
    # Ventana 16:00-05:00 (nocturna), margen 120. A las 02:30 del miércoles los huecos
    # 16..02 de la ventana del MARTES ya pasaron; el siguiente de esa misma ventana es
    # el de las 04:00 (madrugada del miércoles).
    cad = _cad(margen_min=120, hora_inicio="16:00", hora_fin="05:00")
    ahora = datetime(2026, 6, 10, 2, 30)  # miércoles de madrugada
    assert c.proximo_hueco_cadencia(cad, ahora, set()) == "2026-06-10T04:00"


def test_nocturna_rueda_a_la_ventana_de_hoy_al_agotarse_la_de_ayer():
    # Tras el último hueco de la ventana de ayer (05:00), el siguiente es el arranque
    # de la ventana de HOY (16:00).
    cad = _cad(margen_min=120, hora_inicio="16:00", hora_fin="05:00")
    ahora = datetime(2026, 6, 10, 5, 30)
    assert c.proximo_hueco_cadencia(cad, ahora, set()) == "2026-06-10T16:00"


def test_nocturna_dia_activo_es_el_del_arranque_de_la_ventana():
    # Cadencia solo del martes (1): sus huecos de madrugada del miércoles SÍ existen
    # (pertenecen a la ventana del martes); la ventana del miércoles no.
    cad = _cad(margen_min=120, hora_inicio="16:00", hora_fin="05:00", dias=[1])
    ahora = datetime(2026, 6, 10, 2, 30)  # miércoles de madrugada
    assert c.proximo_hueco_cadencia(cad, ahora, set()) == "2026-06-10T04:00"
    # Pasada la cola de la ventana del martes, el siguiente arranque es el MARTES próximo.
    despues = datetime(2026, 6, 10, 5, 30)
    assert c.proximo_hueco_cadencia(cad, despues, set()) == "2026-06-16T16:00"


# --- aplicabilidad por especificidad -----------------------------------------


def test_cadencia_aplicable_prioriza_especifica():
    cads = [
        _cad(marca="", red=""),  # general
        _cad(marca="unotv", red=""),  # marca
        _cad(marca="unotv", red="instagram"),  # específica
    ]
    elegida = c.cadencia_aplicable(cads, "unotv", "instagram")
    assert elegida["marca"] == "unotv" and elegida["red"] == "instagram"


def test_cadencia_aplicable_cae_a_general_y_respeta_activo():
    cads = [_cad(marca="", red="", activo=False)]
    assert c.cadencia_aplicable(cads, "unotv", "x") is None  # la única aplicable está inactiva
    cads2 = [_cad(marca="", red="")]
    assert c.cadencia_aplicable(cads2, "unotv", "x") is not None
