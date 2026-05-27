"""Tests de la API Publicaciones (/api/publicaciones). OFFLINE, DB en tmp.

Cubre: opciones (catalogos), CRUD, lote, filtros, validaciones (marca/red/estado),
resolucion de nombres legibles y edicion parcial.
"""

from __future__ import annotations


def _crear(cliente, **campos):
    base = {"marca": "unotv", "red": "x", "titulo": "T", "contenido": "C"}
    base.update(campos)
    return cliente.post("/api/publicaciones", json=base)


# --------------------------------------------------------------------------- #
# GET /api/publicaciones/opciones                                             #
# --------------------------------------------------------------------------- #


def test_opciones(cliente):
    datos = cliente.get("/api/publicaciones/opciones").json()
    assert {"redes", "estados", "marcas"} <= set(datos)
    # redes en orden fijo con limite
    ids = [r["id"] for r in datos["redes"]]
    assert ids == ["x", "instagram", "facebook", "tiktok", "youtube"]
    x = datos["redes"][0]
    assert x == {"id": "x", "nombre": "X", "limite": 280}
    assert datos["redes"][2]["limite"] is None  # facebook
    # estados con nombre legible
    estados = {e["id"]: e["nombre"] for e in datos["estados"]}
    assert estados == {
        "borrador": "Borrador",
        "en_revision": "En revisión",
        "aprobado": "Aprobado",
        "programado": "Programado",
        "publicado": "Publicado",
    }
    # marcas: las de Skills (con slug)
    assert any(m["id"] == "unotv" for m in datos["marcas"])


# --------------------------------------------------------------------------- #
# POST / GET listado                                                          #
# --------------------------------------------------------------------------- #


def test_crear_y_listar(cliente):
    r = _crear(cliente)
    assert r.status_code == 200
    pub = r.json()["publicacion"]
    assert pub["id"]
    assert pub["estado"] == "borrador"
    assert pub["marca_nombre"] == "UnoTV"
    assert pub["red_nombre"] == "X"
    listado = cliente.get("/api/publicaciones").json()["publicaciones"]
    assert len(listado) == 1


def test_crear_estado_explicito(cliente):
    pub = _crear(cliente, estado="aprobado").json()["publicacion"]
    assert pub["estado"] == "aprobado"


def test_crear_marca_invalida_400(cliente):
    r = _crear(cliente, marca="marca_falsa")
    assert r.status_code == 400
    assert "marca" in r.json()["error"].lower()


def test_crear_marca_golf_rechazada_400(cliente):
    # El golf NO es marca de primer nivel (es un sub-vertical editorial de Claro
    # Sports): no se acepta como destino de copy.
    r = _crear(cliente, marca="claro-sports-golf")
    assert r.status_code == 400
    assert "marca" in r.json()["error"].lower()


def test_crear_id_metricas_no_es_id_canonico_400(cliente):
    # La forma id_metricas (guion_bajo) NO es un id canonico => no vale como marca.
    assert _crear(cliente, marca="claro_sports_golf").status_code == 400


def test_crear_red_invalida_400(cliente):
    r = _crear(cliente, red="myspace")
    assert r.status_code == 400
    assert "red" in r.json()["error"].lower()


def test_crear_estado_invalido_400(cliente):
    r = _crear(cliente, estado="archivado")
    assert r.status_code == 400


def test_crear_titulo_no_texto_400(cliente):
    r = cliente.post("/api/publicaciones", json={"marca": "unotv", "red": "x", "titulo": 5})
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Filtros                                                                     #
# --------------------------------------------------------------------------- #


