"""Tests del CRUD del tablero de CONTENIDO unificado (`keni_consola.db`).

Modelo padre `contenido` (item del tablero: importante/evergreen/evento, o tarea libre)
+ hijos `pieza` (una fila por red con estado y checklist). Probamos el
contrato basico de la persistencia: CRUD del padre y de las filas por plataforma, filtros
combinables, autodeduccion del checklist, cascada al borrar, preservacion de id al migrar,
y que `actualizado` se refresca. Reutiliza la fixture `entorno` (Postgres de pruebas o skip).
"""

from __future__ import annotations

from keni_consola import db, repos
from keni_consola.db import publicacion as db_publicacion


def test_crear_contenido_minimal(entorno):
    """Un item nace con defaults y `id` propio."""
    c = db.crear_publicacion(flujo="importante", titulo="Sismo CDMX")
    assert c["id"]
    assert c["clase"] == "contenido"
    assert c["flujo"] == "importante"
    assert c["titulo"] == "Sismo CDMX"
    assert c["prioridad"] == "media"
    assert c["estado"] == "pendiente"
    assert c["creado"] and c["actualizado"]


def test_senal_viralidad_se_persiste_y_se_lee_como_int(entorno):
    """La señal del Radar (Fase 5) se guarda y vuelve como int; ausente => 0 (degrada)."""
    con = db.crear_publicacion(flujo="importante", titulo="Trending", senal_viralidad=125_000)
    assert con["senal_viralidad"] == 125_000
    leido = db.obtener_publicacion(con["id"])
    assert leido is not None
    assert leido["senal_viralidad"] == 125_000

    sin = db.crear_publicacion(flujo="importante", titulo="Manual")
    assert sin["senal_viralidad"] == 0
    assert db.obtener_publicacion(sin["id"])["senal_viralidad"] == 0


def test_senal_viralidad_invalida_o_negativa_cae_a_cero(entorno):
    """Un valor no entero o negativo se normaliza a 0 (defensivo ante el llamante)."""
    c = db.crear_publicacion(titulo="x", senal_viralidad=-9)
    assert c["senal_viralidad"] == 0


def test_crear_tarea_libre(entorno):
    """Una tarea libre del equipo se guarda con clase='tarea' y sin plataformas."""
    t = db.crear_publicacion(clase="tarea", titulo="Revisar relevo de la noche")
    assert t["clase"] == "tarea"
    assert db.listar_piezas_fila(t["id"]) == []


def test_listar_contenido_filtra_y_ordena_por_prioridad(entorno):
    """Filtra por flujo y ordena prioridad alta primero."""
    db.crear_publicacion(flujo="evergreen", titulo="Everevergreen", prioridad="baja")
    db.crear_publicacion(flujo="importante", titulo="Media", prioridad="media")
    db.crear_publicacion(flujo="importante", titulo="Alta", prioridad="alta")

    importantes = db.listar_publicacion(flujo="importante")
    assert [c["titulo"] for c in importantes] == ["Alta", "Media"]
    assert all(c["flujo"] == "importante" for c in importantes)


def test_listar_contenido_filtra_por_creado_desde(entorno):
    """`creado_desde` acota en SQL por `creado` (la jornada del día), sin traer el histórico."""
    db.crear_publicacion(titulo="Vieja", creado="2020-01-01T00:00:00")
    db.crear_publicacion(titulo="Hoy", creado="2030-06-01T10:00:00")

    recientes = db.listar_publicacion(creado_desde="2030-01-01T00:00:00")
    titulos = {c["titulo"] for c in recientes}
    assert "Hoy" in titulos
    assert "Vieja" not in titulos


def test_plataforma_autodeduce_checklist_de_copy_e_imagen(entorno):
    """Si llega copy/imagen, el checklist 'falta_*' se apaga solo."""
    c = db.crear_publicacion(flujo="evento", titulo="Partido")
    sin = db.crear_pieza_fila(publicacion_id=c["id"], red="x")
    assert sin["falta_copy"] is True
    assert sin["falta_imagen"] is True
    con_copy = db.crear_pieza_fila(
        publicacion_id=c["id"], red="instagram", copy="¡Gol!", imagen="foto.jpg"
    )
    assert con_copy["falta_copy"] is False
    assert con_copy["falta_imagen"] is False


def test_listar_plataformas_de_un_contenido(entorno):
    """Devuelve solo las filas del contenido pedido."""
    a = db.crear_publicacion(titulo="A")
    b = db.crear_publicacion(titulo="B")
    db.crear_pieza_fila(publicacion_id=a["id"], red="x")
    db.crear_pieza_fila(publicacion_id=a["id"], red="facebook")
    db.crear_pieza_fila(publicacion_id=b["id"], red="tiktok")
    redes_a = {p["red"] for p in db.listar_piezas_fila(a["id"])}
    assert redes_a == {"x", "facebook"}


