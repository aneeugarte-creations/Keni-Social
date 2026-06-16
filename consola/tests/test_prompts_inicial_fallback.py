"""Los prompts FALLBACK de cada módulo salen de la INICIAL del paquete, no de strings duplicados.

PURO, sin Postgres: se apunta el store de la Texto a un tmp VACÍO y se hace reventar
`libprompts.cuerpo_efectivo` (lectura del store rota); cada módulo debe resolver su plantilla
desde `libprompts.cuerpo_inicial` (el .md que viaja en `prompts_inicial/`).
"""

from __future__ import annotations

import pytest

from keni_consola import importador_calendario, libprompts
from keni_consola.dominio import (
    clasificador_marca,
    fusionar_semantica,
    generar,
    hashtags,
    recibir_parse,
    parrilla_import_job,
    perfil_editorial,
    traducir,
)


def _inicial(prompt_id: str) -> str:
    from keni_consola.prompts_contratos import resolver_contrato

    doc = libprompts.obtener_inicial(prompt_id)
    assert doc is not None, f"falta la inicial {prompt_id}"
    # El cuerpo efectivo (lo que componen los módulos) resuelve el contrato de salida; el helper
    # debe espejarlo para comparar `plantilla()` (resuelta) con la inicial.
    return resolver_contrato(prompt_id, doc.cuerpo).strip()


@pytest.fixture
def store_roto(monkeypatch, tmp_path):
    """Store vacío + lectura efectiva reventando: solo queda la INICIAL del paquete."""
    monkeypatch.setenv("KENI_PROMPTS_DIR", str(tmp_path / "texto"))

    def boom(_prompt_id: str) -> str:
        raise RuntimeError("store roto (simulado)")

    monkeypatch.setattr(libprompts, "cuerpo_efectivo", boom)


# (función _plantilla, id del seed del que debe salir el fallback)
_CASOS = [
    (traducir._plantilla, "prompt/traducir"),
    (fusionar_semantica._plantilla, "prompt/fusionar"),
    (perfil_editorial._plantilla, "prompt/priorizar"),
    (parrilla_import_job._plantilla, "prompt/importar/parrilla"),
    (importador_calendario._plantilla, "prompt/importar/calendario"),
    (hashtags._plantilla, "prompt/hashtags"),
    (clasificador_marca._plantilla, "prompt/clasificar-marca"),
]

# Ids de prompt que el CÓDIGO espera encontrar en la inicial (la inicial es la única fuente).
# Si alguien borra un .md de `prompts_inicial/`, este test lo caza ANTES del deploy: sin la inicial,
# la generación se quedaría sin ese prompt y degradaría a vacío. CONTRATO inicial↔código.
_IDS_INICIAL_OBLIGATORIA = [
    generar.PROMPT_ENVOLTORIO_REDES,
    generar.PROMPT_ENVOLTORIO_CARRUSEL,
    generar.PROMPT_ENVOLTORIO_COPY_UNICO,
    hashtags._PROMPT_ID,
    clasificador_marca._PROMPT_ID,
]


def test_inicial_cubre_todos_los_prompts_que_el_codigo_espera():
    """La inicial provee CADA prompt cuyo `_FALLBACK_*` se eliminó (cobertura inicial↔código)."""
    for pid in _IDS_INICIAL_OBLIGATORIA:
        doc = libprompts.obtener_inicial(pid)
        assert doc is not None and doc.cuerpo.strip(), f"falta o está vacía la inicial {pid}"


def test_envoltorios_resuelven_desde_la_inicial(store_roto):
    """Con el store roto, los envoltorios de `generar` resuelven su texto desde la INICIAL del
    paquete (no de un string duplicado en código)."""
    for doc_id in (
        generar.PROMPT_ENVOLTORIO_REDES,
        generar.PROMPT_ENVOLTORIO_CARRUSEL, generar.PROMPT_ENVOLTORIO_COPY_UNICO,
    ):
        assert generar._plantilla_envoltorio(doc_id) == _inicial(doc_id), doc_id


def test_cuerpo_inicial_lee_el_paquete_y_nunca_lanza():
    assert "traducciones" in libprompts.cuerpo_inicial("prompt/traducir")
    assert libprompts.cuerpo_inicial("prompt/no-existe") == ""
    assert libprompts.cuerpo_inicial("") == ""


def test_fallback_de_cada_modulo_resuelve_desde_la_inicial(store_roto):
    for plantilla, prompt_id in _CASOS:
        assert plantilla() == _inicial(prompt_id), prompt_id


def test_fallback_insumos_por_cajon_resuelve_desde_la_inicial(store_roto):
    for cajon, prompt_id in recibir_parse._PROMPT_INSUMO_IDS.items():
        prompt = recibir_parse._prompt_de_cajon(cajon, "/tmp/insumo.txt")
        assert prompt == _inicial(prompt_id).replace("{{RUTA}}", "/tmp/insumo.txt"), cajon
        # El contrato JSON del cajón sobrevive al fallback.
        assert '{"items"' in prompt, cajon


def test_fallback_perfil_sigue_sustituyendo_placeholders(store_roto):
    # {{MAX_KEYWORDS}} / {{MARCA}} / {{EDITORIAL}} se aplican igual sobre la inicial.
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
