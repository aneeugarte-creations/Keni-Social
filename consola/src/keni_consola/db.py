"""Persistencia local SQLite de la Consola Keni (tareas + historial de skills).

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
  - `skill_historial`(id, skill, marca, fecha, resultado)
  - `publicaciones`(id, titulo, marca, red, contenido, estado, veredicto,
    fecha_creacion, fecha_actualizacion, fecha_programada, origen, imagen, evergreen)
  - `grupos_hashtags`(id, nombre, marca, hashtags)  [hashtags = JSON list]
  - `franjas`(id, marca, red, dia_semana, hora)  [dia 0=lunes..6=domingo, "HH:MM"]
  - `plantillas`(id, nombre, marca, red, contenido, fecha)
  - `fuentes_rss`(id, nombre, url, marca, fecha)

Las funciones devuelven `dict`s simples (filas) o ids, sin acoplar la capa API a
sqlite3. Cada operacion abre y cierra su propia conexion (la app es local y de
poca concurrencia; mantenerlo simple evita estado global y problemas de hilos con
el `TestClient`).
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import date
from pathlib import Path
from typing import Any

# Estados validos de una tarea (misma convencion que la feature historica).
ESTADOS_TAREA: tuple[str, ...] = ("pendiente", "hecha")

# Estados validos de una publicacion (flujo editorial borrador -> publicado).
ESTADOS_PUBLICACION: tuple[str, ...] = ("borrador", "aprobado", "programado", "publicado")


def ruta_db() -> Path:
    """Ruta del consola.db. `KENI_CONSOLA_DB` la sobreescribe (tests)."""
    if (p := os.environ.get("KENI_CONSOLA_DB")):
        return Path(p).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "keni-social" / "consola.db"


def _conectar() -> sqlite3.Connection:
    """Abre la conexion a la base, crea el esquema on-demand y migra el JSON viejo.

    `row_factory = sqlite3.Row` para poder leer filas como mapeos por nombre.
    """
    ruta = ruta_db()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(ruta))
    con.row_factory = sqlite3.Row
    _crear_esquema(con)
    _migrar_tareas_json(con)
    return con


def _crear_esquema(con: sqlite3.Connection) -> None:
    """Crea las tablas si no existen (idempotente)."""
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
        CREATE TABLE IF NOT EXISTS skill_historial (
            id         TEXT PRIMARY KEY,
            skill      TEXT NOT NULL,
            marca      TEXT NOT NULL,
            fecha      TEXT NOT NULL DEFAULT '',
            resultado  TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS publicaciones (
            id                    TEXT PRIMARY KEY,
            titulo                TEXT NOT NULL DEFAULT '',
            marca                 TEXT NOT NULL,
            red                   TEXT NOT NULL,
            contenido             TEXT NOT NULL DEFAULT '',
            estado                TEXT NOT NULL DEFAULT 'borrador',
            veredicto             TEXT NOT NULL DEFAULT '',
            fecha_creacion        TEXT NOT NULL DEFAULT '',
            fecha_actualizacion   TEXT NOT NULL DEFAULT '',
            fecha_programada      TEXT NOT NULL DEFAULT '',
            origen                TEXT NOT NULL DEFAULT '',
            imagen                TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS grupos_hashtags (
            id        TEXT PRIMARY KEY,
            nombre    TEXT NOT NULL,
            marca     TEXT NOT NULL DEFAULT '',
            hashtags  TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS franjas (
            id          TEXT PRIMARY KEY,
            marca       TEXT NOT NULL DEFAULT '',
            red         TEXT NOT NULL DEFAULT '',
            dia_semana  INTEGER NOT NULL DEFAULT 0,
            hora        TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS plantillas (
            id         TEXT PRIMARY KEY,
            nombre     TEXT NOT NULL,
            marca      TEXT NOT NULL DEFAULT '',
            red        TEXT NOT NULL DEFAULT '',
            contenido  TEXT NOT NULL DEFAULT '',
            fecha      TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS fuentes_rss (
            id      TEXT PRIMARY KEY,
            nombre  TEXT NOT NULL,
            url     TEXT NOT NULL,
            marca   TEXT NOT NULL DEFAULT '',
            fecha   TEXT NOT NULL DEFAULT ''
        );
        """
    )
    _migrar_columna_imagen(con)
    _migrar_columna_evergreen(con)
    con.commit()


