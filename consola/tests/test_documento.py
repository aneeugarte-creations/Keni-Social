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


def _img(x, y, w, h, es_foto=True):
    return {"tipo": "imagen", "x": x, "y": y, "w": w, "h": h, "es_foto": es_foto}


# --------------------------------------------------------------------------- #
# Collage: VARIOS huecos de foto (es_foto)                                     #
# --------------------------------------------------------------------------- #


def test_capas_foto_conserva_varios_huecos():
    # Un collage declara N huecos (es_foto): validar los CONSERVA todos (antes colapsaba a 1).
    doc = d.validar(_doc(capas=[_img(0, 0, 540, 1350), _img(540, 0, 540, 1350), _img(0, 0, 100, 100, es_foto=False)]))
    assert d.cuenta_huecos_foto(doc) == 2
    assert len(d.capas_foto(doc)) == 2


def test_cuenta_huecos_acotada_al_maximo():
    capas = [_img(i * 10, 0, 50, 50) for i in range(d.MAX_HUECOS_FOTO + 3)]
    doc = d.validar(_doc(capas=capas))
    assert d.cuenta_huecos_foto(doc) == d.MAX_HUECOS_FOTO


def test_inyectar_fotos_por_hueco():
    # `componer_desde_plantilla` mete una foto por hueco, en orden de `capas`.
    doc = d.validar(_doc(capas=[_img(0, 0, 540, 1350), _img(540, 0, 540, 1350)]))
    inyectado = e._doc_plantilla_con_fotos(
        doc, [{"objeto": "a.jpg", "foco": [0.3, 0.4], "zoom": 1.2}, {"objeto": "b.jpg"}]
    )
    huecos = d.capas_foto(inyectado)
    assert huecos[0]["objeto"] == "a.jpg" and huecos[0]["foco"] == [0.3, 0.4] and huecos[0]["zoom"] == 1.2
    assert huecos[1]["objeto"] == "b.jpg"


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
    assert doc["formato"] == {
        "w": 1080, "h": 1350, "safe_top": 60, "safe_bottom": 96, "safe_left": 0, "safe_right": 0,
    }
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


def test_validar_capa_imagen_forma_y_radio_defaults_retrocompat():
    # Documento viejo (sin forma/radio): valida con los defaults limpios (rect, 0).
    doc = d.validar(_doc(capas=[{"tipo": "imagen", "x": 0, "y": 0, "w": 100, "h": 100}]))
    capa = doc["capas"][0]
    assert capa["forma"] == "rect" and capa["radio"] == 0


def test_validar_capa_imagen_forma_elipse_y_radio():
    doc = d.validar(_doc(capas=[{"tipo": "imagen", "x": 0, "y": 0, "w": 100, "h": 100,
                                 "forma": "elipse", "radio": 24}]))
    capa = doc["capas"][0]
    assert capa["forma"] == "elipse" and capa["radio"] == 24
    # Forma inválida => "rect" fallback ("triangulo" ya es válido en el catálogo; usamos un token
    # que NO existe para probar el fallback).
    malo = d.validar(_doc(capas=[{"tipo": "imagen", "x": 0, "y": 0, "w": 10, "h": 10,
                                  "forma": "trapecio", "radio": 0}]))
    assert malo["capas"][0]["forma"] == "rect" and malo["capas"][0]["radio"] == 0
    # Radio negativo => DocumentoError (límite [0, ∞); ya no se acota en silencio a 0).
    with pytest.raises(d.DocumentoError, match="radio.*no puede ser menor"):
        d.validar(_doc(capas=[{"tipo": "imagen", "x": 0, "y": 0, "w": 10, "h": 10, "radio": -5}]))


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


def test_validar_capa_imagen_flip_solo_si_true():
    # Ausente / False => NO se persiste (no ensucia documentos viejos ni cambia el render legado).
    sin = d.validar(_doc(capas=[{"tipo": "imagen", "x": 0, "y": 0, "w": 10, "h": 10}]))
    assert "flip_h" not in sin["capas"][0] and "flip_v" not in sin["capas"][0]
    no = d.validar(_doc(capas=[{"tipo": "imagen", "x": 0, "y": 0, "w": 10, "h": 10,
                                "flip_h": False, "flip_v": False}]))
    assert "flip_h" not in no["capas"][0] and "flip_v" not in no["capas"][0]
    # True => se persiste (cada eje por separado).
    con = d.validar(_doc(capas=[{"tipo": "imagen", "x": 0, "y": 0, "w": 10, "h": 10,
                                 "flip_h": True, "flip_v": False}]))
    c = con["capas"][0]
    assert c["flip_h"] is True and "flip_v" not in c
    ambos = d.validar(_doc(capas=[{"tipo": "imagen", "x": 0, "y": 0, "w": 10, "h": 10,
                                   "flip_h": True, "flip_v": True}]))
    assert ambos["capas"][0]["flip_h"] is True and ambos["capas"][0]["flip_v"] is True


