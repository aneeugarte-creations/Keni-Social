"""Persistencia — dominio colaboracion. Implementación de db.py (ver barrel `db.py`)."""
from __future__ import annotations

from ._db_comun import (
    DECISION_APROBADO,
    DECISION_PENDIENTE,
    DECISION_RECHAZADO,
    Any,
    IntegrityError,
    _conectar,
    uuid,
)
from .db_editor import (
    _MAX_REINTENTOS_VERSION,
)
from .tiempo import ahora_iso

# --------------------------------------------------------------------------- #
# Ola COLABORACION: comentarios internos por pieza                             #
# --------------------------------------------------------------------------- #
# Hilo de discusion de redaccion atado a un item de `contenido` (padre). Modelo
# CRUD plano: crear, listar (por contenido, opcionalmente filtrando una plataforma),
# marcar resuelto/reabrir, editar texto, borrar. Aditivo: NO toca `contenido`.

_COLS_COMENTARIO = (
    "id",
    "publicacion_id",
    "pieza_id",
    "autor_id",
    "autor_nombre",
    "texto",
    "resuelto",
    "creado",
    "actualizado",
    "menciones",
)
_SELECT_COMENTARIO = f"SELECT {', '.join(_COLS_COMENTARIO)} FROM publicacion_comentarios"


def _fila_a_comentario(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `publicacion_comentarios` en dict (`resuelto` bool, `menciones` lista)."""
    item: dict[str, Any] = {col: fila[col] for col in _COLS_COMENTARIO}
    item["resuelto"] = bool(fila["resuelto"])
    item["menciones"] = [m for m in (fila["menciones"] or "").split(",") if m]
    return item


def crear_comentario(
    *,
    publicacion_id: str,
    pieza_id: str = "",
    texto: str,
    autor: dict[str, str] | None = None,
    menciones: list[str] | None = None,
) -> dict[str, Any]:
    """Inserta un comentario en el hilo de un contenido y lo devuelve. NO valida.

    `menciones` son ids de usuarios etiquetados con @ (se guardan separados por coma); los
    devolvemos como lista en el dict de salida (ver `_fila_a_comentario`).
    """
    autor = autor or {}
    ahora = ahora_iso()
    fila = {
        "id": uuid.uuid4().hex[:12],
        "publicacion_id": publicacion_id,
        "pieza_id": pieza_id or "",
        "autor_id": autor.get("id", "") or "",
        "autor_nombre": autor.get("usuario", "") or "",
        "texto": texto or "",
        "resuelto": 0,
        "creado": ahora,
        "actualizado": ahora,
        "menciones": ",".join(menciones or []),
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_COMENTARIO)
        con.execute(
            f"INSERT INTO publicacion_comentarios ({', '.join(_COLS_COMENTARIO)}) "
            f"VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_COMENTARIO),
        )
        con.commit()
    finally:
        con.close()
    return _fila_a_comentario(fila)


def listar_comentarios(
    publicacion_id: str, pieza_id: str | None = None
) -> list[dict[str, Any]]:
    """Comentarios de un contenido, mas antiguos primero. `pieza_id` filtra una red."""
    sql = f"{_SELECT_COMENTARIO} WHERE publicacion_id = ?"
    params: list[Any] = [publicacion_id]
    if pieza_id is not None:
        sql += " AND pieza_id = ?"
        params.append(pieza_id)
    sql += " ORDER BY creado ASC, id ASC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_comentario(f) for f in filas]


def obtener_comentario(comentario_id: str) -> dict[str, Any] | None:
    """Un comentario por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_COMENTARIO} WHERE id = ?", (comentario_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_comentario(fila) if fila is not None else None


