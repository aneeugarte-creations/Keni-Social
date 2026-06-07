"""Motor de TRANSCRIPCION ASR de subtitulos de video (Ola VIDEO).

Cubre:
  - PURO: `segmentos_a_ass` (cabecera valida, estilo, tags \\k karaoke con duraciones en cs).
  - PURO: `construir_segmentos` (mapeo de la salida de faster-whisper a nuestro JSON word-level).
  - Ejecutor con faster-whisper y ffmpeg MONKEYPATCHEADOS: kill-switch off -> error; import
    ausente -> error claro; happy-path -> escribe en video_subtitulos estado='transcrito'.

Los tests PUROS no necesitan modelo, ffmpeg ni Postgres. Los del ejecutor que tocan
`video_subtitulos` usan la fixture `entorno` (Postgres de pruebas; se saltan sin el).
"""

from __future__ import annotations

import json
import sys
import types

from keni_consola import generaciones, media, repos
from keni_consola.motores import transcripcion

_MARCA = "claro-sports"


# --------------------------------------------------------------------------- #
# Helpers de simulacion de la salida de faster-whisper                          #
# --------------------------------------------------------------------------- #


class _Word:
    def __init__(self, start, end, word):
        self.start, self.end, self.word = start, end, word


class _Segment:
    def __init__(self, start, end, text, words):
        self.start, self.end, self.text, self.words = start, end, text, words


def _segmentos_fake_fw():
    """Estructura como la que devuelve faster-whisper (objetos con atributos)."""
    return [
        _Segment(
            0.0, 1.5, "Hola mundo",
            [_Word(0.0, 0.5, "Hola"), _Word(0.6, 1.5, "mundo")],
        ),
        _Segment(
            2.0, 2.4, "adios",
            [_Word(2.0, 2.4, "adios")],
        ),
    ]


# --------------------------------------------------------------------------- #
# PURO: construir_segmentos                                                     #
# --------------------------------------------------------------------------- #


def test_construir_segmentos_desde_objetos():
    segs = transcripcion.construir_segmentos(_segmentos_fake_fw())
    assert len(segs) == 2
    s0 = segs[0]
    assert s0["inicio_ms"] == 0 and s0["fin_ms"] == 1500
    assert s0["texto"] == "Hola mundo"
    assert s0["palabras"] == [
        {"inicio_ms": 0, "fin_ms": 500, "texto": "Hola"},
        {"inicio_ms": 600, "fin_ms": 1500, "texto": "mundo"},
    ]
    assert segs[1]["palabras"][0]["texto"] == "adios"


def test_construir_segmentos_acepta_dicts_y_clave_text():
    # Acepta dicts (no solo objetos) y 'text' como alias de 'word' a nivel palabra.
    crudos = [
        {"start": 1.0, "end": 2.0, "text": "uno dos",
         "words": [{"start": 1.0, "end": 1.4, "text": "uno"},
                   {"start": 1.5, "end": 2.0, "word": "dos"}]},
    ]
    segs = transcripcion.construir_segmentos(crudos)
    assert segs[0]["inicio_ms"] == 1000 and segs[0]["fin_ms"] == 2000
    assert [p["texto"] for p in segs[0]["palabras"]] == ["uno", "dos"]


def test_construir_segmentos_descarta_vacios():
    crudos = [{"start": 0, "end": 0, "text": "  ", "words": []}]
    assert transcripcion.construir_segmentos(crudos) == []


# --------------------------------------------------------------------------- #
# PURO: segmentos_a_ass                                                         #
# --------------------------------------------------------------------------- #


def test_segmentos_a_ass_cabecera_y_estilo():
    segs = transcripcion.construir_segmentos(_segmentos_fake_fw())
    ass = transcripcion.segmentos_a_ass(segs)
    # Cabecera ASS valida.
    assert "[Script Info]" in ass
    assert "ScriptType: v4.00+" in ass
    assert "[V4+ Styles]" in ass
    assert "[Events]" in ass
    # El estilo base (nombre 'Keni' + la fuente por defecto es-MX).
    assert "Style: Keni,Barlow,64," in ass
    assert "Format: Layer, Start, End, Style" in ass


def test_segmentos_a_ass_karaoke_duraciones_en_centisegundos():
    segs = transcripcion.construir_segmentos(_segmentos_fake_fw())
    ass = transcripcion.segmentos_a_ass(segs)
    # Primer Dialogue: "Hola" dura 0.5s -> \k50; hueco 0.1s -> \k10; "mundo" dura 0.9s -> \k90.
    assert "{\\k50}Hola " in ass
    assert "{\\k10} " in ass  # hueco entre palabras
    assert "{\\k90}mundo" in ass
    # Tiempos del evento en formato ASS H:MM:SS.cc.
    assert "Dialogue: 0,0:00:00.00,0:00:01.50,Keni" in ass
    # Segundo segmento: "adios" 0.4s -> \k40, evento de 2.00 a 2.40.
    assert "Dialogue: 0,0:00:02.00,0:00:02.40,Keni" in ass
    assert "{\\k40}adios" in ass


