"""Tests PUROS del filtergraph del motor de render de video (Ola VIDEO).

SIN ffmpeg, SIN Postgres, SIN red: solo construccion de strings/argv a partir de un documento
de composicion ya validado. Es el nucleo testeable del motor (reencuadre/overlay/PiP/subs).
"""

from __future__ import annotations

from keni_consola.motores.estudio_video import filtros

# --------------------------------------------------------------------------- #
# Documentos de prueba (esquema del contrato G-video-engine.md)               #
# --------------------------------------------------------------------------- #

_FORMATO_916 = {"w": 1080, "h": 1920, "fps": 30, "preset": "9:16"}


def _doc_base(**extra):
    """Composicion minima: una pista de video base. `extra` mezcla en el clip base."""
    clip = {"id": "c1", "media_id": "videos/abc.mp4", "ajuste": "cover", "foco": [0.5, 0.5]}
    clip.update(extra)
    return {
        "version": 1,
        "marca": "claro-sports",
        "formato": dict(_FORMATO_916),
        "duracion_ms": 30000,
        "pistas": [{"id": "base", "tipo": "video", "clips": [clip]}],
    }


# --------------------------------------------------------------------------- #
# Reencuadre por formato                                                       #
# --------------------------------------------------------------------------- #


def test_reencuadre_cover_escala_increase_y_recorta_con_foco():
    f = filtros.filtro_reencuadre(1080, 1920, "cover", [0.5, 0.5], entrada="0:v", salida="vbase")
    assert "scale=1080:1920:force_original_aspect_ratio=increase" in f
    assert "crop=1080:1920:" in f
    assert f.startswith("[0:v]") and f.endswith("[vbase]")


def test_reencuadre_contain_usa_pad_sin_recorte():
    f = filtros.filtro_reencuadre(1080, 1920, "contain", None, entrada="0:v", salida="vbase")
    assert "force_original_aspect_ratio=decrease" in f
    assert "pad=1080:1920:" in f
    assert "crop=" not in f


def test_reencuadre_foco_desplaza_el_crop():
    # Foco arriba-izquierda -> factores 0.0 en el crop; abajo-derecha -> 1.0.
    sup_izq = filtros.filtro_reencuadre(1080, 1920, "cover", [0.0, 0.0], entrada="0:v", salida="v")
    inf_der = filtros.filtro_reencuadre(1080, 1920, "cover", [1.0, 1.0], entrada="0:v", salida="v")
    assert "*0.0000" in sup_izq
    assert "*1.0000" in inf_der


def test_filtergraph_solo_base_es_un_unico_reencuadre():
    fg, etiqueta = filtros.construir_filtergraph(_doc_base())
    assert etiqueta == "vbase"
    assert fg.count("scale=") == 1
    assert "overlay" not in fg
    assert "ass=" not in fg


# --------------------------------------------------------------------------- #
# Recorte temporal                                                             #
# --------------------------------------------------------------------------- #


def test_recorte_prefiere_recorte_in_out_ms():
    ini, fin = filtros.recorte_de({"recorte_in_ms": 2000, "recorte_out_ms": 5000})
    assert ini == 2.0 and fin == 5.0


def test_recorte_respaldo_inicio_fin_ms():
    ini, fin = filtros.recorte_de({"inicio_ms": 1000, "fin_ms": 4000})
    assert ini == 1.0 and fin == 4.0


def test_recorte_ausente_es_none():
    assert filtros.recorte_de({}) == (None, None)


def test_comando_inserta_ss_to_antes_del_input_base():
    doc = _doc_base(recorte_in_ms=2000, recorte_out_ms=5000)
    argv = filtros.construir_comando(
        "ffmpeg", doc, base_path="/tmp/base.mp4", salida_path="/tmp/out.mp4"
    )
    i_in = argv.index("-i")
    # -ss y -to aparecen ANTES del primer -i (recorte rapido de entrada).
    assert "-ss" in argv[:i_in] and "-to" in argv[:i_in]
    assert argv[argv.index("-ss") + 1] == "2.000"
    assert argv[argv.index("-to") + 1] == "5.000"


# --------------------------------------------------------------------------- #
# Overlay (PNG horneado del Estudio de imagen)                                 #
# --------------------------------------------------------------------------- #


def test_filtergraph_con_overlay_anade_overlay_sobre_base():
    doc = _doc_base()
    doc["pistas"].append({"id": "overlay", "tipo": "overlay", "capas": [{"tipo": "texto"}]})
    fg, etiqueta = filtros.construir_filtergraph(doc, overlay_png="/tmp/ovl.png")
    assert etiqueta == "vovl"
    # El overlay entra como segunda entrada de ffmpeg ([1:v]) y se compone en 0,0.
    assert "[1:v]scale=1080:1920[ovlsc]" in fg
    assert "[vbase][ovlsc]overlay=0:0[vovl]" in fg


