"""Los prompts FALLBACK de cada módulo salen de la SEMILLA del paquete, no de strings duplicados.

PURO, sin Postgres: se apunta el store de la Texto a un tmp VACÍO y se hace reventar
`libtexto.cuerpo_efectivo` (lectura del store rota); cada módulo debe resolver su plantilla
desde `libtexto.cuerpo_semilla` (el .md que viaja en `texto_semilla/`).
"""

from __future__ import annotations

import pytest

from keni_consola import importador_calendario, libtexto
from keni_consola.dominio import (
    asistente,
    clasificador_marca,
    fusionar_semantica,
    generar,
    hashtags,
    recibir_parse,
    parrilla_import_job,
    perfil_editorial,
    traducir,
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
    (traducir._plantilla, "prompt/traducir"),
    (fusionar_semantica._plantilla, "prompt/fusionar"),
    (perfil_editorial._plantilla, "prompt/priorizar"),
    (parrilla_import_job._plantilla, "prompt/importar/parrilla"),
    (importador_calendario._plantilla, "prompt/importar/calendario"),
    (hashtags._plantilla, "prompt/hashtags"),
    (clasificador_marca._plantilla, "prompt/clasificar-marca"),
]

# Ids de prompt que el CÓDIGO espera encontrar en la semilla (la semilla es la única fuente).
# Si alguien borra un .md de `texto_semilla/`, este test lo caza ANTES del deploy: sin la semilla,
# la generación se quedaría sin ese prompt y degradaría a vacío. CONTRATO semilla↔código.
_IDS_SEMILLA_OBLIGATORIA = [
    generar.PROMPT_ENVOLTORIO_SIN_EMOJIS,
    generar.PROMPT_ENVOLTORIO_REDES,
    generar.PROMPT_ENVOLTORIO_CARRUSEL,
    generar.PROMPT_ENVOLTORIO_COPY_UNICO,
    hashtags._PROMPT_ID,
    clasificador_marca._PROMPT_ID,
    "prompt/asistente/variantes",
    "prompt/asistente/resumir",
]


def test_semilla_cubre_todos_los_prompts_que_el_codigo_espera():
    """La semilla provee CADA prompt cuyo `_FALLBACK_*` se eliminó (cobertura semilla↔código)."""
    for pid in _IDS_SEMILLA_OBLIGATORIA:
        doc = libtexto.obtener_semilla(pid)
        assert doc is not None and doc.cuerpo.strip(), f"falta o está vacía la semilla {pid}"


def test_envoltorios_y_modos_resuelven_desde_la_semilla(store_roto):
    """Con el store roto, los envoltorios de `generar` y las instrucciones del asistente
    resuelven su texto desde la SEMILLA del paquete (no de un string duplicado en código)."""
    for doc_id in (
        generar.PROMPT_ENVOLTORIO_SIN_EMOJIS, generar.PROMPT_ENVOLTORIO_REDES,
        generar.PROMPT_ENVOLTORIO_CARRUSEL, generar.PROMPT_ENVOLTORIO_COPY_UNICO,
    ):
        assert generar._plantilla_envoltorio(doc_id) == _semilla(doc_id), doc_id
    for modo in ("variantes", "resumir"):
        assert asistente._instruccion_modo(modo) == _semilla(f"prompt/asistente/{modo}"), modo


def test_cuerpo_semilla_lee_el_paquete_y_nunca_lanza():
    assert "traducciones" in libtexto.cuerpo_semilla("prompt/traducir")
    assert libtexto.cuerpo_semilla("prompt/no-existe") == ""
    assert libtexto.cuerpo_semilla("") == ""


def test_fallback_de_cada_modulo_resuelve_desde_la_semilla(store_roto):
    for plantilla, prompt_id in _CASOS:
        assert plantilla() == _semilla(prompt_id), prompt_id


def test_fallback_insumos_por_cajon_resuelve_desde_la_semilla(store_roto):
    for cajon, prompt_id in recibir_parse._PROMPT_INSUMO_IDS.items():
        prompt = recibir_parse._prompt_de_cajon(cajon, "/tmp/insumo.txt")
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
