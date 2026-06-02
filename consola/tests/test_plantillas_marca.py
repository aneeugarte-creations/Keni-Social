"""Tests del store EDITABLE de Plantilla de marca (`plantillas_marca.py`). OFFLINE, sin BD.

Aisla el store en `tmp_path` via `KENI_PLANTILLAS_MARCA_DIR`. Cubre: defaults por marca
(visuales toman `marcas.json`; el resto, genericos), roundtrip guardar+obtener (el override
gana), merge parcial y validacion (marca, hex, posicion).
"""

from __future__ import annotations

import pytest

from keni_consola import plantillas_marca


@pytest.fixture
def store(monkeypatch, tmp_path):
    """Aisla el store de plantillas en tmp via `KENI_PLANTILLAS_MARCA_DIR`."""
    monkeypatch.setenv(plantillas_marca.ENV_PLANTILLAS_MARCA_DIR, str(tmp_path / "plantillas"))
    return tmp_path


# --------------------------------------------------------------------------- #
# Defaults por marca                                                          #
# --------------------------------------------------------------------------- #


def test_defaults_marca_visual_toman_marcas_json(store):
    d = plantillas_marca.DEFECTOS("unotv")
    assert d["rojo"] == "#E30613"
    assert d["etiqueta_default"] == "ÚLTIMA HORA"
    assert d["wordmark"] == "UnoTV"
    assert d["logo"] == ""
    assert d["logo_posicion"] == "superior-izquierda"


def test_defaults_claro_sports_condensada(store):
    d = plantillas_marca.DEFECTOS("claro-sports")
    assert d["titular_mayusculas"] is True
    assert d["titular_condensada"] is True
    assert d["rojo"] == "#CF2E2E"


def test_defaults_marca_generica(store):
    d = plantillas_marca.DEFECTOS("nacion-gamer")
    assert d["rojo"] == "#E30613"
    assert d["tinta"] == "#111315"
    assert d["blanco"] == "#FFFFFF"
    assert d["etiqueta_default"] == ""
    assert d["titular_mayusculas"] is False
    assert d["logo"] == ""
    assert d["logo_posicion"] == "superior-izquierda"
    assert d["wordmark"] == "Nación Gamer"  # = etiqueta humana


def test_obtener_sin_override_es_defaults(store):
    assert plantillas_marca.obtener("piso-15") == plantillas_marca.DEFECTOS("piso-15")


def test_listar_cubre_todas_las_marcas(store):
    todas = plantillas_marca.listar()
    assert set(todas) == {"unotv", "claro-sports", "nacion-gamer", "piso-15", "fundacion"}


# --------------------------------------------------------------------------- #
# Roundtrip guardar + obtener (el override gana)                              #
# --------------------------------------------------------------------------- #


def test_guardar_y_obtener_override_gana(store):
    plantillas_marca.guardar(
        "unotv",
        {"rojo": "#123456", "etiqueta_default": "EXCLUSIVA", "logo_posicion": "inferior-derecha",
         "titular_mayusculas": True, "logo": "abc.png", "wordmark": "Uno"},
    )
    d = plantillas_marca.obtener("unotv")
    assert d["rojo"] == "#123456"
    assert d["etiqueta_default"] == "EXCLUSIVA"
    assert d["logo_posicion"] == "inferior-derecha"
    assert d["titular_mayusculas"] is True
    assert d["logo"] == "abc.png"
    # Lo no enviado conserva el default de la marca.
    assert d["tinta"] == plantillas_marca.DEFECTOS("unotv")["tinta"]


def test_guardar_parcial_no_borra_campos_previos(store):
    plantillas_marca.guardar("fundacion", {"rojo": "#AAAAAA"})
    plantillas_marca.guardar("fundacion", {"etiqueta_default": "AVISO"})
    d = plantillas_marca.obtener("fundacion")
    assert d["rojo"] == "#AAAAAA"  # persiste del primer guardado
    assert d["etiqueta_default"] == "AVISO"


def test_guardar_devuelve_plantilla_efectiva(store):
    res = plantillas_marca.guardar("piso-15", {"blanco": "#000000"})
    assert res["blanco"] == "#000000"
    assert res == plantillas_marca.obtener("piso-15")


