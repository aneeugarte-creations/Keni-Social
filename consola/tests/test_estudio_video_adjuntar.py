"""Tests del CABLEADO del render a la pieza.

Si la composicion tiene `contenido_id`, se adjunta el video a las plataformas de VIDEO de la
pieza (`video=<clave>`, `falta_video=0`) para que fluya por feed/aprobacion/publicacion.

ffmpeg/render van MONKEYPATCHEADOS. Repos en Postgres de pruebas (fixture `entorno`): SKIP en
local sin BD, corre en CI.
"""

from __future__ import annotations

import json

from keni_consola import generaciones, redes, repos
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
    reg = generaciones.crear({"tipo": "render-video", "marca": _MARCA, "etiqueta": "Render"})
    return reg["id"]


def _fake_ffmpeg(argv, *, timeout, gen_id, documento):
    from pathlib import Path

    Path(argv[-1]).write_bytes(b"mp4-bytes")


def _pieza_video() -> str:
    """Crea una pieza de FORMATO video con sus 5 plataformas (todas con falta_video=1)."""
    pieza = repos.crear_contenido(marca=_MARCA, titulo="Pieza video", formato=redes.FORMATO_VIDEO)
    for red in redes.redes_de_formato(redes.FORMATO_VIDEO):
        repos.crear_contenido_plataforma(
            contenido_id=pieza["id"], red=red, marca=_MARCA, falta_video=True
        )
    return pieza["id"]


# --------------------------------------------------------------------------- #
# Helper aislado: repos.adjuntar_video_a_pieza                                 #
# --------------------------------------------------------------------------- #


def test_adjuntar_helper_cablea_redes_de_video(entorno):
    pieza_id = _pieza_video()
    # Pre: todas las plataformas de video sin asset.
    plats = repos.listar_contenido_plataforma(pieza_id)
    assert all(p.get("falta_video") for p in plats)
    assert all(not (p.get("video") or "") for p in plats)

    tocadas = repos.adjuntar_video_a_pieza(pieza_id, "render/deadbeef.mp4")

    assert set(tocadas) == set(redes.redes_de_formato(redes.FORMATO_VIDEO))
    for p in repos.listar_contenido_plataforma(pieza_id):
        assert p["video"] == "render/deadbeef.mp4"
        assert not p["falta_video"]


def test_adjuntar_helper_es_idempotente(entorno):
    pieza_id = _pieza_video()
    repos.adjuntar_video_a_pieza(pieza_id, "render/aa.mp4")
    tocadas = repos.adjuntar_video_a_pieza(pieza_id, "render/aa.mp4")
    assert set(tocadas) == set(redes.redes_de_formato(redes.FORMATO_VIDEO))
    for p in repos.listar_contenido_plataforma(pieza_id):
        assert p["video"] == "render/aa.mp4"
        assert not p["falta_video"]


def test_adjuntar_helper_solo_toca_redes_de_video(entorno):
    """Una pieza de FOTO (instagram/x/facebook) no tiene redes de video propias salvo el solapo.

    `redes_de_formato(video)` incluye las 3 de foto + tiktok/youtube; el helper adjunta el asset a
    las que EXISTAN. Aqui verificamos que NO crea filas nuevas: solo toca las existentes.
    """
    pieza = repos.crear_contenido(marca=_MARCA, titulo="Pieza foto", formato=redes.FORMATO_FOTO)
    for red in redes.redes_de_formato(redes.FORMATO_FOTO):
        repos.crear_contenido_plataforma(
            contenido_id=pieza["id"], red=red, marca=_MARCA, falta_video=False
        )
    n_antes = len(repos.listar_contenido_plataforma(pieza["id"]))

    tocadas = repos.adjuntar_video_a_pieza(pieza["id"], "render/cc.mp4")

    # No se crean filas; solo se cablean las redes de foto que tambien son de video.
    assert len(repos.listar_contenido_plataforma(pieza["id"])) == n_antes
    assert set(tocadas) == set(redes.redes_de_formato(redes.FORMATO_FOTO))


def test_adjuntar_helper_pieza_sin_plataformas(entorno):
    pieza = repos.crear_contenido(marca=_MARCA, titulo="Sin plats")
    assert repos.adjuntar_video_a_pieza(pieza["id"], "render/x.mp4") == []


# --------------------------------------------------------------------------- #
# Integracion: ejecutar_render adjunta a la pieza ligada                       #
# --------------------------------------------------------------------------- #


def test_render_adjunta_a_pieza_con_contenido_id(entorno, monkeypatch):
    monkeypatch.setattr(estudio_video.media, "leer_objeto", lambda mid: b"clip-bytes")
    monkeypatch.setattr(estudio_video, "_correr_ffmpeg", _fake_ffmpeg)

    pieza_id = _pieza_video()
    comp = repos.crear_video_composicion(
        marca=_MARCA, documento=json.dumps(_DOC), contenido_id=pieza_id
    )
    gen = _mint_gen()
    estudio_video.ejecutar_render(gen, {"composicion_id": comp["id"]})

    g = generaciones.obtener(gen)
    assert g["estado"] == generaciones.ESTADO_COMPLETADO, g.get("error")
    clave = g["resultado"]["media_id"]
    # Todas las plataformas de video de la pieza quedaron cableadas.
    for p in repos.listar_contenido_plataforma(pieza_id):
        assert p["video"] == clave
        assert not p["falta_video"]


def test_render_sin_contenido_id_no_toca_piezas(entorno, monkeypatch):
    monkeypatch.setattr(estudio_video.media, "leer_objeto", lambda mid: b"clip-bytes")
    monkeypatch.setattr(estudio_video, "_correr_ffmpeg", _fake_ffmpeg)

    # Pieza existente que NO esta ligada a la composicion: debe quedar intacta.
    pieza_id = _pieza_video()
    comp = repos.crear_video_composicion(marca=_MARCA, documento=json.dumps(_DOC))
    assert not (repos.obtener_video_composicion(comp["id"]).get("contenido_id") or "")

    gen = _mint_gen()
    estudio_video.ejecutar_render(gen, {"composicion_id": comp["id"]})

    assert generaciones.obtener(gen)["estado"] == generaciones.ESTADO_COMPLETADO
    for p in repos.listar_contenido_plataforma(pieza_id):
        assert p["falta_video"]
        assert not (p.get("video") or "")


def test_render_adjuntado_falla_no_degrada_a_error(entorno, monkeypatch):
    """Si el cableado revienta, el render sigue COMPLETADO (el mp4 ya existe)."""
    monkeypatch.setattr(estudio_video.media, "leer_objeto", lambda mid: b"clip-bytes")
    monkeypatch.setattr(estudio_video, "_correr_ffmpeg", _fake_ffmpeg)

    def _revienta(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(repos, "adjuntar_video_a_pieza", _revienta)

    comp = repos.crear_video_composicion(
        marca=_MARCA, documento=json.dumps(_DOC), contenido_id="alguna-pieza"
    )
    gen = _mint_gen()
    estudio_video.ejecutar_render(gen, {"composicion_id": comp["id"]})

    g = generaciones.obtener(gen)
    assert g["estado"] == generaciones.ESTADO_COMPLETADO
    assert g["resultado"]["media_id"].startswith("render/")


def test_crear_video_composicion_acepta_contenido_id(entorno):
    """Assert ligero que SI requiere BD pero documenta el contrato del campo de liga."""
    comp = repos.crear_video_composicion(
        marca=_MARCA, documento="{}", contenido_id="pieza-123"
    )
    leido = repos.obtener_video_composicion(comp["id"])
    assert leido["contenido_id"] == "pieza-123"
