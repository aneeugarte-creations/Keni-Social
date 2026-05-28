"""Tests de la API `/api/rota/piezas` (#150 PARRILLA 2026.xlsx). Todo OFFLINE.

Cubre el contrato HTTP: CRUD, validacion de `evento_id` contra `rota_eventos`,
validacion de `responsable_id` contra usuario real, allowlist de `estado`, longitud de
`enlace`, filtros combinables y el caso "pieza suelta" (`evento_id=""`).

Reusa la fixture `cliente` (token de mantenimiento) y el aislamiento de `entorno`.
"""

from __future__ import annotations

from keni_consola import auth

CLAVE = "clave-de-prueba"

SAB1 = "2026-05-30"


def _crear_evento(cli, **extra) -> dict:
    base = {"titulo": "LIV GOLF Andalucia R1", "fecha": SAB1, "hora": "07:00"}
    base.update(extra)
    r = cli.post("/api/rota/eventos", json=base)
    assert r.status_code == 201, r.text
    return r.json()["evento"]


def _crear_pieza(cli, **cuerpo) -> dict:
    base: dict = {"programa": "MUNDIAL", "contenido_sugerido": "post pre-evento"}
    base.update(cuerpo)
    r = cli.post("/api/rota/piezas", json=base)
    assert r.status_code == 201, r.text
    return r.json()["pieza"]


# --------------------------------------------------------------------------- #
# Crear / listar                                                                #
# --------------------------------------------------------------------------- #


def test_crear_pieza_suelta(cliente):
    p = _crear_pieza(cliente, programa="Álvaro Fidalgo", contenido_sugerido="Reel semanal")
    assert p["id"]
    assert p["programa"] == "Álvaro Fidalgo"
    assert p["evento_id"] == ""
    assert p["estado"] == "pendiente"


def test_crear_pieza_atada_a_evento(cliente):
    ev = _crear_evento(cliente)
    p = _crear_pieza(
        cliente,
        evento_id=ev["id"],
        red_social="FB, IG, X",
        tipo_pieza="IMAGEN",
        dia=SAB1,
    )
    assert p["evento_id"] == ev["id"]
    assert p["red_social"] == "FB, IG, X"
    assert p["tipo_pieza"] == "IMAGEN"


def test_crear_pieza_evento_inexistente_400(cliente):
    r = cliente.post(
        "/api/rota/piezas",
        json={"evento_id": "no-existe", "contenido_sugerido": "x"},
    )
    assert r.status_code == 400


def test_crear_pieza_sin_nada_relevante_400(cliente):
    """Sin evento_id, programa ni contenido_sugerido la pieza no representa nada."""
    r = cliente.post("/api/rota/piezas", json={"red_social": "FB"})
    assert r.status_code == 400


def test_crear_pieza_estado_invalido_400(cliente):
    r = cliente.post(
        "/api/rota/piezas",
        json={"programa": "X", "estado": "raro"},
    )
    assert r.status_code == 400


def test_crear_pieza_enlace_demasiado_largo_400(cliente):
    r = cliente.post(
        "/api/rota/piezas",
        json={"programa": "X", "enlace": "https://" + "a" * 3000},
    )
    assert r.status_code == 400


def test_crear_pieza_responsable_inexistente_400(cliente):
    r = cliente.post(
        "/api/rota/piezas",
        json={"programa": "X", "responsable_id": "u-no-existe"},
    )
    assert r.status_code == 400


def test_listar_piezas_filtro_evento(cliente):
    ev = _crear_evento(cliente)
    atada = _crear_pieza(cliente, evento_id=ev["id"])
    suelta = _crear_pieza(cliente, programa="MUNDIAL")

    r = cliente.get(f"/api/rota/piezas?evento_id={ev['id']}")
    ids = {p["id"] for p in r.json()["piezas"]}
    assert atada["id"] in ids
    assert suelta["id"] not in ids

    # `evento_id=` (cadena vacia explicita) -> piezas sueltas (sin evento).
    r = cliente.get("/api/rota/piezas?evento_id=")
    ids = {p["id"] for p in r.json()["piezas"]}
    assert suelta["id"] in ids
    assert atada["id"] not in ids


