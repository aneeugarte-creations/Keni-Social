"""Tests OFFLINE de la migración a render on-demand (`migrar_render_ondemand`).

Mockean repos (`listar_documento_versiones`, `actualizar_publicacion`) y `render_pieza.tiene_receta`,
así NO necesitan BD. Verifican la decisión CONSERVADORA por pieza: vacía `imagen` solo si hay
receta y NO es bespoke; conserva el resto; idempotente; respeta `--dry-run`.
"""

from __future__ import annotations

import pytest

from keni_consola import migrar_render_ondemand as mig


@pytest.fixture
def _entorno(monkeypatch):
    """Por defecto: con receta, sin versiones de documento (no bespoke), update OK."""
    monkeypatch.setattr(mig.render_pieza, "tiene_receta", lambda pub: True)
    monkeypatch.setattr(mig.repos, "listar_documento_versiones", lambda c, p: [])
    actualizadas: list[tuple[str, dict]] = []

    def _actualizar(pid, campos):
        actualizadas.append((pid, campos))
        return {"id": pid, **campos}

    monkeypatch.setattr(mig.repos, "actualizar_publicacion", _actualizar)
    return actualizadas


def _pub(**k):
    base = {"id": "p1", "contenido_id": "c1", "imagen": "placa.png", "marca": "unotv"}
    base.update(k)
    return base


def test_vacia_si_receta_y_no_bespoke(_entorno):
    assert mig.migrar_una(_pub(), dry_run=False) == "vaciada"
    assert _entorno == [("p1", {"imagen": ""})]


def test_dry_run_no_escribe(_entorno):
    assert mig.migrar_una(_pub(), dry_run=True) == "vaciaria"
    assert _entorno == []  # no se llamó a actualizar


def test_sin_imagen_se_salta(_entorno):
    assert mig.migrar_una(_pub(imagen=""), dry_run=False) == "sin-imagen"
    assert _entorno == []


def test_conserva_sin_receta(monkeypatch, _entorno):
    monkeypatch.setattr(mig.render_pieza, "tiene_receta", lambda pub: False)
    assert mig.migrar_una(_pub(), dry_run=False) == "conserva-sin-receta"
    assert _entorno == []


def test_conserva_bespoke(monkeypatch, _entorno):
    # Pieza con versiones de documento (editor pro): NO se reconstruye desde la receta.
    monkeypatch.setattr(mig.repos, "listar_documento_versiones", lambda c, p: [{"version": 1}])
    assert mig.migrar_una(_pub(), dry_run=False) == "conserva-bespoke"
    assert _entorno == []


def test_bespoke_ante_error_de_versiones(monkeypatch, _entorno):
    # Si no se puede consultar versiones, ante la duda NO se migra (se trata como bespoke).
    def _boom(c, p):
        raise RuntimeError("sin BD")

    monkeypatch.setattr(mig.repos, "listar_documento_versiones", _boom)
    assert mig.migrar_una(_pub(), dry_run=False) == "conserva-bespoke"
    assert _entorno == []