def test_actualizar_plataforma_estado_y_checklist(entorno):
    """Editar estado y checklist persiste y refresca `actualizado`."""
    c = db.crear_publicacion(titulo="C")
    p = db.crear_pieza_fila(publicacion_id=c["id"], red="x")
    actualizada = db.actualizar_pieza_fila(
        p["id"], {"estado": "en_revision", "falta_copy": False, "red": "hackeo"}
    )
    assert actualizada["estado"] == "en_revision"
    assert actualizada["falta_copy"] is False
    # `red` NO es editable (lista blanca): se ignora.
    assert actualizada["red"] == "x"
    assert actualizada["actualizado"] >= p["actualizado"]


def test_actualizar_contenido_ignora_columnas_no_editables(entorno):
    """`id`/`clase`/`autor_*`/`creado` no se editan; el resto si."""
    c = db.crear_publicacion(titulo="Orig", autor={"id": "u1", "usuario": "ana"})
    upd = db.actualizar_publicacion(
        c["id"], {"id": "otro", "clase": "tarea", "titulo": "Nuevo", "prioridad": "alta"}
    )
    assert upd["id"] == c["id"]
    assert upd["clase"] == "contenido"
    assert upd["titulo"] == "Nuevo"
    assert upd["prioridad"] == "alta"
    assert upd["autor_nombre"] == "ana"


def test_borrar_contenido_cascada_plataformas(entorno):
    """Borrar el padre borra sus filas por plataforma."""
    c = db.crear_publicacion(titulo="Con hijos")
    p = db.crear_pieza_fila(publicacion_id=c["id"], red="x")
    assert db.borrar_publicacion(c["id"]) is True
    assert db.obtener_publicacion(c["id"]) is None
    assert db.obtener_pieza_fila(p["id"]) is None


def test_borrar_publicacion_desliga_noticias(entorno):
    """Borrar el tablero suelta el `publicacion_id` (sentinel) de las noticias que lo apuntaban."""
    pub = db.crear_publicacion(titulo="Tema desde noticia")
    repos.upsert_noticia_cluster({
        "id": "cl-pub", "titulo": "H", "resumen": "r", "marca": "unotv",
        "categoria": "mx", "geo": "MX", "clave": "t:cl-pub", "n_items": 1, "n_fuentes": 1,
        "idiomas": ["es"], "senal": 0, "score": 0.1, "breaking": 0,
        "primer_visto": "", "ultimo_visto": "", "estado": "usado",
        "publicacion_id": pub["id"],
    })
    repos.crear_noticias_items([
        {"fuente_id": "f", "titulo": "It", "clave": "k-pub", "cluster_id": "cl-pub",
         "publicacion_id": pub["id"], "capturado_en": "2020-01-01T00:00:00+00:00"},
    ])

    assert db.borrar_publicacion(pub["id"]) is True

    item = next(it for it in repos.listar_noticias_items(limite=500)[0] if it["clave"] == "k-pub")
    assert item["publicacion_id"] == ""  # no cuelga del tablero borrado
    assert repos.obtener_noticia_cluster("cl-pub")["publicacion_id"] == ""


def test_borrar_pieza_suelta_desliga_noticias(entorno):
    """El borrado del padre 1:1 via `borrar_pieza` también suelta las refs de noticias."""
    pub = db.crear_pieza("unotv", "x", titulo="T", contenido="C")
    padre_id = db.obtener_pieza_fila(pub["id"])["publicacion_id"]
    repos.crear_noticias_items([
        {"fuente_id": "f", "titulo": "It", "clave": "k-pieza", "cluster_id": "",
         "publicacion_id": padre_id, "capturado_en": "2020-01-01T00:00:00+00:00"},
    ])

    assert db.borrar_pieza(pub["id"]) is True

    item = next(it for it in repos.listar_noticias_items(limite=500)[0] if it["clave"] == "k-pieza")
    assert item["publicacion_id"] == ""


def test_crear_preserva_id_para_migracion(entorno):
    """Se puede forzar `id`/`creado` para PRESERVAR identidad de datos legados."""
    c = db.crear_publicacion(id="legado-123", titulo="Migrado", creado="2025-01-01T00:00:00")
    assert c["id"] == "legado-123"
    assert c["creado"] == "2025-01-01T00:00:00"
    p = db.crear_pieza_fila(
        id="pub-legada", publicacion_id=c["id"], red="instagram", estado="publicado"
    )
    assert p["id"] == "pub-legada"
    assert p["estado"] == "publicado"


