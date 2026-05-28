"""Helper unico de rol `keni_consola.permisos` (#153).

`es_admin(request)` lee SOLO lo que el middleware deja en `request.state`:
  - token interino de mantenimiento (`auth_por_token=True`) -> True (plenos permisos),
  - sesion de un admin -> True,
  - sesion de un editor -> False,
  - sin credencial reconocida -> False.

Es la fuente unica que comparten `/api/conexiones`, `/api/usuarios` y `/api/rota`,
asi que el rol se decide en UN solo sitio. Sin red, sin BD: se simula `request.state`.
"""

from __future__ import annotations

from types import SimpleNamespace

from keni_consola import permisos


def _req(**estado):
    """Request falsa con un `state` simulado (lo unico que `es_admin` lee)."""
    return SimpleNamespace(state=SimpleNamespace(**estado))


def test_token_interino_es_admin():
    assert permisos.es_admin(_req(auth_por_token=True, usuario=None)) is True


def test_sesion_admin_es_admin():
    req = _req(auth_por_token=False, usuario={"id": "1", "usuario": "a", "rol": "admin"})
    assert permisos.es_admin(req) is True


def test_sesion_editor_no_es_admin():
    req = _req(auth_por_token=False, usuario={"id": "2", "usuario": "e", "rol": "editor"})
    assert permisos.es_admin(req) is False


def test_sin_credencial_no_es_admin():
    assert permisos.es_admin(_req(auth_por_token=False, usuario=None)) is False


def test_usuario_no_dict_no_es_admin():
    # Defensa: un `usuario` que no sea dict (estado raro) nunca cuenta como admin.
    assert permisos.es_admin(_req(auth_por_token=False, usuario="admin")) is False


def test_rechazo_solo_admin_es_403_json():
    r = permisos.rechazo_solo_admin("nope")
    assert r.status_code == 403
    assert b"nope" in r.body


def test_usuario_actual_devuelve_dict_o_none():
    req = _req(usuario={"id": "1", "usuario": "a", "rol": "admin"})
    assert permisos.usuario_actual(req) == {"id": "1", "usuario": "a", "rol": "admin"}
    assert permisos.usuario_actual(_req(usuario=None)) is None
