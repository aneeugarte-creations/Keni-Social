"""Tests del Carril Rápido de Breaking (dominio + API).

Cubre:
  - `dominio.breaking.items_breaking`: selección pura desde el snapshot.
  - `dominio.breaking.anotar_estado_borrador`: cruce con el tablero.
  - `breaking_daemon.items_a_preparar`: selección pura con dedup + cap.
  - `GET /api/breaking`: devuelve items del snapshot con estado_borrador.
  - `POST /api/breaking/preparar`: crea DRAFT + genera copy (lanzador falso).
"""

from __future__ import annotations

from keni_consola import breaking_daemon as daemon
from keni_consola.dominio import breaking as dom

# --------------------------------------------------------------------------- #
# Helpers de fabricación de items fake
# --------------------------------------------------------------------------- #

def _item_radar(**kw):
    """Fila simulada del snapshot del Investigador."""
    base = {
        "titulo": "Gol de último minuto",
        "senal": 80_000,
        "senal_texto": "80K+",
        "breaking": True,
        "idioma": "es",
        "fuentes": '["Google Trends"]',
        "enlaces": "[]",
        "creado": "2026-06-05T10:00:00",
        "actualizado": "2026-06-05T10:00:00",
        "clave": dom.clave_de_titulo("Gol de último minuto"),
    }
    base.update(kw)
    return base


def _item_contenido(**kw):
    """Fila simulada del tablero (contenido.origen='breaking')."""
    base = {
        "id": "c-1",
        "titulo": "Gol de último minuto",
        "origen": "breaking",
        "clase": "contenido",
        "marca": "claro-sports",
        "estado": "pendiente",
    }
    base.update(kw)
    return base


# --------------------------------------------------------------------------- #
# Tests de dominio puro (sin DB)
# --------------------------------------------------------------------------- #

class TestItemsBreaking:
    def test_devuelve_solo_breaking(self, monkeypatch):
        filas = [
            _item_radar(titulo="Breaking A", breaking=True, senal=90_000),
            _item_radar(titulo="No breaking", breaking=False, senal=50_000),
        ]
        monkeypatch.setattr(
            "keni_consola.dominio.breaking.repos.listar_radar_items",
            lambda **_: filas,
        )
        items = dom.items_breaking("claro-sports", "MX")
        assert len(items) == 1
        assert items[0]["titulo"] == "Breaking A"

    def test_vacio_si_no_hay_marca(self):
        items = dom.items_breaking("", "MX")
        assert items == []

    def test_ordena_por_senal_desc(self, monkeypatch):
        filas = [
            _item_radar(titulo="B1", senal=10_000, breaking=True),
            _item_radar(titulo="B2", senal=50_000, breaking=True),
        ]
        monkeypatch.setattr(
            "keni_consola.dominio.breaking.repos.listar_radar_items",
            lambda **_: filas,
        )
        items = dom.items_breaking("claro-sports", "MX")
        assert [i["titulo"] for i in items] == ["B2", "B1"]

    def test_respeta_maximo(self, monkeypatch):
        filas = [_item_radar(titulo=f"T{i}", breaking=True, senal=i) for i in range(30)]
        monkeypatch.setattr(
            "keni_consola.dominio.breaking.repos.listar_radar_items",
            lambda **_: filas,
        )
        items = dom.items_breaking("claro-sports", "MX")
        assert len(items) <= dom.MAX_ITEMS_BREAKING

    def test_best_effort_ante_fallo(self, monkeypatch):
        def explota(**_):
            raise RuntimeError("DB caída")
        monkeypatch.setattr(
            "keni_consola.dominio.breaking.repos.listar_radar_items",
            explota,
        )
        items = dom.items_breaking("claro-sports", "MX")
        assert items == []


