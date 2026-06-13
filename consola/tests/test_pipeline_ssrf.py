"""Guard SSRF del fetch de ARTÍCULOS de terceros en la ingesta del pipeline (`_comun`). OFFLINE.

La ingesta resuelve URLs de artículos que VIENEN DEL FEED (no confiables): la og:image y el
cuerpo del artículo. `_fetch_html_validado` debe rechazar esquemas no http/https e IPs
privadas/loopback/link-local/metadata ANTES de pedirlas, y revalidar CADA salto de redirección
(un editor legítimo redirige; un atacante podría redirigir a una IP interna). Todo con IPs
literales / httpx mockeado: NUNCA toca la red.
"""

from __future__ import annotations

import pytest
from keni_consola.pipeline_contenido import _comun

# --------------------------------------------------------------------------- #
# Rechazo PRE-fetch (sin red: IPs literales y esquemas)                        #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/x",                       # loopback
        "http://169.254.169.254/latest/meta-data/",  # metadata link-local (cloud)
        "http://10.0.0.5/feed",                      # privada
        "http://192.168.1.1/",                       # privada
        "http://[::1]/",                             # loopback IPv6
        "ftp://ejemplo.test/x",                      # esquema no http/https
        "file:///etc/passwd",                        # esquema no http/https
        "",                                          # vacía
    ],
)
def test_fetch_validado_rechaza_destinos_no_permitidos(url):
    # Ninguna de estas debe llegar a pedirse: el guard corta y devuelve "" sin tocar la red.
    assert _comun._fetch_html_validado(url, timeout=1.0, max_bytes=1024) == ""


def test_fetch_og_y_articulo_aplican_el_guard(monkeypatch):
    # Si el seam llegara a invocar httpx con una IP interna sería un fallo: lo hacemos explotar.
    import httpx

    def _boom(*a, **k):  # pragma: no cover -- no debe llamarse
        raise AssertionError("no debe abrirse cliente httpx para una IP interna")

    monkeypatch.setattr(httpx, "Client", _boom)
    assert _comun._fetch_og_image_real("http://169.254.169.254/") == ""
    assert _comun._fetch_articulo_real("http://127.0.0.1/nota") == ""


# --------------------------------------------------------------------------- #
# Redirecciones: se revalida CADA destino (httpx mockeado, sin red)            #
# --------------------------------------------------------------------------- #

# IP pública literal (de ejemplo): pasa el guard sin resolver DNS.
_URL_PUBLICA = "http://93.184.216.34/"


class _Resp:
    """Respuesta httpx falsa: redirección (`location`) o 200 con cuerpo."""

    def __init__(self, *, redirect_to: str | None = None, body: bytes = b"", url: str = _URL_PUBLICA):
        import httpx

        self.is_redirect = redirect_to is not None
        self.headers = {"location": redirect_to} if redirect_to else {}
        self._body = body
        self.url = httpx.URL(url)

    def raise_for_status(self):
        return None

    def iter_bytes(self):
        yield self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _cliente_falso(rutas: dict[str, _Resp]):
    class _FakeClient:
        def __init__(self, **kw):
            self.kw = kw

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def stream(self, metodo, url):
            return rutas[str(url)]

    return _FakeClient


def test_redireccion_a_ip_interna_se_bloquea(monkeypatch):
    import httpx

    # La URL pública redirige a loopback: el guard debe cortar en el SEGUNDO salto (sin pedirlo).
    rutas = {_URL_PUBLICA: _Resp(redirect_to="http://127.0.0.1/interno")}
    monkeypatch.setattr(httpx, "Client", _cliente_falso(rutas))
    assert _comun._fetch_html_validado(_URL_PUBLICA, timeout=1.0, max_bytes=4096) == ""


def test_doscientos_devuelve_cuerpo_y_extrae_og(monkeypatch):
    import httpx

    html = b'<meta property="og:image" content="https://cdn.test/foto.jpg">'
    rutas = {_URL_PUBLICA: _Resp(body=html)}
    monkeypatch.setattr(httpx, "Client", _cliente_falso(rutas))
    assert _comun._fetch_og_image_real(_URL_PUBLICA) == "https://cdn.test/foto.jpg"
