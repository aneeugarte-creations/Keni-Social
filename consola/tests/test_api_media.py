"""Tests de la API Media (/api/media). OFFLINE: NUNCA se toca la red.

Cubre: subida de imagen (mime/limite), servir con anti-traversal, generacion
"no configurada" (400) y generacion con un proveedor MOCK que devuelve bytes.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from keni_consola import media
from keni_consola.dominio import extraccion_url

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
    # Va a la carpeta `fotos/` (division por tipo) con nombre content-addressed.
    assert cuerpo["id"].startswith("fotos/")
    # El nombre en el almacen NO es el del cliente (es un hash, no "foto.png").
    assert "foto.png" not in cuerpo["id"]


def test_subir_misma_foto_deduplica(cliente):
    """Subir la MISMA imagen dos veces guarda UN solo objeto (misma key content-addressed)."""
    id1 = cliente.post(
        "/api/media", files={"archivo": ("a.png", _PNG_1x1, "image/png")}
    ).json()["id"]
    id2 = cliente.post(
        "/api/media", files={"archivo": ("otro-nombre.png", _PNG_1x1, "image/png")}
    ).json()["id"]
    assert id1 == id2  # mismo contenido -> misma key -> no se duplica


def test_subir_categoria_plantillas(cliente):
    """El editor de plantillas sube con `categoria=plantillas` -> carpeta `plantillas/`."""
    r = cliente.post(
        "/api/media",
        data={"categoria": "plantillas"},
        files={"archivo": ("fondo.png", _PNG_1x1, "image/png")},
    )
    assert r.status_code == 200
    assert r.json()["id"].startswith("plantillas/")


def test_subir_categoria_invalida_cae_a_fotos(cliente):
    """Una categoria fuera de la allowlist publica (p.ej. `logos`) cae a `fotos/` (no se cuela)."""
    r = cliente.post(
        "/api/media",
        data={"categoria": "logos"},
        files={"archivo": ("x.png", _PNG_1x1, "image/png")},
    )
    assert r.status_code == 200
    assert r.json()["id"].startswith("fotos/")


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


def test_subir_video_ok(cliente):
    """POST /api/media/video guarda un mp4 en `videos/` (content-addressed) -> {id, url}."""
    r = cliente.post(
        "/api/media/video", files={"archivo": ("clip.mp4", b"datos-video", "video/mp4")}
    )
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["id"].startswith("videos/")
    assert cuerpo["id"].endswith(".mp4")
    assert cuerpo["url"] == f"/api/media/{cuerpo['id']}"
    assert "clip.mp4" not in cuerpo["id"]  # nombre = hash, no el del cliente


def test_subir_video_mime_no_video_400(cliente):
    r = cliente.post(
        "/api/media/video", files={"archivo": ("nota.txt", b"hola", "text/plain")}
    )
    assert r.status_code == 400


def test_subir_video_sin_archivo_400(cliente):
    r = cliente.post("/api/media/video", data={"otro": "x"})
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
# POST /api/media/desde-url (hostear la imagen original de una URL externa)    #
# --------------------------------------------------------------------------- #
# La descarga binaria vive detras de `extraccion_url._DESCARGADOR_BYTES`, que se
# PARCHEA para NUNCA tocar la red (igual que `_PROVEEDOR` en la generacion).


def test_desde_url_ok(cliente, monkeypatch):
    """Bytes PNG validos => 200 con `{id, url}` y la imagen se puede servir."""
    monkeypatch.setattr(extraccion_url, "_DESCARGADOR_BYTES", lambda url: _PNG_1x1)
    r = cliente.post("/api/media/desde-url", json={"url": "https://example.com/x.png"})
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["id"].endswith(".png")
    assert cuerpo["url"] == f"/api/media/{cuerpo['id']}"
    # El asset hosteado se sirve por la API de media.
    servida = cliente.get(cuerpo["url"])
    assert servida.status_code == 200
    assert servida.content == _PNG_1x1


def test_desde_url_sin_url_400(cliente):
    r = cliente.post("/api/media/desde-url", json={})
    assert r.status_code == 400


def test_desde_url_vacia_400(cliente):
    r = cliente.post("/api/media/desde-url", json={"url": "   "})
    assert r.status_code == 400


def test_desde_url_no_imagen_400(cliente, monkeypatch):
    """Lo descargado NO es una imagen => 400 (ExtraccionError -> mensaje en espanol)."""
    monkeypatch.setattr(extraccion_url, "_DESCARGADOR_BYTES", lambda url: b"<html>error</html>")
    r = cliente.post("/api/media/desde-url", json={"url": "https://example.com/x.png"})
    assert r.status_code == 400
    assert "imagen" in r.json()["error"].lower()


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
    monkeypatch.setattr(
        media, "_PROVEEDOR", lambda prompt, modelo="": media.SalidaImagen(_PNG_1x1, 0.0, modelo)
    )
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


def test_generar_imagen_detallado_captura_coste_y_modelo(monkeypatch, entorno):
    """`generar_imagen_detallado` devuelve bytes + coste + modelo del proveedor."""
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(
        media, "_PROVEEDOR",
        lambda prompt, modelo="": media.SalidaImagen(_PNG_1x1, 0.03, modelo or "def"),
    )
    salida = media.generar_imagen_detallado("un gato", modelo="openai/gpt-5-image")
    assert salida.datos == _PNG_1x1
    assert salida.coste_usd == 0.03
    assert salida.modelo == "openai/gpt-5-image"
    # `generar_imagen` sigue devolviendo SOLO los bytes (compat con los llamadores legados).
    assert media.generar_imagen("un gato") == _PNG_1x1


def test_generar_imagen_detallado_modelo_invalido(monkeypatch, entorno):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    import pytest

    with pytest.raises(media.MediaError):
        media.generar_imagen_detallado("x", modelo="inventado/xl")


def test_coste_de_lee_usage_cost():
    """`_coste_de` saca `usage.cost` (USD); 0.0 si no viene o es invalido."""
    assert media._coste_de({"usage": {"cost": 0.07}}) == 0.07
    assert media._coste_de({"usage": {}}) == 0.0
    assert media._coste_de({}) == 0.0
    assert media._coste_de({"usage": {"cost": "nan-no"}}) == 0.0


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
    assert media._clave_imagen() == "clave-del-almacen"


# --------------------------------------------------------------------------- #
# Modelo de imagen: lista curada + precedencia de _modelo()                   #
# --------------------------------------------------------------------------- #


def test_modelos_disponibles_lista_curada():
    """`modelos_disponibles()` devuelve la lista curada {id, etiqueta}; copia, no la fuente."""
    modelos = media.modelos_disponibles()
    assert modelos == media.MODELOS_IMAGEN  # mismo contenido
    assert modelos is not media.MODELOS_IMAGEN  # pero es una copia
    assert all(set(m) == {"id", "etiqueta"} for m in modelos)
    assert modelos[0]["id"] == media._MODELO_DEFECTO == "openai/gpt-5-image-mini"


def test_modelo_valido():
    assert media.modelo_valido("openai/gpt-5-image-mini") is True
    assert media.modelo_valido("google/gemini-2.5-flash-image") is True
    assert media.modelo_valido("inventado/foo") is False
    assert media.modelo_valido("") is False


def test_modelo_por_defecto_sin_almacen_ni_env(monkeypatch, entorno):
    """Sin modelo guardado y sin env => el por defecto (GPT-5 Image Mini)."""
    monkeypatch.delenv("OPENROUTER_IMAGE_MODEL", raising=False)
    assert media._modelo() == "openai/gpt-5-image-mini"


def test_modelo_env_gana_al_defecto(monkeypatch, entorno):
    """Con env y sin almacen => gana el env."""
    monkeypatch.setenv("OPENROUTER_IMAGE_MODEL", "openai/gpt-5-image")
    assert media._modelo() == "openai/gpt-5-image"


def test_modelo_almacen_gana_al_env_y_defecto(monkeypatch, entorno):
    """El modelo guardado por la UI gana al env y al por defecto (precedencia)."""
    from keni_consola import secretos

    monkeypatch.setenv("OPENROUTER_IMAGE_MODEL", "openai/gpt-5-image")
    secretos.guardar_modelo_imagen("openai/gpt-5.4-image-2")
    assert media._modelo() == "openai/gpt-5.4-image-2"


def test_modelo_almacen_vacio_cae_al_env(monkeypatch, entorno):
    """Un modelo guardado vacio se trata como ausente => cae al env."""
    from keni_consola import secretos

    monkeypatch.setenv("OPENROUTER_IMAGE_MODEL", "openai/gpt-5-image")
    secretos.guardar_modelo_imagen("   ")
    assert media._modelo() == "openai/gpt-5-image"


# --------------------------------------------------------------------------- #
# Seguridad: follow_redirects=False en _proveedor_openrouter (#117)           #
# --------------------------------------------------------------------------- #


def test_proveedor_openrouter_no_sigue_redirects_a_otro_host(monkeypatch):
    """_proveedor_openrouter pasa follow_redirects=False a httpx.post.

    Un redirect 302 a un host distinto NO debe reenviar el Bearer. Con
    follow_redirects=False httpx devuelve la 3xx directamente; el codigo la trata
    como error (status != 200) y lanza MediaError sin seguir el redirect.
    Verificamos que el kwarg llega a httpx.post y que el redirect se rechaza.
    """
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-media-1234")

    mock_resp = MagicMock()
    mock_resp.status_code = 302

    with patch("httpx.post", return_value=mock_resp) as mock_post:
        try:
            media._proveedor_openrouter("un gato espacial")
        except media.MediaError:
            pass  # esperado: 302 no es 200

    _, kwargs = mock_post.call_args
    assert kwargs.get("follow_redirects") is False, (
        "follow_redirects=False ausente: un redirect puede filtrar el Bearer"
    )


def test_proveedor_openrouter_no_reenvio_bearer_en_redirect(monkeypatch):
    """Simula un redirect 302 a otro host y verifica que el Bearer no se reenvía.

    Con follow_redirects=False httpx NO llama al host de destino del redirect,
    así que la clave nunca llega a un servidor externo. El mock confirma que
    httpx.post se invocó UNA SOLA VEZ (solo la URL de OpenRouter, no la de redirect).
    """
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-secreto-media-5678")

    redirect_resp = MagicMock()
    redirect_resp.status_code = 302
    redirect_resp.headers = {"location": "https://evil.example.com/captura"}

    with patch("httpx.post", return_value=redirect_resp) as mock_post:
        try:
            media._proveedor_openrouter("un cohete rojo")
        except media.MediaError:
            pass  # esperado: 302 no es 200

    assert mock_post.call_count == 1
    url_llamada = mock_post.call_args[0][0]
    assert "openrouter.ai" in url_llamada
    assert "evil.example.com" not in url_llamada


# --------------------------------------------------------------------------- #
# Observabilidad del error: el motivo REAL viaja al mensaje (toast)            #
# --------------------------------------------------------------------------- #


def test_proveedor_openrouter_fuerza_imagen_con_system(monkeypatch):
    """La petición DEBE anteponer un mensaje de sistema que fuerce salida de imagen.

    Los modelos GPT-5 Image son chat-based: sin esta directiva responden TEXTO ante
    prompts noticiosos (p. ej. "¿Quieres que redacte un titular?") en vez de la imagen.
    Verificamos que el body lleva `system` (la directiva) ANTES del `user` (el prompt),
    sin perder el prompt ni las `modalities`.
    """
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-1234")
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "choices": [{"message": {"images": [{"image_url": {"url": "data:image/png;base64,eA=="}}]}}]
    }
    with patch("httpx.post", return_value=resp) as mock_post:
        media._proveedor_openrouter("Un sismo en Cuba perceptible en Quintana Roo")

    cuerpo = mock_post.call_args.kwargs["json"]
    mensajes = cuerpo["messages"]
    # El system es el cuerpo EFECTIVO del prompt editable de la Biblioteca (semilla del paquete),
    # no una constante: exige una sola foto y prohibe texto/infografia.
    assert mensajes[0]["role"] == "system"
    assert mensajes[0]["content"] == media._sistema_imagen()
    assert "fotograf" in mensajes[0]["content"].lower()
    assert mensajes[-1] == {"role": "user", "content": "Un sismo en Cuba perceptible en Quintana Roo"}
    assert cuerpo["modalities"] == ["image", "text"]


def test_proveedor_openrouter_200_sin_imagen_muestra_el_texto(monkeypatch):
    """200 pero sin imagen: el modelo respondió TEXTO (rechazo/aclaración). El error
    debe MOSTRAR ese texto en vez del genérico 'respuesta inesperada'."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-1234")
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "choices": [{"finish_reason": "stop", "message": {"content": "No puedo generar esa imagen."}}]
    }
    with patch("httpx.post", return_value=resp):
        try:
            media._proveedor_openrouter("foto de algo")
            raise AssertionError("debió lanzar MediaError")
        except media.MediaError as e:
            assert "No puedo generar esa imagen." in str(e)


def test_proveedor_openrouter_error_muestra_el_motivo(monkeypatch):
    """status != 200: el mensaje incluye el código y el motivo del cuerpo (error.message)."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-1234")
    resp = MagicMock()
    resp.status_code = 400
    resp.json.return_value = {"error": {"message": "modelo no disponible"}}
    with patch("httpx.post", return_value=resp):
        try:
            media._proveedor_openrouter("foto de algo")
            raise AssertionError("debió lanzar MediaError")
        except media.MediaError as e:
            assert "400" in str(e) and "modelo no disponible" in str(e)
