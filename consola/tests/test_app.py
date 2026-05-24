"""Tests de la app: montaje de la API, fallback del SPA, assets y bind 127.0.0.1.

El SPA aun no esta construido en este worktree, asi que probamos tanto el
placeholder (sin build) como un `webapp/index.html` temporal (con build).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from keni_consola import api
from keni_consola import app as app_modulo

from .conftest import _cliente

# --------------------------------------------------------------------------- #
# Auto-descubrimiento de las rutas de la API                                   #
# --------------------------------------------------------------------------- #


def test_auto_descubrimiento_monta_todas_las_areas():
    rutas = api.descubrir(refresco=True)
    paths = {r.path for r in rutas}
    # Una ruta representativa de cada modulo de api/.
    for esperada in (
        "/api/estado",
        "/api/config",
        "/api/proyectos",
        "/api/carpetas",
        "/api/skills",
        "/api/tareas",
        "/api/metricas/reporte",
    ):
        assert esperada in paths


def test_modulo_api_de_prueba_se_monta_solo(entorno, tmp_path):
    """Una ruta soltada en api/ se descubre y monta, sin tocar app.py."""
    import importlib
    import sys

    dir_api = Path(api.__file__).parent
    modulo = dir_api / "zzprueba.py"
    modulo.write_text(
        "from starlette.responses import JSONResponse\n"
        "from starlette.routing import Route\n"
        "\n"
        "async def _ep(request):\n"
        "    return JSONResponse({'ok': True})\n"
        "\n"
        "RUTAS = [Route('/api/zzprueba', _ep)]\n",
        encoding="utf-8",
    )
    importlib.invalidate_caches()
    try:
        c = _cliente()
        r = c.get("/api/zzprueba")
        assert r.status_code == 200
        assert r.json() == {"ok": True}
    finally:
        modulo.unlink(missing_ok=True)
        sys.modules.pop("keni_consola.api.zzprueba", None)
        api.descubrir(refresco=True)


# --------------------------------------------------------------------------- #
# Fallback del SPA: sin build (placeholder) y con build (index.html temporal)  #
# --------------------------------------------------------------------------- #


def test_raiz_sin_build_devuelve_placeholder(cliente):
    r = cliente.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "La interfaz aún no está construida" in r.text


def test_ruta_cualquiera_no_api_devuelve_placeholder(cliente):
    """Cualquier ruta que no sea /api ni /assets cae al fallback del SPA."""
    r = cliente.get("/tareas")  # antes era una pagina; ahora la enruta el SPA
    assert r.status_code == 200
    assert "La interfaz aún no está construida" in r.text


def test_ruta_api_inexistente_no_cae_al_spa(cliente):
    """Una sub-ruta /api inexistente devuelve 404, no el HTML del SPA."""
    r = cliente.get("/api/no-existe-este-endpoint")
    assert r.status_code == 404


@pytest.fixture
def con_build(monkeypatch, tmp_path):
    """Crea un webapp/ temporal con index.html + un asset, apuntando la app a el."""
    webapp = tmp_path / "webapp"
    assets = webapp / "assets"
    assets.mkdir(parents=True)
    (webapp / "index.html").write_text(
        "<!DOCTYPE html><html><body><div id='root'>SPA REACT</div></body></html>",
        encoding="utf-8",
    )
    (assets / "app.js").write_text("console.log('hola');", encoding="utf-8")
    (assets / "app.css").write_text("body{margin:0}", encoding="utf-8")
    (webapp / "favicon.ico").write_bytes(b"\x00\x00fake-ico")
    monkeypatch.setattr(app_modulo, "_DIR_WEBAPP", webapp)
    monkeypatch.setattr(app_modulo, "_INDICE_SPA", webapp / "index.html")
    monkeypatch.setattr(app_modulo, "_DIR_ASSETS", assets)
    return webapp


def test_con_build_sirve_index_en_la_raiz(entorno, con_build):
    c = _cliente()
    r = c.get("/")
    assert r.status_code == 200
    assert "SPA REACT" in r.text


def test_con_build_fallback_devuelve_index_en_ruta_cliente(entorno, con_build):
    """Una ruta de enrutado en cliente devuelve el index (no 404)."""
    c = _cliente()
    r = c.get("/cualquier/ruta/del/spa")
    assert r.status_code == 200
    assert "SPA REACT" in r.text


def test_con_build_sirve_assets(entorno, con_build):
    c = _cliente()
    js = c.get("/assets/app.js")
    css = c.get("/assets/app.css")
    assert js.status_code == 200
    assert "javascript" in js.headers["content-type"]
    assert "console.log" in js.text
    assert css.status_code == 200
    assert "text/css" in css.headers["content-type"]


def test_con_build_sirve_favicon_suelto(entorno, con_build):
    c = _cliente()
    r = c.get("/favicon.ico")
    assert r.status_code == 200


def test_asset_inexistente_da_404(entorno, con_build):
    c = _cliente()
    r = c.get("/assets/no-existe.js")
    assert r.status_code == 404


def test_asset_path_traversal_rechazado(entorno, con_build, tmp_path):
    """Una ruta de asset con `..` no debe escapar de assets/ (404, no fuga)."""
    # Creamos un archivo secreto fuera de assets/ para confirmar que NO se sirve.
    secreto = tmp_path / "webapp" / "secreto.txt"
    secreto.write_text("no debe verse", encoding="utf-8")
    c = _cliente()
    r = c.get("/assets/../secreto.txt")
    # Starlette normaliza la ruta; en cualquier caso nunca se sirve el secreto.
    assert "no debe verse" not in r.text


# --------------------------------------------------------------------------- #
# Bind 127.0.0.1 + puerto configurable                                         #
# --------------------------------------------------------------------------- #


def test_bind_solo_localhost():
    from keni_consola import __main__ as entry

    assert entry.HOST == "127.0.0.1"


def test_puerto_configurable_por_env(monkeypatch):
    from keni_consola import __main__ as entry

    monkeypatch.setenv("KENI_CONSOLA_PORT", "9123")
    assert entry._puerto() == 9123
    monkeypatch.setenv("KENI_CONSOLA_PORT", "no-numero")
    assert entry._puerto() == entry.PUERTO_DEF


def test_landing_es_la_raiz():
    """La URL de landing pasa a ser la raiz (la SPA), no /proyectos."""
    import keni_consola.__main__ as entry

    fuente = Path(entry.__file__).read_text(encoding="utf-8")
    assert 'f"http://{HOST}:{puerto}/"' in fuente


def test_lanzador_no_macos_devuelve_aviso(monkeypatch):
    from keni_consola import lanzador

    monkeypatch.setattr(lanzador.sys, "platform", "linux")
    mensaje = lanzador.abrir_en_claude_code(Path("/tmp/x"))
    assert "macos" in mensaje.lower()