def test_validar_capa_logo_flip_solo_si_true():
    sin = d.validar(_doc(capas=[{"tipo": "logo", "tipo_logo": "wordmark",
                                 "x": 0, "y": 0, "w": 10, "h": 10}]))
    assert "flip_h" not in sin["capas"][0] and "flip_v" not in sin["capas"][0]
    con = d.validar(_doc(capas=[{"tipo": "logo", "tipo_logo": "imagen", "media_id": "l.png",
                                 "x": 0, "y": 0, "w": 10, "h": 10, "flip_v": True}]))
    assert con["capas"][0]["flip_v"] is True and "flip_h" not in con["capas"][0]


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


def test_validar_capa_texto_cursiva_subrayado_solo_si_true():
    # Booleanos opcionales (round-trip editor -> servidor -> render): solo se persisten si True,
    # igual que flip_h/flip_v. Ausentes o False => el documento queda LIMPIO (retrocompat).
    base = {"tipo": "texto", "x": 0, "y": 0, "w": 100, "h": 0, "texto": "hola", "color": "#FFFFFF"}
    sin = d.validar(_doc(capas=[dict(base)]))["capas"][0]
    assert "cursiva" not in sin and "subrayado" not in sin
    falso = d.validar(_doc(capas=[dict(base, cursiva=False, subrayado=False)]))["capas"][0]
    assert "cursiva" not in falso and "subrayado" not in falso
    con = d.validar(_doc(capas=[dict(base, cursiva=True, subrayado=True)]))["capas"][0]
    assert con["cursiva"] is True and con["subrayado"] is True
    # Re-validar el documento ya validado no los pierde (idempotente).
    redoc = d.validar(_doc(capas=[con]))["capas"][0]
    assert redoc["cursiva"] is True and redoc["subrayado"] is True


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
    assert doc["formato"] == {
        "w": 1080, "h": 1350, "safe_top": 60, "safe_bottom": 96, "safe_left": 0, "safe_right": 0,
    }
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


# --------------------------------------------------------------------------- #
# BUG 1: Límites de validación (DoS)                                          #
# --------------------------------------------------------------------------- #


def test_validar_formato_w_fuera_de_rango():
    """w/h fuera de rango [16, 8000] -> DocumentoError (no 400 sutil)."""
    # w muy pequeño
    with pytest.raises(d.DocumentoError, match="no puede ser menor"):
        d.validar(_doc(formato={"w": 15, "h": 1350}))
    # w muy grande
    with pytest.raises(d.DocumentoError, match="no puede ser mayor"):
        d.validar(_doc(formato={"w": 8001, "h": 1350}))
    # h muy pequeño
    with pytest.raises(d.DocumentoError, match="no puede ser menor"):
        d.validar(_doc(formato={"w": 1080, "h": 15}))


def test_validar_capa_texto_tamano_fuera_de_rango():
    """tamano fuera de [4, 2000] -> DocumentoError."""
    # tamano muy pequeño
    with pytest.raises(d.DocumentoError, match="tamano.*no puede ser menor"):
        d.validar(_doc(capas=[{"tipo": "texto", "x": 0, "y": 0, "w": 100, "h": 0,
                               "texto": "hola", "color": "#FFFFFF", "tamano": 3}]))
    # tamano muy grande
    with pytest.raises(d.DocumentoError, match="tamano.*no puede ser mayor"):
        d.validar(_doc(capas=[{"tipo": "texto", "x": 0, "y": 0, "w": 100, "h": 0,
                               "texto": "hola", "color": "#FFFFFF", "tamano": 2001}]))


def test_validar_capa_texto_auto_ajuste_limites():
    """max_lineas en [1, 50]; tam_min en [4, 2000]."""
    # max_lineas fuera de rango
    with pytest.raises(d.DocumentoError, match="max_lineas.*no puede ser menor"):
        d.validar(_doc(capas=[{"tipo": "texto", "x": 0, "y": 0, "w": 100, "h": 200,
                               "texto": "a", "color": "#FFFFFF",
                               "auto_ajuste": {"max_lineas": 0, "tam_min": 40}}]))
    with pytest.raises(d.DocumentoError, match="max_lineas.*no puede ser mayor"):
        d.validar(_doc(capas=[{"tipo": "texto", "x": 0, "y": 0, "w": 100, "h": 200,
                               "texto": "a", "color": "#FFFFFF",
                               "auto_ajuste": {"max_lineas": 51, "tam_min": 40}}]))
    # tam_min fuera de rango
    with pytest.raises(d.DocumentoError, match="tam_min.*no puede ser menor"):
        d.validar(_doc(capas=[{"tipo": "texto", "x": 0, "y": 0, "w": 100, "h": 200,
                               "texto": "a", "color": "#FFFFFF",
                               "auto_ajuste": {"max_lineas": 4, "tam_min": 3}}]))


