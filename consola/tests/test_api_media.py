"""Tests de la API Media (/api/media). OFFLINE: NUNCA se toca la red.

Cubre: subida de imagen (mime/limite), servir con anti-traversal, generacion
"no configurada" (400) y generacion con un proveedor MOCK que devuelve bytes.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from keni_consola import media

from .conftest import _cliente, lanzador_imagen_ejecuta

# PNG minimo valido (1x1) -> bytes de ejemplo para subir.
_PNG_1x1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


# --------------------------------------------------------------------------- #
# POST /api/media (subida)                                                    #
# --------------------------------------------------------------------------- #


def test_subir_imagen_ok(cliente):
    r = cliente.post("/api/media", files={"archivo": ("foto.png", _PNG_1x1, "image/png")})
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["id"].endswith(".png")
    assert cuerpo["url"] == f"/api/media/{cuerpo['id']}"
    # el nombre en disco NO es el del cliente
    assert "foto" not in cuerpo["id"]


def test_subir_sin_archivo_400(cliente):
    r = cliente.post("/api/media", data={"otro": "x"})
    assert r.status_code == 400


def test_subir_mime_no_imagen_400(cliente):
    r = cliente.post("/api/media", files={"archivo": ("nota.txt", b"hola", "text/plain")})
    assert r.status_code == 400
    assert "imágenes" in r.json()["error"].lower() or "imagen" in r.json()["error"].lower()


def test_subir_vacia_400(cliente):
    r = cliente.post("/api/media", files={"archivo": ("v.png", b"", "image/png")})
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# GET /api/media/{nombre} (servir + anti-traversal)                           #
# --------------------------------------------------------------------------- #


def test_servir_imagen_subida(cliente):
    nombre = cliente.post(
        "/api/media", files={"archivo": ("foto.png", _PNG_1x1, "image/png")}
    ).json()["id"]
    r = cliente.get(f"/api/media/{nombre}")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/png")
    assert r.content == _PNG_1x1


def test_servir_inexistente_404(cliente):
    assert cliente.get("/api/media/noexiste.png").status_code == 404


def test_servir_anti_traversal(cliente):
    # Un nombre que intenta escapar del dir de media no debe servir nada sensible.
    r = cliente.get("/api/media/..%2f..%2f..%2fetc%2fpasswd")
    assert r.status_code == 404


def test_resolver_media_rechaza_traversal(entorno):
    assert media.resolver_media("../../etc/passwd") is None
    assert media.resolver_media("/etc/passwd") is None


# --------------------------------------------------------------------------- #
# POST /api/media/generar                                                     #
# --------------------------------------------------------------------------- #


def test_generar_no_configurado_400(cliente):
    """Sin proveedor (OPENAI_API_KEY borrada en conftest) => 400 con mensaje claro."""
    r = cliente.post("/api/media/generar", json={"prompt": "un gato astronauta"})
    assert r.status_code == 400
    assert "no está configurada" in r.json()["error"]


def test_generar_sin_prompt_400(cliente):
    r = cliente.post("/api/media/generar", json={})
    assert r.status_code == 400


def test_generar_con_proveedor_mock(entorno, monkeypatch):
    """Con clave + proveedor MOCK => la generacion (background) completa con `{id,url}`.

    El lanzador de imagen aqui EJECUTA el `generar` real (con el proveedor MOCK), asi se
    cubre el pipeline generar -> guardar -> servir sin red.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "clave-de-prueba")
    monkeypatch.setattr(media, "_PROVEEDOR", lambda prompt: _PNG_1x1)
    cli = _cliente(lanzar_imagen=lanzador_imagen_ejecuta())
    r = cli.post("/api/media/generar", json={"prompt": "un gato astronauta"})
    assert r.status_code == 200
    gen = r.json()["generacion"]
    assert gen["tipo"] == "imagen"
    res = gen["resultado"]
    assert res["id"].endswith(".png")
    # la imagen generada se puede servir
    servida = cli.get(res["url"])
    assert servida.status_code == 200
    assert servida.content == _PNG_1x1


def test_generar_proveedor_configurado_helper(monkeypatch, entorno):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert media.proveedor_configurado() is False
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    assert media.proveedor_configurado() is True


def test_media_lee_clave_del_almacen(monkeypatch, entorno):
    """media toma la clave del almacen de secretos (no solo del env)."""
    from keni_consola import secretos

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert media.proveedor_configurado() is False
    secretos.guardar_clave_imagen("openai", "sk-del-almacen-1234")
    assert media.proveedor_configurado() is True


def test_media_almacen_tiene_prioridad_sobre_env(monkeypatch, entorno):
    """Si hay clave en el almacen, esa se usa antes que la del env."""
    from keni_consola import secretos

    monkeypatch.setenv("OPENAI_API_KEY", "clave-de-env")
    secretos.guardar_clave_imagen("openai", "clave-del-almacen")
    assert media._clave_openai() == "clave-del-almacen"


# --------------------------------------------------------------------------- #
# Seguridad: follow_redirects=False en _proveedor_openai (#117)               #
# --------------------------------------------------------------------------- #


def test_proveedor_openai_no_sigue_redirects_a_otro_host(monkeypatch):
    """_proveedor_openai pasa follow_redirects=False a httpx.post.

    Un redirect 302 de OpenAI a un host distinto NO debe reenviar el Bearer.
    Con follow_redirects=False httpx devuelve la 3xx directamente; el codigo
    la trata como error (status != 200) y lanza MediaError sin seguir el redirect.
    Verificamos que el kwarg llega a httpx.post y que el redirect se rechaza.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-media-1234")

    mock_resp = MagicMock()
    mock_resp.status_code = 302

    with patch("httpx.post", return_value=mock_resp) as mock_post:
        try:
            media._proveedor_openai("un gato espacial")
        except media.MediaError:
            pass  # esperado: 302 no es 200

    _, kwargs = mock_post.call_args
    assert kwargs.get("follow_redirects") is False, (
        "follow_redirects=False ausente: un redirect puede filtrar el Bearer"
    )


def test_proveedor_openai_no_reenvio_bearer_en_redirect(monkeypatch):
    """Simula un redirect 302 a otro host y verifica que el Bearer no se reenvía.

    Con follow_redirects=False httpx NO llama al host de destino del redirect,
    así que la clave nunca llega a un servidor externo. El mock confirma que
    httpx.post se invocó UNA SOLA VEZ (solo la URL de OpenAI, no la de redirect).
    """
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secreto-media-5678")

    redirect_resp = MagicMock()
    redirect_resp.status_code = 302
    redirect_resp.headers = {"location": "https://evil.example.com/captura"}

    with patch("httpx.post", return_value=redirect_resp) as mock_post:
        try:
            media._proveedor_openai("un cohete rojo")
        except media.MediaError:
            pass  # esperado: 302 no es 200

    assert mock_post.call_count == 1
    url_llamada = mock_post.call_args[0][0]
    assert "openai.com" in url_llamada
    assert "evil.example.com" not in url_llamada
