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
