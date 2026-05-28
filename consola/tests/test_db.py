"""Tests del CRUD de tareas (`keni_consola.db`): dato OPERACIONAL.

Tras la ADR 0004 la operacional vive en POSTGRES. La fixture `entorno` apunta a un
Postgres de pruebas (o salta si no hay). Estos tests cubren el tablero compartido (#145
F5): responsable, enlace, ciclo de estado intermedio, filtro por proyecto, allowlist de
campos editables. El CRUD basico y la inyeccion SQL se prueban en `test_db_postgres.py`
(paridad backend); aqui evitamos duplicar y nos quedamos con los casos de tablero.
"""

from __future__ import annotations

from keni_consola import db


# --------------------------------------------------------------------------- #
# Esquema on-demand                                                            #
# --------------------------------------------------------------------------- #


def test_esquema_se_crea_on_demand(entorno):
    """La primera operacion crea el esquema en Postgres y devuelve vacio."""
    assert db.listar_tareas() == []


# --------------------------------------------------------------------------- #
# Tareas: tablero compartido (#145 F5) - responsable, enlace, estado, filtro    #
# --------------------------------------------------------------------------- #


def test_crear_tarea_con_responsable_y_enlace(entorno):
    """Una tarea nace con responsable (id+nombre) y enlace de accion; persisten."""
    t = db.crear_tarea(
        "proj1",
        "Asignada",
        responsable={"id": "u1", "usuario": "ana"},
        enlace="/asistente?skill=copy",
    )
    assert t["responsable_id"] == "u1"
    assert t["responsable_nombre"] == "ana"
    assert t["enlace"] == "/asistente?skill=copy"
    releida = db.obtener_tarea(t["id"])
    assert releida["responsable_nombre"] == "ana"
    assert releida["enlace"] == "/asistente?skill=copy"


def test_crear_tarea_sin_responsable_queda_sin_asignar(entorno):
    """Sin responsable/enlace, los campos quedan vacios (sin asignar)."""
    t = db.crear_tarea("proj1", "Suelta")
    assert t["responsable_id"] == ""
    assert t["responsable_nombre"] == ""
    assert t["enlace"] == ""


def test_actualizar_estado_en_curso(entorno):
    """El ciclo de vida admite el estado intermedio 'en_curso' (#145)."""
    assert "en_curso" in db.ESTADOS_TAREA
    t = db.crear_tarea("proj1", "Avanza")
    actualizada = db.actualizar_tarea(t["id"], {"estado": "en_curso"})
    assert actualizada["estado"] == "en_curso"


def test_actualizar_tarea_reasigna_responsable_y_enlace(entorno):
    """`actualizar_tarea` cambia responsable y enlace; vaciar limpia las columnas."""
    t = db.crear_tarea("proj1", "Reasignar")
    asignada = db.actualizar_tarea(
        t["id"],
        {"responsable_id": "u2", "responsable_nombre": "luis", "enlace": "/x"},
    )
    assert asignada["responsable_nombre"] == "luis"
    assert asignada["enlace"] == "/x"
    # Desasignar: ambos campos vuelven a vacio.
    limpia = db.actualizar_tarea(
        t["id"], {"responsable_id": "", "responsable_nombre": "", "enlace": ""}
    )
    assert limpia["responsable_id"] == ""
    assert limpia["responsable_nombre"] == ""
    assert limpia["enlace"] == ""


def test_actualizar_tarea_ignora_columnas_arbitrarias(entorno):
    """`actualizar_tarea` solo escribe campos de la allowlist (no columnas arbitrarias)."""
    t = db.crear_tarea("proj1", "Titulo original")
    # Intentar reescribir 'titulo'/'proyecto' (no editables) se ignora silenciosamente.
    db.actualizar_tarea(t["id"], {"titulo": "hackeado", "proyecto": "otro", "estado": "hecha"})
    releida = db.obtener_tarea(t["id"])
    assert releida["titulo"] == "Titulo original"
    assert releida["proyecto"] == "proj1"
    assert releida["estado"] == "hecha"  # el campo valido si se aplico


def test_actualizar_tarea_inexistente_devuelve_none(entorno):
    assert db.actualizar_tarea("noexiste", {"estado": "hecha"}) is None


def test_listar_tareas_filtra_por_proyecto(entorno):
    """`listar_tareas(proyecto_id)` acota al proyecto (acotado por marca/proyecto, #145)."""
    db.crear_tarea("proj1", "De A")
    db.crear_tarea("proj2", "De B")
    solo_a = db.listar_tareas("proj1")
    assert len(solo_a) == 1
    assert solo_a[0]["titulo"] == "De A"
    assert len(db.listar_tareas()) == 2


