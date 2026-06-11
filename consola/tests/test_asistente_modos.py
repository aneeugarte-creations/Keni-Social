"""Instrucciones por MODO del asistente del tablero (`dominio.asistente`). PURO, sin BD.

Las instrucciones aditivas de los modos `variantes`/`resumir` viven en la Biblioteca de
Texto (`prompt/asistente/<modo>`, editables); el dict del módulo es solo la red defensiva.
Solo se cubre la composición del texto base (el lanzamiento delega en `dominio.generar`,
cubierto en sus propios tests).
"""

from __future__ import annotations

import pytest

from keni_consola.dominio import asistente


@pytest.fixture(autouse=True)
def _texto_tmp(monkeypatch, tmp_path):
    # Aislar el store de la Biblioteca: sin store, `cuerpo_efectivo` cae a la semilla del paquete.
    monkeypatch.setenv("KENI_TEXTO_DIR", str(tmp_path / "texto"))
    return tmp_path


def test_modo_generar_no_anade_instruccion():
    base = asistente.construir_texto_base(
        modo="generar", titulo="Título", descripcion="Brief", notas=""
    )
    assert base == "Título\n\nBrief"


@pytest.mark.parametrize("modo,esperado", [
    ("variantes", "TRES variantes"),
    ("resumir", "BREVE"),
])
def test_instruccion_del_modo_sale_de_la_semilla(modo, esperado):
    # Sin store, la instrucción aditiva viene del doc semilla `prompt/asistente/<modo>`.
    base = asistente.construir_texto_base(
        modo=modo, titulo="Título", descripcion="Brief", notas=""
    )
    assert base.startswith("Título\n\nBrief\n\n")
    assert esperado in base


def test_instruccion_editada_en_biblioteca_gana():
    from keni_consola import libtexto

    libtexto.importar_semilla()
    libtexto.guardar("prompt/asistente/resumir", cuerpo="RESUME EN UNA LÍNEA.")
    base = asistente.construir_texto_base(
        modo="resumir", titulo="T", descripcion="D", notas=""
    )
    assert base.endswith("RESUME EN UNA LÍNEA.")
    assert "BREVE" not in base


def test_sin_doc_ni_semilla_cae_al_fallback_del_modulo(monkeypatch, tmp_path):
    # Robustez ante stores sin re-seed: sin doc NI semilla, vale el dict del módulo.
    monkeypatch.setenv("KENI_TEXTO_SEMILLA", str(tmp_path / "semilla-vacia"))
    base = asistente.construir_texto_base(
        modo="variantes", titulo="T", descripcion="D", notas=""
    )
    assert "TRES variantes" in base
