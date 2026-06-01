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
# componer (plantilla de marca: con foto y placeholder)                       #
# --------------------------------------------------------------------------- #


def test_marca_tiene_plantilla():
    assert e.marca_tiene_plantilla("unotv")
    assert e.marca_tiene_plantilla("claro-sports")
    assert not e.marca_tiene_plantilla("piso-15")
    assert not e.marca_tiene_plantilla("desconocida")


def test_formato_por_red():
    assert e.formato_por_red("tiktok") == "vertical"
    assert e.formato_por_red("instagram") == "cuadrado"
    assert e.formato_por_red("facebook") == "feed"
    assert e.formato_por_red("desconocida") == "feed"  # default


def _fake_run_que_escribe_salida(monkeypatch):
    """Mockea `subprocess.run` del dominio: escribe el `--salida` y devuelve rc 0. Captura cmd."""
    from pathlib import Path
    from types import SimpleNamespace

    capturado: dict[str, list[str]] = {}

    def _fake(cmd, **kw):
        capturado["cmd"] = cmd
        salida = cmd[cmd.index("--salida") + 1]
        Path(salida).write_bytes(b"png")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(e.subprocess, "run", _fake)
    return capturado


def test_componer_placeholder_sin_foto(entorno, monkeypatch):
    # imagen="" => modo placeholder: pasa --placeholder, NO --foto, y no materializa foto.
    cap = _fake_run_que_escribe_salida(monkeypatch)
    monkeypatch.setattr(media, "importar_imagen", lambda ruta: "placa.png")
    monkeypatch.setattr(
        media, "leer_media", lambda nombre: (_ for _ in ()).throw(AssertionError("no debe leer foto"))
    )

    res = e.componer("", marca="unotv", formato="feed", titular="DATO CLAVE")

    assert res["id"] == "placa.png"
    assert res["info"]["placeholder"] is True
    assert "--placeholder" in cap["cmd"]
    assert "--foto" not in cap["cmd"]
    assert "DATO CLAVE" in cap["cmd"]  # el copy_in viaja como --titular


def test_componer_con_foto_materializa_y_no_placeholder(entorno, monkeypatch):
    cap = _fake_run_que_escribe_salida(monkeypatch)
    monkeypatch.setattr(media, "leer_media", lambda nombre: b"bytes-de-foto")
    monkeypatch.setattr(media, "importar_imagen", lambda ruta: "final.png")

    res = e.componer("foto.jpg", marca="unotv", formato="feed", titular="X")

    assert res["id"] == "final.png"
    assert res["info"]["placeholder"] is False
    assert "--foto" in cap["cmd"]
    assert "--placeholder" not in cap["cmd"]
