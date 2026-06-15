"""Persistencia — rota: solicitudes de cambio de turno (tabla `rota_swaps_turno`)."""
from __future__ import annotations

from ._comun import (
    ESTADO_SWAP_PROPUESTO,
    Any,
    IntegrityError,
    _conectar,
    ahora_iso,
    uuid,
)

# --------------------------------------------------------------------------- #
# Solicitudes de cambio de turno entre companeros (#175)                       #
# --------------------------------------------------------------------------- #
#
# Cuando un CM (solicitante A) necesita cubrir un asunto personal le pide a un
# companero (B) intercambiar el turno de un dia por el de otro. B acepta/rechaza, y si
# acepta, el coordinador de la rota (admin) aprueba o rechaza. La aprobacion EJECUTA el swap en
# `rota_turnos` (intercambia `miembro_id` de las dos franjas) y la solicitud
# pasa a `aplicado`. Las ausencias REALES (vacaciones, baja) viven en SAP, no aqui.
#
# IMPORTANTE: tras la migracion a "franjas por semana", las columnas `franja_a`/`franja_b`
# de `rota_swaps_turno` referencian `rota_franjas.id` (NO strings 'matutino'/'vespertino').
# Es un cambio de SEMANTICA del DATO, no de columna: los call sites deben pasar el
# `franja_id` real al crear el swap y al re-validarlo en el aprobado.

_COLS_SWAP_TURNO = (
    "id",
    "solicitante_id",
    "solicitante_nombre",
    "destinatario_id",
    "destinatario_nombre",
    "fecha_a",
    "franja_a",
    "fecha_b",
    "franja_b",
    "motivo",
    "estado",
    "respuesta_destinatario",
    "respuesta_admin",
    "creado",
    "actualizado",
    "decidido_destinatario",
    "decidido_admin",
    "aplicado",
    # GRID POR MARCA: marca de la rejilla del swap (denormalizada del turno A al crear).
    "marca",
)
_SELECT_SWAP_TURNO = f"SELECT {', '.join(_COLS_SWAP_TURNO)} FROM rota_swaps_turno"

# Campos editables del swap (allowlist DEFENSIVA: la API valida transiciones; aqui se
# garantiza que `actualizar_swap_turno` solo toca columnas de estado/timestamps/respuestas
# y nunca el solicitante/destinatario/turnos originales).
_CAMPOS_EDITABLES_SWAP = (
    "estado",
    "respuesta_destinatario",
    "respuesta_admin",
    "decidido_destinatario",
    "decidido_admin",
    "aplicado",
)


def _fila_a_swap_turno(fila: Any) -> dict[str, Any]:
    return {col: fila[col] for col in _COLS_SWAP_TURNO}


def crear_swap_turno(
    solicitante_id: str,
    destinatario_id: str,
    fecha_a: str,
    franja_a: str,
    fecha_b: str,
    franja_b: str,
    *,
    solicitante_nombre: str = "",
    destinatario_nombre: str = "",
    motivo: str = "",
    marca: str = "",
) -> dict[str, Any]:
    """Inserta una solicitud de swap (estado `propuesto`) y la devuelve.

    NO valida (lo hace la API): que los miembros existan, que sean distintos, que las
    fechas sean ISO y que las franjas pertenezcan a `FRANJAS_TURNO`. La validacion de
    que existen turnos reales en `rota_turnos` que coinciden con (A, fecha_a,
    franja_a) y (B, fecha_b, franja_b) tambien la hace la API.

    GRID POR MARCA: `marca` es la rejilla del swap (denormalizada del turno A por la API).
    """
    ahora = ahora_iso()
    fila = {
        "id": uuid.uuid4().hex[:12],
        "solicitante_id": solicitante_id or "",
        "solicitante_nombre": solicitante_nombre or "",
        "destinatario_id": destinatario_id or "",
        "destinatario_nombre": destinatario_nombre or "",
        "fecha_a": fecha_a or "",
        "franja_a": franja_a or "",
        "fecha_b": fecha_b or "",
        "franja_b": franja_b or "",
        "motivo": motivo or "",
        "estado": ESTADO_SWAP_PROPUESTO,
        "respuesta_destinatario": "",
        "respuesta_admin": "",
        "creado": ahora,
        "actualizado": ahora,
        "decidido_destinatario": "",
        "decidido_admin": "",
        "aplicado": "",
        "marca": marca or "",
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_SWAP_TURNO)
        con.execute(
            f"INSERT INTO rota_swaps_turno ({', '.join(_COLS_SWAP_TURNO)}) "
            f"VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_SWAP_TURNO),
        )
        con.commit()
    finally:
        con.close()
    return fila


