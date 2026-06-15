"""Tests del DESPACHO por canal en el programador: canal=postproxy vs metricool.

Verifica que el selector de canal por marca (`config.canal_publicacion_para`) enruta al
adaptador correcto SIN cambiar el comportamiento de Metricool (que se cubre en
`test_programador_metricool.py`). Aquí:

  - canal=postproxy + gate ON: el barrido entrega al adaptador Postproxy (POST a la API
    de Postproxy, mockeada con respx), la pieza pasa a `publicado` y el id de Postproxy
    se guarda en `id_post_metricool` (columna reusada como id externo).
  - canal=postproxy sin credenciales: degradación honesta (sigue en `programado`).
  - canal=metricool (default): NO toca Postproxy (regresión: enruta a Metricool).
  - botón manual con canal=postproxy: dry-run previsualiza el body Postproxy; real publica.

Todo OFFLINE: respx mockea la red; `_creds_postproxy`/`canal_publicacion_para`/
`_profiles_postproxy` se parchean para no leer config real ni resolver perfiles por red.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from unittest.mock import patch

import httpx
import respx
from httpx import Response

from keni_consola import repos
from keni_consola.programador import preparar_vencidas, programar_pieza_metricool

_POSTPROXY_URL = "https://api.postproxy.dev/api/posts"
_METRICOOL_URL = "https://app.metricool.com/api/v2/scheduler/posts"
_RESP_PP_OK = {"id": "pp-post-001"}


def _pub_programada(
    red: str = "x", contenido: str = "Texto", imagen: str = "", minutos_atras: int = 5
) -> dict[str, Any]:
    pub = repos.crear_publicacion(
        "unotv", red, titulo="Test", contenido=contenido, estado="programado", imagen=imagen,
    )
    pasado = (datetime.now() - timedelta(minutes=minutos_atras)).strftime("%Y-%m-%dT%H:%M")
    return repos.actualizar_publicacion(pub["id"], {"fecha_programada": pasado})


def _canal(valor: str):
    """Parchea el selector de canal del programador para devolver `valor`."""
    return patch("keni_consola.config.canal_publicacion_para", return_value=valor)


def _creds_pp(api_key="PP_KEY", group_id="grp-1"):
    return patch(
        "keni_consola.programador._creds_postproxy", return_value=(api_key, group_id)
    )


def _profiles(lista):
    return patch("keni_consola.programador._profiles_postproxy", return_value=lista)


# --------------------------------------------------------------------------- #
# Barrido automático                                                          #
# --------------------------------------------------------------------------- #
def test_barrido_postproxy_publica_y_guarda_id(entorno, monkeypatch):
    """canal=postproxy + gate ON: entrega a Postproxy y marca publicado con su id."""
    monkeypatch.setenv("KENI_PUBLICAR_REAL", "1")
    monkeypatch.delenv("KENI_CONSOLA_URL_PUBLICA", raising=False)
    pub = _pub_programada(red="x", contenido="Tweet PP")

    cuerpo_enviado: dict | None = None

    def capturar(request, route):  # noqa: ANN001
        import json
        nonlocal cuerpo_enviado
        cuerpo_enviado = json.loads(request.content)
        return Response(200, json=_RESP_PP_OK)

    with _canal("postproxy"), _creds_pp(), _profiles(["twitter"]), respx.mock(
        assert_all_called=False
    ) as mock:
        ruta = mock.post(_POSTPROXY_URL).mock(side_effect=capturar)
        # Aseguramos que NO se toca Metricool.
        mc = mock.post(_METRICOOL_URL).mock(Response(200, json={"data": {"id": "x"}}))
        preparadas = preparar_vencidas(datetime.now())

    assert preparadas == 1
    assert ruta.called
    assert not mc.called  # NO fue a Metricool
    assert cuerpo_enviado is not None
    assert cuerpo_enviado["post"]["body"] == "Tweet PP"
    assert cuerpo_enviado["profiles"] == ["twitter"]
    actualizada = repos.obtener_publicacion(pub["id"])
    assert actualizada["estado"] == "publicado"
    assert actualizada["id_post_metricool"] == "pp-post-001"


def test_barrido_postproxy_sin_creds_degrada(entorno, monkeypatch):
    """canal=postproxy pero sin api_key/grupo: dry-run honesto, sigue en 'programado'."""
    monkeypatch.setenv("KENI_PUBLICAR_REAL", "1")
    pub = _pub_programada(red="x", contenido="Tweet")

    with _canal("postproxy"), patch(
        "keni_consola.programador._creds_postproxy", return_value=(None, None)
    ), respx.mock(assert_all_called=False) as mock:
        ruta = mock.post(_POSTPROXY_URL).mock(Response(200, json=_RESP_PP_OK))
        preparadas = preparar_vencidas(datetime.now())

    assert preparadas == 1
    assert not ruta.called
    actualizada = repos.obtener_publicacion(pub["id"])
    assert actualizada["estado"] == "programado"
    assert actualizada["preparado_en"]
    assert actualizada.get("id_post_metricool", "") == ""


def test_barrido_metricool_por_defecto_no_toca_postproxy(entorno, monkeypatch):
    """canal=metricool (default): enruta a Metricool, NO toca Postproxy (regresión)."""
    monkeypatch.setenv("KENI_PUBLICAR_REAL", "1")
    pub = _pub_programada(red="x", contenido="Tweet MC")

    with patch(
        "keni_consola.programador._creds_metricool",
        return_value={"user_token": "t", "user_id": "1", "blog_id": "2"},
    ), respx.mock(assert_all_called=False) as mock:
        mc = mock.post(_METRICOOL_URL).mock(Response(200, json={"data": {"id": "mc-1"}}))
        pp = mock.post(_POSTPROXY_URL).mock(Response(200, json=_RESP_PP_OK))
        # Sin postproxy configurado, canal_publicacion_para devuelve "metricool" (default real).
        preparar_vencidas(datetime.now())

    assert mc.called
    assert not pp.called
    assert repos.obtener_publicacion(pub["id"])["id_post_metricool"] == "mc-1"


def test_barrido_postproxy_timeout_marca_incierto(entorno, monkeypatch):
    """TIMEOUT en Postproxy: marca 'publicado' (incierto) y no reintenta (no doble-post)."""
    monkeypatch.setenv("KENI_PUBLICAR_REAL", "1")
    pub = _pub_programada(red="x", contenido="Tweet timeout")

    from keni_consola.programador import ID_POST_INCIERTO

    with _canal("postproxy"), _creds_pp(), _profiles(["twitter"]), respx.mock() as mock:
        ruta = mock.post(_POSTPROXY_URL).mock(side_effect=httpx.ReadTimeout("timed out"))
        assert preparar_vencidas(datetime.now()) == 1
        assert preparar_vencidas(datetime.now()) == 0  # no reintenta
        assert ruta.call_count == 1

    actualizada = repos.obtener_publicacion(pub["id"])
    assert actualizada["estado"] == "publicado"
    assert actualizada["id_post_metricool"] == ID_POST_INCIERTO


def test_barrido_postproxy_error_libera_claim(entorno, monkeypatch):
    """Un 5xx de Postproxy libera `preparado_en` para reintentar (igual que Metricool)."""
    monkeypatch.setenv("KENI_PUBLICAR_REAL", "1")
    pub = _pub_programada(red="x", contenido="Tweet 500")

    with _canal("postproxy"), _creds_pp(), _profiles(["twitter"]), respx.mock() as mock:
        mock.post(_POSTPROXY_URL).mock(Response(500, json={"error": "boom"}))
        assert preparar_vencidas(datetime.now()) == 0

    actualizada = repos.obtener_publicacion(pub["id"])
    assert actualizada["estado"] == "programado"
    assert actualizada["preparado_en"] == ""  # claim liberado


# --------------------------------------------------------------------------- #
# Botón manual                                                                #
# --------------------------------------------------------------------------- #
def test_boton_manual_postproxy_dry_run_previsualiza(entorno, monkeypatch):
    """Gate OFF + canal=postproxy: previsualiza el body Postproxy SIN tocar la red."""
    monkeypatch.delenv("KENI_PUBLICAR_REAL", raising=False)
    pub = _pub_programada(red="facebook", contenido="Hola PP")

    with _canal("postproxy"), _creds_pp(), respx.mock(assert_all_called=False) as mock:
        ruta = mock.post(_POSTPROXY_URL).mock(Response(200, json=_RESP_PP_OK))
        res = programar_pieza_metricool(pub)

    assert res["ok"] is True
    assert res["dry_run"] is True
    # Body Postproxy: profiles = nombre de plataforma (facebook), sin resolver id por red.
    assert res["cuerpo"]["profiles"] == ["facebook"]
    assert res["cuerpo"]["post"]["body"] == "Hola PP"
    assert not ruta.called
    # No persiste.
    assert repos.obtener_publicacion(pub["id"])["estado"] == "programado"


def test_boton_manual_postproxy_real_publica(entorno, monkeypatch):
    """Gate ON + canal=postproxy: publica de verdad y guarda el id de Postproxy."""
    monkeypatch.setenv("KENI_PUBLICAR_REAL", "1")
    pub = _pub_programada(red="x", contenido="Publicar ya PP")

    with _canal("postproxy"), _creds_pp(), _profiles(["twitter"]), respx.mock() as mock:
        mock.post(_POSTPROXY_URL).mock(Response(200, json=_RESP_PP_OK))
        res = programar_pieza_metricool(pub)

    assert res["ok"] is True
    assert res["dry_run"] is False
    assert res["id_post"] == "pp-post-001"
    actualizada = repos.obtener_publicacion(pub["id"])
    assert actualizada["estado"] == "publicado"
    assert actualizada["id_post_metricool"] == "pp-post-001"


def test_boton_manual_postproxy_sin_creds(entorno, monkeypatch):
    """canal=postproxy sin credenciales: ok=False con motivo (no lanza)."""
    monkeypatch.delenv("KENI_PUBLICAR_REAL", raising=False)
    pub = _pub_programada(red="facebook", contenido="Hola")

    with _canal("postproxy"), patch(
        "keni_consola.programador._creds_postproxy", return_value=(None, None)
    ):
        res = programar_pieza_metricool(pub)
    assert res["ok"] is False
    assert res["motivo"]


# --------------------------------------------------------------------------- #
# Resolución de perfiles (best-effort con fallback)                          #
# --------------------------------------------------------------------------- #
def test_profiles_postproxy_resuelve_id(entorno):
    """`_profiles_postproxy` resuelve el profile_id real de la plataforma de la pieza."""
    from keni_consola import programador

    perfiles = [
        {"id": "p-ig", "platform": "instagram"},
        {"id": "p-tw", "platform": "twitter"},
    ]
    with patch(
        "keni_metricas.fuentes.postproxy.listar_perfiles",
        return_value=(True, "ok", perfiles),
    ):
        # Pieza en X -> plataforma postproxy "twitter" -> resuelve p-tw.
        assert programador._profiles_postproxy({"red": "x"}, "K", "g") == ["p-tw"]


def test_profiles_postproxy_fallback_a_plataforma(entorno):
    """Si no hay match (o falla la consulta), cae al NOMBRE de plataforma."""
    from keni_consola import programador

    with patch(
        "keni_metricas.fuentes.postproxy.listar_perfiles",
        return_value=(False, "error", []),
    ):
        assert programador._profiles_postproxy({"red": "instagram"}, "K", "g") == ["instagram"]
