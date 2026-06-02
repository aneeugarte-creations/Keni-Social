"""Esquema del SPEC de plantilla de marca: defaults derivados + validación. PURO (sin DB/red)."""

from __future__ import annotations

import pytest

from keni_consola.motores.estudio_imagen import spec_plantilla as sp


def _plana(**over):
    base = {
        "rojo": "#E30613", "tinta": "#111315", "blanco": "#FFFFFF",
        "etiqueta_default": "ÚLTIMA HORA", "titular_mayusculas": False,
        "titular_condensada": True, "logo": "", "logo_posicion": "superior-izquierda",
        "wordmark": "UnoTV",
    }
    base.update(over)
    return base


def test_spec_por_defecto_cuatro_formatos_y_capas():
    spec = sp.spec_por_defecto("unotv", _plana())
    assert spec["version"] == sp.VERSION
    assert sorted(spec["formatos"]) == ["cuadrado", "feed", "horizontal", "vertical"]
    feed = spec["formatos"]["feed"]
    assert feed["lienzo"] == {"w": 1080, "h": 1350, "safe_top": 60, "safe_bottom": 96}
    assert feed["foto_slot"]["w"] == 1080 and feed["foto_slot"]["ajuste"] == "cover"
    # Con etiqueta_default hay pleca + titular; el titular hace binding a copy_in.
    ids = [t["id"] for t in feed["textos"]]
    assert "titular" in ids and "pleca" in ids
    titular = next(t for t in feed["textos"] if t["id"] == "titular")
    assert titular["binding"] == "copy_in"
    assert titular["familia"] == "condensada"  # titular_condensada=True


def test_spec_por_defecto_horizontal_16_9_con_placa():
    """El lienzo 16:9 (X) deriva su SPEC en 1600×900 con logo + pleca + titular legibles."""
    spec = sp.spec_por_defecto("unotv", _plana())
    h = spec["formatos"]["horizontal"]
    assert h["lienzo"] == {"w": 1600, "h": 900, "safe_top": 56, "safe_bottom": 72}
    # Foto a lienzo completo (cover) + las mismas capas de marca que el resto.
    assert h["foto_slot"]["w"] == 1600 and h["foto_slot"]["h"] == 900
    assert h["foto_slot"]["ajuste"] == "cover"
    assert h["logo"]["w"] == 220  # logo presente
    ids = [t["id"] for t in h["textos"]]
    assert "titular" in ids and "pleca" in ids
    titular = next(t for t in h["textos"] if t["id"] == "titular")
    assert titular["binding"] == "copy_in" and titular["ancla"] == "abajo"
    # El titular cabe dentro del lienzo (anclado abajo, sobre la zona segura inferior).
    assert titular["y"] <= h["lienzo"]["h"] - h["lienzo"]["safe_bottom"]


def test_validar_acepta_spec_horizontal_round_trip():
    """Un spec con el formato horizontal valida y es idempotente bajo `validar`."""
    spec = sp.spec_por_defecto("claro-sports", _plana())
    v1 = sp.validar(spec)
    assert "horizontal" in v1["formatos"]
    assert sp.validar(v1) == v1


def test_spec_por_defecto_sin_etiqueta_omite_pleca():
    spec = sp.spec_por_defecto("unotv", _plana(etiqueta_default=""))
    ids = [t["id"] for t in spec["formatos"]["feed"]["textos"]]
    assert ids == ["titular"]


def test_spec_por_defecto_logo_imagen_si_hay_logo():
    spec = sp.spec_por_defecto("unotv", _plana(logo="abc123.png"))
    logo = spec["formatos"]["feed"]["logo"]
    assert logo["tipo"] == "imagen" and logo["media_id"] == "abc123.png"


def test_validar_round_trip_idempotente():
    spec = sp.spec_por_defecto("claro-sports", _plana(wordmark="Claro Sports"))
    v1 = sp.validar(spec)
    v2 = sp.validar(v1)
    assert v1 == v2
    assert v1["fuentes"]["sans"] == "Barlow"


def test_validar_rechaza_hex_invalido():
    spec = sp.spec_por_defecto("unotv", _plana())
    spec["formatos"]["feed"]["fondo"] = {"tipo": "color", "color": "rojo"}
    with pytest.raises(sp.SpecError):
        sp.validar(spec)


def test_validar_rechaza_formato_desconocido():
    with pytest.raises(sp.SpecError):
        sp.validar({"formatos": {"panoramico": {}}})


def test_validar_limita_a_tres_textos():
    spec = sp.spec_por_defecto("unotv", _plana())
    t = spec["formatos"]["feed"]["textos"][0]
    spec["formatos"]["feed"]["textos"] = [dict(t, id="titular"), dict(t, id="pleca"),
                                          dict(t, id="kicker"), dict(t, id="titular")]
    with pytest.raises(sp.SpecError):
        sp.validar(spec)
