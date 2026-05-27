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
#
# `run` es un tipo ESPECIAL: ademas de localizar el YAML (`runs/<id>.yaml` por
# agente), DENORMALIZA las metricas de coste/tokens y el agente/fecha para que el
# monitor agregue (SUM/GROUP BY) SIN leer cuerpos. La fila de un run usa
# `id = "<agente>:<run_id>"` (unico bajo `tipo="run"` entre agentes), `marca` = el
# agente, mas las columnas extra (`agente`, `coste_usd`, `tokens_in`, `tokens_out`,
# `fecha_inicio`, `dia`). El resto de tipos no usa esas columnas (quedan a 0/'').
TIPOS: tuple[str, ...] = (
    "publicacion", "plantilla", "fuente_rss", "grupo_hashtags", "historial", "run",
)


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
            agente          TEXT NOT NULL DEFAULT '',
            coste_usd       REAL NOT NULL DEFAULT 0,
            tokens_in       INTEGER NOT NULL DEFAULT 0,
            tokens_out      INTEGER NOT NULL DEFAULT 0,
            fecha_inicio    TEXT NOT NULL DEFAULT '',
            dia             TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (tipo, id)
        )
        """
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_entradas_tipo_marca ON entradas (tipo, marca)")
    _migrar_columnas(con)
    con.commit()
    return con


# Columnas anadidas DESPUES del esquema original (denormalizacion de runs). Una BD
# de indice creada antes de #121 no las tiene; las anadimos en caliente con un
# `ALTER TABLE ADD COLUMN` idempotente (el indice es regenerable, asi que poblarlas
# lo hace el reindexado de runs; aqui solo garantizamos que la columna existe).
_COLS_EXTRA: tuple[tuple[str, str], ...] = (
    ("agente", "TEXT NOT NULL DEFAULT ''"),
    ("coste_usd", "REAL NOT NULL DEFAULT 0"),
    ("tokens_in", "INTEGER NOT NULL DEFAULT 0"),
    ("tokens_out", "INTEGER NOT NULL DEFAULT 0"),
    ("fecha_inicio", "TEXT NOT NULL DEFAULT ''"),
    ("dia", "TEXT NOT NULL DEFAULT ''"),
)


def _migrar_columnas(con: sqlite3.Connection) -> None:
    """Anade las columnas de denormalizacion de runs si una BD vieja no las tiene."""
    presentes = {fila["name"] for fila in con.execute("PRAGMA table_info(entradas)")}
    for nombre, definicion in _COLS_EXTRA:
        if nombre not in presentes:
            con.execute(f"ALTER TABLE entradas ADD COLUMN {nombre} {definicion}")


# --------------------------------------------------------------------------- #
# Escritura del indice (upsert / borrado)                                      #
# --------------------------------------------------------------------------- #


_COLS = (
    "id", "tipo", "marca", "ruta", "mtime", "red", "estado", "evergreen", "fecha",
    "fecha_creacion", "agente", "coste_usd", "tokens_in", "tokens_out", "fecha_inicio", "dia",
)


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
        entrada.get("agente", ""),
        float(entrada.get("coste_usd", 0) or 0),
        int(entrada.get("tokens_in", 0) or 0),
        int(entrada.get("tokens_out", 0) or 0),
        entrada.get("fecha_inicio", ""),
        entrada.get("dia", ""),
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
        "agente": fila["agente"],
        "coste_usd": fila["coste_usd"],
        "tokens_in": fila["tokens_in"],
        "tokens_out": fila["tokens_out"],
        "fecha_inicio": fila["fecha_inicio"],
        "dia": fila["dia"],
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


# Orden DETERMINISTA por tipo. Los runs (denormalizados) se ordenan por
# `fecha_inicio` desc (paridad con `agentes.listar_runs`/`listar_runs_globales`); el
# resto por su `fecha_creacion`/`fecha`. El `id` desc desempata siempre.
_ORDEN_RUN = "fecha_inicio DESC, id DESC"
_ORDEN_DEF = "fecha_creacion DESC, fecha DESC, id DESC"


def _orden_de(tipo: str) -> str:
    """Clausula ORDER BY (sin el prefijo) para un `tipo`."""
    return _ORDEN_RUN if tipo == "run" else _ORDEN_DEF


def _where(tipo: str, filtros: dict[str, Any] | None) -> tuple[str, list[Any]]:
    """Construye `(clausula_where, params)` para un `tipo` y unos filtros opcionales.

    Filtros soportados (igual semantica que el backend SQLite): `marca`, `red`,
    `estado`, `agente` (igualdad exacta de strings) y `evergreen` (bool). Es el
    chokepoint UNICO compartido por `listar` y `contar` para que paginar y contar
    apliquen EXACTAMENTE los mismos filtros.
    """
    filtros = filtros or {}
    clausulas = ["tipo = ?"]
    params: list[Any] = [tipo]
    for clave in ("marca", "red", "estado", "agente"):
        valor = filtros.get(clave)
        if valor:
            clausulas.append(f"{clave} = ?")
            params.append(valor)
    if filtros.get("evergreen") is not None:
        clausulas.append("evergreen = ?")
        params.append(1 if filtros["evergreen"] else 0)
    return " AND ".join(clausulas), params


def listar(
    tipo: str,
    *,
    filtros: dict[str, Any] | None = None,
    limite: int | None = None,
    desplazamiento: int | None = None,
) -> list[dict[str, Any]]:
    """Lista entradas indexadas de un `tipo`, con filtros y paginacion opcionales.

    Filtros soportados (igual semantica que el backend SQLite): `marca`, `red`,
    `estado`, `agente` (igualdad exacta de strings) y `evergreen` (bool). El orden es
    DETERMINISTA (ver `_orden_de`). El llamante carga luego el YAML por la `ruta`.

    `limite`/`desplazamiento` (offset-based): si `limite` es None se devuelve TODO el
    conjunto filtrado (comportamiento previo, retrocompatible); si viene, se aplica
    `LIMIT ? OFFSET ?` en SQL (la pagina sale SIN leer los cuerpos restantes).
    """
    where, params = _where(tipo, filtros)
    sql = f"SELECT * FROM entradas WHERE {where} ORDER BY {_orden_de(tipo)}"
    if limite is not None:
        sql += " LIMIT ? OFFSET ?"
        params.append(max(0, int(limite)))
        params.append(max(0, int(desplazamiento or 0)))
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_dict(f) for f in filas]


def contar(tipo: str, filtros: dict[str, Any] | None = None) -> int:
    """Cuenta entradas indexadas de un `tipo` con los MISMOS filtros que `listar`.

    Es el `total` del envelope de paginacion: el numero de filas que existirian sin
    `LIMIT/OFFSET`, para que el cliente sepa cuantas paginas hay. No lee cuerpos.
    """
    where, params = _where(tipo, filtros)
    con = _conectar()
    try:
        fila = con.execute(
            f"SELECT COUNT(*) AS n FROM entradas WHERE {where}", tuple(params)
        ).fetchone()
    finally:
        con.close()
    return int(fila["n"]) if fila is not None else 0


# --------------------------------------------------------------------------- #
# Agregacion de runs en SQL (SUM/GROUP BY sobre la denormalizacion)           #
# --------------------------------------------------------------------------- #


def agregados_runs() -> dict[str, Any]:
    """Agrega coste/tokens/runs de los runs INDEXADOS via SQL (SUM/GROUP BY).

    Devuelve `{total, por_agente, por_dia}` con la MISMA forma y orden que el
    full-scan de `agentes.agregados_runs` (paridad exacta de numeros):
      - `total`: `{coste_usd, tokens, runs}` global.
      - `por_agente`: `[{agente, coste_usd, tokens, runs}]`, de mayor a menor coste.
      - `por_dia`: `[{dia, coste_usd, tokens, runs}]`, dias recientes primero.
    `tokens = tokens_in + tokens_out`. El llamante completa `agente_nombre` (el
    nombre legible no se denormaliza: cambia al renombrar y se resuelve barato).
    """
    con = _conectar()
    try:
        total = con.execute(
            "SELECT COALESCE(SUM(coste_usd), 0) AS coste, "
            "COALESCE(SUM(tokens_in + tokens_out), 0) AS tokens, COUNT(*) AS runs "
            "FROM entradas WHERE tipo = 'run'"
        ).fetchone()
        por_agente = con.execute(
            "SELECT agente, COALESCE(SUM(coste_usd), 0) AS coste, "
            "COALESCE(SUM(tokens_in + tokens_out), 0) AS tokens, COUNT(*) AS runs "
            "FROM entradas WHERE tipo = 'run' GROUP BY agente "
            "ORDER BY coste DESC, agente ASC"
        ).fetchall()
        por_dia = con.execute(
            "SELECT dia, COALESCE(SUM(coste_usd), 0) AS coste, "
            "COALESCE(SUM(tokens_in + tokens_out), 0) AS tokens, COUNT(*) AS runs "
            "FROM entradas WHERE tipo = 'run' GROUP BY dia "
            "ORDER BY dia DESC"
        ).fetchall()
    finally:
        con.close()
    return {
        "total": {
            "coste_usd": float(total["coste"]),
            "tokens": int(total["tokens"]),
            "runs": int(total["runs"]),
        },
        "por_agente": [
            {
                "agente": f["agente"],
                "coste_usd": float(f["coste"]),
                "tokens": int(f["tokens"]),
                "runs": int(f["runs"]),
            }
            for f in por_agente
        ],
        "por_dia": [
            {
                "dia": f["dia"],
                "coste_usd": float(f["coste"]),
                "tokens": int(f["tokens"]),
                "runs": int(f["runs"]),
            }
            for f in por_dia
        ],
    }


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
