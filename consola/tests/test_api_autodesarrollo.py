"""Tests de la API del lazo de auto-desarrollo (/api/autodesarrollo), #109.

OFFLINE. El disparo del lazo se inyecta a una fake que NO crea worktree ni llama a
`claude` (ver conftest `_disparar_autodesarrollo_noop`). El flag/auditoría se aíslan en
tmp via `KENI_AUTODESARROLLO_*` (conftest). Nada de efectos reales.
"""

from __future__ import annotations

from .conftest import _cliente


def test_estado_flag_off_por_defecto(cliente):
    r = cliente.get("/api/autodesarrollo")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["activo"] is False
    assert cuerpo["fijado_por_entorno"] is False
    assert cuerpo["cap_lineas"] == 400
    assert cuerpo["auditoria"] == []


def test_activar_requiere_confirmar_riesgo(cliente):
    # Sin confirmar el riesgo, activar es 400 (gate 1: la activación es deliberada).
    r = cliente.post("/api/autodesarrollo/flag", json={"activo": True})
    assert r.status_code == 400
    assert cliente.get("/api/autodesarrollo").json()["activo"] is False


def test_activar_confirmando_riesgo(cliente):
    r = cliente.post("/api/autodesarrollo/flag", json={"activo": True, "confirmo_riesgo": True})
    assert r.status_code == 200
    assert r.json()["activo"] is True
    assert cliente.get("/api/autodesarrollo").json()["activo"] is True


def test_desactivar(cliente):
    cliente.post("/api/autodesarrollo/flag", json={"activo": True, "confirmo_riesgo": True})
    r = cliente.post("/api/autodesarrollo/flag", json={"activo": False})
    assert r.status_code == 200
    assert r.json()["activo"] is False


def test_flag_invalido_400(cliente):
    assert cliente.post("/api/autodesarrollo/flag", json={"activo": "si"}).status_code == 400


def test_flag_por_entorno_no_se_puede_cambiar_por_api(cliente, monkeypatch):
    # Si KENI_AUTODESARROLLO está en el entorno (kill switch), la API no lo cambia.
    monkeypatch.setenv("KENI_AUTODESARROLLO", "0")
    r = cliente.post("/api/autodesarrollo/flag", json={"activo": True, "confirmo_riesgo": True})
    assert r.status_code == 409
    assert cliente.get("/api/autodesarrollo").json()["fijado_por_entorno"] is True


def test_implementar_con_flag_off_es_409(cliente):
    sid = cliente.post("/api/sugerencias", json={"titulo": "Idea"}).json()["sugerencia"]["id"]
    r = cliente.post("/api/autodesarrollo/implementar", json={"sugerencia_id": sid})
    assert r.status_code == 409


def test_implementar_sugerencia_inexistente_404(cliente):
    cliente.post("/api/autodesarrollo/flag", json={"activo": True, "confirmo_riesgo": True})
    r = cliente.post("/api/autodesarrollo/implementar", json={"sugerencia_id": "nope"})
    assert r.status_code == 404


def test_implementar_dispara_en_background_sin_efectos(cliente):
    # Con el flag ON y una sugerencia real, el disparo responde 200 (fake noop: sin git/claude).
    cliente.post("/api/autodesarrollo/flag", json={"activo": True, "confirmo_riesgo": True})
    sid = cliente.post("/api/sugerencias", json={"titulo": "Mejora X"}).json()["sugerencia"]["id"]
    r = cliente.post("/api/autodesarrollo/implementar", json={"sugerencia_id": sid})
    assert r.status_code == 200
    assert "segundo plano" in r.json()["mensaje"].lower()


def test_implementar_falta_sugerencia_id_400(cliente):
    cliente.post("/api/autodesarrollo/flag", json={"activo": True, "confirmo_riesgo": True})
    assert cliente.post("/api/autodesarrollo/implementar", json={}).status_code == 400


def test_disparo_real_recibe_la_sugerencia_completa(entorno):
    """El disparo inyectado recibe el dict de sugerencia (no solo el id)."""
    capturado = {}

    def fake(sugerencia):  # noqa: ANN001
        capturado.update(sugerencia)

    cli = _cliente(disparar_autodesarrollo=fake)
    cli.post("/api/autodesarrollo/flag", json={"activo": True, "confirmo_riesgo": True})
    sid = cli.post("/api/sugerencias", json={"titulo": "Con detalle", "detalle": "hola"}).json()[
        "sugerencia"
    ]["id"]
    cli.post("/api/autodesarrollo/implementar", json={"sugerencia_id": sid})
    assert capturado.get("id") == sid
    assert capturado.get("titulo") == "Con detalle"
