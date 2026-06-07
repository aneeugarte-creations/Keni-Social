"""Tests del EJECUTOR de render (`estudio_video.ejecutar_render`).

ffmpeg y el horneado del overlay van MONKEYPATCHEADOS (no se ejecuta ningun binario). Repos en
Postgres de pruebas (fixture `entorno`). El render es local/gratuito/bajo-demanda: NO tiene
kill-switch. Cubren: errores de entrada, happy-path (completado con resultado
content-addressed) y la degradacion sin ASS (no falla).
"""

from __future__ import annotations

import json

from keni_consola import almacen_media, config, generaciones, repos
from keni_consola.motores import estudio_video

_MARCA = "claro-sports"

_DOC = {
    "version": 1,
    "marca": _MARCA,
    "formato": {"w": 1080, "h": 1920, "fps": 30, "preset": "9:16"},
    "duracion_ms": 30000,
    "pistas": [
        {"id": "base", "tipo": "video", "clips": [
            {"id": "c1", "media_id": "videos/abc.mp4", "ajuste": "cover", "foco": [0.5, 0.5]}
        ]},
    ],
}


def _mint_gen() -> str:
    """Crea un registro de generacion de tipo render-video y devuelve su id."""
    reg = generaciones.crear({"tipo": "render-video", "marca": _MARCA, "etiqueta": "Render"})
    return reg["id"]


def _crear_composicion(doc: dict) -> str:
    comp = repos.crear_video_composicion(marca=_MARCA, documento=json.dumps(doc))
    return comp["id"]


# --------------------------------------------------------------------------- #
# Errores de entrada                                                           #
# --------------------------------------------------------------------------- #


def test_render_sin_composicion_id(entorno):
    gen = _mint_gen()
    estudio_video.ejecutar_render(gen, {})
    g = generaciones.obtener(gen)
    assert g["estado"] == generaciones.ESTADO_ERROR
    assert "composicion_id" in g["error"]


def test_render_composicion_inexistente(entorno):
    gen = _mint_gen()
    estudio_video.ejecutar_render(gen, {"composicion_id": "no-existe"})
    assert generaciones.obtener(gen)["estado"] == generaciones.ESTADO_ERROR


def test_render_sin_clip_base(entorno):
    doc = {"version": 1, "marca": _MARCA, "formato": {"w": 1080, "h": 1920}, "pistas": []}
    comp = _crear_composicion(doc)
    gen = _mint_gen()
    estudio_video.ejecutar_render(gen, {"composicion_id": comp})
    assert generaciones.obtener(gen)["estado"] == generaciones.ESTADO_ERROR


# --------------------------------------------------------------------------- #
# Happy-path                                                                   #
# --------------------------------------------------------------------------- #


def test_render_happy_path_completa_con_resultado(entorno, monkeypatch):
    # Clip base disponible en el almacen.
    monkeypatch.setattr(estudio_video.media, "leer_objeto", lambda mid: b"clip-bytes")

    capturado: dict = {}

    def _fake_ffmpeg(argv, *, timeout, gen_id, documento):
        # Materializa una salida no vacia donde ffmpeg la dejaria (ultimo arg = salida).
        capturado["argv"] = argv
        from pathlib import Path
        Path(argv[-1]).write_bytes(b"mp4-bytes-falsos")

    monkeypatch.setattr(estudio_video, "_correr_ffmpeg", _fake_ffmpeg)

    comp = _crear_composicion(_DOC)
    gen = _mint_gen()
    estudio_video.ejecutar_render(gen, {"composicion_id": comp})

    g = generaciones.obtener(gen)
    assert g["estado"] == generaciones.ESTADO_COMPLETADO, g.get("error")
    res = g["resultado"]
    assert res["media_id"].startswith("render/") and res["media_id"].endswith(".mp4")
    assert res["url"] == f"/api/media/{res['media_id']}"
    # El mp4 quedo guardado content-addressed en el almacen.
    assert almacen_media.objeto_existe(res["media_id"])
    # El comando se construyo con el binario de config y el clip base materializado.
    assert capturado["argv"][0] == config.ffmpeg_bin()


