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

import pytest

from keni_consola import libtexto
from keni_consola.prompts_contratos import (
    CONTRATO_POR_PROMPT,
    PLACEHOLDER,
    contrato_de,
    resolver_contrato,
)


@pytest.fixture(autouse=True)
def _store_tmp(monkeypatch, tmp_path):
    monkeypatch.setenv("KENI_TEXTO_DIR", str(tmp_path / "texto"))


def test_resolver_contrato_rellena_y_es_noop_sin_placeholder():
    assert resolver_contrato("prompt/traducir", "x " + PLACEHOLDER) == "x " + CONTRATO_POR_PROMPT["prompt/traducir"]
    # Sin placeholder: intacto (migración suave).
    assert resolver_contrato("prompt/traducir", "cuerpo sin placeholder") == "cuerpo sin placeholder"
    # Con placeholder pero prompt NO estructurado: limpia el placeholder.
    assert PLACEHOLDER not in resolver_contrato("prompt/ilustrar", "x\n\n" + PLACEHOLDER)


def test_contrato_de_none_para_no_estructurados():
    for pid in ("prompt/ilustrar", "prompt/hashtags", "prompt/asistente/resumir", "prompt/asistente/variantes"):
        assert contrato_de(pid) is None, pid


def test_parrilla_tiene_contrato_inyectado_desde_codigo():
    # parrilla es caso especial: su contrato lo expone `contrato_de` (para el bloque read-only) pero
    # se inyecta desde su módulo (no por placeholder); debe traer el esquema de operaciones.
    c = contrato_de("prompt/importar/parrilla")
    assert c and '"operaciones"' in c and "crear_evento" in c


@pytest.mark.parametrize("prompt_id", list(CONTRATO_POR_PROMPT))
def test_editable_termina_en_placeholder_y_efectivo_resuelve(prompt_id: str):
    contrato = CONTRATO_POR_PROMPT[prompt_id]
    crudo = libtexto.obtener_inicial(prompt_id)
    assert crudo is not None, f"falta la inicial {prompt_id}"
    cuerpo_editable = crudo.cuerpo
    # Editable: termina en el placeholder y NO lleva ya el contrato inline.
    assert cuerpo_editable.rstrip().endswith(PLACEHOLDER), prompt_id
    assert contrato not in cuerpo_editable, prompt_id
    # Efectivo (composición): contrato resuelto al final, sin placeholder.
    efectivo = libtexto.cuerpo_inicial(prompt_id)
    assert PLACEHOLDER not in efectivo, prompt_id
    assert efectivo.rstrip().endswith(contrato.rstrip()), prompt_id
