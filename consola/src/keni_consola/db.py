"""Persistencia local SQLite de la Consola Keni: dato OPERACIONAL (no editorial).

SQLite cubre lo que NO es contenido editable a mano: las `tareas` y el apartado
`comercial` (seguimiento de piezas + su serie temporal de snapshots). El CONTENIDO
editorial (publicaciones, plantillas, fuentes RSS, hashtags, franjas, historial de
skills) vive en ficheros YAML por marca (`ficheros.py`), con un indice SQLite
regenerable (`indice.py`). La fachada `repos.py` enruta cada cosa a su almacen.

La base vive en `~/.config/keni-social/consola.db` (o la ruta de la env var
`KENI_CONSOLA_DB`, util para tests). El esquema se crea ON-DEMAND en la primera
conexion (idempotente). En el primer arranque, si existe el viejo
`~/.config/keni-social/tareas.json`, sus tareas se MIGRAN a SQLite una sola vez
(best-effort, idempotente: si una tarea con ese id ya esta, no se duplica).

SEGURIDAD:
  - SIEMPRE consultas PARAMETRIZADAS (`?`), NUNCA f-strings con datos en el SQL.
  - La base es local; ninguna fila sale de la maquina.

Tablas:
  - `tareas`(id, proyecto, titulo, detalle, estado, fecha)
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

  La logica de auth (hashing, login, sesiones, bootstrap) vive en `auth.py`, que
  reutiliza la conexion de este modulo (`conectar`). El esquema de `usuarios`/
  `sesiones` se crea aqui (on-demand, idempotente) para que exista por cualquier
  via de arranque.

Las funciones devuelven `dict`s simples (filas) o ids, sin acoplar la capa API a
sqlite3. Cada operacion abre y cierra su propia conexion (la app es local y de
poca concurrencia; mantenerlo simple evita estado global y problemas de hilos con
el `TestClient`).

CONCURRENCIA (servicio compartido de una replica, #130): cada conexion abre en WAL
(`PRAGMA journal_mode=WAL`) para que lectores y un escritor convivan sin bloquearse, y
con `PRAGMA busy_timeout` para que la contencion espere (acotada) en vez de fallar al
instante con `database is locked`. Sirve para un servicio multiusuario de UNA replica.

FUTURO BACKEND POSTGRES (#130): para escalar a varias replicas SQLite no basta (un solo
fichero, un escritor). El plan es sustituir esta capa por Postgres. La capa esta acotada
(toda la persistencia operacional pasa por `conectar()` y consultas parametrizadas), asi
que el cambio se localiza aqui SIN tocar las firmas publicas. NO se implementa todavia:
solo se deja la nota y el punto de extension (`conectar()`).
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

# Allowlists de dominio (neutras, sin acoplar a SQLite): viven en `estados.py`.
from . import rutas
from .estados import (
    ESTADO_COMERCIAL_ACTIVA,
    ESTADOS_COMERCIAL,
    ESTADOS_TAREA,
    METRICAS_COMERCIAL,
)

__all__ = [
    "ESTADO_COMERCIAL_ACTIVA",
    "ESTADOS_COMERCIAL",
    "ESTADOS_TAREA",
    "METRICAS_COMERCIAL",
    "actualizar_estado_tarea",
    "actualizar_publicacion_comercial",
    "borrar_publicacion_comercial",
    "borrar_tarea",
    "conectar",
    "crear_publicacion_comercial",
    "crear_tarea",
    "listar_publicaciones_comerciales",
    "listar_snapshots_comerciales",
    "listar_tareas",
    "marcar_aviso_comercial",
    "obtener_publicacion_comercial",
    "obtener_tarea",
    "registrar_snapshot_comercial",
    "ruta_db",
    "ultimo_snapshot_comercial",
]


def ruta_db() -> Path:
    """Ruta del consola.db.

    `KENI_CONSOLA_DB` la sobreescribe (override de maxima prioridad; tests). Si no,
    cuelga de la raiz de estado unica (`rutas.dir_config()`): local
    `${XDG_CONFIG_HOME:-~/.config}/keni-social/consola.db`, o bajo `KENI_DATA_DIR`.
    """
    if (p := os.environ.get("KENI_CONSOLA_DB")):
        return Path(p).expanduser()
    return rutas.dir_config() / "consola.db"


# Espera (ms) ante contencion antes de fallar con `database is locked` (#130).
_BUSY_TIMEOUT_MS = 5000


def _conectar() -> sqlite3.Connection:
    """Abre la conexion a la base, crea el esquema on-demand y migra el JSON viejo.

    `row_factory = sqlite3.Row` para poder leer filas como mapeos por nombre.

    CONCURRENCIA (#130): WAL (`journal_mode=WAL`) deja convivir varios lectores con un
    escritor sin `database is locked`, y `busy_timeout` hace que la contencion espere
    (acotada) en vez de fallar al instante. Necesario para un servicio multiusuario de
    una replica. El WAL es persistente (queda fijado en el fichero), pero lo reafirmamos
    en cada conexion por idempotencia (la base es local y puede recrearse).
    """
    ruta = ruta_db()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(ruta), timeout=_BUSY_TIMEOUT_MS / 1000)
    con.row_factory = sqlite3.Row
    con.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA synchronous = NORMAL")
    _crear_esquema(con)
    _migrar_tareas_json(con)
    return con


def conectar() -> sqlite3.Connection:
    """Conexion publica a la base (mismo `_conectar`, expuesto para `auth.py`).

    El esquema de `usuarios`/`sesiones` se crea aqui igual que el resto de tablas,
    de modo que `auth.py` puede operar sin duplicar la creacion del esquema. Cada
    operacion abre/cierra su propia conexion (la app es local y de poca concurrencia).
    """
    return _conectar()


def _crear_esquema(con: sqlite3.Connection) -> None:
    """Crea las tablas operacionales si no existen (idempotente)."""
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS tareas (
            id        TEXT PRIMARY KEY,
            proyecto  TEXT NOT NULL,
            titulo    TEXT NOT NULL,
            detalle   TEXT NOT NULL DEFAULT '',
            estado    TEXT NOT NULL DEFAULT 'pendiente',
            fecha     TEXT NOT NULL DEFAULT ''
        );
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
        );
        CREATE TABLE IF NOT EXISTS comercial_snapshots (
            id              TEXT PRIMARY KEY,
            publicacion_id  TEXT NOT NULL,
            ts              TEXT NOT NULL,
            interacciones   INTEGER NOT NULL DEFAULT 0,
            alcance         INTEGER NOT NULL DEFAULT 0
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_comercial_snapshots_pub_ts
            ON comercial_snapshots (publicacion_id, ts);
        CREATE INDEX IF NOT EXISTS idx_comercial_snapshots_pub
            ON comercial_snapshots (publicacion_id);
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
        );
        CREATE TABLE IF NOT EXISTS sesiones (
            token       TEXT PRIMARY KEY,
            usuario_id  TEXT NOT NULL,
            creada      TEXT NOT NULL,
            ultimo_uso  TEXT NOT NULL,
            expira      TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sesiones_usuario
            ON sesiones (usuario_id);
        """
    )
    con.commit()


