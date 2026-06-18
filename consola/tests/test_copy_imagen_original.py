"""La foto ORIGINAL de fuente propia se CATALOGA en la Prompts y se inyecta a la pieza.

Cuando `crear_publicaciones_desde_piezas` recibe `imagen_fuente` (og:image de un RSS de marca
propia), descarga la foto, la promueve a la carpeta protegida `artes`, la registra en el
catálogo de media con `tipo="original"` (así APARECE en la Galería de Artes bajo "Originales" y
el GC no la borra) y la pieza nace con ESA key como imagen del feed.

OFFLINE: backend de media en DISCO (S3_* borradas) y descarga binaria parcheada; DB en el
Postgres de pruebas vía la fixture `entorno`.
"""

from __future__ import annotations

from keni_consola import almacen_media, repos
from keni_consola.dominio import copy as dom_copy
from keni_consola.dominio import extraccion_url

_MARCA = "unotv"
_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x01\x02\x03" * 4


def _png(ancho: int, alto: int) -> bytes:
    """PNG mínimo con `ancho`×`alto` en su IHDR (suficiente para medir dimensiones)."""
    return (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\x0dIHDR"
        + ancho.to_bytes(4, "big")
        + alto.to_bytes(4, "big")
        + b"\x08\x06\x00\x00\x00"
    )


def _almacen_disco(monkeypatch):
    """Fuerza backend de media en DISCO (sin S3 ni red), como en test_extraccion_imagen."""
    for var in ("S3_ENDPOINT", "S3_ACCESS_KEY", "S3_SECRET_KEY", "S3_REGION", "S3_BUCKET"):
        monkeypatch.delenv(var, raising=False)
    almacen_media._resetear_cliente_s3()


def test_imagen_fuente_se_cataloga_como_original_y_se_inyecta(entorno, monkeypatch):
    _almacen_disco(monkeypatch)
    monkeypatch.setattr(extraccion_url, "_DESCARGADOR_BYTES", lambda url: _PNG)

    creadas = dom_copy.crear_publicaciones_desde_piezas(
        [{"red": "x", "contenido": "Hola", "copy_in": ""}],
        marca=_MARCA,
        titulo="Nota propia",
        verdicto="",
        origen="hist-1",
        imagen_fuente="https://example.com/foto.png",
        tipo_contenido="fuente",
    )

    # La pieza nace con la foto ORIGINAL como `foto` (foto cruda real, en la carpeta protegida
    # `artes`): así CUENTA como imagen y la pieza queda LISTA (sin "Falta imagen"). NO va a
    # `imagen` (ese campo es la placa horneada y en marca no cuenta como foto real).
    assert len(creadas) == 1
    foto = str(creadas[0].get("foto") or "")
    assert foto.startswith("artes/")
    assert str(creadas[0].get("imagen") or "") == ""
    assert creadas[0].get("falta_imagen") is False

    # Y queda CATALOGADA en la Prompts con tipo="original" y marca de la pieza.
    catalogo = repos.listar_media_catalogo()
    fila = next((c for c in catalogo if (c.get("objeto") or "") == foto), None)
    assert fila is not None
    assert fila.get("tipo") == dom_copy.TIPO_ARTE_ORIGINAL
    assert fila.get("marca") == _MARCA


def test_imagen_fuente_basura_diminuta_no_inyecta_y_queda_sin_foto(entorno, monkeypatch):
    """Una og:image basura/diminuta (p. ej. el emoji-fallback 72×72) NO se inyecta: la pieza
    queda SIN foto y con "Falta imagen" (criterio humano), en vez de auto-publicar algo roto."""
    _almacen_disco(monkeypatch)
    monkeypatch.setattr(extraccion_url, "_DESCARGADOR_BYTES", lambda url: _png(72, 72))

    creadas = dom_copy.crear_publicaciones_desde_piezas(
        [{"red": "x", "contenido": "Hola", "copy_in": ""}],
        marca=_MARCA,
        titulo="Nota con og:image basura",
        verdicto="",
        origen="hist-basura",
        imagen_fuente="https://example.com/emoji.png",
        tipo_contenido="fuente",
    )

    assert len(creadas) == 1
    assert str(creadas[0].get("foto") or "") == ""
    assert creadas[0].get("falta_imagen") is True
    # No se cataloga nada (no hubo descarga válida que promover a "Originales").
    assert repos.listar_media_catalogo() == []