class TestAnotarEstadoBorrador:
    def test_ninguno_si_no_hay_borradores(self, monkeypatch):
        monkeypatch.setattr(
            "keni_consola.dominio.breaking.repos.listar_contenido",
            lambda **_: [],
        )
        items = [_item_radar(titulo="Breaking A")]
        dom.anotar_estado_borrador(items, "claro-sports")
        assert items[0]["estado_borrador"] == "ninguno"
        assert items[0]["contenido_id"] == ""

    def test_listo_cuando_hay_borrador(self, monkeypatch):
        monkeypatch.setattr(
            "keni_consola.dominio.breaking.repos.listar_contenido",
            lambda **_: [_item_contenido()],
        )
        # Sin generaciones activas.
        monkeypatch.setattr(
            "keni_consola.dominio.breaking.generaciones.listar",
            lambda **_: [],
        )
        items = [_item_radar()]
        dom.anotar_estado_borrador(items, "claro-sports")
        assert items[0]["estado_borrador"] == "listo"
        assert items[0]["contenido_id"] == "c-1"

    def test_generando_cuando_hay_generacion_ejecutando(self, monkeypatch):
        monkeypatch.setattr(
            "keni_consola.dominio.breaking.repos.listar_contenido",
            lambda **_: [_item_contenido()],
        )
        monkeypatch.setattr(
            "keni_consola.dominio.breaking.generaciones.listar",
            lambda **_: [{"id": "gen-1", "contenido_id": "c-1", "estado": "ejecutando"}],
        )
        items = [_item_radar()]
        dom.anotar_estado_borrador(items, "claro-sports")
        assert items[0]["estado_borrador"] == "generando"
        assert items[0]["generacion_id"] == "gen-1"

    def test_sin_marca_deja_ninguno(self):
        items = [_item_radar()]
        dom.anotar_estado_borrador(items, "")
        assert items[0]["estado_borrador"] == "ninguno"


# --------------------------------------------------------------------------- #
# Tests del daemon de breaking (selección pura)
# --------------------------------------------------------------------------- #

class TestItemsAPreparar:
    def _item(self, titulo="T", senal=50_000):
        return {"titulo": titulo, "senal": senal, "breaking": True}

    def test_filtra_ya_preparados(self):
        items = [self._item("A"), self._item("B")]
        ya = {dom.clave_de_titulo("A")}
        result = daemon.items_a_preparar(items, maximo=5, ya_preparados=ya)
        assert len(result) == 1
        assert result[0]["titulo"] == "B"

    def test_respeta_maximo(self):
        items = [self._item(f"T{i}") for i in range(10)]
        result = daemon.items_a_preparar(items, maximo=3, ya_preparados=set())
        assert len(result) == 3

    def test_vacio_si_todos_preparados(self):
        items = [self._item("A")]
        ya = {dom.clave_de_titulo("A")}
        result = daemon.items_a_preparar(items, maximo=5, ya_preparados=ya)
        assert result == []


# --------------------------------------------------------------------------- #
# Tests de la API (con Postgres real via fixture `entorno`)
# --------------------------------------------------------------------------- #

from .conftest import _cliente  # noqa: F401,E402  (fixture `cliente` se descubre por nombre)


def test_get_breaking_sin_snapshot(entorno, cliente, monkeypatch):
    """GET /api/breaking?marca=claro-sports devuelve items=[] sin snapshot."""
    # Sin datos en radar_items → lista vacía.
    datos = cliente.get("/api/breaking?marca=claro-sports").json()
    assert "items" in datos
    assert datos["items"] == []


def test_get_breaking_con_snapshot(entorno, cliente, monkeypatch):
    """GET /api/breaking refleja los items breaking del snapshot."""
    from keni_consola import repos

    # Sembrar un snapshot con un item breaking.
    repos.upsert_radar_items(
        "claro-sports",
        "MX",
        [
            {
                "titulo": "Clásico de última hora",
                "clave": dom.clave_de_titulo("Clásico de última hora"),
                "senal": 120_000,
                "senal_texto": "120K+",
                "breaking": True,
                "idioma": "es",
                "fuentes": ["Google Trends"],
                "enlaces": [],
                "por_que": "Trending en búsquedas",
                "estado": "nuevo",
            }
        ],
    )

    datos = cliente.get("/api/breaking?marca=claro-sports").json()
    assert len(datos["items"]) == 1
    item = datos["items"][0]
    assert item["titulo"] == "Clásico de última hora"
    assert item["breaking"] is True
    assert item["estado_borrador"] == "ninguno"