def listar_swaps_turno(
    estado: str | None = None,
    solicitante_id: str | None = None,
    destinatario_id: str | None = None,
    *,
    mio_id: str | None = None,
    marca: str | None = None,
) -> list[dict[str, Any]]:
    """Solicitudes de swap, mas recientes primero. Filtros opcionales combinables.

    `mio_id` es un atajo para "swaps que me involucran": filas en las que `mio_id` es
    solicitante O destinatario. La API lo usa cuando el cliente pide `?mio=true` y hay
    sesion activa.

    GRID POR MARCA: `marca` acota a la rejilla de esa marca; `None` ("Todas") no filtra.
    """
    clausulas: list[str] = []
    params: list[Any] = []
    if estado:
        clausulas.append("estado = ?")
        params.append(estado)
    if solicitante_id:
        clausulas.append("solicitante_id = ?")
        params.append(solicitante_id)
    if destinatario_id:
        clausulas.append("destinatario_id = ?")
        params.append(destinatario_id)
    if marca:
        clausulas.append("marca = ?")
        params.append(marca)
    if mio_id:
        clausulas.append("(solicitante_id = ? OR destinatario_id = ?)")
        params.append(mio_id)
        params.append(mio_id)
    sql = _SELECT_SWAP_TURNO
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)
    sql += " ORDER BY creado DESC, id DESC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_swap_turno(f) for f in filas]


