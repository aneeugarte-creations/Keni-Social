"""Tests del dominio del Estudio de imagen. OFFLINE: ni red ni Pillow ni subprocesos.

`_correr_motor` (subproceso) y el proveedor de media se mockean; se cubre la composicion
del prompt, la materializacion de la entrada y la importacion de las salidas.
"""

from __future__ import annotations

import pytest

from keni_consola import media
from keni_consola.dominio import estudio_imagen as e

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
# componer (plantilla de marca: con foto y placeholder)                       #
# --------------------------------------------------------------------------- #


def test_marca_tiene_plantilla(entorno):
    # Solo cuenta como "con plantilla" una marca REALMENTE configurada: las de tokens
    # precargados (unotv / claro-sports / fundacion) o una marca del catalogo a la que se le
    # diseñó y guardó un SPEC en el editor visual. Una marca del catalogo sin diseño propio
    # (piso-15, nacion-gamer) NO compone por defecto.
    from keni_consola import plantillas_marca

    assert e.marca_tiene_plantilla("unotv")
    assert e.marca_tiene_plantilla("claro-sports")
    assert e.marca_tiene_plantilla("fundacion")
    assert not e.marca_tiene_plantilla("piso-15")
    assert not e.marca_tiene_plantilla("nacion-gamer")
    assert not e.marca_tiene_plantilla("desconocida")

    # Al guardar un SPEC para una marca del catalogo, pasa a tener plantilla configurada.
    plantillas_marca.guardar_spec("nacion-gamer", plantillas_marca.obtener_spec("nacion-gamer"))
    assert e.marca_tiene_plantilla("nacion-gamer")


def test_formato_por_red():
    # Regla de producto: todo post de foto va en 4:5 (`feed`), incluido Instagram.
    assert e.formato_por_red("tiktok") == "vertical"  # video vertical nativo
    assert e.formato_por_red("instagram") == "feed"
    assert e.formato_por_red("facebook") == "feed"
    assert e.formato_por_red("x") == "feed"
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
    monkeypatch.setattr(media, "guardar_bytes_contenido", lambda datos, ext="png": "placa.png")

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
    monkeypatch.setattr(media, "guardar_bytes_contenido", lambda datos, ext="png": "final.png")

    res = e.componer("foto.jpg", marca="unotv", formato="feed", titular="X")

    assert res["id"] == "final.png"
    assert res["info"]["placeholder"] is False
    assert cap["payload"]["foto"] is not None  # foto materializada a ruta temporal


def test_componer_etiqueta_resuelta_en_binding(entorno, monkeypatch):
    # etiqueta="" => pleca omitida: el binding etiqueta_default viaja vacío.
    cap = _fake_render_node(monkeypatch)
    monkeypatch.setattr(media, "guardar_bytes_contenido", lambda datos, ext="png": "x.png")
    e.componer("", marca="unotv", formato="feed", titular="T", etiqueta="")
    assert cap["payload"]["bindings"]["etiqueta_default"] == ""


def test_componer_node_unico_motor_propaga_error(entorno, monkeypatch):
    # Node es el ÚNICO motor (sin fallback Pillow): si falla, `componer` lanza EstudioError.
    def _node_boom(payload, out):
        raise e.EstudioError("node no disponible")

    monkeypatch.setattr(e, "_correr_render_node", _node_boom)
    with pytest.raises(e.EstudioError):
        e.componer("", marca="unotv", formato="feed", titular="T")


def test_componer_logo_path_override_va_a_los_assets(entorno, monkeypatch):
    # `logo_path` (asset de marca mock/oficial) SUSTITUYE al logo del spec en el payload Node.
    cap = _fake_render_node(monkeypatch)
    monkeypatch.setattr(media, "guardar_bytes_contenido", lambda datos, ext="png": "x.png")
    e.componer("", marca="unotv", formato="feed", titular="T", logo_path="/tmp/logo-unotv.png")
    assert cap["payload"]["assets"]["logo"] == "/tmp/logo-unotv.png"


