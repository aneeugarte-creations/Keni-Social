"""Persistencia — rota: coordinador por turno (tabla `rota_coordinacion`)."""
from __future__ import annotations

from ._comun import (
    Any,
    _conectar,
    ahora_iso,
    uuid,
)

# --------------------------------------------------------------------------- #
# Coordinador por turno (ola "coord"): CRUD de `rota_coordinacion`             #
# --------------------------------------------------------------------------- #
#
# Cada celda del calendario (combinacion fecha + franja_id) puede tener UN coordinador.
# Los candidatos son los usuarios con `puede_coordinar=true` (la API lo valida; aqui solo
# persistimos). UNIQUE(fecha, franja_id): un upsert reemplaza el coordinador previo.
# La coordinacion es INDEPENDIENTE del turno de CM: borrar un turno o cambiar franja NO
# borra la coordinacion (el admin la mantiene aparte).

# GRID POR MARCA: `marca` es la rejilla de la celda coordinada (denormalizada de la franja).
_COLS_COORDINACION = (
    "id", "lunes", "fecha", "franja_id", "coordinador_id", "creado", "actualizado", "marca",
)
_SELECT_COORDINACION = f"SELECT {', '.join(_COLS_COORDINACION)} FROM rota_coordinacion"


def _fila_a_coordinacion(fila: Any) -> dict[str, Any]:
    return {col: fila[col] for col in _COLS_COORDINACION}


def listar_coordinacion_semana(
    lunes: str, marca: str | None = None
) -> list[dict[str, Any]]:
    """Coordinaciones de la semana cuyo lunes es `lunes`, ordenadas por fecha y franja.

    GRID POR MARCA: `marca` acota a la rejilla de esa marca; `None` ("Todas") no filtra.
    """
    if not lunes:
        return []
    clausulas = ["lunes = ?"]
    params: list[Any] = [lunes]
    if marca:
        clausulas.append("marca = ?")
        params.append(marca)
    con = _conectar()
    try:
        filas = con.execute(
            f"{_SELECT_COORDINACION} WHERE {' AND '.join(clausulas)} "
            "ORDER BY fecha ASC, franja_id ASC",
            tuple(params),
        ).fetchall()
    finally:
        con.close()
    return [_fila_a_coordinacion(f) for f in filas]


def actualizar_coordinador_rota(
    lunes: str, fecha: str, franja_id: str, coordinador_id: str, marca: str = ""
) -> dict[str, Any]:
    """UPSERT por (fecha, franja_id): asigna `coordinador_id` a la celda; devuelve la fila.

    Si ya hay coordinador en esa celda, se REEMPLAZA (actualiza `coordinador_id` y
    `actualizado`). Si no hay, se crea con `creado` = `actualizado` = ahora. La capa API
    valida que `coordinador_id` corresponda a un usuario con `puede_coordinar=true`.

    GRID POR MARCA: `marca` es la rejilla de la celda (la `franja_id` ya es propia de una
    marca; `marca` se denormaliza para filtrar/etiquetar sin join).
    """
    ahora = ahora_iso()
    nuevo_id = uuid.uuid4().hex[:12]
    con = _conectar()
    try:
        # UPSERT atomico por UNIQUE(fecha, franja_id): un solo statement inserta o reemplaza
        # el coordinador y devuelve la fila resultante (`RETURNING`), sin ventana de carrera
        # entre el chequeo y la escritura. `creado` solo se fija al insertar (el DO UPDATE no
        # lo toca, conserva el original).
        fila = con.execute(
            "INSERT INTO rota_coordinacion "
            "(id, lunes, fecha, franja_id, coordinador_id, creado, actualizado, marca) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (fecha, franja_id) DO UPDATE SET "
            "coordinador_id = EXCLUDED.coordinador_id, lunes = EXCLUDED.lunes, "
            "marca = EXCLUDED.marca, actualizado = EXCLUDED.actualizado "
            f"RETURNING {', '.join(_COLS_COORDINACION)}",
            (nuevo_id, lunes, fecha, franja_id, coordinador_id, ahora, ahora, marca or ""),
        ).fetchone()
        con.commit()
        return _fila_a_coordinacion(fila)
    finally:
        con.close()


def quitar_coordinador_rota(fecha: str, franja_id: str) -> bool:
    """Borra la coordinacion de la celda (fecha, franja_id). True si habia algo que borrar."""
    con = _conectar()
    try:
        cur = con.execute(
            "DELETE FROM rota_coordinacion WHERE fecha = ? AND franja_id = ?",
            (fecha, franja_id),
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()
