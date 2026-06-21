"""Dashboard "Marcas" (`GET /api/marcas`): vista única por marca × red (Postproxy).

SOLO ADMIN: un editor recibe 403. Se MOCKEAN el estado de conexiones y el cliente
de Postproxy, así el test ejercita la AGREGACIÓN (no la red real). Por cada marca: una
fila por red con su estado de conexión + sus números (de Postproxy) y el sumatorio de la
marca. Nunca casca y NUNCA inventa ceros. Metricool NO aparece (vive en Analíticas).
"""

from __future__ import annotations

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth
from keni_consola.api import conexiones
from keni_metricas.fuentes import postproxy as pp_cliente

from .conftest import TOKEN_PRUEBA

_ORIGIN = {"Origin": "http://testserver"}
CLAVE = "contraseña-larga-de-prueba-dash"


def _cli() -> TestClient:
    return TestClient(app_modulo.crear_app(token=TOKEN_PRUEBA))


def _cli_como(rol: str) -> TestClient:
    auth.crear_usuario("u", CLAVE, rol)
    c = _cli()
    r = c.post("/api/auth/login", json={"usuario": "u", "password": CLAVE}, headers=_ORIGIN)
    assert r.status_code == 200
    return c


def _mock_postproxy(monkeypatch, *, api_key="PP_KEY", grupo="g1"):
    monkeypatch.setattr(conexiones, "_postproxy_api_key", lambda cfg: api_key)
    monkeypatch.setattr(conexiones, "_config_existente", lambda: {})
    monkeypatch.setattr(
        conexiones, "estado_postproxy",
        lambda: {"configurado": bool(api_key), "pista": "····9999", "marcas": [
            {"marca": "claro_sports", "etiqueta": "Claro Sports",
             "profile_group_id": grupo, "canal": "postproxy"},
            {"marca": "unotv", "etiqueta": "UnoTV", "profile_group_id": None, "canal": "metricool"}]},
    )

    def _perfiles(_api_key, g):
        if g == "g1":
            return True, "ok", [
                {"id": "p1", "name": "@claro", "platform": "instagram", "status": "active", "post_count": 99},
                {"id": "p2", "name": "Claro FB", "platform": "facebook", "status": "active", "post_count": 30},
            ]
        return False, "sin grupo", []

    def _stats(_api_key, pid):
        if pid == "p1":
            return True, "ok", {"seguidores": 700, "posts_totales": 120, "posts_dia": 2.0}
        return True, "ok", {"seguidores": 300, "posts_totales": None, "posts_dia": None}

    monkeypatch.setattr(pp_cliente, "listar_perfiles", _perfiles)
    monkeypatch.setattr(pp_cliente, "stats_perfil", _stats)


def test_editor_403(entorno):
    c = _cli_como("editor")
    assert c.get("/api/marcas").status_code == 403


def test_vista_unica_estado_mas_numeros(entorno, monkeypatch):
    _mock_postproxy(monkeypatch)
    c = _cli_como("admin")
    r = c.get("/api/marcas")
    assert r.status_code == 200
    cuerpo = r.json()
    assert set(cuerpo["totales"]) == {"seguidores", "posts_totales", "posts_dia"}
    por_marca = {m["marca"]: m for m in cuerpo["marcas"]}
    cs = por_marca["claro_sports"]
    # Sin Metricool en la respuesta.
    assert "metricool" not in cs
    # `marca` es el id_metricas (clave Postproxy); `id` es el canónico (clave del CRUD).
    assert cs["id"] == "claro-sports"
    assert cs["tipo"] == "noticias"  # del catálogo (editable en el form de marca)
    assert cs["canal_publicacion"] == "postproxy"
    assert cs["postproxy"] == {"conectado": True, "profile_group_id": "g1"}
    # Una fila por red del catálogo (10, sin google_business).
    assert len(cs["redes"]) == 10
    ig = next(red for red in cs["redes"] if red["plataforma"] == "instagram")
    assert ig["conectado"] is True
    assert ig["perfil_id"] == "p1"
    assert ig["nombre_cuenta"] == "@claro"
    assert (ig["seguidores"], ig["posts_totales"], ig["posts_dia"]) == (700, 120, 2.0)
    fb = next(red for red in cs["redes"] if red["plataforma"] == "facebook")
    # posts: respaldo al post_count del perfil cuando el snapshot no lo trae.
    assert (fb["seguidores"], fb["posts_totales"], fb["posts_dia"]) == (300, 30, None)
    # Una red sin conectar: todo null + sin perfil.
    tk = next(red for red in cs["redes"] if red["plataforma"] == "tiktok")
    assert tk["conectado"] is False
    assert tk["perfil_id"] is None
    assert tk["seguidores"] is None
    # Sumatorio de la marca.
    assert cs["total"] == {"seguidores": 1000, "posts_totales": 150, "posts_dia": 2.0}
    # Totales globales.
    assert cuerpo["totales"] == {"seguidores": 1000, "posts_totales": 150, "posts_dia": 2.0}
    # google_business NO aparece.
    assert all(r["plataforma"] != "google_business" for m in cuerpo["marcas"] for r in m["redes"])


