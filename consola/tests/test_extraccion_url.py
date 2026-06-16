"""Reintentos con backoff del descargador de páginas (`extraccion_url._descargar_real`).

Resiliencia tipo motor de feeds de Fuentes: los fallos TRANSITORIOS (timeout/conexión) se
reintentan con backoff; un 4xx o "demasiado grande" es definitivo y NO se reintenta. Se mockea
`_un_intento_descarga` (sin red) y `time.sleep` (sin esperas reales).
"""

from __future__ import annotations

import pytest

from keni_consola.dominio import extraccion_url

httpx = pytest.importorskip("httpx")  # dependencia transitiva; si falta, no aplica el reintento


def _sin_esperas(monkeypatch) -> None:
    monkeypatch.setattr(extraccion_url.time, "sleep", lambda _s: None)


def test_reintenta_fallo_transitorio_y_recupera(monkeypatch):
    _sin_esperas(monkeypatch)
    llamadas = {"n": 0}

    def _intento(url, timeout):
        llamadas["n"] += 1
        if llamadas["n"] < 3:
            raise httpx.ConnectTimeout("lento")
        return "<html><body>ok</body></html>"

    monkeypatch.setattr(extraccion_url, "_un_intento_descarga", _intento)
    html = extraccion_url._descargar_real("https://x.test", reintentos=3)
    assert "ok" in html
    assert llamadas["n"] == 3  # falló dos veces, acertó a la tercera


def test_sin_reintentos_propaga_timeout(monkeypatch):
    _sin_esperas(monkeypatch)

    def _intento(url, timeout):
        raise httpx.ConnectTimeout("lento")

    monkeypatch.setattr(extraccion_url, "_un_intento_descarga", _intento)
    with pytest.raises(extraccion_url.ExtraccionError, match="tardó"):
        extraccion_url._descargar_real("https://x.test", reintentos=1)


def test_no_reintenta_errores_definitivos(monkeypatch):
    _sin_esperas(monkeypatch)
    llamadas = {"n": 0}

    def _intento(url, timeout):
        llamadas["n"] += 1
        raise extraccion_url.ExtraccionError("La página respondió con un error (HTTP 404).")

    monkeypatch.setattr(extraccion_url, "_un_intento_descarga", _intento)
    with pytest.raises(extraccion_url.ExtraccionError, match="404"):
        extraccion_url._descargar_real("https://x.test", reintentos=3)
    assert llamadas["n"] == 1  # un 4xx no se reintenta


# --- Mensaje del intento real según el status (fake de httpx, sin red) --- #


class _RespFalsa:
    """Respuesta de `httpx` falsa: solo lo que toca `_un_intento_descarga` (status + cuerpo)."""

    def __init__(self, status: int) -> None:
        self.status_code = status
        self.encoding = "utf-8"

    def __enter__(self):  # `with cliente.stream(...) as respuesta:`
        return self

    def __exit__(self, *_a):
        return False

    def iter_bytes(self):
        return iter([b"<html><body>ok</body></html>"])


class _ClienteFalso:
    def __init__(self, status: int) -> None:
        self._status = status

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def stream(self, _metodo, _url):
        return _RespFalsa(self._status)


def test_403_avisa_que_la_pagina_bloquea(monkeypatch):
    """401/403/429 = la web bloquea la lectura automática: mensaje accionable, no críptico."""
    monkeypatch.setattr(httpx, "Client", lambda **_k: _ClienteFalso(403))
    with pytest.raises(extraccion_url.ExtraccionError, match="bloquea la lectura automática"):
        extraccion_url._un_intento_descarga("https://x.test", None)
    # (un 4xx es definitivo y NO se reintenta: lo cubre `test_no_reintenta_errores_definitivos`).


def test_500_da_mensaje_generico(monkeypatch):
    """Otros status (5xx) conservan el mensaje genérico de error de página."""
    monkeypatch.setattr(httpx, "Client", lambda **_k: _ClienteFalso(500))
    with pytest.raises(extraccion_url.ExtraccionError, match="respondió con un error"):
        extraccion_url._un_intento_descarga("https://x.test", None)
