"""Clasificación de la biblioteca de medios por ORIGEN real: backfill + reorg físico S3.

Cubre las migraciones de datos del tracking de origen de las fotos del PORTAL:
  - BACKFILL (`_migrar_backfill_origen_catalogo`): cruza el titular del catálogo con
    `noticias_items` para recuperar la `fuentes_rss` de la foto; si es externa la saca de la
    carpeta `portal`; los titulares ambiguos no se atribuyen.
  - REORG (`_migrar_reorg_originales_a_portal`): mueve el binario de `originales/` a `portal/`,
    reapunta TODAS las referencias (catálogo + piezas) y borra el viejo; idempotente.
  - CLASIFICACIÓN FINAL por tipo: `subida`→`subidas`, IA (`ia`) fuera de las 3 carpetas (`''`).
  - REORG subidas (`_migrar_reorg_subidas_a_subidas`): lleva las subidas de `artes/` a `subidas/`.
  - REORG externas (`_migrar_reorg_externas_a_fotos`): vacía la legacy `originales/` hacia `fotos/`
    sin arrastrar stragglers del portal.
  - REAPUNTE de DOCUMENTOS (`_migrar_reapuntar_media_documentos`): un reorg mueve el binario, así
    que el documento de la plantilla del estudio debe seguir apuntando a su logo —tanto durante el
    reorg como al reparar los documentos que quedaron con la key muerta—.

OFFLINE: backend de media en DISCO (la fixture `entorno` borra las S3_*); DB en el Postgres de
pruebas. Las migraciones de datos se invocan directamente con una conexión cruda.
"""

from __future__ import annotations

import json

from keni_consola import almacen_media, motor_db, repos
from keni_consola._db_core.migraciones_columnas import (
    _migrar_backfill_origen_catalogo,
    _migrar_fuente_subidas,
    _migrar_reapuntar_media_documentos,
    _migrar_reorg_externas_a_fotos,
    _migrar_reorg_originales_a_portal,
    _migrar_reorg_subidas_a_subidas,
)

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x01\x02\x03" * 4


def _aplicar(fn) -> None:
    """Corre una migración de datos con una conexión cruda y commitea (como el runner real)."""
    con = motor_db.conectar_cruda()
    try:
        fn(con)
        con.commit()
    finally:
        con.close()


def _item(fuente_id: str, titulo: str, clave: str) -> dict:
    return {"fuente_id": fuente_id, "titulo": titulo, "clave": clave}


# --------------------------------------------------------------------------- #
# Backfill: recupera el origen por titular y reclasifica las externas           #
# --------------------------------------------------------------------------- #


def test_backfill_marca_propia_conserva_portal_y_externa_sale(entorno):
    propia = repos.crear_fuente_rss("UnoTV", "https://unotv.com/rss", propia=True)
    externa = repos.crear_fuente_rss("Agencia X", "https://agx.com/rss", propia=False)
    repos.crear_noticias_items([
        _item(propia["id"], "Nota propia", "c1"),
        _item(externa["id"], "Nota externa", "c2"),
    ])
    # Dos fotos del portal sin origen conocido (catalogadas antes del tracking).
    cm_propia = repos.crear_media_catalogo(
        objeto="originales/propia.jpg", tipo="original", titulo="Nota propia", fuente="portal",
    )
    cm_externa = repos.crear_media_catalogo(
        objeto="originales/externa.jpg", tipo="original", titulo="Nota externa", fuente="portal",
    )

    _aplicar(_migrar_backfill_origen_catalogo)

    propia_post = repos.obtener_media_catalogo(cm_propia["id"])
    externa_post = repos.obtener_media_catalogo(cm_externa["id"])
    # Propia: origen recuperado, sigue en la carpeta `portal`.
    assert propia_post["origen_fuente_id"] == propia["id"]
    assert propia_post["fuente"] == "portal"
    # Externa: origen recuperado y SACADA de la carpeta `portal` (queda sin carpeta).
    assert externa_post["origen_fuente_id"] == externa["id"]
    assert externa_post["fuente"] == ""