def obtener_swap_turno(swap_id: str) -> dict[str, Any] | None:
    """Una solicitud de swap por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_SWAP_TURNO} WHERE id = ?", (swap_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_swap_turno(fila) if fila is not None else None


def actualizar_swap_turno(
    swap_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Actualiza campos de un swap (allowlist `_CAMPOS_EDITABLES_SWAP`); None si no existe.

    Refresca `actualizado` SIEMPRE. La API es responsable de las TRANSICIONES validas
    (no se valida aqui). Devuelve el swap actualizado, o None si el id no existe.
    """
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_SWAP}
    if not cambios:
        return obtener_swap_turno(swap_id)
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = list(cambios.values())
    params.append(ahora_iso())
    params.append(swap_id)
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE rota_swaps_turno SET {', '.join(asignaciones)} WHERE id = ?",
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            f"{_SELECT_SWAP_TURNO} WHERE id = ?", (swap_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_swap_turno(fila) if fila is not None else None


def borrar_swap_turno(swap_id: str) -> bool:
    """Borra un swap (uso administrativo; el flujo normal es marcar `cancelado`)."""
    con = _conectar()
    try:
        cur = con.execute("DELETE FROM rota_swaps_turno WHERE id = ?", (swap_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def aplicar_swap_turno(
    swap_id: str,
    *,
    solicitante_id: str,
    solicitante_nombre: str,
    destinatario_id: str,
    destinatario_nombre: str,
    fecha_a: str,
    franja_a: str,
    fecha_b: str,
    franja_b: str,
    respuesta_admin: str = "",
) -> dict[str, Any] | None:
    """Aprueba+ejecuta un swap en UNA transaccion: intercambia los miembros y marca `aplicado`.

    Re-VALIDA dentro de la misma conexion que las franjas actuales en `rota_turnos`
    siguen siendo las del swap original (otro usuario podria haberlas reasignado a mano).
    Si NO coinciden, devuelve `{"error": "no_coinciden", "esperado": {...}, "actual": {...}}`
    y NO toca nada. Si todo cuadra, intercambia los `miembro_id`+`miembro_nombre` de las
    dos filas, marca el swap como `aplicado` con el `respuesta_admin` y los timestamps
    correspondientes, y devuelve el swap actualizado.

    Estados de salida posibles:
      - dict del swap (claves de `_COLS_SWAP_TURNO`) si se aplico,
      - {"error": "no_coinciden", "esperado": ..., "actual": ...} si las franjas no
        coinciden con lo solicitado en este momento,
      - {"error": "conflicto_destino"} si el intercambio chocaria con el indice unico
        `idx_rota_turnos_uniq` (el destinatario ya ocupa la celda de origen, o el
        solicitante la de destino): nada se aplica, el swap queda intacto,
      - None si el `swap_id` no existe.
    """
    ahora = ahora_iso()
    con = _conectar()
    try:
        # 1) El swap debe existir. Lo BLOQUEAMOS (`FOR UPDATE`) para serializar dos aplicaciones
        #    concurrentes del MISMO swap: la segunda espera aqui y, al leer ya `aplicado`, sale
        #    sin re-intercambiar (un doble-swap volveria los turnos a su sitio: corrupcion).
        swap = con.execute(
            f"{_SELECT_SWAP_TURNO} WHERE id = ? FOR UPDATE", (swap_id,)
        ).fetchone()
        if swap is None:
            con.commit()
            return None
        # Idempotencia: si ya esta aplicado (otra peticion gano la carrera), devolvemos el swap
        # tal cual SIN tocar los turnos. El caller lo renderiza igual (no es un error).
        if swap["estado"] == "aplicado":
            con.commit()
            return _fila_a_swap_turno(swap)
        # 2) Las dos franjas reales (por miembro + fecha + franja) deben existir y
        #    seguir asignadas a quien dijo el swap. Buscamos por (fecha, franja) y
        #    comprobamos el miembro actual (asi detectamos el caso 409 con detalle).
        #    Las BLOQUEAMOS (`FOR UPDATE`) para que el intercambio sea atomico frente a otra
        #    reasignacion concurrente de los mismos turnos.
        fila_a = con.execute(
            "SELECT id, miembro_id, miembro_nombre, fecha, franja_id FROM rota_turnos "
            "WHERE fecha = ? AND franja_id = ? AND miembro_id = ? FOR UPDATE",
            (fecha_a, franja_a, solicitante_id),
        ).fetchone()
        fila_b = con.execute(
            "SELECT id, miembro_id, miembro_nombre, fecha, franja_id FROM rota_turnos "
            "WHERE fecha = ? AND franja_id = ? AND miembro_id = ? FOR UPDATE",
            (fecha_b, franja_b, destinatario_id),
        ).fetchone()
        if fila_a is None or fila_b is None:
            # Buscamos el detalle ACTUAL (sin filtrar por miembro) para informar.
            actual_a = con.execute(
                "SELECT miembro_id, miembro_nombre FROM rota_turnos "
                "WHERE fecha = ? AND franja_id = ?",
                (fecha_a, franja_a),
            ).fetchone()
            actual_b = con.execute(
                "SELECT miembro_id, miembro_nombre FROM rota_turnos "
                "WHERE fecha = ? AND franja_id = ?",
                (fecha_b, franja_b),
            ).fetchone()
            con.commit()  # suelta los locks FOR UPDATE; no tocamos nada (caso 409).
            return {
                "error": "no_coinciden",
                "esperado": {
                    "a": {
                        "fecha": fecha_a,
                        "franja": franja_a,
                        "miembro_id": solicitante_id,
                        "miembro_nombre": solicitante_nombre,
                    },
                    "b": {
                        "fecha": fecha_b,
                        "franja": franja_b,
                        "miembro_id": destinatario_id,
                        "miembro_nombre": destinatario_nombre,
                    },
                },
                "actual": {
                    "a": {
                        "fecha": fecha_a,
                        "franja": franja_a,
                        "miembro_id": actual_a["miembro_id"] if actual_a else "",
                        "miembro_nombre": actual_a["miembro_nombre"] if actual_a else "",
                    },
                    "b": {
                        "fecha": fecha_b,
                        "franja": franja_b,
                        "miembro_id": actual_b["miembro_id"] if actual_b else "",
                        "miembro_nombre": actual_b["miembro_nombre"] if actual_b else "",
                    },
                },
            }
        # 3) Intercambiamos los miembros + nombre + actualizado de ambas filas y marcamos
        #    el swap como `aplicado`. Todo bajo la misma conexion (Postgres autocommit
        #    desactivado por defecto en nuestro driver -> la `con.commit()` final lo encierra
        #    como una transaccion).
        # Envolvemos los UPDATE en try/except: si el destinatario YA tiene un turno en la celda
        # de origen `(fecha_a, franja_a)` (o el solicitante en la de destino), el intercambio
        # dejaria dos filas con la misma clave `(marca, semana, fecha, miembro_id, franja_id)` y
        # choca con el indice unico parcial `idx_rota_turnos_uniq` -> `IntegrityError`. Sin captura
        # eso era un 500 opaco; aqui lo convertimos en un sentinel que la API traduce a 409.
        try:
            con.execute(
                "UPDATE rota_turnos SET miembro_id = ?, miembro_nombre = ?, "
                "actualizado = ? WHERE id = ?",
                (destinatario_id, destinatario_nombre, ahora, fila_a["id"]),
            )
            con.execute(
                "UPDATE rota_turnos SET miembro_id = ?, miembro_nombre = ?, "
                "actualizado = ? WHERE id = ?",
                (solicitante_id, solicitante_nombre, ahora, fila_b["id"]),
            )
            # Guardia de estado (defensa en profundidad, ademas del FOR UPDATE): el swap solo se
            # marca `aplicado` si AUN no lo estaba. Bajo el lock esto siempre prospera; el guard
            # protege ante cualquier via que entrara sin pasar por el lock.
            con.execute(
                "UPDATE rota_swaps_turno SET estado = ?, respuesta_admin = ?, "
                "decidido_admin = ?, aplicado = ?, actualizado = ? "
                "WHERE id = ? AND estado <> ?",
                ("aplicado", respuesta_admin or "", ahora, ahora, ahora, swap_id, "aplicado"),
            )
            con.commit()
        except IntegrityError:
            # Colision con `idx_rota_turnos_uniq`: el intercambio dejaria al destinatario (o al
            # solicitante) con dos turnos en la misma celda. El wrapper de la conexion ya hizo
            # rollback al mapear la violacion; lo repetimos por defensa (no-op si ya esta
            # deshecha). NADA se aplico: el swap sigue `aceptado` y los turnos quedan intactos.
            con.rollback()
            return {"error": "conflicto_destino"}
        fila = con.execute(
            f"{_SELECT_SWAP_TURNO} WHERE id = ?", (swap_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_swap_turno(fila) if fila is not None else None
