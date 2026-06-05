"""Tests de la API Biblioteca de ARTES (/api/artes). OFFLINE: NUNCA se toca la red.

Cubre: catalogar un objeto de media existente, idempotencia por `objeto` UNIQUE,
validaciones (objeto inexistente, marca desconocida, tipo invalido), filtros de listado
(marca, busqueda `q`), descatalogado con y sin `purgar`, y que un arte catalogado es una
REFERENCIA VIVA para el GC de media huerfana (no se borra aunque nadie lo use).
"""

from __future__ import annotations

from keni_consola.dominio import media_gc

# PNG minimo valido (1x1) -> bytes para subir como objeto de media.
_PNG_1x1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _subir_objeto(cliente, sufijo: bytes = b"") -> str:
    """Sube un objeto de media y devuelve su key (`fotos/<sha256>.png`).

    El almacen es CONTENT-ADDRESSED con dedup: subir los MISMOS bytes colapsa a UNA key.
    Para tener objetos DISTINTOS (filtros de listado), `sufijo` varia el contenido (el
    content-type fija la extension; estos bytes extra no rompen la deteccion PNG).
    """
    r = cliente.post(
        "/api/media", files={"archivo": ("foto.png", _PNG_1x1 + sufijo, "image/png")}
    )
    assert r.status_code == 200
    return r.json()["id"]


# --------------------------------------------------------------------------- #
# POST /api/artes (catalogar)                                                  #
# --------------------------------------------------------------------------- #


def test_crear_arte_ok(cliente):
    objeto = _subir_objeto(cliente)
    r = cliente.post(
        "/api/artes",
        json={"objeto": objeto, "marca": "unotv", "tipo": "estudio",
              "titulo": "Estadio", "etiquetas": ["mundial", "futbol"]},
    )
    assert r.status_code == 200
    arte = r.json()["arte"]
    # Catalogar PROMUEVE el objeto a la carpeta biblioteca/ (reusable); conserva el basename.
    assert arte["objeto"] == "biblioteca/" + objeto.rsplit("/", 1)[-1]
    assert arte["url"] == f"/api/media/{arte['objeto']}"
    assert arte["marca"] == "unotv"
    assert arte["marca_nombre"]  # nombre legible resuelto en servidor
    assert arte["etiquetas"] == ["mundial", "futbol"]  # lista, no JSON string
    assert arte["tipo"] == "estudio"


def test_crear_arte_idempotente(cliente):
    objeto = _subir_objeto(cliente)
    a = cliente.post("/api/artes", json={"objeto": objeto, "marca": "unotv"}).json()["arte"]
    b = cliente.post("/api/artes", json={"objeto": objeto, "marca": "unotv"}).json()["arte"]
    assert a["id"] == b["id"]  # no duplica: el objeto (ya promovido) es UNIQUE
    # Y en el listado aparece una sola vez (por su key catalogada en biblioteca/).
    artes = cliente.get("/api/artes").json()["artes"]
    assert sum(1 for x in artes if x["objeto"] == a["objeto"]) == 1


def test_crear_objeto_inexistente_400(cliente):
    r = cliente.post("/api/artes", json={"objeto": "noexiste.png", "marca": "unotv"})
    assert r.status_code == 400
    assert "no existe" in r.json()["error"].lower()


def test_crear_sin_objeto_400(cliente):
    assert cliente.post("/api/artes", json={"marca": "unotv"}).status_code == 400


def test_crear_marca_desconocida_400(cliente):
    objeto = _subir_objeto(cliente)
    r = cliente.post("/api/artes", json={"objeto": objeto, "marca": "marca-fantasma"})
    assert r.status_code == 400


def test_crear_tipo_invalido_400(cliente):
    objeto = _subir_objeto(cliente)
    r = cliente.post("/api/artes", json={"objeto": objeto, "tipo": "lo-que-sea"})
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# GET /api/artes (listado + filtros)                                          #
# --------------------------------------------------------------------------- #


def test_listar_filtra_por_marca(cliente):
    o1, o2 = _subir_objeto(cliente, b"\x01"), _subir_objeto(cliente, b"\x02")
    a1 = cliente.post("/api/artes", json={"objeto": o1, "marca": "unotv"}).json()["arte"]
    a2 = cliente.post("/api/artes", json={"objeto": o2, "marca": "claro-sports"}).json()["arte"]
    artes = cliente.get("/api/artes", params={"marca": "unotv"}).json()["artes"]
    objetos = {a["objeto"] for a in artes}
    assert a1["objeto"] in objetos and a2["objeto"] not in objetos


def test_listar_busqueda_q(cliente):
    o1, o2 = _subir_objeto(cliente, b"\x01"), _subir_objeto(cliente, b"\x02")
    a1 = cliente.post("/api/artes", json={"objeto": o1, "marca": "unotv", "etiquetas": ["mundial"]}).json()["arte"]
    a2 = cliente.post("/api/artes", json={"objeto": o2, "marca": "unotv", "titulo": "Liga MX"}).json()["arte"]
    artes = cliente.get("/api/artes", params={"q": "mundial"}).json()["artes"]
    objetos = {a["objeto"] for a in artes}
    assert a1["objeto"] in objetos and a2["objeto"] not in objetos


# --------------------------------------------------------------------------- #
# DELETE /api/artes/{id}                                                      #
# --------------------------------------------------------------------------- #


def test_borrar_descataloga(cliente):
    objeto = _subir_objeto(cliente)
    arte = cliente.post("/api/artes", json={"objeto": objeto, "marca": "unotv"}).json()["arte"]
    assert cliente.delete(f"/api/artes/{arte['id']}").status_code == 200
    # Ya no esta en el catalogo, pero el binario sigue (lo recoge el GC si nadie lo usa).
    assert all(a["id"] != arte["id"] for a in cliente.get("/api/artes").json()["artes"])
    assert cliente.get(f"/api/media/{objeto}").status_code == 200


def test_borrar_inexistente_404(cliente):
    assert cliente.delete("/api/artes/noexiste").status_code == 404


def test_borrar_purgar_borra_el_binario(cliente):
    objeto = _subir_objeto(cliente)
    arte = cliente.post("/api/artes", json={"objeto": objeto, "marca": "unotv"}).json()["arte"]
    assert cliente.delete(f"/api/artes/{arte['id']}", params={"purgar": "1"}).status_code == 200
    # Con purgar=1 el binario catalogado (la copia en biblioteca/) desaparece del almacen.
    assert cliente.get(f"/api/media/{arte['objeto']}").status_code == 404


# --------------------------------------------------------------------------- #
# Integracion con el GC: un arte catalogado es REFERENCIA VIVA                 #
# --------------------------------------------------------------------------- #


def test_arte_catalogado_es_referencia_viva(cliente):
    """Catalogar un objeto lo protege del GC: aparece en `referencias_vivas`."""
    objeto = _subir_objeto(cliente)
    assert objeto not in media_gc.referencias_vivas()
    arte = cliente.post("/api/artes", json={"objeto": objeto, "marca": "unotv"}).json()["arte"]
    # El arte se cataloga por su key PROMOVIDA (biblioteca/...): esa es la referencia viva.
    assert arte["objeto"] in media_gc.referencias_vivas()