def test_componer_bytes_no_persiste(entorno, monkeypatch):
    # Render EFÍMERO: devuelve los bytes del PNG y NO escribe en el almacén (no llama a guardar).
    _fake_render_node(monkeypatch)  # _correr_render_node escribe b"png" en el temporal

    def _no_persiste(*a, **k):
        raise AssertionError("componer_bytes NO debe persistir en el almacén")

    monkeypatch.setattr(media, "guardar_bytes_contenido", _no_persiste)
    monkeypatch.setattr(media, "importar_imagen", _no_persiste)
    datos = e.componer_bytes("", marca="unotv", formato="feed", titular="DATO")
    assert datos == b"png"


# --------------------------------------------------------------------------- #
# Materializacion de assets con KEY de categoria (almacen por carpetas)        #
# Una key con `<categoria>/` se aplana al nombre temporal: el `/` NO crea una  #
# subcarpeta inexistente (que reventaria en FileNotFoundError -> 500).         #
# --------------------------------------------------------------------------- #


def test_nombre_local_plano_aplana_la_categoria():
    assert e._nombre_local_plano("logos/abc.png") == "logos-abc.png"
    assert e._nombre_local_plano("abc.png") == "abc.png"  # key plana: sin cambios


def test_materializar_logo_con_key_de_categoria_no_anida(tmp_path, monkeypatch):
    # La key `logos/<hash>.png` debe volcarse a un fichero PLANO dentro de la carpeta,
    # no a `asset-logos/<hash>.png` (subcarpeta que nadie crea -> FileNotFoundError).
    monkeypatch.setattr(media, "leer_media", lambda nombre: b"bytes-de-logo")
    ruta = e._materializar_logo("logos/deadbeef.png", tmp_path)
    from pathlib import Path

    p = Path(ruta)
    assert p.is_file()
    assert p.parent == tmp_path  # plano: vive directo en la carpeta, sin subdir
    assert p.read_bytes() == b"bytes-de-logo"


def test_renderizar_documento_bytes_con_logo_de_categoria(tmp_path, monkeypatch):
    # Una capa logo cuyo media_id trae prefijo de categoria: materializar el asset
    # lo aplana y el render de `/compuesta` devuelve los bytes sin FileNotFoundError.
    monkeypatch.setattr(media, "leer_media", lambda nombre: b"bytes-de-logo")
    monkeypatch.setattr(e, "_fuentes_extra_de_marca", lambda marca, carpeta: {})

    from pathlib import Path

    cap: dict[str, object] = {}

    def _fake(payload, out):
        # Comprobamos DENTRO del fake: `renderizar_documento_bytes` materializa en un
        # `TemporaryDirectory` que se borra al volver, asi que el asset solo existe aqui.
        ruta_asset = Path(payload["assets"]["fotos/deadbeef.png"])
        cap["asset_existe"] = ruta_asset.is_file()
        cap["asset_parent"] = ruta_asset.parent
        cap["tmp"] = out.parent
        out.write_bytes(b"png-doc")

    monkeypatch.setattr(e, "_correr_render_documento", _fake)

    doc = {
        "formato": {"w": 1080, "h": 1080},
        "capas": [
            {"tipo": "imagen", "x": 0, "y": 0, "w": 1080, "h": 1080,
             "objeto": "fotos/deadbeef.png", "es_foto": True},
        ],
    }
    # El `/` de la key se aplana en el tmp del documento (sin subcarpeta inexistente):
    # renderiza y devuelve los bytes.
    datos = e.renderizar_documento_bytes(doc, bindings={"copy_in": "HOLA"})
    assert datos == b"png-doc"
    assert cap["asset_existe"] is True
    # PLANO: el asset vive DIRECTO en el tmp del documento, no en un subdir `asset-fotos/`.
    assert cap["asset_parent"] == cap["tmp"]
