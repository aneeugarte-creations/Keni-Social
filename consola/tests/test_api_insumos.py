"""Tests de la API de Insumos del día (cajones). OFFLINE.

Cubre CRUD de lotes e ítems, listado por día, historial (GET /dias), aportación ASÍNCRONA
(el parseo corre en el WORKER, no en el back: el back no tiene `claude`), usar→crea
contenido, PATCH de ítem, DELETE de lote. Requiere el Postgres de pruebas (fixture
`cliente`); en CI corre con el service postgres.

FLUJO ASÍNCRONO: `POST /aportar` crea el lote en estado `parseando` y ENCOLA un job. En los
tests inyectamos `lanzar_generacion=lanzador_generacion_completa(<salida canned>)`, que corre
el `procesar` REAL (parsea la salida de Haiku, inserta los ítems y deja el lote `listo`/
`error`) de forma SÍNCRONA. Así cubrimos el post-procesado sin tocar `claude`.
"""

from __future__ import annotations

import json

from .conftest import _cliente, lanzador_generacion_completa

# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _salida_items(items: list[dict]) -> str:
    """Salida canned de Haiku: el JSON `{"items":[...]}` que el `procesar` parsea."""
    return json.dumps({"items": items})


def _cliente_con_items(items: list[dict]):
    """Cliente cuyo lanzador de generación COMPLETA el job con `items` (corre `procesar`)."""
    return _cliente(lanzar_generacion=lanzador_generacion_completa(_salida_items(items)))


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
# POST /api/insumos/aportar (JSON) — flujo asíncrono                           #
# --------------------------------------------------------------------------- #