def _migrar_columna_imagen(con: sqlite3.Connection) -> None:
    """Anade la columna `imagen` a `publicaciones` si una base antigua no la tiene.

    `CREATE TABLE IF NOT EXISTS` no toca tablas ya creadas, asi que una base de una
    version previa no tendria `imagen`. Aqui se anade con `ALTER TABLE ... ADD COLUMN`
    de forma idempotente (best-effort: comprobamos el esquema con PRAGMA antes).
    """
    cols = {fila["name"] for fila in con.execute("PRAGMA table_info(publicaciones)")}
    if "imagen" not in cols:
        con.execute("ALTER TABLE publicaciones ADD COLUMN imagen TEXT NOT NULL DEFAULT ''")


def _migrar_columna_evergreen(con: sqlite3.Connection) -> None:
    """Anade la columna `evergreen` a `publicaciones` si una base antigua no la tiene.

    Misma estrategia que `_migrar_columna_imagen`: `CREATE TABLE IF NOT EXISTS` no toca
    tablas ya creadas, asi que una base de una version previa no tendria `evergreen`.
    Se anade con `ALTER TABLE ... ADD COLUMN` de forma idempotente (PRAGMA antes).
    """
    cols = {fila["name"] for fila in con.execute("PRAGMA table_info(publicaciones)")}
    if "evergreen" not in cols:
        con.execute("ALTER TABLE publicaciones ADD COLUMN evergreen INTEGER NOT NULL DEFAULT 0")


# --------------------------------------------------------------------------- #
# Migracion best-effort del viejo tareas.json                                  #
# --------------------------------------------------------------------------- #


def _ruta_tareas_json() -> Path:
    """Ruta del viejo tareas.json (misma convencion que la feature historica)."""
    if (p := os.environ.get("KENI_CONSOLA_TAREAS")):
        return Path(p).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "keni-social" / "tareas.json"


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
# Historial de skills                                                          #
# --------------------------------------------------------------------------- #


def registrar_historial_skill(skill: str, marca: str, resultado: str) -> str:
    """Guarda una ejecucion de skill en el historial y devuelve su id."""
    hid = uuid.uuid4().hex[:12]
    con = _conectar()
    try:
        con.execute(
            "INSERT INTO skill_historial (id, skill, marca, fecha, resultado) "
            "VALUES (?, ?, ?, ?, ?)",
            (hid, skill, marca, date.today().isoformat(), resultado),
        )
        con.commit()
    finally:
        con.close()
    return hid


def listar_historial_skills() -> list[dict[str, Any]]:
    """Historial completo (sin el resultado entero, solo metadatos), recientes primero."""
    con = _conectar()
    try:
        filas = con.execute(
            "SELECT id, skill, marca, fecha, resultado FROM skill_historial "
            "ORDER BY rowid DESC"
        ).fetchall()
    finally:
        con.close()
    return [
        {
            "id": f["id"],
            "skill": f["skill"],
            "marca": f["marca"],
            "fecha": f["fecha"],
            "resultado": f["resultado"],
        }
        for f in filas
    ]