def test_comando_con_overlay_anade_input_png():
    doc = _doc_base()
    argv = filtros.construir_comando(
        "ffmpeg", doc, base_path="/tmp/base.mp4", overlay_png="/tmp/ovl.png",
        salida_path="/tmp/out.mp4",
    )
    assert "/tmp/ovl.png" in argv
    # Dos -i: el clip base y el PNG de overlay.
    assert argv.count("-i") == 2


# --------------------------------------------------------------------------- #
# Doble pista / PiP                                                            #
# --------------------------------------------------------------------------- #


def _doc_con_pip():
    doc = _doc_base()
    doc["pistas"].append({
        "id": "pip", "tipo": "video",
        "clips": [{"id": "p1", "media_id": "videos/pip.mp4", "x": 40, "y": 60, "w": 480, "h": 270}],
    })
    return doc


def test_filtergraph_pip_escala_y_compone_en_posicion():
    doc = _doc_con_pip()
    fg, etiqueta = filtros.construir_filtergraph(doc, tiene_pip=True)
    assert etiqueta == "vpip"
    assert "[1:v]scale=480:270[pipsc]" in fg
    assert "[vbase][pipsc]overlay=40:60[vpip]" in fg


def test_comando_pip_alinea_orden_de_inputs_base_pip_overlay():
    doc = _doc_con_pip()
    doc["pistas"].append({"id": "overlay", "tipo": "overlay", "capas": [{"tipo": "texto"}]})
    argv = filtros.construir_comando(
        "ffmpeg", doc, base_path="/tmp/base.mp4", pip_path="/tmp/pip.mp4",
        overlay_png="/tmp/ovl.png", salida_path="/tmp/out.mp4",
    )
    # Tres entradas, en orden: base, pip, overlay. El overlay usa [2:v] cuando hay PiP.
    assert argv.count("-i") == 3
    fg = argv[argv.index("-filter_complex") + 1]
    assert "[2:v]scale=1080:1920[ovlsc]" in fg


# --------------------------------------------------------------------------- #
# Subtitulos quemados                                                          #
# --------------------------------------------------------------------------- #


def test_filtergraph_con_ass_quema_subtitulos_al_final():
    doc = _doc_base()
    doc["pistas"].append({"id": "subs", "tipo": "subtitulos", "subtitulo_id": "s1"})
    fg, etiqueta = filtros.construir_filtergraph(doc, ass_path="/tmp/subs.ass")
    assert etiqueta == "vsub"
    assert "ass=" in fg
    assert fg.endswith("[vsub]")


def test_filtro_subtitulos_escapa_la_ruta():
    f = filtros.filtro_subtitulos("/tmp/sub:1.ass", entrada="vbase", salida="vsub")
    # Los dos-puntos de la ruta van escapados dentro de comillas simples.
    assert "ass='/tmp/sub\\:1.ass'" in f


def test_sin_ass_no_hay_filtro_de_subtitulos():
    doc = _doc_base()
    doc["pistas"].append({"id": "subs", "tipo": "subtitulos", "subtitulo_id": "s1"})
    fg, etiqueta = filtros.construir_filtergraph(doc, ass_path=None)
    assert etiqueta == "vbase"
    assert "ass=" not in fg


# --------------------------------------------------------------------------- #
# Comando completo (codec, fps, progreso)                                      #
# --------------------------------------------------------------------------- #


def test_comando_codifica_h264_yuv420p_con_progreso():
    argv = filtros.construir_comando(
        "/usr/bin/ffmpeg", _doc_base(), base_path="/tmp/base.mp4", salida_path="/tmp/out.mp4"
    )
    assert argv[0] == "/usr/bin/ffmpeg"
    assert "libx264" in argv
    assert "yuv420p" in argv
    assert argv[argv.index("-r") + 1] == "30"  # fps del formato
    assert "-progress" in argv and "pipe:1" in argv
    assert argv[-1] == "/tmp/out.mp4"


def test_comando_mapea_audio_opcional_del_base():
    argv = filtros.construir_comando(
        "ffmpeg", _doc_base(), base_path="/tmp/base.mp4", salida_path="/tmp/out.mp4"
    )
    # El audio del clip base se mapea con `?` (no falla si no hay pista de audio).
    assert "0:a?" in argv
