"""Tests del paquete de publicacion en Meta.

Cubren la propiedad de SEGURIDAD central: dry-run = CERO red. Y, con respx
mockeado, que el camino real arma la secuencia correcta (IG container->publish,
FB feed/photo/video).
"""

from __future__ import annotations

import httpx
import pytest
import respx
from pydantic import ValidationError

from keni_metricas.publicacion import (
    AdaptadorPublicacionMeta,
    Borrador,
    MediaRef,
    TipoMedia,
)
from keni_metricas.publicacion.meta import BASE, PublicacionNoConfigurada
from keni_metricas.schema import Plataforma


# --- modelos ---------------------------------------------------------------
def test_borrador_rechaza_plataforma_no_meta():
    with pytest.raises(ValidationError):
        Borrador(plataforma=Plataforma.tiktok, cuenta="x")


def test_borrador_rechaza_cuenta_vacia():
    with pytest.raises(ValidationError):
        Borrador(plataforma=Plataforma.facebook, cuenta="   ")


def test_hashtags_se_normalizan():
    b = Borrador(
        plataforma=Plataforma.instagram,
        cuenta="IG",
        texto="hola",
        media=[MediaRef(tipo=TipoMedia.imagen, url="https://e/x.jpg")],
        hashtags=["#Deporte", "Deporte", "  futbol ", ""],
    )
    assert b.hashtags == ["Deporte", "futbol"]  # quita '#', espacios, dups exactos y vacios
    assert b.texto_final() == "hola\n\n#Deporte #futbol"


def test_media_ref_rechaza_url_vacia():
    with pytest.raises(ValidationError):
        MediaRef(tipo=TipoMedia.imagen, url="  ")


# --- DRY-RUN: cero red -----------------------------------------------------
@respx.mock
def test_dry_run_facebook_no_llama_red_y_arma_feed():
    ad = AdaptadorPublicacionMeta(creds={})  # sin token
    b = Borrador(plataforma=Plataforma.facebook, cuenta="PAGE", texto="Hola FB")
    res = ad.publicar(b)  # dry_run por defecto

    assert res.dry_run is True
    assert len(res.peticiones) == 1
    pet = res.peticiones[0]
    assert pet.paso == "fb_feed"
    assert pet.url == f"{BASE}/PAGE/feed"
    assert pet.data == {"message": "Hola FB"}
    # CERO peticiones reales
    assert respx.calls.call_count == 0
    # el token no aparece en el payload de dry-run
    assert "access_token" not in pet.data


@respx.mock
def test_dry_run_instagram_arma_dos_pasos_sin_red():
    ad = AdaptadorPublicacionMeta(creds={"access_token": "tok"})  # aun con token: dry-run no publica
    b = Borrador(
        plataforma=Plataforma.instagram,
        cuenta="IGID",
        texto="Hola IG",
        media=[MediaRef(tipo=TipoMedia.imagen, url="https://e/x.jpg")],
        hashtags=["a"],
    )
    res = ad.publicar(b, dry_run=True)

    assert res.dry_run is True
    pasos = [p.paso for p in res.peticiones]
    assert pasos == ["ig_container", "ig_publish"]
    cont = res.peticiones[0]
    assert cont.url == f"{BASE}/IGID/media"
    assert cont.data == {"image_url": "https://e/x.jpg", "caption": "Hola IG\n\n#a"}
    pub = res.peticiones[1]
    assert pub.url == f"{BASE}/IGID/media_publish"
    assert pub.data == {"creation_id": "{creation_id}"}
    assert respx.calls.call_count == 0  # CERO red


def test_dry_run_es_el_defecto():
    """publicar(b) sin pasar dry_run debe ser dry-run (defensa de la firma)."""
    ad = AdaptadorPublicacionMeta(creds={"access_token": "tok"})
    b = Borrador(plataforma=Plataforma.facebook, cuenta="PAGE", texto="x")
    assert ad.publicar(b).dry_run is True


def test_ig_dry_run_video_marca_reels():
    ad = AdaptadorPublicacionMeta(creds={})
    b = Borrador(
        plataforma=Plataforma.instagram,
        cuenta="IGID",
        media=[MediaRef(tipo=TipoMedia.video, url="https://e/v.mp4")],
    )
    cont = ad.publicar(b).peticiones[0]
    assert cont.data == {"video_url": "https://e/v.mp4", "caption": "", "media_type": "REELS"}


def test_instagram_sin_media_falla():
    ad = AdaptadorPublicacionMeta(creds={})
    b = Borrador(plataforma=Plataforma.instagram, cuenta="IGID", texto="hola")
    with pytest.raises(ValueError, match="exige media"):
        ad.publicar(b)


# --- camino REAL (mockeado) ------------------------------------------------
@respx.mock
def test_real_facebook_feed_hace_un_post():
    ruta = respx.post(f"{BASE}/PAGE/feed").mock(
        return_value=httpx.Response(200, json={"id": "PAGE_123"})
    )
    ad = AdaptadorPublicacionMeta(creds={"access_token": "tok"})
    b = Borrador(plataforma=Plataforma.facebook, cuenta="PAGE", texto="Hola")
    res = ad.publicar(b, dry_run=False)

    assert ruta.called
    assert res.dry_run is False
    assert res.id_publicacion == "PAGE_123"
    # el token SI viaja en la peticion real (form-encoded)
    enviado = dict(httpx.QueryParams(ruta.calls.last.request.content.decode()))
    assert enviado["access_token"] == "tok"
    assert enviado["message"] == "Hola"