def actualizar_comentario(
    comentario_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita `texto` y/o `resuelto` de un comentario; None si no existe."""
    cambios = {k: v for k, v in campos.items() if k in ("texto", "resuelto")}
    if not cambios:
        return obtener_comentario(comentario_id)
    if "resuelto" in cambios:
        cambios["resuelto"] = 1 if cambios["resuelto"] else 0
    ahora = ahora_iso()
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = [*cambios.values(), ahora, comentario_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE publicacion_comentarios SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            f"{_SELECT_COMENTARIO} WHERE id = ?", (comentario_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_comentario(fila) if fila is not None else None


def borrar_comentario(comentario_id: str) -> bool:
    """Borra un comentario; True si existia."""
    con = _conectar()
    try:
        cur = con.execute(
            "DELETE FROM publicacion_comentarios WHERE id = ?", (comentario_id,)
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()



# --------------------------------------------------------------------------- #
# Ola COLABORACION: historial de versiones del copy                            #
# --------------------------------------------------------------------------- #
# Snapshots inmutables del copy de una fila por plataforma. Cada cambio del copy
# guarda el texto ANTERIOR (con quien/cuando/nota); revertir aplica un texto viejo
# como copy actual y vuelve a snapshotear lo que se pisa: nunca se pierde nada.

_COLS_COPY_VERSION = (
    "id",
    "pieza_id",
    "publicacion_id",
    "version",
    "copy",
    "autor_id",
    "autor_nombre",
    "nota",
    "creado",
)
_SELECT_COPY_VERSION = f"SELECT {', '.join(_COLS_COPY_VERSION)} FROM pieza_copy_versiones"


def _fila_a_copy_version(fila: Any) -> dict[str, Any]:
    return {col: fila[col] for col in _COLS_COPY_VERSION}


def registrar_copy_version(
    *,
    pieza_id: str,
    publicacion_id: str,
    copy: str,
    autor: dict[str, str] | None = None,
    nota: str = "",
) -> dict[str, Any]:
    """Guarda un snapshot del copy de una plataforma con `version` autoincremental (1-based).

    El numero de version se calcula como `MAX(version)+1` sobre esa plataforma (1 si es el
    primero). NO valida: la API decide cuando snapshotear (antes de pisar el copy vivo).

    CONTADOR SEGURO ANTE CONCURRENCIA: bajo el indice UNICO `(pieza_id, version)`, dos
    snapshots simultaneos no pueden compartir version. Si chocan, una gana y la otra REINTENTA
    (bucle acotado) recalculando el siguiente numero (en vez de duplicar la version).
    """
    autor = autor or {}
    ahora = ahora_iso()
    fila_id = uuid.uuid4().hex[:12]
    con = _conectar()
    try:
        ultimo_error: Exception | None = None
        for _ in range(_MAX_REINTENTOS_VERSION):
            fila_max = con.execute(
                "SELECT MAX(version) AS m FROM pieza_copy_versiones WHERE pieza_id = ?",
                (pieza_id,),
            ).fetchone()
            siguiente = (fila_max["m"] or 0) + 1 if fila_max is not None else 1
            fila = {
                "id": fila_id,
                "pieza_id": pieza_id,
                "publicacion_id": publicacion_id or "",
                "version": siguiente,
                "copy": copy or "",
                "autor_id": autor.get("id", "") or "",
                "autor_nombre": autor.get("usuario", "") or "",
                "nota": nota or "",
                "creado": ahora,
            }
            marcadores = ", ".join("?" for _ in _COLS_COPY_VERSION)
            try:
                con.execute(
                    f"INSERT INTO pieza_copy_versiones ({', '.join(_COLS_COPY_VERSION)}) "
                    f"VALUES ({marcadores})",
                    tuple(fila[col] for col in _COLS_COPY_VERSION),
                )
                con.commit()
                return _fila_a_copy_version(fila)
            except IntegrityError as e:
                ultimo_error = e  # otra version gano la carrera; el shim ya hizo rollback.
        raise RuntimeError(
            "No se pudo asignar una version de copy tras varios reintentos "
            f"(plataforma={pieza_id})"
        ) from ultimo_error
    finally:
        con.close()


def listar_copy_versiones(pieza_id: str) -> list[dict[str, Any]]:
    """Historial de versiones del copy de una plataforma, mas RECIENTE primero."""
    con = _conectar()
    try:
        filas = con.execute(
            f"{_SELECT_COPY_VERSION} WHERE pieza_id = ? ORDER BY version DESC, id DESC",
            (pieza_id,),
        ).fetchall()
    finally:
        con.close()
    return [_fila_a_copy_version(f) for f in filas]


def obtener_copy_version(version_id: str) -> dict[str, Any] | None:
    """Una version del copy por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_COPY_VERSION} WHERE id = ?", (version_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_copy_version(fila) if fila is not None else None



# --------------------------------------------------------------------------- #
# Ola COLABORACION: aprobacion multinivel por pieza                            #
# --------------------------------------------------------------------------- #
# Cadena de niveles de aprobacion de una fila por plataforma. Cada fila es la
# decision de UN nivel; la pieza esta aprobada cuando todos sus niveles lo estan.

