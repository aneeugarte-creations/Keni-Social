"""Persistencia OPERACIONAL de la Consola Keni: SQLite (local) o Postgres (hosted).

Cubre lo que NO es contenido editable a mano: las `tareas`, el apartado `comercial`
(seguimiento de piezas + su serie temporal de snapshots), la `rota` y, via `auth/`, los
`usuarios`/`sesiones`. El CONTENIDO editorial (publicaciones, plantillas, fuentes RSS,
hashtags, franjas, historial de skills) vive en ficheros YAML por marca (`ficheros.py`),
con un indice SQLite regenerable (`indice.py`). La fachada `repos.py` enruta cada cosa a
su almacen.

BACKEND (#130): lo elige `motor_db` segun `DATABASE_URL` (ver `motor_db.py`):
  - SIN `DATABASE_URL`  -> SQLite local en `~/.config/keni-social/consola.db` (o la ruta
    de `KENI_CONSOLA_DB`, util para tests). Es el perfil PRIVADO/LOCAL (ADR 0001/0002):
    ninguna fila sale de la maquina. Comportamiento HISTORICO intacto.
  - CON `DATABASE_URL`  -> Postgres (perfil hosted multiusuario; el stack `deploy/` lo
    cablea). El cutover de datos lo hace `migracion.py` (one-shot).

El esquema se crea ON-DEMAND en la primera conexion (idempotente, en ambos backends). En
el perfil SQLite, si existe el viejo `~/.config/keni-social/tareas.json`, sus tareas se
MIGRAN una sola vez (best-effort, idempotente). Las funciones publicas y la fachada
`repos.py` son ESTABLES: ningun call site cambia al cambiar de backend.

SEGURIDAD:
  - SIEMPRE consultas PARAMETRIZADAS (`?`), NUNCA f-strings con datos en el SQL. El
    `motor_db` traduce `?`->`%s` en Postgres sin tocar los datos.
  - En el perfil local la base es local; ninguna fila sale de la maquina.

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
global y problemas de hilos con el `TestClient`; en Postgres es una conexion por op).

CONCURRENCIA (servicio compartido, #130): en SQLite cada conexion abre en WAL
(`journal_mode=WAL`) con `busy_timeout` para una replica (lo configura `motor_db`). En
Postgres la concurrencia multiusuario/multi-replica es nativa: ese es el motivo de migrar.

BACKEND POSTGRES (#130): toda la persistencia operacional pasa por `conectar()` y
consultas parametrizadas, asi que el cambio de backend se localiza en `motor_db`
(SQLite/Postgres) SIN tocar las firmas publicas. `conectar()` es el punto de extension.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

# Allowlists de dominio (neutras, sin acoplar al backend): viven en `estados.py`.
from . import config, motor_db, rutas
from .estados import (
    ESTADO_COMERCIAL_ACTIVA,
    ESTADO_ROTA_APROBADO,
    ESTADO_ROTA_PROPUESTO,
    ESTADOS_COMERCIAL,
    ESTADOS_ROTA,
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
    "ESTADOS_COMERCIAL",
    "ESTADOS_ROTA",
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
    "actualizar_turnos_rota_lote",
    "aprobar_semana_horario_rota",
    "aprobar_semana_rota",
    "arrancar_persistencia",
    "borrar_ausencia_rota",
    "borrar_evento_rota",
    "borrar_publicacion_comercial",
    "borrar_tarea",
    "borrar_turnos_semana_rota",
    "borrar_turnos_trabajo_semana_rota",
    "cancelar_job",
    "conectar",
    "copiar_turnos_rota",
    "copiar_turnos_trabajo_rota",
    "crear_ausencia_rota",
    "crear_evento_rota",
    "crear_publicacion_comercial",
    "crear_tarea",
    "crear_turno_rota",
    "crear_turno_trabajo_rota",
    "encolar_job",
    "job_cancelado",
    "listar_ausencias_rota",
    "listar_eventos_rota",
    "listar_publicaciones_comerciales",
    "listar_snapshots_comerciales",
    "listar_tareas",
    "listar_turnos_rota",
    "listar_turnos_trabajo_rota",
    "marcar_aviso_comercial",
    "obtener_ausencia_rota",
    "obtener_evento_rota",
    "obtener_publicacion_comercial",
    "obtener_tarea",
    "obtener_turno_rota",
    "obtener_turno_trabajo_rota",
    "reclamar_job",
    "registrar_snapshot_comercial",
    "terminar_job",
    "ruta_db",
    "ultimo_snapshot_comercial",
]


def ruta_db() -> Path:
    """Ruta del consola.db (SQLite). Solo aplica en el perfil local (sin `DATABASE_URL`).

    Delega en `motor_db.ruta_db`: `KENI_CONSOLA_DB` la sobreescribe (override de maxima
    prioridad; tests); si no, cuelga de la raiz de estado unica (`rutas.dir_config()`).
    En el perfil Postgres no se usa (la conexion va por `DATABASE_URL`).
    """
    return motor_db.ruta_db()


def _conectar() -> Any:
    """Abre la conexion al backend, crea el esquema on-demand y migra el JSON viejo.

    El backend (SQLite o Postgres) lo elige `motor_db.conectar_cruda()` segun
    `DATABASE_URL`. La conexion devuelta IMITA la API de `sqlite3.Connection` que usan los
    call sites (`execute(sql, params)` con `?`, filas por nombre, `rowcount`, commit/close).

    El esquema se crea aqui (idempotente, en ambos backends) para que exista por cualquier
    via de arranque. La migracion del viejo `tareas.json` solo aplica en SQLite local.
    """
    con = motor_db.conectar_cruda()
    _crear_esquema(con)
    if not motor_db.es_postgres():
        _migrar_tareas_json(con)
    return con


def conectar() -> Any:
    """Conexion publica al backend (mismo `_conectar`, expuesto para `auth/`).

    El esquema de `usuarios`/`sesiones` se crea aqui igual que el resto de tablas, de modo
    que `auth/` puede operar sin duplicar la creacion del esquema. Cada operacion
    abre/cierra su propia conexion.
    """
    return _conectar()


# --------------------------------------------------------------------------- #
# Guardia de arranque: NUNCA arrancar hosted vacio orfanando datos locales      #
# --------------------------------------------------------------------------- #
#
# Tablas cuya PRESENCIA de filas indica "ya hay datos" en un backend. `usuarios` es la
# critica (perder cuentas en un servicio multiusuario es lo peor); incluimos tambien las
# operacionales de negocio. `sesiones` se omite a proposito: son efimeras (caducan), su
# ausencia no significa "base vacia".
_TABLAS_CON_DATOS: tuple[str, ...] = (
    "usuarios",
    "tareas",
    "comercial_publicaciones",
    "comercial_snapshots",
    "rota_eventos",
    "rota_turnos",
    "rota_turnos_trabajo",
    "rota_ausencias",
)


class PersistenciaError(RuntimeError):
    """Error de arranque de la persistencia (p.ej. cutover pendiente). Mensaje en espanol."""


def _hay_filas(con: Any) -> bool:
    """True si CUALQUIERA de las tablas de negocio tiene al menos una fila (en `con`)."""
    for tabla in _TABLAS_CON_DATOS:
        try:
            fila = con.execute(f"SELECT 1 FROM {tabla} LIMIT 1").fetchone()  # noqa: S608 -- tabla de allowlist
        except Exception:  # noqa: BLE001 -- tabla inexistente en un origen viejo: cuenta como vacia
            continue
        if fila is not None:
            return True
    return False


def _sqlite_local_tiene_datos() -> bool:
    """True si existe un `consola.db` SQLite local con datos de negocio (origen del cutover)."""
    ruta = motor_db.ruta_db()
    if not ruta.is_file():
        return False
    import sqlite3 as _sqlite3

    con = _sqlite3.connect(str(ruta))
    con.row_factory = _sqlite3.Row
    try:
        return _hay_filas(con)
    finally:
        con.close()


def arrancar_persistencia() -> None:
    """Comprueba en el arranque que un deploy hosted NO orfana datos locales (SEGURIDAD).

    Crea el esquema on-demand (idempotente, ambos backends) y, en el perfil POSTGRES,
    aplica el guardia: si el Postgres esta VACIO (sin filas de negocio) PERO existe un
    `consola.db` SQLite local CON datos, REHUSA arrancar con un error claro que apunta a la
    migracion (`python -m keni_consola.migracion`). Asi un deploy nunca arranca en blanco
    "perdiendo" silenciosamente los datos que aun viven en el SQLite del volumen.

    En el perfil SQLite local es practicamente no-op (no hay nada que orfanar): solo crea el
    esquema. Idempotente: una vez migrado (Postgres con datos), el guardia es transparente.
    """
    con = _conectar()  # crea el esquema on-demand
    try:
        if not motor_db.es_postgres():
            return  # perfil local: nada que orfanar
        if _hay_filas(con):
            return  # Postgres ya tiene datos: cutover hecho (o nativo). Transparente.
    finally:
        con.close()

    # Postgres vacio: solo es seguro arrancar si NO hay un SQLite local con datos que migrar.
    if _sqlite_local_tiene_datos():
        raise PersistenciaError(
            "Arranque INSEGURO: DATABASE_URL apunta a un Postgres VACIO, pero existe un "
            f"consola.db SQLite local CON datos ({motor_db.ruta_db()}). Arrancar ahora "
            "dejaria esos datos huerfanos. Ejecuta el cutover ANTES de servir:\n"
            "    python -m keni_consola.migracion\n"
            "(idempotente; ver deploy/README.md, seccion 'Cutover a Postgres + S3')."
        )


# DDL del esquema operacional, como sentencias INDIVIDUALES (no un script multi-sentencia)
# para ser PORTABLE entre SQLite y Postgres: `executescript` es exclusivo de sqlite3, asi
# que ejecutamos una a una via `con.execute` (soportado por ambos backends). Los tipos
# (`TEXT`/`INTEGER`), `PRIMARY KEY`, `UNIQUE`, `NOT NULL DEFAULT ''` y
# `CREATE [UNIQUE] INDEX IF NOT EXISTS` son comunes a SQLite y Postgres 16, asi que el
# mismo DDL crea el esquema en ambos. Los ids son TEXT generados por la app (uuid), no
# autoincrementales: no hay `AUTOINCREMENT`/`SERIAL` que diverja.
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
    """Crea las tablas operacionales si no existen (idempotente, ambos backends).

    Ejecuta el DDL sentencia a sentencia (portable SQLite/Postgres) y luego aplica las
    migraciones de columnas ampliadas (`tareas`, `rota_eventos`).

    ESTO CORRE EN AMBOS BACKENDS, a proposito: `CREATE TABLE IF NOT EXISTS` NO anade
    columnas a una tabla que YA existe, asi que cualquier BD —SQLite en disco o Postgres
    hosted— creada ANTES de una ampliacion necesita el `ALTER TABLE ... ADD COLUMN`. Antes
    se daba por hecho que "en Postgres el CREATE TABLE declara el esquema completo", pero el
    Postgres hosted PERSISTE entre despliegues: una tabla creada por una version anterior se
    quedaba sin las columnas nuevas (fallo real: `rota_eventos` sin `tipo_cobertura` → 500 al
    leer el calendario). La deteccion de columnas es portable (`_columnas_existentes`).
    """
    for sentencia in _DDL_ESQUEMA:
        con.execute(sentencia)
    _migrar_columnas_tareas(con)
    _migrar_columnas_eventos_rota(con)
    con.commit()


def _columnas_existentes(con: Any, tabla: str) -> set[str]:
    """Nombres de columnas que YA tiene `tabla`, portable a los dos backends.

    SQLite expone el esquema con `PRAGMA table_info(...)`; Postgres no, asi que alli se
    consulta `information_schema.columns`. `tabla` es SIEMPRE un nombre interno de una
    allowlist (constantes del modulo, nunca entrada de usuario), por eso es seguro
    interpolarlo en el PRAGMA. El placeholder `?` lo traduce `motor_db` a `%s` en Postgres.
    """
    if motor_db.es_postgres():
        filas = con.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
            (tabla,),
        ).fetchall()
        return {fila["column_name"] for fila in filas}
    filas = con.execute(f"PRAGMA table_info({tabla})").fetchall()  # noqa: S608 -- tabla de allowlist
    return {fila["name"] for fila in filas}


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
    responsable "desconocido", sin enlace) y no se pierde ni reescribe nada. Corre en ambos
    backends (ver `_crear_esquema`): el Postgres hosted persiste y tambien puede ir atrasado.
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
    existentes quedan como `transmision`/`media`/sin reprogramar y no se pierde nada. Corre en
    ambos backends (ver `_crear_esquema`); era el origen del 500 del calendario en hosted.
    """
    columnas = _columnas_existentes(con, "rota_eventos")
    for columna, tipo in _COLUMNAS_EVENTO_ROTA_AMPLIADAS:
        if columna not in columnas:
            con.execute(f"ALTER TABLE rota_eventos ADD COLUMN {columna} {tipo}")


