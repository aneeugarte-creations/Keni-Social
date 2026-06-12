"""Tests del cajón CLIPS (`/api/clips`): vídeo/foto de WhatsApp -> pieza automática.

El equipo vuelca el clip (texto + media ya subido) y el sistema genera AUTOMÁTICAMENTE el
tema + su pieza en el feed:
  - un VÍDEO -> `formato='video'` (el vídeo en las 5 redes),
  - FOTOS    -> `formato='carrusel'` (portada=1ª imagen + slides), igual que Presidencia.
El copy se encola en segundo plano (lanzador mockeado por la fixture `cliente`: nunca corre
`claude`).
"""

from __future__ import annotations

import json

from keni_consola import redes, repos

_TEXTO = "Golazo de la Selección Mexicana.\n\nMinuto 90, victoria agónica…"


def _crear(cliente, media, **extra):
    cuerpo = {"marca": "claro-sports", "texto": _TEXTO, "media": media, **extra}
    return cliente.post("/api/clips", json=cuerpo)


def test_clip_de_video_genera_pieza_video(cliente):
    resp = _crear(cliente, [{"tipo": "video", "objeto": "videos/gol.mp4"}])
    assert resp.status_code == 200, resp.text
    datos = resp.json()
    cid = datos["contenido_id"]
    assert datos["clip"]["estado_pieza"] == "generando"
    assert datos["clip"]["formato"] == "video"
    assert datos["generacion"]["id"]

    item = repos.obtener_contenido(cid)
    assert item["origen"] == "clips"
    assert item["formato"] == "video"
    assert item["flujo"] == "importante"
    assert item["descripcion"] == _TEXTO

    plataformas = repos.listar_contenido_plataforma(cid)
    assert {p["red"] for p in plataformas} == set(redes.redes_de_formato(redes.FORMATO_VIDEO))
    for p in plataformas:
        assert p["video"] == "videos/gol.mp4"
        assert p["falta_video"] is False
        assert p["falta_copy"] is True  # el copy llega después (generación en background)


def test_clip_de_fotos_genera_pieza_carrusel(cliente):
    media = [
        {"tipo": "imagen", "objeto": "fotos/1.jpg"},
        {"tipo": "imagen", "objeto": "fotos/2.jpg"},
    ]
    resp = _crear(cliente, media)
    assert resp.status_code == 200, resp.text
    cid = resp.json()["contenido_id"]
    assert resp.json()["clip"]["formato"] == "carrusel"

    item = repos.obtener_contenido(cid)
    assert item["formato"] == "carrusel"

    plataformas = repos.listar_contenido_plataforma(cid)
    assert {p["red"] for p in plataformas} == set(redes.redes_de_formato(redes.FORMATO_CARRUSEL))
    for p in plataformas:
        assert p["foto"] == "fotos/1.jpg"  # portada = primera imagen
        assert p["falta_imagen"] is False
        assert p["falta_copy"] is True
        assert json.loads(p["carrusel"]) == [{"tipo": "imagen", "objeto": "fotos/2.jpg"}]


def test_titulo_se_deriva_de_la_primera_linea(cliente):
    resp = _crear(cliente, [{"tipo": "video", "objeto": "v.mp4"}])
    cid = resp.json()["contenido_id"]
    assert repos.obtener_contenido(cid)["titulo"] == "Golazo de la Selección Mexicana."


def test_titulo_explicito_manda(cliente):
    resp = _crear(cliente, [{"tipo": "video", "objeto": "v.mp4"}], titulo="Gol del minuto 90")
    cid = resp.json()["contenido_id"]
    assert repos.obtener_contenido(cid)["titulo"] == "Gol del minuto 90"


def test_validaciones_de_entrada(cliente):
    foto = [{"tipo": "imagen", "objeto": "f.jpg"}]
    # Marca obligatoria y del catálogo.
    assert _crear(cliente, foto, marca="nope").status_code == 400
    # Texto obligatorio (es el material del copy).
    assert _crear(cliente, foto, texto="  ").status_code == 400
    # Media obligatorio.
    assert _crear(cliente, []).status_code == 400
    # Un clip de vídeo es UN solo vídeo: mezclar vídeo + fotos se rechaza.
    mezcla = [{"tipo": "video", "objeto": "v.mp4"}, {"tipo": "imagen", "objeto": "f.jpg"}]
    assert _crear(cliente, mezcla).status_code == 400
    # Dos vídeos también se rechazan (una pieza = un vídeo).
    dos_videos = [{"tipo": "video", "objeto": "a.mp4"}, {"tipo": "video", "objeto": "b.mp4"}]
    assert _crear(cliente, dos_videos).status_code == 400
    # Tipo desconocido y objeto vacío.
    assert _crear(cliente, [{"tipo": "gif", "objeto": "x"}]).status_code == 400
    assert _crear(cliente, [{"tipo": "imagen", "objeto": ""}]).status_code == 400
    # Tope de slides.
    muchos = [{"tipo": "imagen", "objeto": f"f{i}.jpg"} for i in range(11)]
    assert _crear(cliente, muchos).status_code == 400


def test_listar_clips(cliente):
    _crear(cliente, [{"tipo": "video", "objeto": "v.mp4"}])
    _crear(cliente, [{"tipo": "imagen", "objeto": "f.jpg"}], titulo="Foto del evento")
    resp = cliente.get("/api/clips")
    assert resp.status_code == 200
    datos = resp.json()
    assert len(datos["clips"]) == 2
    assert datos["clips"][0]["estado_pieza"] in {"generando", "lista", "sin_pieza"}
    assert datos["clips"][0]["marca"] == "claro-sports"
    # El filtro por marca acota.
    assert cliente.get("/api/clips?marca=unotv").json()["clips"] == []
