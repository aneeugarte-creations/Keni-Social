"""Tests del motor de transcripcion (`keni_consola.transcripcion`, faster-whisper).

NO cargan faster-whisper ni el modelo reales: parchean el punto inyectable `_TRANSCRIPTOR_JSON` y,
para la disponibilidad, `sys.modules`. Cubren: deteccion de formato, disponibilidad, el mapeo PURO
de segmentos faster-whisper -> forma canonica, la delegacion de `transcribir_datos`, y el camino de
`transcribir_subida` (limite de tamano, formato, happy-path).
"""

from __future__ import annotations

import asyncio
import sys
import types

import pytest

from keni_consola import transcripcion


class _FakeUpload:
    """Mínimo `UploadFile` para los tests: nombre, content_type y `await read(n)` por trozos."""

    def __init__(self, datos: bytes, *, filename: str, content_type: str | None):
        self._datos = datos
        self._pos = 0
        self.filename = filename
        self.content_type = content_type

    async def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            trozo, self._pos = self._datos[self._pos :], len(self._datos)
            return trozo
        trozo = self._datos[self._pos : self._pos + n]
        self._pos += len(trozo)
        return trozo


def _correr(coro):
    return asyncio.run(coro)


# --- deteccion de formato ----------------------------------------------------


@pytest.mark.parametrize(
    "ct,nombre,esperado",
    [
        ("video/mp4", "x.mp4", "mp4"),
        ("audio/mpeg", "x.mp3", "mp3"),
        ("audio/mp4", "x.m4a", "m4a"),
        (None, "grabacion.MOV", "mov"),  # por nombre cuando no hay content-type
        ("video/mp4;codecs=avc1", "x", "mp4"),  # ignora parámetros del content-type
        ("text/plain", "notas.txt", None),  # no es vídeo/audio
        (None, "sin-extension", None),
    ],
)
def test_ext_de_subida(ct, nombre, esperado):
    assert transcripcion.ext_de_subida(ct, nombre) == esperado


# --- disponibilidad (¿está el motor faster-whisper?) -------------------------


def test_disponible_true_con_el_motor(monkeypatch):
    monkeypatch.setitem(sys.modules, "faster_whisper", types.ModuleType("faster_whisper"))
    assert transcripcion.transcripcion_disponible() is True


def test_disponible_false_sin_el_motor(monkeypatch):
    # `sys.modules[...] = None` hace que `import faster_whisper` lance ImportError.
    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    assert transcripcion.transcripcion_disponible() is False


# --- PURO: mapear_segmentos (salida faster-whisper -> forma canonica) --------


class _Word:
    def __init__(self, start, end, word):
        self.start, self.end, self.word = start, end, word


class _Segment:
    def __init__(self, start, end, text, words):
        self.start, self.end, self.text, self.words = start, end, text, words


def _segmentos_fake_fw():
    """Estructura como la que devuelve faster-whisper (objetos con atributos)."""
    return [
        _Segment(0.0, 1.5, "Hola mundo", [_Word(0.0, 0.5, "Hola"), _Word(0.6, 1.5, "mundo")]),
        _Segment(2.0, 2.4, "adios", [_Word(2.0, 2.4, "adios")]),
    ]


def test_mapear_segmentos_word_level():
    segs = transcripcion.mapear_segmentos(_segmentos_fake_fw(), word_level=True)
    assert len(segs) == 2
    assert segs[0]["inicio_ms"] == 0 and segs[0]["fin_ms"] == 1500
    assert segs[0]["texto"] == "Hola mundo"
    assert segs[0]["palabras"] == [
        {"inicio_ms": 0, "fin_ms": 500, "texto": "Hola"},
        {"inicio_ms": 600, "fin_ms": 1500, "texto": "mundo"},
    ]
    assert segs[1]["palabras"][0]["texto"] == "adios"


def test_mapear_segmentos_sin_word_level_no_trocea():
    segs = transcripcion.mapear_segmentos(_segmentos_fake_fw(), word_level=False)
    assert segs[0]["palabras"] == [] and segs[0]["texto"] == "Hola mundo"


