"""Tests de la app: montaje de la API, fallback del SPA, assets y bind 127.0.0.1.

El SPA aun no esta construido en este worktree, asi que probamos tanto el
placeholder (sin build) como un `webapp/index.html` temporal (con build).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette.testclient import TestClient

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
        "/api/ajustes",
        "/api/proyectos",
        "/api/carpetas",
        "/api/texto",
        "/api/contenido",
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


@pytest.fixture
def sin_build(monkeypatch, tmp_path):
    """Simula que el SPA aún NO está compilado: webapp/ existe pero sin index.html.

    Asi probamos el placeholder de forma determinista, exista o no el bundle real
    versionado en el paquete (tras el merge y en CI, webapp/index.html SI existe).
    """
    vacio = tmp_path / "webapp-vacio"
    (vacio / "assets").mkdir(parents=True)
    monkeypatch.setattr(app_modulo, "_DIR_WEBAPP", vacio)
    monkeypatch.setattr(app_modulo, "_INDICE_SPA", vacio / "index.html")
    monkeypatch.setattr(app_modulo, "_DIR_ASSETS", vacio / "assets")
    return vacio


def test_raiz_sin_build_devuelve_placeholder(entorno, sin_build):
    c = _cliente()
    r = c.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "La interfaz aún no está construida" in r.text


def test_ruta_cualquiera_no_api_devuelve_placeholder(entorno, sin_build):
    """Cualquier ruta que no sea /api ni /assets cae al fallback del SPA."""
    c = _cliente()
    r = c.get("/tareas")  # antes era una pagina; ahora la enruta el SPA
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


def test_bind_default_localhost(monkeypatch):
    """Sin `KENI_CONSOLA_HOST`, el bind por defecto sigue siendo 127.0.0.1 (local)."""
    import importlib

    from keni_consola import __main__ as entry

    monkeypatch.delenv("KENI_CONSOLA_HOST", raising=False)
    importlib.reload(entry)
    try:
        assert entry.HOST == "127.0.0.1"
    finally:
        monkeypatch.delenv("KENI_CONSOLA_HOST", raising=False)
        importlib.reload(entry)


def test_bind_configurable_por_env(monkeypatch):
    """`KENI_CONSOLA_HOST` cambia el bind (en contenedor se pone 0.0.0.0 tras un proxy)."""
    import importlib

    from keni_consola import __main__ as entry

    monkeypatch.setenv("KENI_CONSOLA_HOST", "0.0.0.0")
    importlib.reload(entry)
    try:
        assert entry.HOST == "0.0.0.0"
    finally:
        monkeypatch.delenv("KENI_CONSOLA_HOST", raising=False)
        importlib.reload(entry)


def test_puerto_configurable_por_env(monkeypatch):
    from keni_consola import __main__ as entry

    monkeypatch.setenv("KENI_CONSOLA_PORT", "9123")
    assert entry._puerto() == 9123
    monkeypatch.setenv("KENI_CONSOLA_PORT", "no-numero")
    assert entry._puerto() == entry.PUERTO_DEF


# --------------------------------------------------------------------------- #
# Healthcheck de liveness: 200 SIN credencial y NO cae al SPA                   #
# --------------------------------------------------------------------------- #


def test_healthz_responde_200_sin_credencial(entorno):
    """`/healthz` responde 200 JSON simple SIN token (lo deja pasar el middleware)."""
    from .conftest import TOKEN_PRUEBA

    # Cliente que NO manda credencial: la liveness no la exige.
    c = TestClient(app_modulo.crear_app(token=TOKEN_PRUEBA))
    r = c.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"estado": "ok"}


def test_healthz_no_cae_al_spa(entorno, sin_build):
    """`/healthz` es su propia ruta (JSON), no el fallback del SPA (placeholder HTML)."""
    c = _cliente()
    r = c.get("/healthz")
    assert r.status_code == 200
    assert "application/json" in r.headers["content-type"]
    assert "La interfaz aún no está construida" not in r.text


def test_landing_es_la_raiz():
    """La URL de landing pasa a ser la raiz (la SPA), no /proyectos."""
    import keni_consola.__main__ as entry

    fuente = Path(entry.__file__).read_text(encoding="utf-8")
    assert 'f"http://{host_url}:{puerto}/"' in fuente


# --------------------------------------------------------------------------- #
# #150: el arranque NO emite el token en la URL ni en el log/stdout            #
# --------------------------------------------------------------------------- #


def _arrancar_capturando(monkeypatch, capsys):
    """Corre `main()` con uvicorn/hilos/SPA mockeados; devuelve (stdout, url_navegador, token)."""
    from keni_consola import __main__ as entry

    abierto: dict[str, str] = {}
    # uvicorn.run BLOQUEA: lo neutralizamos para que `main()` retorne en los tests.
    monkeypatch.setattr(entry.uvicorn, "run", lambda *a, **k: None)
    # webbrowser.open: capturamos la URL que se abriria (no debe llevar el token, #150).
    monkeypatch.setattr(entry.webbrowser, "open", lambda u: abierto.setdefault("url", u))
    # Los hilos de fondo (captura/programador/worker) no deben arrancar en el test.
    import keni_consola.comercial as comercial
    import keni_consola.programador as programador
    import keni_consola.worker as worker

    monkeypatch.setattr(comercial, "iniciar_captura_programada", lambda: None)
    monkeypatch.setattr(programador, "iniciar_programador", lambda: None)
    monkeypatch.setattr(worker, "iniciar_worker_inproceso", lambda: None)
    # `entry.main()` arranca ~19 daemons de fondo. Si sus BUCLES barren la BD compartida, los
    # hilos se filtran de este test al resto de la suite y contaminan ~40 tests (y agotan el
    # pool). Stubear cada `iniciar_*` ROTA cada vez que añaden uno (ya pasó: scanner, noticias…).
    # En vez de eso neutralizamos el bucle común de los daemons gateados (`daemon_util.bucle_gateado`,
    # 15 de ellos) + los 2 de refresco de métricas que NO lo usan: los hilos arrancan pero su
    # bucle es un no-op (no barren, no contaminan). Rot-proof y sin tocar `threading`.
    import keni_consola.daemon_util as daemon_util
    import keni_consola.metricas_piezas_refresco as metricas_piezas_refresco
    import keni_consola.metricas_refresco as metricas_refresco

    monkeypatch.setattr(daemon_util, "bucle_gateado", lambda *a, **k: None)
    monkeypatch.setattr(metricas_refresco, "iniciar_refresco_metricas", lambda: None)
    monkeypatch.setattr(metricas_piezas_refresco, "iniciar_refresco_piezas", lambda: None)
    # No construimos la app real (toca disco/BD): un stub basta para este test.
    monkeypatch.setattr(entry, "crear_app", lambda token=None: object())

    entry.main()
    salida = capsys.readouterr().out
    from keni_consola import seguridad

    token, _ = seguridad.resolver_token()
    return salida, abierto.get("url", ""), token


def test_arranque_no_imprime_token_ni_lo_pone_en_la_url(entorno, monkeypatch, capsys):
    """#150: con token FIJO, ni el stdout ni la URL del navegador contienen el token."""
    monkeypatch.setenv("KENI_CONSOLA_TOKEN", "token-secreto-de-mantenimiento-xyz")
    salida, url, token = _arrancar_capturando(monkeypatch, capsys)
    assert token == "token-secreto-de-mantenimiento-xyz"
    # El token NO aparece en el stdout del arranque...
    assert token not in salida
    # ...ni en la URL que se abre en el navegador (sin `?token=`).
    assert "?token=" not in url
    assert token not in url


def test_arranque_token_generado_no_se_filtra(entorno, monkeypatch, capsys):
    """#150: sin KENI_CONSOLA_TOKEN se genera uno, pero NO se imprime ni va en la URL."""
    monkeypatch.delenv("KENI_CONSOLA_TOKEN", raising=False)
    salida, url, _token = _arrancar_capturando(monkeypatch, capsys)
    assert "?token=" not in url
    assert "?token=" not in salida
    # Se avisa de que se genero un token de mantenimiento, sin revelar su valor.
    assert "mantenimiento" in salida.lower()


def test_lanzador_no_macos_devuelve_aviso(monkeypatch):
    from keni_consola import lanzador

    monkeypatch.setattr(lanzador.sys, "platform", "linux")
    mensaje = lanzador.abrir_en_claude_code(Path("/tmp/x"))
    assert "macos" in mensaje.lower()
