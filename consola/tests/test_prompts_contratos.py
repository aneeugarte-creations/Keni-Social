"""Contrato de salida (forma del JSON) de los prompts ESTRUCTURADOS: registro en código.

Invariantes:
  - El cuerpo EDITABLE (inicial/`obtener_inicial`) de cada estructurado TERMINA en el placeholder
    `{{CONTRATO_SALIDA}}` y ya NO lleva el contrato inline.
  - El cuerpo EFECTIVO (`cuerpo_inicial`/`cuerpo_efectivo`, lo que componen los pipelines) lleva el
    contrato ya resuelto al final y sin placeholder.
  - `contrato_de` es None para prompts no estructurados; `resolver_contrato` es no-op sin placeholder.
PURO, sin BD: store en tmp vacío -> cae a la inicial del paquete.
"""

from __future__ import annotations

import re

import pytest

from keni_consola import libprompts
from keni_consola.prompts_contratos import (
    CONTRATO_POR_PROMPT,
    PLACEHOLDER,
    contrato_de,
    resolver_contrato,
)

# Fragmentos ADITIVOS que el código compone DENTRO de otro prompt (no son autónomos): su forma
# JSON va entretejida en el cuerpo, fuera del mecanismo `{{CONTRATO_SALIDA}}`. Excepción declarada.
_FRAGMENTOS_JSON_INLINE = {
    "prompt/envoltorios/redes",
    "prompt/envoltorios/copy-unico",
    "prompt/envoltorios/carrusel",
    "prompt/redactar-carrusel",
}

# Un objeto JSON con clave string: la huella de un contrato inline en el cuerpo.
_RE_OBJETO_JSON = re.compile(r'\{\s*"')


def _ids_seed_prompt() -> set[str]:
    base = libprompts.dir_inicial() / "prompt"
    return {"prompt/" + p.relative_to(base).with_suffix("").as_posix() for p in base.rglob("*.md")}


@pytest.fixture(autouse=True)
def _store_tmp(monkeypatch, tmp_path):
    monkeypatch.setenv("KENI_PROMPTS_DIR", str(tmp_path / "texto"))


def test_resolver_contrato_rellena_y_es_noop_sin_placeholder():
    assert resolver_contrato("prompt/traducir", "x " + PLACEHOLDER) == "x " + CONTRATO_POR_PROMPT["prompt/traducir"]
    # Sin placeholder: intacto (migración suave).
    assert resolver_contrato("prompt/traducir", "cuerpo sin placeholder") == "cuerpo sin placeholder"
    # Con placeholder pero prompt NO estructurado: limpia el placeholder.
    assert PLACEHOLDER not in resolver_contrato("prompt/ilustrar", "x\n\n" + PLACEHOLDER)


def test_contrato_de_none_para_no_estructurados():
    for pid in ("prompt/ilustrar", "prompt/envoltorios/redes", "prompt/envoltorios/copy-unico"):
        assert contrato_de(pid) is None, pid


def test_parrilla_tiene_contrato_inyectado_desde_codigo():
    # parrilla es caso especial: su contrato lo expone `contrato_de` (para el bloque read-only) pero
    # se inyecta desde su módulo (no por placeholder); debe traer el esquema de operaciones.
    c = contrato_de("prompt/importar/parrilla")
    assert c and '"operaciones"' in c and "crear_evento" in c


def test_ningun_prompt_estructurado_lleva_contrato_inline():
    # Todo prompt AUTÓNOMO cuyo copy parsea el código debe declarar su contrato en
    # `CONTRATO_POR_PROMPT` y terminar en `{{CONTRATO_SALIDA}}` (el editor lo pinta read-only, así
    # nadie lo rompe al editar). Caza el hueco: un seed con objeto JSON inline que NO usa el
    # placeholder ni es un fragmento/documento declarado.
    ofensores = []
    for pid in sorted(_ids_seed_prompt()):
        doc = libprompts.obtener_inicial(pid)
        assert doc is not None, pid
        if PLACEHOLDER in doc.cuerpo:
            continue  # ya bloqueado: el contrato va read-only desde código
        if pid in _FRAGMENTOS_JSON_INLINE:
            continue  # fragmento aditivo declarado (lo compone el código dentro de otro prompt)
        if _RE_OBJETO_JSON.search(doc.cuerpo):
            ofensores.append(pid)
    assert not ofensores, (
        f"prompts con contrato JSON inline SIN bloquear: {ofensores}. "
        "Muévelo a CONTRATO_POR_PROMPT y termina el cuerpo en {{CONTRATO_SALIDA}}."
    )


@pytest.mark.parametrize("prompt_id", list(CONTRATO_POR_PROMPT))
def test_editable_termina_en_placeholder_y_efectivo_resuelve(prompt_id: str):
    contrato = CONTRATO_POR_PROMPT[prompt_id]
    crudo = libprompts.obtener_inicial(prompt_id)
    assert crudo is not None, f"falta la inicial {prompt_id}"
    cuerpo_editable = crudo.cuerpo
    # Editable: termina en el placeholder y NO lleva ya el contrato inline.
    assert cuerpo_editable.rstrip().endswith(PLACEHOLDER), prompt_id
    assert contrato not in cuerpo_editable, prompt_id
    # Efectivo (composición): contrato resuelto al final, sin placeholder.
    efectivo = libprompts.cuerpo_inicial(prompt_id)
    assert PLACEHOLDER not in efectivo, prompt_id
    assert efectivo.rstrip().endswith(contrato.rstrip()), prompt_id
