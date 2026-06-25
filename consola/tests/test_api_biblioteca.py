"""Tests de la Biblioteca de medios UNIFICADA (/api/biblioteca) + la forma `fuente`/`grupo`.

OFFLINE: ninguna red real. El túnel keni-fotos se simula con una conexión FAKE en memoria (mismo
patrón que `test_api_propio`). Cubre: las columnas nuevas (`fuente`/`grupo`) del catálogo y su
filtrado; el buscador global y sus filtros; conteos de carpetas; guardar una foto remota
(conservando etiquetas); adjuntar un item a una pieza; y la descarga del binario.
"""

from __future__ import annotations

import base64
import json

from keni_consola import fotos_tunel, media, repos

# PNG 1x1 válido: binario de prueba (objeto de media / original del túnel).
_PNG_1x1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _catalogar(*, fuente: str, grupo: str = "", titulo: str = "", etiquetas=None,
               marca: str = "claro-sports", sufijo: bytes = b"") -> dict:
    """Sube un PNG al almacén y lo cataloga con `fuente`/`grupo`; devuelve el item."""
    key = media.guardar_bytes(_PNG_1x1 + sufijo, ext="png", categoria="fotografias")
    return repos.crear_media_catalogo(
        objeto=key, tipo="imagen", titulo=titulo, marca=marca,
        etiquetas=json.dumps(etiquetas or [], ensure_ascii=False),
        fuente=fuente, grupo=grupo,
    )


# --------------------------------------------------------------------------- #
# Forma del catálogo: columnas `fuente`/`grupo` y su filtrado                   #
# --------------------------------------------------------------------------- #


def test_crear_y_filtrar_por_fuente_y_grupo(entorno):
    a = _catalogar(fuente="fotografias", grupo="colombia uzbekistan", sufijo=b"a")
    _catalogar(fuente="originales", grupo="", sufijo=b"b")

    leido = repos.obtener_media_catalogo(a["id"])
    assert leido["fuente"] == "fotografias"
    assert leido["grupo"] == "colombia uzbekistan"

    solo_foto = repos.listar_media_catalogo(fuente="fotografias")
    assert {i["id"] for i in solo_foto} == {a["id"]}
    por_grupo = repos.listar_media_catalogo(grupo="colombia uzbekistan")
    assert {i["id"] for i in por_grupo} == {a["id"]}


# --------------------------------------------------------------------------- #
# GET /api/biblioteca: buscador global + filtros                                #
# --------------------------------------------------------------------------- #


def test_biblioteca_global_cruza_las_fuentes(cliente):
    _catalogar(fuente="fotografias", titulo="Estadio", sufijo=b"1")
    _catalogar(fuente="originales", titulo="Rueda de prensa", sufijo=b"2")
    _catalogar(fuente="portal", titulo="Nota portal", sufijo=b"3")

    items = cliente.get("/api/biblioteca").json()["items"]
    assert {i["fuente"] for i in items} >= {"fotografias", "originales", "portal"}
    # Forma del item: url/thumb por /api/media.
    uno = next(i for i in items if i["titulo"] == "Estadio")
    assert uno["url"] == f"/api/media/{uno['key']}"
    assert uno["thumb"].startswith(f"/api/media/{uno['key']}")


def test_biblioteca_filtra_por_fuente(cliente):
    _catalogar(fuente="fotografias", titulo="A", sufijo=b"1")
    _catalogar(fuente="portal", titulo="B", sufijo=b"2")
    items = cliente.get("/api/biblioteca?fuente=portal").json()["items"]
    assert [i["titulo"] for i in items] == ["B"]


def test_biblioteca_busca_por_titulo_y_etiqueta(cliente):
    _catalogar(fuente="fotografias", titulo="Portero ataja", etiquetas=["penal"], sufijo=b"1")
    _catalogar(fuente="fotografias", titulo="Banca", etiquetas=["suplentes"], sufijo=b"2")
    por_titulo = cliente.get("/api/biblioteca?q=portero").json()["items"]
    assert [i["titulo"] for i in por_titulo] == ["Portero ataja"]
    por_tag = cliente.get("/api/biblioteca?q=PENAL").json()["items"]  # case-insensitive
    assert [i["titulo"] for i in por_tag] == ["Portero ataja"]


def test_biblioteca_fuente_invalida_400(cliente):
    assert cliente.get("/api/biblioteca?fuente=basura").status_code == 400


# --------------------------------------------------------------------------- #
# GET /api/biblioteca/carpetas: conteos                                         #
# --------------------------------------------------------------------------- #


def test_carpetas_cuenta_por_fuente_y_grupo(cliente):
    _catalogar(fuente="fotografias", grupo="partido x", sufijo=b"1")
    _catalogar(fuente="fotografias", grupo="partido x", sufijo=b"2")
    _catalogar(fuente="originales", sufijo=b"3")

    carpetas = {c["fuente"]: c for c in cliente.get("/api/biblioteca/carpetas").json()["carpetas"]}
    assert carpetas["fotografias"]["total"] == 2
    assert carpetas["originales"]["total"] == 1
    assert carpetas["portal"]["total"] == 0
    grupos = {g["grupo"]: g["total"] for g in carpetas["fotografias"]["grupos"]}
    assert grupos == {"partido x": 2}


# --------------------------------------------------------------------------- #
# POST /api/biblioteca/guardar-remoto: original del túnel + conserva etiquetas  #
# --------------------------------------------------------------------------- #


