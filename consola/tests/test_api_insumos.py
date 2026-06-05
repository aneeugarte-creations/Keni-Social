"""Tests de la API de Insumos del día (cajones). OFFLINE.

Cubre CRUD de lotes e ítems, listado por día, historial (GET /dias), aportación con
ejecutor falso (SIN claude real), usar→crea contenido, PATCH de ítem, DELETE de lote.
Requiere el Postgres de pruebas (fixture `cliente`); en CI corre con el service postgres.
"""

from __future__ import annotations

import json

# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _fake_ejecutor_items(items: list[dict]) -> object:
    """Devuelve un ejecutor fake que siempre retorna los ítems dados."""

    def _ejecutor(prompt: str, carpeta: str) -> str:
        return json.dumps({"items": items})

    return _ejecutor


# --------------------------------------------------------------------------- #
# GET /api/insumos (listar cajones)                                            #
# --------------------------------------------------------------------------- #


def test_listar_cajones_vacios_devuelve_4_cajones(cliente):
    r = cliente.get("/api/insumos")
    assert r.status_code == 200, r.text
    data = r.json()
    assert "fecha" in data
    cajones = [c["cajon"] for c in data["cajones"]]
    assert cajones == ["portal", "corresponsales", "reporteros", "eventos_claro"]
    for cajon in data["cajones"]:
        assert cajon["lotes"] == []
        assert cajon["items"] == []


def test_listar_por_fecha_especifica(cliente):
    r = cliente.get("/api/insumos?fecha=2026-06-05")
    assert r.status_code == 200
    assert r.json()["fecha"] == "2026-06-05"


def test_listar_cajon_invalido_400(cliente):
    r = cliente.get("/api/insumos?cajon=noexiste")
    assert r.status_code == 400


def test_listar_marca_invalida_400(cliente):
    r = cliente.get("/api/insumos?marca=noexiste")
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# GET /api/insumos/dias                                                        #
# --------------------------------------------------------------------------- #


def test_dias_sin_insumos_devuelve_lista_vacia(cliente):
    r = cliente.get("/api/insumos/dias")
    assert r.status_code == 200
    assert r.json()["dias"] == []


# --------------------------------------------------------------------------- #
# POST /api/insumos/aportar (JSON)                                             #
# --------------------------------------------------------------------------- #


