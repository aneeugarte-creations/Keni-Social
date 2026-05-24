"""Tests de la API Estado (/api/estado). Todo OFFLINE.

El doctor real escanea el PATH/rutas; para no depender de la maquina, inyectamos
`ejecutar_chequeos` con un set determinista (OK + AVISO + ERROR).
"""

from __future__ import annotations

import pytest
from keni_metricas import doctor

from keni_consola.api import estado as api_estado

from .conftest import _cliente


def _resultados_demo() -> list[doctor.Resultado]:
    """2 OK + 2 AVISO + 1 ERROR (cubre los tres estados)."""
    return [
        doctor.Resultado("Python", doctor.Estado.OK, "Python 3.12.1"),
        doctor.Resultado("Fuente", doctor.Estado.OK, "Fuente de muestra construida correctamente"),
        doctor.Resultado("Configuracion", doctor.Estado.AVISO, "No hay config (se usa muestra)"),
        doctor.Resultado("Credenciales", doctor.Estado.AVISO, "0/5 plataformas conectadas"),
        doctor.Resultado("binario whisper-cli", doctor.Estado.ERROR, "whisper-cli no esta en el PATH."),
    ]


@pytest.fixture
def doctor_mockeado(monkeypatch):
    monkeypatch.setattr(api_estado, "ejecutar_chequeos", lambda *a, **k: _resultados_demo())


def test_estado_devuelve_json_con_contrato(entorno, doctor_mockeado):
    c = _cliente()
    r = c.get("/api/estado")
    assert r.status_code == 200
    assert "application/json" in r.headers["content-type"]
    datos = r.json()
    assert set(datos) >= {"resultados", "resumen", "siguiente_paso"}
    assert isinstance(datos["resultados"], list)
    fila = datos["resultados"][0]
    assert set(fila) == {"estado", "nombre", "detalle", "icono"}


def test_estado_mapea_enum_a_strings(entorno, doctor_mockeado):
    c = _cliente()
    datos = c.get("/api/estado").json()
    estados = [r["estado"] for r in datos["resultados"]]
    assert set(estados) <= {"ok", "aviso", "error"}
    assert "ok" in estados
    assert "aviso" in estados
    assert "error" in estados


def test_estado_incluye_resumen_y_siguiente_paso(entorno, doctor_mockeado):
    resultados = _resultados_demo()
    datos = _cliente().get("/api/estado").json()
    assert datos["resumen"] == doctor.resumen_humano(resultados)
    assert datos["siguiente_paso"] == doctor.cierre_accionable(resultados)


def test_estado_no_expone_secretos(entorno, monkeypatch):
    con_token = [doctor.Resultado("Credenciales", doctor.Estado.OK, "5/5 plataformas conectadas")]
    monkeypatch.setattr(api_estado, "ejecutar_chequeos", lambda *a, **k: con_token)
    datos = _cliente().get("/api/estado").json()
    assert datos["resultados"][0]["detalle"] == "5/5 plataformas conectadas"


def test_estado_si_el_doctor_lanza_da_500_en_espanol(entorno, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("fallo inesperado")

    monkeypatch.setattr(api_estado, "ejecutar_chequeos", boom)
    r = _cliente().get("/api/estado")
    assert r.status_code == 500
    assert "autodiagnóstico" in r.json()["error"]
    assert "Traceback" not in r.json()["error"]


def test_estado_real_offline_no_crashea(entorno):
    """Sin mock: el doctor real (escaneo de PATH, sin red) responde 200."""
    r = _cliente().get("/api/estado")
    assert r.status_code == 200
    assert "resultados" in r.json()
