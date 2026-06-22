"""Columna `variante` de pieza (foto|carrusel): cimiento de la conversión no destructiva.

Una pieza nace `variante='foto'` (default de esquema, toda pieza legada y el flujo normal). La
conversión a carrusel (fases posteriores) crea una variante NUEVA junto a la foto sin pisarla; aquí
solo se valida el cimiento: default 'foto', lectura y edición de la variante. Postgres (`entorno`).
"""

from __future__ import annotations

from keni_consola import repos

_MARCA = "claro-sports"


def test_pieza_nace_variante_foto(entorno):
    tema = repos.crear_publicacion(clase="contenido", titulo="Tema", marca=_MARCA)
    p = repos.crear_pieza_fila(publicacion_id=tema["id"], red="instagram", copy="x")
    assert repos.obtener_pieza(p["id"])["variante"] == "foto"


def test_variante_se_puede_cambiar_a_carrusel(entorno):
    tema = repos.crear_publicacion(clase="contenido", titulo="Tema", marca=_MARCA)
    p = repos.crear_pieza_fila(publicacion_id=tema["id"], red="instagram", copy="x")
    repos.actualizar_pieza(p["id"], {"variante": "carrusel"})
    assert repos.obtener_pieza(p["id"])["variante"] == "carrusel"
    # No arrastra a las hermanas: la variante es por pieza (fila por red).
    otra = repos.crear_pieza_fila(publicacion_id=tema["id"], red="facebook", copy="y")
    assert repos.obtener_pieza(otra["id"])["variante"] == "foto"
