"""Columna `variante` de pieza (foto|carrusel): cimiento de la conversión no destructiva.

Una pieza nace `variante='foto'` (default de esquema, toda pieza legada y el flujo normal). La
conversión a carrusel (fases posteriores) crea una variante NUEVA junto a la foto sin pisarla; aquí
solo se valida el cimiento: default 'foto', lectura y edición de la variante. Postgres (`entorno`).
"""

from __future__ import annotations

from keni_consola import repos
from keni_consola.api.piezas.espejo import _propagar_espejo

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


def test_crear_pieza_variante_carrusel_directo(entorno):
    # El INSERT acepta variante: el rewind crea piezas variante-carrusel junto a las foto.
    tema = repos.crear_publicacion(clase="contenido", titulo="Tema", marca=_MARCA)
    foto = repos.crear_pieza_fila(publicacion_id=tema["id"], red="instagram", copy="x")
    carr = repos.crear_pieza_fila(
        publicacion_id=tema["id"], red="instagram", copy="x", variante="carrusel",
    )
    assert repos.obtener_pieza(foto["id"])["variante"] == "foto"
    assert repos.obtener_pieza(carr["id"])["variante"] == "carrusel"


def test_formato_efectivo_derivado_de_la_variante(entorno):
    # El formato del padre es 'foto', pero la variante carrusel se LEE como formato carrusel
    # (va a sus redes IG/FB) sin tocar el padre ni la hermana foto.
    tema = repos.crear_publicacion(clase="contenido", titulo="Tema", marca=_MARCA)
    foto = repos.crear_pieza_fila(publicacion_id=tema["id"], red="instagram", copy="x")
    carr = repos.crear_pieza_fila(
        publicacion_id=tema["id"], red="instagram", copy="x", variante="carrusel",
    )
    assert repos.obtener_pieza(foto["id"])["formato"] == "foto"
    assert repos.obtener_pieza(carr["id"])["formato"] == "carrusel"


def test_espejo_no_cruza_variantes(entorno):
    # Editar el copy de una pieza foto se espeja a su hermana foto (otra red) pero NO a la
    # variante carrusel: son generaciones independientes del mismo contenido.
    tema = repos.crear_publicacion(clase="contenido", titulo="Tema", marca=_MARCA)
    foto_ig = repos.crear_pieza_fila(publicacion_id=tema["id"], red="instagram", copy="orig")
    foto_fb = repos.crear_pieza_fila(publicacion_id=tema["id"], red="facebook", copy="orig")
    carr_ig = repos.crear_pieza_fila(
        publicacion_id=tema["id"], red="instagram", copy="carrusel copy", variante="carrusel",
    )
    _propagar_espejo(repos.obtener_pieza(foto_ig["id"]), {"contenido": "EDITADO"})
    assert repos.obtener_pieza(foto_fb["id"])["contenido"] == "EDITADO"  # hermana foto: sí
    assert repos.obtener_pieza(carr_ig["id"])["contenido"] == "carrusel copy"  # variante: no