# --------------------------------------------------------------------------- #
# Migracion best-effort del viejo tareas.json                                  #
# --------------------------------------------------------------------------- #


def _ruta_tareas_json() -> Path:
    """Ruta del viejo tareas.json (misma convencion que la feature historica).

    `KENI_CONSOLA_TAREAS` la sobreescribe (tests); si no, cuelga de la raiz de estado
    unica (`rutas.dir_config()`), mismo subpath `keni-social/tareas.json` que antes.
    """
    if (p := os.environ.get("KENI_CONSOLA_TAREAS")):
        return Path(p).expanduser()
    return rutas.dir_config() / "tareas.json"


def _migrar_tareas_json(con: sqlite3.Connection) -> None:
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


def _fila_a_tarea(fila: sqlite3.Row) -> dict[str, Any]:
    """Convierte una fila de `tareas` en un dict simple."""
    return {
        "id": fila["id"],
        "proyecto": fila["proyecto"],
        "titulo": fila["titulo"],
        "detalle": fila["detalle"],
        "estado": fila["estado"],
        "fecha": fila["fecha"],
    }


def listar_tareas() -> list[dict[str, Any]]:
    """Todas las tareas, mas recientes primero (por fecha y luego id)."""
    con = _conectar()
    try:
        filas = con.execute(
            "SELECT id, proyecto, titulo, detalle, estado, fecha FROM tareas "
            "ORDER BY fecha DESC, id DESC"
        ).fetchall()
    finally:
        con.close()
    return [_fila_a_tarea(f) for f in filas]


def crear_tarea(proyecto_id: str, titulo: str, detalle: str = "") -> dict[str, Any]:
    """Inserta una tarea nueva y la devuelve. NO valida el proyecto (lo hace la API)."""
    tarea = {
        "id": uuid.uuid4().hex[:12],
        "proyecto": proyecto_id,
        "titulo": titulo,
        "detalle": detalle,
        "estado": "pendiente",
        "fecha": date.today().isoformat(),
    }
    con = _conectar()
    try:
        con.execute(
            "INSERT INTO tareas (id, proyecto, titulo, detalle, estado, fecha) "
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
    finally:
        con.close()
    return tarea


def obtener_tarea(tarea_id: str) -> dict[str, Any] | None:
    """Una tarea por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            "SELECT id, proyecto, titulo, detalle, estado, fecha FROM tareas WHERE id = ?",
            (tarea_id,),
        ).fetchone()
    finally:
        con.close()
    return _fila_a_tarea(fila) if fila is not None else None


def actualizar_estado_tarea(tarea_id: str, estado: str) -> dict[str, Any] | None:
    """Cambia el estado de una tarea; devuelve la tarea actualizada (None si no existe)."""
    con = _conectar()
    try:
        cur = con.execute(
            "UPDATE tareas SET estado = ? WHERE id = ?", (estado, tarea_id)
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            "SELECT id, proyecto, titulo, detalle, estado, fecha FROM tareas WHERE id = ?",
            (tarea_id,),
        ).fetchone()
    finally:
        con.close()
    return _fila_a_tarea(fila) if fila is not None else None


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


def _fila_a_comercial(fila: sqlite3.Row) -> dict[str, Any]:
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
    sql += " ORDER BY fecha_creacion DESC, rowid DESC"
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
