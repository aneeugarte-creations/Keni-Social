"""Tests del CRUD del tablero de CONTENIDO unificado (`keni_consola.db`).

Modelo padre `contenido` (item del tablero: importante/evergreen/evento, o tarea libre)
+ hijos `contenido_plataforma` (una fila por red con estado y checklist). Probamos el
contrato basico de la persistencia: CRUD del padre y de las filas por plataforma, filtros
combinables, autodeduccion del checklist, cascada al borrar, preservacion de id al migrar,
y que `actualizado` se refresca. Reutiliza la fixture `entorno` (Postgres de pruebas o skip).
"""

from __future__ import annotations

from keni_consola import db, db_contenido


def test_crear_contenido_minimal(entorno):
    """Un item nace con defaults y `id` propio."""
    c = db.crear_contenido(flujo="importante", titulo="Sismo CDMX")
    assert c["id"]
    assert c["clase"] == "contenido"
    assert c["flujo"] == "importante"
    assert c["titulo"] == "Sismo CDMX"
    assert c["prioridad"] == "media"
    assert c["estado"] == "pendiente"
    assert c["creado"] and c["actualizado"]


def test_senal_viralidad_se_persiste_y_se_lee_como_int(entorno):
    """La señal del Radar (Fase 5) se guarda y vuelve como int; ausente => 0 (degrada)."""
    con = db.crear_contenido(flujo="importante", titulo="Trending", senal_viralidad=125_000)
    assert con["senal_viralidad"] == 125_000
    leido = db.obtener_contenido(con["id"])
    assert leido is not None
    assert leido["senal_viralidad"] == 125_000

    sin = db.crear_contenido(flujo="importante", titulo="Manual")
    assert sin["senal_viralidad"] == 0
    assert db.obtener_contenido(sin["id"])["senal_viralidad"] == 0


def test_senal_viralidad_invalida_o_negativa_cae_a_cero(entorno):
    """Un valor no entero o negativo se normaliza a 0 (defensivo ante el llamante)."""
    c = db.crear_contenido(titulo="x", senal_viralidad=-9)
    assert c["senal_viralidad"] == 0


def test_crear_tarea_libre(entorno):
    """Una tarea libre del equipo se guarda con clase='tarea' y sin plataformas."""
    t = db.crear_contenido(clase="tarea", titulo="Revisar relevo de la noche")
    assert t["clase"] == "tarea"
    assert db.listar_contenido_plataforma(t["id"]) == []


def test_listar_contenido_filtra_y_ordena_por_prioridad(entorno):
    """Filtra por flujo y ordena prioridad alta primero."""
    db.crear_contenido(flujo="evergreen", titulo="Everevergreen", prioridad="baja")
    db.crear_contenido(flujo="importante", titulo="Media", prioridad="media")
    db.crear_contenido(flujo="importante", titulo="Alta", prioridad="alta")

    importantes = db.listar_contenido(flujo="importante")
    assert [c["titulo"] for c in importantes] == ["Alta", "Media"]
    assert all(c["flujo"] == "importante" for c in importantes)


def test_plataforma_autodeduce_checklist_de_copy_e_imagen(entorno):
    """Si llega copy/imagen, el checklist 'falta_*' se apaga solo."""
    c = db.crear_contenido(flujo="evento", titulo="Partido")
    sin = db.crear_contenido_plataforma(contenido_id=c["id"], red="x")
    assert sin["falta_copy"] is True
    assert sin["falta_imagen"] is True
    con_copy = db.crear_contenido_plataforma(
        contenido_id=c["id"], red="instagram", copy="¡Gol!", imagen="foto.jpg"
    )
    assert con_copy["falta_copy"] is False
    assert con_copy["falta_imagen"] is False


def test_listar_plataformas_de_un_contenido(entorno):
    """Devuelve solo las filas del contenido pedido."""
    a = db.crear_contenido(titulo="A")
    b = db.crear_contenido(titulo="B")
    db.crear_contenido_plataforma(contenido_id=a["id"], red="x")
    db.crear_contenido_plataforma(contenido_id=a["id"], red="facebook")
    db.crear_contenido_plataforma(contenido_id=b["id"], red="tiktok")
    redes_a = {p["red"] for p in db.listar_contenido_plataforma(a["id"])}
    assert redes_a == {"x", "facebook"}


def test_actualizar_plataforma_estado_y_checklist(entorno):
    """Editar estado y checklist persiste y refresca `actualizado`."""
    c = db.crear_contenido(titulo="C")
    p = db.crear_contenido_plataforma(contenido_id=c["id"], red="x")
    actualizada = db.actualizar_contenido_plataforma(
        p["id"], {"estado": "aprobado", "falta_copy": False, "red": "hackeo"}
    )
    assert actualizada["estado"] == "aprobado"
    assert actualizada["falta_copy"] is False
    # `red` NO es editable (lista blanca): se ignora.
    assert actualizada["red"] == "x"
    assert actualizada["actualizado"] >= p["actualizado"]


def test_actualizar_contenido_ignora_columnas_no_editables(entorno):
    """`id`/`clase`/`autor_*`/`creado` no se editan; el resto si."""
    c = db.crear_contenido(titulo="Orig", autor={"id": "u1", "usuario": "ana"})
    upd = db.actualizar_contenido(
        c["id"], {"id": "otro", "clase": "tarea", "titulo": "Nuevo", "prioridad": "alta"}
    )
    assert upd["id"] == c["id"]
    assert upd["clase"] == "contenido"
    assert upd["titulo"] == "Nuevo"
    assert upd["prioridad"] == "alta"
    assert upd["autor_nombre"] == "ana"