def test_mapear_segmentos_acepta_dicts_y_clave_text():
    # Acepta dicts (no solo objetos) y 'text' como alias de 'word' a nivel palabra.
    crudos = [
        {"start": 1.0, "end": 2.0, "text": "uno dos",
         "words": [{"start": 1.0, "end": 1.4, "text": "uno"},
                   {"start": 1.5, "end": 2.0, "word": "dos"}]},
    ]
    segs = transcripcion.mapear_segmentos(crudos, word_level=True)
    assert segs[0]["inicio_ms"] == 1000 and segs[0]["fin_ms"] == 2000
    assert [p["texto"] for p in segs[0]["palabras"]] == ["uno", "dos"]


def test_mapear_segmentos_descarta_vacios():
    assert transcripcion.mapear_segmentos([{"start": 0, "end": 0, "text": "  ", "words": []}]) == []


# --- PURO: srt_de_segmentos ---------------------------------------------------


def test_srt_de_segmentos():
    segs = [
        {"inicio_ms": 0, "fin_ms": 1500, "texto": "Hola mundo"},
        {"inicio_ms": 2000, "fin_ms": 2400, "texto": "adiós"},
    ]
    srt = transcripcion.srt_de_segmentos(segs)
    assert srt == (
        "1\n00:00:00,000 --> 00:00:01,500\nHola mundo\n\n"
        "2\n00:00:02,000 --> 00:00:02,400\nadiós\n"
    )


def test_srt_de_segmentos_descarta_vacios_y_vacio():
    assert transcripcion.srt_de_segmentos([{"inicio_ms": 0, "fin_ms": 0, "texto": "  "}]) == ""
    assert transcripcion.srt_de_segmentos([]) == ""


# --- transcribir_datos (delega en el inyectable _TRANSCRIPTOR_JSON) ----------


def test_transcribir_datos_delega_en_inyectable(monkeypatch):
    visto: dict = {}

    def fake(datos, *, ext, idioma, word_level):
        visto.update(datos=datos, ext=ext, idioma=idioma, word_level=word_level)
        return {"texto": "hola", "segmentos": [{"inicio_ms": 0, "fin_ms": 1, "texto": "hola", "palabras": []}]}

    monkeypatch.setattr(transcripcion, "_TRANSCRIPTOR_JSON", fake)
    res = transcripcion.transcribir_datos(b"bytes", ext="mp3", idioma="es-MX", word_level=True)
    assert res["texto"] == "hola" and len(res["segmentos"]) == 1
    assert visto == {"datos": b"bytes", "ext": "mp3", "idioma": "es-MX", "word_level": True}


# --- transcribir_subida (con el motor mockeado) ------------------------------


def test_transcribir_subida_formato_no_soportado():
    up = _FakeUpload(b"hola", filename="notas.txt", content_type="text/plain")
    with pytest.raises(transcripcion.TranscripcionError):
        _correr(transcripcion.transcribir_subida(up))


def test_transcribir_subida_vacio():
    up = _FakeUpload(b"", filename="x.mp4", content_type="video/mp4")
    with pytest.raises(transcripcion.TranscripcionError):
        _correr(transcripcion.transcribir_subida(up))


def test_transcribir_subida_demasiado_grande(monkeypatch):
    monkeypatch.setattr(transcripcion, "LIMITE_CLIP", 4)
    up = _FakeUpload(b"12345", filename="x.mp4", content_type="video/mp4")
    with pytest.raises(transcripcion.TranscripcionError):
        _correr(transcripcion.transcribir_subida(up))


def test_transcribir_subida_camino_feliz(monkeypatch):
    visto: dict = {}

    def fake(datos, *, ext, idioma="es", word_level=False):
        visto.update(datos=datos, ext=ext)
        return {"texto": "  texto transcrito  ", "segmentos": []}

    monkeypatch.setattr(transcripcion, "_TRANSCRIPTOR_JSON", fake)
    up = _FakeUpload(b"clipbytes", filename="x.mp4", content_type="video/mp4")
    texto = _correr(transcripcion.transcribir_subida(up))
    assert texto == "  texto transcrito  "  # devuelve el `.texto` del motor tal cual
    assert visto == {"datos": b"clipbytes", "ext": "mp4"}
