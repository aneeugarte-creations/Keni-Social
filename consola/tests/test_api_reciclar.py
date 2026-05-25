"""Tests de reciclar/evergreen (/api/publicaciones). OFFLINE, DB en tmp.

Cubre:
  - el campo `evergreen` en serializacion, PUT y filtro `?evergreen=1`,
  - POST /reciclar con franjas (duplica + encola) y sin franjas (queda borrador),
  - que la copia sea evergreen=1 y conserve contenido/imagen/veredicto/red/marca.
"""

from __future__ import annotations


def _crear(cliente, **campos):
    base = {"marca": "unotv", "red": "x", "titulo": "T", "contenido": "C"}
    base.update(campos)
    return cliente.post("/api/publicaciones", json=base)


# --------------------------------------------------------------------------- #
# Campo evergreen: serializacion, PUT, filtro                                 #
# --------------------------------------------------------------------------- #


def test_evergreen_default_false_en_serializacion(cliente):
    pub = _crear(cliente).json()["publicacion"]
    assert pub["evergreen"] is False


def test_evergreen_put_acepta_bool(cliente):
    pid = _crear(cliente).json()["publicacion"]["id"]
    r = cliente.put(f"/api/publicaciones/{pid}", json={"evergreen": True})
    assert r.status_code == 200
    assert r.json()["publicacion"]["evergreen"] is True
    # volver a false
    r = cliente.put(f"/api/publicaciones/{pid}", json={"evergreen": False})
    assert r.json()["publicacion"]["evergreen"] is False


def test_evergreen_put_no_bool_400(cliente):
    pid = _crear(cliente).json()["publicacion"]["id"]
    assert cliente.put(f"/api/publicaciones/{pid}", json={"evergreen": "si"}).status_code == 400
    assert cliente.put(f"/api/publicaciones/{pid}", json={"evergreen": 1}).status_code == 400


def test_evergreen_filtro_query(cliente):
    a = _crear(cliente).json()["publicacion"]["id"]
    _crear(cliente)
    cliente.put(f"/api/publicaciones/{a}", json={"evergreen": True})
    ever = cliente.get("/api/publicaciones?evergreen=1").json()["publicaciones"]
    assert len(ever) == 1
    assert ever[0]["id"] == a
    no_ever = cliente.get("/api/publicaciones?evergreen=0").json()["publicaciones"]
    assert len(no_ever) == 1
    # sin filtro: las dos
    assert len(cliente.get("/api/publicaciones").json()["publicaciones"]) == 2


# --------------------------------------------------------------------------- #
# POST /reciclar                                                              #
# --------------------------------------------------------------------------- #


def test_reciclar_sin_franjas_queda_borrador(cliente):
    pid = _crear(cliente, contenido="Original", veredicto="ok").json()["publicacion"]["id"]
    r = cliente.post(f"/api/publicaciones/{pid}/reciclar")
    assert r.status_code == 200
    datos = r.json()
    assert datos["encolado"] is False
    copia = datos["publicacion"]
    assert copia["id"] != pid
    assert copia["estado"] == "borrador"
    assert copia["evergreen"] is True
    assert copia["contenido"] == "Original"
    assert copia["veredicto"] == "ok"
    assert copia["marca"] == "unotv"
    assert copia["red"] == "x"
    assert copia["fecha_programada"] == ""
    # ahora hay 2 publicaciones (original + copia)
    assert len(cliente.get("/api/publicaciones").json()["publicaciones"]) == 2


def test_reciclar_con_franjas_encola(cliente):
    # franja general para que aplique a (unotv, x)
    cliente.post("/api/franjas", json={"dia_semana": 2, "hora": "09:00"})
    pid = _crear(cliente).json()["publicacion"]["id"]
    r = cliente.post(f"/api/publicaciones/{pid}/reciclar")
    assert r.status_code == 200
    datos = r.json()
    assert datos["encolado"] is True
    copia = datos["publicacion"]
    assert copia["estado"] == "programado"
    assert copia["evergreen"] is True
    assert copia["fecha_programada"]  # hueco asignado


def test_reciclar_con_franjas_de_otra_marca_no_encola(cliente):
    # franja especifica para piso-15/youtube: NO aplica a unotv/x
    cliente.post(
        "/api/franjas", json={"dia_semana": 2, "hora": "09:00", "marca": "piso-15", "red": "youtube"}
    )
    pid = _crear(cliente, marca="unotv", red="x").json()["publicacion"]["id"]
    datos = cliente.post(f"/api/publicaciones/{pid}/reciclar").json()
    assert datos["encolado"] is False
    assert datos["publicacion"]["estado"] == "borrador"


def test_reciclar_evita_hueco_ya_ocupado(cliente):
    # una sola franja => al reciclar dos veces, la segunda copia salta a la semana siguiente
    cliente.post("/api/franjas", json={"dia_semana": 2, "hora": "09:00"})
    pid = _crear(cliente).json()["publicacion"]["id"]
    primera = cliente.post(f"/api/publicaciones/{pid}/reciclar").json()["publicacion"]
    segunda = cliente.post(f"/api/publicaciones/{pid}/reciclar").json()["publicacion"]
    assert primera["fecha_programada"] != segunda["fecha_programada"]


def test_reciclar_404(cliente):
    assert cliente.post("/api/publicaciones/noexiste/reciclar").status_code == 404
