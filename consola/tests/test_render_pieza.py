"""Tests OFFLINE de `dominio.render_pieza`: resolución de la imagen on-demand desde la receta.

No tocan Node ni la BD: mockean `estudio_imagen.componer`/`componer_desde_plantilla`/
`marca_tiene_plantilla` y `repos.obtener_plantilla_diseno`. Verifican la PRECEDENCIA de la
receta (imagen bespoke > placa oculta > plantilla del estudio > placa de marca > foto) y la
URL servible que decide la serialización.
"""

from __future__ import annotations

from keni_consola import media, plantillas_marca, repos
from keni_consola.dominio import estudio_imagen, render_pieza


def _sin_plantilla_de_marca(monkeypatch, valor=False):
    monkeypatch.setattr(estudio_imagen, "marca_tiene_plantilla", lambda marca: valor)


# --------------------------------------------------------------------------- #
# tiene_receta                                                                 #
# --------------------------------------------------------------------------- #


def test_tiene_receta_placa_oculta_es_falso(monkeypatch):
    _sin_plantilla_de_marca(monkeypatch, True)
    assert render_pieza.tiene_receta({"placa_oculta": True, "marca": "unotv"}) is False


def test_tiene_receta_por_plantilla_del_estudio(monkeypatch):
    # No necesita mirar la marca: con plantilla del estudio ya hay receta.
    _sin_plantilla_de_marca(monkeypatch, False)
    assert render_pieza.tiene_receta({"plantilla_diseno_id": "pl-1", "marca": "x"}) is True


def test_tiene_receta_por_placa_de_marca(monkeypatch):
    _sin_plantilla_de_marca(monkeypatch, True)
    assert render_pieza.tiene_receta({"marca": "unotv"}) is True


def test_tiene_receta_marca_sin_plantilla(monkeypatch):
    _sin_plantilla_de_marca(monkeypatch, False)
    assert render_pieza.tiene_receta({"marca": "piso-15"}) is False


# --------------------------------------------------------------------------- #
# imagen_compuesta_id                                                          #
# --------------------------------------------------------------------------- #


def test_imagen_bespoke_se_respeta(monkeypatch):
    # Si hay `imagen` horneada (editor pro / legacy), se devuelve tal cual sin recomponer.
    def _boom(*a, **k):
        raise AssertionError("no debe componer si ya hay imagen")

    monkeypatch.setattr(estudio_imagen, "componer", _boom)
    assert render_pieza.imagen_compuesta_id({"imagen": "horneada.png"}) == "horneada.png"


def test_placa_oculta_devuelve_foto(monkeypatch):
    _sin_plantilla_de_marca(monkeypatch, True)
    pub = {"imagen": "", "placa_oculta": True, "foto": "foto.jpg", "marca": "unotv"}
    assert render_pieza.imagen_compuesta_id(pub) == "foto.jpg"


def test_sin_receta_devuelve_foto(monkeypatch):
    _sin_plantilla_de_marca(monkeypatch, False)
    pub = {"imagen": "", "foto": "foto.jpg", "marca": "piso-15"}
    assert render_pieza.imagen_compuesta_id(pub) == "foto.jpg"


def test_placa_de_marca_compone(monkeypatch):
    _sin_plantilla_de_marca(monkeypatch, True)
    capt = {}

    def _componer(imagen, *, marca, formato, titular, etiqueta=None, **k):
        capt.update(imagen=imagen, marca=marca, formato=formato, titular=titular)
        return {"id": "compuesta.png", "url": "/api/media/compuesta.png"}

    monkeypatch.setattr(estudio_imagen, "componer", _componer)
    pub = {"imagen": "", "foto": "foto.jpg", "marca": "unotv", "red": "instagram",
           "copy_in": "TITULAR"}
    assert render_pieza.imagen_compuesta_id(pub) == "compuesta.png"
    assert capt["imagen"] == "foto.jpg" and capt["marca"] == "unotv"
    assert capt["titular"] == "TITULAR" and capt["formato"] == "feed"


def test_plantilla_del_estudio_compone_desde_plantilla(monkeypatch):
    monkeypatch.setattr(repos, "obtener_plantilla_diseno", lambda pid: {"documento": "{}"})
    capt = {}

    def _desde(documento, *, copy_in, foto, foco=None, zoom=0.0):
        capt.update(copy_in=copy_in, foto=foto)
        return {"id": "doc.png", "url": "/api/media/doc.png"}

    monkeypatch.setattr(estudio_imagen, "componer_desde_plantilla", _desde)
    pub = {"imagen": "", "plantilla_diseno_id": "pl-1", "foto": "f.jpg",
           "copy_in": "X", "marca": "unotv", "foto_encuadre": ""}
    assert render_pieza.imagen_compuesta_id(pub) == "doc.png"
    assert capt == {"copy_in": "X", "foto": "f.jpg"}


def test_plantilla_borrada_cae_a_placa_de_marca(monkeypatch):
    # Si la plantilla elegida ya no existe, NO se deja la pieza sin imagen: cae a la placa.
    monkeypatch.setattr(repos, "obtener_plantilla_diseno", lambda pid: None)
    monkeypatch.setattr(
        estudio_imagen, "componer",
        lambda *a, **k: {"id": "placa.png", "url": "/api/media/placa.png"},
    )
    pub = {"imagen": "", "plantilla_diseno_id": "pl-borrada", "foto": "f.jpg",
           "marca": "unotv", "red": "x", "copy_in": "Y"}
    assert render_pieza.imagen_compuesta_id(pub) == "placa.png"


