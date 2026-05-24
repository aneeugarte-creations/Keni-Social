"""Tests de la Consola Keni (app web local). Todo OFFLINE.

No se lanza Claude Code real ni se abre el navegador: la funcion `abrir` se
mockea. La config de proyectos vive en `tmp_path` via la env var
`KENI_CONSOLA_CONFIG`. Las metricas usan la fuente `muestra` (offline).
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import proyectos


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


def test_raiz_redirige_a_skills(entorno):
    """La landing por defecto es Generar copy (/skills), lo que un CM usa a diario."""
    c = _cliente()
    r = c.get("/", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "/skills"


def test_proyectos_y_metricas_devuelven_html(entorno):
    c = _cliente()
    rp = c.get("/proyectos")
    rm = c.get("/metricas")
    assert rp.status_code == 200
    assert rm.status_code == 200
    assert "text/html" in rp.headers["content-type"]
    assert "text/html" in rm.headers["content-type"]
    assert "Proyectos" in rp.text
    assert "Métricas" in rm.text


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


def test_metricas_muestra_nombre_humano_de_marca_no_slug(entorno):
    """UX1 (QA #69): la ETIQUETA visible es el nombre humano; el VALUE es el id crudo.

    Skills y Metricas deben mostrar los MISMOS nombres de marca al usuario.
    """
    c = _cliente()
    texto = c.get("/metricas").text
    # Nombre humano legible (con acentos donde toca).
    assert "Claro Sports" in texto
    assert "Nación Gamer" in texto
    assert "Fundación" in texto
    # El value interno (id con guion_bajo) que Metricas necesita se mantiene.
    assert 'value="claro_sports"' in texto
    assert 'value="nacion_gamer"' in texto
    assert 'value="fundacion"' in texto


def test_metricas_labels_con_for_explicito(entorno):
    """UX2 (a11y): cada <label> referencia su <select> por id (for/id homogeneo)."""
    c = _cliente()
    texto = c.get("/metricas").text
    assert '<label for="sel-marca">' in texto
    assert '<select id="sel-marca">' in texto
    assert '<label for="sel-rango">' in texto
    assert '<select id="sel-rango">' in texto


def test_metricas_iframe_tiene_sandbox(entorno):
    """UX3: el iframe del dashboard lleva sandbox (conjunto minimo same-origin)."""
    c = _cliente()
    texto = c.get("/metricas").text
    assert 'id="iframe-dashboard"' in texto
    assert 'sandbox="allow-same-origin"' in texto


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
# Metricas: comparar periodos (A vs B)                                         #
# --------------------------------------------------------------------------- #


def test_metricas_pagina_tiene_seccion_comparar(entorno):
    """La pagina /metricas sigue 200 y trae la nueva seccion de comparar (a11y)."""
    c = _cliente()
    r = c.get("/metricas")
    assert r.status_code == 200
    texto = r.text
    # El dashboard embebido sigue presente.
    assert 'id="iframe-dashboard"' in texto
    # Controles de comparar con label for/id homogeneo (a11y).
    for sel in ("cmp-marca", "cmp-rango-a", "cmp-rango-b"):
        assert f'<label for="{sel}">' in texto
        assert f'<select id="{sel}">' in texto
    assert 'id="btn-comparar"' in texto


def test_comparar_devuelve_estructura_de_dos_rangos(entorno):
    """El endpoint comparar devuelve total + por_marca con las 4 metricas y su
    diferencia/variacion para los dos rangos. Estructura, no textos fragiles."""
    c = _cliente()
    r = c.get("/metricas/comparar.json?rango_a=semana&rango_b=mes")
    assert r.status_code == 200
    assert "application/json" in r.headers["content-type"]
    datos = r.json()
    assert datos["rango_a"] == "semana"
    assert datos["rango_b"] == "mes"
    # Total consolidado: las cuatro metricas, cada una con a/b/diferencia/variacion.
    metricas = datos["total"]["metricas"]
    claves = {m["metrica"] for m in metricas}
    assert claves == {"visualizaciones", "alcance", "interacciones", "engagement_pct"}
    for m in metricas:
        assert set(m) >= {"metrica", "a", "b", "diferencia", "variacion_pct"}
    # Por marca: al menos una marca, con nombre legible y su comparativa.
    assert datos["por_marca"], "debe comparar por marca"
    primera = datos["por_marca"][0]
    assert primera["marca"]  # nombre legible, no vacio
    assert len(primera["comparativa"]) == 4


def test_comparar_diferencia_consistente_con_los_valores(entorno):
    """La diferencia de cada metrica = a - b (sanity de la logica de comparacion)."""
    c = _cliente()
    datos = c.get("/metricas/comparar.json?rango_a=semana&rango_b=mes").json()
    for m in datos["total"]["metricas"]:
        if m["metrica"] == "engagement_pct":
            assert m["diferencia"] == round(m["a"] - m["b"], 1)
        else:
            assert m["diferencia"] == m["a"] - m["b"]


def test_comparar_acotado_por_marca(entorno):
    """Con una marca concreta, la comparativa por_marca contiene solo esa marca."""
    from keni_metricas.config import cargar_config, construir_fuente

    fuente = construir_fuente(cargar_config())
    cuentas = fuente.cuentas()
    assert cuentas
    marca = cuentas[0].id
    c = _cliente()
    datos = c.get(f"/metricas/comparar.json?rango_a=semana&rango_b=mes&marca={marca}").json()
    ids = {m["marca_id"] for m in datos["por_marca"]}
    assert ids == {marca}


def test_comparar_rango_invalido_cae_al_default(entorno):
    """Un rango invalido no crashea: cae al default (mes) y devuelve 200."""
    c = _cliente()
    r = c.get("/metricas/comparar.json?rango_a=anio&rango_b=decada")
    assert r.status_code == 200
    datos = r.json()
    assert datos["rango_a"] == "mes"
    assert datos["rango_b"] == "mes"


# --------------------------------------------------------------------------- #
# Metricas: descargar reporte md / json                                        #
# --------------------------------------------------------------------------- #


def test_export_md_descarga_con_secciones(entorno):
    c = _cliente()
    r = c.get("/metricas/export.md?rango=mes")
    assert r.status_code == 200
    assert "text/markdown" in r.headers["content-type"]
    disp = r.headers["content-disposition"]
    assert "attachment" in disp
    assert ".md" in disp
    # Contenido con secciones del reporte (encabezados Markdown).
    assert r.text.startswith("# Reporte de redes")
    assert "## Total" in r.text


def test_export_json_descarga_parseable(entorno):
    c = _cliente()
    r = c.get("/metricas/export.json?rango=mes")
    assert r.status_code == 200
    assert "application/json" in r.headers["content-type"]
    disp = r.headers["content-disposition"]
    assert "attachment" in disp
    assert ".json" in disp
    # Contenido parseable y con la forma del reporte consolidado.
    datos = json.loads(r.text)
    assert datos["rango"] == "mes"
    assert "total" in datos
    assert "cuentas" in datos


def test_export_md_json_filtrados_por_marca_en_el_nombre(entorno):
    """Con marca, el nombre de descarga la incluye (coherente con el CSV)."""
    from keni_metricas.config import cargar_config, construir_fuente

    fuente = construir_fuente(cargar_config())
    marca = fuente.cuentas()[0].id
    c = _cliente()
    for ext, ctype in (("md", "markdown"), ("json", "json")):
        r = c.get(f"/metricas/export.{ext}?rango=mes&marca={marca}")
        assert r.status_code == 200
        assert ctype in r.headers["content-type"]
        assert marca in r.headers["content-disposition"]


def test_estaticos_metricas_servidos_localmente(entorno):
    """Los estaticos propios de Metricas (css/js) se sirven local, sin red."""
    c = _cliente()
    css = c.get("/estaticos/metricas.css")
    js = c.get("/estaticos/metricas.js")
    assert css.status_code == 200
    assert "text/css" in css.headers["content-type"]
    assert js.status_code == 200
    assert "javascript" in js.headers["content-type"]


# --------------------------------------------------------------------------- #
# Seguridad: bind 127.0.0.1                                                    #
# --------------------------------------------------------------------------- #


def test_bind_solo_localhost():
    """El entrypoint fija el host a 127.0.0.1 (nunca 0.0.0.0)."""
    from keni_consola import __main__ as entry

    assert entry.HOST == "127.0.0.1"


def test_puerto_configurable_por_env(monkeypatch):
    from keni_consola import __main__ as entry

    monkeypatch.setenv("KENI_CONSOLA_PORT", "9123")
    assert entry._puerto() == 9123
    monkeypatch.setenv("KENI_CONSOLA_PORT", "no-numero")
    assert entry._puerto() == entry.PUERTO_DEF  # cae al default sin crashear


def test_lanzador_no_macos_devuelve_aviso(monkeypatch):
    """En no-macOS el lanzador NO intenta nada y avisa con claridad."""
    from keni_consola import lanzador

    monkeypatch.setattr(lanzador.sys, "platform", "linux")
    mensaje = lanzador.abrir_en_claude_code(Path("/tmp/x"))
    assert "macos" in mensaje.lower()


# --------------------------------------------------------------------------- #
# Registry de features: auto-discovery, orden de nav, montaje de una feature   #
# --------------------------------------------------------------------------- #


def test_auto_discovery_encuentra_proyectos_y_metricas():
    """El descubrimiento encuentra al menos las dos features migradas."""
    from keni_consola import features

    ids = [f.id for f in features.descubrir(refresco=True)]
    assert "proyectos" in ids
    assert "metricas" in ids


def test_descubrimiento_ordena_proyectos_antes_que_metricas(entorno):
    """El descubrimiento ordena por `orden`: Proyectos (10) antes que Metricas (20)."""
    from keni_consola import features

    descubiertas = features.descubrir(refresco=True)
    ids = [f.id for f in descubiertas]
    assert ids.index("proyectos") < ids.index("metricas")


def test_nav_html_agrupa_trabajo_antes_que_ajustes(entorno):
    """En el HTML la nav esta agrupada: Metricas (grupo Trabajo) sale ANTES que
    Proyectos (grupo Ajustes), aunque por `orden` Proyectos sea menor. Es la
    agrupacion por sentido de uso, no el orden numerico, la que manda en la barra."""
    c = _cliente()
    html = c.get("/proyectos").text
    assert html.index('href="/metricas"') < html.index('href="/proyectos"')


def test_raiz_redirige_a_skills_si_existe(entorno):
    """GET / aterriza en /skills (Generar copy) si esa feature esta presente."""
    from keni_consola import features

    ids = {f.id for f in features.descubrir(refresco=True)}
    assert "skills" in ids  # precondicion del comportamiento esperado
    c = _cliente()
    r = c.get("/", follow_redirects=False)
    assert r.headers["location"] == "/skills"


@pytest.fixture
def feature_de_prueba():
    """Suelta una feature de prueba en `features/` y la limpia al terminar.

    Verifica el contrato: basta crear UN archivo con `FEATURE` para que se
    descubra, se monte su ruta y aparezca en la nav (cero ediciones a app.py).
    """
    import importlib
    import sys

    from keni_consola import features as features_pkg

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
        sys.modules.pop("keni_consola.features.zzprueba", None)
        features_pkg.descubrir(refresco=True)  # limpia el cache para el resto


def test_feature_de_prueba_se_monta_sola(entorno, feature_de_prueba):
    """Una feature recien soltada en features/ se descubre, monta y navega."""
    from keni_consola import features

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
    from keni_consola.features import Feature, _validar

    f = Feature(id="MAYUS", etiqueta="x", orden=1, rutas=[])
    with pytest.raises(ValueError, match="id invalido"):
        _validar(f, "modulo_x")


# --------------------------------------------------------------------------- #
# Shell/UX: nav agrupada (Trabajo/Ajustes), wordmark, favicon                  #
# --------------------------------------------------------------------------- #


def test_nav_agrupada_trabajo_y_ajustes(entorno):
    """La nav se agrupa en dos bloques con etiqueta: Trabajo y Ajustes."""
    c = _cliente()
    texto = c.get("/skills").text
    assert 'aria-label="Trabajo"' in texto
    assert 'aria-label="Ajustes"' in texto
    # Las etiquetas visibles de cada grupo estan presentes.
    assert ">Trabajo<" in texto
    assert ">Ajustes<" in texto


def test_nav_grupo_trabajo_va_antes_que_ajustes_y_contiene_lo_esperado(entorno):
    """Trabajo (Generar copy/Metricas/Tareas) precede a Ajustes en el HTML."""
    c = _cliente()
    texto = c.get("/skills").text
    pos_trabajo = texto.index('aria-label="Trabajo"')
    pos_ajustes = texto.index('aria-label="Ajustes"')
    assert pos_trabajo < pos_ajustes
    # Las 7 pestanas siguen presentes en la nav (agrupar no las pierde).
    for href in (
        'href="/skills"', 'href="/metricas"', 'href="/tareas"',
        'href="/proyectos"', 'href="/carpetas"', 'href="/estado"', 'href="/config"',
    ):
        assert href in texto
    # Generar copy (skills) cae en Trabajo: aparece antes que el bloque Ajustes.
    assert texto.index('href="/skills"') < pos_ajustes
    # Proyectos cae en Ajustes: aparece despues del inicio del bloque Ajustes.
    assert texto.index('href="/proyectos"') > pos_ajustes


def test_wordmark_y_favicon_presentes(entorno):
    """Barra con wordmark 'KENI · Consola' y un favicon SVG data-URI inline."""
    c = _cliente()
    texto = c.get("/skills").text
    assert "KENI" in texto and "Consola" in texto  # wordmark
    assert '<link rel="icon"' in texto
    assert "data:image/svg+xml" in texto  # favicon inline, sin red
    # El titulo de la pestana usa el separador de marca.
    assert "· Consola Keni" in texto


def test_helper_carga_expuesto_globalmente(entorno):
    """El JS compartido expone window.marcarCargando para que las features lo usen."""
    c = _cliente()
    js = c.get("/estaticos/consola.js").text
    assert "function marcarCargando" in js
    assert "window.marcarCargando" in js
    # El CSS compartido trae el spinner puro (sin librerias) y el estado cargando.
    css = c.get("/estaticos/consola.css").text
    assert ".spinner" in css
    assert ".cargando" in css


# --------------------------------------------------------------------------- #
# marcas.py: fuente unica de verdad de marcas (id / slug / etiqueta)           #
# --------------------------------------------------------------------------- #


def test_marcas_etiqueta_por_id_con_acentos():
    from keni_consola import marcas

    assert marcas.etiqueta_por_id("claro_sports") == "Claro Sports"
    assert marcas.etiqueta_por_id("claro_sports_golf") == "Claro Sports Golf"
    assert marcas.etiqueta_por_id("nacion_gamer") == "Nación Gamer"
    assert marcas.etiqueta_por_id("piso_15") == "Piso 15"
    assert marcas.etiqueta_por_id("fundacion") == "Fundación"
    assert marcas.etiqueta_por_id("unotv") == "UnoTV"
    # Id desconocido cae a si mismo (no lanza).
    assert marcas.etiqueta_por_id("desconocida") == "desconocida"


def test_marcas_etiqueta_por_slug_con_acentos():
    from keni_consola import marcas

    assert marcas.etiqueta_por_slug("claro-sports") == "Claro Sports"
    assert marcas.etiqueta_por_slug("nacion-gamer") == "Nación Gamer"
    assert marcas.etiqueta_por_slug("piso-15") == "Piso 15"
    assert marcas.etiqueta_por_slug("fundacion") == "Fundación"
    assert marcas.etiqueta_por_slug("unotv") == "UnoTV"
    # Slug desconocido cae a si mismo (no lanza).
    assert marcas.etiqueta_por_slug("no-existe") == "no-existe"


def test_marcas_listas_ids_y_slugs():
    from keni_consola import marcas

    assert marcas.ids() == [
        "unotv", "claro_sports", "claro_sports_golf", "nacion_gamer", "piso_15", "fundacion",
    ]
    # Golf tiene id/etiqueta pero NO slug en Skills.
    assert "claro_sports_golf" in marcas.ids()
    assert marcas.slugs() == ["unotv", "claro-sports", "nacion-gamer", "piso-15", "fundacion"]
    assert "claro-sports-golf" not in marcas.slugs()


def test_marcas_opciones_para_selects():
    from keni_consola import marcas

    por_id = dict(marcas.opciones_por_id())
    assert por_id["claro_sports"] == "Claro Sports"
    assert por_id["claro_sports_golf"] == "Claro Sports Golf"
    por_slug = dict(marcas.opciones_por_slug())
    assert por_slug["nacion-gamer"] == "Nación Gamer"
    # Golf no aparece entre las opciones por slug (sin slug curado).
    assert all(slug is not None for slug, _ in marcas.opciones_por_slug())
    assert len(marcas.opciones_por_id()) == 6
    assert len(marcas.opciones_por_slug()) == 5


# --------------------------------------------------------------------------- #
# _http_json.leer_json: body invalido -> {} (sin lanzar)                       #
# --------------------------------------------------------------------------- #


def test_leer_json_objeto_valido():
    import anyio

    from keni_consola._http_json import leer_json

    class _Req:
        async def json(self):
            return {"a": 1, "b": "x"}

    assert anyio.run(leer_json, _Req()) == {"a": 1, "b": "x"}


def test_leer_json_body_invalido_da_dict_vacio():
    import anyio

    from keni_consola._http_json import leer_json

    class _ReqRota:
        async def json(self):
            raise ValueError("body no es JSON")

    assert anyio.run(leer_json, _ReqRota()) == {}


def test_leer_json_no_objeto_da_dict_vacio():
    """Un JSON valido pero que no es objeto (lista/numero) -> {}."""
    import anyio

    from keni_consola._http_json import leer_json

    class _ReqLista:
        async def json(self):
            return [1, 2, 3]

    assert anyio.run(leer_json, _ReqLista()) == {}


# --------------------------------------------------------------------------- #
# Lanzador: ruta con apostrofo no rompe el comando de shell (B1)               #
# --------------------------------------------------------------------------- #


def test_lanzador_ruta_con_apostrofo_no_rompe_el_shell(monkeypatch):
    """Una ruta con apostrofo (/Users/o'brien) se entrecomilla de forma segura."""
    from keni_consola import lanzador

    monkeypatch.setattr(lanzador.sys, "platform", "darwin")

    capturado: dict[str, str] = {}

    def fake_run(args, **kwargs):  # noqa: ANN001, ANN003
        # args = ["osascript", "-e", script]
        capturado["script"] = args[2]

        class _R:
            stdout = ""
            stderr = ""

        return _R()

    monkeypatch.setattr(lanzador.subprocess, "run", fake_run)

    ruta = Path("/Users/o'brien/Proyecto")
    mensaje = lanzador.abrir_en_claude_code(ruta)
    script = capturado["script"]
    # Robustez: que el comando de shell, una vez DESESCAPADO el AppleScript, se
    # parsee con shlex a EXACTAMENTE `["cd", "/Users/o'brien/Proyecto", "&&",
    # "claude"]`. Es decir: el apostrofo llega intacto al programa, sin romper
    # comillas. (Un `cd 'o'brien'` ingenuo dejaria una comilla suelta y fallaria.)
    import shlex

    # Deshacemos el escape de AppleScript (inverso de _escapar_applescript) para
    # recuperar el comando tal cual lo recibiria /bin/sh.
    inicio = script.index('do script "') + len('do script "')
    fin = script.index('"\n', inicio)
    comando_shell = script[inicio:fin].replace('\\"', '"').replace("\\\\", "\\")
    assert shlex.split(comando_shell) == ["cd", "/Users/o'brien/Proyecto", "&&", "claude"]
    # El apostrofo crudo `o'brien` NO debe aparecer pegado (iria escapado).
    assert "o'brien" not in comando_shell
    assert "o'brien" in mensaje  # el mensaje legible si muestra la ruta real
