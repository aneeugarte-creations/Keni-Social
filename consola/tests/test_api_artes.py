"""Tests de la API Galería de ARTES (/api/artes). OFFLINE: NUNCA se toca la red.

Cubre: catalogar un objeto de media existente, idempotencia por `objeto` UNIQUE,
validaciones (objeto inexistente, marca desconocida, tipo invalido), filtros de listado
(marca, busqueda `q`), descatalogado con y sin `purgar`, y que un arte catalogado es una
REFERENCIA VIVA para el GC de media suelta (no se borra aunque nadie lo use).
"""

from __future__ import annotations

from keni_consola import agencias_fotos, autogen_stock, config, media, repos
from keni_consola.dominio import media_gc

from .conftest import _cliente, lanzador_imagen_ejecuta

_ORIGIN = {"Origin": "http://testserver"}

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
    # Catalogar PROMUEVE el objeto a la carpeta artes/ (reusable); conserva el basename.
    assert arte["objeto"] == "artes/" + objeto.rsplit("/", 1)[-1]
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
    # Y en el listado aparece una sola vez (por su key catalogada en artes/).
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


def test_listar_incluye_artes_globales_en_cualquier_marca(cliente):
    """Un arte GLOBAL (marca='') aparece al filtrar por CUALQUIER marca: así una foto generada
    por IA y catalogada como global se reutiliza en todas las marcas/redes. Un arte de OTRA
    marca sigue sin colarse."""
    og, om = _subir_objeto(cliente, b"\x01"), _subir_objeto(cliente, b"\x02")
    glob = cliente.post("/api/artes", json={"objeto": og, "marca": ""}).json()["arte"]
    otra = cliente.post("/api/artes", json={"objeto": om, "marca": "claro-sports"}).json()["arte"]
    assert glob["marca"] == ""
    artes = cliente.get("/api/artes", params={"marca": "unotv"}).json()["artes"]
    objetos = {a["objeto"] for a in artes}
    assert glob["objeto"] in objetos       # el global SÍ aparece bajo unotv
    assert otra["objeto"] not in objetos   # el de claro-sports NO


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
    # Con purgar=1 el binario catalogado (la copia en artes/) desaparece del almacen.
    assert cliente.get(f"/api/media/{arte['objeto']}").status_code == 404


# --------------------------------------------------------------------------- #
# Integracion con el GC: un arte catalogado es REFERENCIA VIVA                 #
# --------------------------------------------------------------------------- #


def test_arte_catalogado_es_referencia_viva(cliente):
    """Catalogar un objeto lo protege del GC: aparece en `referencias_vivas`."""
    objeto = _subir_objeto(cliente)
    assert objeto not in media_gc.referencias_vivas()
    arte = cliente.post("/api/artes", json={"objeto": objeto, "marca": "unotv"}).json()["arte"]
    # El arte se cataloga por su key PROMOVIDA (artes/...): esa es la referencia viva.
    assert arte["objeto"] in media_gc.referencias_vivas()


# --------------------------------------------------------------------------- #
# POST /api/artes/generar (lanzador manual de ARTE: marca + prompt + modelo + N) #
# --------------------------------------------------------------------------- #
# Igual que /api/media/generar: OFFLINE, el proveedor se MOCKEA (SalidaImagen) y el
# lanzador EJECUTA `generar` en el acto, asi se cubre generar -> guardar -> ledger.


