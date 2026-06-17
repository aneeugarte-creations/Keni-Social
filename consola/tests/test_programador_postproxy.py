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

import respx
from httpx import Response

from keni_consola import repos
from keni_consola.programador import programar_pieza_metricool

_POSTPROXY_URL = "https://api.postproxy.dev/api/posts"
_RESP_PP_OK = {"id": "pp-post-001"}


def _pub_programada(
    red: str = "x", contenido: str = "Texto", imagen: str = "", minutos_atras: int = 5
) -> dict[str, Any]:
    pub = repos.crear_pieza(
        "unotv", red, titulo="Test", contenido=contenido, estado="programado", imagen=imagen,
    )
    pasado = (datetime.now() - timedelta(minutes=minutos_atras)).strftime("%Y-%m-%dT%H:%M")
    return repos.actualizar_pieza(pub["id"], {"fecha_programada": pasado})


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
    assert repos.obtener_pieza(pub["id"])["estado"] == "programado"


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
    actualizada = repos.obtener_pieza(pub["id"])
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