def test_borrar_contenido_cascada_plataformas(entorno):
    """Borrar el padre borra sus filas por plataforma."""
    c = db.crear_contenido(titulo="Con hijos")
    p = db.crear_contenido_plataforma(contenido_id=c["id"], red="x")
    assert db.borrar_contenido(c["id"]) is True
    assert db.obtener_contenido(c["id"]) is None
    assert db.obtener_contenido_plataforma(p["id"]) is None


def test_crear_preserva_id_para_migracion(entorno):
    """Se puede forzar `id`/`creado` para PRESERVAR identidad de datos legados."""
    c = db.crear_contenido(id="legado-123", titulo="Migrado", creado="2025-01-01T00:00:00")
    assert c["id"] == "legado-123"
    assert c["creado"] == "2025-01-01T00:00:00"
    p = db.crear_contenido_plataforma(
        id="pub-legada", contenido_id=c["id"], red="instagram", estado="publicado"
    )
    assert p["id"] == "pub-legada"
    assert p["estado"] == "publicado"


def test_migracion_columnas_contenido_idempotente(entorno):
    """Listar varias veces no rompe (el esquema se crea/migra idempotente)."""
    db.listar_contenido()
    db.listar_contenido()
    c = db.crear_contenido(titulo="X")
    assert c["id"]


def test_borrar_publicacion_suelta_borra_el_padre(entorno):
    """Una publicacion SUELTA (padre 1:1) se borra arrastrando su `contenido` padre."""
    pub = db.crear_publicacion("unotv", "x", titulo="T", contenido="C")
    padre_id = db.obtener_contenido_plataforma(pub["id"])["contenido_id"]

    assert db.borrar_publicacion(pub["id"]) is True
    # La fila y su padre 1:1 desaparecen (no queda un contenido suelto y vacio).
    assert db.obtener_publicacion(pub["id"]) is None
    assert db.obtener_contenido(padre_id) is None


def test_borrar_publicacion_anidada_conserva_el_tema(entorno):
    """Un borrador ANIDADO bajo un tema con mas piezas: se borra SOLO su fila, no el tema."""
    tema = db.crear_contenido(flujo="importante", titulo="Tema con copy")
    # Dos filas por plataforma del MISMO tema (ambas son publicaciones, clase='contenido').
    db.crear_contenido_plataforma(contenido_id=tema["id"], red="x")
    borrador = db.crear_contenido_plataforma(
        contenido_id=tema["id"], red="instagram", copy="Hola"
    )

    assert db.borrar_publicacion(borrador["id"]) is True
    # El tema y su otra pieza SIGUEN; solo desaparece el borrador anidado.
    assert db.obtener_contenido(tema["id"]) is not None
    assert db.obtener_contenido_plataforma(borrador["id"]) is None
    restantes = db.listar_contenido_plataforma(tema["id"])
    assert [p["red"] for p in restantes] == ["x"]


def test_fila_a_contenido_plataforma_deriva_imagen_url():
    """`imagen` es el NOMBRE de archivo; el serializador añade `imagen_url` servible.

    Pura (sin DB): la UI (feed/preview) debe usar `imagen_url` en un <img>; `imagen`
    a secas no es navegable.
    """
    fila = {c: "" for c in db_contenido._COLS_CONTENIDO_PLATAFORMA}
    for b in db_contenido._BOOLS_CONTENIDO_PLATAFORMA:
        fila[b] = 0
    fila["estado"] = "pendiente"
    fila["imagen"] = "abc123.png"

    plat = db_contenido._fila_a_contenido_plataforma(fila)
    assert plat["imagen"] == "abc123.png"
    assert plat["imagen_url"] == "/api/media/abc123.png"

    fila["imagen"] = ""
    sin = db_contenido._fila_a_contenido_plataforma(fila)
    assert sin["imagen"] == ""
    assert sin["imagen_url"] == ""


def test_fila_a_contenido_plataforma_imagen_fuente_fallback():
    """Sin media adjunta pero con `imagen_fuente` (tipo 'fuente'), `imagen_url` la sirve.

    La imagen de la FUENTE original ya es navegable (URL externa): se expone tal cual en
    `imagen_url`. Si además hay media adjunta, la media manda sobre la fuente.
    """
    fila = {c: "" for c in db_contenido._COLS_CONTENIDO_PLATAFORMA}
    for b in db_contenido._BOOLS_CONTENIDO_PLATAFORMA:
        fila[b] = 0
    fila["estado"] = "pendiente"
    fila["imagen_fuente"] = "https://cdn.example/orig.jpg"

    plat = db_contenido._fila_a_contenido_plataforma(fila)
    assert plat["imagen_fuente"] == "https://cdn.example/orig.jpg"
    assert plat["imagen_url"] == "https://cdn.example/orig.jpg"

    # La media adjunta gana a la fuente.
    fila["imagen"] = "m.png"
    con_media = db_contenido._fila_a_contenido_plataforma(fila)
    assert con_media["imagen_url"] == "/api/media/m.png"


def test_listar_contenido_plataforma_filtra_por_marca(entorno):
    """El filtro `marca` (denormalizada) se aplica EN SQL: solo viajan las filas de esa
    marca."""
    a = db.crear_contenido(titulo="De UnoTV", marca="unotv")
    b = db.crear_contenido(titulo="De Claro", marca="claro-sports")
    db.crear_contenido_plataforma(contenido_id=a["id"], red="x")
    db.crear_contenido_plataforma(contenido_id=b["id"], red="x")

    solo_uno = db.listar_contenido_plataforma(marca="unotv")
    assert [p["contenido_id"] for p in solo_uno] == [a["id"]]
    # Sin filtro: todas (retrocompat).
    assert len(db.listar_contenido_plataforma()) == 2
    # Combinable con contenido_id.
    assert db.listar_contenido_plataforma(a["id"], marca="claro-sports") == []