@respx.mock
def test_real_facebook_foto_usa_endpoint_photos():
    ruta = respx.post(f"{BASE}/PAGE/photos").mock(
        return_value=httpx.Response(200, json={"id": "img1", "post_id": "PAGE_9"})
    )
    ad = AdaptadorPublicacionMeta(creds={"access_token": "tok"})
    b = Borrador(
        plataforma=Plataforma.facebook,
        cuenta="PAGE",
        texto="con foto",
        media=[MediaRef(tipo=TipoMedia.imagen, url="https://e/x.jpg")],
    )
    res = ad.publicar(b, dry_run=False)
    assert ruta.called
    assert res.id_publicacion == "img1"


@respx.mock
def test_real_instagram_secuencia_container_luego_publish():
    ruta_cont = respx.post(f"{BASE}/IGID/media").mock(
        return_value=httpx.Response(200, json={"id": "CREATION_1"})
    )
    ruta_pub = respx.post(f"{BASE}/IGID/media_publish").mock(
        return_value=httpx.Response(200, json={"id": "IG_POST_1"})
    )
    ad = AdaptadorPublicacionMeta(creds={"access_token": "systok", "tipo_token": "system_user"})
    b = Borrador(
        plataforma=Plataforma.instagram,
        cuenta="IGID",
        texto="reel",
        media=[MediaRef(tipo=TipoMedia.video, url="https://e/v.mp4")],
    )
    res = ad.publicar(b, dry_run=False)

    assert ruta_cont.called and ruta_pub.called
    # el publish usa el creation_id REAL devuelto por el contenedor
    pub_body = dict(httpx.QueryParams(ruta_pub.calls.last.request.content.decode()))
    assert pub_body["creation_id"] == "CREATION_1"
    assert res.id_publicacion == "IG_POST_1"
    assert len(res.respuestas) == 2


@respx.mock
def test_real_sin_token_no_toca_red():
    ruta = respx.post(f"{BASE}/PAGE/feed").mock(return_value=httpx.Response(200, json={"id": "x"}))
    ad = AdaptadorPublicacionMeta(creds={})  # sin token
    b = Borrador(plataforma=Plataforma.facebook, cuenta="PAGE", texto="x")
    with pytest.raises(PublicacionNoConfigurada):
        ad.publicar(b, dry_run=False)
    assert not ruta.called  # falla ANTES de cualquier red


# --- CLI dry-run (__main__): robustez sin tracebacks ------------------------
def test_b2_cli_instagram_sin_media_error_limpio(capsys):
    """B2: IG sin media reventaba con ValueError crudo + traceback en la CLI.

    Ahora `publicar()` esta dentro del try/except: mensaje espanol, codigo != 0
    limpio (sin traceback).
    """
    from keni_metricas.publicacion.__main__ import main

    code = main(["--plataforma", "instagram", "--cuenta", "IG_ID", "--texto", "Hola"])
    assert code == 2
    err = capsys.readouterr().err
    assert "Instagram exige media" in err
    assert "Traceback" not in err


def test_b6_cli_error_pydantic_sin_url_ni_ingles(capsys):
    """B6: errores de pydantic mostraban texto en ingles + errors.pydantic.dev.

    Cuenta vacia (' ') dispara ValidationError; debe verse el mensaje limpio.
    """
    from keni_metricas.publicacion.__main__ import main

    code = main(["--plataforma", "facebook", "--cuenta", "   ", "--texto", "Hola"])
    assert code == 2
    err = capsys.readouterr().err
    assert "obligatorio" in err  # mensaje en espanol del validador
    assert "errors.pydantic.dev" not in err  # sin la URL ni el dump en ingles
    assert "validation error for" not in err


def test_cli_facebook_dry_run_ok(capsys):
    """Camino feliz de la CLI: FB con texto produce el payload dry-run, codigo 0."""
    from keni_metricas.publicacion.__main__ import main

    code = main(["--plataforma", "facebook", "--cuenta", "PAGE", "--texto", "Hola"])
    assert code == 0
    out = capsys.readouterr().out
    assert "DRY-RUN" in out
    assert "PAGE/feed" in out


@respx.mock
def test_real_ig_sin_creation_id_falla_y_no_publica():
    ruta_cont = respx.post(f"{BASE}/IGID/media").mock(
        return_value=httpx.Response(200, json={})  # sin 'id'
    )
    ruta_pub = respx.post(f"{BASE}/IGID/media_publish").mock(
        return_value=httpx.Response(200, json={"id": "no_deberia"})
    )
    ad = AdaptadorPublicacionMeta(creds={"access_token": "tok"})
    b = Borrador(
        plataforma=Plataforma.instagram,
        cuenta="IGID",
        media=[MediaRef(tipo=TipoMedia.imagen, url="https://e/x.jpg")],
    )
    with pytest.raises(RuntimeError, match="creation_id"):
        ad.publicar(b, dry_run=False)
    assert ruta_cont.called
    assert not ruta_pub.called  # nunca se publica si el contenedor falla