def obtener_historial_skill(historial_id: str) -> dict[str, Any] | None:
    """Una entrada del historial por id, con el resultado completo (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            "SELECT id, skill, marca, fecha, resultado FROM skill_historial WHERE id = ?",
            (historial_id,),
        ).fetchone()
    finally:
        con.close()
    if fila is None:
        return None
    return {
        "id": fila["id"],
        "skill": fila["skill"],
        "marca": fila["marca"],
        "fecha": fila["fecha"],
        "resultado": fila["resultado"],
    }


# --------------------------------------------------------------------------- #
# Publicaciones (posts a gestionar: titulo, red, estado, fechas)              #
# --------------------------------------------------------------------------- #

# Columnas de `publicaciones` en orden de declaracion (reusadas en SELECT/INSERT).
_COLS_PUBLICACION = (
    "id",
    "titulo",
    "marca",
    "red",
    "contenido",
    "estado",
    "veredicto",
    "fecha_creacion",
    "fecha_actualizacion",
    "fecha_programada",
    "origen",
    "imagen",
    "evergreen",
)
_SELECT_PUBLICACION = f"SELECT {', '.join(_COLS_PUBLICACION)} FROM publicaciones"

# Campos que la edicion parcial puede tocar (el resto es inmutable desde la API).
_CAMPOS_EDITABLES_PUBLICACION = (
    "titulo",
    "contenido",
    "estado",
    "fecha_programada",
    "imagen",
    "evergreen",
)


def _fila_a_publicacion(fila: sqlite3.Row) -> dict[str, Any]:
    """Convierte una fila de `publicaciones` en un dict simple (`evergreen` como bool)."""
    pub = {col: fila[col] for col in _COLS_PUBLICACION}
    pub["evergreen"] = bool(fila["evergreen"])
    return pub


def _normalizar_publicacion_entrada(datos: dict[str, Any]) -> dict[str, Any]:
    """Toma un dict de entrada y devuelve una fila lista para insertar.

    No valida marca/red/estado (eso es responsabilidad de la API contra sus
    allowlists); aqui solo se rellenan defaults, se genera id y se ponen fechas.
    """
    hoy = date.today().isoformat()
    estado = datos.get("estado") or "borrador"
    return {
        "id": uuid.uuid4().hex[:12],
        "titulo": datos.get("titulo") or "",
        "marca": datos.get("marca") or "",
        "red": datos.get("red") or "",
        "contenido": datos.get("contenido") or "",
        "estado": estado,
        "veredicto": datos.get("veredicto") or "",
        "fecha_creacion": hoy,
        "fecha_actualizacion": hoy,
        "fecha_programada": datos.get("fecha_programada") or "",
        "origen": datos.get("origen") or "",
        "imagen": datos.get("imagen") or "",
        "evergreen": bool(datos.get("evergreen")),
    }


def _valor_columna_publicacion(fila: dict[str, Any], col: str) -> Any:
    """Valor de `col` listo para SQLite (`evergreen` bool -> 0/1; el resto tal cual)."""
    if col == "evergreen":
        return 1 if fila["evergreen"] else 0
    return fila[col]


def _insertar_publicacion(con: sqlite3.Connection, fila: dict[str, Any]) -> None:
    """Inserta una fila ya normalizada de publicacion (consulta parametrizada)."""
    marcadores = ", ".join("?" for _ in _COLS_PUBLICACION)
    con.execute(
        f"INSERT INTO publicaciones ({', '.join(_COLS_PUBLICACION)}) VALUES ({marcadores})",
        tuple(_valor_columna_publicacion(fila, col) for col in _COLS_PUBLICACION),
    )


def crear_publicacion(
    marca: str,
    red: str,
    *,
    titulo: str = "",
    contenido: str = "",
    estado: str = "borrador",
    veredicto: str = "",
    fecha_programada: str = "",
    origen: str = "",
    imagen: str = "",
    evergreen: bool = False,
) -> dict[str, Any]:
    """Inserta una publicacion nueva y la devuelve. NO valida marca/red/estado (lo hace la API)."""
    fila = _normalizar_publicacion_entrada(
        {
            "titulo": titulo,
            "marca": marca,
            "red": red,
            "contenido": contenido,
            "estado": estado,
            "veredicto": veredicto,
            "fecha_programada": fecha_programada,
            "origen": origen,
            "imagen": imagen,
            "evergreen": evergreen,
        }
    )
    con = _conectar()
    try:
        _insertar_publicacion(con, fila)
        con.commit()
    finally:
        con.close()
    return fila


def crear_publicaciones(lista: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Inserta varias publicaciones en una sola transaccion y las devuelve.

    Cada elemento es un dict de entrada (marca/red obligatorias; el resto opcional).
    NO valida marca/red/estado (lo hace la API). Lista vacia => no toca la base.
    """
    if not lista:
        return []
    filas = [_normalizar_publicacion_entrada(d) for d in lista]
    con = _conectar()
    try:
        for fila in filas:
            _insertar_publicacion(con, fila)
        con.commit()
    finally:
        con.close()
    return filas


