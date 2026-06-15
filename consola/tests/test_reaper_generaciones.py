"""Tests del reaper de generaciones atascada (`generaciones.reclamar_atascadas`).

Las generaciones viven en ficheros YAML (no Postgres), así que estos tests usan `tmp_path`
vía `KENI_CONSOLA_GENERACIONES` y NO necesitan base de datos. La hora se inyecta para no
depender del reloj.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from keni_consola import generaciones


@pytest.fixture
def almacen(tmp_path, monkeypatch):
    """Aísla el almacén de generaciones en `tmp_path`."""
    monkeypatch.setenv("KENI_CONSOLA_GENERACIONES", str(tmp_path / "generaciones"))
    return tmp_path


def _crear(estado: str, fecha_inicio: str) -> dict:
    """Crea una generación con estado/fecha controlados (salta los defaults de `crear`)."""
    return generaciones.crear(
        {"tipo": "copy", "marca": "", "etiqueta": "x", "estado": estado, "fecha_inicio": fecha_inicio}
    )


AHORA = datetime(2026, 6, 1, 12, 0, 0)


def _hace(horas: float) -> str:
    return (AHORA - timedelta(hours=horas)).isoformat(timespec="seconds")


def test_cierra_la_ejecutando_vieja(almacen):
    g = _crear(generaciones.ESTADO_EJECUTANDO, _hace(3))  # 3 h colgada
    n = generaciones.reclamar_atascadas(3600, ahora=AHORA)  # TTL 1 h
    assert n == 1
    cerrada = generaciones.obtener(g["id"])
    assert cerrada["estado"] == generaciones.ESTADO_ERROR
    assert cerrada["motivo"] == generaciones.MOTIVO_INTERRUMPIDO
    assert cerrada["fecha_fin"]


def test_respeta_la_ejecutando_reciente(almacen):
    """Una `ejecutando` dentro del TTL podría seguir viva: NO se toca."""
    g = _crear(generaciones.ESTADO_EJECUTANDO, _hace(0.1))  # 6 min
    n = generaciones.reclamar_atascadas(3600, ahora=AHORA)
    assert n == 0
    assert generaciones.obtener(g["id"])["estado"] == generaciones.ESTADO_EJECUTANDO


def test_no_toca_las_terminales(almacen):
    """`completado`/`error` viejas no se reclaman (ya están cerradas)."""
    c = _crear(generaciones.ESTADO_COMPLETADO, _hace(10))
    e = _crear(generaciones.ESTADO_ERROR, _hace(10))
    n = generaciones.reclamar_atascadas(3600, ahora=AHORA)
    assert n == 0
    assert generaciones.obtener(c["id"])["estado"] == generaciones.ESTADO_COMPLETADO
    assert generaciones.obtener(e["id"])["estado"] == generaciones.ESTADO_ERROR


def test_devuelve_cuantas_reclamo(almacen):
    _crear(generaciones.ESTADO_EJECUTANDO, _hace(5))
    _crear(generaciones.ESTADO_EJECUTANDO, _hace(5))
    _crear(generaciones.ESTADO_EJECUTANDO, _hace(0.05))  # reciente, no cuenta
    assert generaciones.reclamar_atascadas(3600, ahora=AHORA) == 2


def test_almacen_vacio_no_rompe(almacen):
    assert generaciones.reclamar_atascadas(3600, ahora=AHORA) == 0


# --------------------------------------------------------------------------- #
# TTL del reparación de QA 'en_curso' (derivado del timeout real; sin BD)            #
# --------------------------------------------------------------------------- #


def test_ttl_qa_en_curso_derivado_del_timeout_real(monkeypatch):
    """Sin override, el TTL es ~2x el wall-timeout REAL de la criba (no 30 min fijos)."""
    from keni_consola import config
    from keni_consola import reaper_generaciones as rg

    monkeypatch.delenv(config.ENV_QA_EN_CURSO_TTL_MIN, raising=False)
    monkeypatch.delenv("KENI_QA_FUENTE_TIMEOUT", raising=False)
    assert rg._ttl_qa_en_curso_seg() == 2 * config.qa_fuente_timeout()  # def 2x180 = 360 s

    monkeypatch.setenv("KENI_QA_FUENTE_TIMEOUT", "60")
    assert rg._ttl_qa_en_curso_seg() == 120

    # Criba sin endurecer (timeout 0): rige el wall-timeout global de claude.
    monkeypatch.setenv("KENI_QA_FUENTE_TIMEOUT", "0")
    assert rg._ttl_qa_en_curso_seg() == 2 * config.claude_timeout()


def test_ttl_qa_en_curso_respeta_el_override_explicito(monkeypatch):
    """`KENI_QA_EN_CURSO_TTL_MIN` explicito manda sobre la derivacion."""
    from keni_consola import config
    from keni_consola import reaper_generaciones as rg

    monkeypatch.setenv(config.ENV_QA_EN_CURSO_TTL_MIN, "30")
    assert rg._ttl_qa_en_curso_seg() == 30 * 60
