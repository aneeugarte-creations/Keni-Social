"""Tests de la feature Carpetas de la Consola Keni. Todo OFFLINE.

La RAIZ permitida y el consola.toml viven en `tmp_path` (env vars), de modo que
ningun test toca el disco real del usuario. No se lanza nada externo ni hay red.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import proyectos
from keni_consola.features import carpetas


@pytest.fixture
def entorno(monkeypatch, tmp_path):
    """RAIZ permitida + consola.toml aislados en tmp (offline)."""
    raiz = tmp_path / "keni-proyectos"
    raiz.mkdir()
    cfg = tmp_path / "consola.toml"
    monkeypatch.setenv("KENI_CONSOLA_RAIZ", str(raiz))
    monkeypatch.setenv("KENI_CONSOLA_CONFIG", str(cfg))
    # Metricas offline (otras features que monta la app no deben tocar red).
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(tmp_path / "noexiste.toml"))
    monkeypatch.delenv("KENI_METRICAS_FUENTE", raising=False)
    monkeypatch.delenv("KENI_METRICAS_MARCAS", raising=False)
    monkeypatch.setenv("KENI_METRICAS_HISTORICO", "0")
    return raiz


def _cliente() -> TestClient:
    def abrir(_ruta):  # noqa: ANN001 -- mock: nunca se lanza nada real
        return "ok-mock"

    return TestClient(app_modulo.crear_app(abrir=abrir))


# --------------------------------------------------------------------------- #
# UI: GET /carpetas                                                            #
# --------------------------------------------------------------------------- #


def test_pagina_carpetas_200_y_lista_plantillas(entorno):
    c = _cliente()
    r = c.get("/carpetas")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    texto = r.text
    # El formulario y las etiquetas de plantilla aparecen en la pagina.
    assert "form-carpetas" in texto
    for _pid, etiqueta in carpetas.plantillas_disponibles():
        assert etiqueta in texto
    # Muestra la raiz permitida para que el equipo sepa donde se crea.
    assert str(entorno) in texto


def test_carpetas_des_jerga_plantilla_de_contexto(entorno):
    """Des-jerga: la UI dice 'Plantilla de contexto', no 'Plantilla de CLAUDE.md'.

    Comprobamos el <main> de la pagina (no la nav, cuyos title= vienen de otras
    features que no editamos)."""
    texto = _cliente().get("/carpetas").text
    main = texto[texto.index("<main") : texto.index("</main>")]
    assert "Plantilla de contexto" in main
    assert "CLAUDE.md" not in main  # nada de jerga del archivo de contexto en la pagina
    assert "Plantilla de CLAUDE.md" not in texto
    # Acentos correctos en textos de usuario.
    assert "después" in main


def test_carpetas_body_malformado_da_400_sin_crashear(entorno):
    """Con `leer_json`, un body no-JSON se trata como vacio => falta nombre => 400."""
    r = _cliente().post(
        "/api/carpetas/crear", content=b"no-json", headers={"Content-Type": "application/json"}
    )
    assert r.status_code == 400
    assert "error" in r.json()


def test_carpetas_aparece_en_la_nav(entorno):
    """La pestana se auto-descubre y sale en la nav de otras paginas."""
    from keni_consola import features

    ids = [f.id for f in features.descubrir(refresco=True)]
    assert "carpetas" in ids
    c = _cliente()
    assert 'href="/carpetas"' in c.get("/proyectos").text


def test_carpetas_sin_recursos_externos(entorno):
    c = _cliente()
    texto = c.get("/carpetas").text.lower()
    assert "https://" not in texto
    assert "cdn" not in texto
    assert "http://" not in texto.replace("http://127.0.0.1", "")


def test_estaticos_de_carpetas_servidos(entorno):
    c = _cliente()
    css = c.get("/estaticos/carpetas.css")
    js = c.get("/estaticos/carpetas.js")
    assert css.status_code == 200
    assert "text/css" in css.headers["content-type"]
    assert js.status_code == 200
    assert "javascript" in js.headers["content-type"]


# --------------------------------------------------------------------------- #
# Crear: dir + CLAUDE.md de plantilla + registro en consola.toml               #
# --------------------------------------------------------------------------- #


def test_crear_carpeta_general_crea_dir_md_y_registra(entorno):
    c = _cliente()
    r = c.post("/api/carpetas/crear", json={"nombre": "mi-proyecto", "plantilla": "general"})
    assert r.status_code == 200

    carpeta = entorno / "mi-proyecto"
    assert carpeta.is_dir()
    md = carpeta / "CLAUDE.md"
    assert md.is_file()
    contenido = md.read_text(encoding="utf-8")
    # El nombre sustituye al marcador {NOMBRE} y el texto es la plantilla general.
    assert "# mi-proyecto" in contenido
    assert "{NOMBRE}" not in contenido
    assert "Plantilla institucional de Keni AI" in contenido

    # Quedo registrado en la allowlist (consola.toml) reutilizando proyectos.
    proys = proyectos.cargar_proyectos()
    assert any(p.ruta == carpeta.resolve() for p in proys)


def test_crear_carpeta_usa_plantilla_de_noticias(entorno):
    c = _cliente()
    r = c.post("/api/carpetas/crear", json={"nombre": "noticias-x", "plantilla": "noticias"})
    assert r.status_code == 200
    contenido = (entorno / "noticias-x" / "CLAUDE.md").read_text(encoding="utf-8")
    # Texto especifico de la plantilla de noticias.
    assert "marca de noticias" in contenido.lower()
    assert "piramide invertida" in contenido.lower()


def test_crear_carpeta_plantilla_invalida_cae_a_general(entorno):
    """Una plantilla desconocida no rompe: cae a la general (defensivo)."""
    c = _cliente()
    r = c.post("/api/carpetas/crear", json={"nombre": "proj", "plantilla": "no-existe"})
    assert r.status_code == 200
    contenido = (entorno / "proj" / "CLAUDE.md").read_text(encoding="utf-8")
    assert "# proj" in contenido


def test_todas_las_plantillas_se_renderizan(entorno):
    """Cada plantilla declarada existe en disco y se renderiza sin marcador."""
    for pid, _etiqueta in carpetas.plantillas_disponibles():
        texto = carpetas.render_claude_md(pid, "Marca X")
        assert "# Marca X" in texto
        assert "{NOMBRE}" not in texto


def test_crear_carpeta_duplicada_rechazada(entorno):
    c = _cliente()
    r1 = c.post("/api/carpetas/crear", json={"nombre": "dup", "plantilla": "general"})
    assert r1.status_code == 200
    r2 = c.post("/api/carpetas/crear", json={"nombre": "dup", "plantilla": "general"})
    assert r2.status_code == 400
    assert "error" in r2.json()


# --------------------------------------------------------------------------- #
# Seguridad: SOLO dentro de la raiz permitida                                  #
# --------------------------------------------------------------------------- #


def test_crear_fuera_de_la_raiz_con_dotdot_rechazado(entorno, tmp_path):
    """Un nombre con `..` no debe crear nada fuera de la raiz."""
    c = _cliente()
    r = c.post("/api/carpetas/crear", json={"nombre": "../fuera", "plantilla": "general"})
    assert r.status_code == 400
    assert "error" in r.json()
    assert not (tmp_path / "fuera").exists()
    assert not (entorno.parent / "fuera").exists()


def test_dotdot_da_mensaje_claro_de_escape_no_de_caracteres(entorno):
    """UX5 (QA #69): un intento con `..` explica que no se permite salir de la
    carpeta base, ANTES que el mensaje generico de caracteres (y sigue 400)."""
    c = _cliente()
    r = c.post("/api/carpetas/crear", json={"nombre": "../fuera", "plantilla": "general"})
    assert r.status_code == 400
    mensaje = r.json()["error"].lower()
    assert "salir de la carpeta base" in mensaje
    assert ".." in r.json()["error"]
    # No es el mensaje generico de caracteres prohibidos.
    assert "caracteres no permitidos" not in mensaje


def test_resolver_destino_dotdot_da_mensaje_de_escape(entorno):
    """`resolver_destino('../x')` lanza el mensaje de escape, no el de caracteres."""
    with pytest.raises(carpetas.NombreInvalido, match="salir de la carpeta base"):
        carpetas.resolver_destino("../x")


def test_crear_con_ruta_absoluta_rechazado(entorno, tmp_path):
    """Una ruta absoluta no debe crear nada fuera de la raiz."""
    objetivo = tmp_path / "intruso"
    c = _cliente()
    r = c.post("/api/carpetas/crear", json={"nombre": str(objetivo), "plantilla": "general"})
    assert r.status_code == 400
    assert not objetivo.exists()


def test_crear_con_subruta_anidada_rechazada(entorno):
    """Separadores de ruta en el nombre se rechazan (solo nombre simple)."""
    c = _cliente()
    r = c.post("/api/carpetas/crear", json={"nombre": "a/b", "plantilla": "general"})
    assert r.status_code == 400
    assert not (entorno / "a").exists()


def test_crear_nombre_vacio_rechazado(entorno):
    c = _cliente()
    r = c.post("/api/carpetas/crear", json={"nombre": "   ", "plantilla": "general"})
    assert r.status_code == 400
    assert "error" in r.json()


def test_crear_sin_nombre_rechazado(entorno):
    c = _cliente()
    r = c.post("/api/carpetas/crear", json={"plantilla": "general"})
    assert r.status_code == 400


def test_resolver_destino_dentro_de_la_raiz(entorno):
    """La ruta resuelta de un nombre valido cae dentro de la raiz permitida."""
    destino = carpetas.resolver_destino("ok")
    assert destino.is_relative_to(entorno)
    assert destino.name == "ok"


def test_resolver_destino_rechaza_escape(entorno):
    for malo in ("..", "../x", "a/../../b", "/abs", "~/x", "a:b"):
        with pytest.raises(carpetas.NombreInvalido):
            carpetas.resolver_destino(malo)
