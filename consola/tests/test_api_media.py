"""Tests de la API Media (/api/media). OFFLINE: NUNCA se toca la red.

Cubre: subida de imagen (mime/limite), servir con anti-traversal, generacion
"no configurada" (400) y generacion con un proveedor MOCK que devuelve bytes.
"""

from __future__ import annotations

from keni_consola import media

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


def test_generar_con_proveedor_mock(cliente, monkeypatch):
    """Con clave + proveedor MOCK que devuelve bytes => 200 y guarda la imagen."""
    monkeypatch.setenv("OPENAI_API_KEY", "clave-de-prueba")
    monkeypatch.setattr(media, "_PROVEEDOR", lambda prompt: _PNG_1x1)
    r = cliente.post("/api/media/generar", json={"prompt": "un gato astronauta"})
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["id"].endswith(".png")
    # la imagen generada se puede servir
    servida = cliente.get(cuerpo["url"])
    assert servida.status_code == 200
    assert servida.content == _PNG_1x1


def test_generar_proveedor_configurado_helper(monkeypatch, entorno):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert media.proveedor_configurado() is False
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    assert media.proveedor_configurado() is True
