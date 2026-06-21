"""Notificaciones in-app del ciclo de vida de un CAMBIO DE TURNO (swap).

Cada transicion del swap deja una notificacion en el "cajon" de la campana del
destinatario correcto (best-effort, sin tumbar la accion). Reusa los fixtures del test
de la API de swaps (`test_api_rota_swaps`) para inicializar horario + sesiones.

Reparto esperado:
  - solicitud        -> al destinatario
  - aceptado         -> a los admin (falta su aprobacion)
  - rechazado por B  -> al solicitante
  - aplicado         -> a solicitante y destinatario (NO al admin que lo aprobo)
  - rechazado_admin  -> a solicitante y destinatario
  - cancelado        -> al destinatario
"""

from __future__ import annotations

from keni_consola import auth, repos

from .test_api_rota_swaps import _ORIGIN, _payload_swap, _setup_con_admin


def _resumenes(usuario_id: str) -> list[str]:
    """Resumenes de las notificaciones de un usuario (sin filtrar por marca)."""
    return [n["resumen"] for n in repos.listar_notificaciones(usuario_id)]


def _id_admin() -> str:
    """Id de elias (el unico admin que siembra `_setup_con_admin`)."""
    return next(u["id"] for u in auth.listar_usuarios() if u["usuario"] == "elias")


def test_solicitud_notifica_al_destinatario(entorno):
    app, ana, beto, cli_ana, _cli_beto, _cli_admin = _setup_con_admin(entorno)
    cli_ana.post("/api/rota/swaps", json=_payload_swap(ana, beto, app), headers=_ORIGIN)
    notis = repos.listar_notificaciones(beto["id"])
    assert len(notis) == 1
    assert notis[0]["tipo"] == "cambio_turno"
    assert "propone un cambio" in notis[0]["resumen"]
    assert notis[0]["enlace"]  # deep-link a la pestaña de cambios y ausencias
    # El solicitante NO se auto-notifica su propia solicitud.
    assert repos.listar_notificaciones(ana["id"]) == []


def test_aceptar_notifica_al_admin(entorno):
    app, ana, beto, cli_ana, cli_beto, _cli_admin = _setup_con_admin(entorno)
    r = cli_ana.post("/api/rota/swaps", json=_payload_swap(ana, beto, app), headers=_ORIGIN)
    swap_id = r.json()["swap"]["id"]
    cli_beto.post(f"/api/rota/swaps/{swap_id}/aceptar", headers=_ORIGIN)
    assert any("falta tu aprobación" in s for s in _resumenes(_id_admin()))


def test_rechazar_destinatario_notifica_al_solicitante(entorno):
    app, ana, beto, cli_ana, cli_beto, _cli_admin = _setup_con_admin(entorno)
    r = cli_ana.post("/api/rota/swaps", json=_payload_swap(ana, beto, app), headers=_ORIGIN)
    swap_id = r.json()["swap"]["id"]
    cli_beto.post(f"/api/rota/swaps/{swap_id}/rechazar", headers=_ORIGIN)
    assert any("rechazó tu cambio" in s for s in _resumenes(ana["id"]))


def test_aprobar_notifica_a_ambas_partes_no_al_admin(entorno):
    app, ana, beto, cli_ana, cli_beto, cli_admin = _setup_con_admin(entorno)
    r = cli_ana.post("/api/rota/swaps", json=_payload_swap(ana, beto, app), headers=_ORIGIN)
    swap_id = r.json()["swap"]["id"]
    cli_beto.post(f"/api/rota/swaps/{swap_id}/aceptar", headers=_ORIGIN)
    cli_admin.post(f"/api/rota/swaps/{swap_id}/aprobar", headers=_ORIGIN)
    assert any("aprobado" in s for s in _resumenes(ana["id"]))
    assert any("aprobado" in s for s in _resumenes(beto["id"]))
    # El admin que aprobó NO recibe el aviso del desenlace que él mismo provocó.
    assert all("aprobado" not in s for s in _resumenes(_id_admin()))


def test_rechazar_admin_notifica_a_ambas_partes(entorno):
    app, ana, beto, cli_ana, cli_beto, cli_admin = _setup_con_admin(entorno)
    r = cli_ana.post("/api/rota/swaps", json=_payload_swap(ana, beto, app), headers=_ORIGIN)
    swap_id = r.json()["swap"]["id"]
    cli_beto.post(f"/api/rota/swaps/{swap_id}/aceptar", headers=_ORIGIN)
    cli_admin.post(f"/api/rota/swaps/{swap_id}/rechazar-admin", headers=_ORIGIN)
    assert any("rechazado por administración" in s for s in _resumenes(ana["id"]))
    assert any("rechazado por administración" in s for s in _resumenes(beto["id"]))


def test_cancelar_notifica_al_destinatario(entorno):
    app, ana, beto, cli_ana, _cli_beto, _cli_admin = _setup_con_admin(entorno)
    r = cli_ana.post("/api/rota/swaps", json=_payload_swap(ana, beto, app), headers=_ORIGIN)
    swap_id = r.json()["swap"]["id"]
    cli_ana.post(f"/api/rota/swaps/{swap_id}/cancelar", headers=_ORIGIN)
    assert any("canceló" in s for s in _resumenes(beto["id"]))
