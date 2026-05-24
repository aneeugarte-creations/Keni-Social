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
        """
    )
    con.commit()


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
