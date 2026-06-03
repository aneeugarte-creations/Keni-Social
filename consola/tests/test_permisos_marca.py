"""Tests del alcance por MARCA (`keni_consola.permisos.rechazo_marca`). OFFLINE.

La consola es por marca: un editor solo puede consultar SUS marcas. Estos tests
cubren las decisiones de `rechazo_marca` sin tocar la BD: el unico camino que
consultaria la BD (editor pidiendo una marca concreta) se cubre monkeypatcheando
`obtener_usuario_por_id`.
"""

from __future__ import annotations

from types import SimpleNamespace

from keni_consola import permisos


def _request(usuario):
    """Request falso: solo expone `request.state.usuario`, que es lo que lee permisos."""
    return SimpleNamespace(state=SimpleNamespace(usuario=usuario))


def test_sin_marca_pedida_no_bloquea():
    # Sin `?marca=` no hay nada que bloquear (el filtro implicito lo pone el cliente).
    req = _request({"id": "u1", "rol": "editor"})
    assert permisos.rechazo_marca(req, None) is None
    assert permisos.rechazo_marca(req, "") is None


def test_admin_ve_cualquier_marca():
    req = _request({"id": "u1", "rol": "admin"})
    assert permisos.marcas_visibles(req) is None
    assert permisos.rechazo_marca(req, "claro-sports") is None


def test_token_sin_usuario_no_restringe():
    # Entrada por token de mantenimiento (sin usuario de sesion): no se restringe aqui.
    req = _request(None)
    assert permisos.marcas_visibles(req) is None
    assert permisos.rechazo_marca(req, "unotv") is None


def test_editor_marca_propia_ok_y_ajena_403(monkeypatch):
    # El editor cubre unotv; pedir unotv pasa, pedir claro-sports da 403.
    monkeypatch.setattr(
        "keni_consola.auth.obtener_usuario_por_id",
        lambda _id: {"id": "u1", "marcas": ["unotv"]},
    )
    req = _request({"id": "u1", "rol": "editor"})
    assert permisos.marcas_visibles(req) == {"unotv"}
    assert permisos.rechazo_marca(req, "unotv") is None
    rechazo = permisos.rechazo_marca(req, "claro-sports")
    assert rechazo is not None
    assert rechazo.status_code == 403


def test_editor_sin_marcas_no_restringe(monkeypatch):
    # Editor sin marcas asignadas (cobertura global): no se restringe.
    monkeypatch.setattr(
        "keni_consola.auth.obtener_usuario_por_id",
        lambda _id: {"id": "u1", "marcas": []},
    )
    req = _request({"id": "u1", "rol": "editor"})
    assert permisos.marcas_visibles(req) is None
    assert permisos.rechazo_marca(req, "claro-sports") is None
