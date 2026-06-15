"""Persistencia — publicaciones y solicitudes de la Biblioteca de Texto (ver barrel `db.py`).

Modelo de PUBLICACION de la Biblioteca:

  - `texto_publicaciones`: cada fila es un acto de PUBLICAR un documento (`doc_id` de
    libtexto) fijando un `sha` git inmutable. La fila MAS RECIENTE por doc_id es el puntero
    de PRODUCCION vigente; el historial completo queda como audit log. Sin filas para un
    doc, los pipelines caen a la working copy (migracion suave).
  - `texto_solicitudes`: flujo editor -> admin. Un editor propone fijar `sha_propuesto`
    como produccion; el admin aprueba (publica + `aprobada`) o rechaza. A lo sumo UNA
    solicitud `abierta` por doc: crear una nueva SUSTITUYE a la abierta anterior.

Este modulo es persistencia PURA (mismo patron que `db_evergreen`): no valida documentos
ni shas (lo hace `api/texto`), no toca git (lo hace `versionado`).
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from ._db_comun import _conectar

# Estados de una solicitud de publicacion.
ESTADO_SOLICITUD_ABIERTA = "abierta"
ESTADO_SOLICITUD_APROBADA = "aprobada"
ESTADO_SOLICITUD_RECHAZADA = "rechazada"
ESTADOS_SOLICITUD_TEXTO = (
    ESTADO_SOLICITUD_ABIERTA,
    ESTADO_SOLICITUD_APROBADA,
    ESTADO_SOLICITUD_RECHAZADA,
)

_COLS_PUBLICACION = ("id", "doc_id", "sha", "autor", "nota", "creado")
_COLS_SOLICITUD = (
    "id", "doc_id", "sha_propuesto", "autor", "nota",
    "estado", "revisor", "comentario", "creado", "resuelto",
)


def _ahora_micros() -> str:
    """ISO UTC con MICROSEGUNDOS: el puntero de produccion es la fila mas reciente por
    `creado`, y el id es un uuid (no monotonico); los microsegundos desempatan dos
    publicaciones consecutivas dentro del mismo segundo (mismo patron que evergreen)."""
    return datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="microseconds")


def _fila_a_dict(fila: Any, cols: tuple[str, ...]) -> dict[str, Any]:
    return {col: fila[col] for col in cols}


# --------------------------------------------------------------------------- #
# Publicaciones (puntero de produccion + audit log)                            #
# --------------------------------------------------------------------------- #


def crear_texto_publicacion(
    *, doc_id: str, sha: str, autor: str = "", nota: str = ""
) -> dict[str, Any]:
    """Registra una publicacion (mueve el puntero de produccion de `doc_id` a `sha`).

    Devuelve la fila creada. NO borra las publicaciones anteriores: son el audit log
    (quien publico que y cuando); el puntero vigente es siempre la fila mas reciente.
    """
    fila = {
        "id": uuid4().hex[:12],
        "doc_id": doc_id,
        "sha": sha,
        "autor": autor or "",
        "nota": nota or "",
        "creado": _ahora_micros(),
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_PUBLICACION)
        con.execute(
            f"INSERT INTO texto_publicaciones ({', '.join(_COLS_PUBLICACION)}) VALUES ({marcadores})",
            tuple(fila[c] for c in _COLS_PUBLICACION),
        )
        con.commit()
    finally:
        con.close()
    return fila


def texto_produccion_de(doc_id: str) -> dict[str, Any] | None:
    """Puntero de PRODUCCION vigente de un documento (la publicacion mas reciente) o None."""
    con = _conectar()
    try:
        fila = con.execute(
            f"SELECT {', '.join(_COLS_PUBLICACION)} FROM texto_publicaciones "
            "WHERE doc_id = ? ORDER BY creado DESC, id DESC LIMIT 1",
            (doc_id,),
        ).fetchone()
    finally:
        con.close()
    return _fila_a_dict(fila, _COLS_PUBLICACION) if fila is not None else None


def texto_producciones() -> dict[str, dict[str, Any]]:
    """Mapa doc_id -> puntero de produccion vigente, para TODOS los docs publicados.

    Una sola consulta (`DISTINCT ON`, Postgres): la usan el listado de la Biblioteca y el
    ensamblaje por lote de adjuntos para no pagar una consulta por documento.
    """
    con = _conectar()
    try:
        filas = con.execute(
            f"SELECT DISTINCT ON (doc_id) {', '.join(_COLS_PUBLICACION)} "
            "FROM texto_publicaciones ORDER BY doc_id, creado DESC, id DESC"
        ).fetchall()
    finally:
        con.close()
    return {f["doc_id"]: _fila_a_dict(f, _COLS_PUBLICACION) for f in filas}


def historial_texto_publicaciones(doc_id: str, *, limite: int = 50) -> list[dict[str, Any]]:
    """Audit log de publicaciones de un documento (recientes primero)."""
    con = _conectar()
    try:
        filas = con.execute(
            f"SELECT {', '.join(_COLS_PUBLICACION)} FROM texto_publicaciones "
            "WHERE doc_id = ? ORDER BY creado DESC, id DESC LIMIT ?",
            (doc_id, max(1, min(limite, 500))),
        ).fetchall()
    finally:
        con.close()
    return [_fila_a_dict(f, _COLS_PUBLICACION) for f in filas]


# --------------------------------------------------------------------------- #
# Solicitudes de publicacion (editor -> admin)                                 #
# --------------------------------------------------------------------------- #


def crear_texto_solicitud(
    *, doc_id: str, sha_propuesto: str, autor: str = "", nota: str = ""
) -> dict[str, Any]:
    """Crea una solicitud ABIERTA para `doc_id`, SUSTITUYENDO la abierta anterior si la hay.

    Decision de diseno: una nueva solicitud sobre el mismo doc
    reemplaza a la abierta (la ultima propuesta del equipo es la que cuenta); las ya
    resueltas (aprobada/rechazada) se conservan como historial.
    """
    fila = {
        "id": uuid4().hex[:12],
        "doc_id": doc_id,
        "sha_propuesto": sha_propuesto,
        "autor": autor or "",
        "nota": nota or "",
        "estado": ESTADO_SOLICITUD_ABIERTA,
        "revisor": "",
        "comentario": "",
        "creado": _ahora_micros(),
        "resuelto": "",
    }
    con = _conectar()
    try:
        con.execute(
            "DELETE FROM texto_solicitudes WHERE doc_id = ? AND estado = ?",
            (doc_id, ESTADO_SOLICITUD_ABIERTA),
        )
        marcadores = ", ".join("?" for _ in _COLS_SOLICITUD)
        con.execute(
            f"INSERT INTO texto_solicitudes ({', '.join(_COLS_SOLICITUD)}) VALUES ({marcadores})",
            tuple(fila[c] for c in _COLS_SOLICITUD),
        )
        con.commit()
    finally:
        con.close()
    return fila


def listar_texto_solicitudes(estado: str | None = None) -> list[dict[str, Any]]:
    """Solicitudes de publicacion, recientes primero. `estado` (opcional) filtra."""
    sql = f"SELECT {', '.join(_COLS_SOLICITUD)} FROM texto_solicitudes"
    params: tuple[Any, ...] = ()
    if estado:
        sql += " WHERE estado = ?"
        params = (estado,)
    sql += " ORDER BY creado DESC, id DESC"
    con = _conectar()
    try:
        filas = con.execute(sql, params).fetchall()
    finally:
        con.close()
    return [_fila_a_dict(f, _COLS_SOLICITUD) for f in filas]


def obtener_texto_solicitud(solicitud_id: str) -> dict[str, Any] | None:
    """Una solicitud por id, o None si no existe."""
    con = _conectar()
    try:
        fila = con.execute(
            f"SELECT {', '.join(_COLS_SOLICITUD)} FROM texto_solicitudes WHERE id = ?",
            (solicitud_id,),
        ).fetchone()
    finally:
        con.close()
    return _fila_a_dict(fila, _COLS_SOLICITUD) if fila is not None else None


def resolver_texto_solicitud(
    solicitud_id: str, *, estado: str, revisor: str = "", comentario: str = ""
) -> dict[str, Any] | None:
    """Marca una solicitud ABIERTA como `aprobada`/`rechazada`. None si no estaba abierta.

    El UPDATE condiciona `estado = 'abierta'` (atomico): dos admins resolviendo a la vez no
    pueden resolverla dos veces; el segundo recibe None y la API responde 409.
    """
    con = _conectar()
    try:
        cur = con.execute(
            "UPDATE texto_solicitudes SET estado = ?, revisor = ?, comentario = ?, resuelto = ? "
            "WHERE id = ? AND estado = ?",
            (estado, revisor or "", comentario or "", _ahora_micros(),
             solicitud_id, ESTADO_SOLICITUD_ABIERTA),
        )
        con.commit()
        if getattr(cur, "rowcount", 0) == 0:
            return None
    finally:
        con.close()
    return obtener_texto_solicitud(solicitud_id)