def test_listar_tareas_filtra_por_evento(entorno):
    """`listar_tareas(evento_id=...)` acota a las tareas atadas a un evento."""
    db.crear_tarea("p", "Libre", evento_id="")
    db.crear_tarea("p", "De evento A", evento_id="evA")
    db.crear_tarea("p", "Otra de A", evento_id="evA")
    db.crear_tarea("p", "De evento B", evento_id="evB")
    de_a = db.listar_tareas(evento_id="evA")
    assert sorted(t["titulo"] for t in de_a) == ["De evento A", "Otra de A"]
    de_b = db.listar_tareas(evento_id="evB")
    assert [t["titulo"] for t in de_b] == ["De evento B"]
    # Sin filtro: todas.
    assert len(db.listar_tareas()) == 4


def test_actualizar_tarea_evento_id(entorno):
    """`actualizar_tarea({'evento_id': ...})` ata/desata una tarea de un evento."""
    t = db.crear_tarea("p", "T")
    assert t["evento_id"] == ""
    actualizada = db.actualizar_tarea(t["id"], {"evento_id": "evX"})
    assert actualizada is not None
    assert actualizada["evento_id"] == "evX"
    # Desatar
    desatada = db.actualizar_tarea(t["id"], {"evento_id": ""})
    assert desatada is not None
    assert desatada["evento_id"] == ""


def test_migracion_columnas_tablero_en_bd_vieja(entorno):
    """Una BD con `tareas` SIN responsable/enlace se ALTERa (idempotente) y se lee vacia."""
    ruta = db.ruta_db()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(ruta))
    # Esquema previo a #145 (con autor de #130 pero sin responsable/enlace).
    con.execute(
        "CREATE TABLE tareas (id TEXT PRIMARY KEY, proyecto TEXT NOT NULL, titulo TEXT NOT NULL, "
        "detalle TEXT NOT NULL DEFAULT '', estado TEXT NOT NULL DEFAULT 'pendiente', "
        "fecha TEXT NOT NULL DEFAULT '', autor_id TEXT NOT NULL DEFAULT '', "
        "autor_nombre TEXT NOT NULL DEFAULT '')"
    )
    con.execute("INSERT INTO tareas (id, proyecto, titulo) VALUES ('vieja', 'p', 'Tarea vieja')")
    con.commit()
    con.close()
    # Cualquier operacion dispara la migracion idempotente.
    t = db.obtener_tarea("vieja")
    assert t is not None
    assert t["responsable_id"] == ""
    assert t["responsable_nombre"] == ""
    assert t["enlace"] == ""
    # Y la columna queda disponible para nuevas filas.
    nueva = db.crear_tarea("p", "Nueva", responsable={"id": "u1", "usuario": "ana"})
    assert nueva["responsable_nombre"] == "ana"


def test_migracion_columna_evento_id_en_bd_vieja(entorno):
    """Una BD con `tareas` SIN `evento_id` se ALTERa (idempotente) y se lee con ''."""
    ruta = db.ruta_db()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(ruta))
    # Esquema previo a la unificacion de pendientes (#145 F5 completo, sin evento_id).
    con.execute(
        "CREATE TABLE tareas (id TEXT PRIMARY KEY, proyecto TEXT NOT NULL, titulo TEXT NOT NULL, "
        "detalle TEXT NOT NULL DEFAULT '', estado TEXT NOT NULL DEFAULT 'pendiente', "
        "fecha TEXT NOT NULL DEFAULT '', autor_id TEXT NOT NULL DEFAULT '', "
        "autor_nombre TEXT NOT NULL DEFAULT '', responsable_id TEXT NOT NULL DEFAULT '', "
        "responsable_nombre TEXT NOT NULL DEFAULT '', enlace TEXT NOT NULL DEFAULT '')"
    )
    con.execute(
        "INSERT INTO tareas (id, proyecto, titulo) VALUES ('vieja', 'p', 'Tarea vieja')"
    )
    con.commit()
    con.close()
    # Cualquier operacion dispara la migracion idempotente.
    t = db.obtener_tarea("vieja")
    assert t is not None
    assert t["evento_id"] == ""
    # Y la columna queda disponible para nuevas filas.
    nueva = db.crear_tarea("p", "Nueva atada", evento_id="ev123")
    assert nueva["evento_id"] == "ev123"
    leida = db.obtener_tarea(nueva["id"])
    assert leida is not None
    assert leida["evento_id"] == "ev123"
    # Migracion idempotente: segunda llamada a una operacion no rompe.
    assert db.obtener_tarea("vieja") is not None