# --------------------------------------------------------------------------- #
# Migracion best-effort del viejo tareas.json                                  #
# --------------------------------------------------------------------------- #


def _ruta_tareas_json() -> Path:
    """Ruta del viejo tareas.json (misma convencion que la feature historica).

    `KENI_CONSOLA_TAREAS` la sobreescribe (tests); si no, cuelga de la raiz de estado
    unica (`rutas.dir_config()`), mismo subpath `keni-social/tareas.json` que antes.
    """
    if (p := config.override_ruta(config.ENV_TAREAS)) is not None:
        return p
    return rutas.dir_config() / "tareas.json"


def _migrar_tareas_json(con: Any) -> None:
    """Si existe el viejo tareas.json, vuelca sus tareas a SQLite (idempotente).

    Best-effort: cualquier fallo de lectura/parseo se ignora en silencio (no debe
    impedir el arranque). Cada tarea se inserta con `INSERT OR IGNORE` por su id,
    asi que repetir la migracion no duplica filas.
    """
    ruta_json = _ruta_tareas_json()
    try:
        texto = ruta_json.read_text(encoding="utf-8")
    except OSError:
        return
    try:
        datos = json.loads(texto)
    except json.JSONDecodeError:
        return
    crudas = datos.get("tareas") if isinstance(datos, dict) else None
    if not isinstance(crudas, list):
        return
    for cruda in crudas:
        tarea = _normalizar_tarea_json(cruda)
        if tarea is None:
            continue
        con.execute(
            "INSERT OR IGNORE INTO tareas (id, proyecto, titulo, detalle, estado, fecha) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                tarea["id"],
                tarea["proyecto"],
                tarea["titulo"],
                tarea["detalle"],
                tarea["estado"],
                tarea["fecha"],
            ),
        )
    con.commit()


