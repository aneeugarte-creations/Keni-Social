"""Los prompts FALLBACK de cada módulo salen de la SEMILLA del paquete, no de strings duplicados.

PURO, sin Postgres: se apunta el store de la Texto a un tmp VACÍO y se hace reventar
`libtexto.cuerpo_efectivo` (lectura del store rota); cada módulo debe resolver su plantilla
desde `libtexto.cuerpo_semilla` (el .md que viaja en `texto_semilla/`).
"""

from __future__ import annotations

import pytest

from keni_consola import importador_calendario, libtexto, sugerencias_editoriales
from keni_consola.dominio import (
    fusion_semantica,
    insumos_parse,
    parrilla_import_job,
    perfil_editorial,
    traduccion,
)


def _semilla(prompt_id: str) -> str:
    doc = libtexto.obtener_semilla(prompt_id)
    assert doc is not None, f"falta la semilla {prompt_id}"
    return doc.cuerpo.strip()


@pytest.fixture
def store_roto(monkeypatch, tmp_path):
    """Store vacío + lectura efectiva reventando: solo queda la SEMILLA del paquete."""
    monkeypatch.setenv("KENI_TEXTO_DIR", str(tmp_path / "texto"))

    def boom(_prompt_id: str) -> str:
        raise RuntimeError("store roto (simulado)")

    monkeypatch.setattr(libtexto, "cuerpo_efectivo", boom)


# (función _plantilla, id del seed del que debe salir el fallback)
_CASOS = [
    (traduccion._plantilla, "prompt/noticias/traduccion"),
    (fusion_semantica._plantilla, "prompt/noticias/fusion-historias"),
    (perfil_editorial._plantilla, "prompt/noticias/perfil-editorial"),
    (parrilla_import_job._plantilla, "prompt/importacion/parrilla"),
    (importador_calendario._plantilla, "prompt/importacion/calendario"),
    (sugerencias_editoriales._plantilla_sugerencias, "prompt/editorial/sugerencias-plataforma"),
]


def test_cuerpo_semilla_lee_el_paquete_y_nunca_lanza():
    assert "traducciones" in libtexto.cuerpo_semilla("prompt/noticias/traduccion")
    assert libtexto.cuerpo_semilla("prompt/no-existe") == ""
    assert libtexto.cuerpo_semilla("") == ""


def test_fallback_de_cada_modulo_resuelve_desde_la_semilla(store_roto):
    for plantilla, prompt_id in _CASOS:
        assert plantilla() == _semilla(prompt_id), prompt_id


def test_fallback_insumos_por_cajon_resuelve_desde_la_semilla(store_roto):
    for cajon, prompt_id in insumos_parse._PROMPT_INSUMO_IDS.items():
        prompt = insumos_parse._prompt_de_cajon(cajon, "/tmp/insumo.txt")
        assert prompt == _semilla(prompt_id).replace("{{RUTA}}", "/tmp/insumo.txt"), cajon
        # El contrato JSON del cajón sobrevive al fallback.
        assert '{"items"' in prompt, cajon


def test_fallback_perfil_sigue_sustituyendo_placeholders(store_roto):
    # {{MAX_KEYWORDS}} / {{MARCA}} / {{EDITORIAL}} se aplican igual sobre la semilla.
    p = perfil_editorial._construir_prompt("unotv", "Cubrimos política y deportes.")
    assert str(perfil_editorial._MAX_KEYWORDS) in p
    assert "unotv" in p
    assert "Cubrimos política y deportes." in p
    assert "{{" not in p


def test_fallback_parrilla_mantiene_contrato_operaciones(store_roto):
    ctx = parrilla_import_job.construir_contexto_prompt(nombres_miembros={"u1": "Luis"})
    p = parrilla_import_job.componer_prompt(ctx=ctx, texto_documento="### HOJA: A\nfila")
    assert '"operaciones"' in p
    assert "{{" not in p
