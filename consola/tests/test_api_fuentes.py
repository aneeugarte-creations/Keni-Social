"""Tests de la API del hub generico de fuentes (/api/fuentes, item G). OFFLINE.

Cubre el CRUD del hub (crear/listar/editar/borrar), la validacion (tipo/marca/config) y la
presencia del estado de agencias (Reuters/AFP) en el listado. Requiere el Postgres de
pruebas (fixture `cliente`); en CI corre con el service postgres, en local se salta.
"""

from __future__ import annotations


def test_crear_fuente_hub_y_listar(cliente):
    r = cliente.post(
        "/api/fuentes",
        json={
            "tipo": "idea",
            "nombre": "Lluvia de ideas",
            "marca": "unotv",
            "prioridad": 5,
            "etiquetas": ["deportes"],
            "config": {"nota": "x"},
        },
    )
    assert r.status_code == 200, r.text
    f = r.json()["fuente"]
    assert f["tipo"] == "idea"
    assert f["nombre"] == "Lluvia de ideas"
    assert f["marca_nombre"] == "UnoTV"
    assert f["prioridad"] == 5
    assert f["etiquetas"] == ["deportes"]
    assert f["config"] == {"nota": "x"}

    listado = cliente.get("/api/fuentes").json()
    assert len(listado["fuentes"]) == 1
    # El estado de las agencias viene SIEMPRE (Reuters/AFP), gateado por credencial.
    assert {a["red"] for a in listado["agencias"]} == {"reuters", "afp"}
    # Sin credenciales en el entorno de test, ambas estan pendientes.
    assert all(not a["disponible"] for a in listado["agencias"])


def test_crear_fuente_hub_tipo_invalido_400(cliente):
    r = cliente.post("/api/fuentes", json={"tipo": "loquesea", "nombre": "X"})
    assert r.status_code == 400


def test_crear_fuente_hub_nombre_obligatorio_400(cliente):
    r = cliente.post("/api/fuentes", json={"tipo": "rss", "nombre": "  "})
    assert r.status_code == 400


def test_crear_fuente_hub_marca_invalida_400(cliente):
    r = cliente.post("/api/fuentes", json={"tipo": "rss", "nombre": "X", "marca": "noexiste"})
    assert r.status_code == 400


def test_crear_fuente_hub_config_no_objeto_400(cliente):
    r = cliente.post("/api/fuentes", json={"tipo": "rss", "nombre": "X", "config": "texto"})
    assert r.status_code == 400


def test_listar_fuentes_hub_filtra_por_tipo(cliente):
    cliente.post("/api/fuentes", json={"tipo": "idea", "nombre": "I"})
    cliente.post("/api/fuentes", json={"tipo": "galeria", "nombre": "G"})
    solo_ideas = cliente.get("/api/fuentes?tipo=idea").json()["fuentes"]
    assert [f["nombre"] for f in solo_ideas] == ["I"]


def test_actualizar_fuente_hub_parcial(cliente):
    fid = cliente.post("/api/fuentes", json={"tipo": "idea", "nombre": "I"}).json()["fuente"]["id"]
    r = cliente.put(f"/api/fuentes/{fid}", json={"activo": False, "prioridad": 9})
    assert r.status_code == 200
    f = r.json()["fuente"]
    assert f["activo"] is False
    assert f["prioridad"] == 9


def test_actualizar_fuente_hub_inexistente_404(cliente):
    assert cliente.put("/api/fuentes/nope", json={"activo": False}).status_code == 404


def test_borrar_fuente_hub(cliente):
    fid = cliente.post("/api/fuentes", json={"tipo": "idea", "nombre": "I"}).json()["fuente"]["id"]
    assert cliente.delete(f"/api/fuentes/{fid}").status_code == 200
    assert cliente.delete(f"/api/fuentes/{fid}").status_code == 404


def test_fuentes_rss_se_espejan_en_el_hub(cliente):
    # Una fuente RSS creada por la API RSS debe aparecer ESPEJADA en el hub (tipo 'rss').
    # La siembra corre al asegurar el esquema; tras crear un RSS, forzamos un re-arranque
    # de persistencia para que el espejo aparezca (idempotente).
    from keni_consola import db

    cliente.post(
        "/api/rss/fuentes", json={"nombre": "Diario", "url": "https://93.184.216.34/feed.xml"}
    )
    con = db._conectar()
    try:
        db._sembrar_fuentes_hub_desde_rss(con)
        con.commit()
    finally:
        con.close()
    rss_en_hub = [f for f in cliente.get("/api/fuentes?tipo=rss").json()["fuentes"]]
    assert any(f["nombre"] == "Diario" and f["origen_rss_id"] for f in rss_en_hub)
