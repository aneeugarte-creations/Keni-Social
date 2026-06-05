"""Tests de la semilla de PLANTILLAS DE DISEÑO (sin BD).

Solo valida la construcción de los documentos (pura): que CADA documento de la semilla
pase `estudio_imagen.validar_documento`, declare un hueco de foto explícito, y que las
marcas/nombres sean los esperados. La creación/refresco real en Postgres la valida el CI.
"""

from __future__ import annotations

from keni_consola import plantillas_semilla as ps
from keni_consola.dominio import estudio_imagen

# Marcas y nombres esperados (espejo del catálogo de la semilla). UnoTV NO se siembra.
_ESPERADO: dict[str, set[str]] = {
    "claro-sports": {"Titular", "Breaking", "Cita textual", "Foto limpia"},
    "fundacion": {"Titular", "Foto limpia"},
    "nacion-gamer": {"Titular", "Destacado", "Foto limpia"},
    "piso-15": {"Titular", "Foto limpia"},
}


def _docs() -> dict[tuple[str, str], dict]:
    return {(m, n): d for m, n, _c, d in ps.documentos_semilla()}


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
    # Las plantillas con titular/cita grande deben bindear el copy de la pieza.
    docs = _docs()
    con_copy = [
        ("claro-sports", "Titular"),
        ("claro-sports", "Breaking"),
        ("claro-sports", "Cita textual"),
        ("fundacion", "Titular"),
        ("nacion-gamer", "Titular"),
        ("nacion-gamer", "Destacado"),
        ("piso-15", "Titular"),
    ]
    for clave in con_copy:
        capas = docs[clave]["capas"]
        bindings = {c.get("binding") for c in capas if c.get("tipo") == "texto"}
        assert "copy_in" in bindings, f"{clave} debe tener un texto con binding copy_in"


def test_claro_breaking_pildora_y_secundaria() -> None:
    # Breaking: píldora roja FIJA "BREAKING" (chip redondeado) + titular + línea secundaria.
    capas = _docs()[("claro-sports", "Breaking")]["capas"]
    pildoras = [
        c for c in capas
        if c.get("tipo") == "texto" and c.get("chip") and c.get("texto") == "BREAKING"
    ]
    assert pildoras, "Breaking debe tener una píldora fija 'BREAKING'"
    chip = pildoras[0]["chip"]
    assert chip["color"] == "#CF2E2E" and chip["radio"] > 0, "la píldora debe ser roja y redondeada"
    assert pildoras[0]["binding"] is None, "la píldora 'BREAKING' es texto fijo (sin binding)"


def test_claro_cita_tiene_retrato_y_aro_elipse() -> None:
    # Cita textual: 2ª capa imagen (retrato) con forma elipse + un marco elipse (aro).
    capas = _docs()[("claro-sports", "Cita textual")]["capas"]
    imagenes = [c for c in capas if c.get("tipo") == "imagen"]
    assert len(imagenes) == 2, "Cita textual debe tener foto a sangre + retrato"
    retratos = [c for c in imagenes if c.get("forma") == "elipse" and not c.get("es_foto")]
    assert retratos, "el retrato debe ser una capa imagen NO es_foto con forma elipse"
    assert retratos[0].get("objeto", "") == "", "el retrato lo rellena el equipo (objeto vacío)"
    aros = [c for c in capas if c.get("tipo") == "marco" and c.get("forma") == "elipse"]
    assert aros, "Cita textual debe tener un aro (marco elipse) alrededor del retrato"
    assert aros[0].get("borde"), "el aro debe tener borde de acento"


def test_claro_sports_intacto() -> None:
    # El catálogo de Claro Sports NO cambia (4 plantillas), tokens de marcas.json.
    docs = _docs()
    nombres = {n for (m, n) in docs if m == "claro-sports"}
    assert nombres == {"Titular", "Breaking", "Cita textual", "Foto limpia"}


def test_nacion_gamer_destacado_chip_de_acento() -> None:
    # Destacado de Nación Gamer: chip neón FIJO "NUEVO" del color de acento placeholder.
    acento = ps._tokens("nacion-gamer")["acento"]
    capas = _docs()[("nacion-gamer", "Destacado")]["capas"]
    chips = [
        c for c in capas
        if c.get("tipo") == "texto" and c.get("chip") and c.get("texto") == "NUEVO"
    ]
    assert chips, "Destacado debe tener un chip fijo 'NUEVO'"
    assert chips[0]["chip"]["color"] == acento, "el chip debe usar el acento neón de la marca"
    assert chips[0]["binding"] is None, "el chip 'NUEVO' es texto fijo (sin binding)"


def test_nacion_gamer_titular_tiene_glow_neon() -> None:
    # El titular gamer lleva GLOW: sombra dy=0, desenfoque alto, color = acento.
    acento = ps._tokens("nacion-gamer")["acento"]
    for nombre in ("Titular", "Destacado"):
        capas = _docs()[("nacion-gamer", nombre)]["capas"]
        titulares = [c for c in capas if c.get("id") == "titular" and c.get("binding") == "copy_in"]
        assert titulares, f"nacion-gamer/{nombre} debe tener un titular copy_in"
        sombra = titulares[0].get("sombra") or {}
        assert sombra.get("color") == acento and sombra.get("desenfoque", 0) >= 20, (
            f"nacion-gamer/{nombre}: el titular debe tener glow neón (sombra color acento, desenfoque alto)"
        )


def test_fundacion_es_minima_sin_chips() -> None:
    # Fundación quedó MÍNIMA: sin chips ni pleca en NINGUNA de sus plantillas.
    docs = _docs()
    fundacion = [d for (m, _n), d in docs.items() if m == "fundacion"]
    assert len(fundacion) == 2, "Fundación debe tener exactamente 2 plantillas mínimas"
    for doc in fundacion:
        chips = [c for c in doc["capas"] if c.get("tipo") == "texto" and c.get("chip")]
        assert not chips, "Fundación no debe llevar chips (estética sobria/mínima)"
        plecas = [c for c in doc["capas"] if c.get("id") == "pleca"]
        assert not plecas, "Fundación no debe llevar pleca"


def test_fundacion_titular_sin_mayusculas() -> None:
    # El titular de Fundación es limpio: SIN mayúsculas (tono cálido, no editorial duro).
    capas = _docs()[("fundacion", "Titular")]["capas"]
    titular = next(c for c in capas if c.get("id") == "titular")
    assert titular["binding"] == "copy_in"
    assert titular.get("mayusculas") is False, "el titular de Fundación no debe ir en mayúsculas"


def test_marcas_sin_marcas_json_usan_tokens_inline() -> None:
    # nacion-gamer y piso-15 no están en marcas.json: caen a _TOKENS_EXTRA (placeholders).
    for marca in ("nacion-gamer", "piso-15"):
        tk = ps._tokens(marca)
        assert tk["acento"] == ps._TOKENS_EXTRA[marca]["acento"]
        assert tk["wordmark"] == ps._TOKENS_EXTRA[marca]["wordmark"]
