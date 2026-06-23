"""Propagación ROBUSTA y RETROACTIVA de la foto de stock entre redes hermanas.

La foto de stock es ayuda del TEMA, no edición por red: se reparte a TODA red en gris sin depender
del frágil toggle `espejo`, sin pisar imágenes propias ni publicadas, y el barrido repara
retroactivamente los temas que quedaron a medias. Aquí se cubre la selección (pura) y el relleno
(con la BD de pruebas, fixture `entorno`).
"""

from __future__ import annotations

from typing import Any

from keni_consola import autogen_stock, repos

_MARCA = "unotv"


def _plat(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "p", "copy": "", "imagen": "", "foto": "", "imagen_origen": "", "estado": "borrador",
    }
    base.update(kw)
    return base


def _item(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"id": "t", "clase": "contenido", "titulo": "T", "marca": _MARCA}
    base.update(kw)
    return base


# --- helpers puros ---------------------------------------------------------- #


def test_es_stock():
    assert autogen_stock._es_stock(_plat(foto="s.jpg", imagen_origen="stock"))
    assert not autogen_stock._es_stock(_plat(foto="s.jpg", imagen_origen=""))  # foto propia
    assert not autogen_stock._es_stock(_plat(imagen_origen="stock"))  # sin foto


# --- selección retroactiva (necesita el store de ajustes: fixture `entorno`) -- #


def test_topics_selecciona_no_procesado_con_vacia(entorno):
    items = [_item()]
    plats = {"t": [_plat(id="a", copy="c")]}
    out = autogen_stock.topics_sin_stock(items, plataformas_por_item=plats, ya_procesados=set(), maximo=5)
    assert [i["id"] for i in out] == ["t"]


def test_topics_omite_procesado_sin_foto_que_repartir(entorno):
    # Ya intentado y sin foto en ninguna red: no se re-busca (evita martillear las APIs).
    items = [_item()]
    plats = {"t": [_plat(id="a", copy="c")]}
    out = autogen_stock.topics_sin_stock(items, plataformas_por_item=plats, ya_procesados={"t"}, maximo=5)
    assert out == []


def test_topics_repara_procesado_si_hay_stock_que_repartir(entorno):
    # Aunque esté procesado, si una red tiene foto de stock y otra está en gris -> se elige (reparto).
    items = [_item()]
    plats = {"t": [_plat(id="a", copy="c"), _plat(id="b", copy="c", foto="s.jpg", imagen_origen="stock")]}
    out = autogen_stock.topics_sin_stock(items, plataformas_por_item=plats, ya_procesados={"t"}, maximo=5)
    assert [i["id"] for i in out] == ["t"]


def test_topics_omite_tema_completo(entorno):
    items = [_item()]
    plats = {"t": [_plat(id="a", copy="c", foto="x.jpg")]}
    out = autogen_stock.topics_sin_stock(items, plataformas_por_item=plats, ya_procesados=set(), maximo=5)
    assert out == []


# --- relleno robusto (BD) --------------------------------------------------- #


def _campos(foto: str = "stock.jpg") -> dict[str, Any]:
    return {
        "foto": foto, "imagen": "", "falta_imagen": True, "imagen_origen": "stock",
        "imagen_proveedor": "openverse", "imagen_autor": "", "imagen_licencia": "",
        "imagen_credito_url": "", "imagen_autorizada": False,
    }


def test_propagar_stock_rellena_vacias_y_respeta_propias(entorno):
    tema = repos.crear_publicacion(clase="contenido", titulo="T", marca=_MARCA)
    a = repos.crear_pieza_fila(publicacion_id=tema["id"], red="x", copy="c")["id"]
    b = repos.crear_pieza_fila(publicacion_id=tema["id"], red="instagram", copy="c")["id"]
    c = repos.crear_pieza_fila(publicacion_id=tema["id"], red="facebook", copy="c", foto="propia.jpg")["id"]
    n = autogen_stock.propagar_stock(tema["id"], _campos())
    assert n == 2  # a y b estaban en gris; c tenía foto propia
    assert repos.obtener_pieza_fila(a)["foto"] == "stock.jpg"
    assert repos.obtener_pieza_fila(b)["imagen_origen"] == "stock"
    assert repos.obtener_pieza_fila(c)["foto"] == "propia.jpg"  # NO se pisa


def test_adjuntar_candidata_propaga_a_todas_las_vacias(entorno, monkeypatch):
    llamadas: list[dict] = []

    def _stub(url, **kw):
        llamadas.append({"url": url, **kw})
        return "bajada.jpg"

    monkeypatch.setattr(autogen_stock.extraccion_url, "descargar_imagen_a_media", _stub)
    tema = repos.crear_publicacion(clase="contenido", titulo="T", marca=_MARCA)
    a = repos.crear_pieza_fila(publicacion_id=tema["id"], red="x", copy="c")["id"]
    b = repos.crear_pieza_fila(publicacion_id=tema["id"], red="instagram", copy="c")["id"]
    autogen_stock.adjuntar_candidata(a, url="https://x.test/y.jpg", proveedor="openverse")
    fa, fb = repos.obtener_pieza_fila(a), repos.obtener_pieza_fila(b)
    assert fa["foto"] == fb["foto"] == "bajada.jpg"
    assert fa["imagen_origen"] == fb["imagen_origen"] == "stock"
    # Sin autorizar en ninguna: el bloqueo sigue de pie hasta decisión humana.
    assert fa["imagen_autorizada"] is False and fb["imagen_autorizada"] is False
    # El stock SIN LICENCIA se descarga a la carpeta `copyright`, aislado de las fotos propias.
    assert llamadas == [{"url": "https://x.test/y.jpg", "categoria": "copyright"}]