def _normalizar_tarea_json(cruda: object) -> dict[str, Any] | None:
    """Valida/normaliza una tarea cruda del JSON viejo; None si no es utilizable."""
    if not isinstance(cruda, dict):
        return None
    tid = cruda.get("id")
    proyecto_id = cruda.get("proyecto")
    titulo = cruda.get("titulo")
    if not (isinstance(tid, str) and tid):
        return None
    if not (isinstance(proyecto_id, str) and proyecto_id):
        return None
    if not (isinstance(titulo, str) and titulo.strip()):
        return None
    estado = cruda.get("estado")
    if estado not in ESTADOS_TAREA:
        estado = "pendiente"
    detalle = cruda.get("detalle")
    fecha = cruda.get("fecha")
    return {
        "id": tid,
        "proyecto": proyecto_id,
        "titulo": titulo.strip(),
        "detalle": detalle.strip() if isinstance(detalle, str) else "",
        "estado": estado,
        "fecha": fecha if isinstance(fecha, str) and fecha else "",
    }


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
# Asignacion flexible (rama rota-asignacion-flexible): helpers de lote + copiar #
# --------------------------------------------------------------------------- #
#
# Soporte para las herramientas de la consola sobre asignacion a mano: edicion
# masiva de turnos (multi-select), copia de la semana anterior, y panel de carga.
# La asignacion es 100% manual; ningun algoritmo de reparto vive aqui.


