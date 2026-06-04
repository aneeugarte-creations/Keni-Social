"""Esquema del DOCUMENTO de capas + adaptador desde spec + render del dominio.

Las pruebas de esquema/adaptador son PURAS (sin DB/red/Node). Las del dominio mockean el
subproceso Node (`_correr_render_documento`) y la media, igual que `test_estudio_imagen`.
"""

from __future__ import annotations

import pytest

from keni_consola import media
from keni_consola.dominio import estudio_imagen as e
from keni_consola.motores.estudio_imagen import documento as d
from keni_consola.motores.estudio_imagen import spec_plantilla as sp


# --------------------------------------------------------------------------- #
# Esquema (validar)                                                            #
# --------------------------------------------------------------------------- #


def _doc(**over):
    base = {
        "formato": {"w": 1080, "h": 1350, "safe_top": 60, "safe_bottom": 96},
        "fondo": {"tipo": "color", "color": "#111315"},
        "capas": [],
    }
    base.update(over)
    return base


def test_validar_documento_minimo_aplica_defaults():
    doc = d.validar(_doc())
    assert doc["version"] == d.VERSION
    assert doc["formato"] == {"w": 1080, "h": 1350, "safe_top": 60, "safe_bottom": 96}
    assert doc["fondo"]["tipo"] == "color"
    assert doc["capas"] == []
    assert doc["fuentes"] == {"sans": "Barlow", "condensada": "Barlow Condensed"}


def test_validar_capa_imagen_normaliza_y_genera_id():
    doc = d.validar(_doc(capas=[{"tipo": "imagen", "objeto": "x.png", "x": 0, "y": 0, "w": 100, "h": 100}]))
    capa = doc["capas"][0]
    assert capa["tipo"] == "imagen" and capa["objeto"] == "x.png"
    assert capa["ajuste"] == "cover" and capa["foco"] == [0.5, 0.5]
    assert isinstance(capa["id"], str) and capa["id"]  # id autogenerado
    assert capa["opacidad"] == 1.0 and capa["visible"] is True


def test_validar_filtros_solo_si_no_neutro():
    sin = d.validar(_doc(capas=[{"tipo": "imagen", "x": 0, "y": 0, "w": 10, "h": 10,
                                  "filtros": {"brillo": 1, "contraste": 1, "saturacion": 1, "desenfoque": 0}}]))
    assert sin["capas"][0]["filtros"] is None
    con = d.validar(_doc(capas=[{"tipo": "imagen", "x": 0, "y": 0, "w": 10, "h": 10,
                                 "filtros": {"brillo": 1.2}}]))
    assert con["capas"][0]["filtros"]["brillo"] == 1.2


def test_validar_sombra_texto_ausente_es_null_y_no_ensucia():
    doc = d.validar(_doc(capas=[{"tipo": "texto", "x": 0, "y": 0, "w": 100, "h": 0,
                                 "texto": "hola", "color": "#FFFFFF"}]))
    assert doc["capas"][0]["sombra"] is None


def test_validar_sombra_texto_plana_no_persiste_blur_ni_opacidad():
    # Sombra clásica (dx,dy,color) sin blur ni opacidad: no se añaden esos campos => render legado.
    doc = d.validar(_doc(capas=[{"tipo": "texto", "x": 0, "y": 0, "w": 100, "h": 0,
                                 "texto": "hola", "color": "#FFFFFF",
                                 "sombra": {"dx": 3, "dy": 4, "color": "#000000"}}]))
    s = doc["capas"][0]["sombra"]
    assert s == {"dx": 3, "dy": 4, "color": "#000000"}
    assert "desenfoque" not in s and "opacidad" not in s


def test_validar_sombra_texto_con_blur_y_opacidad_persisten():
    doc = d.validar(_doc(capas=[{"tipo": "texto", "x": 0, "y": 0, "w": 100, "h": 0,
                                 "texto": "hola", "color": "#FFFFFF",
                                 "sombra": {"dx": 0, "dy": 0, "color": "#000000",
                                            "desenfoque": 20, "opacidad": 0.5}}]))
    s = doc["capas"][0]["sombra"]
    assert s["desenfoque"] == 20.0 and s["opacidad"] == 0.5
    # opacidad==1 NO se persiste (es el default): no debe ensuciar el JSON.
    doc2 = d.validar(_doc(capas=[{"tipo": "texto", "x": 0, "y": 0, "w": 100, "h": 0,
                                  "texto": "hola", "color": "#FFFFFF",
                                  "sombra": {"dx": 1, "dy": 1, "color": "#000000",
                                             "desenfoque": 0, "opacidad": 1}}]))
    assert "desenfoque" not in doc2["capas"][0]["sombra"]
    assert "opacidad" not in doc2["capas"][0]["sombra"]