def test_marca_sin_grupo_todo_desconectado(entorno, monkeypatch):
    _mock_postproxy(monkeypatch)
    c = _cli_como("admin")
    cuerpo = c.get("/api/marcas").json()
    unotv = next(m for m in cuerpo["marcas"] if m["marca"] == "unotv")
    assert unotv["postproxy"]["conectado"] is False
    assert all(r["conectado"] is False for r in unotv["redes"])
    assert unotv["total"] == {"seguidores": None, "posts_totales": None, "posts_dia": None}


def test_sin_api_key_todo_null(entorno, monkeypatch):
    _mock_postproxy(monkeypatch, api_key="")
    c = _cli_como("admin")
    cuerpo = c.get("/api/marcas").json()
    assert cuerpo["totales"] == {"seguidores": None, "posts_totales": None, "posts_dia": None}
    assert all(r["conectado"] is False for m in cuerpo["marcas"] for r in m["redes"])


# --------------------------------------------------------------------------- #
# CRUD del catálogo de marcas (fuente única editable)                          #
# --------------------------------------------------------------------------- #
def test_catalogo_editor_403(entorno):
    c = _cli_como("editor")
    assert c.get("/api/marcas/catalogo").status_code == 403
    assert c.post("/api/marcas/catalogo", json={"etiqueta": "X"}, headers=_ORIGIN).status_code == 403


def test_catalogo_crud(entorno, monkeypatch, tmp_path):
    from keni_shared import marcas as km

    monkeypatch.setenv("KENI_MARCAS_CONFIG", str(tmp_path / "marcas.toml"))
    km.recargar()
    try:
        c = _cli_como("admin")
        # GET inicial: la semilla (amx) mientras no haya overlay.
        r = c.get("/api/marcas/catalogo")
        assert r.status_code == 200
        assert "unotv" in [m["id"] for m in r.json()["marcas"]]

        # Crear: id/id_metricas auto-derivados de la etiqueta.
        r = c.post("/api/marcas/catalogo", json={"etiqueta": "Nueva Marca"}, headers=_ORIGIN)
        assert r.status_code == 201, r.text
        # `tipo` por defecto 'noticias' (una marca nueva pasa por investigación salvo que se diga lo contrario).
        assert r.json()["marca"] == {
            "id": "nueva-marca",
            "etiqueta": "Nueva Marca",
            "id_metricas": "nueva_marca",
            "tipo": "noticias",
            # Nombre del panel de investigación; "Noticias" por defecto.
            "etiqueta_investigacion": "Noticias",
        }
        # El catálogo (vivo) ya la incluye.
        assert km.es_marca("nueva-marca")
        assert "nueva-marca" in [m["id"] for m in c.get("/api/marcas/catalogo").json()["marcas"]]

        # Duplicado: 409.
        assert c.post("/api/marcas/catalogo", json={"etiqueta": "UnoTV", "id": "unotv"}, headers=_ORIGIN).status_code == 409

        # Editar la etiqueta. El `tipo` se PRESERVA al no tocarlo (round-trip no lo borra).
        r = c.put("/api/marcas/catalogo/nueva-marca", json={"etiqueta": "Renombrada"}, headers=_ORIGIN)
        assert r.status_code == 200 and r.json()["marca"]["etiqueta"] == "Renombrada"
        assert r.json()["marca"]["tipo"] == "noticias"
        assert km.etiqueta_de("nueva-marca") == "Renombrada"

        # Cambiar el tipo a contenido propio (se salta la investigación).
        r = c.put("/api/marcas/catalogo/nueva-marca", json={"tipo": "propio"}, headers=_ORIGIN)
        assert r.status_code == 200 and r.json()["marca"]["tipo"] == "propio"
        assert not km.es_noticias("nueva-marca")

        # Nombre del panel (etiqueta_investigacion): se fija y se PRESERVA en un round-trip que no lo toca.
        r = c.put(
            "/api/marcas/catalogo/nueva-marca",
            json={"etiqueta_investigacion": "Curiosidades"},
            headers=_ORIGIN,
        )
        assert r.status_code == 200 and r.json()["marca"]["etiqueta_investigacion"] == "Curiosidades"
        assert km.marca_de("nueva-marca").etiqueta_investigacion == "Curiosidades"
        r = c.put("/api/marcas/catalogo/nueva-marca", json={"etiqueta": "Otra Vez"}, headers=_ORIGIN)
        assert r.json()["marca"]["etiqueta_investigacion"] == "Curiosidades"

        # Borrar.
        assert c.delete("/api/marcas/catalogo/nueva-marca", headers=_ORIGIN).status_code == 200
        assert not km.es_marca("nueva-marca")
        assert c.delete("/api/marcas/catalogo/no-existe", headers=_ORIGIN).status_code == 404
    finally:
        km.recargar()


def test_catalogo_sin_data_dir_no_persiste(entorno, monkeypatch):
    """Sin almacenamiento configurado (ni KENI_MARCAS_CONFIG ni KENI_DATA_DIR): 503 al crear."""
    from keni_shared import marcas as km

    monkeypatch.delenv("KENI_MARCAS_CONFIG", raising=False)
    monkeypatch.delenv("KENI_DATA_DIR", raising=False)
    km.recargar()
    try:
        c = _cli_como("admin")
        r = c.post("/api/marcas/catalogo", json={"etiqueta": "X"}, headers=_ORIGIN)
        assert r.status_code == 503
    finally:
        km.recargar()
