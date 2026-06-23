"""Bloqueo de imagen de STOCK sin licencia: nunca publicable hasta autorizar.

PURO (sin DB ni red): cubre el criterio único `dominio.licencia_imagen` y su efecto en la
derivación de "Falta imagen" (`dominio.piezas`), que es lo que mantiene la pieza fuera de
`programado`/`publicado` y con el badge activo mientras la foto sea stock no autorizada.
"""

from __future__ import annotations

from typing import Any

from keni_consola.dominio import licencia_imagen
from keni_consola.dominio.piezas import flags_falta_de_contenido, pieza_a_dict


def _pub(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "p1",
        "titulo": "T",
        "marca": "unotv",
        "red": "x",
        "contenido": "",
        "estado": "pendiente",
        "revision": "",
        "origen": "pipeline",
        "fecha_creacion": "",
        "fecha_actualizacion": "",
        "fecha_programada": "",
    }
    base.update(kw)
    return base


# --- es_stock_sin_autorizar (criterio único) -------------------------------- #


def test_stock_sin_autorizar_es_true():
    assert licencia_imagen.es_stock_sin_autorizar(
        {"imagen_origen": "stock", "imagen_autorizada": False}
    )


def test_stock_autorizado_no_bloquea():
    assert not licencia_imagen.es_stock_sin_autorizar(
        {"imagen_origen": "stock", "imagen_autorizada": True}
    )


def test_no_stock_nunca_bloquea():
    # Una imagen propia/IA/galería publica como siempre, autorizada o no.
    assert not licencia_imagen.es_stock_sin_autorizar(
        {"imagen_origen": "ia", "imagen_autorizada": False}
    )
    assert not licencia_imagen.es_stock_sin_autorizar(
        {"imagen_origen": "", "imagen_autorizada": False}
    )


def test_pieza_vacia_no_bloquea():
    assert not licencia_imagen.es_stock_sin_autorizar(None)
    assert not licencia_imagen.es_stock_sin_autorizar({})


def test_licenciada_nunca_bloquea_es_publicable():
    # Una foto LICENCIADA (AFP) tiene derechos: publicable directa, sin la autorización del stock.
    # Su licencia editorial EXIGE byline, así que arrastra autor/licencia (que AFP siempre da).
    licenciada = {
        "imagen_origen": licencia_imagen.ORIGEN_LICENCIADA,
        "imagen_autorizada": True,
        "imagen_autor": "Foto AFP",
        "imagen_licencia": "AFP",
        "imagen_proveedor": "afp",
    }
    assert not licencia_imagen.es_stock_sin_autorizar(licenciada)
    assert not licencia_imagen.bloquea_estado(licenciada, "programado")
    assert not licencia_imagen.bloquea_estado(licenciada, "publicado")


# --- bloquea_estado (solo programado/publicado) ----------------------------- #


def test_bloquea_solo_estados_publicables():
    sin_licencia = {"imagen_origen": "stock", "imagen_autorizada": False}
    assert licencia_imagen.bloquea_estado(sin_licencia, "programado")
    assert licencia_imagen.bloquea_estado(sin_licencia, "publicado")
    # Mover a borrador / en revisión NO se bloquea (la foto de stock vive ahí como ayuda visual).
    assert not licencia_imagen.bloquea_estado(sin_licencia, "borrador")
    assert not licencia_imagen.bloquea_estado(sin_licencia, "en_revision")
    assert not licencia_imagen.bloquea_estado(sin_licencia, None)


def test_no_bloquea_si_autorizada():
    # Autorizada Y de licencia libre (Pexels): supera el gate humano del stock Y el legal de la
    # licencia. Sin una licencia publicable, la autorización sola ya no basta (bloqueo determinista).
    ok = {"imagen_origen": "stock", "imagen_autorizada": True, "imagen_proveedor": "pexels"}
    assert not licencia_imagen.bloquea_estado(ok, "programado")
    assert not licencia_imagen.bloquea_estado(ok, "publicado")


# --- efecto en "Falta imagen" (dominio.piezas) ------------------------------ #