def listar_publicaciones(
    marca: str | None = None,
    red: str | None = None,
    estado: str | None = None,
    evergreen: bool | None = None,
) -> list[dict[str, Any]]:
    """Publicaciones (mas recientes primero), con filtros opcionales por marca/red/estado/evergreen."""
    clausulas: list[str] = []
    params: list[Any] = []
    if marca:
        clausulas.append("marca = ?")
        params.append(marca)
    if red:
        clausulas.append("red = ?")
        params.append(red)
    if estado:
        clausulas.append("estado = ?")
        params.append(estado)
    if evergreen is not None:
        clausulas.append("evergreen = ?")
        params.append(1 if evergreen else 0)
    sql = _SELECT_PUBLICACION
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)
    sql += " ORDER BY fecha_creacion DESC, rowid DESC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_publicacion(f) for f in filas]


def obtener_publicacion(publicacion_id: str) -> dict[str, Any] | None:
    """Una publicacion por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_PUBLICACION} WHERE id = ?", (publicacion_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_publicacion(fila) if fila is not None else None


def actualizar_publicacion(
    publicacion_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita parcialmente una publicacion (titulo/contenido/estado/fecha_programada).

    Ignora cualquier otra clave del dict. Pone `fecha_actualizacion` al dia de hoy.
    Devuelve la publicacion actualizada, o None si el id no existe.
    """
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_PUBLICACION}
    if "evergreen" in cambios:
        cambios["evergreen"] = 1 if cambios["evergreen"] else 0
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("fecha_actualizacion = ?")
    params: list[Any] = list(cambios.values())
    params.append(date.today().isoformat())
    params.append(publicacion_id)
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE publicaciones SET {', '.join(asignaciones)} WHERE id = ?",
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            f"{_SELECT_PUBLICACION} WHERE id = ?", (publicacion_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_publicacion(fila) if fila is not None else None


def borrar_publicacion(publicacion_id: str) -> bool:
    """Borra una publicacion; True si existia, False si no."""
    con = _conectar()
    try:
        cur = con.execute("DELETE FROM publicaciones WHERE id = ?", (publicacion_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# Grupos de hashtags (nombre + marca + lista de hashtags como JSON)            #
# --------------------------------------------------------------------------- #


def _fila_a_grupo_hashtags(fila: sqlite3.Row) -> dict[str, Any]:
    """Convierte una fila de `grupos_hashtags` en un dict (hashtags ya como lista)."""
    crudo = fila["hashtags"] or "[]"
    try:
        tags = json.loads(crudo)
    except (json.JSONDecodeError, ValueError):
        tags = []
    if not isinstance(tags, list):
        tags = []
    return {
        "id": fila["id"],
        "nombre": fila["nombre"],
        "marca": fila["marca"],
        "hashtags": [t for t in tags if isinstance(t, str)],
    }


def listar_grupos_hashtags() -> list[dict[str, Any]]:
    """Todos los grupos de hashtags (mas recientes primero por rowid)."""
    con = _conectar()
    try:
        filas = con.execute(
            "SELECT id, nombre, marca, hashtags FROM grupos_hashtags ORDER BY rowid DESC"
        ).fetchall()
    finally:
        con.close()
    return [_fila_a_grupo_hashtags(f) for f in filas]


def obtener_grupo_hashtags(grupo_id: str) -> dict[str, Any] | None:
    """Un grupo de hashtags por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            "SELECT id, nombre, marca, hashtags FROM grupos_hashtags WHERE id = ?",
            (grupo_id,),
        ).fetchone()
    finally:
        con.close()
    return _fila_a_grupo_hashtags(fila) if fila is not None else None


def crear_grupo_hashtags(
    nombre: str, marca: str = "", hashtags: list[str] | None = None
) -> dict[str, Any]:
    """Inserta un grupo de hashtags y lo devuelve. NO valida marca (lo hace la API)."""
    tags = [t for t in (hashtags or []) if isinstance(t, str)]
    grupo = {
        "id": uuid.uuid4().hex[:12],
        "nombre": nombre,
        "marca": marca,
        "hashtags": tags,
    }
    con = _conectar()
    try:
        con.execute(
            "INSERT INTO grupos_hashtags (id, nombre, marca, hashtags) VALUES (?, ?, ?, ?)",
            (grupo["id"], grupo["nombre"], grupo["marca"], json.dumps(tags)),
        )
        con.commit()
    finally:
        con.close()
    return grupo


def actualizar_grupo_hashtags(
    grupo_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita parcialmente un grupo (nombre/marca/hashtags); None si el id no existe.

    `hashtags` se serializa a JSON. Ignora cualquier otra clave del dict.
    """
    asignaciones: list[str] = []
    params: list[Any] = []
    if "nombre" in campos:
        asignaciones.append("nombre = ?")
        params.append(campos["nombre"])
    if "marca" in campos:
        asignaciones.append("marca = ?")
        params.append(campos["marca"])
    if "hashtags" in campos:
        tags = [t for t in (campos["hashtags"] or []) if isinstance(t, str)]
        asignaciones.append("hashtags = ?")
        params.append(json.dumps(tags))
    if not asignaciones:
        return obtener_grupo_hashtags(grupo_id)
    params.append(grupo_id)
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE grupos_hashtags SET {', '.join(asignaciones)} WHERE id = ?",
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            "SELECT id, nombre, marca, hashtags FROM grupos_hashtags WHERE id = ?",
            (grupo_id,),
        ).fetchone()
    finally:
        con.close()
    return _fila_a_grupo_hashtags(fila) if fila is not None else None


def borrar_grupo_hashtags(grupo_id: str) -> bool:
    """Borra un grupo de hashtags; True si existia, False si no."""
    con = _conectar()
    try:
        cur = con.execute("DELETE FROM grupos_hashtags WHERE id = ?", (grupo_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# Franjas horarias (colas: marca/red opcionales + dia_semana 0..6 + hora HH:MM) #
# --------------------------------------------------------------------------- #


def _fila_a_franja(fila: sqlite3.Row) -> dict[str, Any]:
    """Convierte una fila de `franjas` en un dict simple."""
    return {
        "id": fila["id"],
        "marca": fila["marca"],
        "red": fila["red"],
        "dia_semana": fila["dia_semana"],
        "hora": fila["hora"],
    }


def listar_franjas() -> list[dict[str, Any]]:
    """Todas las franjas, ordenadas por dia y hora (luego id, deterministico)."""
    con = _conectar()
    try:
        filas = con.execute(
            "SELECT id, marca, red, dia_semana, hora FROM franjas "
            "ORDER BY dia_semana ASC, hora ASC, id ASC"
        ).fetchall()
    finally:
        con.close()
    return [_fila_a_franja(f) for f in filas]


def crear_franja(
    dia_semana: int, hora: str, marca: str = "", red: str = ""
) -> dict[str, Any]:
    """Inserta una franja y la devuelve. NO valida (lo hace la API)."""
    franja = {
        "id": uuid.uuid4().hex[:12],
        "marca": marca,
        "red": red,
        "dia_semana": dia_semana,
        "hora": hora,
    }
    con = _conectar()
    try:
        con.execute(
            "INSERT INTO franjas (id, marca, red, dia_semana, hora) VALUES (?, ?, ?, ?, ?)",
            (franja["id"], franja["marca"], franja["red"], franja["dia_semana"], franja["hora"]),
        )
        con.commit()
    finally:
        con.close()
    return franja


def borrar_franja(franja_id: str) -> bool:
    """Borra una franja; True si existia, False si no."""
    con = _conectar()
    try:
        cur = con.execute("DELETE FROM franjas WHERE id = ?", (franja_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# Plantillas de post (nombre + marca/red opcionales + contenido reutilizable)  #
# --------------------------------------------------------------------------- #


def _fila_a_plantilla(fila: sqlite3.Row) -> dict[str, Any]:
    """Convierte una fila de `plantillas` en un dict simple."""
    return {
        "id": fila["id"],
        "nombre": fila["nombre"],
        "marca": fila["marca"],
        "red": fila["red"],
        "contenido": fila["contenido"],
        "fecha": fila["fecha"],
    }


def listar_plantillas() -> list[dict[str, Any]]:
    """Todas las plantillas (mas recientes primero por fecha y luego rowid)."""
    con = _conectar()
    try:
        filas = con.execute(
            "SELECT id, nombre, marca, red, contenido, fecha FROM plantillas "
            "ORDER BY fecha DESC, rowid DESC"
        ).fetchall()
    finally:
        con.close()
    return [_fila_a_plantilla(f) for f in filas]


def obtener_plantilla(plantilla_id: str) -> dict[str, Any] | None:
    """Una plantilla por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            "SELECT id, nombre, marca, red, contenido, fecha FROM plantillas WHERE id = ?",
            (plantilla_id,),
        ).fetchone()
    finally:
        con.close()
    return _fila_a_plantilla(fila) if fila is not None else None


def crear_plantilla(
    nombre: str, marca: str = "", red: str = "", contenido: str = ""
) -> dict[str, Any]:
    """Inserta una plantilla y la devuelve. NO valida marca/red (lo hace la API)."""
    plantilla = {
        "id": uuid.uuid4().hex[:12],
        "nombre": nombre,
        "marca": marca,
        "red": red,
        "contenido": contenido,
        "fecha": date.today().isoformat(),
    }
    con = _conectar()
    try:
        con.execute(
            "INSERT INTO plantillas (id, nombre, marca, red, contenido, fecha) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                plantilla["id"],
                plantilla["nombre"],
                plantilla["marca"],
                plantilla["red"],
                plantilla["contenido"],
                plantilla["fecha"],
            ),
        )
        con.commit()
    finally:
        con.close()
    return plantilla


def actualizar_plantilla(
    plantilla_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita parcialmente una plantilla (nombre/marca/red/contenido); None si no existe.

    Ignora cualquier otra clave del dict. Sin campos editables, devuelve la plantilla
    tal cual (no falla).
    """
    editables = ("nombre", "marca", "red", "contenido")
    cambios = {k: v for k, v in campos.items() if k in editables}
    if not cambios:
        return obtener_plantilla(plantilla_id)
    asignaciones = [f"{k} = ?" for k in cambios]
    params: list[Any] = list(cambios.values())
    params.append(plantilla_id)
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE plantillas SET {', '.join(asignaciones)} WHERE id = ?",
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            "SELECT id, nombre, marca, red, contenido, fecha FROM plantillas WHERE id = ?",
            (plantilla_id,),
        ).fetchone()
    finally:
        con.close()
    return _fila_a_plantilla(fila) if fila is not None else None


def borrar_plantilla(plantilla_id: str) -> bool:
    """Borra una plantilla; True si existia, False si no."""
    con = _conectar()
    try:
        cur = con.execute("DELETE FROM plantillas WHERE id = ?", (plantilla_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# Fuentes RSS (nombre + url + marca opcional)                                  #
# --------------------------------------------------------------------------- #


def _fila_a_fuente_rss(fila: sqlite3.Row) -> dict[str, Any]:
    """Convierte una fila de `fuentes_rss` en un dict simple."""
    return {
        "id": fila["id"],
        "nombre": fila["nombre"],
        "url": fila["url"],
        "marca": fila["marca"],
        "fecha": fila["fecha"],
    }


def listar_fuentes_rss() -> list[dict[str, Any]]:
    """Todas las fuentes RSS (mas recientes primero por fecha y luego rowid)."""
    con = _conectar()
    try:
        filas = con.execute(
            "SELECT id, nombre, url, marca, fecha FROM fuentes_rss "
            "ORDER BY fecha DESC, rowid DESC"
        ).fetchall()
    finally:
        con.close()
    return [_fila_a_fuente_rss(f) for f in filas]


def obtener_fuente_rss(fuente_id: str) -> dict[str, Any] | None:
    """Una fuente RSS por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            "SELECT id, nombre, url, marca, fecha FROM fuentes_rss WHERE id = ?",
            (fuente_id,),
        ).fetchone()
    finally:
        con.close()
    return _fila_a_fuente_rss(fila) if fila is not None else None


def crear_fuente_rss(nombre: str, url: str, marca: str = "") -> dict[str, Any]:
    """Inserta una fuente RSS y la devuelve. NO valida url/marca (lo hace la API)."""
    fuente = {
        "id": uuid.uuid4().hex[:12],
        "nombre": nombre,
        "url": url,
        "marca": marca,
        "fecha": date.today().isoformat(),
    }
    con = _conectar()
    try:
        con.execute(
            "INSERT INTO fuentes_rss (id, nombre, url, marca, fecha) VALUES (?, ?, ?, ?, ?)",
            (fuente["id"], fuente["nombre"], fuente["url"], fuente["marca"], fuente["fecha"]),
        )
        con.commit()
    finally:
        con.close()
    return fuente


def borrar_fuente_rss(fuente_id: str) -> bool:
    """Borra una fuente RSS; True si existia, False si no."""
    con = _conectar()
    try:
        cur = con.execute("DELETE FROM fuentes_rss WHERE id = ?", (fuente_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()
