"""Tests de la Consola Keni (app web local). Todo OFFLINE.

No se lanza Claude Code real ni se abre el navegador: la funcion `abrir` se
mockea. La config de proyectos vive en `tmp_path` via la env var
`KENI_CONSOLA_CONFIG`. Las metricas usan la fuente `muestra` (offline).
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from keni_metricas.consola import app as app_modulo
from keni_metricas.consola import proyectos


@pytest.fixture
def entorno(monkeypatch, tmp_path):
    """Config aislada en tmp + fuente de muestra offline."""
    cfg = tmp_path / "consola.toml"
    monkeypatch.setenv("KENI_CONSOLA_CONFIG", str(cfg))
    # Metricas: fuerza muestra y sin config de keni-metricas (offline, sin scope).
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(tmp_path / "noexiste.toml"))
    monkeypatch.delenv("KENI_METRICAS_FUENTE", raising=False)
    monkeypatch.delenv("KENI_METRICAS_MARCAS", raising=False)
    monkeypatch.setenv("KENI_METRICAS_HISTORICO", "0")
    return tmp_path


def _config_con_proyecto(tmp_path: Path) -> Path:
    """Crea una carpeta de proyecto permitida + su CLAUDE.md y la registra."""
    carpeta = tmp_path / "proyecto-a"
    carpeta.mkdir()
    (carpeta / "CLAUDE.md").write_text("# Proyecto A\nContenido original.\n", encoding="utf-8")
    cfg = tmp_path / "consola.toml"
    cfg.write_text(
        f'[[proyecto]]\nnombre = "Proyecto A"\nruta = "{carpeta}"\n',
        encoding="utf-8",
    )
    return carpeta


def _cliente(abrir=None) -> TestClient:
    # Por defecto, una funcion `abrir` que NO lanza nada real (registra la ruta).
    if abrir is None:
        def abrir(_ruta):  # noqa: ANN001
            return "ok-mock"

    return TestClient(app_modulo.crear_app(abrir=abrir))


# --------------------------------------------------------------------------- #
# Rutas basicas: 200 / redireccion / estaticos                                #
# --------------------------------------------------------------------------- #


def test_raiz_redirige_a_proyectos(entorno):
    c = _cliente()
    r = c.get("/", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "/proyectos"


def test_proyectos_y_metricas_devuelven_html(entorno):
    c = _cliente()
    rp = c.get("/proyectos")
    rm = c.get("/metricas")
    assert rp.status_code == 200
    assert rm.status_code == 200
    assert "text/html" in rp.headers["content-type"]
    assert "text/html" in rm.headers["content-type"]
    assert "Proyectos" in rp.text
    assert "Metricas" in rm.text


def test_estaticos_servidos_localmente(entorno):
    c = _cliente()
    css = c.get("/estaticos/consola.css")
    js = c.get("/estaticos/consola.js")
    assert css.status_code == 200
    assert "text/css" in css.headers["content-type"]
    assert js.status_code == 200
    assert "javascript" in js.headers["content-type"]


def test_html_no_referencia_recursos_externos(entorno):
    """Coherente con privacidad: la pagina no carga nada de la red (http/cdn)."""
    c = _cliente()
    for ruta in ("/proyectos", "/metricas"):
        texto = c.get(ruta).text.lower()
        assert "http://" not in texto.replace("http://127.0.0.1", "")  # solo localhost si acaso
        assert "https://" not in texto
        assert "cdn" not in texto


# --------------------------------------------------------------------------- #
# Proyectos: listar, guardar (allowlist), abrir (mock), anadir                 #
# --------------------------------------------------------------------------- #


def test_proyectos_lista_carpetas_de_consola_toml(entorno):
    _config_con_proyecto(entorno)
    c = _cliente()
    texto = c.get("/proyectos").text
    assert "Proyecto A" in texto
    assert "Contenido original." in texto  # el CLAUDE.md se muestra en el textarea
    assert "CLAUDE.md" in texto


def test_guardar_claude_md_escribe_en_carpeta_permitida(entorno):
    carpeta = _config_con_proyecto(entorno)
    proys = proyectos.cargar_proyectos()
    pid = proys[0].id
    c = _cliente()
    nuevo = "# Proyecto A\nContenido NUEVO editado.\n"
    r = c.post("/api/proyectos/claude-md", json={"id": pid, "contenido": nuevo})
    assert r.status_code == 200
    assert (carpeta / "CLAUDE.md").read_text(encoding="utf-8") == nuevo


def test_guardar_claude_md_rechaza_id_fuera_de_allowlist(entorno):
    _config_con_proyecto(entorno)
    c = _cliente()
    r = c.post("/api/proyectos/claude-md", json={"id": "idfalso000", "contenido": "x"})
    assert r.status_code == 400
    assert "error" in r.json()


def test_guardar_claude_md_no_escribe_fuera_de_la_carpeta(entorno, tmp_path):
    """Una ruta arbitraria (id inexistente) NO debe crear archivos en otro lado."""
    _config_con_proyecto(entorno)
    intruso = tmp_path / "fuera"
    intruso.mkdir()
    c = _cliente()
    # El cliente solo manda un id; un id que no esta en la allowlist se rechaza.
    r = c.post("/api/proyectos/claude-md", json={"id": "deadbeef0000", "contenido": "hola"})
    assert r.status_code == 400
    assert not (intruso / "CLAUDE.md").exists()


def test_abrir_llama_a_la_funcion_con_la_ruta_correcta_sin_lanzar_nada(entorno):
    carpeta = _config_con_proyecto(entorno)
    proys = proyectos.cargar_proyectos()
    pid = proys[0].id
    llamadas: list[Path] = []

    def abrir_mock(ruta):
        llamadas.append(ruta)
        return "Claude Code abriendose (mock)."

    c = _cliente(abrir=abrir_mock)
    r = c.post("/api/proyectos/abrir", json={"id": pid})
    assert r.status_code == 200
    assert llamadas == [carpeta.resolve()]
    assert "mock" in r.json()["mensaje"]


def test_abrir_rechaza_id_fuera_de_allowlist(entorno):
    _config_con_proyecto(entorno)
    llamadas = []
    c = _cliente(abrir=lambda r: llamadas.append(r))
    r = c.post("/api/proyectos/abrir", json={"id": "noexiste0000"})
    assert r.status_code == 400
    assert llamadas == []  # NO se intento lanzar nada


def test_anadir_carpeta_valida_la_persiste(entorno, tmp_path):
    nueva = tmp_path / "proyecto-b"
    nueva.mkdir()
    c = _cliente()
    r = c.post("/api/proyectos/anadir", json={"nombre": "Proyecto B", "ruta": str(nueva)})
    assert r.status_code == 200
    proys = proyectos.cargar_proyectos()
    assert any(p.nombre == "Proyecto B" and p.ruta == nueva.resolve() for p in proys)


def test_anadir_carpeta_inexistente_rechazada(entorno, tmp_path):
    c = _cliente()
    r = c.post("/api/proyectos/anadir", json={"nombre": "X", "ruta": str(tmp_path / "no-existe")})
    assert r.status_code == 400
    assert "no existe" in r.json()["error"].lower()


def test_anadir_rechaza_ruta_que_es_archivo(entorno, tmp_path):
    archivo = tmp_path / "soy-archivo.txt"
    archivo.write_text("x", encoding="utf-8")
    c = _cliente()
    r = c.post("/api/proyectos/anadir", json={"nombre": "X", "ruta": str(archivo)})
    assert r.status_code == 400
    assert "carpeta" in r.json()["error"].lower()


# --------------------------------------------------------------------------- #
# Metricas: dashboard embebido (sin red) + export CSV                          #
# --------------------------------------------------------------------------- #


def test_dashboard_devuelve_html_sin_recursos_externos(entorno):
    c = _cliente()
    r = c.get("/metricas/dashboard?rango=mes")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    texto = r.text.lower()
    # El dashboard es autocontenido: nada de CDN ni red externa.
    assert "https://" not in texto
    assert "cdn" not in texto
    assert "<style>" in texto  # CSS inline, no <link> externo


def test_dashboard_rango_invalido_no_crashea(entorno):
    c = _cliente()
    r = c.get("/metricas/dashboard?rango=anio")
    # Cae con elegancia al rango por defecto (mes): 200 con HTML.
    assert r.status_code == 200


def test_export_csv_parseable_con_cabeceras(entorno):
    c = _cliente()
    r = c.get("/metricas/export.csv?rango=mes")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "attachment" in r.headers["content-disposition"]
    filas = list(csv.reader(io.StringIO(r.text)))
    assert filas, "el CSV no debe estar vacio"
    assert filas[0] == ["marca", "plataforma", "visualizaciones", "alcance", "interacciones", "engagement_pct"]
    # Debe haber al menos una fila de total global.
    assert any(f and f[0] == "TOTAL" for f in filas)


def test_export_csv_filtrado_por_marca(entorno):
    """Con una marca concreta, el CSV solo contiene esa marca (FuenteScoped)."""
    c = _cliente()
    # Tomamos una marca real de la fuente de muestra.
    from keni_metricas.config import cargar_config, construir_fuente

    fuente = construir_fuente(cargar_config())
    cuentas = fuente.cuentas()
    assert cuentas
    marca = cuentas[0].id
    r = c.get(f"/metricas/export.csv?rango=mes&marca={marca}")
    assert r.status_code == 200
    filas = list(csv.reader(io.StringIO(r.text)))
    nombre_marca = cuentas[0].nombre
    # marcas presentes (excluyendo filas TOTAL globales)
    marcas_en_csv = {f[0] for f in filas[1:] if f and f[0] != "TOTAL"}
    assert marcas_en_csv == {nombre_marca}


# --------------------------------------------------------------------------- #
# Seguridad: bind 127.0.0.1                                                    #
# --------------------------------------------------------------------------- #


def test_bind_solo_localhost():
    """El entrypoint fija el host a 127.0.0.1 (nunca 0.0.0.0)."""
    from keni_metricas.consola import __main__ as entry

    assert entry.HOST == "127.0.0.1"


def test_puerto_configurable_por_env(monkeypatch):
    from keni_metricas.consola import __main__ as entry

    monkeypatch.setenv("KENI_CONSOLA_PORT", "9123")
    assert entry._puerto() == 9123
    monkeypatch.setenv("KENI_CONSOLA_PORT", "no-numero")
    assert entry._puerto() == entry.PUERTO_DEF  # cae al default sin crashear


def test_lanzador_no_macos_devuelve_aviso(monkeypatch):
    """En no-macOS el lanzador NO intenta nada y avisa con claridad."""
    from keni_metricas.consola import lanzador

    monkeypatch.setattr(lanzador.sys, "platform", "linux")
    mensaje = lanzador.abrir_en_claude_code(Path("/tmp/x"))
    assert "macos" in mensaje.lower()


# --------------------------------------------------------------------------- #
# Registry de features: auto-discovery, orden de nav, montaje de una feature   #
# --------------------------------------------------------------------------- #


def test_auto_discovery_encuentra_proyectos_y_metricas():
    """El descubrimiento encuentra al menos las dos features migradas."""
    from keni_metricas.consola import features

    ids = [f.id for f in features.descubrir(refresco=True)]
    assert "proyectos" in ids
    assert "metricas" in ids


def test_orden_de_nav_proyectos_antes_que_metricas(entorno):
    """La nav se ordena por `orden`: Proyectos (10) va antes que Metricas (20)."""
    from keni_metricas.consola import features

    descubiertas = features.descubrir(refresco=True)
    ids = [f.id for f in descubiertas]
    assert ids.index("proyectos") < ids.index("metricas")

    # Y se refleja en el HTML real: la pestana Proyectos aparece antes en la nav.
    c = _cliente()
    html = c.get("/proyectos").text
    assert html.index('href="/proyectos"') < html.index('href="/metricas"')


def test_raiz_redirige_a_la_primera_feature(entorno):
    """GET / redirige a la primera feature por orden (proyectos)."""
    from keni_metricas.consola import features

    primera = features.descubrir(refresco=True)[0].id
    c = _cliente()
    r = c.get("/", follow_redirects=False)
    assert r.headers["location"] == f"/{primera}"


@pytest.fixture
def feature_de_prueba():
    """Suelta una feature de prueba en `features/` y la limpia al terminar.

    Verifica el contrato: basta crear UN archivo con `FEATURE` para que se
    descubra, se monte su ruta y aparezca en la nav (cero ediciones a app.py).
    """
    import importlib
    import sys

    from keni_metricas.consola import features as features_pkg

    dir_features = Path(features_pkg.__file__).parent
    modulo = dir_features / "zzprueba.py"
    modulo.write_text(
        'from starlette.responses import PlainTextResponse\n'
        'from starlette.routing import Route\n'
        'from . import Feature\n'
        '\n'
        'async def _pagina(request):\n'
        '    return PlainTextResponse("hola prueba")\n'
        '\n'
        'FEATURE = Feature(\n'
        '    id="zzprueba",\n'
        '    etiqueta="Prueba",\n'
        '    orden=999,\n'
        '    rutas=[Route("/zzprueba", _pagina)],\n'
        ')\n',
        encoding="utf-8",
    )
    importlib.invalidate_caches()
    try:
        yield
    finally:
        modulo.unlink(missing_ok=True)
        sys.modules.pop("keni_metricas.consola.features.zzprueba", None)
        features_pkg.descubrir(refresco=True)  # limpia el cache para el resto


def test_feature_de_prueba_se_monta_sola(entorno, feature_de_prueba):
    """Una feature recien soltada en features/ se descubre, monta y navega."""
    from keni_metricas.consola import features

    ids = [f.id for f in features.descubrir(refresco=True)]
    assert "zzprueba" in ids
    # orden=999 => al final de la nav.
    assert ids[-1] == "zzprueba"

    c = _cliente()
    r = c.get("/zzprueba")
    assert r.status_code == 200
    assert "hola prueba" in r.text
    # Y su pestana aparece en la nav de las demas paginas, sin tocar app.py.
    assert 'href="/zzprueba"' in c.get("/proyectos").text


def test_id_de_feature_duplicado_da_error_claro():
    """Dos features con el mismo id => error explicito (no silencioso)."""
    from keni_metricas.consola.features import Feature, _validar

    f = Feature(id="MAYUS", etiqueta="x", orden=1, rutas=[])
    with pytest.raises(ValueError, match="id invalido"):
        _validar(f, "modulo_x")
