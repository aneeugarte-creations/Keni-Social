"""Tests del cajón PRESIDENCIA (`/api/presidencia/notas`): nota WhatsApp -> pieza carrusel.

El equipo vuelca la nota (texto + media ya subido) y el sistema genera AUTOMÁTICAMENTE el
tema + la pieza `formato='carrusel'` en el feed: portada = primera imagen (foto cruda para
la placa), resto del media EN CRUDO como slides (campo `carrusel`), copy encolado en
segundo plano (lanzador mockeado por la fixture `cliente`: nunca corre `claude`).
"""

from __future__ import annotations

import json

from keni_consola import redes, repos

_MEDIA = [
    {"tipo": "imagen", "objeto": "fotos/p1.jpg"},
    {"tipo": "imagen", "objeto": "fotos/p2.jpg"},
    {"tipo": "video", "objeto": "videos/clip.mp4"},
    {"tipo": "imagen", "objeto": "fotos/p3.jpg"},
]

_NOTA = "Inauguración del nuevo hospital.\n\nLa presidenta encabezó el evento…"


def _crear(cliente, **extra):
    cuerpo = {"marca": "unotv", "texto": _NOTA, "media": _MEDIA, **extra}
    return cliente.post("/api/presidencia/notas", json=cuerpo)


def test_crear_nota_genera_pieza_carrusel(cliente):
    resp = _crear(cliente)
    assert resp.status_code == 200, resp.text
    datos = resp.json()
    cid = datos["contenido_id"]
    assert datos["nota"]["estado_pieza"] == "generando"
    assert datos["generacion"]["id"]

    item = repos.obtener_contenido(cid)
    assert item["origen"] == "presidencia"
    assert item["formato"] == "carrusel"
    assert item["flujo"] == "importante"
    assert item["descripcion"] == _NOTA  # la nota íntegra queda trazada en el tema

    plataformas = repos.listar_contenido_plataforma(cid)
    assert {p["red"] for p in plataformas} == set(
        redes.redes_de_formato(redes.FORMATO_CARRUSEL)
    )
    for p in plataformas:
        # Portada = PRIMERA imagen (foto cruda para componer la placa); pieza sin hueco de imagen.
        assert p["foto"] == "fotos/p1.jpg"
        assert p["falta_imagen"] is False
        assert p["falta_copy"] is True  # el copy llega después (generación en background)
        # El resto del media, EN CRUDO y EN ORDEN, como slides extra.
        assert json.loads(p["carrusel"]) == [
            {"tipo": "imagen", "objeto": "fotos/p2.jpg"},
            {"tipo": "video", "objeto": "videos/clip.mp4"},
            {"tipo": "imagen", "objeto": "fotos/p3.jpg"},
        ]


def test_titulo_se_deriva_de_la_primera_linea(cliente):
    resp = _crear(cliente)
    cid = resp.json()["contenido_id"]
    assert repos.obtener_contenido(cid)["titulo"] == "Inauguración del nuevo hospital."


def test_titulo_explicito_manda(cliente):
    resp = _crear(cliente, titulo="Nota de presidencia")
    cid = resp.json()["contenido_id"]
    assert repos.obtener_contenido(cid)["titulo"] == "Nota de presidencia"


def test_portada_es_la_primera_imagen_aunque_abra_un_video(cliente):
    media = [{"tipo": "video", "objeto": "videos/abre.mp4"}, *_MEDIA]
    resp = _crear(cliente, media=media)
    assert resp.status_code == 200, resp.text
    plataformas = repos.listar_contenido_plataforma(resp.json()["contenido_id"])
    p = plataformas[0]
    assert p["foto"] == "fotos/p1.jpg"  # primera IMAGEN, no el video que abre
    # El video que abría la nota sigue en los slides, en su posición original.
    assert json.loads(p["carrusel"])[0] == {"tipo": "video", "objeto": "videos/abre.mp4"}


def test_validaciones_de_entrada(cliente):
    # Marca obligatoria y del catálogo.
    assert _crear(cliente, marca="nope").status_code == 400
    # Texto obligatorio (es el material del copy).
    assert _crear(cliente, texto="  ").status_code == 400
    # Media obligatorio, con al menos una imagen (la portada se compone sobre una foto).
    assert _crear(cliente, media=[]).status_code == 400
    sin_imagen = [{"tipo": "video", "objeto": "videos/x.mp4"}]
    assert _crear(cliente, media=sin_imagen).status_code == 400
    # Tipo desconocido y objeto vacío se rechazan con mensaje claro.
    assert _crear(cliente, media=[{"tipo": "gif", "objeto": "x"}]).status_code == 400
    assert _crear(cliente, media=[{"tipo": "imagen", "objeto": ""}]).status_code == 400
    # Tope de slides.
    muchos = [{"tipo": "imagen", "objeto": f"f{i}.jpg"} for i in range(11)]
    assert _crear(cliente, media=muchos).status_code == 400


def test_listar_notas(cliente):
    _crear(cliente)
    _crear(cliente, titulo="Segunda nota")
    resp = cliente.get("/api/presidencia/notas")
    assert resp.status_code == 200
    datos = resp.json()
    assert len(datos["notas"]) == 2
    # Recientes primero; cada nota trae el estado resumido de su pieza.
    assert datos["notas"][0]["estado_pieza"] in {"generando", "lista", "sin_pieza"}
    assert datos["notas"][0]["marca"] == "unotv"
    # El filtro por marca acota.
    resp = cliente.get("/api/presidencia/notas?marca=claro-sports")
    assert resp.json()["notas"] == []