def test_sin_imagen_fuente_no_cataloga_ni_pone_imagen(entorno, monkeypatch):
    _almacen_disco(monkeypatch)

    creadas = dom_copy.crear_publicaciones_desde_piezas(
        [{"red": "x", "contenido": "Hola", "copy_in": ""}],
        marca=_MARCA,
        titulo="Sin foto",
        verdicto="",
        origen="hist-2",
    )

    assert len(creadas) == 1
    assert str(creadas[0].get("imagen") or "") == ""
    assert repos.listar_media_catalogo() == []


# --------------------------------------------------------------------------- #
# CARRUSEL EDITORIAL (DOS tipos de output): slides con titular -> placas + flip #
# --------------------------------------------------------------------------- #


def _piezas_tres_redes():
    return [
        {"red": "instagram", "contenido": "Hola", "copy_in": "PANEL"},
        {"red": "x", "contenido": "Hola", "copy_in": "PANEL"},
        {"red": "facebook", "contenido": "Hola", "copy_in": "PANEL"},
    ]


def _mock_componer_slide(monkeypatch, *, falla=()):
    """Parchea el seam de composición de slides (el real corre el renderer Node).

    Devuelve la lista de llamadas `(marca, titular, foto)`. Los titulares en `falla`
    devuelven un slide incomponible (`objeto=""`). El seam devuelve `{"objeto", "foto"}`:
    `foto` espeja la foto fuente recibida (la procedencia que el slide persiste).
    """
    llamadas = []

    def fake(marca, titular, foto):
        llamadas.append((marca, titular, foto))
        if titular in falla:
            return {"objeto": "", "foto": ""}
        return {"objeto": f"artes/slide-{len(llamadas)}.png", "foto": foto or ""}

    monkeypatch.setattr(dom_copy, "_COMPONER_SLIDE", fake)
    return llamadas


def test_slides_carrusel_arman_pieza_carrusel_nidada(entorno, monkeypatch):
    """Con `slides_carrusel` y tema: placa por slide, flip a carrusel, redes X/IG/FB."""
    import json

    from keni_consola import redes

    _almacen_disco(monkeypatch)
    monkeypatch.setattr(extraccion_url, "_DESCARGADOR_BYTES", lambda url: _PNG)
    llamadas = _mock_componer_slide(monkeypatch)
    tema = repos.crear_publicacion(clase="contenido", titulo="Panel", marca=_MARCA)

    creadas = dom_copy.crear_publicaciones_desde_piezas(
        _piezas_tres_redes(),
        marca=_MARCA,
        titulo="Panel",
        verdicto="",
        origen="hist-3",
        publicacion_id=tema["id"],
        imagen_fuente="https://example.com/portada.png",
        tipo_contenido="fuente",
        slides_carrusel=[
            {"titular": "Concierto A", "foto": "https://example.com/a.png"},
            {"titular": "Concierto B", "foto": ""},
        ],
    )

    # Cada slide se HORNEÓ con su titular y su foto (la B, placa de solo texto).
    assert llamadas == [
        (_MARCA, "Concierto A", "https://example.com/a.png"),
        (_MARCA, "Concierto B", ""),
    ]
    # El FORMATO decide las redes: carrusel -> X/IG/FB (igual que foto; nunca yt/tiktok).
    assert sorted(str(c["red"]) for c in creadas) == ["facebook", "instagram", "x"]
    assert repos.obtener_publicacion(tema["id"])["formato"] == redes.FORMATO_CARRUSEL
    # Cada borrador lleva los slides horneados detrás de la portada (que va en `imagen`).
    for creada in creadas:
        slides = json.loads(str(creada.get("carrusel") or "[]"))
        assert [s["objeto"] for s in slides] == ["artes/slide-1.png", "artes/slide-2.png"]
        assert all(s["tipo"] == "imagen" for s in slides)
        assert str(creada.get("imagen") or "").startswith("artes/")
        # PROCEDENCIA persistida por slide (para re-editar la placa): titular siempre; foto fuente
        # solo si la sub-historia la traía (el slide A tenía foto; el B era placa de solo texto).
        assert slides[0]["titular"] == "Concierto A"
        assert slides[0]["foto"]  # foto fuente del slide A
        assert slides[1]["titular"] == "Concierto B"
        assert "foto" not in slides[1]  # sin foto fuente -> no se persiste el campo