def test_filtros(cliente):
    _crear(cliente, red="x", estado="borrador")
    _crear(cliente, red="instagram", estado="aprobado")
    _crear(cliente, marca="piso-15", red="x")
    assert len(cliente.get("/api/publicaciones?marca=unotv").json()["publicaciones"]) == 2
    assert len(cliente.get("/api/publicaciones?red=x").json()["publicaciones"]) == 2
    assert len(cliente.get("/api/publicaciones?estado=aprobado").json()["publicaciones"]) == 1
    assert (
        len(cliente.get("/api/publicaciones?marca=unotv&red=x").json()["publicaciones"]) == 1
    )


# --------------------------------------------------------------------------- #
# Lote                                                                        #
# --------------------------------------------------------------------------- #


def test_crear_lote(cliente):
    r = cliente.post(
        "/api/publicaciones/lote",
        json={
            "publicaciones": [
                {"marca": "unotv", "red": "x", "contenido": "a"},
                {"marca": "unotv", "red": "instagram", "contenido": "b"},
            ]
        },
    )
    assert r.status_code == 200
    assert len(r.json()["publicaciones"]) == 2
    assert len(cliente.get("/api/publicaciones").json()["publicaciones"]) == 2


def test_lote_una_invalida_no_inserta_nada(cliente):
    r = cliente.post(
        "/api/publicaciones/lote",
        json={
            "publicaciones": [
                {"marca": "unotv", "red": "x"},
                {"marca": "unotv", "red": "myspace"},  # invalida
            ]
        },
    )
    assert r.status_code == 400
    # todo o nada: no se inserto la primera
    assert cliente.get("/api/publicaciones").json()["publicaciones"] == []


def test_lote_vacio_400(cliente):
    r = cliente.post("/api/publicaciones/lote", json={"publicaciones": []})
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# GET / PUT / DELETE por id                                                   #
# --------------------------------------------------------------------------- #


def test_detalle(cliente):
    pid = _crear(cliente).json()["publicacion"]["id"]
    r = cliente.get(f"/api/publicaciones/{pid}")
    assert r.status_code == 200
    assert r.json()["publicacion"]["id"] == pid


def test_detalle_404(cliente):
    assert cliente.get("/api/publicaciones/noexiste").status_code == 404


def test_actualizar_parcial(cliente):
    pid = _crear(cliente, titulo="Viejo").json()["publicacion"]["id"]
    r = cliente.put(
        f"/api/publicaciones/{pid}", json={"titulo": "Nuevo", "estado": "aprobado"}
    )
    assert r.status_code == 200
    pub = r.json()["publicacion"]
    assert pub["titulo"] == "Nuevo"
    assert pub["estado"] == "aprobado"


def test_actualizar_estado_invalido_400(cliente):
    pid = _crear(cliente).json()["publicacion"]["id"]
    r = cliente.put(f"/api/publicaciones/{pid}", json={"estado": "archivado"})
    assert r.status_code == 400


def test_actualizar_sin_campos_400(cliente):
    pid = _crear(cliente).json()["publicacion"]["id"]
    r = cliente.put(f"/api/publicaciones/{pid}", json={})
    assert r.status_code == 400


def test_actualizar_404(cliente):
    r = cliente.put("/api/publicaciones/noexiste", json={"titulo": "x"})
    assert r.status_code == 404


def test_actualizar_no_toca_marca_ni_red(cliente):
    """La edicion parcial ignora marca/red aunque vengan en el body."""
    pid = _crear(cliente, marca="unotv", red="x").json()["publicacion"]["id"]
    r = cliente.put(
        f"/api/publicaciones/{pid}", json={"titulo": "Z", "marca": "piso-15", "red": "youtube"}
    )
    pub = r.json()["publicacion"]
    assert pub["marca"] == "unotv"
    assert pub["red"] == "x"


def test_borrar(cliente):
    pid = _crear(cliente).json()["publicacion"]["id"]
    assert cliente.delete(f"/api/publicaciones/{pid}").status_code == 200
    assert cliente.get(f"/api/publicaciones/{pid}").status_code == 404


def test_borrar_404(cliente):
    assert cliente.delete("/api/publicaciones/noexiste").status_code == 404
