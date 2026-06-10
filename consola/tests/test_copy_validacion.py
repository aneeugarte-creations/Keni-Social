"""Validación PRE-PERSISTENCIA de piezas de copy (`dominio.copy`).

Una pieza con red desconocida, texto vacío o que excede el límite técnico de su red
(`keni_shared.limites_plataforma`; en hilos/carruseles, por tramo) NO crea borrador: se
descarta SOLO esa pieza, se loguea WARN y, si hay tema, se deja una nota en él. Las piezas
válidas del mismo lote se crean igual.

Los helpers de tramos/motivo son PUROS (sin DB); la creación de borradores usa Postgres
(fixture `entorno`).
"""

from __future__ import annotations

from keni_consola import repos
from keni_consola.dominio import copy as dom_copy

_MARCA = "unotv"


# --------------------------------------------------------------------------- #
# Tramos publicables (contrato de piezas compuestas) — PURO                     #
# --------------------------------------------------------------------------- #


def test_pieza_simple_es_un_unico_tramo():
    assert dom_copy._tramos_publicables("Hola X") == ["Hola X"]


def test_hilo_se_parte_por_tuits_numerados():
    texto = "1/3 Gancho del hilo\n2/3 Desarrollo\ncon segunda línea\n3/3 Cierre con CTA"
    tramos = dom_copy._tramos_publicables(texto)
    assert tramos == ["1/3 Gancho del hilo", "2/3 Desarrollo\ncon segunda línea", "3/3 Cierre con CTA"]


def test_carrusel_se_parte_por_separador():
    texto = "Slide 1: gancho\n---\nSlide 2: dato\n---\nSlide 3: CTA"
    assert dom_copy._tramos_publicables(texto) == ["Slide 1: gancho", "Slide 2: dato", "Slide 3: CTA"]


def test_una_sola_linea_numerada_no_es_hilo():
    # "1/2 de la población…" como apertura de una pieza simple NO debe partirse.
    texto = "1/2 de la población vio el partido"
    assert dom_copy._tramos_publicables(texto) == [texto]


# --------------------------------------------------------------------------- #
# Motivo de invalidez — PURO                                                   #
# --------------------------------------------------------------------------- #


def test_motivo_red_desconocida():
    assert "red desconocida" in dom_copy._motivo_invalida({"red": "threads", "contenido": "hola"})
    assert "red desconocida" in dom_copy._motivo_invalida({"red": 3, "contenido": "hola"})


def test_motivo_texto_vacio():
    assert "texto vacío" in dom_copy._motivo_invalida({"red": "x", "contenido": "  "})
    assert "texto vacío" in dom_copy._motivo_invalida({"red": "x", "contenido": None})


def test_motivo_excede_limite_de_la_red():
    motivo = dom_copy._motivo_invalida({"red": "x", "contenido": "a" * 281})
    assert "límite 280" in motivo


def test_hilo_valida_por_tuit_no_por_total():
    # Un hilo de 3 tuits ≤280 supera los 280 totales y AUN ASI es válido (límite por tramo).
    hilo = "\n".join(f"{i}/3 " + "a" * 200 for i in (1, 2, 3))
    assert len(hilo) > 280
    assert dom_copy._motivo_invalida({"red": "x", "contenido": hilo}) is None
    # Pero un tuit individual pasado de 280 invalida la pieza.
    roto = "1/2 " + "a" * 300 + "\n2/2 corto"
    assert "límite 280" in dom_copy._motivo_invalida({"red": "x", "contenido": roto})


def test_sin_tope_tecnico_no_invalida_por_longitud():
    assert dom_copy._motivo_invalida({"red": "facebook", "contenido": "a" * 100_000}) is None


def test_pieza_valida_no_tiene_motivo():
    assert dom_copy._motivo_invalida({"red": "x", "contenido": "Hola X"}) is None


# --------------------------------------------------------------------------- #
# Creación de borradores: descarta inválidas sin romper las válidas (Postgres)  #
# --------------------------------------------------------------------------- #


def test_pieza_invalida_no_crea_borrador_y_respeta_las_validas(entorno):
    creadas = dom_copy.crear_publicaciones_desde_piezas(
        [
            {"red": "x", "contenido": "a" * 500, "copy_in": ""},  # excede el límite de X
            {"red": "instagram", "contenido": "", "copy_in": ""},  # texto vacío
            {"red": "facebook", "contenido": "Hola FB", "copy_in": ""},  # válida
        ],
        marca=_MARCA, titulo="T", verdicto="", origen="h1",
    )
    assert [str(p["red"]) for p in creadas] == ["facebook"]
    pubs = repos.listar_publicaciones(marca=_MARCA)
    assert all(p.get("red") != "x" for p in pubs)


def test_pieza_invalida_deja_nota_en_el_tema(entorno):
    tema = repos.crear_contenido(clase="contenido", titulo="Tema", marca=_MARCA, notas="previa")
    dom_copy.crear_publicaciones_desde_piezas(
        [{"red": "x", "contenido": "a" * 500, "copy_in": ""}],
        marca=_MARCA, titulo="T", verdicto="", origen="h1", contenido_id=tema["id"],
    )
    releido = repos.obtener_contenido(tema["id"])
    assert "previa" in releido["notas"]  # no pisa las notas existentes
    assert "Copy descartado" in releido["notas"]
    assert "límite 280" in releido["notas"]


def test_redes_filtro_no_cuenta_como_descarte(entorno):
    # Excluir una red por filtro del llamante NO es una pieza inválida: ni nota ni WARN.
    tema = repos.crear_contenido(clase="contenido", titulo="Tema", marca=_MARCA)
    dom_copy.crear_publicaciones_desde_piezas(
        [{"red": "x", "contenido": "Hola X", "copy_in": ""}],
        marca=_MARCA, titulo="T", verdicto="", origen="h1",
        redes_filtro={"instagram"}, contenido_id=tema["id"],
    )
    assert "Copy descartado" not in (repos.obtener_contenido(tema["id"])["notas"] or "")
