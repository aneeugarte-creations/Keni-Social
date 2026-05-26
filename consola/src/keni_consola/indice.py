"""Indice REGENERABLE del backend de ficheros (NO es la fuente de verdad).

La fuente de verdad son los ficheros YAML por marca (ver `ficheros.py`). Este
modulo mantiene un SQLite de SOLO indice que mapea cada entidad de contenido a
`(marca, tipo, ruta)` y guarda los campos FILTRABLES (red, estado, evergreen,
fechas) para resolver `obtener_X(id)` directo y `listar_X(filtros)` rapido sin
escanear todo el disco.

CONTRATO:
  - El indice se puede BORRAR en cualquier momento: se regenera leyendo los YAML.
  - Al escribir un YAML, el backend actualiza el indice (upsert/delete).
  - Si un YAML cambia POR FUERA (mtime distinto al indexado), se re-indexa esa
    entrada al consultarla; un escaneo completo sincroniza altas/bajas en disco.
  - Vive en `~/.config/keni-social/indice.sqlite` (env `KENI_CONSOLA_INDICE`).

Tabla unica `entradas`:
  id, tipo, marca, ruta, mtime, red, estado, evergreen, fecha, fecha_creacion

`tipo` ∈ {publicacion, plantilla, fuente_rss, grupo_hashtags, historial}.
Las franjas NO se indexan (viven en un unico fichero lista por marca; se leen
escaneando esos ficheros, que son pocos). Los items RSS vistos tampoco (viven en
`.keni/rss-vistos.yaml` por marca).

SEGURIDAD: SIEMPRE consultas parametrizadas. La base es local y derivada; ninguna
fila es autoritativa.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

# Tipos de entidad indexados (cada uno tiene su sub-carpeta por marca).
TIPOS: tuple[str, ...] = ("publicacion", "plantilla", "fuente_rss", "grupo_hashtags", "historial")


def ruta_indice() -> Path:
    """Ruta del SQLite de indice. `KENI_CONSOLA_INDICE` la sobreescribe (tests)."""
    if (p := os.environ.get("KENI_CONSOLA_INDICE")):
        return Path(p).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "keni-social" / "indice.sqlite"


def _conectar() -> sqlite3.Connection:
    """Abre la conexion al indice y crea el esquema on-demand (idempotente).

    Concurrencia: la consola lanza jobs en hilos de fondo que escriben contenido
    (y por tanto el indice) mientras la UI lee. Para no caer en `database is
    locked` se abre en WAL (lectores y un escritor conviven) con `busy_timeout`
    (espera acotada ante contencion en vez de fallar al instante). El esquema se
    asegura en cada conexion a proposito: el indice es REGENERABLE y puede
    borrarse en caliente, asi que `CREATE TABLE IF NOT EXISTS` debe sobrevivir a
    que el fichero desaparezca entre operaciones.
    """
    ruta = ruta_indice()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(ruta), timeout=5.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout = 5000")
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA synchronous = NORMAL")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS entradas (
            id              TEXT NOT NULL,
            tipo            TEXT NOT NULL,
            marca           TEXT NOT NULL DEFAULT '',
            ruta            TEXT NOT NULL,
            mtime           REAL NOT NULL DEFAULT 0,
            red             TEXT NOT NULL DEFAULT '',
            estado          TEXT NOT NULL DEFAULT '',
            evergreen       INTEGER NOT NULL DEFAULT 0,
            fecha           TEXT NOT NULL DEFAULT '',
            fecha_creacion  TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (tipo, id)
        )
        """
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_entradas_tipo_marca ON entradas (tipo, marca)")
    con.commit()
    return con


# --------------------------------------------------------------------------- #
# Escritura del indice (upsert / borrado)                                      #
# --------------------------------------------------------------------------- #


_COLS = ("id", "tipo", "marca", "ruta", "mtime", "red", "estado", "evergreen", "fecha", "fecha_creacion")


