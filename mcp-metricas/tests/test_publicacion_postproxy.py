"""Tests del adaptador de PUBLICACION via Postproxy (`publicacion.postproxy`).

SIN red real. Cubren la propiedad de SEGURIDAD central (dry-run = CERO red y la api_key
NUNCA en el body) y el mapeo `Borrador` -> `POST /api/posts`. El camino real va mockeado
con respx para verificar la cabecera `Authorization: Bearer`, el cuerpo enviado, el
soporte de MÚLTIPLES profiles y el parseo del id del post en la respuesta.

`programar(...)` devuelve un `ResultadoProgramacion` (el MISMO tipo que el adaptador de
Metricool): en dry-run trae la `peticion` exacta; en real trae `id_post` + `estados`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
import respx

from keni_metricas.publicacion import (
    AdaptadorPublicacionPostproxy,
    Borrador,
    MediaRef,
    ProgramacionNoConfigurada,
    ResultadoProgramacion,
    TipoMedia,
)
from keni_metricas.publicacion.postproxy import BASE, ENDPOINT_PUBLICAR

URL = f"{BASE}{ENDPOINT_PUBLICAR}"
API_KEY = "PP_SECRET_KEY"


def _img(url: str = "https://e/x.jpg", desc: str | None = None) -> MediaRef:
    return MediaRef(tipo=TipoMedia.imagen, url=url, descripcion=desc)


def _borrador(**kw) -> Borrador:
    base = {"plataforma": "facebook", "cuenta": "perfil-123", "texto": "hola"}
    base.update(kw)
    return Borrador(**base)


# --- dry-run: CERO red, body exacto, SIN secreto -----------------------------
def test_dry_run_no_toca_red_y_arma_body():
    b = _borrador(texto="cuerpo", hashtags=["#Deporte", "futbol"])
    a = AdaptadorPublicacionPostproxy(api_key=API_KEY)
    res = a.programar(b)  # dry_run=True por defecto
    assert isinstance(res, ResultadoProgramacion)
    assert res.dry_run is True
    p = res.peticion
    assert p.metodo == "POST"
    assert p.url == URL
    assert p.body["post"]["body"] == "cuerpo\n\n#Deporte #futbol"
    assert p.body["post"]["draft"] is False
    assert "scheduled_at" not in p.body["post"]  # sin publicar_en => se omite
    assert p.body["profiles"] == ["perfil-123"]
    assert "media" not in p.body
    assert res.redes == ["perfil-123"]
    assert res.estados == {}  # dry-run no resuelve estados


def test_dry_run_no_filtra_la_api_key():
    """La api_key NUNCA aparece en el resultado del dry-run (viaja solo en la cabecera)."""
    a = AdaptadorPublicacionPostproxy(api_key=API_KEY)
    res = a.programar(_borrador())
    assert API_KEY not in str(res.como_dict())


def test_dry_run_incluye_media():
    b = _borrador(media=[_img("https://e/a.jpg"), _img("https://e/b.jpg")])
    a = AdaptadorPublicacionPostproxy(api_key=API_KEY)
    res = a.programar(b)
    assert res.peticion.body["media"] == ["https://e/a.jpg", "https://e/b.jpg"]


def test_dry_run_funciona_sin_api_key():
    """El dry-run no necesita credenciales (no toca la red)."""
    a = AdaptadorPublicacionPostproxy()
    res = a.programar(_borrador())
    assert res.peticion.body["profiles"] == ["perfil-123"]


def test_dry_run_multiples_profiles():
    """`profiles=` admite varios destinos y los vuelca en el body."""
    a = AdaptadorPublicacionPostproxy(api_key=API_KEY)
    res = a.programar(_borrador(), profiles=["instagram", "facebook", "p-99"])
    assert res.peticion.body["profiles"] == ["instagram", "facebook", "p-99"]
    assert res.redes == ["instagram", "facebook", "p-99"]


def test_profiles_vacio_cae_a_cuenta():
    """`profiles=[]` (o solo blancos) cae al `cuenta` del borrador."""
    a = AdaptadorPublicacionPostproxy(api_key=API_KEY)
    res = a.programar(_borrador(), profiles=["  ", ""])
    assert res.peticion.body["profiles"] == ["perfil-123"]


# --- camino real: requiere api_key, envía Bearer + body ----------------------
def test_real_sin_api_key_lanza_no_configurada():
    a = AdaptadorPublicacionPostproxy()  # sin api_key
    with pytest.raises(ProgramacionNoConfigurada):
        a.programar(_borrador(), dry_run=False)


@respx.mock
def test_real_envia_bearer_y_cuerpo_y_parsea_id():
    ruta = respx.post(URL).mock(
        return_value=httpx.Response(200, json={"id": "post-1"})
    )
    a = AdaptadorPublicacionPostproxy(api_key=API_KEY)
    res = a.programar(_borrador(texto="real"), profiles=["instagram", "facebook"], dry_run=False)
    assert ruta.called
    req = ruta.calls[0].request
    assert req.headers["Authorization"] == f"Bearer {API_KEY}"
    import json as _json

    enviado = _json.loads(req.content)
    assert enviado["post"]["body"] == "real"
    assert enviado["profiles"] == ["instagram", "facebook"]
    # Resultado: id parseado + estados por defecto "programado" por perfil.
    assert res.dry_run is False
    assert res.id_post == "post-1"
    assert res.redes == ["instagram", "facebook"]
    assert res.estados == {"instagram": "programado", "facebook": "programado"}
    assert res.peticion.url == URL


@respx.mock
def test_real_parsea_id_anidado_en_data():
    respx.post(URL).mock(return_value=httpx.Response(200, json={"data": {"post_id": "abc"}}))
    a = AdaptadorPublicacionPostproxy(api_key=API_KEY)
    res = a.programar(_borrador(), dry_run=False)
    assert res.id_post == "abc"


@respx.mock
def test_real_parsea_estados_por_perfil_si_vienen():
    respx.post(URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "p1",
                "profiles": [
                    {"platform": "instagram", "status": "scheduled"},
                    {"platform": "facebook", "status": "error"},
                ],
            },
        )
    )
    a = AdaptadorPublicacionPostproxy(api_key=API_KEY)
    res = a.programar(_borrador(), profiles=["instagram", "facebook"], dry_run=False)
    assert res.id_post == "p1"
    assert res.estados == {"instagram": "scheduled", "facebook": "error"}


@respx.mock
def test_real_sin_id_en_respuesta_queda_none():
    respx.post(URL).mock(return_value=httpx.Response(200, json={"ok": True}))
    a = AdaptadorPublicacionPostproxy(api_key=API_KEY)
    res = a.programar(_borrador(), dry_run=False)
    assert res.id_post is None
    assert res.estados == {"perfil-123": "programado"}
