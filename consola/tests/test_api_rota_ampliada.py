"""Tests de la AMPLIACION del backend de la rota (auditoria post-piloto).

Cubre lo que se anadio al cerrar los gaps que dejo la auditoria:

  - CRUD `rota_turnos` completo: POST directo, DELETE individual, lote/borrar.
  - CRUD `rota_eventos` ampliado: duplicar (sin turnos; `cambiado` reset).
  - Validacion cruzada `rota_turnos_trabajo` vs `rota_ausencias` (override exigido).

Reusa `cliente` (token de mantenimiento) y el aislamiento de `entorno`.
"""

from __future__ import annotations

# Fechas de referencia.
SAB1 = "2026-05-30"


def _crear_evento(cli, **extra) -> dict:
    base = {"titulo": "Partido", "fecha": SAB1, "hora": "16:00", "contenido": "Clip del gol"}
    base.update(extra)
    r = cli.post("/api/rota/eventos", json=base)
    assert r.status_code == 201, r.text
    return r.json()["evento"]


# --------------------------------------------------------------------------- #
# Duplicar evento                                                               #
# --------------------------------------------------------------------------- #


def test_duplicar_evento_y_cambiado_reset(cliente):
    """Duplicar un evento da uno NUEVO con `cambiado=0` (no reprogramado).

    Modelo ola back3: los turnos no van atados a eventos, asi que la cuestion de
    "no se clonan turnos" es trivial (no habia nada que clonar). El clon nace fresco.
    """
    original = _crear_evento(cliente, titulo="Pumas vs America J17", hora="16:00")
    # Lo marcamos como reprogramado (cambiado=1).
    cliente.patch(f"/api/rota/eventos/{original['id']}", json={"hora": "18:00"})
    actualizado = cliente.get(
        f"/api/rota/eventos?desde={SAB1}&hasta={SAB1}"
    ).json()["eventos"]
    assert any(e["id"] == original["id"] and e["cambiado"] for e in actualizado)

    # Duplicar para Jornada 18.
    r = cliente.post(
        f"/api/rota/eventos/{original['id']}/duplicar",
        json={"fecha": "2026-06-06", "titulo": "Pumas vs America J18"},
    )
    assert r.status_code == 201, r.text
    clon = r.json()["evento"]
    assert clon["id"] != original["id"]
    assert clon["fecha"] == "2026-06-06"
    assert clon["titulo"] == "Pumas vs America J18"
    assert clon["cambiado"] is False


def test_duplicar_evento_propaga_marca(cliente):
    """El clon HEREDA la marca del original (regresion auditoria-turnos hallazgo A).

    Sin esto el clon nacia con marca="" e INVISIBLE en toda vista filtrada por marca
    (la rejilla y el export de Claro Sports): el caso estrella "Jornada 17 -> 18" se
    duplicaba y "desaparecia", obligando a recrear el partido a mano.
    """
    original = _crear_evento(cliente, titulo="Pumas vs America J17", marca="claro-sports")
    assert original["marca"] == "claro-sports"
    r = cliente.post(
        f"/api/rota/eventos/{original['id']}/duplicar",
        json={"fecha": "2026-06-06", "titulo": "Pumas vs America J18"},
    )
    assert r.status_code == 201, r.text
    clon = r.json()["evento"]
    assert clon["marca"] == "claro-sports"
    # Y aparece en la vista scopeada por marca (no solo en el agregado "Todas").
    visibles = cliente.get(
        f"/api/rota/eventos?desde=2026-06-06&hasta=2026-06-06&marca=claro-sports"
    ).json()["eventos"]
    assert any(e["id"] == clon["id"] for e in visibles)


def test_duplicar_evento_inexistente_404(cliente):
    r = cliente.post("/api/rota/eventos/no-existe/duplicar", json={})
    assert r.status_code == 404


def test_duplicar_evento_titulo_vacio_400(cliente):
    original = _crear_evento(cliente)
    r = cliente.post(
        f"/api/rota/eventos/{original['id']}/duplicar", json={"titulo": "   "}
    )
    assert r.status_code == 400


def test_duplicar_evento_fecha_invalida_400(cliente):
    original = _crear_evento(cliente)
    r = cliente.post(
        f"/api/rota/eventos/{original['id']}/duplicar", json={"fecha": "no-fecha"}
    )
    assert r.status_code == 400