def test_backfill_titulo_ambiguo_no_atribuye(entorno):
    a = repos.crear_fuente_rss("UnoTV", "https://unotv.com/rss", propia=True)
    b = repos.crear_fuente_rss("ClaroSports", "https://claro.com/rss", propia=True)
    # MISMO titular en dos fuentes distintas: no se puede atribuir el origen.
    repos.crear_noticias_items([
        _item(a["id"], "Titular repetido", "c1"),
        _item(b["id"], "Titular repetido", "c2"),
    ])
    cm = repos.crear_media_catalogo(
        objeto="originales/ambigua.jpg", tipo="original", titulo="Titular repetido", fuente="portal",
    )

    _aplicar(_migrar_backfill_origen_catalogo)

    post = repos.obtener_media_catalogo(cm["id"])
    assert post["origen_fuente_id"] == ""  # ambiguo -> no se atribuye
    assert post["fuente"] == "portal"  # se mantiene


def test_backfill_idempotente_no_pisa_origen_ya_puesto(entorno):
    propia = repos.crear_fuente_rss("UnoTV", "https://unotv.com/rss", propia=True)
    repos.crear_noticias_items([_item(propia["id"], "Nota", "c1")])
    cm = repos.crear_media_catalogo(
        objeto="originales/y.jpg", tipo="original", titulo="Nota", fuente="portal",
        origen_fuente_id="manual-ya-puesto",
    )

    _aplicar(_migrar_backfill_origen_catalogo)

    # Una fila con origen ya puesto NO se toca (la guarda `origen_fuente_id=''`).
    assert repos.obtener_media_catalogo(cm["id"])["origen_fuente_id"] == "manual-ya-puesto"


# --------------------------------------------------------------------------- #
# Reorg físico S3: originales/ -> portal/, reapunta refs, idempotente           #
# --------------------------------------------------------------------------- #


def _crear_pieza(con, *, id: str, **campos) -> None:
    cols = ("id", *campos.keys())
    marcadores = ", ".join("?" for _ in cols)
    con.execute(
        f"INSERT INTO pieza ({', '.join(cols)}) VALUES ({marcadores})",
        (id, *campos.values()),
    )


def test_reorg_mueve_objeto_y_reapunta_referencias(entorno):
    viejo = "originales/foto.jpg"
    nuevo = "portal/foto.jpg"
    almacen_media.guardar_objeto(viejo, _PNG, content_type="image/jpeg")
    cm = repos.crear_media_catalogo(
        objeto=viejo, tipo="original", titulo="Portada", fuente="portal", origen_fuente_id="f1",
    )
    # Las piezas exigen una publicacion padre (FK fk_pieza_publicacion_id).
    pub = repos.crear_publicacion(titulo="Portada")
    # Tres formas de referenciar la foto desde piezas: `foto`, collage `fotos`, slide `carrusel`.
    con = motor_db.conectar_cruda()
    try:
        _crear_pieza(con, id="p-foto", publicacion_id=pub["id"], foto=viejo, imagen=viejo)
        _crear_pieza(
            con, id="p-collage", publicacion_id=pub["id"],
            fotos=json.dumps([{"objeto": viejo, "foco": None, "zoom": 0}]),
        )
        _crear_pieza(
            con, id="p-carrusel", publicacion_id=pub["id"],
            carrusel=json.dumps([{"tipo": "imagen", "objeto": "artes/slide.png", "foto": viejo}]),
        )
        con.commit()
    finally:
        con.close()

    _aplicar(_migrar_reorg_originales_a_portal)

    # El catálogo apunta a la nueva key; el binario vive en `portal/` y el viejo se borró.
    assert repos.obtener_media_catalogo(cm["id"])["objeto"] == nuevo
    assert almacen_media.objeto_existe(nuevo)
    assert not almacen_media.objeto_existe(viejo)
    # TODAS las referencias de piezas reapuntadas (foto/imagen + JSON collage + JSON carrusel).
    con = motor_db.conectar_cruda()
    try:
        foto = con.execute("SELECT foto, imagen FROM pieza WHERE id = ?", ("p-foto",)).fetchone()
        collage = con.execute("SELECT fotos FROM pieza WHERE id = ?", ("p-collage",)).fetchone()
        carrusel = con.execute("SELECT carrusel FROM pieza WHERE id = ?", ("p-carrusel",)).fetchone()
    finally:
        con.close()
    assert foto["foto"] == nuevo and foto["imagen"] == nuevo
    assert json.loads(collage["fotos"])[0]["objeto"] == nuevo
    assert json.loads(carrusel["carrusel"])[0]["foto"] == nuevo


