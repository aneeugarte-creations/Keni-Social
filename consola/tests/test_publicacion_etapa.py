"""La etapa IA serializada refleja el CONTENIDO real, no los flags `falta_*` almacenados.

PURO (sin DB ni red): `pieza_a_dict` solo transforma un dict usando catálogos y lógica
pura. El bug que cubre: los flags `falta_copy`/`falta_imagen` se desincronizan del contenido
(la pipeline rellena copy/imagen sin tocar el flag), y el label del feed mentía.
"""

from __future__ import annotations

from typing import Any

from keni_consola.dominio.piezas import flags_falta_de_contenido, pieza_a_dict


def _pub(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "p1",
        "titulo": "T",
        "marca": "unotv",
        "red": "x",
        "contenido": "",
        "estado": "pendiente",
        "revision": "",
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
    d = pieza_a_dict(
        _pub(contenido="Ya hay copy", copy_in="TITULAR", imagen="placa.png", falta_copy=True)
    )
    assert d["etapa_ia"] == "generando_arte"  # hay copy, lleva imagen, falta la foto real


def test_etapa_generando_copy_solo_si_no_hay_copy():
    d = pieza_a_dict(_pub(contenido="", copy_in="TITULAR"))
    assert d["etapa_ia"] == "generando_copy"


def test_pieza_sin_foto_no_esta_lista_aunque_no_lleve_copy_in():
    # TODO post necesita una FOTO real: sin foto (ni copy-in) NO está lista -> "Falta imagen".
    d = pieza_a_dict(_pub(contenido="Solo texto", copy_in="", imagen="", foto=""))
    assert d["etapa_ia"] == "generando_arte"


def test_imagen_de_fuente_no_cuenta_como_foto_real():
    # Una pieza de MARCA que trae la imagen del ARTÍCULO de origen (`imagen_fuente`) pero NO una
    # foto propia inyectada sigue en "Falta imagen": la URL de la nota es referencia, no la foto
    # de la pieza. El equipo debe poner la foto real.
    d = pieza_a_dict(
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
    d2 = pieza_a_dict(
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
    # Pieza nacida del pipeline CON `publicacion_id`: `pipeline_id` = ese id (la UI enlaza al run).
    d = pieza_a_dict(_pub(origen="pipeline", publicacion_id="c-123"))
    assert d["pipeline_id"] == "c-123"
    # Pieza manual (otro origen): sin run que encontrar -> `pipeline_id` vacío.
    d2 = pieza_a_dict(_pub(origen="equipo", publicacion_id="c-123"))
    assert d2["pipeline_id"] == ""
    # Origen pipeline pero sin `publicacion_id` (pieza legada): vacío.
    d3 = pieza_a_dict(_pub(origen="pipeline"))
    assert d3["pipeline_id"] == ""


def test_pieza_sin_marca_con_imagen_subida_esta_lista():
    # En piezas SIN marca/placa, la imagen subida (bespoke) SÍ cuenta como foto real -> lista
    # (con el copy ya con su hashtag; sin él, gatearía en `falta_hashtags`).
    d = pieza_a_dict(_pub(marca="", contenido="copy #x", copy_in="", imagen="subida.png", foto=""))
    assert d["etapa_ia"] == "lista_para_revisar"


def test_placa_sola_no_cuenta_como_imagen():
    # La PLACA (campo imagen) es solo plantilla: con copy-in pero sin foto real -> falta imagen.
    d = pieza_a_dict(_pub(contenido="copy", copy_in="TITULAR", imagen="placa.png", foto=""))
    assert d["etapa_ia"] == "generando_arte"


def test_con_foto_real_esta_lista():
    d = pieza_a_dict(_pub(contenido="copy #x", copy_in="TITULAR", imagen="placa.png", foto="bg.png"))
    assert d["etapa_ia"] == "lista_para_revisar"


def test_falta_copy_in_en_pieza_de_marca():
    # Pieza de MARCA en revisión con copy (CON hashtag) + foto pero SIN texto en la imagen (placa):
    # la acción pendiente es el copy-in (los hashtags ya están, así no tapan al copy-in).
    d = pieza_a_dict(_pub(estado="en_revision", contenido="copy #x", copy_in="", foto="bg.png"))
    assert d["etapa_ia"] == "falta_copy_in"


def test_copy_in_no_aplica_sin_marca():
    # Sin marca (imagen bespoke) no hay placa: no se exige copy-in -> lista (con el copy ya con
    # su hashtag).
    d = pieza_a_dict(_pub(marca="", contenido="copy #x", copy_in="", imagen="subida.png", foto=""))
    assert d["etapa_ia"] == "lista_para_revisar"


def test_en_revision_sin_hashtags_pide_hashtags():
    # YA en revisión, completa (copy + foto + placa) pero sin hashtags: la acción es ponerlos
    # (clave para campañas/líneas).
    d = pieza_a_dict(
        _pub(estado="en_revision", contenido="Texto sin etiquetas", copy_in="TITULAR", foto="bg.png")
    )
    assert d["etapa_ia"] == "falta_hashtags"


def test_en_revision_con_hashtags_es_lista():
    d = pieza_a_dict(
        _pub(estado="en_revision", contenido="Texto #Mundial2026 #UnoTV", copy_in="TITULAR", foto="bg.png")
    )
    assert d["etapa_ia"] == "lista_para_revisar"


def test_falta_el_hashtag_de_la_linea_aunque_haya_otros():
    # La pieza lleva hashtags, pero NO el de su LÍNEA (`linea_hashtags`): el de la sección es
    # obligatorio (métricas por línea), así que gatea en su etapa propia `falta_hashtag_editorial`
    # (no en `falta_hashtags`, que es «no hay NINGÚN hashtag»).
    d = pieza_a_dict(
        _pub(
            estado="en_revision", contenido="Texto #UnoTV #Mexico", copy_in="TITULAR",
            foto="bg.png", linea_hashtags="cienciatech",
        )
    )
    assert d["etapa_ia"] == "falta_hashtag_editorial"
    assert d["falta_hashtag_editorial"] is True
    assert d["falta_hashtags"] is False  # sí hay hashtags, solo falta el de la línea


def test_con_el_hashtag_de_la_linea_esta_lista():
    # Mismo caso pero el caption ya incluye el hashtag de la línea (case-insensitive): pasa el gate.
    d = pieza_a_dict(
        _pub(
            estado="en_revision", contenido="Texto #CienciaTech #UnoTV", copy_in="TITULAR",
            foto="bg.png", linea_hashtags="cienciatech",
        )
    )
    assert d["etapa_ia"] == "lista_para_revisar"


def test_sin_linea_basta_con_cualquier_hashtag():
    # Contenido sin línea (o línea sin hashtag fijado): el gate solo exige que haya ALGÚN hashtag.
    d = pieza_a_dict(
        _pub(estado="en_revision", contenido="Texto #Mexico", copy_in="TITULAR", foto="bg.png")
    )
    assert d["etapa_ia"] == "lista_para_revisar"


def test_expone_hashtags_linea_para_la_sugerencia_roja():
    # El hashtag de la línea (de `linea_hashtags`, CSV) se expone APARTE, con '#', para el feed.
    d = pieza_a_dict(_pub(contenido="Texto", linea_hashtags="cienciatech, salud"))
    assert d["hashtags_linea"] == ["#cienciatech", "#salud"]
    assert pieza_a_dict(_pub(contenido="Texto"))["hashtags_linea"] == []  # sin línea: vacío


def test_hashtags_gatean_en_borrador():
    # Los hashtags GATEAN igual que copy/foto: en borrador, una pieza completa (copy+foto+placa)
    # pero SIN hashtags NO está "lista" -> falta_hashtags. Nada sale sin hashtag.
    d = pieza_a_dict(
        _pub(estado="pendiente", contenido="Texto sin tags", copy_in="TITULAR", foto="bg.png")
    )
    assert d["etapa_ia"] == "falta_hashtags"


def test_red_sin_hashtags_de_la_marca_no_gatea():
    # Claro Sports declara 0 hashtags en X (`conteo_por_red.x == 0`): no etiqueta ahí. Una pieza
    # de esa marca+red sin hashtags está LISTA, no atascada en "Faltan hashtags".
    d = pieza_a_dict(
        _pub(
            marca="claro-sports", red="x", estado="en_revision",
            contenido="GOLAZO de último minuto 🦅", copy_in="TITULAR", foto="bg.png",
        )
    )
    assert d["etapa_ia"] == "lista_para_revisar"
    assert d["falta_hashtags"] is False


def test_red_sin_hashtags_ignora_tambien_el_de_la_linea():
    # En una red donde la marca no etiqueta, tampoco se exige el hashtag de la LÍNEA aunque la
    # línea lo declare: el gate editorial está apagado igual que el estructural.
    d = pieza_a_dict(
        _pub(
            marca="claro-sports", red="x", estado="en_revision",
            contenido="Crónica sin etiquetas", copy_in="TITULAR", foto="bg.png",
            linea_hashtags="ligamx",
        )
    )
    assert d["etapa_ia"] == "lista_para_revisar"
    assert d["falta_hashtag_editorial"] is False


def test_red_que_si_etiqueta_sigue_gateando():
    # La misma marca SÍ etiqueta en Facebook (`conteo_por_red.facebook == 1`): ahí el gate sigue
    # exigiendo hashtags. El apagado es por red, no por marca.
    d = pieza_a_dict(
        _pub(
            marca="claro-sports", red="facebook", estado="en_revision",
            contenido="GOLAZO de último minuto 🦅", copy_in="TITULAR", foto="bg.png",
        )
    )
    assert d["etapa_ia"] == "falta_hashtags"


def test_en_revision_no_oculta_lo_que_falta():
    # «Revisión» es interno: NO manda sobre el contenido. Una pieza en revisión sin la foto real
    # (solo copy + placa) enseña la acción pendiente —"Falta imagen"—, no un "para revisar" que
    # mienta.
    d = pieza_a_dict(_pub(contenido="copy", copy_in="TITULAR", estado="en_revision", foto=""))
    assert d["etapa_ia"] == "generando_arte"


def _carrusel(slides: list[dict[str, Any]], *, foto: str = "fotos/portada.jpg", **kw: Any) -> dict[str, Any]:
    import json as _json

    return _pub(
        variante="carrusel", formato="carrusel", foto=foto,
        carrusel=_json.dumps(slides), **kw,
    )


def test_carrusel_con_slide_de_solo_texto_faltan_fotos_no_portada():
    # Un slide de SOLO TEXTO (placa sin foto de fondo) deja el carrusel en «Faltan fotos», NO en
    # «Falta portada»: la portada SÍ está (su foto). `falta_imagen` (portada) es False.
    pub = _carrusel(
        [{"tipo": "imagen", "objeto": "artes/a.png", "titular": "Uno", "foto": ""}],
        contenido="copy",
    )
    assert flags_falta_de_contenido(pub)["falta_imagen"] is False
    assert pieza_a_dict(pub)["etapa_ia"] == "faltan_fotos"


def test_carrusel_sin_portada_es_generando_arte_no_faltan_fotos():
    # Sin foto de portada manda «generando_arte» (Falta portada), antes que el chequeo de slides.
    pub = _carrusel(
        [{"tipo": "imagen", "objeto": "artes/a.png", "foto": ""}],
        contenido="copy", foto="",
    )
    assert flags_falta_de_contenido(pub)["falta_imagen"] is True
    assert pieza_a_dict(pub)["etapa_ia"] == "generando_arte"


def test_carrusel_con_foto_en_todos_los_slides_esta_listo():
    # Portada con foto + cada slide con su foto real de fondo -> no falta nada de imagen.
    pub = _carrusel(
        [
            {"tipo": "imagen", "objeto": "artes/a.png", "titular": "Uno", "foto": "fotos/1.jpg"},
            {"tipo": "imagen", "objeto": "fotos/2.jpg", "sinPlaca": True},
        ],
        contenido="copy #x",
        copy_in="TITULAR",
        estado="en_revision",
    )
    assert pieza_a_dict(pub)["etapa_ia"] == "lista_para_revisar"


def test_carrusel_slide_de_video_cuenta_si_trae_asset():
    pub = _carrusel(
        [
            {"tipo": "imagen", "objeto": "artes/a.png", "foto": "fotos/1.jpg"},
            {"tipo": "video", "objeto": "videos/v.mp4"},
        ],
        contenido="copy",
    )
    assert pieza_a_dict(pub)["etapa_ia"] != "faltan_fotos"
    # Sin asset de vídeo el slide está incompleto -> faltan_fotos.
    pub_sin = _carrusel(
        [{"tipo": "imagen", "objeto": "artes/a.png", "foto": "fotos/1.jpg"},
         {"tipo": "video", "objeto": ""}],
        contenido="copy",
    )
    assert pieza_a_dict(pub_sin)["etapa_ia"] == "faltan_fotos"


def test_carrusel_de_media_cruda_esta_completo():
    # Slides de FOTO/VÍDEO crudos (presidencia/clips): el `objeto` ES la media real, no una placa
    # de texto -> completos sin campo `foto` de procedencia (no faltan_fotos).
    pub = _carrusel(
        [
            {"tipo": "imagen", "objeto": "fotos/p2.jpg"},
            {"tipo": "video", "objeto": "videos/clip.mp4"},
            {"tipo": "imagen", "objeto": "fotos/p3.jpg"},
        ],
        contenido="copy",
    )
    assert pieza_a_dict(pub)["etapa_ia"] != "faltan_fotos"


def test_carrusel_sin_slides_extra_lo_decide_la_portada():
    # Sin slides extra (campo vacío), la completitud la decide solo la portada (`foto`).
    con = _pub(variante="carrusel", formato="carrusel", foto="fotos/p.jpg", carrusel="", contenido="c")
    assert flags_falta_de_contenido(con)["falta_imagen"] is False
    assert pieza_a_dict(con)["etapa_ia"] != "faltan_fotos"
    sin = _pub(variante="carrusel", formato="carrusel", foto="", carrusel="", contenido="c")
    assert flags_falta_de_contenido(sin)["falta_imagen"] is True
