"""Persistencia — rota: franjas por semana (tabla `rota_franjas`)."""
from __future__ import annotations

from ._comun import (
    Any,
    IntegrityError,
    _conectar,
    _inicializar_franjas_por_defecto_en,
    uuid,
)

# --------------------------------------------------------------------------- #
# Franjas por semana (#XYZ "Mundial"): CRUD de `rota_franjas`                  #
# --------------------------------------------------------------------------- #
#
# Cada semana tiene sus propias franjas (nombre libre, rangos HH:MM, solapes permitidos,
# soporte a franjas que cruzan medianoche). Se inicializan 2 por defecto ("Mañana", "Tarde")
# la primera vez que la API lee la semana; admin puede anadir, editar o borrar mas.

# GRID POR MARCA: `marca` es la rejilla a la que pertenece la franja (columna del grid).
_COLS_FRANJA_SEMANA = ("id", "lunes", "nombre", "inicio", "fin", "orden", "es_descanso", "marca")
_SELECT_FRANJA_SEMANA = (
    f"SELECT {', '.join(_COLS_FRANJA_SEMANA)} FROM rota_franjas"
)


def _fila_a_franja_semana(fila: Any) -> dict[str, Any]:
    fila_dict = {col: fila[col] for col in _COLS_FRANJA_SEMANA}
    # Normaliza `es_descanso` a bool (Postgres devuelve True/False, sqlite-fake 0/1).
    fila_dict["es_descanso"] = bool(fila_dict.get("es_descanso", False))
    return fila_dict


