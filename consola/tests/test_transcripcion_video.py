"""Motor de TRANSCRIPCION ASR de subtitulos de video (Ola VIDEO).

Cubre:
  - PURO: `segmentos_a_ass` (cabecera valida, estilo, tags \\k karaoke con duraciones en cs).
  - Ejecutor con el MOTOR COMPARTIDO (`keni_consola.transcripcion.transcribir_datos`) y `media`
    MONKEYPATCHEADOS: motor ausente (extra asr) -> error claro; happy-path -> escribe en
    video_subtitulos estado='transcrito'.

El mapeo del JSON de whisper.cpp a segmentos vive ahora en el motor compartido
(`keni_consola.transcripcion.mapear_segmentos`, cubierto en `test_transcripcion.py`).

Los tests PUROS no necesitan modelo, ffmpeg ni Postgres. Los del ejecutor que tocan
`video_subtitulos` usan la fixture `entorno` (Postgres de pruebas; se saltan sin el).
"""

from __future__ import annotations

import json

from keni_consola import generaciones, media, repos
from keni_consola import transcripcion as transcripcion_raiz
from keni_consola.motores import transcripcion

_MARCA = "claro-sports"


def _segmentos_canonicos():
    """Segmentos en la FORMA canonica que devuelve el motor compartido (word-level)."""
    return [
        {
            "inicio_ms": 0, "fin_ms": 1500, "texto": "Hola mundo",
            "palabras": [
                {"inicio_ms": 0, "fin_ms": 500, "texto": "Hola"},
                {"inicio_ms": 600, "fin_ms": 1500, "texto": "mundo"},
            ],
        },
        {
            "inicio_ms": 2000, "fin_ms": 2400, "texto": "adios",
            "palabras": [{"inicio_ms": 2000, "fin_ms": 2400, "texto": "adios"}],
        },
    ]


# --------------------------------------------------------------------------- #
# PURO: segmentos_a_ass                                                         #
# --------------------------------------------------------------------------- #


def test_segmentos_a_ass_cabecera_y_estilo():
    ass = transcripcion.segmentos_a_ass(_segmentos_canonicos())
    # Cabecera ASS valida.
    assert "[Script Info]" in ass
    assert "ScriptType: v4.00+" in ass
    assert "[V4+ Styles]" in ass
    assert "[Events]" in ass
    # El estilo base (nombre 'Keni' + la fuente por defecto es-MX).
    assert "Style: Keni,Barlow,64," in ass
    assert "Format: Layer, Start, End, Style" in ass


def test_segmentos_a_ass_karaoke_duraciones_en_centisegundos():
    ass = transcripcion.segmentos_a_ass(_segmentos_canonicos())
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
    ass = transcripcion.segmentos_a_ass(_segmentos_canonicos(), {"fuente": "Roboto", "tam": 80})
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
# Ejecutor: deps ausentes, subtitulo inexistente, happy-path                   #
# (El ASR es local/gratuito/bajo-demanda: NO tiene kill-switch.)               #
# --------------------------------------------------------------------------- #


def test_ejecutor_deps_ausentes_marca_error(entorno, monkeypatch):
    """Sin el motor (extra asr), el motor compartido lanza error claro y el ejecutor lo reporta."""
    c = repos.crear_video_composicion(marca=_MARCA)
    s = repos.crear_video_subtitulo(composicion_id=c["id"])

    monkeypatch.setattr(media, "leer_objeto", lambda nombre: b"fake-video-bytes")

    def _falla(*a, **k):
        raise transcripcion_raiz.TranscripcionError(
            "Falta el motor de transcripción en este servicio."
        )

    monkeypatch.setattr(transcripcion_raiz, "transcribir_datos", _falla)

    capturas: list[dict] = []
    real_actualizar = generaciones.actualizar
    monkeypatch.setattr(
        generaciones, "actualizar",
        lambda gid, cambios: capturas.append(cambios) or real_actualizar(gid, cambios),
    )
    transcripcion.ejecutar_transcripcion("g2", {"subtitulo_id": s["id"], "media_id": "videos/x.mp4"})
    assert capturas[-1]["estado"] == generaciones.ESTADO_ERROR
    assert "motor de transcripción" in capturas[-1]["error"]
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
    """Con el motor compartido mockeado, escribe segmentos+ass y estado='transcrito'."""
    c = repos.crear_video_composicion(marca=_MARCA)
    s = repos.crear_video_subtitulo(composicion_id=c["id"])

    # El media existe en el almacen (bytes cualquiera; el motor esta mockeado).
    monkeypatch.setattr(media, "leer_objeto", lambda nombre: b"fake-video-bytes")

    def _transcribir(datos, *, ext, idioma, word_level):
        assert word_level is True
        assert idioma == "es-MX"
        segs = _segmentos_canonicos()
        return {"texto": " ".join(x["texto"] for x in segs), "segmentos": segs}

    monkeypatch.setattr(transcripcion_raiz, "transcribir_datos", _transcribir)

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