def test_validar_relleno_degradado_texto():
    # Ausente => None (no ensucia). Presente y válido => persiste con ángulo default 180.
    sin = d.validar(_doc(capas=[{"tipo": "texto", "x": 0, "y": 0, "w": 100, "h": 0,
                                 "texto": "hola", "color": "#FFFFFF"}]))
    assert sin["capas"][0]["relleno_degradado"] is None
    con = d.validar(_doc(capas=[{"tipo": "texto", "x": 0, "y": 0, "w": 100, "h": 0,
                                 "texto": "hola", "color": "#FFFFFF",
                                 "relleno_degradado": {"desde": "#FF0000", "hasta": "#0000FF"}}]))
    rd = con["capas"][0]["relleno_degradado"]
    assert rd == {"desde": "#FF0000", "hasta": "#0000FF", "angulo": 180.0}
    # Hex inválido => se descarta (None), no rompe.
    malo = d.validar(_doc(capas=[{"tipo": "texto", "x": 0, "y": 0, "w": 100, "h": 0,
                                  "texto": "hola", "color": "#FFFFFF",
                                  "relleno_degradado": {"desde": "rojo", "hasta": "#0000FF"}}]))
    assert malo["capas"][0]["relleno_degradado"] is None


def test_validar_sombra_imagen_opcional():
    sin = d.validar(_doc(capas=[{"tipo": "imagen", "x": 0, "y": 0, "w": 10, "h": 10}]))
    assert sin["capas"][0]["sombra"] is None
    con = d.validar(_doc(capas=[{"tipo": "imagen", "x": 0, "y": 0, "w": 10, "h": 10,
                                 "sombra": {"dx": 0, "dy": 8, "color": "#000000", "desenfoque": 16, "opacidad": 0.4}}]))
    s = con["capas"][0]["sombra"]
    assert s["dy"] == 8 and s["desenfoque"] == 16.0 and s["opacidad"] == 0.4


def test_validar_marco_sombra_y_relleno_degradado():
    sin = d.validar(_doc(capas=[{"tipo": "marco", "x": 0, "y": 0, "w": 100, "h": 100,
                                 "forma": "rect", "relleno": "#FF0000"}]))
    assert sin["capas"][0]["sombra"] is None
    assert sin["capas"][0]["relleno_degradado"] is None
    con = d.validar(_doc(capas=[{"tipo": "marco", "x": 0, "y": 0, "w": 100, "h": 100,
                                 "forma": "rect",
                                 "relleno_degradado": {"desde": "#111111", "hasta": "#222222", "angulo": 45},
                                 "sombra": {"dx": 0, "dy": 12, "color": "#000000", "desenfoque": 24, "opacidad": 0.5}}]))
    m = con["capas"][0]
    assert m["relleno_degradado"] == {"desde": "#111111", "hasta": "#222222", "angulo": 45.0}
    assert m["sombra"]["desenfoque"] == 24.0 and m["sombra"]["opacidad"] == 0.5


def test_validar_capa_texto_exige_color_hex():
    with pytest.raises(d.DocumentoError):
        d.validar(_doc(capas=[{"tipo": "texto", "x": 0, "y": 0, "w": 100, "h": 0,
                               "texto": "hola", "color": "rojo"}]))


def test_validar_capa_texto_valign_se_valida_y_persiste():
    doc = d.validar(_doc(capas=[{"tipo": "texto", "x": 0, "y": 0, "w": 100, "h": 200,
                                 "texto": "hola", "color": "#FFFFFF", "valign": "centro"}]))
    t = doc["capas"][0]
    assert t["valign"] == "centro"
    # `ancla` se sigue aceptando (compatibilidad) y conserva su default.
    assert t["ancla"] == "arriba"


def test_validar_capa_texto_valign_invalido_deriva_de_ancla():
    # valign ausente/ inválido => deriva de `ancla` ("abajo" -> "abajo", si no "arriba").
    doc = d.validar(_doc(capas=[{"tipo": "texto", "x": 0, "y": 0, "w": 100, "h": 0,
                                 "texto": "hola", "color": "#FFFFFF", "ancla": "abajo",
                                 "valign": "diagonal"}]))
    t = doc["capas"][0]
    assert t["valign"] == "abajo"
    assert t["ancla"] == "abajo"