_COLS_APROBACION = (
    "id",
    "pieza_id",
    "publicacion_id",
    "nivel",
    "etiqueta",
    "decision",
    "decisor_id",
    "decisor_nombre",
    "comentario",
    "creado",
    "decidido_en",
    "cargo_requerido",
)
_SELECT_APROBACION = f"SELECT {', '.join(_COLS_APROBACION)} FROM pieza_aprobaciones"


def _fila_a_aprobacion(fila: Any) -> dict[str, Any]:
    return {col: fila[col] for col in _COLS_APROBACION}


def crear_cadena_aprobacion(
    *,
    pieza_id: str,
    publicacion_id: str,
    etiquetas: list[str],
    cargos: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Crea (o RECREA) la cadena de aprobacion de una plataforma a partir de `etiquetas`.

    Borra cualquier cadena previa de esa plataforma y crea un nivel `pendiente` por cada
    etiqueta, en orden (nivel 1-based). `cargos` (opcional, paralela a `etiquetas`) sella el
    `cargo_requerido` de cada nivel (item C); "" o lista corta -> sin requisito en ese nivel.
    Devuelve la cadena nueva. NO valida.
    """
    cargos = cargos or []
    ahora = ahora_iso()
    con = _conectar()
    try:
        con.execute(
            "DELETE FROM pieza_aprobaciones WHERE pieza_id = ?", (pieza_id,)
        )
        creados: list[dict[str, Any]] = []
        for indice, etiqueta in enumerate(etiquetas, start=1):
            cargo = cargos[indice - 1] if indice - 1 < len(cargos) else ""
            fila = {
                "id": uuid.uuid4().hex[:12],
                "pieza_id": pieza_id,
                "publicacion_id": publicacion_id or "",
                "nivel": indice,
                "etiqueta": etiqueta or f"Nivel {indice}",
                "decision": "pendiente",
                "decisor_id": "",
                "decisor_nombre": "",
                "comentario": "",
                "creado": ahora,
                "decidido_en": "",
                "cargo_requerido": cargo or "",
            }
            marcadores = ", ".join("?" for _ in _COLS_APROBACION)
            con.execute(
                f"INSERT INTO pieza_aprobaciones ({', '.join(_COLS_APROBACION)}) "
                f"VALUES ({marcadores})",
                tuple(fila[col] for col in _COLS_APROBACION),
            )
            creados.append(_fila_a_aprobacion(fila))
        con.commit()
    finally:
        con.close()
    return creados


def listar_aprobaciones(pieza_id: str) -> list[dict[str, Any]]:
    """Cadena de aprobacion de una plataforma, por nivel ascendente."""
    con = _conectar()
    try:
        filas = con.execute(
            f"{_SELECT_APROBACION} WHERE pieza_id = ? ORDER BY nivel ASC, id ASC",
            (pieza_id,),
        ).fetchall()
    finally:
        con.close()
    return [_fila_a_aprobacion(f) for f in filas]


def obtener_aprobacion(aprobacion_id: str) -> dict[str, Any] | None:
    """Un nivel de la cadena por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_APROBACION} WHERE id = ?", (aprobacion_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_aprobacion(fila) if fila is not None else None


