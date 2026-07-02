"""Tests de la LOGICA PURA de la recurrencia de eventos (`dominio.recurrencia`).

Una serie se define por (fecha_base, dias_semana, repetir_hasta) y se materializa en
fechas concretas. Aqui se prueba la expansion: la base siempre entra, los dias del patron
se anaden hasta el fin (inclusive), el tope acota, y el saneo de los dias del request.

Son funciones puras: no hay Postgres, asi que NO se saltan (corren siempre, tambien en CI).
"""

from __future__ import annotations

from keni_consola.operacion import recurrencia

# 2026-06-15 es LUNES; la semana 15..21 jun = L M X J V S D.


# --------------------------------------------------------------------------- #
# normalizar_dias_semana / CSV                                                #
# --------------------------------------------------------------------------- #


def test_normalizar_ordena_dedup_y_filtra_fuera_de_rango():
    assert recurrencia.normalizar_dias_semana([4, 0, 0, 2]) == [0, 2, 4]
    assert recurrencia.normalizar_dias_semana([7, -1, "3", 3]) == [3]


def test_normalizar_descarta_booleanos_y_no_listas():
    # True/False son `int` en Python: NO deben colarse como días 1/0.
    assert recurrencia.normalizar_dias_semana([True, False, 5]) == [5]
    assert recurrencia.normalizar_dias_semana("0,1,2") == []
    assert recurrencia.normalizar_dias_semana(None) == []


def test_csv_ida_y_vuelta():
    assert recurrencia.dias_semana_a_csv([0, 1, 2, 3, 4]) == "0,1,2,3,4"
    assert recurrencia.csv_a_dias_semana("0,1,2,3,4") == [0, 1, 2, 3, 4]
    assert recurrencia.csv_a_dias_semana("") == []
    assert recurrencia.csv_a_dias_semana("5, 6") == [5, 6]


# --------------------------------------------------------------------------- #
# fechas_recurrencia                                                          #
# --------------------------------------------------------------------------- #


def test_sin_dias_devuelve_solo_la_base():
    assert recurrencia.fechas_recurrencia("2026-06-15", [], "2026-06-30") == ["2026-06-15"]


def test_fecha_base_invalida_devuelve_vacio():
    assert recurrencia.fechas_recurrencia("no-es-fecha", [0], "2026-06-30") == []


def test_laborables_una_semana():
    # Base lunes + L-V hasta el domingo: L M X J V (no S/D).
    out = recurrencia.fechas_recurrencia("2026-06-15", [0, 1, 2, 3, 4], "2026-06-21")
    assert out == ["2026-06-15", "2026-06-16", "2026-06-17", "2026-06-18", "2026-06-19"]


def test_fin_de_semana_incluye_base_aunque_no_sea_del_patron():
    # La base (lunes) SIEMPRE entra aunque el patrón sea S-D; luego añade S y D.
    out = recurrencia.fechas_recurrencia("2026-06-15", [5, 6], "2026-06-21")
    assert out == ["2026-06-15", "2026-06-20", "2026-06-21"]


def test_semanal_mismo_dia_de_la_semana():
    # "Una vez por semana" = el weekday de la base (lunes) cada 7 días.
    out = recurrencia.fechas_recurrencia("2026-06-15", [0], "2026-07-06")
    assert out == ["2026-06-15", "2026-06-22", "2026-06-29", "2026-07-06"]


def test_hasta_es_inclusive():
    out = recurrencia.fechas_recurrencia("2026-06-15", [0], "2026-06-22")
    assert "2026-06-22" in out


def test_hasta_anterior_a_la_base_devuelve_solo_la_base():
    out = recurrencia.fechas_recurrencia("2026-06-15", [0, 1, 2], "2026-06-10")
    assert out == ["2026-06-15"]


def test_tope_acota_un_hasta_lejano():
    # Diario con tope de 3 días: base + 3 días siguientes = 4 fechas.
    out = recurrencia.fechas_recurrencia(
        "2026-06-15", [0, 1, 2, 3, 4, 5, 6], "2099-12-31", tope_dias=3
    )
    assert out == ["2026-06-15", "2026-06-16", "2026-06-17", "2026-06-18"]


def test_salida_ordenada_y_sin_duplicados():
    out = recurrencia.fechas_recurrencia("2026-06-15", [0, 1, 2, 3, 4, 5, 6], "2026-06-21")
    assert out == sorted(out)
    assert len(out) == len(set(out))
    assert len(out) == 7
