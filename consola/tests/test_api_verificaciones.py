"""Tests de la API Verificacion (/api/verificar). OFFLINE: NUNCA se toca la red.

El motor real (`verifica-video/analiza-video.py`, que invoca yt-dlp/ffmpeg/tesseract)
se MONKEYPATCHEA: aqui solo se cubre el endpoint + el job en background (reutiliza la
infra de imagen). Cubre: validacion (400 sin enlace), exito (reporte en `resultado`)
y error del motor reflejado en el registro.
"""

from __future__ import annotations

from keni_consola.api import verificaciones

from .conftest import _cliente, lanzador_imagen_ejecuta

# Reporte canned que devolveria el motor (forma de analiza-video.py, sin ocr.texto).
_REPORTE = {
    "entrada": "https://x.com/u/status/1",
    "tipo_entrada": "url",
    "contexto_afirmado": "supuestamente de hoy",
    "metadatos": {
        "disponible": True,
        "plataforma": "Twitter",
        "titulo": "Clip viral",
        "autor": "alguien",
        "subido_iso": "2013-10-15",
        "anio_subida": 2013,
        "miniatura": "https://cdn.example/thumb.jpg",
    },
    "ocr": {"frames_analizados": 5, "anios": [2013], "fechas": ["2013-05-12"], "horas": []},
    "busqueda_inversa": {
        "base": "miniatura publica del video",
        "enlaces": {
            "tineye_mas_antiguo": "https://www.tineye.com/search?url=...&sort=crawl_date&order=asc",
            "google_lens": "https://lens.google.com/uploadbyurl?url=...",
        },
    },
    "fact_check": {"consultado": False, "motivo": "sin GOOGLE_FACTCHECK_API_KEY (opcional)."},
    "senales": [{"nivel": "medio", "texto": "Hay fechas en pantalla anteriores a la subida."}],
}


def test_verificar_sin_enlace_400(cliente):
    r = cliente.post("/api/verificar", json={})
    assert r.status_code == 400
    assert "enlace" in r.json()["error"].lower()


def test_verificar_ok(entorno, monkeypatch):
    """Con el motor MOCK, la verificacion (background) completa con `{verificacion: ...}`."""
    monkeypatch.setattr(verificaciones, "analizar", lambda enlace, contexto: {"verificacion": _REPORTE})
    cli = _cliente(lanzar_imagen=lanzador_imagen_ejecuta())
    r = cli.post("/api/verificar", json={"enlace": "https://x.com/u/status/1", "contexto": "hoy"})
    assert r.status_code == 200
    gen = r.json()["generacion"]
    assert gen["tipo"] == "verificacion"
    assert gen["estado"] == "completado"
    verif = gen["resultado"]["verificacion"]
    assert verif["metadatos"]["subido_iso"] == "2013-10-15"
    assert verif["senales"][0]["nivel"] == "medio"
    assert "tineye_mas_antiguo" in verif["busqueda_inversa"]["enlaces"]


def test_verificar_motor_error_se_refleja(entorno, monkeypatch):
    """Si el motor lanza, la generacion queda en `error` con mensaje legible (sin traceback)."""
    def _explota(enlace, contexto):  # noqa: ANN001
        raise RuntimeError("yt-dlp no pudo leer el enlace.")

    monkeypatch.setattr(verificaciones, "analizar", _explota)
    cli = _cliente(lanzar_imagen=lanzador_imagen_ejecuta())
    r = cli.post("/api/verificar", json={"enlace": "https://x.com/u/status/1"})
    assert r.status_code == 200  # el POST responde de inmediato; el error vive en el registro
    gen = r.json()["generacion"]
    assert gen["estado"] == "error"
    assert "yt-dlp" in gen["error"]
