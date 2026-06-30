"""Tests del reloj canonico (`keni_consola.tiempo`): UTC SIN offset, segundos. OFFLINE.

El sistema persiste timestamps como TEXT y los compara LEXICOGRAFICAMENTE en SQL; el
canon (naive-UTC, `timespec="seconds"`) es lo que hace que ese orden sea correcto. Aqui
se fija el contrato del helper para que ningun call-site re-introduzca "+00:00" ni
microsegundos en columnas comparadas.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta, timezone

from keni_consola.tiempo import (
    ahora_iso,
    dia_cdmx,
    fraccion_dia_cdmx,
    hoy_cdmx,
    inicio_dia_cdmx_iso_utc,
    iso_utc,
)

_RE_CANON = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")


def test_ahora_iso_formato_canonico():
    valor = ahora_iso()
    assert _RE_CANON.match(valor), valor  # sin offset, sin microsegundos
    # Es UTC real: a segundos de `datetime.now(UTC)`.
    delta = abs(datetime.fromisoformat(valor) - datetime.now(UTC).replace(tzinfo=None))
    assert delta < timedelta(seconds=5)


def test_iso_utc_naive_se_asume_utc():
    dt = datetime(2026, 6, 9, 12, 30, 45, 123456)  # naive con microsegundos
    assert iso_utc(dt) == "2026-06-09T12:30:45"  # truncado a segundos, sin tocar la hora


def test_iso_utc_aware_se_convierte_a_utc_y_pierde_offset():
    # 12:00 en UTC-6 (CDMX sin DST) == 18:00 UTC.
    dt = datetime(2026, 6, 9, 12, 0, 0, tzinfo=timezone(timedelta(hours=-6)))
    assert iso_utc(dt) == "2026-06-09T18:00:00"


def test_iso_utc_aware_utc_es_identidad_sin_offset():
    dt = datetime(2026, 6, 9, 12, 0, 7, tzinfo=UTC)
    assert iso_utc(dt) == "2026-06-09T12:00:07"


def test_inicio_dia_cdmx_floor_a_medianoche_mx_en_utc():
    # 12:00 UTC del 11-jun == 06:00 en CDMX (UTC-6): la medianoche MX de ESE día es las
    # 00:00 MX == 06:00 UTC del mismo 11-jun.
    momento = datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC)
    assert inicio_dia_cdmx_iso_utc(momento) == "2026-06-11T06:00:00"


def test_inicio_dia_cdmx_madrugada_utc_sigue_siendo_el_dia_mx_anterior():
    # 03:00 UTC del 11-jun == 21:00 MX del 10-jun: aún es el día 10 en México, así que el
    # corte es la medianoche MX del 10 == 06:00 UTC del 10. (Esto es lo que hace que la
    # parrilla NO resetee a 0 a las 18:00 hora MX como haría un corte en UTC.)
    momento = datetime(2026, 6, 11, 3, 0, 0, tzinfo=UTC)
    assert inicio_dia_cdmx_iso_utc(momento) == "2026-06-10T06:00:00"


def test_inicio_dia_cdmx_naive_se_asume_utc():
    # Naive == UTC (convención del módulo): 12:00 naive == 12:00 UTC == 06:00 MX.
    assert inicio_dia_cdmx_iso_utc(datetime(2026, 6, 11, 12, 0, 0)) == "2026-06-11T06:00:00"


def test_inicio_dia_cdmx_canonico_y_no_futuro():
    valor = inicio_dia_cdmx_iso_utc()
    assert _RE_CANON.match(valor), valor  # sin offset, sin microsegundos
    # El inicio del día MX nunca está en el futuro respecto a ahora.
    assert datetime.fromisoformat(valor) <= datetime.now(UTC).replace(tzinfo=None)


def test_dia_cdmx_madrugada_utc_es_el_dia_mx_anterior():
    # 02:00 UTC del 30-jun == 20:00 MX del 29-jun: el bucket-día del gasto es el 29 (MX), no el
    # 30 (UTC). Este es el caso que vaciaba el consumo del día a las 18:00 hora MX.
    momento = datetime(2026, 6, 30, 2, 0, 0, tzinfo=UTC)
    assert dia_cdmx(momento) == "2026-06-29"
    assert hoy_cdmx(momento).isoformat() == "2026-06-29"


def test_dia_cdmx_mediodia_utc_es_el_mismo_dia():
    # 12:00 UTC == 06:00 MX: mismo día calendario.
    momento = datetime(2026, 6, 29, 12, 0, 0, tzinfo=UTC)
    assert dia_cdmx(momento) == "2026-06-29"


def test_dia_cdmx_naive_se_asume_utc():
    assert dia_cdmx(datetime(2026, 6, 30, 2, 0, 0)) == "2026-06-29"


def test_fraccion_dia_cdmx_es_de_la_jornada_mx():
    # Mediodía UTC = 06:00 MX -> 0.25; medianoche UTC = 18:00 MX -> 0.75.
    assert fraccion_dia_cdmx(datetime(2026, 6, 21, 12, 0, 0, tzinfo=UTC)) == 0.25
    assert fraccion_dia_cdmx(datetime(2026, 6, 21, 0, 0, 0, tzinfo=UTC)) == 0.75


def test_orden_lexicografico_consistente():
    """El motivo del canon: valores generados ordenan igual como texto que como instantes."""
    a = iso_utc(datetime(2026, 6, 9, 9, 59, 59, tzinfo=UTC))
    b = iso_utc(datetime(2026, 6, 9, 10, 0, 0))
    c = ahora_iso()
    assert a < b  # mezcla aware/naive ya canonizada ordena bien
    assert b < c or c >= b  # c es "ahora" (>= ambos si el reloj va despues de 2026-06-09)