def test_aportar_json_crea_lote_e_items(cliente, monkeypatch):
    # Inyectar el ejecutor falso antes de que la petición llegue al módulo.
    fake_ej = _fake_ejecutor_items([
        {"titulo": "Nota 1", "marca": "unotv", "tipo": "nota"},
        {"titulo": "Nota 2", "marca": "claro-sports", "tipo": "nota"},
    ])
    monkeypatch.setattr(
        "keni_consola.dominio.insumos_parse._ejecutar_claude_json", fake_ej
    )
    r = cliente.post(
        "/api/insumos/aportar",
        json={"cajon": "portal", "texto": "1.- Nota 1\n2.- Nota 2", "fecha": "2026-06-05"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    lote = data["lote"]
    items = data["items"]
    assert lote["cajon"] == "portal"
    assert lote["fecha"] == "2026-06-05"
    assert lote["estado"] == "listo"
    assert lote["total_items"] == 2
    assert len(items) == 2
    assert items[0]["titulo"] == "Nota 1"
    assert items[0]["marca_nombre"] != ""  # resuelto
    assert items[1]["marca"] == "claro-sports"
    # usado viene como bool False
    assert items[0]["usado"] is False


def test_aportar_sin_texto_ni_archivo_400(cliente):
    r = cliente.post("/api/insumos/aportar", json={"cajon": "portal"})
    assert r.status_code == 400


def test_aportar_cajon_invalido_400(cliente):
    r = cliente.post("/api/insumos/aportar", json={"cajon": "basura", "texto": "x"})
    assert r.status_code == 400


def test_aportar_marca_invalida_400(cliente):
    r = cliente.post(
        "/api/insumos/aportar",
        json={"cajon": "portal", "texto": "x", "marca": "noexiste"},
    )
    assert r.status_code == 400


def test_aportar_parse_falla_devuelve_lote_error(cliente, monkeypatch):
    """Si el ejecutor falla completamente, el lote queda en estado error (HTTP 200)."""
    def ejecutor_roto(prompt: str, carpeta: str) -> str:
        raise RuntimeError("claude no disponible en test")

    monkeypatch.setattr(
        "keni_consola.dominio.insumos_parse._ejecutar_claude_json", ejecutor_roto
    )
    r = cliente.post(
        "/api/insumos/aportar",
        json={"cajon": "corresponsales", "texto": "texto de prueba"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["lote"]["estado"] == "error"
    assert data["items"] == []


# --------------------------------------------------------------------------- #
# POST /api/insumos/aportar (multipart)                                        #
# --------------------------------------------------------------------------- #


def test_aportar_multipart_archivo(cliente, monkeypatch):
    fake_ej = _fake_ejecutor_items([{"titulo": "Cobertura Oaxaca", "tipo": "cobertura"}])
    monkeypatch.setattr(
        "keni_consola.dominio.insumos_parse._ejecutar_claude_json", fake_ej
    )
    r = cliente.post(
        "/api/insumos/aportar",
        data={"cajon": "reporteros", "fecha": "2026-06-05"},
        files={"archivo": ("agenda.txt", b"GUARDIA\nCobertura Oaxaca", "text/plain")},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["lote"]["origen_archivo"] == "agenda.txt"
    assert data["items"][0]["titulo"] == "Cobertura Oaxaca"


# --------------------------------------------------------------------------- #
# GET /api/insumos/lote/{id}                                                   #
# --------------------------------------------------------------------------- #


def test_detalle_lote_existente(cliente, monkeypatch):
    fake_ej = _fake_ejecutor_items([{"titulo": "Evento Chivas", "tipo": "evento"}])
    monkeypatch.setattr(
        "keni_consola.dominio.insumos_parse._ejecutar_claude_json", fake_ej
    )
    resp = cliente.post(
        "/api/insumos/aportar",
        json={"cajon": "eventos_claro", "texto": "Chivas vs América"},
    )
    lote_id = resp.json()["lote"]["id"]
    r = cliente.get(f"/api/insumos/lote/{lote_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["lote"]["id"] == lote_id
    assert len(data["items"]) == 1


def test_detalle_lote_inexistente_404(cliente):
    r = cliente.get("/api/insumos/lote/noexiste")
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# PATCH /api/insumos/item/{id}                                                 #
# --------------------------------------------------------------------------- #


def test_editar_item(cliente, monkeypatch):
    fake_ej = _fake_ejecutor_items([{"titulo": "Original", "tipo": "nota"}])
    monkeypatch.setattr(
        "keni_consola.dominio.insumos_parse._ejecutar_claude_json", fake_ej
    )
    items = cliente.post(
        "/api/insumos/aportar",
        json={"cajon": "portal", "texto": "original"},
    ).json()["items"]
    item_id = items[0]["id"]

    r = cliente.patch(
        f"/api/insumos/item/{item_id}",
        json={"titulo": "Editado", "resumen": "nuevo resumen", "marca": "unotv"},
    )
    assert r.status_code == 200, r.text
    item = r.json()["item"]
    assert item["titulo"] == "Editado"
    assert item["resumen"] == "nuevo resumen"
    assert item["marca"] == "unotv"


def test_editar_item_tipo_invalido_400(cliente, monkeypatch):
    fake_ej = _fake_ejecutor_items([{"titulo": "Item"}])
    monkeypatch.setattr(
        "keni_consola.dominio.insumos_parse._ejecutar_claude_json", fake_ej
    )
    item_id = cliente.post(
        "/api/insumos/aportar",
        json={"cajon": "portal", "texto": "x"},
    ).json()["items"][0]["id"]
    r = cliente.patch(f"/api/insumos/item/{item_id}", json={"tipo": "invalido"})
    assert r.status_code == 400


def test_editar_item_inexistente_404(cliente):
    r = cliente.patch("/api/insumos/item/noexiste", json={"titulo": "x"})
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# POST /api/insumos/item/{id}/usar                                             #
# --------------------------------------------------------------------------- #


def test_usar_item_crea_contenido(cliente, monkeypatch):
    fake_ej = _fake_ejecutor_items([{"titulo": "Nota para tablero", "marca": "unotv"}])
    monkeypatch.setattr(
        "keni_consola.dominio.insumos_parse._ejecutar_claude_json", fake_ej
    )
    item_id = cliente.post(
        "/api/insumos/aportar",
        json={"cajon": "portal", "texto": "nota", "fecha": "2026-06-05"},
    ).json()["items"][0]["id"]

    r = cliente.post(f"/api/insumos/item/{item_id}/usar", json={"generar": False})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["item"]["usado"] is True
    assert data["contenido_id"] != ""
    assert data["item"]["contenido_id"] == data["contenido_id"]


def test_usar_item_doble_es_idempotente(cliente, monkeypatch):
    fake_ej = _fake_ejecutor_items([{"titulo": "Nota idempotente", "marca": "unotv"}])
    monkeypatch.setattr(
        "keni_consola.dominio.insumos_parse._ejecutar_claude_json", fake_ej
    )
    item_id = cliente.post(
        "/api/insumos/aportar",
        json={"cajon": "portal", "texto": "nota"},
    ).json()["items"][0]["id"]

    r1 = cliente.post(f"/api/insumos/item/{item_id}/usar", json={"generar": False})
    r2 = cliente.post(f"/api/insumos/item/{item_id}/usar", json={"generar": False})
    assert r1.status_code == 200
    assert r2.status_code == 200
    # Ambas devuelven el mismo contenido_id
    assert r1.json()["contenido_id"] == r2.json()["contenido_id"]


def test_usar_item_inexistente_404(cliente):
    r = cliente.post("/api/insumos/item/noexiste/usar", json={})
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# POST /api/insumos/item/{id}/crear-evento                                     #
# --------------------------------------------------------------------------- #


def _crear_item_evento(cliente, monkeypatch):
    """Crea un ítem en el cajón `eventos_claro` (tipo='evento') y devuelve su id."""
    fake_ej = _fake_ejecutor_items([
        {
            "titulo": "Cruz Azul vs América",
            "fecha": "2026-06-10",
            "hora": "21:00",
            "resumen": "Clip del gol y resumen 1 min",
            "marca": "claro-sports",
            "tipo": "evento",
        }
    ])
    monkeypatch.setattr(
        "keni_consola.dominio.insumos_parse._ejecutar_claude_json", fake_ej
    )
    return cliente.post(
        "/api/insumos/aportar",
        json={"cajon": "eventos_claro", "texto": "x", "fecha": "2026-06-10"},
    ).json()["items"][0]["id"]


def test_crear_evento_crea_evento_y_marca_item_usado(cliente, monkeypatch):
    item_id = _crear_item_evento(cliente, monkeypatch)

    r = cliente.post(f"/api/insumos/item/{item_id}/crear-evento", json={})
    assert r.status_code == 200, r.text
    data = r.json()
    # El ítem queda usado y guarda el id del evento en `contenido_id`.
    assert data["item"]["usado"] is True
    assert data["evento_id"] != ""
    assert data["item"]["contenido_id"] == data["evento_id"]
    # El evento mapea los campos del insumo (resumen → nota).
    evento = data["evento"]
    assert evento["titulo"] == "Cruz Azul vs América"
    assert evento["fecha"] == "2026-06-10"
    assert evento["hora"] == "21:00"
    assert evento["nota"] == "Clip del gol y resumen 1 min"

    # El evento es visible en /api/rota/eventos (recorrido Excel → cajón → evento).
    eventos = cliente.get("/api/rota/eventos?desde=2026-06-10&hasta=2026-06-10").json()["eventos"]
    assert any(e["id"] == data["evento_id"] for e in eventos)


def test_crear_evento_doble_es_idempotente(cliente, monkeypatch):
    item_id = _crear_item_evento(cliente, monkeypatch)

    r1 = cliente.post(f"/api/insumos/item/{item_id}/crear-evento", json={})
    r2 = cliente.post(f"/api/insumos/item/{item_id}/crear-evento", json={})
    assert r1.status_code == 200
    assert r2.status_code == 200
    # La segunda no crea un evento nuevo: devuelve el mismo evento_id.
    assert r1.json()["evento_id"] == r2.json()["evento_id"]


def test_crear_evento_item_inexistente_404(cliente):
    r = cliente.post("/api/insumos/item/noexiste/crear-evento", json={})
    assert r.status_code == 404


def test_crear_evento_propaga_marca_del_item(cliente, monkeypatch):
    """El evento creado desde un ítem de cajón hereda la `marca` del ítem."""
    item_id = _crear_item_evento(cliente, monkeypatch)
    r = cliente.post(f"/api/insumos/item/{item_id}/crear-evento", json={})
    assert r.status_code == 200, r.text
    evento = r.json()["evento"]
    # El ítem fue creado con marca="claro-sports" (ver _crear_item_evento).
    assert evento["marca"] == "claro-sports"


# --------------------------------------------------------------------------- #
# DELETE /api/insumos/lote/{id}                                                #
# --------------------------------------------------------------------------- #


def test_borrar_lote_borra_lote_e_items(cliente, monkeypatch):
    fake_ej = _fake_ejecutor_items([{"titulo": "A borrar"}, {"titulo": "Tambien"}])
    monkeypatch.setattr(
        "keni_consola.dominio.insumos_parse._ejecutar_claude_json", fake_ej
    )
    data = cliente.post(
        "/api/insumos/aportar",
        json={"cajon": "portal", "texto": "contenido"},
    ).json()
    lote_id = data["lote"]["id"]

    r = cliente.delete(f"/api/insumos/lote/{lote_id}")
    assert r.status_code == 200
    assert r.json()["ok"] is True

    # El lote ya no existe.
    assert cliente.get(f"/api/insumos/lote/{lote_id}").status_code == 404


def test_borrar_lote_inexistente_404(cliente):
    r = cliente.delete("/api/insumos/lote/noexiste")
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# Historial de días (GET /dias después de aportar)                             #
# --------------------------------------------------------------------------- #


def test_dias_aparece_despues_de_aportar(cliente, monkeypatch):
    fake_ej = _fake_ejecutor_items([{"titulo": "Nota histórica"}])
    monkeypatch.setattr(
        "keni_consola.dominio.insumos_parse._ejecutar_claude_json", fake_ej
    )
    cliente.post(
        "/api/insumos/aportar",
        json={"cajon": "portal", "texto": "x", "fecha": "2026-05-01"},
    )
    r = cliente.get("/api/insumos/dias")
    assert r.status_code == 200
    dias = r.json()["dias"]
    fechas = [d["fecha"] for d in dias]
    assert "2026-05-01" in fechas
    dia = next(d for d in dias if d["fecha"] == "2026-05-01")
    assert dia["total"] >= 1
    assert "portal" in dia["por_cajon"]


def test_listar_muestra_items_despues_de_aportar(cliente, monkeypatch):
    fake_ej = _fake_ejecutor_items([{"titulo": "Item del día"}])
    monkeypatch.setattr(
        "keni_consola.dominio.insumos_parse._ejecutar_claude_json", fake_ej
    )
    cliente.post(
        "/api/insumos/aportar",
        json={"cajon": "portal", "texto": "x", "fecha": "2026-06-05"},
    )
    r = cliente.get("/api/insumos?fecha=2026-06-05")
    data = r.json()
    portal = next(c for c in data["cajones"] if c["cajon"] == "portal")
    assert len(portal["items"]) >= 1
    assert portal["items"][0]["titulo"] == "Item del día"
    # marca_nombre presente en la respuesta
    assert "marca_nombre" in portal["items"][0]


# --------------------------------------------------------------------------- #
# Frescura: campo `frescura` y filtro `solo_frescos`                           #
# --------------------------------------------------------------------------- #


def test_items_tienen_campo_frescura(cliente, monkeypatch):
    """Todos los ítems de la respuesta deben incluir el campo 'frescura'."""
    fake_ej = _fake_ejecutor_items([{"titulo": "Con frescura", "marca": "unotv"}])
    monkeypatch.setattr(
        "keni_consola.dominio.insumos_parse._ejecutar_claude_json", fake_ej
    )
    cliente.post(
        "/api/insumos/aportar",
        json={"cajon": "portal", "texto": "x", "fecha": "2026-06-05"},
    )
    r = cliente.get("/api/insumos?fecha=2026-06-05")
    assert r.status_code == 200
    portal = next(c for c in r.json()["cajones"] if c["cajon"] == "portal")
    for item in portal["items"]:
        assert "frescura" in item
        assert item["frescura"] in ("fresco", "caduco")


def test_items_sin_linea_son_siempre_frescos(cliente, monkeypatch):
    """Un ítem sin línea asignada debe ser 'fresco' (sin dato = sin caducidad)."""
    fake_ej = _fake_ejecutor_items([{"titulo": "Sin línea", "marca": "unotv", "linea": ""}])
    monkeypatch.setattr(
        "keni_consola.dominio.insumos_parse._ejecutar_claude_json", fake_ej
    )
    # Fecha antigua para que un posible TTL la caduque
    cliente.post(
        "/api/insumos/aportar",
        json={"cajon": "portal", "texto": "x", "fecha": "2020-01-01"},
    )
    r = cliente.get("/api/insumos?fecha=2020-01-01")
    portal = next(c for c in r.json()["cajones"] if c["cajon"] == "portal")
    item = next((i for i in portal["items"] if i["titulo"] == "Sin línea"), None)
    assert item is not None
    assert item["frescura"] == "fresco"


def test_solo_frescos_no_devuelve_caducados(cliente, monkeypatch):
    """Con solo_frescos=1, ítems de líneas con TTL y fecha vieja no aparecen."""
    # Siembra una línea con TTL=1 para unotv (Nacional)
    import keni_consola.repos as repos
    repos.crear_etiqueta(nombre="Nacional-test-ttl", clase="vertical", marca="unotv", ttl_dias=1, es_green=False)

    fecha_vieja = "2020-01-01"

    fake_ej = _fake_ejecutor_items([
        {"titulo": "Noticia vieja", "marca": "unotv", "linea": "Nacional-test-ttl"},
    ])
    monkeypatch.setattr(
        "keni_consola.dominio.insumos_parse._ejecutar_claude_json", fake_ej
    )
    cliente.post(
        "/api/insumos/aportar",
        json={"cajon": "portal", "texto": "x", "fecha": fecha_vieja},
    )

    # Sin filtro: aparece
    r_todos = cliente.get(f"/api/insumos?fecha={fecha_vieja}")
    portal_todos = next(c for c in r_todos.json()["cajones"] if c["cajon"] == "portal")
    titulos_todos = [i["titulo"] for i in portal_todos["items"]]
    assert "Noticia vieja" in titulos_todos

    # Con solo_frescos=1: no aparece (la fecha es muy antigua)
    r_frescos = cliente.get(f"/api/insumos?fecha={fecha_vieja}&solo_frescos=1")
    assert r_frescos.status_code == 200
    portal_frescos = next(c for c in r_frescos.json()["cajones"] if c["cajon"] == "portal")
    titulos_frescos = [i["titulo"] for i in portal_frescos["items"]]
    assert "Noticia vieja" not in titulos_frescos


def test_solo_frescos_mantiene_items_sin_ttl(cliente, monkeypatch):
    """Con solo_frescos=1, ítems de líneas sin TTL (0) o sin línea siguen apareciendo."""
    fecha_vieja = "2020-01-01"

    fake_ej = _fake_ejecutor_items([
        {"titulo": "Evergreen item", "marca": "unotv", "linea": ""},
    ])
    monkeypatch.setattr(
        "keni_consola.dominio.insumos_parse._ejecutar_claude_json", fake_ej
    )
    cliente.post(
        "/api/insumos/aportar",
        json={"cajon": "portal", "texto": "x", "fecha": fecha_vieja},
    )

    r = cliente.get(f"/api/insumos?fecha={fecha_vieja}&solo_frescos=1")
    assert r.status_code == 200
    portal = next(c for c in r.json()["cajones"] if c["cajon"] == "portal")
    titulos = [i["titulo"] for i in portal["items"]]
    assert "Evergreen item" in titulos
