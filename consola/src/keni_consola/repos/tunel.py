"""Repositorio — túnel keni-fotos: registro compartido de conexiones + bus RPC cross-worker.

Persistencia (Postgres) del registro de WebSockets vivos (`tunel_conexiones`) y de la cola de
llamadas enrutadas al worker dueño (`tunel_rpc`), más el `pg_notify` que las coordina. Es SQL
puro (sin lógica del túnel, que vive en `fotos_tunel.py`): el barrel `repos.py` lo reexpone.

Las marcas/galerías/payload/resultado viajan como JSON en columnas TEXT (Postgres aguanta MB en
la columna; los timestamps son ISO UTC canónico). Los `NOTIFY` solo llevan el id del RPC: el
payload grande va SIEMPRE en la columna `resultado`, nunca en el aviso (límite 8 KB).
"""
from __future__ import annotations

from typing import Any

from ._comun import db


def tunel_upsert_conexion(
    *,
    id: str,
    worker: str,
    usuario: str,
    dispositivo: str,
    version: str,
    marcas: str,
    galerias: str,
    visto_en: str,
) -> None:
    """Da de alta o refresca la fila de una conexión viva (idempotente por `id`)."""
    con = db.conectar()
    try:
        con.execute(
            "INSERT INTO tunel_conexiones "
            "(id, worker, usuario, dispositivo, version, marcas, galerias, visto_en) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (id) DO UPDATE SET worker = excluded.worker, usuario = excluded.usuario, "
            "dispositivo = excluded.dispositivo, version = excluded.version, "
            "marcas = excluded.marcas, galerias = excluded.galerias, visto_en = excluded.visto_en",
            (id, worker, usuario, dispositivo, version, marcas, galerias, visto_en),
        )
        con.commit()
    finally:
        con.close()


def tunel_latido_conexion(id: str, visto_en: str) -> None:
    """Refresca el `visto_en` de una conexión (heartbeat ~20 s; mantiene la fila viva)."""
    con = db.conectar()
    try:
        con.execute("UPDATE tunel_conexiones SET visto_en = ? WHERE id = ?", (visto_en, id))
        con.commit()
    finally:
        con.close()


def tunel_baja_conexion(id: str) -> None:
    """Borra la fila de una conexión (la app se desconectó). Idempotente."""
    con = db.conectar()
    try:
        con.execute("DELETE FROM tunel_conexiones WHERE id = ?", (id,))
        con.commit()
    finally:
        con.close()


def tunel_conexiones_vivas(umbral: str) -> list[dict[str, Any]]:
    """Conexiones con `visto_en >= umbral` (las de workers vivos), recientes primero."""
    con = db.conectar()
    try:
        filas = con.execute(
            "SELECT id, worker, usuario, dispositivo, version, marcas, galerias, visto_en "
            "FROM tunel_conexiones WHERE visto_en >= ? ORDER BY visto_en DESC",
            (umbral,),
        ).fetchall()
        return [dict(f) for f in filas]
    finally:
        con.close()


def tunel_purgar_conexiones_muertas(umbral: str) -> int:
    """Borra las filas con `visto_en < umbral` (workers caídos). Devuelve cuántas quitó."""
    con = db.conectar()
    try:
        cur = con.execute("DELETE FROM tunel_conexiones WHERE visto_en < ?", (umbral,))
        con.commit()
        return cur.rowcount
    finally:
        con.close()


def tunel_usuarios_registrados(etiqueta: str, ahora: str) -> list[dict[str, Any]]:
    """Usuarios con un token de escritorio VIGENTE (`etiqueta`): los REGISTRADOS de la Galería.

    Vigente = no revocado y sin caducar (`expira` vacío o futuro). Devuelve `{usuario_id, usuario}`
    ordenado por nombre; el flag `online` lo decide el llamante cruzando con `tunel_conexiones`.
    """
    con = db.conectar()
    try:
        filas = con.execute(
            "SELECT DISTINCT u.id AS usuario_id, u.usuario AS usuario "
            "FROM tokens_mcp t JOIN usuarios u ON u.id = t.usuario_id "
            "WHERE t.etiqueta = ? AND t.revocado = 0 "
            "AND (t.expira IS NULL OR t.expira = '' OR t.expira > ?) "
            "ORDER BY u.usuario",
            (etiqueta, ahora),
        ).fetchall()
        return [dict(f) for f in filas]
    finally:
        con.close()


def tunel_notificar(canal: str, payload: str) -> None:
    """Emite un `NOTIFY <canal>, '<payload>'` (el payload solo lleva ids, nunca datos grandes)."""
    con = db.conectar()
    try:
        con.execute("SELECT pg_notify(?, ?)", (canal, payload))
        con.commit()
    finally:
        con.close()


def tunel_crear_rpc(*, id: str, tipo: str, conexion_id: str, payload: str, creado: str) -> None:
    """Encola un RPC `pendiente` dirigido a `conexion_id` (lo ejecuta su worker dueño)."""
    con = db.conectar()
    try:
        con.execute(
            "INSERT INTO tunel_rpc (id, tipo, conexion_id, payload, estado, resultado, creado) "
            "VALUES (?, ?, ?, ?, 'pendiente', '', ?)",
            (id, tipo, conexion_id, payload, creado),
        )
        con.commit()
    finally:
        con.close()


def tunel_leer_rpc(id: str) -> dict[str, Any] | None:
    """Lee una fila de RPC por id (con su `estado`/`resultado`), o None si ya no está."""
    con = db.conectar()
    try:
        fila = con.execute(
            "SELECT id, tipo, conexion_id, payload, estado, resultado, creado "
            "FROM tunel_rpc WHERE id = ?",
            (id,),
        ).fetchone()
        return dict(fila) if fila is not None else None
    finally:
        con.close()


def tunel_rpc_pendientes() -> list[dict[str, Any]]:
    """RPC aún `pendiente` (id + conexion_id): cada worker ejecuta los de SUS conexiones."""
    con = db.conectar()
    try:
        filas = con.execute(
            "SELECT id, conexion_id FROM tunel_rpc WHERE estado = 'pendiente'"
        ).fetchall()
        return [dict(f) for f in filas]
    finally:
        con.close()


def tunel_resolver_rpc(id: str, estado: str, resultado: str) -> bool:
    """Marca un RPC `pendiente` como `listo`/`error` con su `resultado`. True si lo cambió.

    Solo toca filas aún `pendiente` (claim-once): si otro worker ya lo resolvió, devuelve False.
    """
    con = db.conectar()
    try:
        cur = con.execute(
            "UPDATE tunel_rpc SET estado = ?, resultado = ? WHERE id = ? AND estado = 'pendiente'",
            (estado, resultado, id),
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def tunel_borrar_rpc(id: str) -> None:
    """Borra una fila de RPC ya consumida. Idempotente."""
    con = db.conectar()
    try:
        con.execute("DELETE FROM tunel_rpc WHERE id = ?", (id,))
        con.commit()
    finally:
        con.close()


def tunel_purgar_rpc_viejos(umbral: str) -> int:
    """Borra RPC con `creado < umbral` (peticiones colgadas/huérfanas). Devuelve cuántos quitó."""
    con = db.conectar()
    try:
        cur = con.execute("DELETE FROM tunel_rpc WHERE creado < ?", (umbral,))
        con.commit()
        return cur.rowcount
    finally:
        con.close()
