"""Tests de la API del envelope de PAGINACION (#121). OFFLINE, todo en tmp.

Verifica que los listados pesados devuelven el envelope ADITIVO retrocompatible:
mantienen su clave de lista (`publicaciones`/`generaciones`/`runs`) y AÑADEN
`paginacion:{total, limite, desplazamiento}`. Sin `?limite=` se devuelve el conjunto
completo (comportamiento previo) con `total` exacto; con `?limite=&desplazamiento=`
se pagina. Un cliente viejo que solo lee la clave de lista sigue funcionando.
"""

from __future__ import annotations


def _crear_pub(cliente, titulo):
    return cliente.post(
        "/api/publicaciones", json={"marca": "unotv", "red": "x", "titulo": titulo, "contenido": "C"}
    )


# --------------------------------------------------------------------------- #
# Publicaciones                                                               #
# --------------------------------------------------------------------------- #


def test_publicaciones_sin_params_devuelve_todo_y_paginacion(cliente):
    for i in range(3):
        _crear_pub(cliente, f"P{i}")
    datos = cliente.get("/api/publicaciones").json()
    assert "publicaciones" in datos  # clave de lista intacta (retrocompat)
    assert len(datos["publicaciones"]) == 3
    pag = datos["paginacion"]
    assert pag["total"] == 3
    assert pag["desplazamiento"] == 0
    # Sin paginar, `limite` reportado abarca todo el conjunto.
    assert pag["limite"] == 3


def test_publicaciones_paginado(cliente):
    for i in range(5):
        _crear_pub(cliente, f"P{i}")
    p1 = cliente.get("/api/publicaciones?limite=2&desplazamiento=0").json()
    p2 = cliente.get("/api/publicaciones?limite=2&desplazamiento=2").json()
    assert len(p1["publicaciones"]) == 2
    assert len(p2["publicaciones"]) == 2
    assert p1["paginacion"] == {"total": 5, "limite": 2, "desplazamiento": 0}
    assert p2["paginacion"] == {"total": 5, "limite": 2, "desplazamiento": 2}
    # Paginas distintas (sin solape).
    ids1 = {p["id"] for p in p1["publicaciones"]}
    ids2 = {p["id"] for p in p2["publicaciones"]}
    assert not (ids1 & ids2)


def test_publicaciones_paginacion_respeta_filtros(cliente):
    for i in range(3):
        _crear_pub(cliente, f"U{i}")  # unotv
    cliente.post(
        "/api/publicaciones",
        json={"marca": "claro-sports", "red": "x", "titulo": "C", "contenido": "C"},
    )
    datos = cliente.get("/api/publicaciones?marca=unotv&limite=2").json()
    assert datos["paginacion"]["total"] == 3  # total filtrado, no 4
    assert len(datos["publicaciones"]) == 2


# --------------------------------------------------------------------------- #
# Generaciones                                                                #
# --------------------------------------------------------------------------- #


def test_generaciones_envelope(cliente):
    # Sin generaciones: lista vacia + paginacion 0.
    datos = cliente.get("/api/generaciones").json()
    assert datos["generaciones"] == []
    assert datos["paginacion"]["total"] == 0