def test_aportar_json_encola_y_procesa_items():
    """`aportar` crea el lote `parseando`, encola, y el `procesar` inserta los ítems y lo deja `listo`."""
    cli = _cliente_con_items([
        {"titulo": "Nota 1", "marca": "unotv", "tipo": "nota"},
        {"titulo": "Nota 2", "marca": "claro-sports", "tipo": "nota"},
    ])
    r = cli.post(
        "/api/insumos/aportar",
        json={"cajon": "portal", "texto": "1.- Nota 1\n2.- Nota 2", "fecha": "2026-06-05"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    lote = data["lote"]
    assert lote["cajon"] == "portal"
    assert lote["fecha"] == "2026-06-05"
    # `lanzador_generacion_completa` corre `procesar` SÍNCRONO, así que el lote ya quedó listo.
    assert lote["estado"] == "listo"
    assert lote["total_items"] == 2
    # La respuesta trae la generación encolada (para sondeo del SPA).
    assert data["generacion"] is not None
    assert data["generacion"]["tipo"] == "insumos"

    # Los ítems están en el detalle del lote.
    detalle = cli.get(f"/api/insumos/lote/{lote['id']}").json()
    items = detalle["items"]
    assert len(items) == 2
    assert items[0]["titulo"] == "Nota 1"
    assert items[0]["marca_nombre"] != ""  # resuelto
    assert items[1]["marca"] == "claro-sports"
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


def test_aportar_lote_nace_parseando_sin_worker(cliente):
    """Con el lanzador NOOP (no corre `procesar`), el lote queda en `parseando` (worker pendiente)."""
    # El `cliente` por defecto usa el lanzador NOOP: encola pero NO corre `procesar`.
    r = cliente.post(
        "/api/insumos/aportar",
        json={"cajon": "portal", "texto": "1.- Nota", "fecha": "2026-06-05"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["lote"]["estado"] == "parseando"
    assert data["generacion"] is not None


def test_aportar_parse_falla_deja_lote_error(cliente):
    """Si la salida del asistente no es JSON legible, el `procesar` deja el lote en `error`."""
    cli = _cliente(lanzar_generacion=lanzador_generacion_completa("esto no es json"))
    r = cli.post(
        "/api/insumos/aportar",
        json={"cajon": "corresponsales", "texto": "texto de prueba"},
    )
    assert r.status_code == 200, r.text
    lote = r.json()["lote"]
    assert lote["estado"] == "error"
    detalle = cli.get(f"/api/insumos/lote/{lote['id']}").json()
    assert detalle["items"] == []


# --------------------------------------------------------------------------- #
# POST /api/insumos/aportar (multipart)                                        #
# --------------------------------------------------------------------------- #


def test_aportar_multipart_archivo():
    cli = _cliente_con_items([{"titulo": "Cobertura Oaxaca", "tipo": "cobertura"}])
    r = cli.post(
        "/api/insumos/aportar",
        data={"cajon": "reporteros", "fecha": "2026-06-05"},
        files={"archivo": ("agenda.txt", b"GUARDIA\nCobertura Oaxaca", "text/plain")},
    )
    assert r.status_code == 200, r.text
    lote = r.json()["lote"]
    assert lote["origen_archivo"] == "agenda.txt"
    assert lote["estado"] == "listo"
    detalle = cli.get(f"/api/insumos/lote/{lote['id']}").json()
    assert detalle["items"][0]["titulo"] == "Cobertura Oaxaca"


# --------------------------------------------------------------------------- #
# Helpers para crear ítems vía el flujo asíncrono                              #
# --------------------------------------------------------------------------- #


def _aportar_un_item(cli, *, cajon: str, fecha: str = "2026-06-05"):
    """Aporta a `cajon` y devuelve (lote_id, item_id) del PRIMER ítem que el procesar insertó.

    `cli` ya fue construido con `lanzador_generacion_completa(...)`, así que su salida canned
    define qué ítems se insertan; aquí solo disparamos el aporte y leemos el primero.
    """
    r = cli.post(
        "/api/insumos/aportar",
        json={"cajon": cajon, "texto": "x", "fecha": fecha},
    )
    lote_id = r.json()["lote"]["id"]
    detalle = cli.get(f"/api/insumos/lote/{lote_id}").json()
    return lote_id, detalle["items"][0]["id"]


# --------------------------------------------------------------------------- #
# GET /api/insumos/lote/{id}                                                   #
# --------------------------------------------------------------------------- #


def test_detalle_lote_existente():
    cli = _cliente_con_items([{"titulo": "Evento Chivas", "tipo": "evento"}])
    resp = cli.post(
        "/api/insumos/aportar",
        json={"cajon": "eventos_claro", "texto": "Chivas vs América"},
    )
    lote_id = resp.json()["lote"]["id"]
    r = cli.get(f"/api/insumos/lote/{lote_id}")
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


def test_editar_item():
    cli = _cliente_con_items([{"titulo": "Original", "tipo": "nota"}])
    _, item_id = _aportar_un_item(cli, cajon="portal")
    r = cli.patch(
        f"/api/insumos/item/{item_id}",
        json={"titulo": "Editado", "resumen": "nuevo resumen", "marca": "unotv"},
    )
    assert r.status_code == 200, r.text
    item = r.json()["item"]
    assert item["titulo"] == "Editado"
    assert item["resumen"] == "nuevo resumen"
    assert item["marca"] == "unotv"


def test_editar_item_tipo_invalido_400():
    cli = _cliente_con_items([{"titulo": "Item"}])
    _, item_id = _aportar_un_item(cli, cajon="portal")
    r = cli.patch(f"/api/insumos/item/{item_id}", json={"tipo": "invalido"})
    assert r.status_code == 400


def test_editar_item_inexistente_404(cliente):
    r = cliente.patch("/api/insumos/item/noexiste", json={"titulo": "x"})
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# POST /api/insumos/item/{id}/usar                                             #
# --------------------------------------------------------------------------- #


def test_usar_item_crea_contenido():
    cli = _cliente_con_items([{"titulo": "Nota para tablero", "marca": "unotv"}])
    _, item_id = _aportar_un_item(cli, cajon="portal")
    r = cli.post(f"/api/insumos/item/{item_id}/usar", json={"generar": False})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["item"]["usado"] is True
    assert data["contenido_id"] != ""
    assert data["item"]["contenido_id"] == data["contenido_id"]


def test_usar_item_doble_es_idempotente():
    cli = _cliente_con_items([{"titulo": "Nota idempotente", "marca": "unotv"}])
    _, item_id = _aportar_un_item(cli, cajon="portal")
    r1 = cli.post(f"/api/insumos/item/{item_id}/usar", json={"generar": False})
    r2 = cli.post(f"/api/insumos/item/{item_id}/usar", json={"generar": False})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["contenido_id"] == r2.json()["contenido_id"]


def test_usar_item_inexistente_404(cliente):
    r = cliente.post("/api/insumos/item/noexiste/usar", json={})
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# POST /api/insumos/item/{id}/crear-evento                                     #
# --------------------------------------------------------------------------- #


def _crear_item_evento(cli):
    """Crea un ítem en el cajón `eventos_claro` (tipo='evento') y devuelve su id."""
    r = cli.post(
        "/api/insumos/aportar",
        json={"cajon": "eventos_claro", "texto": "x", "fecha": "2026-06-10"},
    )
    lote_id = r.json()["lote"]["id"]
    return cli.get(f"/api/insumos/lote/{lote_id}").json()["items"][0]["id"]


def _cliente_evento():
    return _cliente_con_items([
        {
            "titulo": "Cruz Azul vs América",
            "fecha": "2026-06-10",
            "hora": "21:00",
            "resumen": "Clip del gol y resumen 1 min",
            "marca": "claro-sports",
            "tipo": "evento",
        }
    ])


def test_crear_evento_crea_evento_y_marca_item_usado():
    cli = _cliente_evento()
    item_id = _crear_item_evento(cli)
    r = cli.post(f"/api/insumos/item/{item_id}/crear-evento", json={})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["item"]["usado"] is True
    assert data["evento_id"] != ""
    assert data["item"]["contenido_id"] == data["evento_id"]
    evento = data["evento"]
    assert evento["titulo"] == "Cruz Azul vs América"
    assert evento["fecha"] == "2026-06-10"
    assert evento["hora"] == "21:00"
    assert evento["nota"] == "Clip del gol y resumen 1 min"

    eventos = cli.get("/api/rota/eventos?desde=2026-06-10&hasta=2026-06-10").json()["eventos"]
    assert any(e["id"] == data["evento_id"] for e in eventos)


def test_crear_evento_doble_es_idempotente():
    cli = _cliente_evento()
    item_id = _crear_item_evento(cli)
    r1 = cli.post(f"/api/insumos/item/{item_id}/crear-evento", json={})
    r2 = cli.post(f"/api/insumos/item/{item_id}/crear-evento", json={})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["evento_id"] == r2.json()["evento_id"]


def test_crear_evento_item_inexistente_404(cliente):
    r = cliente.post("/api/insumos/item/noexiste/crear-evento", json={})
    assert r.status_code == 404


def test_crear_evento_propaga_marca_del_item():
    cli = _cliente_evento()
    item_id = _crear_item_evento(cli)
    r = cli.post(f"/api/insumos/item/{item_id}/crear-evento", json={})
    assert r.status_code == 200, r.text
    evento = r.json()["evento"]
    assert evento["marca"] == "claro-sports"


# --------------------------------------------------------------------------- #
# DELETE /api/insumos/lote/{id}                                                #
# --------------------------------------------------------------------------- #


def test_borrar_lote_borra_lote_e_items():
    cli = _cliente_con_items([{"titulo": "A borrar"}, {"titulo": "Tambien"}])
    data = cli.post(
        "/api/insumos/aportar",
        json={"cajon": "portal", "texto": "contenido"},
    ).json()
    lote_id = data["lote"]["id"]

    r = cli.delete(f"/api/insumos/lote/{lote_id}")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert cli.get(f"/api/insumos/lote/{lote_id}").status_code == 404


def test_borrar_lote_inexistente_404(cliente):
    r = cliente.delete("/api/insumos/lote/noexiste")
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# Historial de días (GET /dias después de aportar)                             #
# --------------------------------------------------------------------------- #


def test_dias_aparece_despues_de_aportar():
    cli = _cliente_con_items([{"titulo": "Nota histórica"}])
    cli.post(
        "/api/insumos/aportar",
        json={"cajon": "portal", "texto": "x", "fecha": "2026-05-01"},
    )
    r = cli.get("/api/insumos/dias")
    assert r.status_code == 200
    dias = r.json()["dias"]
    fechas = [d["fecha"] for d in dias]
    assert "2026-05-01" in fechas
    dia = next(d for d in dias if d["fecha"] == "2026-05-01")
    assert dia["total"] >= 1
    assert "portal" in dia["por_cajon"]


def test_listar_muestra_items_despues_de_aportar():
    cli = _cliente_con_items([{"titulo": "Item del día"}])
    cli.post(
        "/api/insumos/aportar",
        json={"cajon": "portal", "texto": "x", "fecha": "2026-06-05"},
    )
    r = cli.get("/api/insumos?fecha=2026-06-05")
    data = r.json()
    portal = next(c for c in data["cajones"] if c["cajon"] == "portal")
    assert len(portal["items"]) >= 1
    assert portal["items"][0]["titulo"] == "Item del día"
    assert "marca_nombre" in portal["items"][0]


# --------------------------------------------------------------------------- #
# Frescura: campo `frescura` y filtro `solo_frescos`                           #
# --------------------------------------------------------------------------- #


def test_items_tienen_campo_frescura():
    cli = _cliente_con_items([{"titulo": "Con frescura", "marca": "unotv"}])
    cli.post(
        "/api/insumos/aportar",
        json={"cajon": "portal", "texto": "x", "fecha": "2026-06-05"},
    )
    r = cli.get("/api/insumos?fecha=2026-06-05")
    assert r.status_code == 200
    portal = next(c for c in r.json()["cajones"] if c["cajon"] == "portal")
    for item in portal["items"]:
        assert "frescura" in item
        assert item["frescura"] in ("fresco", "caduco")


def test_items_sin_linea_son_siempre_frescos():
    cli = _cliente_con_items([{"titulo": "Sin línea", "marca": "unotv", "linea": ""}])
    cli.post(
        "/api/insumos/aportar",
        json={"cajon": "portal", "texto": "x", "fecha": "2020-01-01"},
    )
    r = cli.get("/api/insumos?fecha=2020-01-01")
    portal = next(c for c in r.json()["cajones"] if c["cajon"] == "portal")
    item = next((i for i in portal["items"] if i["titulo"] == "Sin línea"), None)
    assert item is not None
    assert item["frescura"] == "fresco"


def test_solo_frescos_no_devuelve_caducados():
    """Con solo_frescos=1, ítems de líneas con TTL y fecha vieja no aparecen."""
    import keni_consola.repos as repos
    repos.crear_etiqueta(nombre="Nacional-test-ttl", clase="vertical", marca="unotv", ttl_dias=1, es_green=False)

    fecha_vieja = "2020-01-01"
    cli = _cliente_con_items([
        {"titulo": "Noticia vieja", "marca": "unotv", "linea": "Nacional-test-ttl"},
    ])
    cli.post(
        "/api/insumos/aportar",
        json={"cajon": "portal", "texto": "x", "fecha": fecha_vieja},
    )

    r_todos = cli.get(f"/api/insumos?fecha={fecha_vieja}")
    portal_todos = next(c for c in r_todos.json()["cajones"] if c["cajon"] == "portal")
    titulos_todos = [i["titulo"] for i in portal_todos["items"]]
    assert "Noticia vieja" in titulos_todos

    r_frescos = cli.get(f"/api/insumos?fecha={fecha_vieja}&solo_frescos=1")
    assert r_frescos.status_code == 200
    portal_frescos = next(c for c in r_frescos.json()["cajones"] if c["cajon"] == "portal")
    titulos_frescos = [i["titulo"] for i in portal_frescos["items"]]
    assert "Noticia vieja" not in titulos_frescos


def test_solo_frescos_mantiene_items_sin_ttl():
    """Con solo_frescos=1, ítems de líneas sin TTL (0) o sin línea siguen apareciendo."""
    fecha_vieja = "2020-01-01"
    cli = _cliente_con_items([
        {"titulo": "Evergreen item", "marca": "unotv", "linea": ""},
    ])
    cli.post(
        "/api/insumos/aportar",
        json={"cajon": "portal", "texto": "x", "fecha": fecha_vieja},
    )

    r = cli.get(f"/api/insumos?fecha={fecha_vieja}&solo_frescos=1")
    assert r.status_code == 200
    portal = next(c for c in r.json()["cajones"] if c["cajon"] == "portal")
    titulos = [i["titulo"] for i in portal["items"]]
    assert "Evergreen item" in titulos