def _cli_arte(monkeypatch, *, coste=0.0, modelo_dev=None):
    """Cliente con proveedor de imagen MOCK (SalidaImagen) y lanzador que ejecuta en el acto.

    `coste` es el coste por imagen que reporta el proveedor; `modelo_dev`, si se da, el modelo
    que devuelve (por defecto, el que pidio el llamador) para verificar la propagacion.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "clave-de-prueba")

    def _prov(prompt, modelo=""):  # noqa: ANN001 -- doble del proveedor real
        return media.SalidaImagen(_PNG_1x1, coste, modelo_dev if modelo_dev is not None else modelo)

    monkeypatch.setattr(media, "_PROVEEDOR", _prov)
    return _cliente(lanzar_imagen=lanzador_imagen_ejecuta())


def test_generar_arte_ok_n_imagenes(entorno, monkeypatch):
    """Camino feliz: marca + prompt + N -> N generaciones tipo imagen que completan con url."""
    cli = _cli_arte(monkeypatch, coste=0.02)
    r = cli.post("/api/artes/generar", json={"marca": "unotv", "prompt": "estadio lleno", "n": 3})
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["n"] == 3
    assert cuerpo["modelo"]  # modelo resuelto (el por defecto)
    assert len(cuerpo["generaciones"]) == 3
    for gen in cuerpo["generaciones"]:
        assert gen["tipo"] == "imagen"
        assert gen["marca"] == "unotv"
        res = gen["resultado"]
        assert res["id"].endswith(".png")
        assert res["url"] == f"/api/media/{res['id']}"
        # La imagen generada se puede servir.
        assert cli.get(res["url"]).status_code == 200
    # El coste medio viaja en la respuesta (USD), ya con muestras de estas 3 generaciones.
    cm = cuerpo["coste_medio"]
    assert cm["moneda"] == "USD"
    assert cm["muestras"] >= 3
    assert abs(cm["por_imagen"] - 0.02) < 1e-9


def test_generar_arte_sin_prompt_usa_prompts(entorno, monkeypatch):
    """Sin `prompt` cae al prompt de arte de la Prompts (cuerpo efectivo no vacio)."""
    cli = _cli_arte(monkeypatch)
    r = cli.post("/api/artes/generar", json={"marca": "unotv"})
    assert r.status_code == 200
    assert r.json()["n"] == 1


def test_generar_arte_modelo_explicito_se_propaga(entorno, monkeypatch):
    """Un `modelo` valido se usa y vuelve en la respuesta y en el resultado de la generacion."""
    modelo = "openai/gpt-5-image"
    cli = _cli_arte(monkeypatch, coste=0.05)
    r = cli.post("/api/artes/generar", json={"marca": "unotv", "prompt": "x", "modelo": modelo})
    assert r.status_code == 200
    assert r.json()["modelo"] == modelo
    assert r.json()["generaciones"][0]["resultado"]["modelo"] == modelo


def test_generar_arte_marca_invalida_400(entorno, monkeypatch):
    cli = _cli_arte(monkeypatch)
    assert cli.post("/api/artes/generar", json={"marca": "no-existe", "prompt": "x"}).status_code == 400
    assert cli.post("/api/artes/generar", json={"prompt": "x"}).status_code == 400


def test_generar_arte_n_fuera_de_rango_400(entorno, monkeypatch):
    cli = _cli_arte(monkeypatch)
    assert cli.post("/api/artes/generar", json={"marca": "unotv", "prompt": "x", "n": 0}).status_code == 400
    assert cli.post("/api/artes/generar", json={"marca": "unotv", "prompt": "x", "n": 99}).status_code == 400
    assert cli.post("/api/artes/generar", json={"marca": "unotv", "prompt": "x", "n": "muchas"}).status_code == 400


def test_generar_arte_modelo_invalido_400(entorno, monkeypatch):
    cli = _cli_arte(monkeypatch)
    r = cli.post("/api/artes/generar", json={"marca": "unotv", "prompt": "x", "modelo": "inventado/xl"})
    assert r.status_code == 400


def test_generar_arte_sin_proveedor_400(entorno, monkeypatch):
    """Sin clave de proveedor (no configurado) => 400 con mensaje claro, sin lanzar nada."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    cli = _cliente(lanzar_imagen=lanzador_imagen_ejecuta())
    r = cli.post("/api/artes/generar", json={"marca": "unotv", "prompt": "x"})
    assert r.status_code == 400
    assert "no está configurada" in r.json()["error"]


# --------------------------------------------------------------------------- #
# GET /api/artes/coste-medio (coste medio por imagen, USD, fallback global)     #
# --------------------------------------------------------------------------- #


def test_coste_medio_sin_datos(cliente):
    """Sin historial de imagen: por_imagen None y muestras 0 (el front cae al fallback)."""
    r = cliente.get("/api/artes/coste-medio")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["por_imagen"] is None
    assert cuerpo["muestras"] == 0
    assert cuerpo["moneda"] == "USD"


def test_coste_medio_por_modelo_con_fallback_global(entorno, monkeypatch):
    """Tras generar con un modelo, su coste medio sale; un modelo sin datos cae a la global."""
    modelo = "openai/gpt-5-image"
    cli = _cli_arte(monkeypatch, coste=0.04, modelo_dev=modelo)
    cli.post("/api/artes/generar", json={"marca": "unotv", "prompt": "x", "modelo": modelo, "n": 2})
    # El modelo con historial: media de sus generaciones.
    r = cli.get(f"/api/artes/coste-medio?modelo={modelo}")
    assert r.status_code == 200
    propio = r.json()
    assert propio["muestras"] == 2
    assert abs(propio["por_imagen"] - 0.04) < 1e-9
    assert propio["global"] is False
    # Otro modelo SIN historial propio: cae a la media global (que sí tiene datos).
    otro = cli.get("/api/artes/coste-medio?modelo=openai/gpt-5-image-mini").json()
    assert otro["global"] is True
    assert otro["muestras"] == 2


def test_coste_medio_modelo_invalido_400(cliente):
    assert cliente.get("/api/artes/coste-medio?modelo=inventado/xl").status_code == 400


# --------------------------------------------------------------------------- #
# FOTOS LICENCIADAS DE AGENCIA (AFP): buscar + adjuntar PUBLICABLE             #
# --------------------------------------------------------------------------- #


