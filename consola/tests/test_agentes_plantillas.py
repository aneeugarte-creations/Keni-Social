"""Plantillas de CLAUDE.md del dominio agentes (`agentes._plantillas`). OFFLINE.

Cubre el catalogo de plantillas, el render (sustitucion del nombre) y el fallback de
un id desconocido a la plantilla general.
"""

from __future__ import annotations

from keni_consola.agentes import _plantillas


def test_plantillas_disponibles_incluye_las_cinco():
    ids = {pid for pid, _etiqueta in _plantillas.plantillas_disponibles()}
    assert {"general", "noticias", "deportes", "podcast", "social"} <= ids


def test_todas_las_plantillas_renderizan_y_sustituyen_el_nombre():
    for pid, _etiqueta in _plantillas.plantillas_disponibles():
        texto = _plantillas.render_claude_md(pid, "Marca X")
        assert "# Marca X" in texto
        assert "{NOMBRE}" not in texto


def test_render_general_trae_la_cabecera_institucional():
    texto = _plantillas.render_claude_md("general", "mi-agente")
    assert "# mi-agente" in texto
    assert "Plantilla institucional de Keni AI" in texto


def test_render_noticias_es_de_marca_de_noticias():
    texto = _plantillas.render_claude_md("noticias", "Noticias X").lower()
    assert "marca de noticias" in texto
    assert "piramide invertida" in texto


def test_id_desconocido_cae_a_general():
    texto = _plantillas.render_claude_md("no-existe", "Cae")
    assert "# Cae" in texto
    assert "Plantilla institucional de Keni AI" in texto
