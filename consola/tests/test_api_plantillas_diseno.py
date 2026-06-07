"""Tests de la API de plantillas de diseño (/api/plantillas-diseno). OFFLINE."""

from __future__ import annotations

# Toda plantilla necesita un HUECO DE FOTO explícito (`es_foto`): el doc base lo incluye.
_DOC = {
    "formato": {"w": 1080, "h": 1350, "safe_top": 60, "safe_bottom": 96},
    "capas": [
        {"tipo": "imagen", "objeto": "", "x": 0, "y": 0, "w": 1080, "h": 1350, "z": 0, "es_foto": True},
    ],
}


def test_listar_vacio(cliente):
    r = cliente.get("/api/plantillas-diseno")
    assert r.status_code == 200
    assert r.json() == {"plantillas": []}


def test_crear_y_listar(cliente):
    r = cliente.post("/api/plantillas-diseno", json={
        "marca": "unotv", "nombre": "Última hora", "categoria": "post",
        "documento": _DOC, "lineas": ["linea-nacional", "linea-nacional"],
    })
    assert r.status_code == 200, r.text
    p = r.json()["plantilla"]
    assert p["marca"] == "unotv" and p["nombre"] == "Última hora"
    assert p["documento"]["formato"]["w"] == 1080
    assert p["documento"]["version"] == 1  # validado/normalizado por el dominio
    assert p["lineas"] == ["linea-nacional"]
    assert p["marca_nombre"]

    assert len(cliente.get("/api/plantillas-diseno?marca=unotv").json()["plantillas"]) == 1
    assert len(cliente.get("/api/plantillas-diseno?categoria=post").json()["plantillas"]) == 1
    assert len(cliente.get("/api/plantillas-diseno?categoria=historia").json()["plantillas"]) == 0
    assert len(cliente.get("/api/plantillas-diseno?linea=linea-nacional").json()["plantillas"]) == 1
    assert len(cliente.get("/api/plantillas-diseno?linea=otra").json()["plantillas"]) == 0


def test_crear_documento_invalido_400(cliente):
    r = cliente.post("/api/plantillas-diseno", json={"marca": "unotv", "documento": {"capas": "no-es-lista"}})
    assert r.status_code == 400


def test_crear_sin_documento_400(cliente):
    r = cliente.post("/api/plantillas-diseno", json={"marca": "unotv", "nombre": "x"})
    assert r.status_code == 400


def test_crear_sin_hueco_de_foto_400(cliente):
    # Sin una capa imagen marcada `es_foto`, la plantilla no declara dónde va la foto -> 400.
    sin_hueco = {"formato": {"w": 1080, "h": 1350, "safe_top": 60, "safe_bottom": 96}, "capas": []}
    r = cliente.post("/api/plantillas-diseno", json={"marca": "unotv", "documento": sin_hueco})
    assert r.status_code == 400
    assert "hueco de foto" in r.json()["error"].lower()


def test_crear_marca_invalida_400(cliente):
    r = cliente.post("/api/plantillas-diseno", json={"marca": "no-existe", "documento": _DOC})
    assert r.status_code == 400


def test_obtener_actualizar_borrar(cliente):
    pid = cliente.post("/api/plantillas-diseno", json={
        "marca": "claro-sports", "nombre": "Gol", "documento": _DOC,
    }).json()["plantilla"]["id"]

    assert cliente.get(f"/api/plantillas-diseno/{pid}").json()["plantilla"]["nombre"] == "Gol"
    assert cliente.get("/api/plantillas-diseno/inexistente").status_code == 404

    r = cliente.patch(f"/api/plantillas-diseno/{pid}", json={"nombre": "Gol de México", "categoria": "historia"})
    assert r.status_code == 200
    assert r.json()["plantilla"]["nombre"] == "Gol de México"
    assert r.json()["plantilla"]["categoria"] == "historia"

    # Documento inválido en PATCH -> 400 (no corrompe la plantilla).
    assert cliente.patch(f"/api/plantillas-diseno/{pid}", json={"documento": {"capas": 5}}).status_code == 400

    assert cliente.delete(f"/api/plantillas-diseno/{pid}").status_code == 200
    assert cliente.delete(f"/api/plantillas-diseno/{pid}").status_code == 404