def test_reorg_idempotente(entorno):
    almacen_media.guardar_objeto("originales/z.jpg", _PNG, content_type="image/jpeg")
    cm = repos.crear_media_catalogo(
        objeto="originales/z.jpg", tipo="original", titulo="Z", fuente="portal",
    )

    _aplicar(_migrar_reorg_originales_a_portal)
    primera = repos.obtener_media_catalogo(cm["id"])["objeto"]
    # Segunda pasada: la fila ya está en `portal/`, no entra al SELECT -> no-op.
    _aplicar(_migrar_reorg_originales_a_portal)
    assert repos.obtener_media_catalogo(cm["id"])["objeto"] == primera == "portal/z.jpg"


def test_reorg_no_mueve_las_externas(entorno):
    """Una foto ya sacada de `portal` (externa, fuente='') NO se mueve a portal/."""
    almacen_media.guardar_objeto("originales/ext.jpg", _PNG, content_type="image/jpeg")
    cm = repos.crear_media_catalogo(
        objeto="originales/ext.jpg", tipo="original", titulo="Ext", fuente="",
    )

    _aplicar(_migrar_reorg_originales_a_portal)

    assert repos.obtener_media_catalogo(cm["id"])["objeto"] == "originales/ext.jpg"
    assert almacen_media.objeto_existe("originales/ext.jpg")


# --------------------------------------------------------------------------- #
# Clasificación final por tipo                                                  #
# --------------------------------------------------------------------------- #


def test_subida_se_clasifica_en_subidas_e_ia_queda_fuera(entorno):
    subida = repos.crear_media_catalogo(objeto="fotos/s.jpg", tipo="subida", titulo="Subida")
    ia = repos.crear_media_catalogo(objeto="generadas/g.png", tipo="ia", titulo="Generada")

    _aplicar(_migrar_fuente_subidas)

    # Una subida manual cae a la carpeta `subidas`; la foto de IA queda SIN carpeta de biblioteca.
    assert repos.obtener_media_catalogo(subida["id"])["fuente"] == "subidas"
    assert repos.obtener_media_catalogo(ia["id"])["fuente"] == ""


# --------------------------------------------------------------------------- #
# Reorg físico S3: subidas (artes/ -> subidas/) y externas (originales/ -> fotos/) #
# --------------------------------------------------------------------------- #


def test_reorg_subidas_mueve_de_artes_a_subidas(entorno):
    viejo = "artes/sub.jpg"
    nuevo = "subidas/sub.jpg"
    almacen_media.guardar_objeto(viejo, _PNG, content_type="image/jpeg")
    cm = repos.crear_media_catalogo(objeto=viejo, tipo="subida", titulo="Sub", fuente="subidas")
    pub = repos.crear_publicacion(titulo="Sub")
    con = motor_db.conectar_cruda()
    try:
        _crear_pieza(con, id="p-sub", publicacion_id=pub["id"], foto=viejo, imagen=viejo)
        con.commit()
    finally:
        con.close()

    _aplicar(_migrar_reorg_subidas_a_subidas)

    # El catálogo y la pieza apuntan a `subidas/`; el binario se movió y el viejo se borró.
    assert repos.obtener_media_catalogo(cm["id"])["objeto"] == nuevo
    assert almacen_media.objeto_existe(nuevo)
    assert not almacen_media.objeto_existe(viejo)
    con = motor_db.conectar_cruda()
    try:
        foto = con.execute("SELECT foto, imagen FROM pieza WHERE id = ?", ("p-sub",)).fetchone()
    finally:
        con.close()
    assert foto["foto"] == nuevo and foto["imagen"] == nuevo


def test_reorg_subidas_idempotente(entorno):
    almacen_media.guardar_objeto("subidas/ya.jpg", _PNG, content_type="image/jpeg")
    cm = repos.crear_media_catalogo(
        objeto="subidas/ya.jpg", tipo="subida", titulo="Ya", fuente="subidas",
    )
    _aplicar(_migrar_reorg_subidas_a_subidas)
    # Ya está en `subidas/`: no entra al SELECT -> no-op.
    assert repos.obtener_media_catalogo(cm["id"])["objeto"] == "subidas/ya.jpg"
    assert almacen_media.objeto_existe("subidas/ya.jpg")


