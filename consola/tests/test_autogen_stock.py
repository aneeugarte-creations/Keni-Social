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


def test_topics_selecciona_divergente_sin_huecos_vacios(entorno):
    # Tema sin red en gris pero con DOS fotos de stock distintas: se elige para UNIFICAR (aunque
    # esté procesado: repartir no gasta APIs).
    items = [_item()]
    plats = {
        "t": [
            _plat(id="a", copy="c", foto="x.jpg", imagen_origen="stock", imagen_credito_url="u-a"),
            _plat(id="b", copy="c", foto="y.jpg", imagen_origen="stock", imagen_credito_url="u-b"),
        ]
    }
    out = autogen_stock.topics_sin_stock(items, plataformas_por_item=plats, ya_procesados={"t"}, maximo=5)
    assert [i["id"] for i in out] == ["t"]


def test_topics_omite_stock_convergente_sin_vacias(entorno):
    # Misma foto de stock en todas las redes y sin huecos: nada que unificar -> no se elige.
    items = [_item()]
    plats = {
        "t": [
            _plat(id="a", copy="c", foto="x.jpg", imagen_origen="stock", imagen_credito_url="u"),
            _plat(id="b", copy="c", foto="x.jpg", imagen_origen="stock", imagen_credito_url="u"),
        ]
    }
    out = autogen_stock.topics_sin_stock(items, plataformas_por_item=plats, ya_procesados=set(), maximo=5)
    assert out == []


def test_topics_omite_tema_completo(entorno):
    items = [_item()]
    plats = {"t": [_plat(id="a", copy="c", foto="x.jpg")]}
    out = autogen_stock.topics_sin_stock(items, plataformas_por_item=plats, ya_procesados=set(), maximo=5)
    assert out == []


def test_topics_omite_portal(entorno):
    # PORTAL: usa SOLO su foto propia; nunca foto de stock, aunque la pieza esté en gris.
    items = [_item(origen=autogen_stock.ORIGEN_PORTAL)]
    plats = {"t": [_plat(id="a", copy="c")]}
    out = autogen_stock.topics_sin_stock(items, plataformas_por_item=plats, ya_procesados=set(), maximo=5)
    assert out == []
    # Un tema del pipeline normal en la misma situación SÍ se elige.
    items_pipeline = [_item(origen="pipeline")]
    out_pipeline = autogen_stock.topics_sin_stock(
        items_pipeline, plataformas_por_item=plats, ya_procesados=set(), maximo=5
    )
    assert [i["id"] for i in out_pipeline] == ["t"]


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


def test_propagar_stock_unifica_hermana_con_otra_foto_de_stock(entorno):
    # UNA foto por tema: una hermana con OTRA foto de stock (autor/crédito divergentes) se UNIFICA
    # a la canónica; una red en gris se rellena. Ambas acaban con los MISMOS campos.
    tema = repos.crear_publicacion(clase="contenido", titulo="T", marca=_MARCA)
    a = repos.crear_pieza_fila(publicacion_id=tema["id"], red="x", copy="c")["id"]
    b = repos.crear_pieza_fila(publicacion_id=tema["id"], red="facebook", copy="c")["id"]
    repos.actualizar_pieza_fila(
        b,
        {
            "foto": "otra.jpg", "imagen_origen": "stock", "imagen_proveedor": "pexels",
            "imagen_autor": "Autor B", "imagen_credito_url": "https://b.test", "falta_imagen": True,
        },
    )
    n = autogen_stock.propagar_stock(tema["id"], _campos())  # canónica: stock.jpg / openverse
    assert n == 2  # a (gris) rellenada + b (stock divergente) unificada
    fa, fb = repos.obtener_pieza_fila(a), repos.obtener_pieza_fila(b)
    assert fa["foto"] == fb["foto"] == "stock.jpg"
    assert fb["imagen_proveedor"] == "openverse"
    assert fb["imagen_autor"] == ""
    assert fb["imagen_credito_url"] == ""


def test_propagar_stock_no_pisa_imagen_propia(entorno):
    # La unificación es SOLO entre fotos de stock: una imagen PROPIA del usuario nunca se sobrescribe.
    tema = repos.crear_publicacion(clase="contenido", titulo="T", marca=_MARCA)
    c = repos.crear_pieza_fila(publicacion_id=tema["id"], red="facebook", copy="c")["id"]
    repos.actualizar_pieza_fila(c, {"foto": "propia.jpg", "imagen_origen": "subida"})
    n = autogen_stock.propagar_stock(tema["id"], _campos())
    assert n == 0
    fc = repos.obtener_pieza_fila(c)
    assert fc["foto"] == "propia.jpg"
    assert fc["imagen_origen"] == "subida"


