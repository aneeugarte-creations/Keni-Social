"""Catálogo de transparencia prompt -> proceso(s) (`prompts_procesos`). PURO, sin red ni BD."""

from __future__ import annotations

from keni_consola import prompts_procesos as pp


def test_procesos_de_prompt_conocido():
    procs = pp.procesos_de("prompt/imagen/sistema-generador")
    assert procs and any("imagen" in p.lower() for p in procs)


def test_procesos_de_desconocido_es_vacio():
    assert pp.procesos_de("prompt/no-existe") == []
    assert pp.procesos_de("") == []


def test_catalogo_cubre_los_prompts_inyectados():
    # Los prompts que migramos a la Biblioteca DEBEN estar catalogados: la transparencia exige ver
    # a qué proceso se inyectan. Si cableas un prompt nuevo, añádelo también a `prompts_procesos`.
    esperados = {
        "prompt/imagen/sistema-generador",
        "prompt/imagen/arte-noticia",
        "prompt/insumos/portal",
        "prompt/insumos/corresponsales",
        "prompt/insumos/reporteros",
        "prompt/insumos/eventos-claro",
        "prompt/editorial/sugerencias-plataforma",
        "prompt/noticias/traduccion",
        "prompt/noticias/fusion-historias",
        "prompt/noticias/perfil-editorial",
        "prompt/importacion/calendario",
        "prompt/importacion/parrilla",
        "prompt/qa-fuente",
    }
    faltan = esperados - set(pp.PROCESOS_POR_PROMPT)
    assert not faltan, f"prompts inyectados sin catalogar: {faltan}"


def test_todas_las_claves_son_ids_de_prompt_con_etiqueta():
    assert all(k.startswith("prompt/") for k in pp.PROCESOS_POR_PROMPT)
    # Ninguna entrada con lista vacía (una entrada sin proceso no aporta transparencia).
    assert all(pp.PROCESOS_POR_PROMPT[k] for k in pp.PROCESOS_POR_PROMPT)
