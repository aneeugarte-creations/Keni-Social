"""Tests PUROS (sin DB ni red) de `keni_shared.video`: presets + validador de composicion."""

from __future__ import annotations

import pytest
from keni_shared import video


def test_presets_formato_resoluciones():
    assert video.PRESETS_FORMATO["9:16"]["w"] == 1080
    assert video.PRESETS_FORMATO["9:16"]["h"] == 1920
    assert video.PRESETS_FORMATO["1:1"]["w"] == video.PRESETS_FORMATO["1:1"]["h"] == 1080
    assert video.PRESETS_FORMATO["16:9"]["w"] == 1920
    # Zonas seguras razonables (no negativas y < alto).
    for asp, p in video.PRESETS_FORMATO.items():
        assert 0 <= p["safe_top"] < p["h"], asp
        assert 0 <= p["safe_bottom"] < p["h"], asp


def test_preset_para_aspecto_desconocido_cae_al_defecto():
    assert video.preset_para_aspecto("raro") == video.preset_para_aspecto(video.ASPECTO_DEFECTO)


def test_preset_para_aspecto_devuelve_copia():
    p = video.preset_para_aspecto("9:16")
    p["w"] = 1
    assert video.PRESETS_FORMATO["9:16"]["w"] == 1080  # no mutó el global


def test_preset_para_red_mapea_video_specs():
    # X es horizontal (16:9 en VIDEO_SPECS); el resto vertical (9:16).
    assert video.preset_para_red("x")["aspecto"] == "16:9"
    assert video.preset_para_red("tiktok")["aspecto"] == "9:16"
    # Red desconocida -> aspecto por defecto.
    assert video.preset_para_red("nope")["aspecto"] == video.ASPECTO_DEFECTO


def _composicion_valida() -> dict:
    return {
        "version": 1,
        "marca": "claro-sports",
        "formato": {"w": 1080, "h": 1920, "fps": 30, "preset": "9:16"},
        "duracion_ms": 30000,
        "pistas": [
            {"id": "base", "tipo": "video", "clips": []},
            {"id": "overlay", "tipo": "overlay", "capas": []},
            {"id": "subs", "tipo": "subtitulos", "subtitulo_id": "s1"},
        ],
    }


def test_validar_composicion_valida_normaliza():
    norm = video.validar_composicion(_composicion_valida())
    assert norm["formato"]["w"] == 1080
    assert norm["formato"]["preset"] == "9:16"
    assert norm["formato"]["fps"] == 30
    assert [p["id"] for p in norm["pistas"]] == ["base", "overlay", "subs"]


def test_validar_composicion_rellena_preset_y_fps_por_dimension():
    doc = _composicion_valida()
    del doc["formato"]["preset"]
    del doc["formato"]["fps"]
    norm = video.validar_composicion(doc)
    assert norm["formato"]["preset"] == "9:16"  # derivado de 1080x1920
    assert norm["formato"]["fps"] == 30


def test_validar_composicion_no_muta_entrada():
    doc = _composicion_valida()
    antes = dict(doc["formato"])
    video.validar_composicion(doc)
    assert doc["formato"] == antes


@pytest.mark.parametrize(
    "doc, fragmento",
    [
        ("no es dict", "objeto JSON"),
        ({"pistas": []}, "formato"),
        ({"formato": {"w": 0, "h": 1920}, "pistas": []}, "mayores que cero"),
        ({"formato": {"w": 1080, "h": 1920}}, "pistas"),
        ({"formato": {"w": 1080, "h": 1920}, "pistas": [{"tipo": "video"}]}, "id"),
        (
            {"formato": {"w": 1080, "h": 1920}, "pistas": [{"id": "a", "tipo": "raro"}]},
            "tipo invalido",
        ),
        (
            {
                "formato": {"w": 1080, "h": 1920},
                "pistas": [{"id": "a", "tipo": "video"}, {"id": "a", "tipo": "overlay"}],
            },
            "repetido",
        ),
    ],
)
def test_validar_composicion_invalida_lanza_valueerror(doc, fragmento):
    with pytest.raises(ValueError) as exc:
        video.validar_composicion(doc)
    assert fragmento in str(exc.value)