def test_carrusel_degrada_a_post_si_ningun_slide_compone(entorno, monkeypatch):
    """Si NINGÚN slide se pudo hornear, todo sigue como post de foto (sin flip ni filtro)."""
    from keni_consola import redes

    _almacen_disco(monkeypatch)
    monkeypatch.setattr(extraccion_url, "_DESCARGADOR_BYTES", lambda url: _PNG)
    _mock_componer_slide(monkeypatch, falla=("Concierto A", "Concierto B"))
    tema = repos.crear_publicacion(clase="contenido", titulo="Panel", marca=_MARCA)

    creadas = dom_copy.crear_publicaciones_desde_piezas(
        _piezas_tres_redes(),
        marca=_MARCA,
        titulo="Panel",
        verdicto="",
        origen="hist-4",
        publicacion_id=tema["id"],
        imagen_fuente="https://example.com/portada.png",
        tipo_contenido="fuente",
        slides_carrusel=[
            {"titular": "Concierto A", "foto": ""},
            {"titular": "Concierto B", "foto": ""},
        ],
    )

    assert sorted(str(c["red"]) for c in creadas) == ["facebook", "instagram", "x"]
    assert repos.obtener_publicacion(tema["id"])["formato"] == redes.FORMATO_FOTO
    assert all(not str(c.get("carrusel") or "") for c in creadas)


def test_procesar_copy_arma_carrusel_si_el_modelo_lo_elige(entorno, monkeypatch):
    """Cableado parseo→depósito: `tipo: carrusel` + slides -> placas con la foto de SU nota."""
    import json

    from keni_consola import redes

    _almacen_disco(monkeypatch)
    monkeypatch.setattr(extraccion_url, "_DESCARGADOR_BYTES", lambda url: _PNG)
    llamadas = _mock_componer_slide(monkeypatch)
    tema = repos.crear_publicacion(clase="contenido", titulo="Panel", marca=_MARCA)
    fotos = [
        {"titulo": "Concierto A", "imagen": "https://example.com/a.png"},
        {"titulo": "Concierto B", "imagen": "https://example.com/b.png"},
    ]

    procesar = dom_copy.construir_procesar_copy(
        "copy-desde-nota", _MARCA,
        redes_ids=["instagram", "x", "facebook"], titulo_dado="Panel", texto_base="nota",
        publicacion_id=tema["id"], imagen_fuente=fotos[0]["imagen"], fotos_notas=fotos,
        tipo_contenido="fuente",
    )
    salida = (
        '```json\n{"texto": "Copy", "copy_in": "PANEL", "tipo": "carrusel", '
        '"slides": [{"titular": "Concierto B", "foto": 2}, '
        '{"titular": "Sin foto", "foto": 0}, '
        '{"titular": "Fuera de rango", "foto": 7}]}\n```'
    )
    resultado = procesar(salida, None)

    # Cada slide resolvió su foto por NÚMERO del catálogo (0/fuera de rango = sin foto).
    assert llamadas == [
        (_MARCA, "Concierto B", "https://example.com/b.png"),
        (_MARCA, "Sin foto", ""),
        (_MARCA, "Fuera de rango", ""),
    ]
    assert sorted(str(p["red"]) for p in resultado["piezas"]) == ["facebook", "instagram", "x"]
    assert repos.obtener_publicacion(tema["id"])["formato"] == redes.FORMATO_CARRUSEL
    slides = json.loads(str(resultado["piezas"][0].get("carrusel") or "[]"))
    assert len(slides) == 3


def test_procesar_copy_carrusel_sin_panel_no_flip_de_formato(entorno, monkeypatch):
    """`tipo: carrusel` SIN panel horneable (1 slide / tema único) NO cambia el formato.

    El modelo eligió carrusel pero no hay panel multi-historia que hornear (menos de 2 slides,
    sin catálogo de fotos): no se hornea ninguna placa y el formato NO flip-ea. El post sigue
    siendo foto; el equipo arma el carrusel a mano (acción «Carrusel» del feed)."""
    from keni_consola import redes

    _almacen_disco(monkeypatch)
    monkeypatch.setattr(extraccion_url, "_DESCARGADOR_BYTES", lambda url: _PNG)
    llamadas = _mock_componer_slide(monkeypatch)
    tema = repos.crear_publicacion(clase="contenido", titulo="Biomas", marca=_MARCA)

    procesar = dom_copy.construir_procesar_copy(
        "copy-desde-nota", _MARCA,
        redes_ids=["instagram", "x"], titulo_dado="Biomas", texto_base="nota",
        publicacion_id=tema["id"], imagen_fuente="https://example.com/portada.png",
        fotos_notas=[], tipo_contenido="fuente",
    )
    salida = (
        '```json\n{"texto": "Copy", "copy_in": "T", "tipo": "carrusel", '
        '"slides": [{"titular": "Única", "foto": 0}]}\n```'
    )
    resultado = procesar(salida, None)

    # Ningún slide horneado (no es panel) y el formato NO flip-ea: sigue siendo foto.
    assert llamadas == []
    assert repos.obtener_publicacion(tema["id"])["formato"] == redes.FORMATO_FOTO
    # Las redes son las del lanzamiento (foto), sin acotar a las del carrusel.
    assert sorted(str(p["red"]) for p in resultado["piezas"]) == ["instagram", "x"]
    # El campo `carrusel` de la pieza queda vacío.
    assert all(not str(p.get("carrusel") or "") for p in resultado["piezas"])


