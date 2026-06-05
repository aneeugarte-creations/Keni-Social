"""Tests de la semilla de PLANTILLAS DE DISEÑO (sin BD).

Solo valida la construcción de los documentos (pura): que CADA documento de la semilla
pase `estudio_imagen.validar_documento`, declare un hueco de foto explícito, y que las
marcas/nombres sean los esperados. La creación real en Postgres la valida el CI.
"""

from __future__ import annotations

from keni_consola import plantillas_semilla as ps
from keni_consola.dominio import estudio_imagen

# Marcas y nombres esperados (espejo del catálogo de la semilla). UnoTV NO se siembra.
_ESPERADO: dict[str, set[str]] = {
    "claro-sports": {
        "Galería informativa",
        "Galería informativa · centro",
        "Breaking",
        "Foto limpia",
    },
    "fundacion": {"Comunidad", "Historia", "Foto limpia"},
}


def test_marcas_y_nombres_esperados() -> None:
    docs = ps.documentos_semilla()
    por_marca: dict[str, set[str]] = {}
    for marca, nombre, _categoria, _doc in docs:
        por_marca.setdefault(marca, set()).add(nombre)
    assert por_marca == _ESPERADO
    # UnoTV no se siembra (ya está en producción): no aparece en la semilla.
    assert "unotv" not in por_marca


def test_categoria_es_post() -> None:
    for _marca, _nombre, categoria, _doc in ps.documentos_semilla():
        assert categoria == "post"


def test_cada_documento_valida() -> None:
    for marca, nombre, _categoria, doc in ps.documentos_semilla():
        # No debe lanzar: documento válido según el esquema de capas.
        estudio_imagen.validar_documento(doc)
        assert doc["marca"] == marca, f"{marca}/{nombre}: marca incoherente"


def test_cada_documento_tiene_hueco_de_foto() -> None:
    for marca, nombre, _categoria, doc in ps.documentos_semilla():
        assert estudio_imagen.documento_tiene_hueco(doc), (
            f"{marca}/{nombre} debe declarar un hueco de foto explícito (es_foto)"
        )


def test_formato_feed_y_fondo_color() -> None:
    for _marca, _nombre, _categoria, doc in ps.documentos_semilla():
        fmt = doc["formato"]
        assert (fmt["w"], fmt["h"]) == (1080, 1350)
        assert doc["fondo"]["tipo"] == "color"


def test_titular_usa_binding_copy_in_donde_aplica() -> None:
    # Las plantillas con titular grande deben bindear el copy de la pieza.
    docs = {(m, n): d for m, n, _c, d in ps.documentos_semilla()}
    con_titular = [
        ("claro-sports", "Galería informativa"),
        ("claro-sports", "Galería informativa · centro"),
        ("claro-sports", "Breaking"),
        ("fundacion", "Comunidad"),
        ("fundacion", "Historia"),
    ]
    for clave in con_titular:
        capas = docs[clave]["capas"]
        bindings = {c.get("binding") for c in capas if c.get("tipo") == "texto"}
        assert "copy_in" in bindings, f"{clave} debe tener un texto con binding copy_in"


def test_chip_usa_acento_de_marca() -> None:
    # El chip de etiqueta debe pintar con el acento de la marca (rojo / ámbar).
    docs = {(m, n): d for m, n, _c, d in ps.documentos_semilla()}
    # claro-sports = rojo #CF2E2E ; fundacion = ámbar #D97706 (de marcas.json)
    casos = {
        ("claro-sports", "Breaking"): "#CF2E2E",
        ("fundacion", "Comunidad"): "#D97706",
    }
    for clave, acento in casos.items():
        chips = [
            c.get("chip") for c in docs[clave]["capas"]
            if c.get("tipo") == "texto" and c.get("chip")
        ]
        assert chips, f"{clave} debe tener un chip de etiqueta"
        assert any(ch["color"] == acento for ch in chips), (
            f"{clave}: el chip debe usar el acento {acento}"
        )