def test_stock_sin_autorizar_mantiene_falta_imagen():
    # Aunque la pieza tenga una `foto` adjunta, si es stock sin autorizar NO cuenta como imagen
    # real: sigue "Falta imagen" y no avanza/publica.
    pub = _pub(foto="stock123.jpg", imagen_origen="stock", imagen_autorizada=False)
    assert flags_falta_de_contenido(pub)["falta_imagen"] is True


def test_stock_autorizado_completa_la_imagen():
    pub = _pub(foto="stock123.jpg", imagen_origen="stock", imagen_autorizada=True)
    assert flags_falta_de_contenido(pub)["falta_imagen"] is False


# --- nivel_licencia (clasificador, espejo del front con BY-SA aparte) ------- #


def test_nivel_licencia_libre():
    assert licencia_imagen.nivel_licencia("CC0 1.0", "") == "libre"
    assert licencia_imagen.nivel_licencia("Public Domain Mark", "") == "libre"
    assert licencia_imagen.nivel_licencia("cualquier", "pexels") == "libre"
    assert licencia_imagen.nivel_licencia("cualquier", "pixabay") == "libre"
    assert licencia_imagen.nivel_licencia("NASA (dominio público)", "nasa") == "libre"


def test_nivel_licencia_atribucion_solo_by():
    assert licencia_imagen.nivel_licencia("CC BY 4.0", "openverse") == "atribucion"


def test_nivel_licencia_by_sa_es_compartir_igual():
    assert licencia_imagen.nivel_licencia("CC BY-SA 4.0", "wikimedia") == "compartir_igual"
    assert licencia_imagen.es_share_alike("CC BY-SA 4.0") is True


def test_nivel_licencia_nc_nd_y_desconocida_restringida():
    assert licencia_imagen.nivel_licencia("CC BY-NC 4.0", "") == "restringida"
    assert licencia_imagen.nivel_licencia("CC BY-ND 4.0", "") == "restringida"
    assert licencia_imagen.nivel_licencia("CC BY-NC-ND", "") == "restringida"
    assert licencia_imagen.nivel_licencia("Wikimedia Commons", "wikimedia") == "restringida"
    assert licencia_imagen.nivel_licencia("", "openverse") == "restringida"


# --- publicable_por_licencia (política de publicación) ----------------------- #


def test_publicable_cc0_y_by():
    assert licencia_imagen.publicable_por_licencia("CC0", "openverse", "stock")
    assert licencia_imagen.publicable_por_licencia("CC BY 4.0", "openverse", "stock")


def test_no_publicable_nc_nd_bysa_desconocida():
    assert not licencia_imagen.publicable_por_licencia("CC BY-SA 4.0", "wikimedia", "stock")
    assert not licencia_imagen.publicable_por_licencia("CC BY-NC", "openverse", "stock")
    assert not licencia_imagen.publicable_por_licencia("CC BY-ND", "openverse", "stock")
    assert not licencia_imagen.publicable_por_licencia("", "wikimedia", "stock")


def test_publicable_licenciada_y_propia():
    # Agencia AFP: publicable (su licencia editorial lo cubre), aunque la licencia textual no sea CC.
    assert licencia_imagen.publicable_por_licencia("AFP", "afp", "licenciada")
    # Foto propia (no stock): el gate de licencia CC no aplica.
    assert licencia_imagen.publicable_por_licencia("", "", "ia")
    assert licencia_imagen.publicable_por_licencia("", "", "")


# --- requiere_atribucion ---------------------------------------------------- #


def test_requiere_atribucion_by_y_licenciada():
    assert licencia_imagen.requiere_atribucion("CC BY 4.0", "openverse", "stock")
    assert licencia_imagen.requiere_atribucion("AFP", "afp", "licenciada")


def test_no_requiere_atribucion_libre_ni_propia():
    assert not licencia_imagen.requiere_atribucion("CC0", "openverse", "stock")
    assert not licencia_imagen.requiere_atribucion("Pexels License", "pexels", "stock")
    assert not licencia_imagen.requiere_atribucion("", "", "ia")


