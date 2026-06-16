"""Catálogo de transparencia prompt -> proceso(s) (`prompts_procesos`). PURO, sin red ni BD."""

from __future__ import annotations

from keni_consola import libprompts, prompts_procesos as pp


def _ids_seed_prompt() -> set[str]:
    """Ids de TODOS los prompts que viajan en la inicial del paquete (derivados de la ruta)."""
    base = libprompts.dir_inicial() / "prompt"
    return {
        "prompt/" + p.relative_to(base).with_suffix("").as_posix()
        for p in base.rglob("*.md")
    }


def test_todo_seed_prompt_esta_catalogado():
    # COBERTURA TOTAL: cada prompt que viaja en la inicial DEBE estar en el catálogo, para que la
    # pestaña «Prompts» muestre siempre a qué proceso se inyecta. Si añades un seed de prompt
    # nuevo y olvidas catalogarlo, este test lo caza.
    sin_catalogar = _ids_seed_prompt() - set(pp.PROCESOS_POR_PROMPT)
    assert not sin_catalogar, f"seeds tipo=prompt sin catalogar en prompts_procesos: {sin_catalogar}"


def test_catalogo_no_tiene_ids_fantasma():
    # Inverso: ninguna clave del catálogo apunta a un prompt que no existe como inicial (evita
    # etiquetas sueltas si se renombra/borra un seed).
    fantasma = set(pp.PROCESOS_POR_PROMPT) - _ids_seed_prompt()
    assert not fantasma, f"catálogo con ids sin seed: {fantasma}"


def test_procesos_de_prompt_conocido():
    procs = pp.procesos_de("prompt/ilustrar")
    assert procs and any("imagen" in p.lower() for p in procs)


def test_procesos_de_desconocido_es_vacio():
    assert pp.procesos_de("prompt/no-existe") == []
    assert pp.procesos_de("") == []


def test_catalogo_cubre_los_prompts_inyectados():
    # Los prompts que migramos a la Prompts DEBEN estar catalogados: la transparencia exige ver
    # a qué proceso se inyectan. Si cableas un prompt nuevo, añádelo también a `prompts_procesos`.
    esperados = {
        "prompt/ilustrar",
        "prompt/recibir/portal",
        "prompt/recibir/corresponsales",
        "prompt/recibir/reporteros",
        "prompt/recibir/eventos-claro",
        "prompt/recibir/notas",
        "prompt/recibir/contexto",
        "prompt/traducir",
        "prompt/fusionar",
        "prompt/priorizar",
        "prompt/importar/calendario",
        "prompt/importar/parrilla",
        "prompt/verificar",
        # Envoltorios del copy (dominio/generar.py)
        "prompt/envoltorios/redes",
        "prompt/envoltorios/copy-unico",
        "prompt/envoltorios/carrusel",
        "prompt/envoltorios/sin-emojis",
    }
    faltan = esperados - set(pp.PROCESOS_POR_PROMPT)
    assert not faltan, f"prompts inyectados sin catalogar: {faltan}"


def test_todas_las_claves_son_ids_de_prompt_con_etiqueta():
    assert all(k.startswith("prompt/") for k in pp.PROCESOS_POR_PROMPT)
    # Ninguna entrada con lista vacía (una entrada sin proceso no aporta transparencia).
    assert all(pp.PROCESOS_POR_PROMPT[k] for k in pp.PROCESOS_POR_PROMPT)
