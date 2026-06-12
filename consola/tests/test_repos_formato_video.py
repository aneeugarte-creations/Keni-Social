"""Tests de VIDEO en el tablero: columnas video/falta_video, flip de formato y checklist.

Usa la fixture `entorno` (Postgres de pruebas o SKIP si no hay). Cubre el contrato F-video:
  - `crear_contenido_plataforma` persiste video/falta_video.
  - `ajustar_plataformas_por_formato`: foto->video añade youtube+tiktok; video->foto elimina
    las extra VACÍAS y CONSERVA (reportando) las que tienen trabajo.
  - el checklist por formato (falta_video en video, falta_imagen en foto).
"""

from __future__ import annotations

from keni_consola import db, repos


def _crear_pieza_foto():
    """Crea una pieza formato=foto con sus 3 redes (instagram, x, facebook)."""
    item = db.crear_contenido(titulo="Pieza", formato="foto")
    for red in ("instagram", "x", "facebook"):
        db.crear_contenido_plataforma(contenido_id=item["id"], red=red)
    return item


def test_columnas_video_se_persisten(entorno):
    item = db.crear_contenido(titulo="Con video", formato="video")
    plat = db.crear_contenido_plataforma(
        contenido_id=item["id"], red="tiktok", video="videos/abc.mp4", falta_video=False
    )
    assert plat["video"] == "videos/abc.mp4"
    assert plat["falta_video"] is False
    assert plat["video_url"] == "/api/media/videos/abc.mp4"
    leido = db.obtener_contenido_plataforma(plat["id"])
    assert leido["video"] == "videos/abc.mp4"


def test_falta_video_default_es_falso(entorno):
    """Sin pasar falta_video (None), una fila nace con falta_video=False (N/A en foto)."""
    item = db.crear_contenido(titulo="X", formato="foto")
    plat = db.crear_contenido_plataforma(contenido_id=item["id"], red="instagram")
    assert plat["falta_video"] is False
    assert plat["video"] == ""
    assert plat["video_url"] == ""


def test_flip_foto_a_video_anade_youtube_y_tiktok(entorno):
    item = _crear_pieza_foto()
    res = repos.ajustar_plataformas_por_formato(item["id"], "video")
    assert set(res["creadas"]) == {"youtube", "tiktok"}
    assert res["eliminadas"] == []
    assert res["conservadas"] == []
    redes = {p["red"] for p in db.listar_contenido_plataforma(item["id"])}
    assert redes == {"instagram", "x", "facebook", "youtube", "tiktok"}
    # En video, todas las filas sin asset marcan falta_video=1 y falta_imagen=0.
    for p in db.listar_contenido_plataforma(item["id"]):
        assert p["falta_video"] is True
        assert p["falta_imagen"] is False


def test_flip_video_a_foto_elimina_extras_vacias(entorno):
    item = db.crear_contenido(titulo="V", formato="video")
    for red in ("instagram", "x", "facebook", "youtube", "tiktok"):
        db.crear_contenido_plataforma(contenido_id=item["id"], red=red, falta_video=True)
    res = repos.ajustar_plataformas_por_formato(item["id"], "foto")
    assert set(res["eliminadas"]) == {"youtube", "tiktok"}
    assert res["conservadas"] == []
    redes = {p["red"] for p in db.listar_contenido_plataforma(item["id"])}
    assert redes == {"instagram", "x", "facebook"}
    # En foto, falta_video pasa a False (N/A) en las filas restantes.
    for p in db.listar_contenido_plataforma(item["id"]):
        assert p["falta_video"] is False


