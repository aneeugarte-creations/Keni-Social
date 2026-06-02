"""Tests de la API de Plantillas de CONTENIDO (catálogo unificado, `/api/plantillas-contenido`).

Cubre los dos modos del catálogo unificado:
  - 'estructura': cuerpo con `{{variables}}` + `aplicar` que compone el copy.
  - 'plano':      `contenido` directo; `aplicar` lo devuelve tal cual.
y la coherencia modo<->cuerpo en alta/edición. OFFLINE, DB en Postgres de pruebas.
"""

from __future__ import annotations


def test_crear_estructura_y_aplicar(cliente):
    r = cliente.post(
        "/api/plantillas-contenido",
        json={
            "nombre": "Gol",
            "modo": "estructura",
            "estructura": "¡GOL de {{equipo}}! {{jugador}}.",
            "variables": [{"clave": "equipo", "etiqueta": "Equipo", "ejemplo": "Águilas"}],
        },
    )
    assert r.status_code == 200, r.text
    p = r.json()["plantilla"]
    assert p["modo"] == "estructura"
    assert p["contenido"] == ""

    ap = cliente.post(
        f"/api/plantillas-contenido/{p['id']}/aplicar",
        json={"valores": {"equipo": "Águilas", "jugador": "Pérez"}},
    )
    assert ap.status_code == 200
    assert ap.json()["copy"] == "¡GOL de Águilas! Pérez."
    assert ap.json()["faltan"] == []


def test_crear_plano_y_aplicar_devuelve_contenido(cliente):
    r = cliente.post(
        "/api/plantillas-contenido",
        json={"nombre": "Despedida", "modo": "plano", "contenido": "¡Gracias por seguirnos!"},
    )
    assert r.status_code == 200, r.text
    p = r.json()["plantilla"]
    assert p["modo"] == "plano"
    assert p["contenido"] == "¡Gracias por seguirnos!"
    assert p["estructura"] == ""

    ap = cliente.post(f"/api/plantillas-contenido/{p['id']}/aplicar", json={"valores": {}})
    assert ap.status_code == 200
    assert ap.json() == {"copy": "¡Gracias por seguirnos!", "faltan": []}


def test_plano_exige_contenido(cliente):
    r = cliente.post(
        "/api/plantillas-contenido", json={"nombre": "X", "modo": "plano", "contenido": "  "}
    )
    assert r.status_code == 400


def test_estructura_exige_estructura(cliente):
    r = cliente.post(
        "/api/plantillas-contenido", json={"nombre": "X", "modo": "estructura", "estructura": ""}
    )
    assert r.status_code == 400


def test_modo_invalido_rechazado(cliente):
    r = cliente.post(
        "/api/plantillas-contenido", json={"nombre": "X", "modo": "raro", "contenido": "a"}
    )
    assert r.status_code == 400


def test_cambiar_a_plano_requiere_contenido_coherente(cliente):
    p = cliente.post(
        "/api/plantillas-contenido",
        json={"nombre": "T", "modo": "estructura", "estructura": "Hola {{x}}"},
    ).json()["plantilla"]
    # Cambiar a plano sin dar contenido (y el guardado está vacío) -> 400.
    r = cliente.put(f"/api/plantillas-contenido/{p['id']}", json={"modo": "plano"})
    assert r.status_code == 400
    # Con contenido, OK.
    r = cliente.put(
        f"/api/plantillas-contenido/{p['id']}", json={"modo": "plano", "contenido": "Texto fijo"}
    )
    assert r.status_code == 200
    assert r.json()["plantilla"]["modo"] == "plano"


def test_clave_variable_debe_empezar_por_letra(cliente):
    # La clave de una variable DEBE empezar por letra: `123` o `_x` se rechazan (400).
    for clave_mala in ("123", "_x", "9gol"):
        r = cliente.post(
            "/api/plantillas-contenido",
            json={
                "nombre": "T",
                "modo": "estructura",
                "estructura": "Hola {{x}}",
                "variables": [{"clave": clave_mala}],
            },
        )
        assert r.status_code == 400, f"{clave_mala} debió rechazarse: {r.text}"
    # Una clave válida (empieza por letra) sí se acepta.
    r = cliente.post(
        "/api/plantillas-contenido",
        json={
            "nombre": "T2",
            "modo": "estructura",
            "estructura": "Hola {{equipo1}}",
            "variables": [{"clave": "equipo1"}],
        },
    )
    assert r.status_code == 200, r.text


def test_default_modo_estructura_compatibilidad(cliente):
    # Sin `modo`, el alta sigue siendo de estructura (compatibilidad con clientes viejos).
    r = cliente.post(
        "/api/plantillas-contenido", json={"nombre": "Compat", "estructura": "Hola {{x}}"}
    )
    assert r.status_code == 200
    assert r.json()["plantilla"]["modo"] == "estructura"
