"""Tests del dominio del Estudio de imagen. OFFLINE: ni red ni Pillow ni subprocesos.

`_correr_motor` (subproceso) y el proveedor de media se mockean; se cubre la composicion
del prompt, la materializacion de la entrada y la importacion de las salidas.
"""

from __future__ import annotations

import pytest

from keni_consola import media
from keni_consola.dominio import estudio_imagen as e

# --------------------------------------------------------------------------- #
# componer_prompt                                                             #
# --------------------------------------------------------------------------- #


def test_componer_prompt_incluye_base_marca_y_aspecto(entorno):
    """La base viene de la SEMILLA (store vacio), mas la nota de marca y el aspecto del formato."""
    p = e.componer_prompt("estadio al atardecer", "claro-sports", "feed")
    assert "estadio al atardecer" in p
    assert "Claro Sports" in p  # nota de estilo de marca
    assert "4:5" in p  # aspecto del formato feed
    assert "director de arte" in p.lower()  # cuerpo de la semilla prompt/imagen/ilustracion-fondo


def test_componer_prompt_formato_desconocido_cae_a_feed(entorno):
    p = e.componer_prompt("algo", "", "inventado")
    assert "4:5" in p  # feed por defecto


def test_componer_prompt_sin_marca_no_revienta(entorno):
    p = e.componer_prompt("algo", "", "vertical")
    assert "9:16" in p


# --------------------------------------------------------------------------- #
# editar (determinista, motor mockeado)                                       #
# --------------------------------------------------------------------------- #


def test_editar_op_invalida(entorno):
    with pytest.raises(e.EstudioError):
        e.editar("x.png", "borrar-todo", {})


def test_editar_recortar_importa_salidas(entorno, monkeypatch):
    monkeypatch.setattr(media, "leer_media", lambda nombre: b"bytes-de-imagen")
    monkeypatch.setattr(
        e, "_correr_motor", lambda cmd, **kw: {"op": "recortar", "salidas": [{"salida": "/tmp/out.png"}]}
    )
    monkeypatch.setattr(media, "importar_imagen", lambda ruta: "nuevo.png")
    res = e.editar("origen.png", "recortar", {"formato": "feed"})
    assert res["id"] == "nuevo.png"
    assert res["url"] == "/api/media/nuevo.png"
    assert res["imagenes"] == [{"id": "nuevo.png", "url": "/api/media/nuevo.png"}]
    assert res["info"]["op"] == "recortar"


def test_editar_imagen_inexistente(entorno, monkeypatch):
    monkeypatch.setattr(media, "leer_media", lambda nombre: None)
    with pytest.raises(e.EstudioError):
        e.editar("noexiste.png", "recortar", {"formato": "feed"})


def test_editar_motor_sin_datos(entorno, monkeypatch):
    monkeypatch.setattr(media, "leer_media", lambda nombre: b"bytes")
    monkeypatch.setattr(e, "_correr_motor", lambda cmd, **kw: {"op": "recortar"})  # sin "salidas"
    with pytest.raises(e.EstudioError):
        e.editar("origen.png", "recortar", {"formato": "feed"})


def test_editar_placa_sin_foto_ok(entorno, monkeypatch):
    """`placa` puede no llevar foto: no se materializa nada y aun asi corre."""
    capt = {}

    def _fake(cmd, **kw):
        capt["cmd"] = cmd
        return {"op": "placa", "salidas": [{"salida": "/tmp/placa.png"}]}

    monkeypatch.setattr(e, "_correr_motor", _fake)
    monkeypatch.setattr(media, "importar_imagen", lambda ruta: "placa.png")
    res = e.editar("", "placa", {"formato": "feed", "texto": "Gol", "marca": "unotv"})
    assert res["id"] == "placa.png"
    assert "--foto" not in capt["cmd"]  # sin foto de fondo


# --------------------------------------------------------------------------- #
# expandir (outpainting, motor mockeado)                                      #
# --------------------------------------------------------------------------- #


def test_expandir_importa_salida(entorno, monkeypatch):
    monkeypatch.setattr(media, "leer_media", lambda nombre: b"bytes")
    monkeypatch.setattr(
        e, "_correr_motor", lambda cmd, **kw: {"modelo": "x", "salidas": [{"salida": "/tmp/exp.png"}]}
    )
    monkeypatch.setattr(media, "importar_imagen", lambda ruta: "exp.png")
    res = e.expandir("origen.png", formato="feed", marca="claro-sports", strength=0.4)
    assert res["id"] == "exp.png"
    assert res["info"]["modelo"] == "x"


def test_expandir_sin_imagen(entorno):
    with pytest.raises(e.EstudioError):
        e.expandir("", formato="feed")


# --------------------------------------------------------------------------- #
# retocar (instruccion generativa, motor mockeado)                            #
# --------------------------------------------------------------------------- #


