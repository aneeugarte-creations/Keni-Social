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

    monkeypatch.setattr(api_sistema, "_cliente_s3", lambda: _ClienteFake())
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

    monkeypatch.setattr(api_sistema, "_cliente_s3", boom)
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

    monkeypatch.setattr(api_sistema, "_cliente_s3", lambda: _ClienteFake())
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

    monkeypatch.setattr(api_sistema, "_cliente_s3", lambda: _ClienteFake())
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

    monkeypatch.setattr(api_sistema, "_cliente_s3", boom)
    c = _cli_como("admin")
    r = c.get("/api/sistema/s3/objetos")
    assert r.status_code == 200
    datos = r.json()
    assert datos["configurado"] is True
    assert datos["error"]
    assert datos["carpetas"] == []
    assert datos["objetos"] == []