def test_validar_documento_limite_capas():
    """Más de MAX_CAPAS_DOCUMENTO (200) capas incluyendo hijas de grupos -> DocumentoError."""
    capas_muchas = [{"tipo": "imagen", "x": 0, "y": 0, "w": 10, "h": 10} for _ in range(201)]
    with pytest.raises(d.DocumentoError, match="demasiadas capas"):
        d.validar(_doc(capas=capas_muchas))


def test_validar_documento_limite_capas_con_grupo():
    """Las capas hijas de un grupo cuentan para el límite total (201 incluyendo 1 grupo + 200 hijas)."""
    capas = [{"tipo": "grupo", "x": 0, "y": 0, "w": 10, "h": 10,
              "capas": [{"tipo": "imagen", "x": 0, "y": 0, "w": 10, "h": 10} for _ in range(200)]}]
    with pytest.raises(d.DocumentoError, match="demasiadas capas"):
        d.validar(_doc(capas=capas))


# --------------------------------------------------------------------------- #
# BUG 2: Casts sin guardar -> 500 en vez de 400                               #
# --------------------------------------------------------------------------- #


def test_capa_base_z_invalido_400():
    """z con valor no-numérico -> DocumentoError (no 500)."""
    with pytest.raises(d.DocumentoError, match="z.*número entero"):
        d.validar(_doc(capas=[{"tipo": "imagen", "x": 0, "y": 0, "w": 10, "h": 10, "z": "x"}]))


def test_capa_base_rotacion_invalida_400():
    """rotacion con valor no-numérico -> DocumentoError (no 500)."""
    with pytest.raises(d.DocumentoError, match="rotacion"):
        d.validar(_doc(capas=[{"tipo": "imagen", "x": 0, "y": 0, "w": 10, "h": 10, "rotacion": {}}]))


def test_capa_texto_tamano_no_numerico_400():
    """tamano con valor no-numérico (ej. dict) -> DocumentoError (no 500)."""
    with pytest.raises(d.DocumentoError, match="tamano.*número entero"):
        d.validar(_doc(capas=[{"tipo": "texto", "x": 0, "y": 0, "w": 100, "h": 0,
                               "texto": "a", "color": "#FFFFFF", "tamano": {}}]))


def test_capa_texto_peso_no_numerico_400():
    """peso con valor no-numérico -> DocumentoError (no 500)."""
    with pytest.raises(d.DocumentoError, match="peso.*número entero"):
        d.validar(_doc(capas=[{"tipo": "texto", "x": 0, "y": 0, "w": 100, "h": 0,
                               "texto": "a", "color": "#FFFFFF", "peso": "bold"}]))


def test_capa_sombra_dx_no_numerico_400():
    """sombra.dx con valor no-numérico -> DocumentoError (no 500)."""
    with pytest.raises(d.DocumentoError, match="dx.*número entero"):
        d.validar(_doc(capas=[{"tipo": "imagen", "x": 0, "y": 0, "w": 10, "h": 10,
                               "sombra": {"dx": "nope", "dy": 2, "color": "#000000"}}]))


def test_capa_chip_pad_no_numerico_400():
    """chip.pad_x con valor no-numérico -> DocumentoError (no 500)."""
    with pytest.raises(d.DocumentoError, match="pad_x.*número entero"):
        d.validar(_doc(capas=[{"tipo": "texto", "x": 0, "y": 0, "w": 100, "h": 0,
                               "texto": "a", "color": "#FFFFFF",
                               "chip": {"color": "#FF0000", "pad_x": "wide"}}]))


def test_capa_overlay_alpha_no_numerico_400():
    """overlay.alpha con valor no-numérico -> DocumentoError (no 500)."""
    with pytest.raises(d.DocumentoError, match="alpha.*número entero"):
        d.validar(_doc(capas=[{"tipo": "overlay", "x": 0, "y": 0, "w": 100, "h": 100,
                               "color": "#000000", "alpha": "opaque"}]))