def actualizar_turnos_rota_lote(
    ids: list[str], campos: dict[str, Any]
) -> tuple[int, list[dict[str, Any]]]:
    """UPDATE masivo sobre `rota_turnos` para los `ids` dados. Devuelve `(n, turnos)`.

    `campos` solo aplica las claves editables (mismas que `actualizar_turno_rota`). `n`
    es el rowcount del UPDATE; `turnos` son los registros tras el cambio (SELECT por ids,
    para que la API devuelva el estado fresco sin tirar de los call sites uno a uno).

    Si `ids` viene vacio o no hay campos editables, no toca BD y devuelve `(0, [])`.
    """
    if not ids:
        return 0, []
    editables = ("miembro_id", "miembro_nombre", "estado", "override", "motivo")
    cambios = {k: v for k, v in campos.items() if k in editables}
    if not cambios:
        return 0, []
    if "override" in cambios:
        cambios["override"] = 1 if cambios["override"] else 0
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = list(cambios.values())
    params.append(datetime.now().isoformat(timespec="seconds"))
    marcadores = ", ".join("?" for _ in ids)
    sql_update = (
        f"UPDATE rota_turnos SET {', '.join(asignaciones)} "
        f"WHERE id IN ({marcadores})"  # noqa: S608 -- columnas de allowlist
    )
    sql_select = f"{_SELECT_TURNO_ROTA} WHERE id IN ({marcadores})"  # noqa: S608
    con = _conectar()
    try:
        cur = con.execute(sql_update, tuple(params) + tuple(ids))
        con.commit()
        filas = con.execute(sql_select, tuple(ids)).fetchall()
    finally:
        con.close()
    return cur.rowcount, [_fila_a_turno_rota(f) for f in filas]


