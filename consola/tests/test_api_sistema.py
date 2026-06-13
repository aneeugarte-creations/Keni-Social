"""Tests de la API Sistema (/api/sistema): panel de ADMIN (CPU/RAM/disco + S3). OFFLINE.

Cubre el CONTRATO y el cerrojo de rol (#150/#153): la info de sistema/S3 es sensible, asi
que SOLO una sesion admin real la ve; un editor o el token de mantenimiento -> 403. Nada
toca red ni disco real: el disco va por `shutil` (stdlib, sobre rutas reales del entorno
aislado) y S3 esta SIN configurar por defecto (degradado), o se mockea boto3.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth, config

from .conftest import TOKEN_PRUEBA

_ORIGIN = {"Origin": "http://testserver"}
CLAVE = "clave-de-prueba"


def _app():
    return app_modulo.crear_app(token=TOKEN_PRUEBA)


def _cli() -> TestClient:
    return TestClient(_app())


def _login(c: TestClient, usuario: str, password: str):
    return c.post(
        "/api/auth/login", json={"usuario": usuario, "password": password}, headers=_ORIGIN
    )


def _cli_como(rol: str) -> TestClient:
    """TestClient autenticado por SESION con un usuario del rol dado (admin/editor)."""
    auth.crear_usuario("u", CLAVE, rol)
    c = _cli()
    assert _login(c, "u", CLAVE).status_code == 200
    return c


def _cli_token() -> TestClient:
    """TestClient que entra SOLO por el TOKEN de mantenimiento (NO es admin, #150)."""
    c = _cli()
    c.headers.update({"Authorization": f"Bearer {TOKEN_PRUEBA}"})
    return c


# --------------------------------------------------------------------------- #
# Permisos: solo admin (editor y token -> 403)                                #
# --------------------------------------------------------------------------- #


def test_editor_no_ve_recursos_403(entorno):
    c = _cli_como("editor")
    r = c.get("/api/sistema/recursos")
    assert r.status_code == 403
    assert "administrador" in r.json()["error"].lower()


def test_editor_no_ve_s3_403(entorno):
    c = _cli_como("editor")
    assert c.get("/api/sistema/s3").status_code == 403


def test_token_mantenimiento_no_es_admin_403(entorno):
    """El token pasa la barrera de /api pero NO da acceso al panel de sistema (#150)."""
    c = _cli_token()
    assert c.get("/api/sistema/recursos").status_code == 403
    assert c.get("/api/sistema/s3").status_code == 403
    assert c.post("/api/sistema/s3/probar", headers=_ORIGIN).status_code == 403


# --------------------------------------------------------------------------- #
# Recursos (CPU/RAM/disco): contrato + degradado sin psutil                   #
# --------------------------------------------------------------------------- #


def test_admin_ve_recursos_contrato(entorno):
    c = _cli_como("admin")
    r = c.get("/api/sistema/recursos")
    assert r.status_code == 200
    datos = r.json()
    assert set(datos) >= {"cpu", "ram", "discos", "psutil"}
    assert set(datos["cpu"]) == {"porcentaje", "cores"}
    assert set(datos["ram"]) == {"usado", "total", "porcentaje"}
    assert isinstance(datos["discos"], list)
    # El entorno aislado tiene un tmp real: al menos un disco se mide (stdlib `shutil`).
    assert datos["discos"], "deberia medirse al menos el disco del volumen de estado"
    for d in datos["discos"]:
        assert set(d) == {"etiqueta", "ruta", "usado", "total", "porcentaje"}
        assert d["total"] >= d["usado"] >= 0


def test_recursos_degrada_sin_psutil(entorno, monkeypatch):
    """Si psutil no esta, CPU/RAM van a None pero el disco SIGUE (no 500)."""
    import builtins

    real_import = builtins.__import__

    def sin_psutil(nombre, *a, **k):
        if nombre == "psutil":
            raise ImportError("psutil no instalado")
        return real_import(nombre, *a, **k)

    monkeypatch.setattr(builtins, "__import__", sin_psutil)
    c = _cli_como("admin")
    r = c.get("/api/sistema/recursos")
    assert r.status_code == 200
    datos = r.json()
    assert datos["psutil"] is False
    assert datos["cpu"]["porcentaje"] is None
    assert datos["ram"]["total"] is None
    # El disco no depende de psutil: sigue presente.
    assert datos["discos"]


# --------------------------------------------------------------------------- #
# S3: degradado sin configurar + prueba de conexion                           #
# --------------------------------------------------------------------------- #


def test_s3_sin_configurar_degradado(entorno):
    """Sin S3 cableado (perfil local): degradado, NUNCA 500."""
    assert config.s3_configurado() is False
    c = _cli_como("admin")
    r = c.get("/api/sistema/s3")
    assert r.status_code == 200
    datos = r.json()
    assert datos["configurado"] is False
    assert datos["bucket"] is None
    assert datos["objetos"] is None


def test_probar_s3_sin_configurar_409(entorno):
    c = _cli_como("admin")
    r = c.post("/api/sistema/s3/probar", headers=_ORIGIN)
    assert r.status_code == 409
    assert "configurado" in r.json()["error"].lower()


def test_s3_configurado_mide_bucket(entorno, monkeypatch):
    """Con S3 cableado: head_bucket OK + conteo/suma de objetos (boto3 mockeado)."""
    monkeypatch.setenv("S3_ENDPOINT", "http://garage:3900")
    monkeypatch.setenv("S3_ACCESS_KEY", "ak")
    monkeypatch.setenv("S3_SECRET_KEY", "sk")
    monkeypatch.setenv("S3_BUCKET", "keni-media")

    class _ClienteFake:
        def head_bucket(self, **k):
            return {}

        def list_objects_v2(self, **k):
            return {
                "Contents": [{"Key": "a.png", "Size": 100}, {"Key": "b.png", "Size": 250}],
                "IsTruncated": False,
            }

    from keni_consola.api import sistema as api_sistema

    monkeypatch.setattr(api_sistema.s3, "_cliente_s3", lambda: _ClienteFake())
    c = _cli_como("admin")
    datos = c.get("/api/sistema/s3").json()
    assert datos["configurado"] is True
    assert datos["bucket"] == "keni-media"
    assert datos["salud"] == "ok"
    assert datos["objetos"] == 2
    assert datos["bytes"] == 350
    assert datos["error"] is None


def test_s3_configurado_fallo_red_degrada(entorno, monkeypatch):
    """Un fallo de boto3/red se reporta como salud err + mensaje, NO 500."""
    monkeypatch.setenv("S3_ENDPOINT", "http://garage:3900")
    monkeypatch.setenv("S3_ACCESS_KEY", "ak")
    monkeypatch.setenv("S3_SECRET_KEY", "sk")

    from keni_consola.api import sistema as api_sistema

    def boom():
        raise RuntimeError("sin red")

    monkeypatch.setattr(api_sistema.s3, "_cliente_s3", boom)
    c = _cli_como("admin")
    r = c.get("/api/sistema/s3")
    assert r.status_code == 200
    datos = r.json()
    assert datos["configurado"] is True
    assert datos["salud"] == "err"
    assert datos["error"]


# --------------------------------------------------------------------------- #
# GET /api/sistema/s3/objetos: navegador de carpetas/objetos                  #
# --------------------------------------------------------------------------- #


def test_objetos_editor_403(entorno):
    """Un editor (no admin) recibe 403 en el endpoint de objetos."""
    c = _cli_como("editor")
    assert c.get("/api/sistema/s3/objetos").status_code == 403


def test_objetos_token_403(entorno):
    """El token de mantenimiento (no sesion admin) recibe 403."""
    c = _cli_token()
    assert c.get("/api/sistema/s3/objetos").status_code == 403


def test_objetos_sin_s3_configurado(entorno):
    """Sin S3 cableado: degradado (configurado:false), NUNCA 500."""
    assert not __import__("keni_consola.config", fromlist=["config"]).s3_configurado()
    c = _cli_como("admin")
    r = c.get("/api/sistema/s3/objetos")
    assert r.status_code == 200
    datos = r.json()
    assert datos["configurado"] is False
    assert datos["carpetas"] == []
    assert datos["objetos"] == []
    assert datos["error"]  # mensaje de "no configurado"


def test_objetos_raiz(entorno, monkeypatch):
    """Con S3 cableado: lista carpetas y objetos del nivel raiz (prefijo vacio)."""
    monkeypatch.setenv("S3_ENDPOINT", "http://garage:3900")
    monkeypatch.setenv("S3_ACCESS_KEY", "ak")
    monkeypatch.setenv("S3_SECRET_KEY", "sk")
    monkeypatch.setenv("S3_BUCKET", "keni-media")

    class _ClienteFake:
        def list_objects_v2(self, **k):
            assert k.get("Delimiter") == "/"
            assert k.get("Prefix") == ""
            return {
                "CommonPrefixes": [{"Prefix": "videos/"}, {"Prefix": "imagenes/"}],
                "Contents": [{"Key": "logo.png", "Size": 512, "LastModified": None}],
                "IsTruncated": False,
            }

    from keni_consola.api import sistema as api_sistema

    monkeypatch.setattr(api_sistema.s3, "_cliente_s3", lambda: _ClienteFake())
    c = _cli_como("admin")
    r = c.get("/api/sistema/s3/objetos")
    assert r.status_code == 200
    datos = r.json()
    assert datos["configurado"] is True
    assert datos["prefijo"] == ""
    assert "videos/" in datos["carpetas"]
    assert "imagenes/" in datos["carpetas"]
    assert len(datos["objetos"]) == 1
    assert datos["objetos"][0]["key"] == "logo.png"
    assert datos["objetos"][0]["nombre"] == "logo.png"
    assert datos["objetos"][0]["tamano"] == 512
    # Migas: solo la raiz
    assert datos["migas"] == [{"nombre": "Raiz", "prefijo": ""}]
    assert datos["error"] is None


def test_objetos_subprefijo(entorno, monkeypatch):
    """Navegando a un subprefijo devuelve el prefijo normalizado y las migas correctas."""
    monkeypatch.setenv("S3_ENDPOINT", "http://garage:3900")
    monkeypatch.setenv("S3_ACCESS_KEY", "ak")
    monkeypatch.setenv("S3_SECRET_KEY", "sk")
    monkeypatch.setenv("S3_BUCKET", "keni-media")

    from datetime import datetime, timezone

    ts = datetime(2024, 5, 1, 12, 0, 0, tzinfo=timezone.utc)

    class _ClienteFake:
        def list_objects_v2(self, **k):
            assert k.get("Prefix") == "videos/"
            return {
                "CommonPrefixes": [{"Prefix": "videos/2024/"}],
                "Contents": [{"Key": "videos/portada.jpg", "Size": 1024, "LastModified": ts}],
                "IsTruncated": False,
            }

    from keni_consola.api import sistema as api_sistema

    monkeypatch.setattr(api_sistema.s3, "_cliente_s3", lambda: _ClienteFake())
    c = _cli_como("admin")
    # El prefijo se puede enviar con o sin barra final; el back lo normaliza.
    r = c.get("/api/sistema/s3/objetos?prefijo=videos")
    assert r.status_code == 200
    datos = r.json()
    assert datos["prefijo"] == "videos/"
    assert datos["carpetas"] == ["videos/2024/"]
    assert len(datos["objetos"]) == 1
    assert datos["objetos"][0]["nombre"] == "portada.jpg"
    assert datos["objetos"][0]["tamano"] == 1024
    assert datos["objetos"][0]["modificado"] == ts.isoformat()
    # Migas: Raiz + videos
    assert len(datos["migas"]) == 2
    assert datos["migas"][0] == {"nombre": "Raiz", "prefijo": ""}
    assert datos["migas"][1] == {"nombre": "videos", "prefijo": "videos/"}


def test_objetos_fallo_red_degrada(entorno, monkeypatch):
    """Un fallo de boto3/red en el explorador se reporta en error, NO 500."""
    monkeypatch.setenv("S3_ENDPOINT", "http://garage:3900")
    monkeypatch.setenv("S3_ACCESS_KEY", "ak")
    monkeypatch.setenv("S3_SECRET_KEY", "sk")

    from keni_consola.api import sistema as api_sistema

    def boom():
        raise RuntimeError("sin red")

    monkeypatch.setattr(api_sistema.s3, "_cliente_s3", boom)
    c = _cli_como("admin")
    r = c.get("/api/sistema/s3/objetos")
    assert r.status_code == 200
    datos = r.json()
    assert datos["configurado"] is True
    assert datos["error"]
    assert datos["carpetas"] == []
    assert datos["objetos"] == []


# --------------------------------------------------------------------------- #
# GET /api/sistema/s3/objeto: streaming de un objeto (preview/descarga)        #
# --------------------------------------------------------------------------- #


def test_objeto_editor_403(entorno):
    """Un editor (no admin) recibe 403 al pedir un objeto."""
    c = _cli_como("editor")
    assert c.get("/api/sistema/s3/objeto?key=a.png").status_code == 403


def test_objeto_token_403(entorno):
    """El token de mantenimiento (no sesion admin) recibe 403."""
    c = _cli_token()
    assert c.get("/api/sistema/s3/objeto?key=a.png").status_code == 403


def test_objeto_sin_s3_409(entorno):
    """Sin S3 cableado: 409 (no hay nada que servir), NUNCA 500."""
    c = _cli_como("admin")
    r = c.get("/api/sistema/s3/objeto?key=a.png")
    assert r.status_code == 409
    assert "configurado" in r.json()["error"].lower()


def test_objeto_key_traversal_rechazada(entorno, monkeypatch):
    """Una key con `..` se rechaza con 400 (anti-traversal), sin tocar S3."""
    monkeypatch.setenv("S3_ENDPOINT", "http://garage:3900")
    monkeypatch.setenv("S3_ACCESS_KEY", "ak")
    monkeypatch.setenv("S3_SECRET_KEY", "sk")
    monkeypatch.setenv("S3_BUCKET", "keni-media")

    from keni_consola.api import sistema as api_sistema

    # Si llegara a pedir el cliente seria un fallo: la validacion va antes.
    def boom():
        raise AssertionError("no debe construirse el cliente para una key invalida")

    monkeypatch.setattr(api_sistema.s3, "_cliente_s3", boom)
    c = _cli_como("admin")
    for key in ("../secret", "a/../../b", "/etc/passwd", ""):
        r = c.get(f"/api/sistema/s3/objeto?key={key}")
        assert r.status_code == 400, key


def test_objeto_inexistente_404(entorno, monkeypatch):
    """get_object que lanza NoSuchKey -> 404 (no 500)."""
    monkeypatch.setenv("S3_ENDPOINT", "http://garage:3900")
    monkeypatch.setenv("S3_ACCESS_KEY", "ak")
    monkeypatch.setenv("S3_SECRET_KEY", "sk")
    monkeypatch.setenv("S3_BUCKET", "keni-media")

    class _ClienteFake:
        def get_object(self, **k):
            err = RuntimeError("not found")
            # Imita el `e.response` de un ClientError de botocore.
            err.response = {  # type: ignore[attr-defined]
                "Error": {"Code": "NoSuchKey"},
                "ResponseMetadata": {"HTTPStatusCode": 404},
            }
            raise err

    from keni_consola.api import sistema as api_sistema

    monkeypatch.setattr(api_sistema.s3, "_cliente_s3", lambda: _ClienteFake())
    c = _cli_como("admin")
    r = c.get("/api/sistema/s3/objeto?key=no-existe.png")
    assert r.status_code == 404
    assert "no existe" in r.json()["error"].lower()


def test_objeto_streaming_ok(entorno, monkeypatch):
    """get_object OK: streamea los bytes con el Content-Type real + inline por defecto."""
    monkeypatch.setenv("S3_ENDPOINT", "http://garage:3900")
    monkeypatch.setenv("S3_ACCESS_KEY", "ak")
    monkeypatch.setenv("S3_SECRET_KEY", "sk")
    monkeypatch.setenv("S3_BUCKET", "keni-media")

    contenido = b"\x89PNG\r\n\x1a\n" + b"datos-de-imagen" * 10

    class _Body:
        def __init__(self, data: bytes):
            self._buf = data
            self._pos = 0

        def read(self, n: int = -1) -> bytes:
            if n is None or n < 0:
                trozo = self._buf[self._pos :]
                self._pos = len(self._buf)
                return trozo
            trozo = self._buf[self._pos : self._pos + n]
            self._pos += len(trozo)
            return trozo

        def close(self):
            pass

    class _ClienteFake:
        def get_object(self, **k):
            assert k["Bucket"] == "keni-media"
            assert k["Key"] == "logo.png"
            return {
                "Body": _Body(contenido),
                "ContentType": "image/png",
                "ContentLength": len(contenido),
            }

    from keni_consola.api import sistema as api_sistema

    monkeypatch.setattr(api_sistema.s3, "_cliente_s3", lambda: _ClienteFake())
    c = _cli_como("admin")
    r = c.get("/api/sistema/s3/objeto?key=logo.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert "inline" in r.headers["content-disposition"]
    assert "logo.png" in r.headers["content-disposition"]
    assert r.content == contenido


def test_objeto_descarga_attachment(entorno, monkeypatch):
    """`?descargar=1` fuerza Content-Disposition: attachment."""
    monkeypatch.setenv("S3_ENDPOINT", "http://garage:3900")
    monkeypatch.setenv("S3_ACCESS_KEY", "ak")
    monkeypatch.setenv("S3_SECRET_KEY", "sk")
    monkeypatch.setenv("S3_BUCKET", "keni-media")

    class _Body:
        def __init__(self):
            self._dado = False

        def read(self, n: int = -1) -> bytes:
            if self._dado:
                return b""
            self._dado = True
            return b"contenido"

        def close(self):
            pass

    class _ClienteFake:
        def get_object(self, **k):
            return {"Body": _Body(), "ContentType": "text/plain", "ContentLength": 9}

    from keni_consola.api import sistema as api_sistema

    monkeypatch.setattr(api_sistema.s3, "_cliente_s3", lambda: _ClienteFake())
    c = _cli_como("admin")
    r = c.get("/api/sistema/s3/objeto?key=nota.txt&descargar=1")
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]


def test_objeto_demasiado_grande_413(entorno, monkeypatch):
    """Un objeto que supera el cap de tamano -> 413 (no se streamea)."""
    monkeypatch.setenv("S3_ENDPOINT", "http://garage:3900")
    monkeypatch.setenv("S3_ACCESS_KEY", "ak")
    monkeypatch.setenv("S3_SECRET_KEY", "sk")
    monkeypatch.setenv("S3_BUCKET", "keni-media")

    from keni_consola.api import sistema as api_sistema

    class _ClienteFake:
        def get_object(self, **k):
            return {
                "Body": object(),  # no se debe leer: el cap corta antes
                "ContentType": "application/octet-stream",
                "ContentLength": api_sistema._MAX_BYTES_OBJETO + 1,
            }

    monkeypatch.setattr(api_sistema.s3, "_cliente_s3", lambda: _ClienteFake())
    c = _cli_como("admin")
    r = c.get("/api/sistema/s3/objeto?key=enorme.bin")
    assert r.status_code == 413


# --------------------------------------------------------------------------- #
# Borrado de un objeto (POST /api/sistema/s3/borrar) — UNICA op destructiva    #
# --------------------------------------------------------------------------- #


def _s3_env(monkeypatch):
    """Cablea las S3_* para los tests de borrado (sin tocar red real)."""
    monkeypatch.setenv("S3_ENDPOINT", "http://garage:3900")
    monkeypatch.setenv("S3_ACCESS_KEY", "ak")
    monkeypatch.setenv("S3_SECRET_KEY", "sk")
    monkeypatch.setenv("S3_BUCKET", "keni-media")


def test_borrar_editor_403(entorno):
    """Un editor (no admin) recibe 403 al intentar borrar."""
    c = _cli_como("editor")
    r = c.post("/api/sistema/s3/borrar", json={"key": "a.png"}, headers=_ORIGIN)
    assert r.status_code == 403


def test_borrar_token_403(entorno):
    """El token de mantenimiento (no sesion admin) recibe 403."""
    c = _cli_token()
    r = c.post("/api/sistema/s3/borrar", json={"key": "a.png"}, headers=_ORIGIN)
    assert r.status_code == 403


def test_borrar_sin_s3_409(entorno):
    """Sin S3 cableado: 409 (no hay nada que borrar), NUNCA 500."""
    c = _cli_como("admin")
    r = c.post("/api/sistema/s3/borrar", json={"key": "a.png"}, headers=_ORIGIN)
    assert r.status_code == 409
    assert "configurado" in r.json()["error"].lower()


def test_borrar_key_invalida_400(entorno, monkeypatch):
    """Keys con `..`, absolutas, vacias o de 'carpeta' (terminadas en /) -> 400 sin tocar S3."""
    _s3_env(monkeypatch)
    from keni_consola.api import sistema as api_sistema

    def boom():
        raise AssertionError("no debe construirse el cliente para una key invalida")

    monkeypatch.setattr(api_sistema.s3, "_cliente_s3", boom)
    c = _cli_como("admin")
    for key in ("../secret", "a/../../b", "/etc/passwd", "", "carpeta/"):
        r = c.post("/api/sistema/s3/borrar", json={"key": key}, headers=_ORIGIN)
        assert r.status_code == 400, key


def test_borrar_inexistente_404(entorno, monkeypatch):
    """head_object que lanza NoSuchKey -> 404 y NO se llama a delete_object."""
    _s3_env(monkeypatch)

    class _ClienteFake:
        def head_object(self, **k):
            err = RuntimeError("not found")
            err.response = {  # type: ignore[attr-defined]
                "Error": {"Code": "NoSuchKey"},
                "ResponseMetadata": {"HTTPStatusCode": 404},
            }
            raise err

        def delete_object(self, **k):
            raise AssertionError("no debe borrar un objeto inexistente")

    from keni_consola.api import sistema as api_sistema

    monkeypatch.setattr(api_sistema.s3, "_cliente_s3", lambda: _ClienteFake())
    c = _cli_como("admin")
    r = c.post("/api/sistema/s3/borrar", json={"key": "no-existe.png"}, headers=_ORIGIN)
    assert r.status_code == 404
    assert "no existe" in r.json()["error"].lower()


def test_borrar_ok(entorno, monkeypatch):
    """head_object OK + delete_object con la key exacta -> 200 {borrado, key}."""
    _s3_env(monkeypatch)
    llamadas: dict = {}

    class _ClienteFake:
        def head_object(self, **k):
            return {"ContentLength": 10}

        def delete_object(self, **k):
            llamadas["bucket"] = k["Bucket"]
            llamadas["key"] = k["Key"]
            return {}

    from keni_consola.api import sistema as api_sistema

    monkeypatch.setattr(api_sistema.s3, "_cliente_s3", lambda: _ClienteFake())
    c = _cli_como("admin")
    r = c.post(
        "/api/sistema/s3/borrar", json={"key": "videos/clip.mp4"}, headers=_ORIGIN
    )
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo == {"borrado": True, "key": "videos/clip.mp4"}
    assert llamadas == {"bucket": "keni-media", "key": "videos/clip.mp4"}


def test_borrar_fallo_red_502(entorno, monkeypatch):
    """Un fallo de almacenamiento al borrar (no 404) -> 502, sin tumbar la pagina."""
    _s3_env(monkeypatch)

    class _ClienteFake:
        def head_object(self, **k):
            return {"ContentLength": 10}

        def delete_object(self, **k):
            raise RuntimeError("garage caido")

    from keni_consola.api import sistema as api_sistema

    monkeypatch.setattr(api_sistema.s3, "_cliente_s3", lambda: _ClienteFake())
    c = _cli_como("admin")
    r = c.post("/api/sistema/s3/borrar", json={"key": "a.png"}, headers=_ORIGIN)
    assert r.status_code == 502


# --------------------------------------------------------------------------- #
# Borrado en lote (seleccion multiple del explorador)                          #
# --------------------------------------------------------------------------- #


def test_borrar_lote_token_403(entorno):
    """El token de mantenimiento (no sesion admin) recibe 403."""
    c = _cli_token()
    r = c.post("/api/sistema/s3/borrar-lote", json={"keys": ["a.png"]}, headers=_ORIGIN)
    assert r.status_code == 403


def test_borrar_lote_sin_s3_409(entorno):
    """Sin S3 cableado: 409, NUNCA 500."""
    c = _cli_como("admin")
    r = c.post("/api/sistema/s3/borrar-lote", json={"keys": ["a.png"]}, headers=_ORIGIN)
    assert r.status_code == 409


def test_borrar_lote_sin_keys_validas_400(entorno, monkeypatch):
    """keys=[] o solo invalidas/'carpetas' -> 400 sin tocar S3."""
    _s3_env(monkeypatch)
    from keni_consola.api import sistema as api_sistema

    def boom():
        raise AssertionError("no debe construirse el cliente sin keys validas")

    monkeypatch.setattr(api_sistema.s3, "_cliente_s3", boom)
    c = _cli_como("admin")
    for keys in ([], ["../secret", "carpeta/", "/abs", ""]):
        r = c.post("/api/sistema/s3/borrar-lote", json={"keys": keys}, headers=_ORIGIN)
        assert r.status_code == 400, keys
    # keys no es lista -> 400.
    r = c.post("/api/sistema/s3/borrar-lote", json={"keys": "a.png"}, headers=_ORIGIN)
    assert r.status_code == 400


def test_borrar_lote_ok(entorno, monkeypatch):
    """delete_objects con las keys validas/deduplicadas -> 200 {borrados, fallidos}."""
    _s3_env(monkeypatch)
    llamadas: dict = {}

    class _ClienteFake:
        def delete_objects(self, **k):
            llamadas["bucket"] = k["Bucket"]
            llamadas["objects"] = [o["Key"] for o in k["Delete"]["Objects"]]
            return {"Deleted": [{"Key": o["Key"]} for o in k["Delete"]["Objects"]]}

    from keni_consola.api import sistema as api_sistema

    monkeypatch.setattr(api_sistema.s3, "_cliente_s3", lambda: _ClienteFake())
    c = _cli_como("admin")
    # Mezcla validas, una duplicada y una "carpeta" (se descarta).
    r = c.post(
        "/api/sistema/s3/borrar-lote",
        json={"keys": ["a.png", "videos/clip.mp4", "a.png", "carpeta/"]},
        headers=_ORIGIN,
    )
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["borrados"] == ["a.png", "videos/clip.mp4"]
    assert cuerpo["fallidos"] == []
    # Sin duplicados ni carpetas en la llamada a S3.
    assert llamadas["objects"] == ["a.png", "videos/clip.mp4"]
    assert llamadas["bucket"] == "keni-media"


def test_borrar_lote_errores_parciales(entorno, monkeypatch):
    """Errors de delete_objects -> en fallidos; el resto en borrados."""
    _s3_env(monkeypatch)

    class _ClienteFake:
        def delete_objects(self, **k):
            return {
                "Deleted": [{"Key": "ok.png"}],
                "Errors": [{"Key": "malo.png", "Message": "AccessDenied"}],
            }

    from keni_consola.api import sistema as api_sistema

    monkeypatch.setattr(api_sistema.s3, "_cliente_s3", lambda: _ClienteFake())
    c = _cli_como("admin")
    r = c.post(
        "/api/sistema/s3/borrar-lote",
        json={"keys": ["ok.png", "malo.png"]},
        headers=_ORIGIN,
    )
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["borrados"] == ["ok.png"]
    assert cuerpo["fallidos"] == [{"key": "malo.png", "error": "AccessDenied"}]


def test_borrar_lote_fallo_red_502(entorno, monkeypatch):
    """delete_objects que revienta (no por key) -> 502, sin tumbar la pagina."""
    _s3_env(monkeypatch)

    class _ClienteFake:
        def delete_objects(self, **k):
            raise RuntimeError("garage caido")

    from keni_consola.api import sistema as api_sistema

    monkeypatch.setattr(api_sistema.s3, "_cliente_s3", lambda: _ClienteFake())
    c = _cli_como("admin")
    r = c.post(
        "/api/sistema/s3/borrar-lote", json={"keys": ["a.png"]}, headers=_ORIGIN
    )
    assert r.status_code == 502