def test_segmentos_a_ass_estilo_personalizado():
    segs = transcripcion.construir_segmentos(_segmentos_fake_fw())
    ass = transcripcion.segmentos_a_ass(segs, {"fuente": "Roboto", "tam": 80})
    assert "Style: Keni,Roboto,80," in ass


def test_segmentos_a_ass_sin_palabras_cae_a_texto_plano():
    segs = [{"inicio_ms": 0, "fin_ms": 1000, "texto": "sin karaoke", "palabras": []}]
    ass = transcripcion.segmentos_a_ass(segs)
    assert "sin karaoke" in ass
    assert "\\k" not in ass.split("[Events]")[1]


def test_segmentos_a_ass_escapa_llaves():
    segs = [{"inicio_ms": 0, "fin_ms": 1000, "texto": "{raro}", "palabras": []}]
    ass = transcripcion.segmentos_a_ass(segs)
    # Las llaves del texto no deben aparecer crudas (romperian el parser ASS).
    eventos = ass.split("[Events]")[1]
    assert "{raro}" not in eventos
    assert "(raro)" in eventos


# --------------------------------------------------------------------------- #
# Ejecutor: import ausente, happy-path                                          #
# (El ASR es local/gratuito/bajo-demanda: NO tiene kill-switch.)               #
# --------------------------------------------------------------------------- #


def test_ejecutor_import_ausente_marca_error(entorno, monkeypatch):
    """Sin faster-whisper instalado, el ejecutor degrada con error claro (no rompe)."""
    # Subtitulo real para pasar la validacion previa.
    c = repos.crear_video_composicion(marca=_MARCA)
    s = repos.crear_video_subtitulo(composicion_id=c["id"])
    # Forzar ImportError del import perezoso `from faster_whisper import WhisperModel`.
    monkeypatch.setitem(sys.modules, "faster_whisper", None)

    capturas: list[dict] = []
    real_actualizar = generaciones.actualizar
    monkeypatch.setattr(
        generaciones, "actualizar",
        lambda gid, cambios: capturas.append(cambios) or real_actualizar(gid, cambios),
    )
    transcripcion.ejecutar_transcripcion("g2", {"subtitulo_id": s["id"], "media_id": "videos/x.mp4"})
    assert capturas[-1]["estado"] == generaciones.ESTADO_ERROR
    assert "faster-whisper" in capturas[-1]["error"]
    # El subtitulo NO avanzo de estado.
    assert repos.obtener_video_subtitulo(s["id"])["estado"] == "pendiente"


def test_ejecutor_subtitulo_inexistente_error(monkeypatch):
    capturas: list[dict] = []
    monkeypatch.setattr(
        generaciones, "actualizar", lambda gid, cambios: capturas.append(cambios) or cambios
    )
    transcripcion.ejecutar_transcripcion("g3", {"subtitulo_id": "no-existe", "media_id": "videos/x.mp4"})
    assert capturas[-1]["estado"] == generaciones.ESTADO_ERROR


def test_ejecutor_happy_path_escribe_transcrito(entorno, monkeypatch):
    """Con ffmpeg + faster-whisper mockeados, escribe segmentos+ass y estado='transcrito'."""
    c = repos.crear_video_composicion(marca=_MARCA)
    s = repos.crear_video_subtitulo(composicion_id=c["id"])

    # El media existe en el almacen (bytes cualquiera; ffmpeg esta mockeado).
    monkeypatch.setattr(media, "leer_objeto", lambda nombre: b"fake-video-bytes")
    # ffmpeg: en vez de extraer audio, escribe un wav vacio en el destino.
    monkeypatch.setattr(
        transcripcion, "_extraer_audio_wav",
        lambda origen, destino: destino.write_bytes(b"RIFF"),
    )

    # faster-whisper falso: modulo con WhisperModel que devuelve el iterador simulado.
    class _ModeloFake:
        def __init__(self, modelo):
            self.modelo = modelo

        def transcribe(self, ruta, **kw):
            assert kw.get("word_timestamps") is True
            assert kw.get("language") == "es"  # 'es-MX' -> 'es'
            return iter(_segmentos_fake_fw()), {"language": "es"}

    fake_mod = types.ModuleType("faster_whisper")
    fake_mod.WhisperModel = _ModeloFake
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_mod)

    transcripcion.ejecutar_transcripcion(
        "g4", {"subtitulo_id": s["id"], "media_id": "videos/x.mp4", "idioma": "es-MX"}
    )

    sub = repos.obtener_video_subtitulo(s["id"])
    assert sub["estado"] == "transcrito"
    assert sub["transcrito_en"]
    segs = json.loads(sub["segmentos"])
    assert len(segs) == 2 and segs[0]["palabras"][0]["texto"] == "Hola"
    assert "[Script Info]" in sub["ass"]
    assert "{\\k50}Hola " in sub["ass"]

    g = generaciones.obtener("g4")
    assert g["estado"] == generaciones.ESTADO_COMPLETADO
    assert g["resultado"]["subtitulo_id"] == s["id"]
    assert g["resultado"]["segmentos"] == 2