def test_propagar_stock_no_pisa_stock_autorizada(entorno):
    # Una foto de stock que un humano ya AUTORIZÓ no se unifica (su decisión manda): se preserva.
    tema = repos.crear_publicacion(clase="contenido", titulo="T", marca=_MARCA)
    c = repos.crear_pieza_fila(publicacion_id=tema["id"], red="facebook", copy="c")["id"]
    repos.actualizar_pieza_fila(
        c,
        {
            "foto": "autorizada.jpg", "imagen_origen": "stock", "imagen_proveedor": "pexels",
            "imagen_autorizada": True, "falta_imagen": False,
        },
    )
    n = autogen_stock.propagar_stock(tema["id"], _campos())
    assert n == 0
    assert repos.obtener_pieza_fila(c)["foto"] == "autorizada.jpg"


def test_propagar_stock_idempotente_no_reescribe_la_canonica(entorno):
    # Una red que YA tiene la canónica no se vuelve a tocar (no diverge).
    tema = repos.crear_publicacion(clase="contenido", titulo="T", marca=_MARCA)
    b = repos.crear_pieza_fila(publicacion_id=tema["id"], red="facebook", copy="c")["id"]
    repos.actualizar_pieza_fila(b, _campos())  # ya es la canónica
    assert autogen_stock.propagar_stock(tema["id"], _campos()) == 0


def test_lanzar_para_topic_no_rebusca_si_ya_hay_stock(entorno, monkeypatch):
    # Camino 1: con stock en alguna red, se reparte la canónica y NUNCA se llama a las APIs.
    llamadas: list[str] = []
    monkeypatch.setattr(
        autogen_stock.stock_fotos, "buscar_todos",
        lambda *a, **k: (llamadas.append("buscar"), [])[1],
    )
    tema = repos.crear_publicacion(clase="contenido", titulo="T", marca=_MARCA)
    a = repos.crear_pieza_fila(publicacion_id=tema["id"], red="x", copy="c")["id"]
    b = repos.crear_pieza_fila(publicacion_id=tema["id"], red="facebook", copy="c")["id"]
    repos.actualizar_pieza_fila(b, _campos())  # b ya tiene foto de stock
    autogen_stock.lanzar_para_topic({"id": tema["id"], "titulo": "T", "marca": _MARCA})
    assert llamadas == []  # no se buscó: se repartió la existente
    assert repos.obtener_pieza_fila(a)["foto"] == "stock.jpg"  # gris -> canónica


def test_lanzar_para_topic_unifica_sin_red_en_gris(entorno, monkeypatch):
    # Tema SIN huecos vacíos pero con stock DIVERGENTE entre redes: converge a una sola, sin buscar.
    llamadas: list[str] = []
    monkeypatch.setattr(
        autogen_stock.stock_fotos, "buscar_todos",
        lambda *a, **k: (llamadas.append("buscar"), [])[1],
    )
    tema = repos.crear_publicacion(clase="contenido", titulo="T", marca=_MARCA)
    # `creado` explícito y distinto: la canónica es la PRIMERA red con stock por el orden de
    # `listar_piezas_fila` (`creado ASC, id ASC`). Sin fijarlo, ambas filas comparten el segundo
    # (`ahora_iso` redondea a segundos) y el desempate cae al `id` (uuid aleatorio): cuál gana sería
    # una moneda al aire. Con `a` anterior a `b`, `a` es la canónica de forma determinista.
    a = repos.crear_pieza_fila(
        publicacion_id=tema["id"], red="x", copy="c", creado="2026-06-24T10:00:00"
    )["id"]
    b = repos.crear_pieza_fila(
        publicacion_id=tema["id"], red="facebook", copy="c", creado="2026-06-24T10:00:01"
    )["id"]
    repos.actualizar_pieza_fila(a, _campos("foto_a.jpg"))
    repos.actualizar_pieza_fila(b, _campos("foto_b.jpg"))
    autogen_stock.lanzar_para_topic({"id": tema["id"], "titulo": "T", "marca": _MARCA})
    assert llamadas == []
    fa, fb = repos.obtener_pieza_fila(a), repos.obtener_pieza_fila(b)
    # La canónica es la primera red con stock (a, la de `creado` más antiguo); b converge a ella.
    assert fa["foto"] == fb["foto"] == "foto_a.jpg"


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
    # El stock SIN LICENCIA se descarga a la carpeta `copyright` (aislado de las fotos propias)
    # y con piso de tamaño, para descartar iconos/emojis colados como candidata.
    assert llamadas == [
        {"url": "https://x.test/y.jpg", "categoria": "copyright", "min_lado": 320}
    ]