def test_guardar_persiste_solo_campos_editables(store):
    plantillas_marca.guardar("unotv", {"rojo": "#111111", "nombre": "HACK", "verificar": "x"})
    import json
    crudo = json.loads((store / "plantillas" / "unotv.json").read_text())
    assert set(crudo) <= set(plantillas_marca.CAMPOS)
    assert "nombre" not in crudo and "verificar" not in crudo


# --------------------------------------------------------------------------- #
# Validacion                                                                  #
# --------------------------------------------------------------------------- #


def test_marca_desconocida_lanza(store):
    with pytest.raises(plantillas_marca.PlantillaMarcaError):
        plantillas_marca.obtener("no-existe")
    with pytest.raises(plantillas_marca.PlantillaMarcaError):
        plantillas_marca.guardar("no-existe", {"rojo": "#FFFFFF"})


def test_hex_invalido_lanza(store):
    for malo in ("rojo", "tinta", "blanco"):
        with pytest.raises(plantillas_marca.PlantillaMarcaError):
            plantillas_marca.guardar("unotv", {malo: "rojo"})
    with pytest.raises(plantillas_marca.PlantillaMarcaError):
        plantillas_marca.guardar("unotv", {"rojo": "#FFF"})  # 3 digitos no vale
    with pytest.raises(plantillas_marca.PlantillaMarcaError):
        plantillas_marca.guardar("unotv", {"rojo": "E30613"})  # sin almohadilla


def test_logo_posicion_invalida_lanza(store):
    with pytest.raises(plantillas_marca.PlantillaMarcaError):
        plantillas_marca.guardar("unotv", {"logo_posicion": "centro"})


def test_flags_no_bool_lanzan(store):
    with pytest.raises(plantillas_marca.PlantillaMarcaError):
        plantillas_marca.guardar("unotv", {"titular_mayusculas": "si"})


def test_logo_no_str_lanza(store):
    with pytest.raises(plantillas_marca.PlantillaMarcaError):
        plantillas_marca.guardar("unotv", {"logo": 123})


def test_hex_valido_acepta_mayusculas_y_minusculas(store):
    plantillas_marca.guardar("unotv", {"rojo": "#abcDEF"})
    assert plantillas_marca.obtener("unotv")["rojo"] == "#abcDEF"


# --------------------------------------------------------------------------- #
# SPEC de capas (editor visual)                                               #
# --------------------------------------------------------------------------- #


def test_obtener_spec_deriva_de_planos_si_no_hay_guardado(store):
    spec = plantillas_marca.obtener_spec("unotv")
    assert sorted(spec["formatos"]) == ["cuadrado", "feed", "horizontal", "vertical"]
    assert spec["marca"] == "unotv"


def test_guardar_spec_round_trip(store):
    spec = plantillas_marca.obtener_spec("unotv")
    # Modifica una coordenada del logo y persiste.
    spec["formatos"]["feed"]["logo"]["x"] = 123
    plantillas_marca.guardar_spec("unotv", spec)
    releido = plantillas_marca.obtener_spec("unotv")
    assert releido["formatos"]["feed"]["logo"]["x"] == 123


def test_guardar_spec_conserva_campos_planos(store):
    plantillas_marca.guardar("unotv", {"rojo": "#123456", "etiqueta_default": "AHORA"})
    plantillas_marca.guardar_spec("unotv", plantillas_marca.obtener_spec("unotv"))
    plana = plantillas_marca.obtener("unotv")
    assert plana["rojo"] == "#123456" and plana["etiqueta_default"] == "AHORA"


def test_guardar_plano_conserva_spec(store):
    plantillas_marca.guardar_spec("unotv", plantillas_marca.obtener_spec("unotv"))
    plantillas_marca.guardar("unotv", {"rojo": "#654321"})  # PUT plano no borra el spec
    crudo = plantillas_marca._leer_override("unotv")
    assert plantillas_marca.SPEC_KEY in crudo


def test_guardar_spec_invalido_lanza(store):
    from keni_consola.motores.estudio_imagen import spec_plantilla as sp
    spec = plantillas_marca.obtener_spec("unotv")
    spec["formatos"]["feed"]["fondo"] = {"tipo": "color", "color": "no-hex"}
    with pytest.raises(plantillas_marca.PlantillaMarcaError):
        plantillas_marca.guardar_spec("unotv", spec)
    assert sp  # import usado
