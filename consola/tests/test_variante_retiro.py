"""Retiro de la variante hermana al programar (anti doble publicación).

Cuando una pieza se programa, su variante hermana de la MISMA red (foto vs carrusel) se retira si
sigue en borrador/en_revisión: solo sale la elegida. Las guardas son estrictas — nunca toca la
misma variante, otra red, ni algo ya programado/publicado. Postgres (`entorno`).
"""

from __future__ import annotations

from keni_consola import repos
from keni_consola.api.aprobacion import _retirar_variantes_hermanas

_MARCA = "claro-sports"


def _tema():
    return repos.crear_publicacion(clase="contenido", titulo="Tema", marca=_MARCA)


def test_retira_la_variante_hermana_de_la_misma_red(entorno):
    tema = _tema()
    foto = repos.crear_pieza_fila(publicacion_id=tema["id"], red="instagram", copy="x")
    carr = repos.crear_pieza_fila(
        publicacion_id=tema["id"], red="instagram", copy="x", variante="carrusel",
    )
    _retirar_variantes_hermanas(repos.obtener_pieza(foto["id"]))
    assert repos.obtener_pieza(foto["id"]) is not None  # la elegida se conserva
    assert repos.obtener_pieza(carr["id"]) is None  # la hermana carrusel se retira


def test_no_toca_misma_variante_ni_otra_red(entorno):
    tema = _tema()
    foto_ig = repos.crear_pieza_fila(publicacion_id=tema["id"], red="instagram", copy="x")
    foto_fb = repos.crear_pieza_fila(publicacion_id=tema["id"], red="facebook", copy="x")
    carr_fb = repos.crear_pieza_fila(
        publicacion_id=tema["id"], red="facebook", copy="x", variante="carrusel",
    )
    _retirar_variantes_hermanas(repos.obtener_pieza(foto_ig["id"]))
    # Programar la foto de IG no toca: la foto de FB (misma variante, otra red) ni la carrusel de FB
    # (otra red). Solo retiraría la variante hermana de la MISMA red (IG), que aquí no existe.
    assert repos.obtener_pieza(foto_fb["id"]) is not None
    assert repos.obtener_pieza(carr_fb["id"]) is not None


def test_no_retira_hermana_ya_publicada(entorno):
    tema = _tema()
    foto = repos.crear_pieza_fila(publicacion_id=tema["id"], red="instagram", copy="x")
    carr = repos.crear_pieza_fila(
        publicacion_id=tema["id"], red="instagram", copy="x", variante="carrusel",
    )
    repos.transicionar_estado_pieza(carr["id"], "borrador", "publicado")
    _retirar_variantes_hermanas(repos.obtener_pieza(foto["id"]))
    # Lo que ya salió no se retira.
    assert repos.obtener_pieza(carr["id"]) is not None
