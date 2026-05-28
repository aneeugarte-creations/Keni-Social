"""Persistencia OPERACIONAL de la Consola Keni: Postgres (ADR 0004).

Cubre lo que NO es contenido editable a mano: las `tareas`, el apartado `comercial`
(seguimiento de piezas + su serie temporal de snapshots), la `rota` y, via `auth/`, los
`usuarios`/`sesiones`. El CONTENIDO editorial (publicaciones, plantillas, fuentes RSS,
hashtags, franjas, historial de skills) vive en ficheros YAML por marca (`ficheros.py`),
con un indice SQLite regenerable (`indice.py`). La fachada `repos.py` enruta cada cosa a
su almacen.

BACKEND (#130 / ADR 0004): UNICO, Postgres. `motor_db.conectar_cruda()` abre Postgres con
`DATABASE_URL` (OBLIGATORIA, local o hosted). Antes el backend se elegia segun esa var
(sin URL -> SQLite local); la ADR 0004 retira ese SQLite operacional para eliminar el drift
SQLite<->Postgres. La privacidad del perfil local se preserva con un Postgres LOCAL
(`deploy/dev/docker-compose.yml`); se pierde el "cero-config/offline por defecto".

El esquema se crea ON-DEMAND en la primera conexion (idempotente). Las funciones publicas y
la fachada `repos.py` son ESTABLES: ningun call site cambia (siguen usando `?`/`fila["col"]`,
que `motor_db` traduce a Postgres).

SEGURIDAD:
  - SIEMPRE consultas PARAMETRIZADAS (`?`), NUNCA f-strings con datos en el SQL. El
    `motor_db` traduce `?`->`%s` en Postgres sin tocar los datos.
  - Con un Postgres LOCAL ninguna fila sale de la maquina (privacidad preservada).

Tablas:
  - `tareas`(id, proyecto, titulo, detalle, estado, fecha, autor_id, autor_nombre,
    responsable_id, responsable_nombre, enlace)
    [tablero de pendientes compartido del equipo (#145): autor = quien la creo;
    responsable = a quien se le asigna; enlace = ruta/URL opcional para actuar]
  - `comercial_publicaciones`(id, url, titulo, marca, cliente, campania, red,
    metrica_objetivo, objetivo, estado, publicado, notas, aviso_en,
    fecha_creacion, fecha_actualizacion)
    [seguimiento de UNA publicacion comercial por su link; estado activa|pausada|cerrada]
  - `comercial_snapshots`(id, publicacion_id, ts, interacciones, alcance)
    [serie temporal de cada publicacion; UNIQUE(publicacion_id, ts)]
  - `usuarios`(id, usuario UNICO, rol, salt, hash, debe_cambiar_password,
    intentos_fallidos, bloqueo_hasta, creado, ultimo_acceso)
    [auth multiusuario (#130): el `salt`/`hash` son scrypt; NUNCA texto plano]
  - `sesiones`(token, usuario_id, creada, ultimo_uso, expira)
    [sesion server-side por cookie; el token es el de la cookie del navegador]

  La logica de auth (hashing, login, sesiones, bootstrap) vive en `auth/`, que
  reutiliza la conexion de este modulo (`conectar`). El esquema de `usuarios`/
  `sesiones` se crea aqui (on-demand, idempotente) para que exista por cualquier
  via de arranque.

Las funciones devuelven `dict`s simples (filas) o ids, sin acoplar la capa API al
backend. Cada operacion abre y cierra su propia conexion (mantenerlo simple evita estado
global y problemas de hilos con el `TestClient`; es una conexion por op).

CONCURRENCIA (servicio compartido, #130): la concurrencia multiusuario/multi-replica es
nativa de Postgres (el claim de la cola de jobs usa `FOR UPDATE SKIP LOCKED`); ese fue el
motivo de migrar y de retirar SQLite (ADR 0004).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

# Allowlists de dominio (neutras, sin acoplar al backend): viven en `estados.py`.
from . import motor_db
from .estados import (
    ESTADO_COMERCIAL_ACTIVA,
    ESTADO_ROTA_APROBADO,
    ESTADO_ROTA_PROPUESTO,
    ESTADO_SWAP_PROPUESTO,
    ESTADOS_COMERCIAL,
    ESTADOS_ROTA,
    ESTADOS_SWAP,
    ESTADOS_TAREA,
    FRANJA_DESCANSO,
    FRANJAS_TURNO,
    METRICAS_COMERCIAL,
    PRIORIDAD_EVENTO_DEFECTO,
    PRIORIDADES_EVENTO,
    TIPO_COBERTURA_TRANSMISION,
    TIPOS_AUSENCIA,
    TIPOS_COBERTURA,
)

__all__ = [
    "ESTADO_COMERCIAL_ACTIVA",
    "ESTADO_ROTA_APROBADO",
    "ESTADO_ROTA_PROPUESTO",
    "ESTADO_SWAP_PROPUESTO",
    "ESTADOS_COMERCIAL",
    "ESTADOS_ROTA",
    "ESTADOS_SWAP",
    "ESTADOS_TAREA",
    "FRANJAS_TURNO",
    "METRICAS_COMERCIAL",
    "PRIORIDADES_EVENTO",
    "TIPOS_COBERTURA",
    "TIPOS_AUSENCIA",
    "actualizar_estado_tarea",
    "actualizar_evento_rota",
    "actualizar_publicacion_comercial",
    "actualizar_ausencia_rota",
    "actualizar_tarea",
    "actualizar_turno_rota",
    "actualizar_turno_trabajo_rota",
    "aprobar_semana_horario_rota",
    "aprobar_semana_rota",
    "arrancar_persistencia",
    "borrar_ausencia_rota",
    "borrar_evento_rota",
    "borrar_publicacion_comercial",
    "borrar_swap_turno",
    "borrar_tarea",
    "borrar_turnos_semana_rota",
    "borrar_turnos_trabajo_semana_rota",
    "cancelar_job",
    "conectar",
    "crear_ausencia_rota",
    "crear_evento_rota",
    "crear_publicacion_comercial",
    "crear_swap_turno",
    "crear_tarea",
    "crear_turno_rota",
    "crear_turno_trabajo_rota",
    "encolar_job",
    "job_cancelado",
    "listar_ausencias_rota",
    "listar_eventos_rota",
    "listar_publicaciones_comerciales",
    "listar_snapshots_comerciales",
    "listar_swaps_turno",
    "listar_tareas",
    "listar_turnos_rota",
    "listar_turnos_trabajo_rota",
    "marcar_aviso_comercial",
    "obtener_ausencia_rota",
    "obtener_evento_rota",
    "obtener_publicacion_comercial",
    "obtener_swap_turno",
    "obtener_tarea",
    "obtener_turno_rota",
    "obtener_turno_trabajo_rota",
    "reclamar_job",
    "registrar_snapshot_comercial",
    "terminar_job",
    "ultimo_snapshot_comercial",
    "actualizar_swap_turno",
    "aplicar_swap_turno",
]


def _conectar() -> Any:
    """Abre la conexion a Postgres y crea el esquema on-demand.

    `motor_db.conectar_cruda()` abre Postgres con `DATABASE_URL` (obligatoria, ADR 0004) y
    devuelve una conexion que IMITA la API de `sqlite3.Connection` que usan los call sites
    (`execute(sql, params)` con `?`, filas por nombre, `rowcount`, commit/close).

    El esquema se crea aqui (idempotente) para que exista por cualquier via de arranque.
    """
    con = motor_db.conectar_cruda()
    _crear_esquema(con)
    return con


def conectar() -> Any:
    """Conexion publica al backend (mismo `_conectar`, expuesto para `auth/`).

    El esquema de `usuarios`/`sesiones` se crea aqui igual que el resto de tablas, de modo
    que `auth/` puede operar sin duplicar la creacion del esquema. Cada operacion
    abre/cierra su propia conexion.
    """
    return _conectar()


# --------------------------------------------------------------------------- #
# Arranque de la persistencia                                                  #
# --------------------------------------------------------------------------- #


def arrancar_persistencia() -> None:
    """Crea el esquema operacional on-demand en el arranque (idempotente).

    Abre Postgres (`DATABASE_URL` obligatoria, ADR 0004) y crea/migra el esquema, de modo
    que el back arranca con las tablas listas por cualquier via. Si falta `DATABASE_URL`,
    `motor_db.conectar_cruda()` lanza un `RuntimeError` accionable (no se traga: un back sin
    Postgres no debe servir). El antiguo guardia anti-orfanamiento SQLite->Postgres se
    retiro con SQLite (ADR 0004): ya no hay un origen local que orfanar.
    """
    _conectar().close()  # crea/migra el esquema y cierra


# DDL del esquema operacional, como sentencias INDIVIDUALES (no un script multi-sentencia
# `executescript`, exclusivo de sqlite3): se ejecutan una a una via `con.execute`. El DDL
# se mantiene portable (heredado de cuando coexistia SQLite): tipos `TEXT`/`INTEGER`,
# `PRIMARY KEY`, `UNIQUE`, `NOT NULL DEFAULT ''` y `CREATE [UNIQUE] INDEX IF NOT EXISTS` son
# todos validos en Postgres 16. Los ids son TEXT generados por la app (uuid), no
# autoincrementales: no hay `AUTOINCREMENT`/`SERIAL`.
_DDL_ESQUEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS tareas (
        id                  TEXT PRIMARY KEY,
        proyecto            TEXT NOT NULL,
        titulo              TEXT NOT NULL,
        detalle             TEXT NOT NULL DEFAULT '',
        estado              TEXT NOT NULL DEFAULT 'pendiente',
        fecha               TEXT NOT NULL DEFAULT '',
        autor_id            TEXT NOT NULL DEFAULT '',
        autor_nombre        TEXT NOT NULL DEFAULT '',
        responsable_id      TEXT NOT NULL DEFAULT '',
        responsable_nombre  TEXT NOT NULL DEFAULT '',
        enlace              TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS comercial_publicaciones (
        id                   TEXT PRIMARY KEY,
        url                  TEXT NOT NULL,
        titulo               TEXT NOT NULL DEFAULT '',
        marca                TEXT NOT NULL DEFAULT '',
        cliente              TEXT NOT NULL DEFAULT '',
        campania             TEXT NOT NULL DEFAULT '',
        red                  TEXT NOT NULL DEFAULT '',
        metrica_objetivo     TEXT NOT NULL DEFAULT 'interacciones',
        objetivo             INTEGER NOT NULL DEFAULT 0,
        estado               TEXT NOT NULL DEFAULT 'activa',
        publicado            TEXT NOT NULL DEFAULT '',
        notas                TEXT NOT NULL DEFAULT '',
        aviso_en             TEXT NOT NULL DEFAULT '',
        fecha_creacion       TEXT NOT NULL DEFAULT '',
        fecha_actualizacion  TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS comercial_snapshots (
        id              TEXT PRIMARY KEY,
        publicacion_id  TEXT NOT NULL,
        ts              TEXT NOT NULL,
        interacciones   INTEGER NOT NULL DEFAULT 0,
        alcance         INTEGER NOT NULL DEFAULT 0
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_comercial_snapshots_pub_ts "
    "ON comercial_snapshots (publicacion_id, ts)",
    "CREATE INDEX IF NOT EXISTS idx_comercial_snapshots_pub "
    "ON comercial_snapshots (publicacion_id)",
    """
    CREATE TABLE IF NOT EXISTS usuarios (
        id                     TEXT PRIMARY KEY,
        usuario                TEXT NOT NULL UNIQUE,
        rol                    TEXT NOT NULL DEFAULT 'editor',
        salt                   TEXT NOT NULL,
        hash                   TEXT NOT NULL,
        debe_cambiar_password  INTEGER NOT NULL DEFAULT 0,
        intentos_fallidos      INTEGER NOT NULL DEFAULT 0,
        bloqueo_hasta          TEXT NOT NULL DEFAULT '',
        creado                 TEXT NOT NULL DEFAULT '',
        ultimo_acceso          TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sesiones (
        token       TEXT PRIMARY KEY,
        usuario_id  TEXT NOT NULL,
        creada      TEXT NOT NULL,
        ultimo_uso  TEXT NOT NULL,
        expira      TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_sesiones_usuario ON sesiones (usuario_id)",
    # `tipo_cobertura`/`prioridad`/`cambiado`/`actualizado` (ola B): el evento ya no es
    # solo "que sacar"; lleva COMO se cubre (transmision|imagenes|no_cubrir), su PRIORIDAD
    # y si se REPROGRAMO (`cambiado`=1: hay que volver a avisar al equipo). `actualizado`
    # se refresca en cada edicion. Para bases NUEVAS se declaran aqui; las viejas las
    # migra `_migrar_columnas_eventos_rota` (idempotente, solo SQLite).
    """
    CREATE TABLE IF NOT EXISTS rota_eventos (
        id             TEXT PRIMARY KEY,
        titulo         TEXT NOT NULL,
        fecha          TEXT NOT NULL DEFAULT '',
        hora           TEXT NOT NULL DEFAULT '',
        contenido      TEXT NOT NULL DEFAULT '',
        nota           TEXT NOT NULL DEFAULT '',
        tipo_cobertura TEXT NOT NULL DEFAULT 'transmision',
        prioridad      TEXT NOT NULL DEFAULT 'media',
        cambiado       INTEGER NOT NULL DEFAULT 0,
        actualizado    TEXT NOT NULL DEFAULT '',
        creado         TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_rota_eventos_fecha ON rota_eventos (fecha)",
    """
    CREATE TABLE IF NOT EXISTS rota_turnos (
        id            TEXT PRIMARY KEY,
        semana        TEXT NOT NULL,
        evento_id     TEXT NOT NULL,
        miembro_id    TEXT NOT NULL DEFAULT '',
        miembro_nombre TEXT NOT NULL DEFAULT '',
        estado        TEXT NOT NULL DEFAULT 'propuesto',
        override      INTEGER NOT NULL DEFAULT 0,
        motivo        TEXT NOT NULL DEFAULT '',
        creado        TEXT NOT NULL DEFAULT '',
        actualizado   TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_rota_turnos_semana ON rota_turnos (semana)",
    "CREATE INDEX IF NOT EXISTS idx_rota_turnos_miembro ON rota_turnos (miembro_id)",
    # Horario de TRABAJO del equipo (F4 · #144, gestion de turnos): el reparto del turno
    # de cada persona por dia (matutino/vespertino/descanso), por semana, con estado
    # propuesto|aprobado y un `override` que rompe la rotacion de sabados. `nota_relevo` es
    # el reporte de fin de turno ("que esta pendiente para el siguiente turno"). Paralela a
    # `rota_turnos` (cobertura de eventos): no la sustituye, la complementa.
    """
    CREATE TABLE IF NOT EXISTS rota_turnos_trabajo (
        id             TEXT PRIMARY KEY,
        semana         TEXT NOT NULL,
        fecha          TEXT NOT NULL DEFAULT '',
        miembro_id     TEXT NOT NULL DEFAULT '',
        miembro_nombre TEXT NOT NULL DEFAULT '',
        franja         TEXT NOT NULL DEFAULT 'descanso',
        estado         TEXT NOT NULL DEFAULT 'propuesto',
        override       INTEGER NOT NULL DEFAULT 0,
        motivo         TEXT NOT NULL DEFAULT '',
        nota_relevo    TEXT NOT NULL DEFAULT '',
        creado         TEXT NOT NULL DEFAULT '',
        actualizado    TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_rota_turnos_trabajo_semana ON rota_turnos_trabajo (semana)",
    "CREATE INDEX IF NOT EXISTS idx_rota_turnos_trabajo_miembro "
    "ON rota_turnos_trabajo (miembro_id)",
    # Ausencias/vacaciones del horario (F4 · #144): un rango de fechas (inclusivo) en que un
    # miembro NO esta disponible. El proponedor del horario las RESPETA (excluye al miembro
    # esos dias). `tipo` es vacaciones|descanso|baja|otro.
    """
    CREATE TABLE IF NOT EXISTS rota_ausencias (
        id             TEXT PRIMARY KEY,
        miembro_id     TEXT NOT NULL DEFAULT '',
        miembro_nombre TEXT NOT NULL DEFAULT '',
        tipo           TEXT NOT NULL DEFAULT 'otro',
        desde          TEXT NOT NULL DEFAULT '',
        hasta          TEXT NOT NULL DEFAULT '',
        motivo         TEXT NOT NULL DEFAULT '',
        creado         TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_rota_ausencias_miembro ON rota_ausencias (miembro_id)",
    # Solicitudes de cambio de turno entre compañeros (#175): cuando un CM (A) quiere
    # canjear su turno por el de otro (B) por un asunto personal, crea una solicitud en
    # estado `propuesto`; B acepta/rechaza, y si acepta, Elias (admin) aprueba o rechaza.
    # Al aprobar se ejecuta el swap en `rota_turnos_trabajo` (intercambia miembro_id) y la
    # solicitud queda `aplicado`. Las ausencias de verdad (vacaciones/baja) siguen en SAP
    # y NO se gestionan aqui. Estados validos: ESTADOS_SWAP (ver `estados.py`).
    """
    CREATE TABLE IF NOT EXISTS rota_swaps_turno (
        id                       TEXT PRIMARY KEY,
        solicitante_id           TEXT NOT NULL,
        solicitante_nombre       TEXT NOT NULL DEFAULT '',
        destinatario_id          TEXT NOT NULL,
        destinatario_nombre      TEXT NOT NULL DEFAULT '',
        fecha_a                  TEXT NOT NULL,
        franja_a                 TEXT NOT NULL,
        fecha_b                  TEXT NOT NULL,
        franja_b                 TEXT NOT NULL,
        motivo                   TEXT NOT NULL DEFAULT '',
        estado                   TEXT NOT NULL DEFAULT 'propuesto',
        respuesta_destinatario   TEXT NOT NULL DEFAULT '',
        respuesta_admin          TEXT NOT NULL DEFAULT '',
        creado                   TEXT NOT NULL DEFAULT '',
        actualizado              TEXT NOT NULL DEFAULT '',
        decidido_destinatario    TEXT NOT NULL DEFAULT '',
        decidido_admin           TEXT NOT NULL DEFAULT '',
        aplicado                 TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_rota_swaps_solicitante ON rota_swaps_turno (solicitante_id)",
    "CREATE INDEX IF NOT EXISTS idx_rota_swaps_destinatario ON rota_swaps_turno (destinatario_id)",
    "CREATE INDEX IF NOT EXISTS idx_rota_swaps_estado ON rota_swaps_turno (estado)",
    "CREATE INDEX IF NOT EXISTS idx_rota_swaps_fechas ON rota_swaps_turno (fecha_a, fecha_b)",
    # Cola de jobs de generacion (#130 Fase 2 / ADR 0002 Fase B): el back ENCOLA y un
    # WORKER (in-proceso en local, servicio aparte en hosted) los CLAVA y ejecuta `claude
    # -p`. La fila es el "sobre" de despacho: `gen_id` es el registro de generacion
    # (fuente de verdad del sondeo), `spec` el JSON serializable para reconstruir el job
    # (prompt + post-procesado + cwd) en el worker, `estado` el del ciclo de la cola
    # (pendiente|reclamado|terminado), `claimed_at`/`worker` para depurar y reaprovechar
    # jobs huerfanos (un worker que muere a media ejecucion). `cancelado` lo marca el back
    # al cancelar: el worker lo lee y mata el arbol (cancelacion cross-proceso).
    """
    CREATE TABLE IF NOT EXISTS jobs (
        id          TEXT PRIMARY KEY,
        gen_id      TEXT NOT NULL,
        spec        TEXT NOT NULL,
        estado      TEXT NOT NULL DEFAULT 'pendiente',
        cancelado   INTEGER NOT NULL DEFAULT 0,
        worker      TEXT NOT NULL DEFAULT '',
        creado      TEXT NOT NULL DEFAULT '',
        claimed_at  TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_jobs_estado ON jobs (estado)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_gen ON jobs (gen_id)",
)


def _crear_esquema(con: Any) -> None:
    """Crea las tablas operacionales si no existen (idempotente).

    Ejecuta el DDL sentencia a sentencia y luego aplica las migraciones de columnas
    ampliadas (`tareas`, `rota_eventos`).

    Las migraciones de columnas son NECESARIAS, no opcionales: `CREATE TABLE IF NOT EXISTS`
    NO anade columnas a una tabla que YA existe, y el Postgres hosted PERSISTE entre
    despliegues. Una tabla creada por una version anterior se quedaba sin las columnas
    nuevas (fallo real: `rota_eventos` sin `tipo_cobertura` → 500 al leer el calendario).
    """
    for sentencia in _DDL_ESQUEMA:
        con.execute(sentencia)
    _migrar_columnas_tareas(con)
    _migrar_columnas_eventos_rota(con)
    _migrar_columnas_swaps(con)
    con.commit()


def _columnas_existentes(con: Any, tabla: str) -> set[str]:
    """Nombres de columnas que YA tiene `tabla` (Postgres, via `information_schema`).

    `tabla` es SIEMPRE un nombre interno de una allowlist (constantes del modulo, nunca
    entrada de usuario). El placeholder `?` lo traduce `motor_db` a `%s`.
    """
    filas = con.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
        (tabla,),
    ).fetchall()
    return {fila["column_name"] for fila in filas}


# Columnas que se anadieron a `tareas` despues de su esquema original. Una BD creada
# antes de cada ampliacion no las tiene; `ALTER TABLE ... ADD COLUMN DEFAULT ''` es
# retrocompatible (las filas viejas quedan con el campo vacio, sin reescribir nada).
#   - autor_id/autor_nombre: atribucion por usuario (#130 Fase 1).
#   - responsable_id/responsable_nombre/enlace: tablero compartido del equipo (#145, F5).
_COLUMNAS_TAREAS_AMPLIADAS: tuple[str, ...] = (
    "autor_id",
    "autor_nombre",
    "responsable_id",
    "responsable_nombre",
    "enlace",
)


def _migrar_columnas_tareas(con: Any) -> None:
    """Anade a `tareas` las columnas ampliadas que una BD vieja no tuviera (idempotente).

    El `CREATE TABLE IF NOT EXISTS` ya las declara para bases NUEVAS, pero una base creada
    antes de cada ampliacion no las tiene. Recorre `_COLUMNAS_TAREAS_AMPLIADAS` y anade solo
    la que falte, con `DEFAULT ''`: las tareas existentes quedan con el campo vacio (autor /
    responsable "desconocido", sin enlace) y no se pierde ni reescribe nada. El Postgres
    hosted persiste entre despliegues, asi que tambien puede ir atrasado (ver `_crear_esquema`).
    """
    columnas = _columnas_existentes(con, "tareas")
    for columna in _COLUMNAS_TAREAS_AMPLIADAS:
        if columna not in columnas:
            con.execute(f"ALTER TABLE tareas ADD COLUMN {columna} TEXT NOT NULL DEFAULT ''")


# Columnas que se anadieron a `rota_eventos` despues de su esquema original (ola B, #144).
# Una BD creada antes no las tiene; `ALTER TABLE ... ADD COLUMN ... DEFAULT ...` es
# retrocompatible (las filas viejas quedan con el valor por defecto, sin reescribir nada):
#   - tipo_cobertura: transmision|imagenes|no_cubrir; legado -> "transmision" (sigue cubierto).
#   - prioridad: alta|media|baja; legado -> "media".
#   - cambiado: 0/1, "se reprogramo, hay que avisar"; legado -> 0 (sin reprogramar).
#   - actualizado: timestamp de la ultima edicion; legado -> "" (nunca editado tras migrar).
# Cada par es (columna, fragmento de tipo/DEFAULT) para emitir el ALTER correcto.
_COLUMNAS_EVENTO_ROTA_AMPLIADAS: tuple[tuple[str, str], ...] = (
    ("tipo_cobertura", "TEXT NOT NULL DEFAULT 'transmision'"),
    ("prioridad", "TEXT NOT NULL DEFAULT 'media'"),
    ("cambiado", "INTEGER NOT NULL DEFAULT 0"),
    ("actualizado", "TEXT NOT NULL DEFAULT ''"),
)


def _migrar_columnas_eventos_rota(con: Any) -> None:
    """Anade a `rota_eventos` las columnas de la ola B que una BD vieja no tuviera (idempotente).

    El `CREATE TABLE IF NOT EXISTS` ya las declara para bases NUEVAS, pero una base creada
    antes de la ampliacion (cobertura/prioridad/reprogramaciones) no las tiene. Recorre
    `_COLUMNAS_EVENTO_ROTA_AMPLIADAS` y anade solo la que falte con su DEFAULT: los eventos
    existentes quedan como `transmision`/`media`/sin reprogramar y no se pierde nada. El
    Postgres hosted persiste entre despliegues; era el origen del 500 del calendario.
    """
    columnas = _columnas_existentes(con, "rota_eventos")
    for columna, tipo in _COLUMNAS_EVENTO_ROTA_AMPLIADAS:
        if columna not in columnas:
            con.execute(f"ALTER TABLE rota_eventos ADD COLUMN {columna} {tipo}")


# Columnas que se podrian anadir a `rota_swaps_turno` en futuras ampliaciones. Hoy esta
# tupla esta VACIA: la primera version del swap nace ya con todo el esquema declarado en
# el `CREATE TABLE IF NOT EXISTS` (sin previas en produccion). Se conserva el hook por
# coherencia con el patron de `_migrar_columnas_*` (tareas, eventos): cuando aparezca una
# columna nueva, se agrega aqui como (col, tipo) y este migrador la pondra a las bases
# viejas sin reescribir nada. Idempotente.
_COLUMNAS_SWAP_AMPLIADAS: tuple[tuple[str, str], ...] = ()


def _migrar_columnas_swaps(con: Any) -> None:
    """Anade a `rota_swaps_turno` las columnas que una BD vieja no tuviera (idempotente).

    Hoy es no-op (tupla vacia): la tabla nace completa. Cuando se amplie, basta con
    declarar la columna en el `CREATE TABLE` (para bases NUEVAS) y anadir `(col, tipo)` a
    `_COLUMNAS_SWAP_AMPLIADAS` (para que las bases ANTIGUAS la reciban via ALTER). Mismo
    patron que `_migrar_columnas_tareas` / `_migrar_columnas_eventos_rota`.
    """
    if not _COLUMNAS_SWAP_AMPLIADAS:
        return
    columnas = _columnas_existentes(con, "rota_swaps_turno")
    for columna, tipo in _COLUMNAS_SWAP_AMPLIADAS:
        if columna not in columnas:
            con.execute(f"ALTER TABLE rota_swaps_turno ADD COLUMN {columna} {tipo}")


# --------------------------------------------------------------------------- #
# Tareas                                                                       #
# --------------------------------------------------------------------------- #


# Columnas de `tareas` en el SELECT (atribucion por usuario #130; responsable/enlace #145).
_SELECT_TAREA = (
    "SELECT id, proyecto, titulo, detalle, estado, fecha, autor_id, autor_nombre, "
    "responsable_id, responsable_nombre, enlace FROM tareas"
)


def _fila_a_tarea(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `tareas` en un dict simple.

    `autor_id`/`autor_nombre` (atribucion por usuario, #130 Fase 1) y
    `responsable_id`/`responsable_nombre`/`enlace` (tablero compartido, #145 F5) salen ""
    en tareas legadas / anonimas / sin asignar; la UI las muestra como "desconocido" / "sin
    asignar".
    """
    return {
        "id": fila["id"],
        "proyecto": fila["proyecto"],
        "titulo": fila["titulo"],
        "detalle": fila["detalle"],
        "estado": fila["estado"],
        "fecha": fila["fecha"],
        "autor_id": fila["autor_id"] or "",
        "autor_nombre": fila["autor_nombre"] or "",
        "responsable_id": fila["responsable_id"] or "",
        "responsable_nombre": fila["responsable_nombre"] or "",
        "enlace": fila["enlace"] or "",
    }


def listar_tareas(proyecto_id: str | None = None) -> list[dict[str, Any]]:
    """Tareas del tablero compartido, mas recientes primero (por fecha y luego id).

    Con `proyecto_id` filtra a un solo proyecto/marca (acotado por proyecto, #145 F5); sin
    el, devuelve el tablero completo del equipo.
    """
    con = _conectar()
    try:
        if proyecto_id:
            filas = con.execute(
                f"{_SELECT_TAREA} WHERE proyecto = ? ORDER BY fecha DESC, id DESC",
                (proyecto_id,),
            ).fetchall()
        else:
            filas = con.execute(
                f"{_SELECT_TAREA} ORDER BY fecha DESC, id DESC"
            ).fetchall()
    finally:
        con.close()
    return [_fila_a_tarea(f) for f in filas]


def crear_tarea(
    proyecto_id: str,
    titulo: str,
    detalle: str = "",
    *,
    autor: dict[str, str] | None = None,
    responsable: dict[str, str] | None = None,
    enlace: str = "",
) -> dict[str, Any]:
    """Inserta una tarea nueva y la devuelve. NO valida el proyecto (lo hace la API).

    `autor` (atribucion por usuario, #130 Fase 1) es `{"id", "usuario"}` o `None`
    (creacion anonima / por token de mantenimiento); se persiste vacio en ese caso.

    `responsable` (tablero compartido, #145 F5) es `{"id", "usuario"}` o `None` (sin
    asignar). `enlace` es una ruta/URL opcional para actuar sobre la tarea.
    """
    autor = autor or {}
    responsable = responsable or {}
    tarea = {
        "id": uuid.uuid4().hex[:12],
        "proyecto": proyecto_id,
        "titulo": titulo,
        "detalle": detalle,
        "estado": "pendiente",
        "fecha": date.today().isoformat(),
        "autor_id": autor.get("id", "") or "",
        "autor_nombre": autor.get("usuario", "") or "",
        "responsable_id": responsable.get("id", "") or "",
        "responsable_nombre": responsable.get("usuario", "") or "",
        "enlace": enlace or "",
    }
    con = _conectar()
    try:
        con.execute(
            "INSERT INTO tareas (id, proyecto, titulo, detalle, estado, fecha, "
            "autor_id, autor_nombre, responsable_id, responsable_nombre, enlace) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                tarea["id"],
                tarea["proyecto"],
                tarea["titulo"],
                tarea["detalle"],
                tarea["estado"],
                tarea["fecha"],
                tarea["autor_id"],
                tarea["autor_nombre"],
                tarea["responsable_id"],
                tarea["responsable_nombre"],
                tarea["enlace"],
            ),
        )
        con.commit()
    finally:
        con.close()
    return tarea


def obtener_tarea(tarea_id: str) -> dict[str, Any] | None:
    """Una tarea por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_TAREA} WHERE id = ?",
            (tarea_id,),
        ).fetchone()
    finally:
        con.close()
    return _fila_a_tarea(fila) if fila is not None else None


# Campos de `tareas` editables via `actualizar_tarea` (tablero compartido, #145 F5).
# El `responsable` se actualiza como par id+nombre desde la API; aqui se mapean a sus dos
# columnas. La validacion (estado valido, responsable real) es de la capa API.
_CAMPOS_EDITABLES_TAREA: tuple[str, ...] = (
    "estado",
    "responsable_id",
    "responsable_nombre",
    "enlace",
)


def actualizar_tarea(tarea_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    """Actualiza campos de una tarea (estado/responsable/enlace) y la devuelve.

    `campos` se filtra a `_CAMPOS_EDITABLES_TAREA` (defensa en profundidad: nunca se
    escriben columnas arbitrarias). Devuelve la tarea actualizada, o None si no existe o no
    hay nada que actualizar tras el filtro. La validacion de valores la hace la capa API.
    """
    editables = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_TAREA}
    if not editables:
        return obtener_tarea(tarea_id)
    asignaciones = ", ".join(f"{col} = ?" for col in editables)
    valores = [*editables.values(), tarea_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE tareas SET {asignaciones} WHERE id = ?",  # noqa: S608 -- columnas de allowlist
            valores,
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            f"{_SELECT_TAREA} WHERE id = ?",
            (tarea_id,),
        ).fetchone()
    finally:
        con.close()
    return _fila_a_tarea(fila) if fila is not None else None


def actualizar_estado_tarea(tarea_id: str, estado: str) -> dict[str, Any] | None:
    """Cambia el estado de una tarea; devuelve la tarea actualizada (None si no existe).

    Atajo historico sobre `actualizar_tarea` (se conserva para no romper a quien solo cambia
    el estado).
    """
    return actualizar_tarea(tarea_id, {"estado": estado})


def borrar_tarea(tarea_id: str) -> bool:
    """Borra una tarea; True si existia, False si no."""
    con = _conectar()
    try:
        cur = con.execute("DELETE FROM tareas WHERE id = ?", (tarea_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# Publicaciones comerciales (seguimiento de UNA pieza por su link)             #
# --------------------------------------------------------------------------- #
#
# A diferencia de las `publicaciones` editoriales (que viven en YAML), esto monitoriza
# el rendimiento de una pieza ya publicada: se registra su link, se le toman snapshots
# periodicos de interacciones/alcance (serie temporal) y, al llegar el KPI, se arma su
# reporte. Es dato OPERACIONAL append-only: no encaja como un fichero por entidad, por
# eso vive en SQLite.

# Columnas de `comercial_publicaciones` en orden de declaracion (reusadas en SELECT/INSERT).
_COLS_COMERCIAL = (
    "id",
    "url",
    "titulo",
    "marca",
    "cliente",
    "campania",
    "red",
    "metrica_objetivo",
    "objetivo",
    "estado",
    "publicado",
    "notas",
    "aviso_en",
    "fecha_creacion",
    "fecha_actualizacion",
)
_SELECT_COMERCIAL = f"SELECT {', '.join(_COLS_COMERCIAL)} FROM comercial_publicaciones"

# Campos que la edicion parcial puede tocar (url y fechas/aviso son inmutables desde la API).
_CAMPOS_EDITABLES_COMERCIAL = (
    "titulo",
    "marca",
    "cliente",
    "campania",
    "red",
    "metrica_objetivo",
    "objetivo",
    "estado",
    "publicado",
    "notas",
)


def _fila_a_comercial(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `comercial_publicaciones` en un dict (`objetivo` como int)."""
    pub = {col: fila[col] for col in _COLS_COMERCIAL}
    pub["objetivo"] = int(fila["objetivo"] or 0)
    return pub


def crear_publicacion_comercial(
    url: str,
    *,
    titulo: str = "",
    marca: str = "",
    cliente: str = "",
    campania: str = "",
    red: str = "",
    metrica_objetivo: str = "interacciones",
    objetivo: int = 0,
    estado: str = "activa",
    publicado: str = "",
    notas: str = "",
) -> dict[str, Any]:
    """Inserta una publicacion comercial a monitorear y la devuelve.

    NO valida marca/red/estado/metrica (lo hace la API contra sus allowlists). `aviso_en`
    nace vacio; se rellena la primera vez que el valor supera el objetivo.
    """
    ahora = datetime.now().isoformat(timespec="seconds")
    fila = {
        "id": uuid.uuid4().hex[:12],
        "url": url,
        "titulo": titulo,
        "marca": marca,
        "cliente": cliente,
        "campania": campania,
        "red": red,
        "metrica_objetivo": metrica_objetivo or "interacciones",
        "objetivo": int(objetivo or 0),
        "estado": estado or "activa",
        "publicado": publicado or date.today().isoformat(),
        "notas": notas,
        "aviso_en": "",
        "fecha_creacion": ahora,
        "fecha_actualizacion": ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_COMERCIAL)
        con.execute(
            f"INSERT INTO comercial_publicaciones ({', '.join(_COLS_COMERCIAL)}) "
            f"VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_COMERCIAL),
        )
        con.commit()
    finally:
        con.close()
    return fila


def listar_publicaciones_comerciales(
    estado: str | None = None,
    cliente: str | None = None,
    campania: str | None = None,
) -> list[dict[str, Any]]:
    """Publicaciones comerciales (mas recientes primero), con filtros opcionales."""
    clausulas: list[str] = []
    params: list[Any] = []
    if estado:
        clausulas.append("estado = ?")
        params.append(estado)
    if cliente:
        clausulas.append("cliente = ?")
        params.append(cliente)
    if campania:
        clausulas.append("campania = ?")
        params.append(campania)
    sql = _SELECT_COMERCIAL
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)
    # Desempate por `id` (uuid, PK presente en ambos backends) en vez del `rowid` de
    # SQLite (que Postgres no tiene). Solo influye cuando dos piezas comparten
    # `fecha_creacion` (mismo segundo): un orden estable y portable, no autoritativo.
    sql += " ORDER BY fecha_creacion DESC, id DESC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_comercial(f) for f in filas]


def obtener_publicacion_comercial(publicacion_id: str) -> dict[str, Any] | None:
    """Una publicacion comercial por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_COMERCIAL} WHERE id = ?", (publicacion_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_comercial(fila) if fila is not None else None


def actualizar_publicacion_comercial(
    publicacion_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita parcialmente una publicacion comercial; None si el id no existe.

    Solo toca los campos de `_CAMPOS_EDITABLES_COMERCIAL`; ignora el resto. Pone
    `fecha_actualizacion` a ahora. NO valida (lo hace la API).
    """
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_COMERCIAL}
    if "objetivo" in cambios:
        cambios["objetivo"] = int(cambios["objetivo"] or 0)
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("fecha_actualizacion = ?")
    params: list[Any] = list(cambios.values())
    params.append(datetime.now().isoformat(timespec="seconds"))
    params.append(publicacion_id)
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE comercial_publicaciones SET {', '.join(asignaciones)} WHERE id = ?",
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            f"{_SELECT_COMERCIAL} WHERE id = ?", (publicacion_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_comercial(fila) if fila is not None else None


def marcar_aviso_comercial(publicacion_id: str, ts: str) -> None:
    """Marca el instante en que la pieza alcanzo su objetivo (solo la PRIMERA vez).

    El `WHERE aviso_en = ''` lo hace idempotente: una vez avisada, no se re-marca.
    """
    con = _conectar()
    try:
        con.execute(
            "UPDATE comercial_publicaciones SET aviso_en = ? WHERE id = ? AND aviso_en = ''",
            (ts, publicacion_id),
        )
        con.commit()
    finally:
        con.close()


def borrar_publicacion_comercial(publicacion_id: str) -> bool:
    """Borra una publicacion comercial y sus snapshots; True si existia, False si no."""
    con = _conectar()
    try:
        con.execute(
            "DELETE FROM comercial_snapshots WHERE publicacion_id = ?", (publicacion_id,)
        )
        cur = con.execute(
            "DELETE FROM comercial_publicaciones WHERE id = ?", (publicacion_id,)
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


# --- Snapshots (serie temporal de interacciones/alcance por publicacion) ------


def registrar_snapshot_comercial(
    publicacion_id: str, ts: str, interacciones: int, alcance: int
) -> bool:
    """Inserta un snapshot (idempotente por `(publicacion_id, ts)`).

    Devuelve True si inserto una fila nueva, False si ya habia un snapshot en ese `ts`
    (el indice UNICO lo evita; asi re-capturar en el mismo minuto no duplica puntos).
    """
    con = _conectar()
    try:
        cur = con.execute(
            "INSERT OR IGNORE INTO comercial_snapshots "
            "(id, publicacion_id, ts, interacciones, alcance) VALUES (?, ?, ?, ?, ?)",
            (uuid.uuid4().hex[:12], publicacion_id, ts, int(interacciones), int(alcance)),
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def listar_snapshots_comerciales(publicacion_id: str) -> list[dict[str, Any]]:
    """Serie temporal de una publicacion (mas antiguo primero), lista para graficar."""
    con = _conectar()
    try:
        filas = con.execute(
            "SELECT ts, interacciones, alcance FROM comercial_snapshots "
            "WHERE publicacion_id = ? ORDER BY ts ASC",
            (publicacion_id,),
        ).fetchall()
    finally:
        con.close()
    return [
        {"ts": f["ts"], "interacciones": int(f["interacciones"]), "alcance": int(f["alcance"])}
        for f in filas
    ]


def ultimo_snapshot_comercial(publicacion_id: str) -> dict[str, Any] | None:
    """El snapshot mas reciente de una publicacion (None si aun no tiene)."""
    con = _conectar()
    try:
        fila = con.execute(
            "SELECT ts, interacciones, alcance FROM comercial_snapshots "
            "WHERE publicacion_id = ? ORDER BY ts DESC LIMIT 1",
            (publicacion_id,),
        ).fetchone()
    finally:
        con.close()
    if fila is None:
        return None
    return {
        "ts": fila["ts"],
        "interacciones": int(fila["interacciones"]),
        "alcance": int(fila["alcance"]),
    }


# --------------------------------------------------------------------------- #
# Rota de horarios del equipo (F4 · #144): eventos/transmisiones + turnos       #
# --------------------------------------------------------------------------- #
#
# Sustituye el Excel manual de Elias. Dos tablas operacionales:
#   - `rota_eventos`: el calendario de eventos/transmisiones (fecha+hora+que sacar).
#   - `rota_turnos`:  las asignaciones (un miembro cubre un evento), por semana, con
#                     estado propuesto|aprobado y un flag `override` (cobertura forzada
#                     que rompe la rotacion de sabados; la decide Elias). NO se publica
#                     nada al equipo hasta que la semana esta `aprobada`.
# El PROPONEDOR (rota.py) es puro; aqui solo se persiste lo que la API decide.

# Columnas de `rota_eventos`. La ola B (#144) anade tipo_cobertura/prioridad/cambiado/
# actualizado: `cambiado`/`actualizado` son GESTIONADAS POR EL SISTEMA (no editables a
# pelo: `cambiado` lo derivamos al reprogramar y `actualizado` se refresca en cada edicion),
# por eso quedan fuera de `_CAMPOS_EDITABLES_EVENTO_ROTA`.
_COLS_EVENTO_ROTA = (
    "id",
    "titulo",
    "fecha",
    "hora",
    "contenido",
    "nota",
    "tipo_cobertura",
    "prioridad",
    "cambiado",
    "actualizado",
    "creado",
)
_SELECT_EVENTO_ROTA = f"SELECT {', '.join(_COLS_EVENTO_ROTA)} FROM rota_eventos"
_CAMPOS_EDITABLES_EVENTO_ROTA = (
    "titulo",
    "fecha",
    "hora",
    "contenido",
    "nota",
    "tipo_cobertura",
    "prioridad",
)

_COLS_TURNO_ROTA = (
    "id",
    "semana",
    "evento_id",
    "miembro_id",
    "miembro_nombre",
    "estado",
    "override",
    "motivo",
    "creado",
    "actualizado",
)
_SELECT_TURNO_ROTA = f"SELECT {', '.join(_COLS_TURNO_ROTA)} FROM rota_turnos"


def _fila_a_evento_rota(fila: Any) -> dict[str, Any]:
    evento = {col: fila[col] for col in _COLS_EVENTO_ROTA}
    # `cambiado` se persiste como 0/1; lo exponemos como bool para la capa API/UI.
    evento["cambiado"] = bool(fila["cambiado"])
    # Defensa retrocompatible: una fila migrada con NULL/"" cae al valor por defecto.
    evento["tipo_cobertura"] = fila["tipo_cobertura"] or TIPO_COBERTURA_TRANSMISION
    evento["prioridad"] = fila["prioridad"] or PRIORIDAD_EVENTO_DEFECTO
    return evento


def _fila_a_turno_rota(fila: Any) -> dict[str, Any]:
    turno = {col: fila[col] for col in _COLS_TURNO_ROTA}
    turno["override"] = bool(fila["override"])
    return turno


# --- Eventos / transmisiones --------------------------------------------------


def crear_evento_rota(
    titulo: str,
    *,
    fecha: str = "",
    hora: str = "",
    contenido: str = "",
    nota: str = "",
    tipo_cobertura: str = TIPO_COBERTURA_TRANSMISION,
    prioridad: str = PRIORIDAD_EVENTO_DEFECTO,
) -> dict[str, Any]:
    """Inserta un evento/transmision y lo devuelve. NO valida (lo hace la API).

    Nace `cambiado=0` (sin reprogramar) y con `actualizado`=`creado` (alta = primera version).
    """
    ahora = datetime.now().isoformat(timespec="seconds")
    fila = {
        "id": uuid.uuid4().hex[:12],
        "titulo": titulo,
        "fecha": fecha or "",
        "hora": hora or "",
        "contenido": contenido or "",
        "nota": nota or "",
        "tipo_cobertura": tipo_cobertura if tipo_cobertura in TIPOS_COBERTURA else TIPO_COBERTURA_TRANSMISION,
        "prioridad": prioridad if prioridad in PRIORIDADES_EVENTO else PRIORIDAD_EVENTO_DEFECTO,
        "cambiado": 0,
        "actualizado": ahora,
        "creado": ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_EVENTO_ROTA)
        con.execute(
            f"INSERT INTO rota_eventos ({', '.join(_COLS_EVENTO_ROTA)}) VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_EVENTO_ROTA),
        )
        con.commit()
    finally:
        con.close()
    fila["cambiado"] = bool(fila["cambiado"])
    return fila


def listar_eventos_rota(
    desde: str | None = None,
    hasta: str | None = None,
    *,
    solo_cambiados: bool = False,
    tipo_cobertura: str | None = None,
) -> list[dict[str, Any]]:
    """Eventos de la rota, en orden cronologico. Filtros opcionales (todos combinables).

    `desde`/`hasta` acotan por rango de fechas (ISO). `solo_cambiados` deja solo los
    REPROGRAMADOS (`cambiado=1`, los que Elias debe re-avisar). `tipo_cobertura` filtra por
    tipo de cobertura (transmision|imagenes|no_cubrir); la API ya valida el valor.
    """
    clausulas: list[str] = []
    params: list[Any] = []
    if desde:
        clausulas.append("fecha >= ?")
        params.append(desde)
    if hasta:
        clausulas.append("fecha <= ?")
        params.append(hasta)
    if solo_cambiados:
        clausulas.append("cambiado = ?")
        params.append(1)
    if tipo_cobertura:
        clausulas.append("tipo_cobertura = ?")
        params.append(tipo_cobertura)
    sql = _SELECT_EVENTO_ROTA
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)
    sql += " ORDER BY fecha ASC, hora ASC, titulo ASC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_evento_rota(f) for f in filas]


def obtener_evento_rota(evento_id: str) -> dict[str, Any] | None:
    con = _conectar()
    try:
        fila = con.execute(f"{_SELECT_EVENTO_ROTA} WHERE id = ?", (evento_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_evento_rota(fila) if fila is not None else None


# Campos cuya EDICION reprograma el evento: si cambia su valor, `cambiado` se pone a 1
# (hay que volver a avisar al equipo). Son los datos "logisticos" que el equipo de
# programacion mueve constantemente ("tres cambios en horarios para el fin de semana").
_CAMPOS_REPROGRAMAN_EVENTO: tuple[str, ...] = ("fecha", "hora", "tipo_cobertura")


def actualizar_evento_rota(evento_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    """Edita parcialmente un evento; None si el id no existe.

    Reglas de SEGUIMIENTO DE CAMBIOS (ola B, #144):
      - `actualizado` SIEMPRE se refresca (toda edicion deja marca temporal).
      - Si la edicion cambia `fecha`, `hora` o `tipo_cobertura` -> `cambiado=1` automatico
        (se reprogramo: el equipo debe re-enterarse). Solo si el valor REALMENTE cambia.
      - Si el request trae `cambiado=False` explicito (la accion "ya avisé / visto" de
        Elias) -> se LIMPIA a 0, y limpiar GANA aunque en el mismo request se hubiera
        reprogramado (Elias dice "ya está visto").
    Solo se escriben los campos editables; `cambiado`/`actualizado` los gestiona el sistema.
    """
    actual = obtener_evento_rota(evento_id)
    if actual is None:
        return None

    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_EVENTO_ROTA}

    # ¿Se reprogramo? Solo cuenta un cambio REAL de fecha/hora/tipo_cobertura.
    reprogramado = any(
        k in cambios and cambios[k] != actual.get(k) for k in _CAMPOS_REPROGRAMAN_EVENTO
    )
    nuevo_cambiado = 1 if reprogramado else int(bool(actual["cambiado"]))
    # La accion explicita "marcar avisado" (cambiado=False) limpia y GANA al reprograma.
    if "cambiado" in campos and not campos["cambiado"]:
        nuevo_cambiado = 0
    elif "cambiado" in campos and campos["cambiado"]:
        nuevo_cambiado = 1

    ahora = datetime.now().isoformat(timespec="seconds")
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("cambiado = ?")
    asignaciones.append("actualizado = ?")
    params: list[Any] = [*cambios.values(), nuevo_cambiado, ahora, evento_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE rota_eventos SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- columnas de allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(f"{_SELECT_EVENTO_ROTA} WHERE id = ?", (evento_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_evento_rota(fila) if fila is not None else None


def borrar_evento_rota(evento_id: str) -> bool:
    """Borra un evento y los turnos que lo referencian; True si existia."""
    con = _conectar()
    try:
        con.execute("DELETE FROM rota_turnos WHERE evento_id = ?", (evento_id,))
        cur = con.execute("DELETE FROM rota_eventos WHERE id = ?", (evento_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


# --- Turnos (asignaciones de la rota) -----------------------------------------


def crear_turno_rota(
    semana: str,
    evento_id: str,
    *,
    miembro_id: str = "",
    miembro_nombre: str = "",
    estado: str = ESTADO_ROTA_PROPUESTO,
    override: bool = False,
    motivo: str = "",
) -> dict[str, Any]:
    """Inserta un turno (asignacion) y lo devuelve. NO valida (lo hace la API)."""
    ahora = datetime.now().isoformat(timespec="seconds")
    fila = {
        "id": uuid.uuid4().hex[:12],
        "semana": semana,
        "evento_id": evento_id,
        "miembro_id": miembro_id or "",
        "miembro_nombre": miembro_nombre or "",
        "estado": estado if estado in ESTADOS_ROTA else ESTADO_ROTA_PROPUESTO,
        "override": 1 if override else 0,
        "motivo": motivo or "",
        "creado": ahora,
        "actualizado": ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_TURNO_ROTA)
        con.execute(
            f"INSERT INTO rota_turnos ({', '.join(_COLS_TURNO_ROTA)}) VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_TURNO_ROTA),
        )
        con.commit()
    finally:
        con.close()
    fila["override"] = bool(fila["override"])
    return fila


def listar_turnos_rota(semana: str | None = None) -> list[dict[str, Any]]:
    """Turnos de la rota; filtro opcional por `semana` (lunes ISO)."""
    sql = _SELECT_TURNO_ROTA
    params: tuple[Any, ...] = ()
    if semana:
        sql += " WHERE semana = ?"
        params = (semana,)
    sql += " ORDER BY semana ASC, creado ASC, id ASC"
    con = _conectar()
    try:
        filas = con.execute(sql, params).fetchall()
    finally:
        con.close()
    return [_fila_a_turno_rota(f) for f in filas]


def obtener_turno_rota(turno_id: str) -> dict[str, Any] | None:
    con = _conectar()
    try:
        fila = con.execute(f"{_SELECT_TURNO_ROTA} WHERE id = ?", (turno_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_turno_rota(fila) if fila is not None else None


def actualizar_turno_rota(turno_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    """Edita un turno (miembro/override/motivo/estado); None si el id no existe.

    Pone `actualizado` a ahora. `override` se normaliza a 0/1. NO valida (lo hace la API).
    """
    editables = ("miembro_id", "miembro_nombre", "estado", "override", "motivo")
    cambios = {k: v for k, v in campos.items() if k in editables}
    if "override" in cambios:
        cambios["override"] = 1 if cambios["override"] else 0
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = list(cambios.values())
    params.append(datetime.now().isoformat(timespec="seconds"))
    params.append(turno_id)
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE rota_turnos SET {', '.join(asignaciones)} WHERE id = ?", tuple(params)
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(f"{_SELECT_TURNO_ROTA} WHERE id = ?", (turno_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_turno_rota(fila) if fila is not None else None


def borrar_turnos_semana_rota(semana: str) -> int:
    """Borra TODOS los turnos de una semana (al re-proponer). Devuelve cuantos borro."""
    con = _conectar()
    try:
        cur = con.execute("DELETE FROM rota_turnos WHERE semana = ?", (semana,))
        con.commit()
        return cur.rowcount
    finally:
        con.close()


def aprobar_semana_rota(semana: str) -> int:
    """Marca TODOS los turnos de una semana como `aprobado` (publica al equipo).

    Devuelve cuantos turnos quedaron aprobados. Idempotente: re-aprobar no rompe.
    """
    ahora = datetime.now().isoformat(timespec="seconds")
    con = _conectar()
    try:
        cur = con.execute(
            "UPDATE rota_turnos SET estado = ?, actualizado = ? WHERE semana = ?",
            (ESTADO_ROTA_APROBADO, ahora, semana),
        )
        con.commit()
        return cur.rowcount
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# Horario de TRABAJO del equipo (F4 · #144, gestion de turnos): turnos + ausencias #
# --------------------------------------------------------------------------- #
#
# Paralelo a la cobertura de eventos: el reparto del TURNO de cada persona por dia
# (matutino/vespertino/descanso) y las AUSENCIAS/vacaciones que el proponedor respeta.
# El PROPONEDOR (rota.py, `proponer_horario`) es puro; aqui solo se persiste lo que la
# API decide. Nada se publica al equipo hasta que la semana esta `aprobada`.

_COLS_TURNO_TRABAJO_ROTA = (
    "id",
    "semana",
    "fecha",
    "miembro_id",
    "miembro_nombre",
    "franja",
    "estado",
    "override",
    "motivo",
    "nota_relevo",
    "creado",
    "actualizado",
)
_SELECT_TURNO_TRABAJO_ROTA = (
    f"SELECT {', '.join(_COLS_TURNO_TRABAJO_ROTA)} FROM rota_turnos_trabajo"
)

_COLS_AUSENCIA_ROTA = (
    "id",
    "miembro_id",
    "miembro_nombre",
    "tipo",
    "desde",
    "hasta",
    "motivo",
    "creado",
)
_SELECT_AUSENCIA_ROTA = f"SELECT {', '.join(_COLS_AUSENCIA_ROTA)} FROM rota_ausencias"


def _fila_a_turno_trabajo_rota(fila: Any) -> dict[str, Any]:
    turno = {col: fila[col] for col in _COLS_TURNO_TRABAJO_ROTA}
    turno["override"] = bool(fila["override"])
    return turno


def _fila_a_ausencia_rota(fila: Any) -> dict[str, Any]:
    return {col: fila[col] for col in _COLS_AUSENCIA_ROTA}


# --- Turnos de trabajo (asignaciones del horario) -----------------------------


def crear_turno_trabajo_rota(
    semana: str,
    fecha: str,
    *,
    miembro_id: str = "",
    miembro_nombre: str = "",
    franja: str = FRANJA_DESCANSO,
    estado: str = ESTADO_ROTA_PROPUESTO,
    override: bool = False,
    motivo: str = "",
    nota_relevo: str = "",
) -> dict[str, Any]:
    """Inserta un turno de trabajo (asignacion de horario) y lo devuelve. NO valida (lo hace la API)."""
    ahora = datetime.now().isoformat(timespec="seconds")
    fila = {
        "id": uuid.uuid4().hex[:12],
        "semana": semana,
        "fecha": fecha or "",
        "miembro_id": miembro_id or "",
        "miembro_nombre": miembro_nombre or "",
        "franja": franja if franja in FRANJAS_TURNO else FRANJA_DESCANSO,
        "estado": estado if estado in ESTADOS_ROTA else ESTADO_ROTA_PROPUESTO,
        "override": 1 if override else 0,
        "motivo": motivo or "",
        "nota_relevo": nota_relevo or "",
        "creado": ahora,
        "actualizado": ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_TURNO_TRABAJO_ROTA)
        con.execute(
            f"INSERT INTO rota_turnos_trabajo ({', '.join(_COLS_TURNO_TRABAJO_ROTA)}) "
            f"VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_TURNO_TRABAJO_ROTA),
        )
        con.commit()
    finally:
        con.close()
    fila["override"] = bool(fila["override"])
    return fila


def listar_turnos_trabajo_rota(semana: str | None = None) -> list[dict[str, Any]]:
    """Turnos de trabajo del horario; filtro opcional por `semana` (lunes ISO)."""
    sql = _SELECT_TURNO_TRABAJO_ROTA
    params: tuple[Any, ...] = ()
    if semana:
        sql += " WHERE semana = ?"
        params = (semana,)
    sql += " ORDER BY semana ASC, fecha ASC, franja ASC, creado ASC, id ASC"
    con = _conectar()
    try:
        filas = con.execute(sql, params).fetchall()
    finally:
        con.close()
    return [_fila_a_turno_trabajo_rota(f) for f in filas]


def obtener_turno_trabajo_rota(turno_id: str) -> dict[str, Any] | None:
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_TURNO_TRABAJO_ROTA} WHERE id = ?", (turno_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_turno_trabajo_rota(fila) if fila is not None else None


def actualizar_turno_trabajo_rota(
    turno_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita un turno de trabajo (franja/miembro/override/motivo/nota_relevo/estado); None si no existe.

    Pone `actualizado` a ahora. `override` se normaliza a 0/1. NO valida (lo hace la API).
    """
    editables = (
        "miembro_id",
        "miembro_nombre",
        "franja",
        "estado",
        "override",
        "motivo",
        "nota_relevo",
    )
    cambios = {k: v for k, v in campos.items() if k in editables}
    if "override" in cambios:
        cambios["override"] = 1 if cambios["override"] else 0
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = list(cambios.values())
    params.append(datetime.now().isoformat(timespec="seconds"))
    params.append(turno_id)
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE rota_turnos_trabajo SET {', '.join(asignaciones)} WHERE id = ?",
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            f"{_SELECT_TURNO_TRABAJO_ROTA} WHERE id = ?", (turno_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_turno_trabajo_rota(fila) if fila is not None else None


def borrar_turnos_trabajo_semana_rota(semana: str) -> int:
    """Borra TODOS los turnos de trabajo de una semana (al re-proponer). Devuelve cuantos borro."""
    con = _conectar()
    try:
        cur = con.execute("DELETE FROM rota_turnos_trabajo WHERE semana = ?", (semana,))
        con.commit()
        return cur.rowcount
    finally:
        con.close()


def aprobar_semana_horario_rota(semana: str) -> int:
    """Marca TODOS los turnos de trabajo de una semana como `aprobado` (publica al equipo).

    Devuelve cuantos turnos quedaron aprobados. Idempotente: re-aprobar no rompe.
    """
    ahora = datetime.now().isoformat(timespec="seconds")
    con = _conectar()
    try:
        cur = con.execute(
            "UPDATE rota_turnos_trabajo SET estado = ?, actualizado = ? WHERE semana = ?",
            (ESTADO_ROTA_APROBADO, ahora, semana),
        )
        con.commit()
        return cur.rowcount
    finally:
        con.close()


# --- Ausencias / vacaciones ---------------------------------------------------


def crear_ausencia_rota(
    miembro_id: str,
    desde: str,
    hasta: str,
    *,
    miembro_nombre: str = "",
    tipo: str = "otro",
    motivo: str = "",
) -> dict[str, Any]:
    """Inserta una ausencia (rango inclusivo) y la devuelve. NO valida (lo hace la API)."""
    ahora = datetime.now().isoformat(timespec="seconds")
    fila = {
        "id": uuid.uuid4().hex[:12],
        "miembro_id": miembro_id or "",
        "miembro_nombre": miembro_nombre or "",
        "tipo": tipo if tipo in TIPOS_AUSENCIA else "otro",
        "desde": desde or "",
        "hasta": hasta or "",
        "motivo": motivo or "",
        "creado": ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_AUSENCIA_ROTA)
        con.execute(
            f"INSERT INTO rota_ausencias ({', '.join(_COLS_AUSENCIA_ROTA)}) "
            f"VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_AUSENCIA_ROTA),
        )
        con.commit()
    finally:
        con.close()
    return fila


def listar_ausencias_rota(
    miembro_id: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
) -> list[dict[str, Any]]:
    """Ausencias de la rota, mas recientes primero. Filtros opcionales por miembro y solape de rango.

    `desde`/`hasta` filtran las ausencias que SOLAPAN con ese rango (ausencia.hasta >= desde
    AND ausencia.desde <= hasta): util para resolver las ausencias relevantes a una semana.
    """
    clausulas: list[str] = []
    params: list[Any] = []
    if miembro_id:
        clausulas.append("miembro_id = ?")
        params.append(miembro_id)
    if desde:
        clausulas.append("hasta >= ?")
        params.append(desde)
    if hasta:
        clausulas.append("desde <= ?")
        params.append(hasta)
    sql = _SELECT_AUSENCIA_ROTA
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)
    sql += " ORDER BY desde DESC, id DESC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_ausencia_rota(f) for f in filas]


def obtener_ausencia_rota(ausencia_id: str) -> dict[str, Any] | None:
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_AUSENCIA_ROTA} WHERE id = ?", (ausencia_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_ausencia_rota(fila) if fila is not None else None


def actualizar_ausencia_rota(
    ausencia_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita parcialmente una ausencia (tipo/desde/hasta/motivo); None si el id no existe."""
    editables = ("tipo", "desde", "hasta", "motivo")
    cambios = {k: v for k, v in campos.items() if k in editables}
    if not cambios:
        return obtener_ausencia_rota(ausencia_id)
    asignaciones = [f"{k} = ?" for k in cambios]
    params: list[Any] = list(cambios.values())
    params.append(ausencia_id)
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE rota_ausencias SET {', '.join(asignaciones)} WHERE id = ?",
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            f"{_SELECT_AUSENCIA_ROTA} WHERE id = ?", (ausencia_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_ausencia_rota(fila) if fila is not None else None


def borrar_ausencia_rota(ausencia_id: str) -> bool:
    """Borra una ausencia; True si existia, False si no."""
    con = _conectar()
    try:
        cur = con.execute("DELETE FROM rota_ausencias WHERE id = ?", (ausencia_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# Solicitudes de cambio de turno entre companeros (#175)                       #
# --------------------------------------------------------------------------- #
#
# Cuando un CM (solicitante A) necesita cubrir un asunto personal le pide a un
# companero (B) intercambiar el turno de un dia por el de otro. B acepta/rechaza, y si
# acepta, Elias (admin) aprueba o rechaza. La aprobacion EJECUTA el swap en
# `rota_turnos_trabajo` (intercambia `miembro_id` de las dos franjas) y la solicitud
# pasa a `aplicado`. Las ausencias REALES (vacaciones, baja) viven en SAP, no aqui.

_COLS_SWAP_TURNO = (
    "id",
    "solicitante_id",
    "solicitante_nombre",
    "destinatario_id",
    "destinatario_nombre",
    "fecha_a",
    "franja_a",
    "fecha_b",
    "franja_b",
    "motivo",
    "estado",
    "respuesta_destinatario",
    "respuesta_admin",
    "creado",
    "actualizado",
    "decidido_destinatario",
    "decidido_admin",
    "aplicado",
)
_SELECT_SWAP_TURNO = f"SELECT {', '.join(_COLS_SWAP_TURNO)} FROM rota_swaps_turno"

# Campos editables del swap (allowlist DEFENSIVA: la API valida transiciones; aqui se
# garantiza que `actualizar_swap_turno` solo toca columnas de estado/timestamps/respuestas
# y nunca el solicitante/destinatario/turnos originales).
_CAMPOS_EDITABLES_SWAP = (
    "estado",
    "respuesta_destinatario",
    "respuesta_admin",
    "decidido_destinatario",
    "decidido_admin",
    "aplicado",
)


def _fila_a_swap_turno(fila: Any) -> dict[str, Any]:
    return {col: fila[col] for col in _COLS_SWAP_TURNO}


def crear_swap_turno(
    solicitante_id: str,
    destinatario_id: str,
    fecha_a: str,
    franja_a: str,
    fecha_b: str,
    franja_b: str,
    *,
    solicitante_nombre: str = "",
    destinatario_nombre: str = "",
    motivo: str = "",
) -> dict[str, Any]:
    """Inserta una solicitud de swap (estado `propuesto`) y la devuelve.

    NO valida (lo hace la API): que los miembros existan, que sean distintos, que las
    fechas sean ISO y que las franjas pertenezcan a `FRANJAS_TURNO`. La validacion de
    que existen turnos reales en `rota_turnos_trabajo` que coinciden con (A, fecha_a,
    franja_a) y (B, fecha_b, franja_b) tambien la hace la API.
    """
    ahora = datetime.now().isoformat(timespec="seconds")
    fila = {
        "id": uuid.uuid4().hex[:12],
        "solicitante_id": solicitante_id or "",
        "solicitante_nombre": solicitante_nombre or "",
        "destinatario_id": destinatario_id or "",
        "destinatario_nombre": destinatario_nombre or "",
        "fecha_a": fecha_a or "",
        "franja_a": franja_a or "",
        "fecha_b": fecha_b or "",
        "franja_b": franja_b or "",
        "motivo": motivo or "",
        "estado": ESTADO_SWAP_PROPUESTO,
        "respuesta_destinatario": "",
        "respuesta_admin": "",
        "creado": ahora,
        "actualizado": ahora,
        "decidido_destinatario": "",
        "decidido_admin": "",
        "aplicado": "",
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_SWAP_TURNO)
        con.execute(
            f"INSERT INTO rota_swaps_turno ({', '.join(_COLS_SWAP_TURNO)}) "
            f"VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_SWAP_TURNO),
        )
        con.commit()
    finally:
        con.close()
    return fila


def listar_swaps_turno(
    estado: str | None = None,
    solicitante_id: str | None = None,
    destinatario_id: str | None = None,
    *,
    mio_id: str | None = None,
) -> list[dict[str, Any]]:
    """Solicitudes de swap, mas recientes primero. Filtros opcionales combinables.

    `mio_id` es un atajo para "swaps que me involucran": filas en las que `mio_id` es
    solicitante O destinatario. La API lo usa cuando el cliente pide `?mio=true` y hay
    sesion activa.
    """
    clausulas: list[str] = []
    params: list[Any] = []
    if estado:
        clausulas.append("estado = ?")
        params.append(estado)
    if solicitante_id:
        clausulas.append("solicitante_id = ?")
        params.append(solicitante_id)
    if destinatario_id:
        clausulas.append("destinatario_id = ?")
        params.append(destinatario_id)
    if mio_id:
        clausulas.append("(solicitante_id = ? OR destinatario_id = ?)")
        params.append(mio_id)
        params.append(mio_id)
    sql = _SELECT_SWAP_TURNO
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)
    sql += " ORDER BY creado DESC, id DESC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_swap_turno(f) for f in filas]


def obtener_swap_turno(swap_id: str) -> dict[str, Any] | None:
    """Una solicitud de swap por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_SWAP_TURNO} WHERE id = ?", (swap_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_swap_turno(fila) if fila is not None else None


def actualizar_swap_turno(
    swap_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Actualiza campos de un swap (allowlist `_CAMPOS_EDITABLES_SWAP`); None si no existe.

    Refresca `actualizado` SIEMPRE. La API es responsable de las TRANSICIONES validas
    (no se valida aqui). Devuelve el swap actualizado, o None si el id no existe.
    """
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_SWAP}
    if not cambios:
        return obtener_swap_turno(swap_id)
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = list(cambios.values())
    params.append(datetime.now().isoformat(timespec="seconds"))
    params.append(swap_id)
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE rota_swaps_turno SET {', '.join(asignaciones)} WHERE id = ?",
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            f"{_SELECT_SWAP_TURNO} WHERE id = ?", (swap_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_swap_turno(fila) if fila is not None else None


def borrar_swap_turno(swap_id: str) -> bool:
    """Borra un swap (uso administrativo; el flujo normal es marcar `cancelado`)."""
    con = _conectar()
    try:
        cur = con.execute("DELETE FROM rota_swaps_turno WHERE id = ?", (swap_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def aplicar_swap_turno(
    swap_id: str,
    *,
    solicitante_id: str,
    solicitante_nombre: str,
    destinatario_id: str,
    destinatario_nombre: str,
    fecha_a: str,
    franja_a: str,
    fecha_b: str,
    franja_b: str,
    respuesta_admin: str = "",
) -> dict[str, Any] | None:
    """Aprueba+ejecuta un swap en UNA transaccion: intercambia los miembros y marca `aplicado`.

    Re-VALIDA dentro de la misma conexion que las franjas actuales en `rota_turnos_trabajo`
    siguen siendo las del swap original (otro usuario podria haberlas reasignado a mano).
    Si NO coinciden, devuelve `{"error": "no_coinciden", "esperado": {...}, "actual": {...}}`
    y NO toca nada. Si todo cuadra, intercambia los `miembro_id`+`miembro_nombre` de las
    dos filas, marca el swap como `aplicado` con el `respuesta_admin` y los timestamps
    correspondientes, y devuelve el swap actualizado.

    Estados de salida posibles:
      - dict del swap (claves de `_COLS_SWAP_TURNO`) si se aplico,
      - {"error": "no_coinciden", "esperado": ..., "actual": ...} si las franjas no
        coinciden con lo solicitado en este momento,
      - None si el `swap_id` no existe.
    """
    ahora = datetime.now().isoformat(timespec="seconds")
    con = _conectar()
    try:
        # 1) El swap debe existir.
        swap = con.execute(
            f"{_SELECT_SWAP_TURNO} WHERE id = ?", (swap_id,)
        ).fetchone()
        if swap is None:
            return None
        # 2) Las dos franjas reales (por miembro + fecha + franja) deben existir y
        #    seguir asignadas a quien dijo el swap. Buscamos por (fecha, franja) y
        #    comprobamos el miembro actual (asi detectamos el caso 409 con detalle).
        fila_a = con.execute(
            "SELECT id, miembro_id, miembro_nombre, fecha, franja FROM rota_turnos_trabajo "
            "WHERE fecha = ? AND franja = ? AND miembro_id = ?",
            (fecha_a, franja_a, solicitante_id),
        ).fetchone()
        fila_b = con.execute(
            "SELECT id, miembro_id, miembro_nombre, fecha, franja FROM rota_turnos_trabajo "
            "WHERE fecha = ? AND franja = ? AND miembro_id = ?",
            (fecha_b, franja_b, destinatario_id),
        ).fetchone()
        if fila_a is None or fila_b is None:
            # Buscamos el detalle ACTUAL (sin filtrar por miembro) para informar.
            actual_a = con.execute(
                "SELECT miembro_id, miembro_nombre FROM rota_turnos_trabajo "
                "WHERE fecha = ? AND franja = ?",
                (fecha_a, franja_a),
            ).fetchone()
            actual_b = con.execute(
                "SELECT miembro_id, miembro_nombre FROM rota_turnos_trabajo "
                "WHERE fecha = ? AND franja = ?",
                (fecha_b, franja_b),
            ).fetchone()
            return {
                "error": "no_coinciden",
                "esperado": {
                    "a": {
                        "fecha": fecha_a,
                        "franja": franja_a,
                        "miembro_id": solicitante_id,
                        "miembro_nombre": solicitante_nombre,
                    },
                    "b": {
                        "fecha": fecha_b,
                        "franja": franja_b,
                        "miembro_id": destinatario_id,
                        "miembro_nombre": destinatario_nombre,
                    },
                },
                "actual": {
                    "a": {
                        "fecha": fecha_a,
                        "franja": franja_a,
                        "miembro_id": actual_a["miembro_id"] if actual_a else "",
                        "miembro_nombre": actual_a["miembro_nombre"] if actual_a else "",
                    },
                    "b": {
                        "fecha": fecha_b,
                        "franja": franja_b,
                        "miembro_id": actual_b["miembro_id"] if actual_b else "",
                        "miembro_nombre": actual_b["miembro_nombre"] if actual_b else "",
                    },
                },
            }
        # 3) Intercambiamos los miembros + nombre + actualizado de ambas filas y marcamos
        #    el swap como `aplicado`. Todo bajo la misma conexion (Postgres autocommit
        #    desactivado por defecto en nuestro driver -> la `con.commit()` final lo encierra
        #    como una transaccion).
        con.execute(
            "UPDATE rota_turnos_trabajo SET miembro_id = ?, miembro_nombre = ?, "
            "actualizado = ? WHERE id = ?",
            (destinatario_id, destinatario_nombre, ahora, fila_a["id"]),
        )
        con.execute(
            "UPDATE rota_turnos_trabajo SET miembro_id = ?, miembro_nombre = ?, "
            "actualizado = ? WHERE id = ?",
            (solicitante_id, solicitante_nombre, ahora, fila_b["id"]),
        )
        con.execute(
            "UPDATE rota_swaps_turno SET estado = ?, respuesta_admin = ?, "
            "decidido_admin = ?, aplicado = ?, actualizado = ? WHERE id = ?",
            ("aplicado", respuesta_admin or "", ahora, ahora, ahora, swap_id),
        )
        con.commit()
        fila = con.execute(
            f"{_SELECT_SWAP_TURNO} WHERE id = ?", (swap_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_swap_turno(fila) if fila is not None else None


# --------------------------------------------------------------------------- #
# Cola de jobs de generacion (#130 Fase 2 / ADR 0002 Fase B)                    #
# --------------------------------------------------------------------------- #
#
# El back ENCOLA (`encolar_job`) y devuelve de inmediato; un WORKER (in-proceso en local,
# servicio aparte en hosted) CLAVA un pendiente (`reclamar_job`) y corre `claude -p`. La
# reclamacion es CONCURRENTE-SEGURA en Postgres con `FOR UPDATE SKIP LOCKED`: varios workers
# no clavan el mismo job. La cancelacion viaja por la columna `cancelado` (el back la marca;
# el worker la lee y mata el arbol), de modo que funciona AUNQUE el worker sea otro proceso.

# Estados del ciclo de la cola (distintos de los del registro de generacion).
JOB_PENDIENTE = "pendiente"
JOB_RECLAMADO = "reclamado"
JOB_TERMINADO = "terminado"


def encolar_job(gen_id: str, spec: str) -> str:
    """Encola un job de generacion para el `gen_id` dado con su `spec` (JSON). Devuelve el job id.

    `spec` es el JSON serializable que el worker usa para reconstruir el trabajo (prompt +
    post-procesado + cwd). Idempotente por `gen_id` (indice UNICO): re-encolar el mismo
    registro no duplica filas. El back lo llama dentro de la peticion y responde al instante.
    """
    job_id = uuid.uuid4().hex[:12]
    ahora = datetime.now().isoformat(timespec="seconds")
    con = _conectar()
    try:
        con.execute(
            "INSERT OR IGNORE INTO jobs (id, gen_id, spec, estado, creado) "
            "VALUES (?, ?, ?, ?, ?)",
            (job_id, gen_id, spec, JOB_PENDIENTE, ahora),
        )
        con.commit()
    finally:
        con.close()
    return job_id


def reclamar_job(worker: str = "") -> dict[str, Any] | None:
    """Clava UN job pendiente de forma CONCURRENTE-SEGURA y lo devuelve (None si no hay).

    `SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1` dentro de la transaccion + UPDATE a
    `reclamado`: otro worker que corra a la vez SALTA esa fila (no la doble-ejecuta).
    Devuelve `{id, gen_id, spec}` del job clavado.
    """
    ahora = datetime.now().isoformat(timespec="seconds")
    con = _conectar()
    try:
        fila = con.execute(
            "SELECT id, gen_id, spec FROM jobs WHERE estado = ? "
            "ORDER BY creado ASC, id ASC LIMIT 1 FOR UPDATE SKIP LOCKED",
            (JOB_PENDIENTE,),
        ).fetchone()
        if fila is None:
            con.commit()
            return None
        con.execute(
            "UPDATE jobs SET estado = ?, worker = ?, claimed_at = ? WHERE id = ?",
            (JOB_RECLAMADO, worker, ahora, fila["id"]),
        )
        con.commit()
        return {"id": fila["id"], "gen_id": fila["gen_id"], "spec": fila["spec"]}
    finally:
        con.close()


def terminar_job(job_id: str) -> None:
    """Marca un job como terminado (el worker ya fijo el estado terminal del registro)."""
    con = _conectar()
    try:
        con.execute("UPDATE jobs SET estado = ? WHERE id = ?", (JOB_TERMINADO, job_id))
        con.commit()
    finally:
        con.close()


def cancelar_job(gen_id: str) -> bool:
    """Marca el job de un `gen_id` como cancelado (cross-proceso). True si habia un job.

    El back lo llama al cancelar; el worker LEE `cancelado` y mata el arbol. Tambien
    cubre el caso de un job AUN pendiente (no reclamado): el worker, al clavarlo, ve el
    flag y lo finaliza como cancelado sin lanzar `claude`. Devuelve False si no hay job
    (ya terminado o nunca encolado): el llamante cae a la cancelacion in-memoria.
    """
    con = _conectar()
    try:
        cur = con.execute(
            "UPDATE jobs SET cancelado = 1 WHERE gen_id = ? AND estado <> ?",
            (gen_id, JOB_TERMINADO),
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def job_cancelado(job_id: str) -> bool:
    """True si el job esta marcado como cancelado (lo sondea el worker en ejecucion)."""
    con = _conectar()
    try:
        fila = con.execute("SELECT cancelado FROM jobs WHERE id = ?", (job_id,)).fetchone()
    finally:
        con.close()
    return bool(fila["cancelado"]) if fila is not None else False