def test_listar_piezas_filtro_estado_y_programa(cliente):
    _crear_pieza(cliente, programa="MUNDIAL", estado="pendiente")
    _crear_pieza(cliente, programa="MUNDIAL", estado="listo")
    _crear_pieza(cliente, programa="Real Oviedo", estado="listo")

    r = cliente.get("/api/rota/piezas?programa=MUNDIAL&estado=listo")
    piezas = r.json()["piezas"]
    assert len(piezas) == 1
    assert piezas[0]["programa"] == "MUNDIAL"
    assert piezas[0]["estado"] == "listo"


def test_listar_piezas_rango_dia(cliente):
    _crear_pieza(cliente, dia="2026-06-01")
    _crear_pieza(cliente, dia="2026-06-10")
    _crear_pieza(cliente, dia="2026-06-20")
    r = cliente.get("/api/rota/piezas?desde=2026-06-05&hasta=2026-06-15")
    piezas = r.json()["piezas"]
    assert len(piezas) == 1
    assert piezas[0]["dia"] == "2026-06-10"


def test_listar_piezas_estado_invalido_400(cliente):
    r = cliente.get("/api/rota/piezas?estado=raro")
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Actualizar / borrar                                                           #
# --------------------------------------------------------------------------- #


def test_actualizar_pieza_cambia_estado_y_publicado(cliente):
    p = _crear_pieza(cliente)
    r = cliente.patch(
        f"/api/rota/piezas/{p['id']}", json={"estado": "listo", "publicado": True}
    )
    assert r.status_code == 200
    pieza = r.json()["pieza"]
    assert pieza["estado"] == "listo"
    assert pieza["publicado"] is True


def test_actualizar_pieza_workflow_booleanos(cliente):
    p = _crear_pieza(cliente)
    r = cliente.patch(
        f"/api/rota/piezas/{p['id']}",
        json={
            "material_entregado": True,
            "contenido_entregado": True,
            "publicado": False,
            "enlace": "https://example.com/post/abc",
        },
    )
    assert r.status_code == 200
    pieza = r.json()["pieza"]
    assert pieza["material_entregado"] is True
    assert pieza["contenido_entregado"] is True
    assert pieza["publicado"] is False
    assert pieza["enlace"] == "https://example.com/post/abc"


def test_actualizar_pieza_responsable_se_resuelve(cliente):
    """Asignar un `responsable_id` real rellena `responsable_nombre` desde auth."""
    usuario = auth.crear_usuario("ana", CLAVE, "editor")
    p = _crear_pieza(cliente)
    r = cliente.patch(
        f"/api/rota/piezas/{p['id']}", json={"responsable_id": usuario["id"]}
    )
    assert r.status_code == 200
    pieza = r.json()["pieza"]
    assert pieza["responsable_id"] == usuario["id"]
    assert pieza["responsable_nombre"] == "ana"

    # Desasignar limpia ambas columnas.
    r = cliente.patch(
        f"/api/rota/piezas/{p['id']}", json={"responsable_id": ""}
    )
    pieza = r.json()["pieza"]
    assert pieza["responsable_id"] == ""
    assert pieza["responsable_nombre"] == ""


def test_actualizar_pieza_responsable_invalido_400(cliente):
    p = _crear_pieza(cliente)
    r = cliente.patch(
        f"/api/rota/piezas/{p['id']}", json={"responsable_id": "no-existe"}
    )
    assert r.status_code == 400


def test_actualizar_pieza_evento_inexistente_400(cliente):
    p = _crear_pieza(cliente)
    r = cliente.patch(
        f"/api/rota/piezas/{p['id']}", json={"evento_id": "no-existe"}
    )
    assert r.status_code == 400


def test_actualizar_pieza_estado_invalido_400(cliente):
    p = _crear_pieza(cliente)
    r = cliente.patch(
        f"/api/rota/piezas/{p['id']}", json={"estado": "raro"}
    )
    assert r.status_code == 400


def test_actualizar_pieza_inexistente_404(cliente):
    r = cliente.patch("/api/rota/piezas/no-existe", json={"estado": "listo"})
    assert r.status_code == 404


def test_borrar_pieza(cliente):
    p = _crear_pieza(cliente)
    r = cliente.delete(f"/api/rota/piezas/{p['id']}")
    assert r.status_code == 200
    r = cliente.delete(f"/api/rota/piezas/{p['id']}")
    assert r.status_code == 404