def test_post_preparar_crea_draft(entorno, cliente, monkeypatch):
    """POST /api/breaking/preparar crea un DRAFT (origen='breaking') y lanza copy."""
    from keni_consola import autogen_copy

    generados: list = []

    def fake_lanzar(item):
        generados.append(item)
        return {"id": "gen-fake-1"}

    monkeypatch.setattr(autogen_copy, "lanzar_para_topic", fake_lanzar)
    monkeypatch.setattr(autogen_copy, "_id_etiqueta_autogen", lambda **_: "")

    resp = cliente.post(
        "/api/breaking/preparar",
        json={"titulo": "Hat-trick épico", "marca": "claro-sports"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["contenido_id"]
    assert data["generacion_id"] == "gen-fake-1"

    # El contenido debe existir en el tablero con origen='breaking'.
    from keni_consola import repos
    todos = repos.listar_contenido(marca="claro-sports")
    borradores = [it for it in todos if it.get("origen") == "breaking"]
    assert len(borradores) == 1
    assert borradores[0]["titulo"] == "Hat-trick épico"
    assert borradores[0]["flujo"] == "importante"
    assert borradores[0]["prioridad"] == "alta"


def test_post_preparar_dedup(entorno, cliente, monkeypatch):
    """POST /api/breaking/preparar no crea duplicados para el mismo título."""
    from keni_consola import autogen_copy

    monkeypatch.setattr(autogen_copy, "lanzar_para_topic", lambda _: {"id": "gen-1"})
    monkeypatch.setattr(autogen_copy, "_id_etiqueta_autogen", lambda **_: "")

    body = {"titulo": "Penalti polémico", "marca": "claro-sports"}
    r1 = cliente.post("/api/breaking/preparar", json=body)
    r2 = cliente.post("/api/breaking/preparar", json=body)
    assert r1.status_code == 200
    assert r2.status_code == 200
    # Mismo contenido_id → no se duplicó.
    assert r1.json()["contenido_id"] == r2.json()["contenido_id"]


def test_post_preparar_marca_invalida(entorno, cliente):
    """POST /api/breaking/preparar rechaza una marca no válida."""
    resp = cliente.post(
        "/api/breaking/preparar",
        json={"titulo": "Test", "marca": "marca-inexistente"},
    )
    assert resp.status_code == 400


def test_get_breaking_estado_borrador_listo(entorno, cliente, monkeypatch):
    """GET /api/breaking reporta estado_borrador='listo' cuando ya hay un borrador."""
    from keni_consola import autogen_copy, repos

    # Sembrar snapshot breaking.
    repos.upsert_radar_items(
        "claro-sports",
        "MX",
        [
            {
                "titulo": "Remontada histórica",
                "clave": dom.clave_de_titulo("Remontada histórica"),
                "senal": 200_000,
                "senal_texto": "200K+",
                "breaking": True,
                "idioma": "es",
                "fuentes": ["Google Trends"],
                "enlaces": [],
                "por_que": "",
                "estado": "nuevo",
            }
        ],
    )

    # Crear un borrador de breaking para ese título.
    monkeypatch.setattr(autogen_copy, "lanzar_para_topic", lambda _: None)
    monkeypatch.setattr(autogen_copy, "_id_etiqueta_autogen", lambda **_: "")
    cliente.post(
        "/api/breaking/preparar",
        json={"titulo": "Remontada histórica", "marca": "claro-sports"},
    )

    # No hay generaciones en el almacén de tests → estado='listo' (borrador existe).
    monkeypatch.setattr(
        "keni_consola.dominio.breaking.generaciones.listar",
        lambda **_: [],
    )
    datos = cliente.get("/api/breaking?marca=claro-sports").json()
    item = datos["items"][0]
    assert item["estado_borrador"] == "listo"
    assert item["contenido_id"]