def test_flip_video_a_foto_conserva_extras_con_trabajo(entorno):
    """Una red extra con copy o video NO se borra; se conserva y se reporta."""
    item = db.crear_contenido(titulo="V", formato="video")
    for red in ("instagram", "x", "facebook"):
        db.crear_contenido_plataforma(contenido_id=item["id"], red=red)
    db.crear_contenido_plataforma(contenido_id=item["id"], red="youtube", copy="Guion listo")
    db.crear_contenido_plataforma(
        contenido_id=item["id"], red="tiktok", video="videos/x.mp4"
    )
    res = repos.ajustar_plataformas_por_formato(item["id"], "foto")
    assert res["eliminadas"] == []
    assert set(res["conservadas"]) == {"youtube", "tiktok"}
    redes = {p["red"] for p in db.listar_contenido_plataforma(item["id"])}
    assert redes == {"instagram", "x", "facebook", "youtube", "tiktok"}


def test_flip_es_idempotente(entorno):
    """Repetir el ajuste al mismo formato no crea ni borra nada."""
    item = _crear_pieza_foto()
    repos.ajustar_plataformas_por_formato(item["id"], "video")
    res = repos.ajustar_plataformas_por_formato(item["id"], "video")
    assert res["creadas"] == []
    assert res["eliminadas"] == []


def test_flip_foto_a_video_borra_foto_plantilla_y_vuelve_a_borrador(entorno):
    """foto->video: borra la foto/placa y la plantilla, y devuelve la pieza a borrador. El copy se queda."""
    item = db.crear_contenido(titulo="P", formato="foto")
    plat = db.crear_contenido_plataforma(
        contenido_id=item["id"], red="instagram",
        foto="fotos/a.jpg", fotos='[{"objeto":"fotos/a.jpg"}]', foto_encuadre="0.5,0.5,1",
        imagen="render/x.png", plantilla_diseno_id="pl-1", estado="en_revision",
        falta_revision=False, falta_publicar=False, copy="texto del post", falta_copy=False,
    )
    repos.ajustar_plataformas_por_formato(item["id"], "video")
    p = db.obtener_contenido_plataforma(plat["id"])
    assert p["foto"] == "" and p["fotos"] == "" and p["foto_encuadre"] == "" and p["imagen"] == ""
    assert p["plantilla_diseno_id"] == ""
    assert p["estado"] == "pendiente" and p["falta_revision"] is True
    assert p["falta_video"] is True and p["falta_imagen"] is False
    assert p["copy"] == "texto del post"  # el COPY no se toca


def test_flip_video_a_foto_borra_video_plantilla_y_vuelve_a_borrador(entorno):
    """video->foto: borra el vídeo y la plantilla, vuelve a borrador; la foto (si la hay) se conserva."""
    item = db.crear_contenido(titulo="V", formato="video")
    plat = db.crear_contenido_plataforma(
        contenido_id=item["id"], red="instagram",
        video="videos/x.mp4", falta_video=False, foto="fotos/keep.jpg",
        plantilla_diseno_id="pm-1", estado="en_revision",
        falta_revision=False, falta_publicar=False, copy="guion", falta_copy=False,
    )
    repos.ajustar_plataformas_por_formato(item["id"], "foto")
    p = db.obtener_contenido_plataforma(plat["id"])
    assert p["video"] == ""
    assert p["plantilla_diseno_id"] == ""
    assert p["estado"] == "pendiente" and p["falta_revision"] is True
    assert p["foto"] == "fotos/keep.jpg"  # la foto se conserva
    assert p["copy"] == "guion" and p["falta_video"] is False


def test_flip_no_revierte_ni_borra_lo_publicado(entorno):
    """Una fila ya `publicado` no pierde su asset/plantilla ni se revierte de estado."""
    item = db.crear_contenido(titulo="Pub", formato="foto")
    plat = db.crear_contenido_plataforma(
        contenido_id=item["id"], red="instagram",
        foto="fotos/pub.jpg", plantilla_diseno_id="pl-1", estado="publicado",
    )
    repos.ajustar_plataformas_por_formato(item["id"], "video")
    p = db.obtener_contenido_plataforma(plat["id"])
    assert p["estado"] == "publicado"
    assert p["foto"] == "fotos/pub.jpg" and p["plantilla_diseno_id"] == "pl-1"


