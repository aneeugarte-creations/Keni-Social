"""La etapa IA serializada refleja el CONTENIDO real, no los flags `falta_*` almacenados.

PURO (sin DB ni red): `publicacion_a_dict` solo transforma un dict usando catálogos y lógica
pura. El bug que cubre: los flags `falta_copy`/`falta_imagen` se desincronizan del contenido
(la tubería rellena copy/imagen sin tocar el flag), y el label del feed mentía.
"""

from __future__ import annotations

from typing import Any

from keni_consola.dominio.publicaciones import publicacion_a_dict


def _pub(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "p1",
        "titulo": "T",
        "marca": "unotv",
        "red": "x",
        "contenido": "",
        "estado": "pendiente",
        "veredicto": "",
        "origen": "pipeline",
        "fecha_creacion": "",
        "fecha_actualizacion": "",
        "fecha_programada": "",
    }
    base.update(kw)
    return base


def test_etapa_ignora_flag_copy_desincronizado():
    # Flag dice "falta copy" (stale) PERO el copy ya está: la etapa NO debe ser "generando_copy".
    # Pieza CON copy-in (lleva imagen) pero sin foto -> generando_arte (falta la foto real).
    d = publicacion_a_dict(
        _pub(contenido="Ya hay copy", copy_in="TITULAR", imagen="placa.png", falta_copy=True)
    )
    assert d["etapa_ia"] == "generando_arte"  # hay copy, lleva imagen, falta la foto real


def test_etapa_generando_copy_solo_si_no_hay_copy():
    d = publicacion_a_dict(_pub(contenido="", copy_in="TITULAR"))
    assert d["etapa_ia"] == "generando_copy"


def test_pieza_sin_foto_no_esta_lista_aunque_no_lleve_copy_in():
    # TODO post necesita una FOTO real: sin foto (ni copy-in) NO está lista -> "Falta imagen".
    d = publicacion_a_dict(_pub(contenido="Solo texto", copy_in="", imagen="", foto=""))
    assert d["etapa_ia"] == "generando_arte"


def test_imagen_de_fuente_no_cuenta_como_foto_real():
    # Una pieza de MARCA que trae la imagen del ARTÍCULO de origen (`imagen_fuente`) pero NO una
    # foto propia inyectada sigue en "Falta imagen": la URL de la nota es referencia, no la foto
    # de la pieza. El equipo debe poner la foto real.
    d = publicacion_a_dict(
        _pub(
            estado="en_revision",
            contenido="copy #gol",
            copy_in="TITULAR",
            imagen="placa.png",
            imagen_fuente="https://nota.test/orig.jpg",
            foto="",
        )
    )
    assert d["etapa_ia"] == "generando_arte"
    # Con la foto propia ya inyectada (y el copy con su hashtag), la misma pieza SÍ queda
    # lista para revisar: lo que la bloqueaba era la foto, no el resto.
    d2 = publicacion_a_dict(
        _pub(
            estado="en_revision",
            contenido="copy #gol",
            copy_in="TITULAR",
            imagen="placa.png",
            imagen_fuente="https://nota.test/orig.jpg",
            foto="bg.png",
        )
    )
    assert d2["etapa_ia"] == "lista_para_revisar"


def test_pipeline_id_enlaza_solo_piezas_del_pipeline():
    # Pieza nacida del pipeline CON `contenido_id`: `pipeline_id` = ese id (la UI enlaza al run).
    d = publicacion_a_dict(_pub(origen="pipeline", contenido_id="c-123"))
    assert d["pipeline_id"] == "c-123"
    # Pieza manual (otro origen): sin run que encontrar -> `pipeline_id` vacío.
    d2 = publicacion_a_dict(_pub(origen="equipo", contenido_id="c-123"))
    assert d2["pipeline_id"] == ""
    # Origen pipeline pero sin `contenido_id` (pieza legada): vacío.
    d3 = publicacion_a_dict(_pub(origen="pipeline"))
    assert d3["pipeline_id"] == ""


def test_pieza_sin_marca_con_imagen_subida_esta_lista():
    # En piezas SIN marca/placa, la imagen subida (bespoke) SÍ cuenta como foto real -> lista.
    d = publicacion_a_dict(_pub(marca="", contenido="copy", copy_in="", imagen="subida.png", foto=""))
    assert d["etapa_ia"] == "lista_para_revisar"


def test_placa_sola_no_cuenta_como_imagen():
    # La PLACA (campo imagen) es solo plantilla: con copy-in pero sin foto real -> falta imagen.
    d = publicacion_a_dict(_pub(contenido="copy", copy_in="TITULAR", imagen="placa.png", foto=""))
    assert d["etapa_ia"] == "generando_arte"


def test_con_foto_real_esta_lista():
    d = publicacion_a_dict(_pub(contenido="copy", copy_in="TITULAR", imagen="placa.png", foto="bg.png"))
    assert d["etapa_ia"] == "lista_para_revisar"


def test_falta_copy_in_en_pieza_de_marca():
    # Pieza de MARCA en revisión con copy + foto pero SIN texto en la imagen (placa): la acción
    # pendiente es el copy-in. (En borrador no bloquea; es acción de la fase de revisión.)
    d = publicacion_a_dict(_pub(estado="en_revision", contenido="copy", copy_in="", foto="bg.png"))
    assert d["etapa_ia"] == "falta_copy_in"


def test_copy_in_no_aplica_sin_marca():
    # Sin marca (imagen bespoke) no hay placa: no se exige copy-in -> lista (en pendiente, sin
    # hashtags, no bloquea).
    d = publicacion_a_dict(_pub(marca="", contenido="copy", copy_in="", imagen="subida.png", foto=""))
    assert d["etapa_ia"] == "lista_para_revisar"


def test_en_revision_sin_hashtags_pide_hashtags():
    # YA en revisión, completa (copy + foto + placa) pero sin hashtags: la acción es ponerlos
    # (clave para campañas/líneas).
    d = publicacion_a_dict(
        _pub(estado="en_revision", contenido="Texto sin etiquetas", copy_in="TITULAR", foto="bg.png")
    )
    assert d["etapa_ia"] == "falta_hashtags"


def test_en_revision_con_hashtags_es_lista():
    d = publicacion_a_dict(
        _pub(estado="en_revision", contenido="Texto #Mundial2026 #UnoTV", copy_in="TITULAR", foto="bg.png")
    )
    assert d["etapa_ia"] == "lista_para_revisar"


def test_hashtags_no_bloquean_en_borrador():
    # En borrador (pendiente), faltar hashtags NO la saca de "lista": el avance la mueve y los
    # hashtags se piden ya en revisión.
    d = publicacion_a_dict(
        _pub(estado="pendiente", contenido="Texto sin tags", copy_in="TITULAR", foto="bg.png")
    )
    assert d["etapa_ia"] == "lista_para_revisar"


def test_en_revision_no_oculta_lo_que_falta():
    # «Revisión» es interno: NO manda sobre el contenido. Una pieza en revisión sin la foto real
    # (solo copy + placa) enseña la acción pendiente —"Falta imagen"—, no un "para revisar" que
    # mienta.
    d = publicacion_a_dict(_pub(contenido="copy", copy_in="TITULAR", estado="en_revision", foto=""))
    assert d["etapa_ia"] == "generando_arte"