def copiar_turnos_rota(
    de_lunes: str, a_lunes: str, *, reemplazar: bool = False
) -> tuple[int, str]:
    """Copia COBERTURAS de una semana a otra. DECISION: solo el horario tiene sentido copiar.

    La cobertura está ligada a un `evento_id` concreto, y cada semana son eventos distintos
    (los partidos cambian); copiar turnos de cobertura sin sus eventos no aporta valor real.
    Para mantener el contrato simétrico con `copiar_turnos_trabajo_rota`, este helper existe
    pero devuelve siempre `(0, mensaje)` y no toca BD. El `mensaje` lo propaga la API a la UI
    como warning.

    `reemplazar` y los parametros se aceptan para mantener la firma uniforme con horario.
    """
    del de_lunes, a_lunes, reemplazar  # firma uniforme; no se usan (ver docstring).
    return 0, "Solo se copia el horario; los eventos cambian cada semana."


def copiar_turnos_trabajo_rota(
    de_lunes: str, a_lunes: str, *, reemplazar: bool = False
) -> int:
    """Copia el horario laboral (`rota_turnos_trabajo`) de `de_lunes` a `a_lunes`.

    Para cada turno de la semana origen, crea uno nuevo en la semana destino con `fecha`
    desplazada +7 dias y el mismo `miembro_id`/`franja`/`motivo`/`nota_relevo`. Los IDs
    son nuevos (uuid); el `estado` arranca como `propuesto` (Elias re-aprueba antes de
    publicar). Si `reemplazar=True`, primero borra los turnos existentes de `a_lunes`.

    Devuelve cuantas filas se crearon. Si `de_lunes` o `a_lunes` no son fechas validas,
    devuelve 0 sin tocar BD.
    """
    try:
        d_de = date.fromisoformat(de_lunes)
        d_a = date.fromisoformat(a_lunes)
    except (ValueError, TypeError):
        return 0
    delta = (d_a - d_de).days
    con = _conectar()
    try:
        if reemplazar:
            con.execute(
                "DELETE FROM rota_turnos_trabajo WHERE semana = ?", (a_lunes,)
            )
        filas = con.execute(
            f"{_SELECT_TURNO_TRABAJO_ROTA} WHERE semana = ? ORDER BY fecha ASC, franja ASC",
            (de_lunes,),
        ).fetchall()
        creadas = 0
        ahora = datetime.now().isoformat(timespec="seconds")
        marcadores = ", ".join("?" for _ in _COLS_TURNO_TRABAJO_ROTA)
        for f in filas:
            fila = _fila_a_turno_trabajo_rota(f)
            # Desplaza la fecha +delta dias; si no parsea, salta esa fila.
            try:
                nueva_fecha = (date.fromisoformat(fila["fecha"]) + timedelta(days=delta)).isoformat()
            except (ValueError, TypeError):
                continue
            nuevo = {
                "id": uuid.uuid4().hex[:12],
                "semana": a_lunes,
                "fecha": nueva_fecha,
                "miembro_id": fila["miembro_id"],
                "miembro_nombre": fila["miembro_nombre"],
                "franja": fila["franja"],
                "estado": ESTADO_ROTA_PROPUESTO,
                "override": 1 if fila["override"] else 0,
                "motivo": fila["motivo"],
                "nota_relevo": fila["nota_relevo"],
                "creado": ahora,
                "actualizado": ahora,
            }
            con.execute(
                f"INSERT INTO rota_turnos_trabajo ({', '.join(_COLS_TURNO_TRABAJO_ROTA)}) "
                f"VALUES ({marcadores})",
                tuple(nuevo[col] for col in _COLS_TURNO_TRABAJO_ROTA),
            )
            creadas += 1
        con.commit()
    finally:
        con.close()
    return creadas


