"""Entrada por ENLACE y TEXTO al import de parrilla (además del fichero de siempre).

La extracción de URL y el encolado del job `claude -p` se MOCKEAN (sin red ni IA): se verifica
el CABLEADO — propuesta creada con marca/doc_tipo y job encolado con el texto, o mensaje claro
si la URL no es legible (vídeo/streaming).
"""

from __future__ import annotations

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth, repos
from keni_consola.dominio import extraccion_url
from keni_consola.dominio import parrilla_import_job as job

from .conftest import TOKEN_PRUEBA

_ORIGIN = {"Origin": "http://testserver"}
_CLAVE = "clave-de-prueba"


def _cli(usuario: str = "ana") -> TestClient:
    auth.crear_usuario(usuario, _CLAVE, "editor")
    c = TestClient(app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False))
    r = c.post(
        "/api/auth/login", json={"usuario": usuario, "password": _CLAVE}, headers=_ORIGIN
    )
    assert r.status_code == 200
    return c


def test_importar_desde_enlace_crea_propuesta_con_marca_y_encola(entorno, monkeypatch):
    monkeypatch.setattr(extraccion_url, "validar_url", lambda u: (u, None))
    monkeypatch.setattr(
        extraccion_url,
        "_DESCARGADOR",
        lambda url: (
            "<html><head><title>Cruz Azul vs América</title></head>"
            "<body><p>Domingo 20:00, jornada 17. Sacar gol y reacciones.</p></body></html>"
        ),
    )
    capturado: dict = {}
    monkeypatch.setattr(
        job, "lanzar_desde_texto", lambda **kw: capturado.update(kw) or {"id": "gen-1"}
    )

    c = _cli()
    r = c.post(
        "/api/parrilla/importar",
        data={"url": "https://liga.test/partido", "marca": "claro-sports"},
        headers=_ORIGIN,
    )
    # Responde al INSTANTE (la descarga del enlace se hace en 2º plano, como Cajones del día). El
    # TestClient corre el BackgroundTask tras la respuesta, así que el encolado ya ocurrió aquí.
    assert r.status_code == 202, r.text
    prop = repos.obtener_propuesta_parrilla(r.json()["propuesta_id"])
    assert prop["marca"] == "claro-sports"
    assert prop["doc_tipo"] == "enlace"
    assert prop["gen_id"] == "gen-1"  # el gen_id lo estampa el job en 2º plano, no la respuesta
    assert "Cruz Azul" in capturado.get("texto", "")


def test_importar_enlace_de_video_da_422_con_mensaje(entorno, monkeypatch):
    # El host de vídeo se rechaza SÍNCRONO (chequeo barato del host), sin crear propuesta.
    monkeypatch.setattr(extraccion_url, "validar_url", lambda u: (u, None))
    c = _cli()
    r = c.post(
        "/api/parrilla/importar",
        data={"url": "https://youtube.com/watch?v=x"},
        headers=_ORIGIN,
    )
    assert r.status_code == 422
    assert "v" in r.json()["error"].lower()  # "vídeo" en el mensaje


def test_importar_enlace_lento_deja_la_propuesta_en_error(entorno, monkeypatch):
    # La descarga falla EN 2º PLANO (página lenta/ilegible): ya no es un timeout de la petición,
    # sino una propuesta en `error` con mensaje claro que el frontend muestra al sondear.
    monkeypatch.setattr(extraccion_url, "validar_url", lambda u: (u, None))

    def _revienta(url: str, **_kw):
        raise extraccion_url.ExtraccionError("La página tardó demasiado y se canceló.")

    monkeypatch.setattr(extraccion_url, "extraer_texto", _revienta)
    c = _cli()
    r = c.post(
        "/api/parrilla/importar",
        data={"url": "https://lenta.test/cartelera"},
        headers=_ORIGIN,
    )
    assert r.status_code == 202, r.text
    prop = repos.obtener_propuesta_parrilla(r.json()["propuesta_id"])
    assert prop["estado"] == "error"
    assert "tardó" in prop["error"]


def test_importar_desde_texto_pegado_encola(entorno, monkeypatch):
    capturado: dict = {}
    monkeypatch.setattr(
        job, "lanzar_desde_texto", lambda **kw: capturado.update(kw) or {"id": "gen-2"}
    )
    c = _cli()
    r = c.post(
        "/api/parrilla/importar",
        data={"texto": "Cruz Azul vs América, dom 20:00", "marca": "claro-sports"},
        headers=_ORIGIN,
    )
    assert r.status_code == 202, r.text
    prop = repos.obtener_propuesta_parrilla(r.json()["propuesta_id"])
    assert prop["doc_tipo"] == "texto"
    assert prop["marca"] == "claro-sports"
    assert "Cruz Azul" in capturado.get("texto", "")


def test_importar_sin_nada_da_400(entorno):
    c = _cli()
    r = c.post("/api/parrilla/importar", data={}, headers=_ORIGIN)
    assert r.status_code == 400