# --- credito_completo / linea_credito --------------------------------------- #


def test_credito_completo_con_autor_y_fuente():
    pieza = {
        "imagen_autor": "Foto AFP",
        "imagen_licencia": "AFP",
        "imagen_proveedor": "afp",
    }
    assert licencia_imagen.credito_completo(pieza)


def test_credito_incompleto_sin_autor():
    pieza = {"imagen_autor": "", "imagen_licencia": "CC BY 4.0", "imagen_proveedor": "openverse"}
    assert not licencia_imagen.credito_completo(pieza)


def test_linea_credito_formato_y_url():
    pieza = {
        "imagen_autor": "Jane Doe",
        "imagen_licencia": "CC BY 4.0",
        "imagen_proveedor": "openverse",
        "imagen_credito_url": "https://ov/obra",
    }
    linea = licencia_imagen.linea_credito(pieza)
    assert "Jane Doe" in linea
    assert "CC BY 4.0" in linea
    assert "Openverse" in linea
    assert "https://ov/obra" in linea


def test_linea_credito_vacia_sin_datos():
    assert licencia_imagen.linea_credito({}) == ""


# --- motivo_bloqueo / bloquea_estado (gates legales) ------------------------ #


def _foto_stock(**kw: Any) -> dict[str, Any]:
    base = {"imagen_origen": "stock", "imagen_autorizada": True}
    base.update(kw)
    return base


def test_motivo_cc0_publica_sin_credito():
    pieza = _foto_stock(imagen_licencia="CC0", imagen_proveedor="openverse")
    assert licencia_imagen.motivo_bloqueo(pieza, "programado") is None
    assert not licencia_imagen.bloquea_estado(pieza, "programado")


def test_motivo_by_sin_credito_bloquea():
    pieza = _foto_stock(imagen_licencia="CC BY 4.0", imagen_proveedor="openverse")
    assert licencia_imagen.motivo_bloqueo(pieza, "programado") == (
        licencia_imagen.MOTIVO_CREDITO_AUSENTE
    )


def test_motivo_by_con_credito_publica():
    pieza = _foto_stock(
        imagen_licencia="CC BY 4.0", imagen_proveedor="openverse", imagen_autor="Jane Doe"
    )
    assert licencia_imagen.motivo_bloqueo(pieza, "programado") is None


def test_motivo_by_sa_bloquea_por_licencia():
    pieza = _foto_stock(
        imagen_licencia="CC BY-SA 4.0", imagen_proveedor="wikimedia", imagen_autor="A"
    )
    assert licencia_imagen.motivo_bloqueo(pieza, "programado") == (
        licencia_imagen.MOTIVO_LICENCIA_NO_PUBLICABLE
    )


def test_motivo_nc_nd_bloquea_por_licencia():
    for lic in ("CC BY-NC 4.0", "CC BY-ND 4.0", "CC BY-NC-ND"):
        pieza = _foto_stock(imagen_licencia=lic, imagen_proveedor="openverse", imagen_autor="A")
        assert licencia_imagen.motivo_bloqueo(pieza, "programado") == (
            licencia_imagen.MOTIVO_LICENCIA_NO_PUBLICABLE
        )


def test_motivo_licenciada_con_credito_publica_sin_credito_bloquea():
    con = {
        "imagen_origen": "licenciada",
        "imagen_autorizada": True,
        "imagen_autor": "Foto AFP",
        "imagen_licencia": "AFP",
        "imagen_proveedor": "afp",
    }
    assert licencia_imagen.motivo_bloqueo(con, "programado") is None
    sin = {"imagen_origen": "licenciada", "imagen_autorizada": True, "imagen_proveedor": "afp"}
    assert licencia_imagen.motivo_bloqueo(sin, "programado") == (
        licencia_imagen.MOTIVO_CREDITO_AUSENTE
    )


def test_motivo_stock_sin_autorizar_igual_que_antes():
    pieza = {"imagen_origen": "stock", "imagen_autorizada": False, "imagen_licencia": "CC0"}
    assert licencia_imagen.motivo_bloqueo(pieza, "programado") == licencia_imagen.MOTIVO_BLOQUEO


