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
    fg, etiqueta, _ = filtros.construir_filtergraph(_doc_base())
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
    fg, etiqueta, _ = filtros.construir_filtergraph(doc, overlay_png="/tmp/ovl.png")
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
    fg, etiqueta, _ = filtros.construir_filtergraph(doc, tiene_pip=True)
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
    fg, etiqueta, _ = filtros.construir_filtergraph(doc, ass_path="/tmp/subs.ass")
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
    fg, etiqueta, _ = filtros.construir_filtergraph(doc, ass_path=None)
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
    # Sin ajustes de audio (sin split/volumen/silenciar/musica) se mapea el audio del base con `?`.
    assert "0:a?" in argv


# --------------------------------------------------------------------------- #
# Split / concat de segmentos del clip base                                    #
# --------------------------------------------------------------------------- #


def _doc_split():
    """Composicion con DOS segmentos del clip base (corte/split)."""
    base = {"id": "c1", "media_id": "videos/abc.mp4", "ajuste": "cover", "foco": [0.5, 0.5]}
    seg1 = {**base, "recorte_in_ms": 0, "recorte_out_ms": 10000}
    seg2 = {**base, "id": "c2", "recorte_in_ms": 20000, "recorte_out_ms": 30000}
    doc = _doc_base()
    doc["pistas"][0]["clips"] = [seg1, seg2]
    return doc


def test_filtergraph_split_concatena_segmentos_antes_del_reencuadre():
    fg, etiqueta, _ = filtros.construir_filtergraph(_doc_split())
    assert etiqueta == "vbase"
    assert "[0:v]trim=start=0.000:end=10.000,setpts=PTS-STARTPTS[vseg0]" in fg
    assert "[0:v]trim=start=20.000:end=30.000,setpts=PTS-STARTPTS[vseg1]" in fg
    assert "[vseg0][vseg1]concat=n=2:v=1:a=0[vcat]" in fg
    # El reencuadre toma la concatenacion, no [0:v] directo.
    assert "[vcat]scale=" in fg


def test_comando_split_no_pone_ss_to_a_nivel_input():
    argv = filtros.construir_comando(
        "ffmpeg", _doc_split(), base_path="/tmp/base.mp4", salida_path="/tmp/out.mp4"
    )
    i_in = argv.index("-i")
    # El recorte vive en el filtergraph (trim), no como -ss/-to del input base.
    assert "-ss" not in argv[:i_in]
    # El audio del split se reconstruye con atrim+concat y se mapea por etiqueta (no 0:a?).
    fg = argv[argv.index("-filter_complex") + 1]
    assert "concat=n=2:v=0:a=1[acat]" in fg
    assert "0:a?" not in argv


# --------------------------------------------------------------------------- #
# Audio: volumen / silenciar / musica                                          #
# --------------------------------------------------------------------------- #


def test_filtergraph_volumen_base_aplica_filtro_volume():
    fg, _v, etiqueta_audio = filtros.construir_filtergraph(_doc_base(volumen=0.5))
    assert "[0:a]volume=0.500[abase]" in fg
    assert etiqueta_audio == "abase"


def test_comando_audio_silenciado_no_mapea_audio():
    argv = filtros.construir_comando(
        "ffmpeg", _doc_base(silenciar=True), base_path="/tmp/base.mp4", salida_path="/tmp/out.mp4"
    )
    # Silenciado y sin musica: no se mapea ninguna pista de audio (ni 0:a? ni etiqueta).
    assert "0:a?" not in argv
    maps = [argv[i + 1] for i, x in enumerate(argv) if x == "-map"]
    assert maps == ["[vbase]"]


def _doc_con_musica(**base_extra):
    doc = _doc_base(**base_extra)
    doc["pistas"].append(
        {
            "id": "audio",
            "tipo": "audio",
            "clips": [
                {"id": "a1", "media_id": "videos/m.mp3", "volumen": 0.6,
                 "recorte_in_ms": 0, "recorte_out_ms": 8000}
            ],
        }
    )
    return doc


def test_filtergraph_musica_se_mezcla_con_amix():
    fg, _v, etiqueta_audio = filtros.construir_filtergraph(_doc_con_musica(), tiene_musica=True)
    assert etiqueta_audio == "aout"
    # Audio base (anull) + musica (volume) mezclados con amix.
    assert "[0:a]anull[abase]" in fg
    assert "volume=0.600[amus]" in fg
    assert "amix=inputs=2" in fg
    assert fg.endswith("[aout]") or "[aout]" in fg


def test_comando_musica_anade_input_al_final_y_mapea_aout():
    argv = filtros.construir_comando(
        "ffmpeg", _doc_con_musica(), base_path="/tmp/base.mp4",
        musica_path="/tmp/m.mp3", salida_path="/tmp/out.mp4",
    )
    assert "/tmp/m.mp3" in argv
    # Dos inputs: el base [0] y la musica [1] al final.
    assert argv.count("-i") == 2
    maps = [argv[i + 1] for i, x in enumerate(argv) if x == "-map"]
    assert "[aout]" in maps


# --------------------------------------------------------------------------- #
# Audio: fundidos (afade) de la musica                                         #
# --------------------------------------------------------------------------- #


def _doc_con_musica_fades(**fade_extra):
    """Composicion con musica que lleva `fade_in_ms` y/o `fade_out_ms`."""
    doc = _doc_base()
    clip = {"id": "a1", "media_id": "videos/m.mp3", "volumen": 0.6,
            "recorte_in_ms": 0, "recorte_out_ms": 10000}
    clip.update(fade_extra)
    doc["pistas"].append({"id": "audio", "tipo": "audio", "clips": [clip]})
    return doc


def test_filtergraph_musica_con_fade_in_incluye_afade_in():
    fg, _v, _a = filtros.construir_filtergraph(
        _doc_con_musica_fades(fade_in_ms=1000), tiene_musica=True
    )
    assert "afade=t=in:st=0:d=1.000" in fg


def test_filtergraph_musica_con_fade_out_incluye_afade_out():
    # Duracion = 10000-0 = 10 s; fade_out_ms=2000 => st=8.0
    fg, _v, _a = filtros.construir_filtergraph(
        _doc_con_musica_fades(fade_out_ms=2000), tiene_musica=True
    )
    assert "afade=t=out:st=8.000:d=2.000" in fg


def test_filtergraph_musica_con_ambos_fades_incluye_afade_in_y_out():
    fg, _v, _a = filtros.construir_filtergraph(
        _doc_con_musica_fades(fade_in_ms=500, fade_out_ms=1500), tiene_musica=True
    )
    assert "afade=t=in:st=0:d=0.500" in fg
    # Duracion = 10 s; st = 10.0 - 1.5 = 8.5
    assert "afade=t=out:st=8.500:d=1.500" in fg


def test_filtergraph_musica_sin_fades_no_incluye_afade():
    fg, _v, _a = filtros.construir_filtergraph(_doc_con_musica(), tiene_musica=True)
    assert "afade" not in fg
