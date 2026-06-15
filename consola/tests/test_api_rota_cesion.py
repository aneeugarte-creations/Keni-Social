"""Verbo CEDER (#175, Fase 1): A ofrece su turno (una vía), otro lo RECLAMA, el admin aprueba.

Reutiliza los fixtures del test de swaps (mismo horario sembrado). Flujo:
  crear cesión (propuesto, sin destinatario) -> reclamar (aceptado, destinatario=quien reclama)
  -> aprobar (aplicado: el turno de A pasa a ser del que reclamó).
"""

from __future__ import annotations

from starlette.testclient import TestClient

from keni_consola import auth

from .conftest import TOKEN_PRUEBA
from .test_api_rota_swaps import (
    _FRANJAS_LUNES,
    _ORIGIN,
    CLAVE,
    DIA_A,
    LUNES,
    _cli_de,
    _setup_con_admin,
)


def _payload_cesion() -> dict:
    """Cuerpo de una cesión del turno (DIA_A, Mañana) del solicitante."""
    return {
        "tipo": "cesion",
        "fecha_a": DIA_A,
        "franja_a": _FRANJAS_LUNES["matutino"],
        "motivo": "No puedo ese día",
    }


def test_cesion_flujo_completo(entorno):
    app, ana, _beto, cli_ana, _cli_beto, cli_admin = _setup_con_admin(entorno)
    caro = auth.crear_usuario("caro", CLAVE, "editor")
    cli_caro = _cli_de(app, "caro")

    # 1) ana CEDE su turno (DIA_A, Mañana): nace propuesto, sin destinatario.
    r = cli_ana.post("/api/rota/swaps", json=_payload_cesion(), headers=_ORIGIN)
    assert r.status_code == 201, r.text
    swap = r.json()["swap"]
    assert swap["tipo"] == "cesion"
    assert swap["estado"] == "propuesto"
    assert swap["destinatario_id"] == ""
    swap_id = swap["id"]

    # 2) caro la RECLAMA: pasa a aceptado con caro como destinatario.
    rc = cli_caro.post(f"/api/rota/swaps/{swap_id}/reclamar", headers=_ORIGIN)
    assert rc.status_code == 200, rc.text
    reclamado = rc.json()["swap"]
    assert reclamado["estado"] == "aceptado"
    assert reclamado["destinatario_id"] == caro["id"]

    # 3) el admin APRUEBA: el turno (DIA_A, Mañana) de ana pasa a ser de caro.
    ra = cli_admin.post(f"/api/rota/swaps/{swap_id}/aprobar", headers=_ORIGIN)
    assert ra.status_code == 200, ra.text
    assert ra.json()["swap"]["estado"] == "aplicado"

    token_cli = TestClient(app, headers={"Authorization": f"Bearer {TOKEN_PRUEBA}"})
    turnos = token_cli.get(f"/api/rota/turnos?lunes={LUNES}").json()["turnos"]
    turno = next(
        t for t in turnos
        if t["fecha"] == DIA_A and t["franja_id"] == _FRANJAS_LUNES["matutino"]
    )
    assert turno["miembro_id"] == caro["id"]


def test_no_puedo_reclamar_mi_propia_cesion_400(entorno):
    app, ana, _beto, cli_ana, _cli_beto, _cli_admin = _setup_con_admin(entorno)
    del ana
    r = cli_ana.post("/api/rota/swaps", json=_payload_cesion(), headers=_ORIGIN)
    swap_id = r.json()["swap"]["id"]
    rc = cli_ana.post(f"/api/rota/swaps/{swap_id}/reclamar", headers=_ORIGIN)
    assert rc.status_code == 400


def test_cesion_solo_se_reclama_una_vez_409(entorno):
    app, ana, _beto, cli_ana, cli_beto, _cli_admin = _setup_con_admin(entorno)
    del ana
    auth.crear_usuario("caro", CLAVE, "editor")
    cli_caro = _cli_de(app, "caro")
    r = cli_ana.post("/api/rota/swaps", json=_payload_cesion(), headers=_ORIGIN)
    swap_id = r.json()["swap"]["id"]
    # caro la reclama primero (ok); beto llega tarde -> 409 (ya no es propuesto).
    assert cli_caro.post(f"/api/rota/swaps/{swap_id}/reclamar", headers=_ORIGIN).status_code == 200
    assert cli_beto.post(f"/api/rota/swaps/{swap_id}/reclamar", headers=_ORIGIN).status_code == 409