def test_migracion_columnas_eventos_rota_en_bd_vieja(entorno):
    """Un `rota_eventos` SIN cobertura/prioridad/cambiado/actualizado se ALTERa idempotente."""
    ruta = db.ruta_db()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(ruta))
    # Esquema previo a la ola B (solo los campos originales del evento).
    con.execute(
        "CREATE TABLE rota_eventos (id TEXT PRIMARY KEY, titulo TEXT NOT NULL, "
        "fecha TEXT NOT NULL DEFAULT '', hora TEXT NOT NULL DEFAULT '', "
        "contenido TEXT NOT NULL DEFAULT '', nota TEXT NOT NULL DEFAULT '', "
        "creado TEXT NOT NULL DEFAULT '')"
    )
    con.execute(
        "INSERT INTO rota_eventos (id, titulo, fecha) VALUES ('viejo', 'Partido', '2026-05-30')"
    )
    con.commit()
    con.close()
    # Cualquier operacion dispara la migracion idempotente; el evento legado queda con
    # los valores por defecto sensatos (transmision/media/sin reprogramar).
    ev = db.obtener_evento_rota("viejo")
    assert ev is not None
    assert ev["tipo_cobertura"] == "transmision"
    assert ev["prioridad"] == "media"
    assert ev["cambiado"] is False
    assert ev["actualizado"] == ""
    # Y las columnas quedan disponibles para nuevas filas.
    nuevo = db.crear_evento_rota("Nuevo", fecha="2026-05-30", tipo_cobertura="imagenes")
    assert nuevo["tipo_cobertura"] == "imagenes"


def test_sql_parametrizado_no_inyectable(entorno):
    """Un titulo con sintaxis SQL se guarda LITERAL (consultas parametrizadas)."""
    malicioso = "'; DROP TABLE tareas; --"
    t = db.crear_tarea("proj1", malicioso)
    # La tabla sigue viva y el titulo se guardo tal cual.
    assert db.obtener_tarea(t["id"])["titulo"] == malicioso
    assert len(db.listar_tareas()) == 1


# --------------------------------------------------------------------------- #
# Swaps de turno (#175): esquema idempotente + CRUD basico                      #
# --------------------------------------------------------------------------- #


def test_tabla_swaps_se_crea_on_demand(entorno):
    """La primera operacion crea `rota_swaps_turno` y devuelve vacio (no excepcion)."""
    assert db.listar_swaps_turno() == []


def test_migracion_columnas_swaps_idempotente(entorno):
    """Llamar a `_crear_esquema` varias veces no falla y no duplica columnas."""
    # Provoca dos creaciones de esquema (cada operacion abre/cierra y vuelve a crear).
    db.listar_swaps_turno()
    db.listar_swaps_turno()
    db.listar_swaps_turno()
    # Hasta aqui no hay excepcion; la idempotencia esta probada por la ausencia de fallo.
    assert db.listar_swaps_turno() == []


def test_crear_y_listar_swap_turno(entorno):
    """Crear un swap deja el estado en `propuesto` y se recupera por listar/obtener."""
    s = db.crear_swap_turno(
        "u-a",
        "u-b",
        "2026-05-25",
        "matutino",
        "2026-05-27",
        "vespertino",
        solicitante_nombre="ana",
        destinatario_nombre="beto",
        motivo="Boda de la prima",
    )
    assert s["estado"] == "propuesto"
    assert s["solicitante_nombre"] == "ana"
    assert s["destinatario_nombre"] == "beto"
    listado = db.listar_swaps_turno()
    assert any(x["id"] == s["id"] for x in listado)
    # Filtro por `mio_id` devuelve tanto si soy A como si soy B.
    assert any(x["id"] == s["id"] for x in db.listar_swaps_turno(mio_id="u-a"))
    assert any(x["id"] == s["id"] for x in db.listar_swaps_turno(mio_id="u-b"))
    assert db.listar_swaps_turno(mio_id="u-z") == []


def test_actualizar_swap_filtra_columnas_arbitrarias(entorno):
    """`actualizar_swap_turno` solo escribe la allowlist (no toca solicitante/franjas)."""
    s = db.crear_swap_turno(
        "u-a", "u-b", "2026-05-25", "matutino", "2026-05-27", "vespertino"
    )
    # Intentar reescribir el solicitante/franjas se ignora; el estado SI cambia.
    actualizado = db.actualizar_swap_turno(
        s["id"],
        {
            "solicitante_id": "hackeado",
            "fecha_a": "1900-01-01",
            "estado": "aceptado",
            "respuesta_destinatario": "Sí, te cubro.",
        },
    )
    assert actualizado["solicitante_id"] == "u-a"  # intacto
    assert actualizado["fecha_a"] == "2026-05-25"
    assert actualizado["estado"] == "aceptado"
    assert actualizado["respuesta_destinatario"] == "Sí, te cubro."
