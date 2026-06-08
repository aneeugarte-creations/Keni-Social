"""Persistencia — dominio editor: versiones de documento (historial por pieza). Ver barrel `db.py`."""
from __future__ import annotations

from ._comun import Any, IntegrityError, _conectar, datetime, uuid

# --------------------------------------------------------------------------- #
# Versiones de documento (historial del editor por pieza)                        #
# --------------------------------------------------------------------------- #

_COLS_DOC_VERSIONES = (
    "id",
    "contenido_id",
    "plataforma_id",
    "version",
    "documento",
    "render_objeto",
    "autor_id",
    "autor_nombre",
    "creado",
)
_SELECT_DOC_VERSIONES = f"SELECT {', '.join(_COLS_DOC_VERSIONES)} FROM documento_versiones"


def _fila_a_doc_version(fila: Any) -> dict[str, Any]:
    item: dict[str, Any] = {col: fila[col] for col in _COLS_DOC_VERSIONES}
    item["documento"] = fila["documento"] or "{}"
    return item


# Tope de reintentos del contador de versiones ante choques de version concurrentes. Cada
# choque significa que OTRA edicion gano esa version; releemos el MAX y probamos la siguiente.
# Generoso a proposito: en el peor caso de N escritores simultaneos, un escritor puede perder
# hasta ~N-1 carreras antes de clavar su numero, asi que el tope debe holgar sobre la
# concurrencia realista de editores sobre UNA misma pieza (siempre baja en este producto).
_MAX_REINTENTOS_VERSION = 32


def crear_documento_version(
    *,
    contenido_id: str,
    plataforma_id: str,
    documento: str,
    render_objeto: str = "",
    autor: dict[str, str] | None = None,
    id: str = "",
    creado: str = "",
) -> dict[str, Any]:
    """Apende una versión del documento de una pieza (version = max+1 para esa pieza).

    CONTADOR SEGURO ANTE CONCURRENCIA: `MAX(version)+1` + INSERT bajo el indice UNICO
    `(contenido_id, plataforma_id, version)`. Si dos ediciones simultaneas calculan el MISMO
    numero, una gana y la otra recibe una UniqueViolation; aqui REINTENTAMOS (bucle acotado)
    recalculando el siguiente numero, en vez de duplicar la version (que rompia el historial).
    """
    autor = autor or {}
    ahora = datetime.now().isoformat(timespec="seconds")
    fila_id = id or uuid.uuid4().hex[:12]
    con = _conectar()
    try:
        ultimo_error: Exception | None = None
        for _ in range(_MAX_REINTENTOS_VERSION):
            fila_max = con.execute(
                "SELECT COALESCE(MAX(version), 0) AS m FROM documento_versiones "
                "WHERE contenido_id = ? AND plataforma_id = ?",
                (contenido_id, plataforma_id),
            ).fetchone()
            siguiente = int(fila_max["m"]) + 1
            fila = {
                "id": fila_id,
                "contenido_id": contenido_id or "",
                "plataforma_id": plataforma_id or "",
                "version": siguiente,
                "documento": documento or "{}",
                "render_objeto": render_objeto or "",
                "autor_id": autor.get("id", "") or "",
                "autor_nombre": autor.get("usuario", "") or "",
                "creado": creado or ahora,
            }
            marcadores = ", ".join("?" for _ in _COLS_DOC_VERSIONES)
            try:
                con.execute(
                    f"INSERT INTO documento_versiones ({', '.join(_COLS_DOC_VERSIONES)}) VALUES ({marcadores})",
                    tuple(fila[col] for col in _COLS_DOC_VERSIONES),
                )
                con.commit()
                return _fila_a_doc_version(fila)
            except IntegrityError as e:
                # Choque de version (otra edicion gano la carrera): el shim ya hizo rollback;
                # reintentamos releyendo el MAX para coger el numero siguiente.
                ultimo_error = e
        raise RuntimeError(
            "No se pudo asignar una version de documento tras varios reintentos "
            f"(contenido={contenido_id}, plataforma={plataforma_id})"
        ) from ultimo_error
    finally:
        con.close()


def listar_documento_versiones(contenido_id: str, plataforma_id: str) -> list[dict[str, Any]]:
    """Versiones de una pieza, mas reciente primero."""
    con = _conectar()
    try:
        filas = con.execute(
            f"{_SELECT_DOC_VERSIONES} WHERE contenido_id = ? AND plataforma_id = ? "
            "ORDER BY version DESC",
            (contenido_id, plataforma_id),
        ).fetchall()
    finally:
        con.close()
    return [_fila_a_doc_version(f) for f in filas]


def ultima_documento_version(contenido_id: str, plataforma_id: str) -> dict[str, Any] | None:
    """La última versión del documento de una pieza (None si no hay)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_DOC_VERSIONES} WHERE contenido_id = ? AND plataforma_id = ? "
            "ORDER BY version DESC LIMIT 1",
            (contenido_id, plataforma_id),
        ).fetchone()
    finally:
        con.close()
    return _fila_a_doc_version(fila) if fila is not None else None