def test_retocar_importa_salida(entorno, monkeypatch):
    monkeypatch.setattr(media, "leer_media", lambda nombre: b"bytes")
    capt = {}

    def _fake(cmd, **kw):
        capt["cmd"] = cmd
        return {"op": "retocar", "modelo": "x", "salidas": [{"salida": "/tmp/ret.png"}]}

    monkeypatch.setattr(e, "_correr_motor", _fake)
    monkeypatch.setattr(media, "importar_imagen", lambda ruta: "ret.png")
    res = e.retocar("origen.png", "oscurece el cielo", strength=0.6)
    assert res["id"] == "ret.png"
    assert "--instruccion" in capt["cmd"]
    assert "oscurece el cielo" in capt["cmd"]


def test_retocar_sin_imagen(entorno):
    with pytest.raises(e.EstudioError):
        e.retocar("", "algo")


def test_retocar_sin_instruccion(entorno):
    with pytest.raises(e.EstudioError):
        e.retocar("origen.png", "  ")


# --------------------------------------------------------------------------- #
# componer (plantilla de marca: con foto y placeholder)                       #
# --------------------------------------------------------------------------- #


def test_marca_tiene_plantilla(entorno):
    # Solo cuenta como "con plantilla" una marca REALMENTE configurada: las de tokens
    # precargados (unotv / claro-sports) o una marca del catalogo a la que se le diseñó y
    # guardó un SPEC en el editor visual. Una marca del catalogo sin diseño propio (piso-15,
    # fundacion) NO compone por defecto.
    from keni_consola import plantillas_marca

    assert e.marca_tiene_plantilla("unotv")
    assert e.marca_tiene_plantilla("claro-sports")
    assert not e.marca_tiene_plantilla("piso-15")
    assert not e.marca_tiene_plantilla("fundacion")
    assert not e.marca_tiene_plantilla("desconocida")

    # Al guardar un SPEC para una marca del catalogo, pasa a tener plantilla configurada.
    plantillas_marca.guardar_spec("fundacion", plantillas_marca.obtener_spec("fundacion"))
    assert e.marca_tiene_plantilla("fundacion")


def test_formato_por_red():
    assert e.formato_por_red("tiktok") == "vertical"
    assert e.formato_por_red("instagram") == "cuadrado"
    assert e.formato_por_red("facebook") == "feed"
    assert e.formato_por_red("desconocida") == "feed"  # default


def _fake_render_node(monkeypatch):
    """Mockea `_correr_render_node`: escribe el PNG y captura el payload. No ejecuta Node."""
    cap: dict[str, object] = {}

    def _fake(payload, out):
        cap["payload"] = payload
        out.write_bytes(b"png")

    monkeypatch.setattr(e, "_correr_render_node", _fake)
    return cap


def test_componer_placeholder_node(entorno, monkeypatch):
    # imagen="" => placeholder; el motor por defecto (Node) recibe el spec y el copy_in.
    cap = _fake_render_node(monkeypatch)
    monkeypatch.setattr(media, "importar_imagen", lambda ruta: "placa.png")

    res = e.componer("", marca="unotv", formato="feed", titular="DATO CLAVE")

    assert res["id"] == "placa.png"
    assert res["info"]["motor"] == "node"
    p = cap["payload"]
    assert p["placeholder"] is True and p["foto"] is None
    assert p["formato"] == "feed" and "formatos" in p["spec"]
    assert p["bindings"]["copy_in"] == "DATO CLAVE"


def test_componer_con_foto_node(entorno, monkeypatch):
    cap = _fake_render_node(monkeypatch)
    monkeypatch.setattr(media, "leer_media", lambda nombre: b"bytes-de-foto")
    monkeypatch.setattr(media, "importar_imagen", lambda ruta: "final.png")

    res = e.componer("foto.jpg", marca="unotv", formato="feed", titular="X")

    assert res["id"] == "final.png"
    assert res["info"]["placeholder"] is False
    assert cap["payload"]["foto"] is not None  # foto materializada a ruta temporal


def test_componer_etiqueta_resuelta_en_binding(entorno, monkeypatch):
    # etiqueta="" => pleca omitida: el binding etiqueta_default viaja vacío.
    cap = _fake_render_node(monkeypatch)
    monkeypatch.setattr(media, "importar_imagen", lambda ruta: "x.png")
    e.componer("", marca="unotv", formato="feed", titular="T", etiqueta="")
    assert cap["payload"]["bindings"]["etiqueta_default"] == ""


def test_componer_node_unico_motor_propaga_error(entorno, monkeypatch):
    # Node es el ÚNICO motor (sin fallback Pillow): si falla, `componer` lanza EstudioError.
    def _node_boom(payload, out):
        raise e.EstudioError("node no disponible")

    monkeypatch.setattr(e, "_correr_render_node", _node_boom)
    with pytest.raises(e.EstudioError):
        e.componer("", marca="unotv", formato="feed", titular="T")
