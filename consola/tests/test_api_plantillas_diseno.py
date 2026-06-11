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
        "marca": "unotv", "nombre": "Última hora", "categoria": "Última hora",
        "documento": _DOC, "lineas": ["linea-nacional", "linea-nacional"],
    })
    assert r.status_code == 200, r.text
    p = r.json()["plantilla"]
    assert p["marca"] == "unotv" and p["nombre"] == "Última hora"
    assert p["categoria"] == "ultima-hora"  # texto libre normalizado a slug
    assert p["documento"]["formato"]["w"] == 1080
    assert p["documento"]["version"] == 1  # validado/normalizado por el dominio
    assert p["lineas"] == ["linea-nacional"]
    assert p["marca_nombre"]

    assert len(cliente.get("/api/plantillas-diseno?marca=unotv").json()["plantillas"]) == 1
    # El filtro de categoría acepta el slug exacto Y cualquier forma que normalice a él.
    assert len(cliente.get("/api/plantillas-diseno?categoria=ultima-hora").json()["plantillas"]) == 1
    assert len(cliente.get("/api/plantillas-diseno?categoria=%C3%9Altima%20hora").json()["plantillas"]) == 1
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
# Tests de campo `categoria` (texto libre normalizado; fallback "general")      #
# --------------------------------------------------------------------------- #

def test_categoria_default_general(cliente):
    """Sin enviar `categoria`, la plantilla cae en 'general' (el fallback del catálogo)."""
    r = cliente.post("/api/plantillas-diseno", json={"marca": "unotv", "documento": _DOC})
    assert r.status_code == 200, r.text
    assert r.json()["plantilla"]["categoria"] == "general"


def test_categoria_legado_post_cae_a_general(cliente):
    """El legado 'post' (categoría hardcodeada histórica) se normaliza a 'general' al escribir."""
    r = cliente.post("/api/plantillas-diseno", json={
        "marca": "unotv", "categoria": "post", "documento": _DOC,
    })
    assert r.status_code == 200, r.text
    assert r.json()["plantilla"]["categoria"] == "general"


def test_categoria_texto_libre_se_normaliza(cliente):
    """Texto libre con acentos/espacios/mayúsculas -> slug en minúsculas con guiones."""
    r = cliente.post("/api/plantillas-diseno", json={
        "marca": "claro-sports", "categoria": "  Previa de Partido!! ", "documento": _DOC,
    })
    assert r.status_code == 200, r.text
    assert r.json()["plantilla"]["categoria"] == "previa-de-partido"


def test_patch_categoria_normaliza_y_vacia_cae_a_general(cliente):
    pid = cliente.post("/api/plantillas-diseno", json={
        "marca": "unotv", "categoria": "marcador", "documento": _DOC,
    }).json()["plantilla"]["id"]

    r = cliente.patch(f"/api/plantillas-diseno/{pid}", json={"categoria": "Efemérides"})
    assert r.status_code == 200
    assert r.json()["plantilla"]["categoria"] == "efemerides"

    r2 = cliente.patch(f"/api/plantillas-diseno/{pid}", json={"categoria": ""})
    assert r2.status_code == 200
    assert r2.json()["plantilla"]["categoria"] == "general"


def test_busqueda_q_por_nombre_y_categoria(cliente):
    cliente.post("/api/plantillas-diseno", json={
        "marca": "unotv", "nombre": "Placa roja", "categoria": "ultima-hora", "documento": _DOC,
    })
    cliente.post("/api/plantillas-diseno", json={
        "marca": "unotv", "nombre": "Tabla general", "categoria": "marcador", "documento": _DOC,
    })

    # Por nombre (substring, case-insensitive).
    assert [p["nombre"] for p in cliente.get("/api/plantillas-diseno?q=roja").json()["plantillas"]] == ["Placa roja"]
    # Por categoría (forma legible -> slug normalizado).
    assert [p["nombre"] for p in cliente.get("/api/plantillas-diseno?q=%C3%9Altima").json()["plantillas"]] == ["Placa roja"]
    # Sin coincidencias.
    assert cliente.get("/api/plantillas-diseno?q=nada-que-ver").json()["plantillas"] == []


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


# ── Orden manual (drag-and-drop de la galería) ──────────────────────────────────────────────────

def _crear(cliente, nombre, marca="unotv"):
    r = cliente.post("/api/plantillas-diseno", json={"marca": marca, "nombre": nombre, "documento": _DOC})
    assert r.status_code == 200, r.text
    return r.json()["plantilla"]["id"]


def test_orden_por_defecto_es_cero(cliente):
    # Las nuevas nacen "sin ordenar" (orden=0): el orden visible lo da `creado DESC` hasta reordenar.
    _crear(cliente, "A")
    _crear(cliente, "B")
    plantillas = cliente.get("/api/plantillas-diseno?marca=unotv").json()["plantillas"]
    assert all(p["orden"] == 0 for p in plantillas)


def test_reordenar_fija_la_secuencia_exacta(cliente):
    a = _crear(cliente, "A")
    b = _crear(cliente, "B")
    c = _crear(cliente, "C")
    r = cliente.post("/api/plantillas-diseno/reordenar", json={"ids": [a, c, b]})
    assert r.status_code == 200, r.text
    assert r.json()["actualizadas"] == 3
    plantillas = cliente.get("/api/plantillas-diseno?marca=unotv").json()["plantillas"]
    assert [p["id"] for p in plantillas] == [a, c, b]  # orden visible == secuencia pedida
    assert {p["id"]: p["orden"] for p in plantillas} == {a: 1, c: 2, b: 3}  # orden 1..N


def test_reordenar_las_nuevas_caen_al_final(cliente):
    a = _crear(cliente, "A")
    b = _crear(cliente, "B")
    cliente.post("/api/plantillas-diseno/reordenar", json={"ids": [b, a]})
    nueva = _crear(cliente, "Nueva")  # orden=0: cae DESPUÉS de las ya ordenadas
    ids = [p["id"] for p in cliente.get("/api/plantillas-diseno?marca=unotv").json()["plantillas"]]
    assert ids == [b, a, nueva]


def test_reordenar_es_por_marca(cliente):
    a = _crear(cliente, "A", "unotv")
    x = _crear(cliente, "X", "claro-sports")
    cliente.post("/api/plantillas-diseno/reordenar", json={"ids": [a]})
    # Reordenar unotv no toca claro-sports.
    otra = cliente.get("/api/plantillas-diseno?marca=claro-sports").json()["plantillas"]
    assert [p["id"] for p in otra] == [x]
    assert otra[0]["orden"] == 0


def test_reordenar_ignora_ids_inexistentes(cliente):
    a = _crear(cliente, "A")
    b = _crear(cliente, "B")
    r = cliente.post("/api/plantillas-diseno/reordenar", json={"ids": [a, "no-existe", b]})
    assert r.status_code == 200
    assert r.json()["actualizadas"] == 2  # solo a y b existen
    ids = [p["id"] for p in cliente.get("/api/plantillas-diseno?marca=unotv").json()["plantillas"]]
    assert ids == [a, b]


def test_reordenar_cuerpo_invalido_400(cliente):
    assert cliente.post("/api/plantillas-diseno/reordenar", json={"ids": "no-es-lista"}).status_code == 400
    assert cliente.post("/api/plantillas-diseno/reordenar", json={"ids": [1, 2]}).status_code == 400
