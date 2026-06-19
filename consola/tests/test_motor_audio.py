"""Motor de TRANSCRIPCION del gestor de AUDIO (audio→texto).

Ejecutor `motores.audio.ejecutar_transcripcion_audio` con el MOTOR COMPARTIDO
(`keni_consola.transcripcion.transcribir_datos`) y `media` MONKEYPATCHEADOS: deps ausentes ->
error claro + fila en 'error'; happy-path -> escribe segmentos+texto y estado='transcrito'.

Los tests del ejecutor tocan `audio_transcripciones`, así que usan la fixture `entorno` (Postgres
de pruebas; se saltan sin él).
"""

from __future__ import annotations

import json

from keni_consola import generaciones, media, repos
from keni_consola import transcripcion as transcripcion_raiz
from keni_consola.motores import audio

_MARCA = "claro-sports"


def _segmentos_canonicos():
    return [
        {"inicio_ms": 0, "fin_ms": 1500, "texto": "Hola mundo", "palabras": []},
        {"inicio_ms": 2000, "fin_ms": 2400, "texto": "adiós", "palabras": []},
    ]


def test_ejecutor_audio_falta_transcripcion_id_error(monkeypatch):
    capturas: list[dict] = []
    monkeypatch.setattr(
        generaciones, "actualizar", lambda gid, cambios: capturas.append(cambios) or cambios
    )
    audio.ejecutar_transcripcion_audio("g1", {"media_id": "audios/x.mp4"})
    assert capturas[-1]["estado"] == generaciones.ESTADO_ERROR


def test_ejecutor_audio_deps_ausentes_marca_error(entorno, monkeypatch):
    """Sin el motor (extra asr), el motor compartido lanza error; el ejecutor lo refleja en la fila."""
    fila = repos.crear_audio_transcripcion(marca=_MARCA, media_id="audios/x.mp4")
    monkeypatch.setattr(media, "leer_objeto", lambda nombre: b"fake-bytes")

    def _falla(*a, **k):
        raise transcripcion_raiz.TranscripcionError("Falta el motor de transcripción en este servicio.")

    monkeypatch.setattr(transcripcion_raiz, "transcribir_datos", _falla)

    capturas: list[dict] = []
    real = generaciones.actualizar
    monkeypatch.setattr(
        generaciones, "actualizar",
        lambda gid, cambios: capturas.append(cambios) or real(gid, cambios),
    )
    audio.ejecutar_transcripcion_audio(
        "g2", {"transcripcion_id": fila["id"], "media_id": "audios/x.mp4"}
    )
    assert capturas[-1]["estado"] == generaciones.ESTADO_ERROR
    assert "motor de transcripción" in capturas[-1]["error"]
    # La fila queda en 'error' con el motivo.
    actualizada = repos.obtener_audio_transcripcion(fila["id"])
    assert actualizada["estado"] == "error"
    assert "motor de transcripción" in actualizada["error"]


def test_ejecutor_audio_happy_path_escribe_transcrito(entorno, monkeypatch):
    """Con el motor compartido mockeado, persiste segmentos+texto y estado='transcrito'."""
    fila = repos.crear_audio_transcripcion(
        marca=_MARCA, media_id="audios/x.mp4", nombre="grabacion.mp4", idioma="es-MX"
    )
    monkeypatch.setattr(media, "leer_objeto", lambda nombre: b"fake-bytes")

    def _transcribir(datos, *, ext, idioma, word_level, progreso=None):
        assert ext == "mp4" and idioma == "es-MX"
        # El motor pasa un callback de progreso; lo invocamos para cubrir ese camino.
        if progreso is not None:
            progreso(1.5, 2.4)
        segs = _segmentos_canonicos()
        return {"texto": " ".join(s["texto"] for s in segs), "segmentos": segs}

    monkeypatch.setattr(transcripcion_raiz, "transcribir_datos", _transcribir)

    audio.ejecutar_transcripcion_audio(
        "g3", {"transcripcion_id": fila["id"], "media_id": "audios/x.mp4", "idioma": "es-MX"}
    )

    out = repos.obtener_audio_transcripcion(fila["id"])
    assert out["estado"] == "transcrito"
    assert out["texto"] == "Hola mundo adiós"
    assert out["duracion_ms"] == 2400
    segs = json.loads(out["segmentos"])
    assert len(segs) == 2 and segs[0]["texto"] == "Hola mundo"

    g = generaciones.obtener("g3")
    assert g["estado"] == generaciones.ESTADO_COMPLETADO
    assert g["resultado"]["transcripcion_id"] == fila["id"]
    assert g["resultado"]["segmentos"] == 2

    # Sin tratamientos pedidos, el motor crea SOLO el artefacto SRT (siempre).
    arts = repos.listar_audio_artefactos(fila["id"])
    assert [a["tipo"] for a in arts] == ["srt"]
    srt = arts[0]
    assert srt["formato"] == "srt" and srt["estado"] == "listo"
    assert "00:00:00,000 --> 00:00:01,500" in srt["contenido"]


def test_ejecutor_audio_tratamientos_crea_texto_y_lanza_claude(entorno, monkeypatch):
    """Con tratamientos pedidos: crea SRT + texto (síncronos) y LANZA los de Claude."""
    fila = repos.crear_audio_transcripcion(marca=_MARCA, media_id="audios/x.mp4", idioma="es-MX")
    monkeypatch.setattr(media, "leer_objeto", lambda nombre: b"fake-bytes")
    monkeypatch.setattr(
        transcripcion_raiz, "transcribir_datos",
        lambda datos, *, ext, idioma, word_level, progreso=None: {
            "texto": "hola", "segmentos": _segmentos_canonicos()
        },
    )

    from keni_consola.dominio import audio_artefactos
    lanzados: list[str] = []

    def _fake_lanzar(transcripcion, tipo, **k):
        lanzados.append(tipo)
        return {"artefacto": {"id": "a-" + tipo}, "gen": {"id": "g-" + tipo}}

    monkeypatch.setattr(audio_artefactos, "lanzar_tratamiento", _fake_lanzar)

    audio.ejecutar_transcripcion_audio(
        "g5",
        {
            "transcripcion_id": fila["id"], "media_id": "audios/x.mp4", "idioma": "es-MX",
            "tratamientos": ["texto", "resumen", "ideas"],
        },
    )

    tipos = sorted(a["tipo"] for a in repos.listar_audio_artefactos(fila["id"]))
    assert tipos == ["srt", "texto"]  # los síncronos; los de Claude los crea el launcher (mockeado)
    assert sorted(lanzados) == ["ideas", "resumen"]  # 'texto' NO va por el launcher


def test_ejecutor_audio_media_inexistente_error(entorno, monkeypatch):
    fila = repos.crear_audio_transcripcion(marca=_MARCA, media_id="audios/x.mp4")
    monkeypatch.setattr(media, "leer_objeto", lambda nombre: None)
    audio.ejecutar_transcripcion_audio(
        "g4", {"transcripcion_id": fila["id"], "media_id": "audios/x.mp4"}
    )
    assert generaciones.obtener("g4")["estado"] == generaciones.ESTADO_ERROR
    assert repos.obtener_audio_transcripcion(fila["id"])["estado"] == "error"