# --------------------------------------------------------------------------- #
# Formato CARRUSEL: columna `carrusel` (slides extra) y sus flips              #
# --------------------------------------------------------------------------- #

_SLIDES = '[{"tipo":"imagen","objeto":"fotos/b.jpg"},{"tipo":"video","objeto":"videos/c.mp4"}]'


def test_columna_carrusel_se_persiste(entorno):
    """`crear_contenido_plataforma` persiste los slides extra del carrusel (JSON)."""
    item = db.crear_contenido(titulo="Carrusel", formato="carrusel")
    plat = db.crear_contenido_plataforma(
        contenido_id=item["id"], red="instagram", foto="fotos/a.jpg", carrusel=_SLIDES
    )
    assert plat["carrusel"] == _SLIDES
    leido = db.obtener_contenido_plataforma(plat["id"])
    assert leido["carrusel"] == _SLIDES
    # Y es editable por la lista blanca (el editor reordena/añade slides).
    db.actualizar_contenido_plataforma(plat["id"], {"carrusel": ""})
    assert db.obtener_contenido_plataforma(plat["id"])["carrusel"] == ""


def test_flip_foto_a_carrusel_conserva_x_y_portada(entorno):
    """foto->carrusel: MISMAS redes que foto (X/IG/FB), no se quita ninguna, y CONSERVA la
    portada (foto/placa). Foto y carrusel comparten destino de imagen; X ya no se elimina."""
    item = db.crear_contenido(titulo="P", formato="foto")
    plat_ig = db.crear_contenido_plataforma(
        contenido_id=item["id"], red="instagram", foto="fotos/portada.jpg"
    )
    db.crear_contenido_plataforma(contenido_id=item["id"], red="x")
    db.crear_contenido_plataforma(contenido_id=item["id"], red="facebook")
    res = repos.ajustar_plataformas_por_formato(item["id"], "carrusel")
    assert res["creadas"] == []
    assert res["eliminadas"] == []  # X es destino del carrusel: ya no se quita
    redes_ = {p["red"] for p in db.listar_contenido_plataforma(item["id"])}
    assert redes_ == {"instagram", "x", "facebook"}
    p = db.obtener_contenido_plataforma(plat_ig["id"])
    # La portada (foto cruda) sobrevive al flip foto->carrusel: misma parte visual.
    assert p["foto"] == "fotos/portada.jpg"
    assert p["falta_video"] is False and p["falta_imagen"] is False


def test_flip_carrusel_a_foto_limpia_slides_y_anade_x(entorno):
    """carrusel->foto: añade x y limpia los slides extra; la portada se conserva."""
    item = db.crear_contenido(titulo="C", formato="carrusel")
    plat = db.crear_contenido_plataforma(
        contenido_id=item["id"], red="instagram", foto="fotos/portada.jpg", carrusel=_SLIDES
    )
    db.crear_contenido_plataforma(contenido_id=item["id"], red="facebook", carrusel=_SLIDES)
    res = repos.ajustar_plataformas_por_formato(item["id"], "foto")
    assert res["creadas"] == ["x"]
    p = db.obtener_contenido_plataforma(plat["id"])
    assert p["carrusel"] == ""  # los slides son EXCLUSIVOS del carrusel
    assert p["foto"] == "fotos/portada.jpg"  # la portada se conserva


def test_flip_carrusel_a_video_borra_portada_y_slides(entorno):
    """carrusel->video: borra la parte visual entera (portada + slides) y exige video."""
    item = db.crear_contenido(titulo="C", formato="carrusel")
    plat = db.crear_contenido_plataforma(
        contenido_id=item["id"], red="instagram", foto="fotos/portada.jpg", carrusel=_SLIDES
    )
    repos.ajustar_plataformas_por_formato(item["id"], "video")
    p = db.obtener_contenido_plataforma(plat["id"])
    assert p["foto"] == "" and p["carrusel"] == ""
    assert p["falta_video"] is True and p["falta_imagen"] is False