def _conexion_original(marca: str):
    """Registra una conexión FAKE que sirve el original `_PNG_1x1` y declara una galería con nombre."""
    class _FakeWS:
        def __init__(self):
            self.conexion = None

        async def send_json(self, mensaje):
            if self.conexion is None:
                return
            if mensaje.get("tipo") == "original":
                self.conexion.resolver(mensaje["id"], {
                    "tipo": "original_datos", "id": mensaje["id"], "mime": "image/png",
                    "datos_b64": base64.b64encode(_PNG_1x1).decode("ascii"),
                })
            elif mensaje.get("tipo") == "rafaga":
                self.conexion.resolver(mensaje["id"], {
                    "tipo": "rafaga_datos", "id": mensaje["id"],
                    "fotos": [
                        {"archivo": "keeper.jpg", "thumb_b64": "data:image/jpeg;base64,xx"},
                        {"archivo": "keeper2.jpg", "thumb_b64": "data:image/jpeg;base64,yy"},
                    ],
                })

    ws = _FakeWS()
    conexion = fotos_tunel.Conexion(ws, "ale")
    conexion.dispositivo = "Mac de Ale"
    conexion.galerias = [{"id": "g1", "nombre": "Colombia vs Uzbekistán"}]
    conexion.marcas = {marca}
    ws.conexion = conexion
    fotos_tunel.registrar(conexion)
    return conexion


def test_guardar_remoto_cataloga_en_fotografias_y_conserva_etiquetas(cliente):
    fotos_tunel._REGISTRO.clear()
    try:
        _conexion_original("claro-sports")
        r = cliente.post(
            "/api/biblioteca/guardar-remoto",
            json={"galeria_id": "g1", "archivo": "keeper.jpg", "marca": "claro-sports",
                  "titulo": "Atajada", "etiquetas": ["portero", "in-game"]},
        )
        assert r.status_code == 200, r.text
        item = r.json()["item"]
        assert item["fuente"] == "fotografias"
        assert item["grupo"] == "Colombia vs Uzbekistán"  # nombre de la galería, no el id
        assert item["etiquetas"] == ["portero", "in-game"]  # MANTENER etiquetas
        assert item["key"].startswith("fotografias/")
        # Coordenadas del túnel echoadas para navegar la ráfaga justo tras guardar.
        assert item["galeria_id"] == "g1" and item["archivo"] == "keeper.jpg"
        # Persistió en el catálogo y aparece en el buscador.
        assert any(i["id"] == item["id"] for i in cliente.get("/api/biblioteca").json()["items"])
    finally:
        fotos_tunel._REGISTRO.clear()


def test_rafaga_propio_lista_el_burst(cliente):
    fotos_tunel._REGISTRO.clear()
    try:
        _conexion_original("claro-sports")
        r = cliente.get(
            "/api/artes/propio/rafaga?galeria_id=g1&archivo=keeper.jpg&marca=claro-sports"
        )
        assert r.status_code == 200
        fotos = r.json()["fotos"]
        assert [f["archivo"] for f in fotos] == ["keeper.jpg", "keeper2.jpg"]
        assert all(f["thumb"] for f in fotos)
    finally:
        fotos_tunel._REGISTRO.clear()


def test_rafaga_propio_sin_datos_devuelve_vacio(cliente):
    fotos_tunel._REGISTRO.clear()
    assert cliente.get("/api/artes/propio/rafaga?galeria_id=g1").json() == {"fotos": []}


def test_guardar_remoto_sin_dispositivo_400(cliente):
    fotos_tunel._REGISTRO.clear()
    r = cliente.post(
        "/api/biblioteca/guardar-remoto",
        json={"galeria_id": "g1", "archivo": "keeper.jpg", "marca": "claro-sports"},
    )
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# POST /api/biblioteca/adjuntar + GET /api/biblioteca/descargar/{id}            #
# --------------------------------------------------------------------------- #


def test_adjuntar_item_a_pieza(cliente):
    tema = repos.crear_publicacion(clase="contenido", titulo="T", marca="claro-sports")
    pid = repos.crear_pieza_fila(publicacion_id=tema["id"], red="instagram", copy="c")["id"]
    item = _catalogar(fuente="fotografias", titulo="Foto", sufijo=b"adj")

    r = cliente.post("/api/biblioteca/adjuntar", json={"pieza_id": pid, "id": item["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["plataforma"]["foto"]

    fila = repos.obtener_pieza_fila(pid)
    assert fila["imagen_origen"] == "galeria"
    assert bool(fila["falta_imagen"]) is False
    assert fila["foto"]


def test_adjuntar_item_inexistente_404(cliente):
    tema = repos.crear_publicacion(clase="contenido", titulo="T", marca="claro-sports")
    pid = repos.crear_pieza_fila(publicacion_id=tema["id"], red="instagram", copy="c")["id"]
    r = cliente.post("/api/biblioteca/adjuntar", json={"pieza_id": pid, "id": "noexiste"})
    assert r.status_code == 404


def test_descargar_devuelve_attachment(cliente):
    item = _catalogar(fuente="fotografias", titulo="Foto", sufijo=b"dl")
    r = cliente.get(f"/api/biblioteca/descargar/{item['id']}")
    assert r.status_code == 200
    assert r.content == _PNG_1x1 + b"dl"
    assert "attachment" in r.headers["content-disposition"]


def test_descargar_inexistente_404(cliente):
    assert cliente.get("/api/biblioteca/descargar/noexiste").status_code == 404