def test_render_overlay_hornea_png_y_lo_compone(entorno, monkeypatch):
    monkeypatch.setattr(estudio_video.media, "leer_objeto", lambda mid: b"clip-bytes")
    # El horneado del overlay (Estudio de imagen) devuelve un PNG falso.
    monkeypatch.setattr(
        estudio_video.estudio_imagen, "renderizar_documento_bytes", lambda doc, **k: b"png-falso"
    )

    capturado: dict = {}

    def _fake_ffmpeg(argv, *, timeout, gen_id, documento):
        capturado["argv"] = argv
        from pathlib import Path
        Path(argv[-1]).write_bytes(b"mp4")

    monkeypatch.setattr(estudio_video, "_correr_ffmpeg", _fake_ffmpeg)

    doc = json.loads(json.dumps(_DOC))
    doc["pistas"].append({"id": "overlay", "tipo": "overlay", "capas": [{"tipo": "texto"}]})
    comp = _crear_composicion(doc)
    gen = _mint_gen()
    estudio_video.ejecutar_render(gen, {"composicion_id": comp})

    assert generaciones.obtener(gen)["estado"] == generaciones.ESTADO_COMPLETADO
    fg = capturado["argv"][capturado["argv"].index("-filter_complex") + 1]
    assert "overlay=0:0" in fg  # el PNG horneado se compuso sobre el video


def test_render_subtitulos_sin_ass_no_falla(entorno, monkeypatch):
    """Pista de subtitulos sin ASS aun -> el render OMITE subtitulos y completa igual."""
    monkeypatch.setattr(estudio_video.media, "leer_objeto", lambda mid: b"clip-bytes")

    capturado: dict = {}

    def _fake_ffmpeg(argv, *, timeout, gen_id, documento):
        capturado["argv"] = argv
        from pathlib import Path
        Path(argv[-1]).write_bytes(b"mp4")

    monkeypatch.setattr(estudio_video, "_correr_ffmpeg", _fake_ffmpeg)

    doc = json.loads(json.dumps(_DOC))
    doc["pistas"].append({"id": "subs", "tipo": "subtitulos", "subtitulo_id": "no-existe"})
    comp = _crear_composicion(doc)
    gen = _mint_gen()
    estudio_video.ejecutar_render(gen, {"composicion_id": comp})

    assert generaciones.obtener(gen)["estado"] == generaciones.ESTADO_COMPLETADO
    assert "-filter_complex" in capturado["argv"]
    fg = capturado["argv"][capturado["argv"].index("-filter_complex") + 1]
    assert "ass=" not in fg  # sin ASS no se quema nada


def test_render_subtitulos_con_ass_quema(entorno, monkeypatch):
    monkeypatch.setattr(estudio_video.media, "leer_objeto", lambda mid: b"clip-bytes")

    capturado: dict = {}

    def _fake_ffmpeg(argv, *, timeout, gen_id, documento):
        capturado["argv"] = argv
        from pathlib import Path
        Path(argv[-1]).write_bytes(b"mp4")

    monkeypatch.setattr(estudio_video, "_correr_ffmpeg", _fake_ffmpeg)

    doc = json.loads(json.dumps(_DOC))
    comp = _crear_composicion(doc)
    # Subtitulo con ASS listo, ligado a la composicion.
    sub = repos.crear_video_subtitulo(composicion_id=comp, estado="transcrito", ass="[Script Info]\n")
    doc["pistas"].append({"id": "subs", "tipo": "subtitulos", "subtitulo_id": sub["id"]})
    # Re-guardar el documento con la pista de subtitulos.
    repos.actualizar_video_composicion(comp, {"documento": json.dumps(doc)})

    gen = _mint_gen()
    estudio_video.ejecutar_render(gen, {"composicion_id": comp})

    assert generaciones.obtener(gen)["estado"] == generaciones.ESTADO_COMPLETADO
    fg = capturado["argv"][capturado["argv"].index("-filter_complex") + 1]
    assert "ass=" in fg


# --------------------------------------------------------------------------- #
# Fallos de ffmpeg                                                             #
# --------------------------------------------------------------------------- #


def test_render_clip_no_en_almacen(entorno, monkeypatch):
    monkeypatch.setattr(estudio_video.media, "leer_objeto", lambda mid: None)
    comp = _crear_composicion(_DOC)
    gen = _mint_gen()
    estudio_video.ejecutar_render(gen, {"composicion_id": comp})
    g = generaciones.obtener(gen)
    assert g["estado"] == generaciones.ESTADO_ERROR
    assert "almacen" in g["error"]


def test_render_ffmpeg_falla_marca_error(entorno, monkeypatch):
    monkeypatch.setattr(estudio_video.media, "leer_objeto", lambda mid: b"clip-bytes")

    def _ffmpeg_revienta(argv, *, timeout, gen_id, documento):
        raise estudio_video.RenderError("ffmpeg fallo (codigo 1): algo")

    monkeypatch.setattr(estudio_video, "_correr_ffmpeg", _ffmpeg_revienta)
    comp = _crear_composicion(_DOC)
    gen = _mint_gen()
    estudio_video.ejecutar_render(gen, {"composicion_id": comp})
    g = generaciones.obtener(gen)
    assert g["estado"] == generaciones.ESTADO_ERROR
    assert "ffmpeg" in g["error"]
