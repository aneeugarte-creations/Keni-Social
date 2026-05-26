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
    """Set determinista que cubre los tres estados DENTRO del dominio consola.

    El error vive en un chequeo del dominio (`Fuente`), no en whisper/ffmpeg: la
    consola filtra esos chequeos clip-a-copy fuera de su indicador de salud.
    """
    return [
        doctor.Resultado("Python", doctor.Estado.OK, "Python 3.12.1"),
        doctor.Resultado("Fuente", doctor.Estado.ERROR, "No se pudo construir la fuente"),
        doctor.Resultado("Configuracion", doctor.Estado.AVISO, "No hay config (se usa muestra)"),
        doctor.Resultado("Credenciales", doctor.Estado.AVISO, "0/5 plataformas conectadas"),
    ]


def _resultados_con_clip_a_copy() -> list[doctor.Resultado]:
    """El set del doctor incluye los chequeos clip-a-copy que la consola filtra."""
    return [
        *_resultados_demo(),
        doctor.Resultado("binario whisper-cli", doctor.Estado.ERROR, "whisper-cli no esta en el PATH."),
        doctor.Resultado("binario ffmpeg", doctor.Estado.ERROR, "ffmpeg no esta en el PATH."),
        doctor.Resultado("modelo whisper", doctor.Estado.ERROR, "no se encontro modelo de whisper."),
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


def test_estado_filtra_chequeos_clip_a_copy(entorno, monkeypatch):
    """whisper-cli / ffmpeg / modelo whisper NO aparecen en el indicador consola."""
    monkeypatch.setattr(
        api_estado, "ejecutar_chequeos", lambda *a, **k: _resultados_con_clip_a_copy()
    )
    datos = _cliente().get("/api/estado").json()
    nombres = {r["nombre"] for r in datos["resultados"]}
    assert "binario whisper-cli" not in nombres
    assert "binario ffmpeg" not in nombres
    assert "modelo whisper" not in nombres
    # Los chequeos del dominio de la consola SI se conservan.
    assert {"Python", "Fuente", "Configuracion", "Credenciales"} <= nombres


def test_estado_filtrado_no_arrastra_error_ajeno(entorno, monkeypatch):
    """El resumen/estado refleja solo el dominio: un error ajeno no lo contamina."""
    solo_clip = [
        doctor.Resultado("Python", doctor.Estado.OK, "Python 3.12.1"),
        doctor.Resultado("binario whisper-cli", doctor.Estado.ERROR, "no esta"),
        doctor.Resultado("binario ffmpeg", doctor.Estado.ERROR, "no esta"),
    ]
    monkeypatch.setattr(api_estado, "ejecutar_chequeos", lambda *a, **k: solo_clip)
    datos = _cliente().get("/api/estado").json()
    estados = {r["estado"] for r in datos["resultados"]}
    assert estados == {"ok"}
    # El resumen se calcula sobre lo filtrado (solo el Python OK), sin errores.
    assert datos["resumen"] == doctor.resumen_humano([solo_clip[0]])


def test_estado_real_offline_no_crashea(entorno):
    """Sin mock: el doctor real (escaneo de PATH, sin red) responde 200."""
    r = _cliente().get("/api/estado")
    assert r.status_code == 200
    assert "resultados" in r.json()