# --------------------------------------------------------------------------- #
# imagen_url_de (decisión barata, sin componer)                                #
# --------------------------------------------------------------------------- #


def test_url_imagen_horneada(monkeypatch):
    _sin_plantilla_de_marca(monkeypatch, True)
    assert render_pieza.imagen_url_de({"id": "p1", "imagen": "h.png"}) == "/api/media/h.png"


def test_url_receta_apunta_a_compuesta(monkeypatch):
    _sin_plantilla_de_marca(monkeypatch, True)
    pub = {"id": "p1", "imagen": "", "marca": "unotv"}
    assert render_pieza.imagen_url_de(pub) == "/api/publicaciones/p1/compuesta"


def test_url_solo_foto(monkeypatch):
    _sin_plantilla_de_marca(monkeypatch, False)
    pub = {"id": "p1", "imagen": "", "marca": "piso-15", "foto": "f.jpg"}
    assert render_pieza.imagen_url_de(pub) == "/api/media/f.jpg"


def test_url_fuente_externa(monkeypatch):
    _sin_plantilla_de_marca(monkeypatch, False)
    pub = {"id": "p1", "imagen": "", "marca": "piso-15", "foto": "",
           "imagen_fuente": "https://x/foto.jpg"}
    assert render_pieza.imagen_url_de(pub) == "https://x/foto.jpg"


# --------------------------------------------------------------------------- #
# render_bytes (efímero, sin persistir) — el camino de /compuesta              #
# --------------------------------------------------------------------------- #


def test_render_bytes_placa_compone_sin_persistir(monkeypatch):
    _sin_plantilla_de_marca(monkeypatch, True)

    def _no_persiste(*a, **k):
        raise AssertionError("render_bytes NO debe persistir")

    monkeypatch.setattr(estudio_imagen, "componer_bytes", lambda *a, **k: b"PNG")
    monkeypatch.setattr(media, "guardar_bytes_contenido", _no_persiste)
    pub = {"id": "p1", "imagen": "", "marca": "unotv", "red": "x", "copy_in": "T", "foto": "f.jpg"}
    assert render_pieza.render_bytes(pub) == (b"PNG", "image/png")


def test_render_bytes_plantilla(monkeypatch):
    monkeypatch.setattr(repos, "obtener_plantilla_diseno", lambda pid: {"documento": "{}"})
    monkeypatch.setattr(estudio_imagen, "componer_desde_plantilla_bytes", lambda *a, **k: b"DOC")
    pub = {"id": "p1", "imagen": "", "plantilla_diseno_id": "pl-1", "foto": "f.jpg",
           "copy_in": "X", "marca": "unotv", "foto_encuadre": ""}
    assert render_pieza.render_bytes(pub) == (b"DOC", "image/png")


def test_render_bytes_imagen_bespoke_passthrough(monkeypatch):
    # `imagen` ya horneada: se sirven sus bytes tal cual, sin recomponer ni persistir.
    monkeypatch.setattr(media, "leer_media", lambda n: b"BYTES" if n == "h.png" else None)
    monkeypatch.setattr(media, "mime_de", lambda n: "image/png")
    assert render_pieza.render_bytes({"id": "p1", "imagen": "h.png"}) == (b"BYTES", "image/png")


def test_render_bytes_solo_foto(monkeypatch):
    _sin_plantilla_de_marca(monkeypatch, False)
    monkeypatch.setattr(media, "leer_media", lambda n: b"FOTO" if n == "f.jpg" else None)
    monkeypatch.setattr(media, "mime_de", lambda n: "image/jpeg")
    pub = {"id": "p1", "imagen": "", "marca": "piso-15", "foto": "f.jpg"}
    assert render_pieza.render_bytes(pub) == (b"FOTO", "image/jpeg")


def test_render_bytes_none_sin_imagen(monkeypatch):
    _sin_plantilla_de_marca(monkeypatch, False)
    pub = {"id": "p1", "imagen": "", "marca": "piso-15", "foto": ""}
    assert render_pieza.render_bytes(pub) is None


# --------------------------------------------------------------------------- #
# firma_receta (ETag): cambia sii cambia la salida                             #
# --------------------------------------------------------------------------- #


def test_firma_estable_y_sensible(monkeypatch):
    # Spec fijo (sin IO): la firma depende de los campos de la receta.
    monkeypatch.setattr(plantillas_marca, "obtener_spec", lambda marca: {"v": 1})
    base = {"id": "p1", "imagen": "", "marca": "unotv", "red": "x", "foto": "f.jpg",
            "copy_in": "A", "foto_encuadre": "", "placa_oculta": False, "plantilla_diseno_id": ""}
    f1 = render_pieza.firma_receta(dict(base))
    f2 = render_pieza.firma_receta(dict(base))
    f3 = render_pieza.firma_receta({**base, "copy_in": "B"})
    assert f1 == f2 and f1 != f3


def test_firma_cambia_si_cambia_el_spec(monkeypatch):
    # Editar el spec de la marca (mismo copy_in) invalida la caché HTTP.
    base = {"id": "p1", "imagen": "", "marca": "unotv", "red": "x", "foto": "f.jpg",
            "copy_in": "A", "foto_encuadre": "", "placa_oculta": False, "plantilla_diseno_id": ""}
    monkeypatch.setattr(plantillas_marca, "obtener_spec", lambda marca: {"v": 1})
    f1 = render_pieza.firma_receta(dict(base))
    monkeypatch.setattr(plantillas_marca, "obtener_spec", lambda marca: {"v": 2})
    f2 = render_pieza.firma_receta(dict(base))
    assert f1 != f2