# --------------------------------------------------------------------------- #
# Cola de jobs de generacion (#130 Fase 2 / ADR 0002 Fase B)                    #
# --------------------------------------------------------------------------- #
#
# El back ENCOLA (`encolar_job`) y devuelve de inmediato; un WORKER (in-proceso en local,
# servicio aparte en hosted) CLAVA un pendiente (`reclamar_job`) y corre `claude -p`. La
# reclamacion es CONCURRENTE-SEGURA: en Postgres con `FOR UPDATE SKIP LOCKED` (varios
# workers no clavan el mismo job); en SQLite con un UPDATE GUARDADO condicional
# (`WHERE estado='pendiente'`) que, por el WAL + busy_timeout de `motor_db`, es atomico (el
# que gane el UPDATE se lleva la fila; los demas ven rowcount 0). La cancelacion viaja por
# la columna `cancelado` (el back la marca; el worker la lee y mata el arbol), de modo que
# funciona AUNQUE el worker sea otro proceso.

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

    Postgres: `SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1` dentro de la transaccion + UPDATE
    a `reclamado`; otro worker que corra a la vez salta esa fila (no la doble-ejecuta).
    SQLite: selecciona un candidato y lo CLAVA con un UPDATE GUARDADO
    (`WHERE id=? AND estado='pendiente'`); si dos workers eligen el mismo, solo uno tiene
    rowcount>0 (el otro reintenta). Devuelve `{id, gen_id, spec, ...}` del job clavado.
    """
    ahora = datetime.now().isoformat(timespec="seconds")
    con = _conectar()
    try:
        if motor_db.es_postgres():
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
        # SQLite: candidato + UPDATE guardado (atomico por el WAL/busy_timeout).
        while True:
            fila = con.execute(
                "SELECT id, gen_id, spec FROM jobs WHERE estado = ? "
                "ORDER BY creado ASC, id ASC LIMIT 1",
                (JOB_PENDIENTE,),
            ).fetchone()
            if fila is None:
                return None
            cur = con.execute(
                "UPDATE jobs SET estado = ?, worker = ?, claimed_at = ? "
                "WHERE id = ? AND estado = ?",
                (JOB_RECLAMADO, worker, ahora, fila["id"], JOB_PENDIENTE),
            )
            con.commit()
            if cur.rowcount > 0:
                return {"id": fila["id"], "gen_id": fila["gen_id"], "spec": fila["spec"]}
            # Otro worker lo clavo entre el SELECT y el UPDATE: reintenta con otro candidato.
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
