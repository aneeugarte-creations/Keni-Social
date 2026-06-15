"""Tests de la API de fuentes (/api/fuentes). OFFLINE.

`/api/fuentes` presenta el catálogo de feeds desde `fuentes_rss` (la única tabla de fuentes,
fuente de verdad del motor de ingesta) como tipo='rss', más el estado de agencias (Reuters/
AFP) y la aportación manual (idea/interna). Requiere el Postgres de pruebas (fixture
`cliente`); en CI corre con el service postgres, en local se salta.
"""

from __future__ import annotations


def test_listar_fuentes_lee_de_fuentes_rss(cliente):
    # /api/fuentes presenta los feeds de `fuentes_rss` como catálogo (tipo='rss'). Crear un feed por la API RSS lo hace aparecer aquí.
    cliente.post(
        "/api/rss/fuentes",
        json={"nombre": "Diario", "url": "https://93.184.216.34/feed.xml", "marca": "unotv"},
    )
    listado = cliente.get("/api/fuentes").json()
    diario = [f for f in listado["fuentes"] if f["nombre"] == "Diario"]
    assert len(diario) == 1
    assert diario[0]["tipo"] == "rss"
    assert diario[0]["marca_nombre"] == "UnoTV"
    # El estado de las agencias viene SIEMPRE (Reuters/AFP), gateado por credencial.
    assert {a["red"] for a in listado["agencias"]} == {"reuters", "afp"}
    # Sin credenciales en el entorno de test, ambas estan pendientes.
    assert all(not a["disponible"] for a in listado["agencias"])


def test_listar_fuentes_filtra_por_tipo(cliente):
    cliente.post(
        "/api/rss/fuentes", json={"nombre": "Diario", "url": "https://93.184.216.34/feed.xml"}
    )
    assert cliente.get("/api/fuentes?tipo=idea").json()["fuentes"] == []
    assert len(cliente.get("/api/fuentes?tipo=rss").json()["fuentes"]) == 1


def test_listar_fuentes_tipo_invalido_400(cliente):
    assert cliente.get("/api/fuentes?tipo=loquesea").status_code == 400
    assert cliente.get("/api/fuentes?tipo=api").status_code == 400
    assert cliente.get("/api/fuentes?tipo=galeria").status_code == 400


def test_catalogo_tipos_sin_tipos_muertos(cliente):
    # El catálogo expuesto a la UI ya no ofrece los tipos muertos `api`/`galeria`.
    tipos = cliente.get("/api/fuentes").json()["tipos"]
    assert "api" not in tipos
    assert "galeria" not in tipos
    assert "rss" in tipos


def test_listar_fuentes_filtra_por_marca(cliente):
    """`?marca=` devuelve las fuentes de ESA marca + las compartidas; sin marca, todas."""
    cliente.post(
        "/api/rss/fuentes",
        json={"nombre": "UnoTV", "url": "https://93.184.216.34/uno.xml", "marca": "unotv"},
    )
    cliente.post(
        "/api/rss/fuentes",
        json={
            "nombre": "Claro",
            "url": "https://93.184.216.34/claro.xml",
            "marca": "claro-sports",
        },
    )
    cliente.post(
        "/api/rss/fuentes",
        json={"nombre": "Compartida", "url": "https://93.184.216.34/comun.xml"},
    )

    todas = {f["nombre"] for f in cliente.get("/api/fuentes").json()["fuentes"]}
    assert todas == {"UnoTV", "Claro", "Compartida"}

    de_unotv = {f["nombre"] for f in cliente.get("/api/fuentes?marca=unotv").json()["fuentes"]}
    assert de_unotv == {"UnoTV", "Compartida"}

    assert cliente.get("/api/fuentes?marca=marca_falsa").status_code == 400


# --------------------------------------------------------------------------- #
# Reactivar feed auto-desactivado (Ola D)                                      #
# --------------------------------------------------------------------------- #


def test_reactivar_feed_auto_desactivado(cliente):
    from keni_consola import repos

    f = repos.crear_fuente_rss("Demo", "https://example.com/feed.xml", categoria="mx")
    # Simula el estado tras auto-desactivado por el daemon.
    repos.actualizar_fuente_rss(
        f["id"], {"activo": False, "desactivado_auto": True, "errores_seguidos": 8}
    )
    r = cliente.post(f"/api/fuentes/{f['id']}/reactivar")
    assert r.status_code == 200, r.text
    fuente = r.json()["fuente"]
    assert fuente["activo"] is True
    assert fuente["desactivado_auto"] is False
    assert fuente["errores_seguidos"] == 0
    assert fuente["proximo_sondeo"] == ""


def test_reactivar_feed_inexistente_404(cliente):
    assert cliente.post("/api/fuentes/nope/reactivar").status_code == 404