def _crear_pieza(cliente) -> dict:
    r = cliente.post(
        "/api/piezas",
        json={"marca": "unotv", "red": "x", "titulo": "T", "contenido": "C"},
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    return r.json()["pieza"]


def test_buscar_agencias_sin_credencial_lista_pendiente(cliente, monkeypatch):
    monkeypatch.setattr(config, "afp_configurado", lambda: False)
    r = cliente.get("/api/artes/agencias/buscar?q=mundial")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["candidatos"] == []
    assert cuerpo["proveedores"][0]["proveedor"] == "afp"
    assert cuerpo["proveedores"][0]["disponible"] is False


def test_buscar_agencias_devuelve_candidatos(cliente, monkeypatch):
    monkeypatch.setattr(config, "afp_configurado", lambda: True)
    monkeypatch.setattr(
        agencias_fotos,
        "_BUSCADOR",
        lambda q, n: {"response": {"docs": [
            {"title": "Gol", "creator": "Foto AFP", "creditline": "AFP",
             "medias": [{"role": "highdef", "href": "https://afp/g.jpg"}]}
        ]}},
    )
    r = cliente.get("/api/artes/agencias/buscar?q=gol&limite=3")
    assert r.status_code == 200
    cands = r.json()["candidatos"]
    assert len(cands) == 1
    assert cands[0]["proveedor"] == "afp"
    assert cands[0]["url"] == "https://afp/g.jpg"


def test_adjuntar_agencias_deja_pieza_licenciada_y_publicable(cliente, monkeypatch):
    monkeypatch.setattr(
        autogen_stock.extraccion_url, "descargar_imagen_a_media", lambda url, **kw: "afp.jpg"
    )
    pieza = _crear_pieza(cliente)
    r = cliente.post(
        "/api/artes/agencias/adjuntar",
        json={
            "pieza_id": pieza["id"],
            "url": "https://afp/g.jpg",
            "proveedor": "afp",
            "autor": "Foto AFP",
            "licencia": "AFP",
            "credito_url": "https://afp.com/g",
        },
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text
    plat = r.json()["plataforma"]
    assert plat["imagen_origen"] == "licenciada"
    assert plat["imagen_autorizada"] is True
    assert plat["falta_imagen"] is False
    assert plat["imagen_autor"] == "Foto AFP"

    fila = repos.obtener_pieza_fila(pieza["id"])
    assert fila["imagen_origen"] == "licenciada"

    # PUBLICABLE: programar NO se bloquea (la licencia cubre los derechos).
    r2 = cliente.patch(
        f"/api/publicaciones/{pieza['publicacion_id']}/plataformas/{pieza['id']}",
        json={"estado": "programado", "fecha_programada": "2030-01-01T10:00"},
        headers=_ORIGIN,
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["plataforma"]["estado"] == "programado"


def test_autorizar_stock_espeja_a_hermana_misma_foto(cliente):
    """Autorizar una foto de stock se ESPEJA a la hermana del mismo tema con la MISMA foto.

    La hermana lleva un `foto` DISTINTO (puede pasar entre redes) pero el mismo crédito: el
    matching robusto (por `imagen_credito_url`) la reconoce y autoriza también, sin obligar a
    autorizar red por red.
    """
    pieza = _crear_pieza(cliente)
    pub_id = pieza["publicacion_id"]
    meta = {
        "imagen_origen": "stock",
        "imagen_proveedor": "openverse",
        "imagen_autor": "Jane Doe",
        "imagen_licencia": "CC BY 4.0",
        "imagen_credito_url": "https://ov/obra",
        "imagen_autorizada": False,
        "falta_imagen": True,
    }
    repos.actualizar_pieza_fila(pieza["id"], {"foto": "stock.jpg", **meta})
    hermana = repos.crear_pieza_fila(publicacion_id=pub_id, red="facebook", falta_imagen=True)
    repos.actualizar_pieza_fila(hermana["id"], {"foto": "otra-key.jpg", **meta})

    r = cliente.post(
        "/api/artes/stock/autorizar",
        json={"pieza_id": pieza["id"], "autorizar": True},
        headers=_ORIGIN,
    )
    assert r.status_code == 200, r.text

    original = repos.obtener_pieza_fila(pieza["id"])
    assert original["imagen_autorizada"] in (True, 1)
    h = repos.obtener_pieza_fila(hermana["id"])
    assert h["imagen_autorizada"] in (True, 1)
    assert h["falta_imagen"] in (False, 0)


def test_adjuntar_agencias_sin_url_400(cliente):
    pieza = _crear_pieza(cliente)
    r = cliente.post(
        "/api/artes/agencias/adjuntar",
        json={"pieza_id": pieza["id"]},
        headers=_ORIGIN,
    )
    assert r.status_code == 400