def test_migracion_columnas_contenido_idempotente(entorno):
    """Listar varias veces no rompe (el esquema se crea/migra idempotente)."""
    db.listar_publicacion()
    db.listar_publicacion()
    c = db.crear_publicacion(titulo="X")
    assert c["id"]


def test_borrar_publicacion_suelta_borra_el_padre(entorno):
    """Una pieza SUELTA (padre 1:1) se borra arrastrando su `contenido` padre."""
    pub = db.crear_pieza("unotv", "x", titulo="T", contenido="C")
    padre_id = db.obtener_pieza_fila(pub["id"])["publicacion_id"]

    assert db.borrar_pieza(pub["id"]) is True
    # La fila y su padre 1:1 desaparecen (no queda un contenido suelto y vacio).
    assert db.obtener_pieza(pub["id"]) is None
    assert db.obtener_publicacion(padre_id) is None


def test_borrar_publicacion_anidada_conserva_el_tema(entorno):
    """Un borrador ANIDADO bajo un tema con mas piezas: se borra SOLO su fila, no el tema."""
    tema = db.crear_publicacion(flujo="importante", titulo="Tema con copy")
    # Dos filas por plataforma del MISMO tema (ambas son piezas, clase='contenido').
    db.crear_pieza_fila(publicacion_id=tema["id"], red="x")
    borrador = db.crear_pieza_fila(
        publicacion_id=tema["id"], red="instagram", copy="Hola"
    )

    assert db.borrar_pieza(borrador["id"]) is True
    # El tema y su otra pieza SIGUEN; solo desaparece el borrador anidado.
    assert db.obtener_publicacion(tema["id"]) is not None
    assert db.obtener_pieza_fila(borrador["id"]) is None
    restantes = db.listar_piezas_fila(tema["id"])
    assert [p["red"] for p in restantes] == ["x"]


def test_fila_a_contenido_plataforma_deriva_imagen_url():
    """`imagen` es el NOMBRE de archivo; el serializador añade `imagen_url` servible.

    Pura (sin DB): la UI (feed/preview) debe usar `imagen_url` en un <img>; `imagen`
    a secas no es navegable.
    """
    fila = {c: "" for c in db_publicacion._COLS_PIEZA}
    for b in db_publicacion._BOOLS_PIEZA:
        fila[b] = 0
    fila["estado"] = "pendiente"
    fila["imagen"] = "abc123.png"

    plat = db_publicacion._fila_a_pieza(fila)
    assert plat["imagen"] == "abc123.png"
    assert plat["imagen_url"] == "/api/media/abc123.png"

    fila["imagen"] = ""
    sin = db_publicacion._fila_a_pieza(fila)
    assert sin["imagen"] == ""
    assert sin["imagen_url"] == ""


def test_fila_a_contenido_plataforma_imagen_fuente_fallback():
    """Sin media adjunta pero con `imagen_fuente` (tipo 'fuente'), `imagen_url` la sirve.

    La imagen de la FUENTE original ya es navegable (URL externa): se expone tal cual en
    `imagen_url`. Si además hay media adjunta, la media manda sobre la fuente.
    """
    fila = {c: "" for c in db_publicacion._COLS_PIEZA}
    for b in db_publicacion._BOOLS_PIEZA:
        fila[b] = 0
    fila["estado"] = "pendiente"
    fila["imagen_fuente"] = "https://cdn.example/orig.jpg"

    plat = db_publicacion._fila_a_pieza(fila)
    assert plat["imagen_fuente"] == "https://cdn.example/orig.jpg"
    assert plat["imagen_url"] == "https://cdn.example/orig.jpg"

    # La media adjunta gana a la fuente.
    fila["imagen"] = "m.png"
    con_media = db_publicacion._fila_a_pieza(fila)
    assert con_media["imagen_url"] == "/api/media/m.png"


def test_listar_contenido_plataforma_filtra_por_marca(entorno):
    """El filtro `marca` (denormalizada) se aplica EN SQL: solo viajan las filas de esa
    marca."""
    a = db.crear_publicacion(titulo="De UnoTV", marca="unotv")
    b = db.crear_publicacion(titulo="De Claro", marca="claro-sports")
    db.crear_pieza_fila(publicacion_id=a["id"], red="x")
    db.crear_pieza_fila(publicacion_id=b["id"], red="x")

    solo_uno = db.listar_piezas_fila(marca="unotv")
    assert [p["publicacion_id"] for p in solo_uno] == [a["id"]]
    # Sin filtro: todas (retrocompat).
    assert len(db.listar_piezas_fila()) == 2
    # Combinable con publicacion_id.
    assert db.listar_piezas_fila(a["id"], marca="claro-sports") == []