def listar_franjas_semana(
    lunes: str, marca: str | None = None
) -> list[dict[str, Any]]:
    """Franjas de la semana cuyo lunes es `lunes`, ordenadas por `orden` ASC.

    GRID POR MARCA: `marca` acota a la rejilla de esa marca; `None` ("Todas") devuelve las de
    TODAS las marcas (la UI las apila como columnas etiquetadas por marca).
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
            f"{_SELECT_FRANJA_SEMANA} WHERE {' AND '.join(clausulas)} "
            "ORDER BY orden ASC, nombre ASC",
            tuple(params),
        ).fetchall()
    finally:
        con.close()
    return [_fila_a_franja_semana(f) for f in filas]


def obtener_franja_semana(franja_id: str) -> dict[str, Any] | None:
    """Una franja por id, None si no existe."""
    if not franja_id:
        return None
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_FRANJA_SEMANA} WHERE id = ?", (franja_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_franja_semana(fila) if fila is not None else None


def crear_franja_semana(
    lunes: str,
    nombre: str,
    inicio: str,
    fin: str,
    *,
    orden: int = 0,
    es_descanso: bool = False,
    marca: str = "",
) -> dict[str, Any] | None:
    """Inserta una franja en `rota_franjas`. Devuelve la franja creada o None si
    ya existe una con el mismo `(marca, lunes, nombre)` (UNIQUE por marca).

    NO valida formato (lo hace la API): aqui solo persistimos lo que llega. La franja con
    `es_descanso=true` se trata como "no laboral": no cubre eventos (ver
    `rota.franjas_activas_en`), pero el turno existe (y puede asignarse a un miembro).

    GRID POR MARCA: `marca` ata la franja (columna) a la rejilla de esa marca.
    """
    fila = {
        "id": uuid.uuid4().hex[:12],
        "lunes": lunes,
        "nombre": nombre,
        "inicio": inicio,
        "fin": fin,
        "orden": int(orden),
        "es_descanso": bool(es_descanso),
        "marca": marca or "",
    }
    con = _conectar()
    try:
        try:
            con.execute(
                "INSERT INTO rota_franjas (id, lunes, nombre, inicio, fin, orden, es_descanso, marca) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    fila["id"],
                    fila["lunes"],
                    fila["nombre"],
                    fila["inicio"],
                    fila["fin"],
                    fila["orden"],
                    fila["es_descanso"],
                    fila["marca"],
                ),
            )
            con.commit()
        except IntegrityError:
            # UNIQUE violation (marca, lunes, nombre) -> ya existe. `_ConexionPg` ya hizo rollback.
            return None
    finally:
        con.close()
    return fila


def actualizar_franja_semana(
    franja_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita campos de una franja (allowlist `nombre/inicio/fin/orden`); None si no existe.

    NOTA: `es_descanso` NO se edita (cambiarlo a posteriori dejaria turnos de descanso
    "convertidos" en laborales o viceversa: una incoherencia silenciosa). Si se quiere
    "renombrar" una franja de descanso, se borra y se crea una nueva.
    """
    editables = ("nombre", "inicio", "fin", "orden")
    cambios = {k: v for k, v in campos.items() if k in editables}
    if not cambios:
        return obtener_franja_semana(franja_id)
    if "orden" in cambios:
        cambios["orden"] = int(cambios["orden"])
    asignaciones = [f"{k} = ?" for k in cambios]
    params: list[Any] = [*cambios.values(), franja_id]
    con = _conectar()
    try:
        try:
            cur = con.execute(
                f"UPDATE rota_franjas SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
                tuple(params),
            )
            con.commit()
        except IntegrityError:
            # UNIQUE violation (otra franja con el mismo nombre en la semana).
            return None
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            f"{_SELECT_FRANJA_SEMANA} WHERE id = ?", (franja_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_franja_semana(fila) if fila is not None else None


def contar_turnos_de_franja(franja_id: str) -> int:
    """Numero de turnos que tienen esa `franja_id` (para el 409 al borrar)."""
    if not franja_id:
        return 0
    con = _conectar()
    try:
        fila = con.execute(
            "SELECT COUNT(*) AS n FROM rota_turnos WHERE franja_id = ?",
            (franja_id,),
        ).fetchone()
    finally:
        con.close()
    return int(fila["n"]) if fila is not None else 0


def borrar_franja_semana(franja_id: str, *, forzar: bool = False) -> dict[str, Any]:
    """Borra una franja. Devuelve `{borrada: bool, turnos_borrados: int, turnos_asociados: int}`.

    Si hay turnos asociados y `forzar=False`, no borra y devuelve
    `{borrada: False, turnos_asociados: N, turnos_borrados: 0}` para que la API responda
    con 409. Con `forzar=True`, borra los turnos en cascada y la franja despues.
    """
    if not franja_id:
        return {"borrada": False, "turnos_asociados": 0, "turnos_borrados": 0}
    con = _conectar()
    try:
        fila_count = con.execute(
            "SELECT COUNT(*) AS n FROM rota_turnos WHERE franja_id = ?",
            (franja_id,),
        ).fetchone()
        asociados = int(fila_count["n"]) if fila_count is not None else 0
        if asociados > 0 and not forzar:
            return {
                "borrada": False,
                "turnos_asociados": asociados,
                "turnos_borrados": 0,
            }
        turnos_borrados = 0
        if asociados > 0 and forzar:
            cur_t = con.execute(
                "DELETE FROM rota_turnos WHERE franja_id = ?", (franja_id,)
            )
            turnos_borrados = cur_t.rowcount
        cur_f = con.execute("DELETE FROM rota_franjas WHERE id = ?", (franja_id,))
        con.commit()
        return {
            "borrada": cur_f.rowcount > 0,
            "turnos_asociados": asociados,
            "turnos_borrados": turnos_borrados,
        }
    finally:
        con.close()


def inicializar_franjas_por_defecto(lunes: str, marca: str = "") -> list[dict[str, Any]]:
    """Idempotente: siembra ("Mañana", "Tarde", "Descanso") para `(marca, lunes)` si faltan.

    Devuelve la lista de franjas de ESA marca tras el inicializado (orden ASC). Si ya estan las
    tres, no toca nada.

    GRID POR MARCA: siembra la rejilla de UNA marca. La API NO siembra en "Todas" (sin marca
    concreta no hay rejilla que inicializar).
    """
    if not lunes:
        return []
    con = _conectar()
    try:
        _inicializar_franjas_por_defecto_en(con, lunes, marca)
        con.commit()
    finally:
        con.close()
    return listar_franjas_semana(lunes, marca or None)
