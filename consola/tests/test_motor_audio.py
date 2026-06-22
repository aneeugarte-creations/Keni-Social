"""Motor de TRANSCRIPCION del gestor de AUDIO (audio→texto).

Ejecutor `motores.audio.ejecutar_transcripcion_audio` con el MOTOR COMPARTIDO
(`keni_consola.transcripcion.transcribir_datos`) y `media` MONKEYPATCHEADOS: deps ausentes ->
error claro + fila en 'error'; happy-path -> escribe segmentos+texto y estado='transcrito'.

Los tests del ejecutor tocan `audio_transcripciones`, así que usan la fixture `entorno` (Postgres
de pruebas; se saltan sin él).
"""

from __future__ import annotations

import copy
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


def _mock_motor(monkeypatch, *, duracion_s, segs):
    """Mockea el camino POR TRAMOS: decodifica->sentinela; duración fija; cada tramo devuelve los
    segmentos (timestamps absolutos) cuyo inicio cae en [inicio_s, fin_s). Devuelve la lista de
    ventanas pedidas, para comprobar la reanudación."""
    monkeypatch.setattr(transcripcion_raiz, "decodificar_audio", lambda datos, *, ext: object())
    monkeypatch.setattr(transcripcion_raiz, "duracion_audio", lambda _audio: duracion_s)
    ventanas: list[tuple[float, float]] = []

    def _frag(_audio, *, inicio_s, fin_s, idioma, word_level=False):
        ventanas.append((inicio_s, fin_s))
        ini_ms, fin_ms = int(inicio_s * 1000), int(fin_s * 1000)
        return [copy.deepcopy(s) for s in segs if ini_ms <= s["inicio_ms"] < fin_ms]

    monkeypatch.setattr(transcripcion_raiz, "transcribir_fragmento", _frag)
    return ventanas


def test_ejecutor_audio_falta_transcripcion_id_error(monkeypatch):
    capturas: list[dict] = []
    monkeypatch.setattr(
        generaciones, "actualizar", lambda gid, cambios: capturas.append(cambios) or cambios
    )
    audio.ejecutar_transcripcion_audio("g1", {"media_id": "audios/x.mp4"})
    assert capturas[-1]["estado"] == generaciones.ESTADO_ERROR


def test_ejecutor_audio_deps_ausentes_marca_error(entorno, monkeypatch):
    """Sin el motor (extra asr), decodificar lanza error; el ejecutor lo refleja en la fila."""
    fila = repos.crear_audio_transcripcion(marca=_MARCA, media_id="audios/x.mp4")
    monkeypatch.setattr(media, "leer_objeto", lambda nombre: b"fake-bytes")

    def _falla(*a, **k):
        raise transcripcion_raiz.TranscripcionError("Falta el motor de transcripción en este servicio.")

    monkeypatch.setattr(transcripcion_raiz, "decodificar_audio", _falla)

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
    """Con el motor (por tramos) mockeado, persiste segmentos+texto y estado='transcrito'."""
    fila = repos.crear_audio_transcripcion(
        marca=_MARCA, media_id="audios/x.mp4", nombre="grabacion.mp4", idioma="es-MX"
    )
    monkeypatch.setattr(media, "leer_objeto", lambda nombre: b"fake-bytes")
    _mock_motor(monkeypatch, duracion_s=2.4, segs=_segmentos_canonicos())

    audio.ejecutar_transcripcion_audio(
        "g3", {"transcripcion_id": fila["id"], "media_id": "audios/x.mp4", "idioma": "es-MX"}
    )

    out = repos.obtener_audio_transcripcion(fila["id"])
    assert out["estado"] == "transcrito"
    assert out["texto"] == "Hola mundo adiós"
    assert out["duracion_ms"] == 2400
    assert out["progreso_ms"] == 2400  # checkpoint al 100%
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


def test_ejecutor_audio_segmento_sin_fin_ms_no_revienta(entorno, monkeypatch):
    """Un segmento ASR sin `fin_ms` no tumba el cierre: la duración cae al total transcrito."""
    fila = repos.crear_audio_transcripcion(
        marca=_MARCA, media_id="audios/y.mp4", nombre="grabacion.mp4", idioma="es-MX"
    )
    monkeypatch.setattr(media, "leer_objeto", lambda nombre: b"fake-bytes")
    segs = [
        {"inicio_ms": 0, "fin_ms": 1500, "texto": "Hola mundo", "palabras": []},
        {"inicio_ms": 2000, "texto": "adiós", "palabras": []},  # sin `fin_ms`
    ]
    _mock_motor(monkeypatch, duracion_s=2.4, segs=segs)

    audio.ejecutar_transcripcion_audio(
        "g9", {"transcripcion_id": fila["id"], "media_id": "audios/y.mp4", "idioma": "es-MX"}
    )

    out = repos.obtener_audio_transcripcion(fila["id"])
    assert out["estado"] == "transcrito"
    assert out["duracion_ms"] == 2400  # respaldo al total tras transcribir
    assert generaciones.obtener("g9")["estado"] == generaciones.ESTADO_COMPLETADO


def test_ejecutor_audio_reanuda_desde_checkpoint(entorno, monkeypatch):
    """Con un checkpoint a medias, REANUDA: solo transcribe el tramo restante y no duplica el SRT."""
    # Audio de 600 s, ya transcrito hasta 300 s (un segmento guardado).
    hechos = [{"inicio_ms": 10_000, "fin_ms": 11_000, "texto": "ya hecho", "palabras": []}]
    fila = repos.crear_audio_transcripcion(
        marca=_MARCA, media_id="audios/x.mp4", idioma="es-MX",
        segmentos=json.dumps(hechos), progreso_ms=300_000, estado="transcribiendo",
    )
    repos.crear_audio_artefacto(  # un SRT a medias de la pasada anterior
        transcripcion_id=fila["id"], tipo="srt", titulo="Subtítulos (SRT)", contenido="viejo", formato="srt"
    )
    monkeypatch.setattr(media, "leer_objeto", lambda nombre: b"fake-bytes")
    # El tramo [300,600) produce un segmento nuevo en 400 s.
    todos = hechos + [{"inicio_ms": 400_000, "fin_ms": 401_000, "texto": "resto", "palabras": []}]
    ventanas = _mock_motor(monkeypatch, duracion_s=600.0, segs=todos)

    audio.ejecutar_transcripcion_audio(
        "g6", {"transcripcion_id": fila["id"], "media_id": "audios/x.mp4", "idioma": "es-MX"}
    )

    # Solo se pidió el tramo restante (no se rehízo desde 0).
    assert ventanas == [(300.0, 600.0)]
    out = repos.obtener_audio_transcripcion(fila["id"])
    assert out["estado"] == "transcrito"
    segs = json.loads(out["segmentos"])
    assert [s["texto"] for s in segs] == ["ya hecho", "resto"]
    # Idempotente: no duplica el SRT que ya existía.
    arts = repos.listar_audio_artefactos(fila["id"])
    assert [a["tipo"] for a in arts] == ["srt"] and arts[0]["contenido"] == "viejo"


def test_ejecutor_audio_tratamientos_crea_texto_y_lanza_claude(entorno, monkeypatch):
    """Con tratamientos pedidos: crea SRT + texto (síncronos) y LANZA los de Claude."""
    fila = repos.crear_audio_transcripcion(marca=_MARCA, media_id="audios/x.mp4", idioma="es-MX")
    monkeypatch.setattr(media, "leer_objeto", lambda nombre: b"fake-bytes")
    _mock_motor(monkeypatch, duracion_s=2.4, segs=_segmentos_canonicos())

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