def upsert(entrada: dict[str, Any]) -> None:
    """Inserta o reemplaza una entrada del indice (`INSERT OR REPLACE` por (tipo, id))."""
    con = _conectar()
    try:
        _upsert_con(con, entrada)
        con.commit()
    finally:
        con.close()


def _upsert_con(con: sqlite3.Connection, entrada: dict[str, Any]) -> None:
    """Upsert dentro de una conexion ya abierta (sin commit)."""
    valores = (
        entrada["id"],
        entrada["tipo"],
        entrada.get("marca", ""),
        entrada["ruta"],
        float(entrada.get("mtime", 0)),
        entrada.get("red", ""),
        entrada.get("estado", ""),
        1 if entrada.get("evergreen") else 0,
        entrada.get("fecha", ""),
        entrada.get("fecha_creacion", ""),
    )
    marcadores = ", ".join("?" for _ in _COLS)
    con.execute(
        f"INSERT OR REPLACE INTO entradas ({', '.join(_COLS)}) VALUES ({marcadores})",
        valores,
    )


def borrar(tipo: str, entidad_id: str) -> None:
    """Elimina una entrada del indice por (tipo, id). Best-effort (no falla si falta)."""
    con = _conectar()
    try:
        con.execute("DELETE FROM entradas WHERE tipo = ? AND id = ?", (tipo, entidad_id))
        con.commit()
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# Lectura del indice                                                          #
# --------------------------------------------------------------------------- #


def _fila_a_dict(fila: sqlite3.Row) -> dict[str, Any]:
    """Convierte una fila del indice en un dict (evergreen como bool)."""
    return {
        "id": fila["id"],
        "tipo": fila["tipo"],
        "marca": fila["marca"],
        "ruta": fila["ruta"],
        "mtime": fila["mtime"],
        "red": fila["red"],
        "estado": fila["estado"],
        "evergreen": bool(fila["evergreen"]),
        "fecha": fila["fecha"],
        "fecha_creacion": fila["fecha_creacion"],
    }


def obtener(tipo: str, entidad_id: str) -> dict[str, Any] | None:
    """Devuelve la entrada del indice por (tipo, id), o None si no esta indexada."""
    con = _conectar()
    try:
        fila = con.execute(
            "SELECT * FROM entradas WHERE tipo = ? AND id = ?", (tipo, entidad_id)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_dict(fila) if fila is not None else None


def listar(tipo: str, *, filtros: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Lista entradas indexadas de un `tipo`, con filtros opcionales.

    Filtros soportados (igual semantica que el backend SQLite): `marca`, `red`,
    `estado` (igualdad exacta de strings) y `evergreen` (bool). El orden es
    DETERMINISTA: `fecha_creacion DESC, fecha DESC, id DESC` (cae a `id` para los
    tipos sin fecha_creacion). El llamante carga luego el YAML por la `ruta`.
    """
    filtros = filtros or {}
    clausulas = ["tipo = ?"]
    params: list[Any] = [tipo]
    for clave in ("marca", "red", "estado"):
        valor = filtros.get(clave)
        if valor:
            clausulas.append(f"{clave} = ?")
            params.append(valor)
    if filtros.get("evergreen") is not None:
        clausulas.append("evergreen = ?")
        params.append(1 if filtros["evergreen"] else 0)
    sql = (
        "SELECT * FROM entradas WHERE "
        + " AND ".join(clausulas)
        + " ORDER BY fecha_creacion DESC, fecha DESC, id DESC"
    )
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_dict(f) for f in filas]


def reemplazar_tipo(tipo: str, entradas: list[dict[str, Any]]) -> None:
    """Reemplaza TODAS las entradas indexadas de un `tipo` por las dadas (en una tx).

    Se usa al reconstruir el indice desde disco: borra lo viejo de ese tipo y
    vuelca lo encontrado. Atomico (transaccion unica).
    """
    con = _conectar()
    try:
        con.execute("DELETE FROM entradas WHERE tipo = ?", (tipo,))
        for entrada in entradas:
            _upsert_con(con, entrada)
        con.commit()
    finally:
        con.close()