def test_validar_marco_y_overlay_y_grupo():
    doc = d.validar(_doc(capas=[
        {"tipo": "marco", "x": 0, "y": 0, "w": 100, "h": 100, "forma": "rect",
         "relleno": "#FF0000", "borde": {"color": "#000000", "grosor": 4}, "radio": 8},
        {"tipo": "overlay", "x": 0, "y": 0, "w": 1080, "h": 1350, "color": "#111315"},
        {"tipo": "grupo", "x": 0, "y": 0, "w": 10, "h": 10, "capas": [
            {"tipo": "texto", "x": 0, "y": 0, "w": 10, "h": 0, "texto": "a", "color": "#FFFFFF"},
        ]},
    ]))
    marco, overlay, grupo = doc["capas"]
    assert marco["forma"] == "rect" and marco["borde"]["grosor"] == 4.0
    assert overlay["tipo"] == "overlay" and overlay["alpha"] == sp._DEGRADADO_ALPHA
    assert grupo["tipo"] == "grupo" and grupo["capas"][0]["tipo"] == "texto"


def test_validar_tipo_capa_invalido():
    with pytest.raises(d.DocumentoError):
        d.validar(_doc(capas=[{"tipo": "video", "x": 0, "y": 0, "w": 1, "h": 1}]))


# --------------------------------------------------------------------------- #
# Adaptador desde_spec                                                         #
# --------------------------------------------------------------------------- #


def _plana(**over):
    base = {
        "rojo": "#E30613", "tinta": "#111315", "blanco": "#FFFFFF",
        "etiqueta_default": "ÚLTIMA HORA", "titular_mayusculas": False,
        "titular_condensada": True, "logo": "", "logo_posicion": "superior-izquierda",
        "wordmark": "UnoTV",
    }
    base.update(over)
    return base


def test_desde_spec_produce_documento_de_capas():
    spec = sp.spec_por_defecto("unotv", _plana())
    doc = d.desde_spec(spec, "feed")
    assert doc["formato"] == {"w": 1080, "h": 1350, "safe_top": 60, "safe_bottom": 96}
    tipos = [c["tipo"] for c in doc["capas"]]
    # foto (imagen), overlay, pleca+titular (texto), logo.
    assert tipos.count("imagen") == 1
    assert "overlay" in tipos and "logo" in tipos
    assert tipos.count("texto") >= 1
    foto = next(c for c in doc["capas"] if c["tipo"] == "imagen")
    assert foto["id"] == "foto" and foto["z"] == 0
    titular = next(c for c in doc["capas"] if c["tipo"] == "texto" and c.get("binding") == "copy_in")
    assert titular["ancla"] == "abajo"
    # `valign` deriva de `ancla` por defecto (las plantillas del spec solo traen `ancla`).
    assert titular["valign"] == "abajo"


def test_desde_spec_formato_inexistente():
    spec = sp.spec_por_defecto("unotv", _plana())
    with pytest.raises(d.DocumentoError):
        d.desde_spec(spec, "no-existe")


# --------------------------------------------------------------------------- #
# Dominio: renderizar_documento (Node mockeado)                                #
# --------------------------------------------------------------------------- #


def _fake_render_doc(monkeypatch):
    cap: dict[str, object] = {}

    def _fake(payload, out):
        cap["payload"] = payload
        out.write_bytes(b"png")

    monkeypatch.setattr(e, "_correr_render_documento", _fake)
    return cap


def test_renderizar_documento_materializa_assets(entorno, monkeypatch):
    cap = _fake_render_doc(monkeypatch)
    monkeypatch.setattr(media, "leer_media", lambda nombre: b"bytes")
    # El render persiste el PNG con NOMBRE POR CONTENIDO (hash); mockeamos esa función.
    monkeypatch.setattr(media, "guardar_bytes_contenido", lambda datos, ext="png": "render.png")

    doc = _doc(capas=[
        {"tipo": "imagen", "objeto": "foto-1.png", "x": 0, "y": 0, "w": 1080, "h": 1350},
        {"tipo": "logo", "tipo_logo": "imagen", "media_id": "logo-2.png",
         "x": 40, "y": 40, "w": 220, "h": 96},
        {"tipo": "texto", "x": 40, "y": 1200, "w": 1000, "h": 0, "texto": "Hola", "color": "#FFFFFF"},
    ])
    res = e.renderizar_documento(doc, bindings={"copy_in": "T"})

    assert res == {"id": "render.png", "url": "/api/media/render.png"}
    assets = cap["payload"]["assets"]
    assert set(assets) == {"foto-1.png", "logo-2.png"}  # solo las imágenes referenciadas
    assert cap["payload"]["bindings"] == {"copy_in": "T"}


def test_renderizar_documento_invalido_lanza_estudioerror(entorno, monkeypatch):
    _fake_render_doc(monkeypatch)
    with pytest.raises(e.EstudioError):
        e.renderizar_documento({"formato": {"w": 100, "h": 100}, "capas": [{"tipo": "video"}]})


def test_documento_desde_plantilla_marca_desconocida(entorno):
    with pytest.raises(e.EstudioError):
        e.documento_desde_plantilla("marca-fantasma", "feed")