def test_procesar_copy_carrusel_de_tema_unico_sin_slides_no_flip(entorno, monkeypatch):
    """Un TEMA ÚNICO que sugiere `tipo: carrusel` SIN clave `slides` NO cambia el formato.

    No hay nada que hornear (es un explainer, no un panel multi-historia) y la sugerencia ya NO
    flip-ea el formato: el post sigue siendo foto y el equipo decide el carrusel a mano (acción
    «Carrusel» del feed)."""
    from keni_consola import redes

    _almacen_disco(monkeypatch)
    monkeypatch.setattr(extraccion_url, "_DESCARGADOR_BYTES", lambda url: _PNG)
    llamadas = _mock_componer_slide(monkeypatch)
    tema = repos.crear_publicacion(clase="contenido", titulo="Biomas de México", marca=_MARCA)

    procesar = dom_copy.construir_procesar_copy(
        "copy-desde-nota", _MARCA,
        redes_ids=["instagram", "x", "facebook"], titulo_dado="Biomas", texto_base="nota",
        publicacion_id=tema["id"], imagen_fuente="https://example.com/portada.png",
        fotos_notas=[], tipo_contenido="fuente",
    )
    # Sugerencia pura: `tipo: carrusel` y NI SIQUIERA clave `slides`.
    salida = '```json\n{"texto": "Copy", "copy_in": "BIOMAS", "tipo": "carrusel"}\n```'
    resultado = procesar(salida, None)

    assert llamadas == []  # nada que hornear
    assert repos.obtener_publicacion(tema["id"])["formato"] == redes.FORMATO_FOTO
    assert sorted(str(p["red"]) for p in resultado["piezas"]) == ["facebook", "instagram", "x"]
    assert all(not str(p.get("carrusel") or "") for p in resultado["piezas"])


def test_procesar_copy_tipo_post_no_arma_carrusel(entorno, monkeypatch):
    """Con catálogo disponible pero `tipo: post` (o sin tipo), la pieza es el post de siempre."""
    from keni_consola import redes

    _almacen_disco(monkeypatch)
    monkeypatch.setattr(extraccion_url, "_DESCARGADOR_BYTES", lambda url: _PNG)
    llamadas = _mock_componer_slide(monkeypatch)
    tema = repos.crear_publicacion(clase="contenido", titulo="Panel", marca=_MARCA)
    fotos = [
        {"titulo": "Concierto A", "imagen": "https://example.com/a.png"},
        {"titulo": "Concierto B", "imagen": "https://example.com/b.png"},
    ]

    procesar = dom_copy.construir_procesar_copy(
        "copy-desde-nota", _MARCA,
        redes_ids=["instagram", "x", "facebook"], titulo_dado="Panel", texto_base="nota",
        publicacion_id=tema["id"], imagen_fuente=fotos[0]["imagen"], fotos_notas=fotos,
        tipo_contenido="fuente",
    )
    salida = '```json\n{"texto": "Copy", "copy_in": "T"}\n```'
    resultado = procesar(salida, None)

    assert llamadas == []
    assert sorted(str(p["red"]) for p in resultado["piezas"]) == [
        "facebook", "instagram", "x",
    ]
    assert repos.obtener_publicacion(tema["id"])["formato"] == redes.FORMATO_FOTO
    assert all(not str(p.get("carrusel") or "") for p in resultado["piezas"])


def test_slides_carrusel_sin_tema_se_ignoran(entorno, monkeypatch):
    """Sin `publicacion_id` no hay carrusel que nidar: borradores sueltos de foto, como hoy."""
    _almacen_disco(monkeypatch)
    monkeypatch.setattr(extraccion_url, "_DESCARGADOR_BYTES", lambda url: _PNG)
    llamadas = _mock_componer_slide(monkeypatch)

    creadas = dom_copy.crear_publicaciones_desde_piezas(
        _piezas_tres_redes(),
        marca=_MARCA,
        titulo="Suelta",
        verdicto="",
        origen="hist-5",
        imagen_fuente="https://example.com/portada.png",
        tipo_contenido="fuente",
        slides_carrusel=[{"titular": "A", "foto": ""}, {"titular": "B", "foto": ""}],
    )

    assert llamadas == []
    assert sorted(str(c["red"]) for c in creadas) == ["facebook", "instagram", "x"]
    assert all(not str(c.get("carrusel") or "") for c in creadas)
