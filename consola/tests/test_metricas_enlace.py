"""Índice de enlace pieza↔contenido por `id_post_metricool` (`_indice_contenido_por_post`).

Lógica PURA (sin BD): se le pasan contenidos y filas de plataforma en memoria y se verifica
que los SELLOS de degradación (`incierto-timeout`, `reconc-timeout-…`) NO entran al índice
por id —compartirían una clave ficticia entre varias piezas y atribuirían métricas a la
pieza equivocada—, mientras que los ids reales sí enlazan y el título sigue de fallback.
"""

from __future__ import annotations

from keni_consola import metricas_pieza
from keni_consola.programador import ID_POST_INCIERTO


def test_id_real_enlaza_y_sello_no():
    """Un id real entra al índice; el sello de timeout queda fuera (y la pieza enlaza por título)."""
    contenidos = [
        {"id": "c1", "id_post_metricool": "337716803", "titulo": "Noticia con id real"},
        {"id": "c2", "id_post_metricool": ID_POST_INCIERTO, "titulo": "Noticia que expiró"},
    ]
    por_id, por_titulo = metricas_pieza._indice_contenido_por_post(contenidos, [])
    assert por_id == {"337716803": "c1"}  # el sello "incierto-timeout" NO está
    # La pieza incierta sigue siendo recuperable por el fallback de título (red de seguridad).
    assert por_titulo[metricas_pieza._normalizar_titulo("Noticia que expiró")] == "c2"


def test_sellos_no_colisionan_entre_piezas():
    """Varias piezas con el MISMO sello compartido no se pisan bajo una clave ficticia."""
    contenidos = [
        {"id": "c1", "id_post_metricool": ID_POST_INCIERTO, "titulo": "A"},
        {"id": "c2", "id_post_metricool": ID_POST_INCIERTO, "titulo": "B"},
        # Sello externo escrito por ops a mano sobre una pieza incierta.
        {"id": "c3", "id_post_metricool": "reconc-timeout-20260611-2045", "titulo": "C"},
    ]
    por_id, _ = metricas_pieza._indice_contenido_por_post(contenidos, [])
    assert por_id == {}  # ningún sello (ni interno ni externo) entra al índice por id


def test_plataforma_id_real_si_enlaza_sello_no():
    """El enlace por red (`pieza.id_post_metricool`) aplica el mismo filtro."""
    plataformas = [
        {"publicacion_id": "c1", "id_post_metricool": "148786388488561_1011295324604797"},
        {"publicacion_id": "c2", "id_post_metricool": ID_POST_INCIERTO},
    ]
    por_id, _ = metricas_pieza._indice_contenido_por_post([], plataformas)
    assert por_id == {"148786388488561_1011295324604797": "c1"}
