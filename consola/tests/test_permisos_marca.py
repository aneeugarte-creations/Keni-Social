"""Tests del FOCO POR DEFECTO por MARCA (`keni_consola.permisos.marcas_preferentes`). OFFLINE.

La marca NO es una restriccion: el equipo es multidisciplinar y cualquiera cubre/accede
CUALQUIER marca. `marcas_preferentes` solo da el FOCO POR DEFECTO (None = sin preferencia
=> todas) que usan los listados/metricas cuando no se pide marca explicita. Ya NO existe
ningun cerrojo por marca (`rechazo_pieza`/`rechazo_marca` se eliminaron): estos tests
confirman el contrato de foco-no-cerrojo sin tocar la BD (el unico camino que consultaria
la BD —editor con marcas— se cubre monkeypatcheando `obtener_usuario_por_id`).
"""

from __future__ import annotations

from types import SimpleNamespace

from keni_consola import permisos


def _request(usuario):
    """Request falso: solo expone `request.state.usuario`, que es lo que lee permisos."""
    return SimpleNamespace(state=SimpleNamespace(usuario=usuario))


def test_admin_sin_preferencia():
    # Admin => sin foco por defecto (None => todas las marcas).
    req = _request({"id": "u1", "rol": "admin"})
    assert permisos.marcas_preferentes(req) is None


def test_token_sin_usuario_sin_preferencia():
    # Entrada por token de mantenimiento (sin usuario de sesion): sin foco (None => todas).
    req = _request(None)
    assert permisos.marcas_preferentes(req) is None


def test_editor_con_marca_da_su_foco(monkeypatch):
    # El editor cubre unotv: su FOCO por defecto es {unotv}, pero NO le restringe nada.
    monkeypatch.setattr(
        "keni_consola.auth.obtener_usuario_por_id",
        lambda _id: {"id": "u1", "marcas": ["unotv"]},
    )
    req = _request({"id": "u1", "rol": "editor"})
    assert permisos.marcas_preferentes(req) == {"unotv"}


def test_editor_varias_marcas_da_conjunto(monkeypatch):
    monkeypatch.setattr(
        "keni_consola.auth.obtener_usuario_por_id",
        lambda _id: {"id": "u1", "marcas": ["unotv", "claro-sports"]},
    )
    req = _request({"id": "u1", "rol": "editor"})
    assert permisos.marcas_preferentes(req) == {"unotv", "claro-sports"}


def test_editor_sin_marcas_sin_preferencia(monkeypatch):
    # Editor sin marcas asignadas (cobertura global): sin foco (None => todas).
    monkeypatch.setattr(
        "keni_consola.auth.obtener_usuario_por_id",
        lambda _id: {"id": "u1", "marcas": []},
    )
    req = _request({"id": "u1", "rol": "editor"})
    assert permisos.marcas_preferentes(req) is None


def test_no_existe_cerrojo_por_marca():
    # Garantia explicita del giro de contrato: NO hay helpers de bloqueo por marca.
    assert not hasattr(permisos, "rechazo_pieza")
    assert not hasattr(permisos, "rechazo_marca")
    assert not hasattr(permisos, "marcas_visibles")
    assert not hasattr(permisos, "marcas_scope")