def actualizar_aprobacion(
    aprobacion_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Aplica una decision a un nivel (`decision`/`decisor_*`/`comentario`/`decidido_en`).

    CAS DE LA MAQUINA DE ESTADOS (concurrencia): si los `campos` mueven el nivel a una decision
    TERMINAL (`aprobado`/`rechazado`), el UPDATE solo prospera si el nivel SEGUIA `pendiente`
    (`AND decision = 'pendiente'`). Asi dos peticiones simultaneas (doble-click, dos revisores a
    la vez, aprobar-tras-rechazar) NO se pisan: la primera gana y la segunda ve `rowcount == 0`
    y recibe `None` (el caller lo traduce a 409 "ya fue decidido"). Resetear a `pendiente`
    (deshacer) o tocar solo metadatos NO lleva guardia (no es una transicion de estado que se
    pueda perder). El camino normal/no contendido se comporta IGUAL que antes (rowcount 1).
    Devuelve el nivel actualizado, o None si no existia o si el CAS no aplico (ya decidido).
    """
    permitidos = ("decision", "decisor_id", "decisor_nombre", "comentario", "decidido_en")
    cambios = {k: v for k, v in campos.items() if k in permitidos}
    if not cambios:
        return obtener_aprobacion(aprobacion_id)
    asignaciones = [f"{k} = ?" for k in cambios]
    params: list[Any] = [*cambios.values(), aprobacion_id]
    # Guardia CAS solo al pasar a una decision terminal: la transicion pendiente->aprobado/
    # rechazado es la unica que se puede "perder" si dos la aplican a la vez.
    decision_nueva = cambios.get("decision")
    where_cas = ""
    if decision_nueva in (DECISION_APROBADO, DECISION_RECHAZADO):
        where_cas = " AND decision = ?"
        params.append(DECISION_PENDIENTE)
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE pieza_aprobaciones SET {', '.join(asignaciones)} "  # noqa: S608 -- allowlist
            f"WHERE id = ?{where_cas}",
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            f"{_SELECT_APROBACION} WHERE id = ?", (aprobacion_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_aprobacion(fila) if fila is not None else None


def decidir_nivel_aprobacion_tx(
    pieza_id: str,
    nivel_id: str,
    validar: Any,
) -> tuple[dict[str, Any] | None, str | None]:
    """Decide UN nivel de la cadena RE-VALIDANDO bajo bloqueo, en una sola transaccion.

    Cierra la condicion de carrera de INVARIANTE CRUZADO ENTRE FILAS que el CAS por-fila no
    cubre: el "dos OK = dos personas distintas" (y el orden de la cadena) se comprueba contra
    el ESTADO de toda la cadena, no de un solo nivel. Dos decisiones simultaneas de la MISMA
    persona sobre niveles distintos podrian, leyendo cada una un snapshot donde la otra aun no
    consta, pasar las dos el chequeo de "decisor distinto" y dejar a una persona dando los dos
    OK. Aqui:

      1) Bloqueamos las filas de la cadena (`SELECT ... FOR UPDATE`) de `pieza_id`: la otra
         decision concurrente sobre la misma cadena ESPERA aqui (no lee un snapshot obsoleto).
      2) Re-leemos la cadena ya consistente y llamamos `validar(nivel_actual, cadena)` —la regla
         PURA del dominio (`colaboracion.decidir`)— sobre datos frescos. Devuelve `(campos, None)`
         o `(None, error)`.
      3) Si valida, aplicamos el UPDATE con la MISMA guardia CAS (`AND decision='pendiente'`) y
         confirmamos. Todo bajo una sola conexion/transaccion.

    Devuelve `(nivel_decidido, None)` con el nivel ya actualizado, o `(None, error)` si la
    validacion lo rechaza (texto legible para 409) o si el CAS no aplico (decidido en paralelo).
    `validar` recibe `(nivel_actual_dict | None, cadena_list)` y debe ser una funcion PURA.
    """
    con = _conectar()
    try:
        # 1) Bloqueo de la cadena: serializa las decisiones concurrentes de la MISMA pieza.
        con.execute(
            "SELECT id FROM pieza_aprobaciones WHERE pieza_id = ? "
            "ORDER BY nivel ASC, id ASC FOR UPDATE",
            (pieza_id,),
        ).fetchall()
        # 2) Re-lectura consistente de la cadena + del nivel objetivo.
        filas = con.execute(
            f"{_SELECT_APROBACION} WHERE pieza_id = ? ORDER BY nivel ASC, id ASC",
            (pieza_id,),
        ).fetchall()
        cadena = [_fila_a_aprobacion(f) for f in filas]
        nivel = next((n for n in cadena if n.get("id") == nivel_id), None)
        if nivel is None:
            con.commit()
            return None, "Ese nivel ya no existe."
        campos, error = validar(nivel, cadena)
        if error is not None:
            con.commit()
            return None, error
        # 3) Escritura con la misma guardia CAS (defensa en profundidad bajo el lock).
        permitidos = ("decision", "decisor_id", "decisor_nombre", "comentario", "decidido_en")
        cambios = {k: v for k, v in (campos or {}).items() if k in permitidos}
        asignaciones = [f"{k} = ?" for k in cambios]
        params: list[Any] = [*cambios.values(), nivel_id, DECISION_PENDIENTE]
        cur = con.execute(
            f"UPDATE pieza_aprobaciones SET {', '.join(asignaciones)} "  # noqa: S608 -- allowlist
            "WHERE id = ? AND decision = ?",
            tuple(params),
        )
        if cur.rowcount == 0:
            con.commit()
            return None, "Este nivel ya fue decidido (el estado cambió)."
        fila = con.execute(
            f"{_SELECT_APROBACION} WHERE id = ?", (nivel_id,)
        ).fetchone()
        con.commit()
    finally:
        con.close()
    return (_fila_a_aprobacion(fila) if fila is not None else None), None