# --- normalizar_campos_imagen (invariante de metadata de licencia) ---------- #


def test_normalizar_no_op_si_no_toca_imagen():
    previa = {"imagen_origen": "stock", "imagen_licencia": "CC BY-SA 4.0"}
    assert licencia_imagen.normalizar_campos_imagen({"estado": "programado"}, previa) == {
        "estado": "programado"
    }


def test_normalizar_composicion_preserva_metadata_stock():
    # COMPOSICIÓN: solo cambia `imagen` (placa), el origen sigue siendo stock -> NO toca metadata.
    previa = {
        "imagen_origen": "stock",
        "imagen_autorizada": True,
        "imagen_licencia": "CC BY 4.0",
        "imagen_autor": "Jane",
        "imagen_proveedor": "openverse",
        "imagen_credito_url": "https://ov/obra",
        "foto": "s.jpg",
    }
    campos = licencia_imagen.normalizar_campos_imagen({"imagen": "placa.png"}, previa)
    assert campos == {"imagen": "placa.png"}


def test_normalizar_composicion_preserva_metadata_licenciada():
    previa = {"imagen_origen": "licenciada", "imagen_autor": "Foto AFP", "imagen_licencia": "AFP"}
    campos = licencia_imagen.normalizar_campos_imagen({"imagen": "x.png"}, previa)
    assert campos == {"imagen": "x.png"}


def test_normalizar_reemplazo_propio_limpia_metadata():
    # REEMPLAZO: foto propia (origen '') -> limpia toda la metadata de licencia stale.
    previa = {
        "imagen_origen": "stock",
        "imagen_autorizada": True,
        "imagen_licencia": "CC BY-SA 4.0",
        "imagen_autor": "A",
        "imagen_proveedor": "wikimedia",
        "imagen_credito_url": "u",
        "foto": "s.jpg",
    }
    campos = licencia_imagen.normalizar_campos_imagen(
        {"foto": "propia.jpg", "imagen_origen": ""}, previa
    )
    assert campos["imagen_origen"] == ""
    assert campos["imagen_proveedor"] == ""
    assert campos["imagen_autor"] == ""
    assert campos["imagen_licencia"] == ""
    assert campos["imagen_credito_url"] == ""
    assert campos["imagen_autorizada"] is False
    assert campos["falta_imagen"] is False


def test_normalizar_ia_limpia_y_marca_imagen_presente():
    previa = {"imagen_origen": "stock", "imagen_licencia": "CC BY 4.0", "foto": "s.jpg"}
    campos = licencia_imagen.normalizar_campos_imagen(
        {"imagen": "arte.png", "imagen_origen": "ia"}, previa
    )
    assert campos["imagen_origen"] == "ia"
    assert campos["imagen_licencia"] == ""
    assert campos["imagen_autorizada"] is False
    assert campos["falta_imagen"] is False


def test_origen_propio_nunca_es_licencia():
    assert licencia_imagen.origen_propio("stock") == ""
    assert licencia_imagen.origen_propio("licenciada") == ""
    assert licencia_imagen.origen_propio("galeria") == "galeria"
    assert licencia_imagen.origen_propio("subida") == "subida"
    assert licencia_imagen.origen_propio(" IA ") == "ia"
    assert licencia_imagen.origen_propio(None) == ""
    assert licencia_imagen.origen_propio("cualquiercosa") == ""


def test_etapa_ia_de_stock_sin_autorizar_es_generando_arte():
    # La etapa serializada (la que prefiere el feed) mantiene "Falta imagen" para stock no autorizado.
    d = pieza_a_dict(
        _pub(
            estado="en_revision",
            contenido="copy #gol",
            copy_in="TITULAR",
            foto="stock123.jpg",
            imagen_origen="stock",
            imagen_autorizada=False,
        )
    )
    assert d["etapa_ia"] == "generando_arte"
    assert d["imagen_origen"] == "stock"
    assert d["imagen_autorizada"] is False
