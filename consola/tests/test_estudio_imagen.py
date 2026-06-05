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
# Regresion: desde que la key trae `<categoria>/` el nombre temporal NO debe   #
# convertir ese `/` en una subcarpeta inexistente (FileNotFoundError -> 500).  #
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
    # Reproduce el 500 de `/compuesta`: una capa logo cuyo media_id trae prefijo de categoria.
    # Antes del fix, materializar el asset reventaba con FileNotFoundError. Ahora renderiza.
    monkeypatch.setattr(media, "leer_media", lambda nombre: b"bytes-de-logo")
    monkeypatch.setattr(e, "_fuentes_extra_de_marca", lambda marca, carpeta: {})

    cap: dict[str, object] = {}

    def _fake(payload, out):
        cap["payload"] = payload
        out.write_bytes(b"png-doc")

    monkeypatch.setattr(e, "_correr_render_documento", _fake)

    doc = {
        "formato": {"w": 1080, "h": 1080},
        "capas": [
            {"tipo": "imagen", "z": 0, "objeto": "fotos/deadbeef.png", "es_foto": True},
            {"tipo": "texto", "z": 1, "binding": "copy_in", "texto": ""},
        ],
    }
    datos = e.renderizar_documento_bytes(doc, bindings={"copy_in": "HOLA"})
    assert datos == b"png-doc"
    # El asset se materializo a una ruta PLANA (sin `/` extra tras el prefijo del tmp).
    ruta_asset = cap["payload"]["assets"]["fotos/deadbeef.png"]
    from pathlib import Path

    assert Path(ruta_asset).is_file()


# --------------------------------------------------------------------------- #
# generar_set_formatos (de un tiro: encaje determinista + marca por lienzo)   #
# --------------------------------------------------------------------------- #


def test_set_formatos_marca_desconocida(entorno):
    with pytest.raises(e.EstudioError):
        e.generar_set_formatos("foto.png", marca="nope")


def test_set_formatos_sin_imagen(entorno):
    with pytest.raises(e.EstudioError):
        e.generar_set_formatos("", marca="unotv")


def _mock_set(monkeypatch):
    """Mockea encaje (`editar`), marca (`componer`) y el asset de logo. Captura las llamadas."""
    llamadas = {"encaje": [], "componer": []}

    def _editar(imagen, op, params):
        assert op == "extender"
        llamadas["encaje"].append(params["formato"])
        return {"id": f"enc-{params['formato']}.png", "url": f"/api/media/enc-{params['formato']}.png"}

    def _componer(imagen, **kw):
        llamadas["componer"].append(kw["formato"])
        return {"id": f"marca-{kw['formato']}.png", "url": f"/api/media/marca-{kw['formato']}.png",
                "imagenes": [], "info": {}}

    monkeypatch.setattr(e, "editar", _editar)
    monkeypatch.setattr(e, "componer", _componer)
    monkeypatch.setattr(e, "_logo_de_marca", lambda marca: "/tmp/logo.png")
    return llamadas


def test_set_formatos_por_red_instagram(entorno, monkeypatch):
    """IG -> feed (marcado) + vertical (marcado); cada lienzo se encaja y luego se marca."""
    llamadas = _mock_set(monkeypatch)
    res = e.generar_set_formatos("foto.png", marca="unotv", red="instagram", titular="Gol")
    lienzos = [f["lienzo"] for f in res["formatos"]]
    assert lienzos == ["feed", "vertical"]
    assert llamadas["encaje"] == ["feed", "vertical"]  # encaja ambos
    assert llamadas["componer"] == ["feed", "vertical"]  # ambos llevan marca (no horizontal)
    assert all(f["marcado"] for f in res["formatos"])
    assert res["formatos"][0]["url"] == "/api/media/marca-feed.png"
    assert len(res["imagenes"]) == 2


def test_set_formatos_x_horizontal_con_placa(entorno, monkeypatch):
    """X -> horizontal: se encaja Y se compone la marca (el compositor por SPEC sí hace 16:9)."""
    llamadas = _mock_set(monkeypatch)
    res = e.generar_set_formatos("foto.png", marca="unotv", red="x")
    assert [f["lienzo"] for f in res["formatos"]] == ["horizontal"]
    assert llamadas["encaje"] == ["horizontal"]
    assert llamadas["componer"] == ["horizontal"]  # ahora SÍ se compone la placa 16:9
    assert res["formatos"][0]["marcado"] is True
    assert res["formatos"][0]["url"] == "/api/media/marca-horizontal.png"  # el encaje YA marcado


def test_set_formatos_sin_red_usa_lienzos_canonicos(entorno, monkeypatch):
    """Sin red, el set MAXIMO: todos los lienzos canonicos de la matriz."""
    from keni_consola import formatos_red

    _mock_set(monkeypatch)
    res = e.generar_set_formatos("foto.png", marca="claro-sports")
    assert {f["lienzo"] for f in res["formatos"]} == set(formatos_red.lienzos_canonicos())


def test_set_formatos_sin_aplicar_marca_solo_encaja(entorno, monkeypatch):
    """`aplicar_marca=False`: solo encaja a los lienzos, sin estampar marca (ni en feed/cuadrado)."""
    llamadas = _mock_set(monkeypatch)
    res = e.generar_set_formatos("foto.png", marca="unotv", red="instagram", aplicar_marca=False)
    assert llamadas["componer"] == []
    assert all(not f["marcado"] for f in res["formatos"])
