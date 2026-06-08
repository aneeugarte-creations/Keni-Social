"""Tests de la API de fuentes (/api/fuentes). OFFLINE.

`/api/fuentes` presenta el catálogo de feeds desde `fuentes_rss` (la única tabla de fuentes,
fuente de verdad del motor de ingesta) como tipo='rss', más el estado de agencias (Reuters/
AFP) y la aportación manual (idea/enlace/interna). Requiere el Postgres de pruebas (fixture
`cliente`); en CI corre con el service postgres, en local se salta.
"""

from __future__ import annotations


def test_listar_fuentes_lee_de_fuentes_rss(cliente):
    # /api/fuentes presenta los feeds de `fuentes_rss` como catálogo (tipo='rss'); ya no hay
    # una tabla-hub espejo aparte. Crear un feed por la API RSS lo hace aparecer aquí.
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
    # Solo existe el tipo 'rss'; pedir otro tipo devuelve vacío (sin error).
    cliente.post(
        "/api/rss/fuentes", json={"nombre": "Diario", "url": "https://93.184.216.34/feed.xml"}
    )
    assert cliente.get("/api/fuentes?tipo=idea").json()["fuentes"] == []
    assert len(cliente.get("/api/fuentes?tipo=rss").json()["fuentes"]) == 1


def test_listar_fuentes_tipo_invalido_400(cliente):
    assert cliente.get("/api/fuentes?tipo=loquesea").status_code == 400


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


# --- Aportacion MANUAL (idea / enlace / interna) -> item REAL en el tablero --- #


def test_aportar_idea_crea_item_en_pendientes(cliente):
    # Sin marca -> NO se lanza copy (gateado), pero el item REAL entra al tablero con su origen.
    r = cliente.post(
        "/api/fuentes/aportar",
        json={"tipo": "idea", "texto": "Hilo con los momentazos de la jornada"},
    )
    assert r.status_code == 200, r.text
    cont = r.json()["contenido"]
    assert cont["flujo"] == "importante"
    assert cont["origen"] == "idea"
    assert cont["titulo"] == "Hilo con los momentazos de la jornada"
    assert r.json()["copy_en_proceso"] is False
    # El item aparece en el tablero (clase contenido, flujo importante).
    tablero = cliente.get("/api/contenido").json()["contenidos"]
    assert any(c["origen"] == "idea" for c in tablero)


def test_aportar_interna_crea_item_con_redes(cliente):
    r = cliente.post(
        "/api/fuentes/aportar",
        json={"tipo": "interna", "texto": "Brief interno de AMX", "redes": ["x", "instagram"]},
    )
    assert r.status_code == 200, r.text
    cont = r.json()["contenido"]
    assert cont["origen"] == "interna"
    assert len(cont["plataformas"]) == 2


def test_aportar_idea_vacia_400(cliente):
    assert cliente.post("/api/fuentes/aportar", json={"tipo": "idea", "texto": "   "}).status_code == 400


def test_aportar_tipo_invalido_400(cliente):
    assert cliente.post("/api/fuentes/aportar", json={"tipo": "rss", "texto": "x"}).status_code == 400


def test_aportar_enlace_extrae_y_crea_item(cliente, monkeypatch):
    # Mockeamos la descarga de la URL: el enlace pegado dispara el flujo URL->item.
    from keni_consola.dominio import extraccion_url

    html = "<html><head><title>Gol histórico</title></head><body><p>Una nota de prueba.</p></body></html>"
    monkeypatch.setattr(extraccion_url, "_DESCARGADOR", lambda _url: html)
    r = cliente.post(
        "/api/fuentes/aportar",
        json={"tipo": "enlace", "url": "https://93.184.216.34/nota"},
    )
    assert r.status_code == 200, r.text
    cont = r.json()["contenido"]
    assert cont["origen"] == "enlace"
    # El titular extraido titula el item; la URL queda en la descripcion (nota no verificada).
    assert "Gol histórico" in cont["titulo"]
    assert "93.184.216.34" in cont["descripcion"]


def test_aportar_enlace_url_invalida_400(cliente):
    assert (
        cliente.post("/api/fuentes/aportar", json={"tipo": "enlace", "url": "no-es-url"}).status_code
        == 400
    )


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