# --------------------------------------------------------------------------- #
# Tests de campo `tipo`                                                        #
# --------------------------------------------------------------------------- #

def test_tipo_default_foto(cliente):
    """Sin enviar `tipo`, la plantilla queda como 'foto'."""
    r = cliente.post("/api/plantillas-diseno", json={"marca": "unotv", "documento": _DOC})
    assert r.status_code == 200, r.text
    assert r.json()["plantilla"]["tipo"] == "foto"


def test_tipo_miniatura_persiste(cliente):
    """Crear con tipo='miniatura' y verificar que se persiste y devuelve."""
    r = cliente.post("/api/plantillas-diseno", json={
        "marca": "unotv", "nombre": "Cover YT", "tipo": "miniatura", "documento": _DOC,
    })
    assert r.status_code == 200, r.text
    p = r.json()["plantilla"]
    assert p["tipo"] == "miniatura"

    # GET por id también lo devuelve.
    p2 = cliente.get(f"/api/plantillas-diseno/{p['id']}").json()["plantilla"]
    assert p2["tipo"] == "miniatura"


def test_tipo_invalido_normaliza_a_foto(cliente):
    """Un tipo desconocido en POST se silencia a 'foto'."""
    r = cliente.post("/api/plantillas-diseno", json={
        "marca": "unotv", "tipo": "raro", "documento": _DOC,
    })
    assert r.status_code == 200, r.text
    assert r.json()["plantilla"]["tipo"] == "foto"


def test_patch_tipo(cliente):
    """PATCH puede cambiar tipo de 'foto' a 'miniatura' y viceversa."""
    pid = cliente.post("/api/plantillas-diseno", json={
        "marca": "unotv", "documento": _DOC,
    }).json()["plantilla"]["id"]

    r = cliente.patch(f"/api/plantillas-diseno/{pid}", json={"tipo": "miniatura"})
    assert r.status_code == 200
    assert r.json()["plantilla"]["tipo"] == "miniatura"

    r2 = cliente.patch(f"/api/plantillas-diseno/{pid}", json={"tipo": "foto"})
    assert r2.status_code == 200
    assert r2.json()["plantilla"]["tipo"] == "foto"


def test_patch_tipo_invalido_400(cliente):
    """PATCH con tipo inválido devuelve 400."""
    pid = cliente.post("/api/plantillas-diseno", json={
        "marca": "unotv", "documento": _DOC,
    }).json()["plantilla"]["id"]

    r = cliente.patch(f"/api/plantillas-diseno/{pid}", json={"tipo": "gif"})
    assert r.status_code == 400
    assert "tipo" in r.json()["error"].lower()


def test_listar_filtro_tipo(cliente):
    """?tipo= filtra correctamente; ?tipo= invalido devuelve 400."""
    # Crear una de cada tipo.
    cliente.post("/api/plantillas-diseno", json={"marca": "unotv", "tipo": "foto", "documento": _DOC})
    cliente.post("/api/plantillas-diseno", json={"marca": "unotv", "tipo": "miniatura", "documento": _DOC})

    fotos = cliente.get("/api/plantillas-diseno?tipo=foto").json()["plantillas"]
    miniaturas = cliente.get("/api/plantillas-diseno?tipo=miniatura").json()["plantillas"]
    todas = cliente.get("/api/plantillas-diseno").json()["plantillas"]

    assert all(p["tipo"] == "foto" for p in fotos)
    assert all(p["tipo"] == "miniatura" for p in miniaturas)
    assert len(todas) == len(fotos) + len(miniaturas)

    # Tipo inválido -> 400.
    assert cliente.get("/api/plantillas-diseno?tipo=raro").status_code == 400
