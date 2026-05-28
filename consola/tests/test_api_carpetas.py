"""Tests de la API Carpetas (/api/carpetas). OFFLINE.

La RAIZ permitida y el consola.toml viven en tmp (env vars); ningun test toca el
disco real. Mantiene TODA la validacion anti-escape de rutas.
"""

from __future__ import annotations

import pytest

from keni_consola import proyectos
from keni_consola.api import carpetas

from .conftest import _cliente


@pytest.fixture
def raiz(monkeypatch, tmp_path):
    """RAIZ permitida + consola.toml aislados en tmp; Postgres operacional aislado."""
    # La app llama `arrancar_persistencia` al crearse: exige `DATABASE_URL` (ADR 0004).
    from ._postgres import limpiar_postgres, requiere_postgres

    url_pg = requiere_postgres()
    limpiar_postgres(url_pg)
    monkeypatch.setenv("DATABASE_URL", url_pg)
    raiz = tmp_path / "keni-proyectos"
    raiz.mkdir()
    monkeypatch.setenv("KENI_CONSOLA_RAIZ", str(raiz))
    monkeypatch.setenv("KENI_CONSOLA_CONFIG", str(tmp_path / "consola.toml"))
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(tmp_path / "noexiste.toml"))
    try:
        yield raiz
    finally:
        limpiar_postgres(url_pg)


# --------------------------------------------------------------------------- #
# GET /api/carpetas (opciones)                                                #
# --------------------------------------------------------------------------- #


def test_get_opciones_contrato(raiz):
    datos = _cliente().get("/api/carpetas").json()
    assert set(datos) == {"raiz", "plantillas"}
    assert datos["raiz"] == str(raiz)
    ids = {p["id"] for p in datos["plantillas"]}
    assert {"general", "noticias", "deportes", "podcast", "social"} <= ids
    for p in datos["plantillas"]:
        assert set(p) == {"id", "nombre"}


# --------------------------------------------------------------------------- #
# POST /api/carpetas (crear)                                                  #
# --------------------------------------------------------------------------- #


def test_crear_general_crea_dir_md_y_registra(raiz):
    r = _cliente().post("/api/carpetas", json={"nombre": "mi-proyecto", "plantilla": "general"})
    assert r.status_code == 200
    assert "ruta" in r.json()
    carpeta = raiz / "mi-proyecto"
    assert carpeta.is_dir()
    contenido = (carpeta / "CLAUDE.md").read_text(encoding="utf-8")
    assert "# mi-proyecto" in contenido
    assert "{NOMBRE}" not in contenido
    assert "Plantilla institucional de Keni AI" in contenido
    proys = proyectos.cargar_proyectos()
    assert any(p.ruta == carpeta.resolve() for p in proys)


def test_crear_plantilla_noticias(raiz):
    r = _cliente().post("/api/carpetas", json={"nombre": "noticias-x", "plantilla": "noticias"})
    assert r.status_code == 200
    contenido = (raiz / "noticias-x" / "CLAUDE.md").read_text(encoding="utf-8")
    assert "marca de noticias" in contenido.lower()
    assert "piramide invertida" in contenido.lower()


def test_crear_plantilla_invalida_cae_a_general(raiz):
    r = _cliente().post("/api/carpetas", json={"nombre": "proj", "plantilla": "no-existe"})
    assert r.status_code == 200
    assert "# proj" in (raiz / "proj" / "CLAUDE.md").read_text(encoding="utf-8")


def test_todas_las_plantillas_renderizan(raiz):
    for pid, _etiqueta in carpetas.plantillas_disponibles():
        texto = carpetas.render_claude_md(pid, "Marca X")
        assert "# Marca X" in texto
        assert "{NOMBRE}" not in texto


def test_crear_duplicada_400(raiz):
    assert _cliente().post("/api/carpetas", json={"nombre": "dup", "plantilla": "general"}).status_code == 200
    r2 = _cliente().post("/api/carpetas", json={"nombre": "dup", "plantilla": "general"})
    assert r2.status_code == 400


def test_body_malformado_400(raiz):
    r = _cliente().post(
        "/api/carpetas", content=b"no-json", headers={"Content-Type": "application/json"}
    )
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Seguridad: SOLO dentro de la raiz permitida                                  #
# --------------------------------------------------------------------------- #


def test_crear_con_dotdot_rechazado(raiz, tmp_path):
    r = _cliente().post("/api/carpetas", json={"nombre": "../fuera", "plantilla": "general"})
    assert r.status_code == 400
    assert not (tmp_path / "fuera").exists()
    assert not (raiz.parent / "fuera").exists()


def test_dotdot_da_mensaje_de_escape(raiz):
    r = _cliente().post("/api/carpetas", json={"nombre": "../fuera", "plantilla": "general"})
    assert r.status_code == 400
    mensaje = r.json()["error"].lower()
    assert "salir de la carpeta base" in mensaje
    assert "caracteres no permitidos" not in mensaje


def test_crear_ruta_absoluta_rechazada(raiz, tmp_path):
    objetivo = tmp_path / "intruso"
    r = _cliente().post("/api/carpetas", json={"nombre": str(objetivo), "plantilla": "general"})
    assert r.status_code == 400
    assert not objetivo.exists()


def test_crear_subruta_anidada_rechazada(raiz):
    r = _cliente().post("/api/carpetas", json={"nombre": "a/b", "plantilla": "general"})
    assert r.status_code == 400
    assert not (raiz / "a").exists()


def test_crear_nombre_vacio_rechazado(raiz):
    r = _cliente().post("/api/carpetas", json={"nombre": "   ", "plantilla": "general"})
    assert r.status_code == 400


def test_crear_sin_nombre_rechazado(raiz):
    r = _cliente().post("/api/carpetas", json={"plantilla": "general"})
    assert r.status_code == 400


def test_resolver_destino_dentro_de_la_raiz(raiz):
    destino = carpetas.resolver_destino("ok")
    assert destino.is_relative_to(raiz)
    assert destino.name == "ok"


def test_resolver_destino_rechaza_escape(raiz):
    for malo in ("..", "../x", "a/../../b", "/abs", "~/x", "a:b"):
        with pytest.raises(carpetas.NombreInvalido):
            carpetas.resolver_destino(malo)