def test_reorg_externas_vacia_originales_a_fotos(entorno):
    viejo = "originales/ext.jpg"
    nuevo = "fotos/ext.jpg"
    almacen_media.guardar_objeto(viejo, _PNG, content_type="image/jpeg")
    cm = repos.crear_media_catalogo(objeto=viejo, tipo="original", titulo="Ext", fuente="")
    pub = repos.crear_publicacion(titulo="Ext")
    con = motor_db.conectar_cruda()
    try:
        _crear_pieza(con, id="p-ext", publicacion_id=pub["id"], foto=viejo, imagen=viejo)
        con.commit()
    finally:
        con.close()

    _aplicar(_migrar_reorg_externas_a_fotos)

    # La externa pasa a `fotos/` con su pieza reapuntada; `originales/` queda vacía.
    assert repos.obtener_media_catalogo(cm["id"])["objeto"] == nuevo
    assert almacen_media.objeto_existe(nuevo)
    assert not almacen_media.objeto_existe(viejo)
    con = motor_db.conectar_cruda()
    try:
        foto = con.execute("SELECT foto, imagen FROM pieza WHERE id = ?", ("p-ext",)).fetchone()
    finally:
        con.close()
    assert foto["foto"] == nuevo and foto["imagen"] == nuevo


def test_reorg_externas_no_arrastra_straggler_del_portal(entorno):
    """Un portal aún en `originales/` (la 0057 no lo verificó) NO se mal-enruta a `fotos/`."""
    almacen_media.guardar_objeto("originales/p.jpg", _PNG, content_type="image/jpeg")
    cm = repos.crear_media_catalogo(
        objeto="originales/p.jpg", tipo="original", titulo="P", fuente="portal",
    )
    _aplicar(_migrar_reorg_externas_a_fotos)
    # Se queda en `originales/` (lo moverá la 0057 a `portal/`), no acaba en `fotos/`.
    assert repos.obtener_media_catalogo(cm["id"])["objeto"] == "originales/p.jpg"


# --------------------------------------------------------------------------- #
# Documentos del estudio: el reorg reapunta su logo y la reparación lo rescata   #
# --------------------------------------------------------------------------- #


def _doc_con_logo(clave: str) -> str:
    """Documento de capas mínimo con una capa imagen (el logo de marca) apuntando a `clave`."""
    return json.dumps({
        "version": 1,
        "marca": "unotv",
        "formato": {"w": 1080, "h": 1350},
        "capas": [{"id": "logo", "tipo": "imagen", "objeto": clave, "x": 0, "y": 0, "w": 200, "h": 80}],
    })


def test_reorg_subidas_reapunta_el_logo_de_la_plantilla(entorno):
    """Mover el binario reapunta el documento de la plantilla: la placa no pierde su logo."""
    viejo, nuevo = "artes/logo.png", "subidas/logo.png"
    almacen_media.guardar_objeto(viejo, _PNG, content_type="image/png")
    repos.crear_media_catalogo(objeto=viejo, tipo="subida", titulo="Logo", fuente="subidas")
    plantilla = repos.crear_plantilla_diseno(
        marca="unotv", nombre="Placa de marca", documento=_doc_con_logo(viejo), miniatura=viejo,
    )

    _aplicar(_migrar_reorg_subidas_a_subidas)

    post = repos.obtener_plantilla_diseno(plantilla["id"])
    assert nuevo in post["documento"] and viejo not in post["documento"]
    assert post["miniatura"] == nuevo


def test_reapunte_rescata_el_logo_muerto_de_un_documento(entorno):
    """Reparación: una key ya borrada se reapunta a su gemelo por nombre en otra carpeta."""
    almacen_media.guardar_objeto("subidas/logo.png", _PNG, content_type="image/png")
    plantilla = repos.crear_plantilla_diseno(
        marca="unotv", nombre="Placa", documento=_doc_con_logo("artes/logo.png"),
    )

    _aplicar(_migrar_reapuntar_media_documentos)

    assert "subidas/logo.png" in repos.obtener_plantilla_diseno(plantilla["id"])["documento"]


def test_reapunte_no_toca_lo_vivo_ni_lo_irrecuperable(entorno):
    """Solo se reapunta lo MUERTO con copia viva: ni la key viva ni la huérfana se tocan."""
    almacen_media.guardar_objeto("artes/vivo.png", _PNG, content_type="image/png")
    viva = repos.crear_plantilla_diseno(
        marca="unotv", nombre="Viva", documento=_doc_con_logo("artes/vivo.png"),
    )
    huerfana = repos.crear_plantilla_diseno(
        marca="unotv", nombre="Huérfana", documento=_doc_con_logo("artes/no-esta.png"),
    )

    _aplicar(_migrar_reapuntar_media_documentos)

    assert "artes/vivo.png" in repos.obtener_plantilla_diseno(viva["id"])["documento"]
    assert "artes/no-esta.png" in repos.obtener_plantilla_diseno(huerfana["id"])["documento"]
