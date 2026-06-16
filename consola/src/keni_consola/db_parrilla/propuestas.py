"""Persistencia — propuestas de importación de parrilla (tabla `parrilla_propuesta`).

Ver barrel `db.py`."""
from __future__ import annotations

from .._db_json import a_json_lista
from ..db_publicacion import _fila_publicacion_nueva, _insertar_publicacion
from ..tiempo import ahora_iso
from ._comun import (
    ESTADO_ROTA_PROPUESTO,
    Any,
    _conectar,
    date,
    json,
    timedelta,
    uuid,
)

# --------------------------------------------------------------------------- #
# PARRILLA: propuestas de importacion desde documento (#parrilla-import)        #
# --------------------------------------------------------------------------- #
#
# Una `parrilla_propuesta` es el resultado ESTACIONADO de un `claude -p` que leyo un documento
# y propuso operaciones (eventos/turnos nuevos, modificaciones). NO se aplica hasta que el
# usuario acepta: entonces `aplicar_propuesta_parrilla` aplica TODO el diff en UNA transaccion
# reusando las MISMAS tablas (`rota_eventos`/`rota_turnos`) que los endpoints de la rota.

_COLS_PROPUESTA = (
    "id",
    "creado",
    "actualizado",
    "estado",
    "autor_id",
    "autor_nombre",
    "doc_nombre",
    "doc_tipo",
    "semana",
    "gen_id",
    "operaciones",
    "resumen",
    "error",
    "marca",
)
_SELECT_PROPUESTA = f"SELECT {', '.join(_COLS_PROPUESTA)} FROM parrilla_propuesta"

# Campos editables via `actualizar_propuesta_parrilla` (allowlist). `id`/`creado` no se tocan;
# `actualizado` lo gestiona el sistema.
_CAMPOS_EDITABLES_PROPUESTA: tuple[str, ...] = (
    "estado",
    "operaciones",
    "resumen",
    "error",
    "doc_nombre",
    "doc_tipo",
    "gen_id",
)


def _fila_a_propuesta(fila: Any) -> dict[str, Any]:
    """Fila de `parrilla_propuesta` -> dict publico. `operaciones` se deserializa de JSON.

    `operaciones` vive como TEXT JSON ("" si el job aun no termino); lo exponemos como lista
    (o None si esta vacio) para que la API no tenga que (de)serializar.
    """
    p = {col: fila[col] for col in _COLS_PROPUESTA}
    crudo = p.get("operaciones") or ""
    if crudo:
        try:
            cargado = json.loads(crudo)
            p["operaciones"] = cargado if isinstance(cargado, list) else None
        except (json.JSONDecodeError, ValueError):
            p["operaciones"] = None
    else:
        p["operaciones"] = None
    return p


def crear_propuesta_parrilla(
    *,
    semana: str,
    doc_nombre: str,
    doc_tipo: str = "",
    gen_id: str = "",
    autor_id: str = "",
    autor_nombre: str = "",
    estado: str = "generando",
    marca: str = "",
) -> dict[str, Any]:
    """Crea una propuesta en estado `generando` y la devuelve. NO valida (lo hace la API)."""
    ahora = ahora_iso()
    fila = {
        "id": uuid.uuid4().hex,
        "creado": ahora,
        "actualizado": ahora,
        "estado": estado,
        "autor_id": autor_id or "",
        "autor_nombre": autor_nombre or "",
        "doc_nombre": doc_nombre or "",
        "doc_tipo": doc_tipo or "",
        "semana": semana or "",
        "gen_id": gen_id or "",
        "operaciones": "",
        "resumen": "",
        "error": "",
        "marca": marca or "",
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_PROPUESTA)
        con.execute(
            f"INSERT INTO parrilla_propuesta ({', '.join(_COLS_PROPUESTA)}) VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_PROPUESTA),
        )
        con.commit()
    finally:
        con.close()
    fila["operaciones"] = None
    return fila


def obtener_propuesta_parrilla(propuesta_id: str) -> dict[str, Any] | None:
    """Una propuesta por id; None si no existe."""
    if not propuesta_id:
        return None
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_PROPUESTA} WHERE id = ?", (propuesta_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_propuesta(fila) if fila is not None else None


def listar_propuestas_parrilla(
    *, estado: str | None = None, limite: int = 100
) -> list[dict[str, Any]]:
    """Propuestas mas recientes primero; filtro opcional por `estado`."""
    sql = _SELECT_PROPUESTA
    params: list[Any] = []
    if estado:
        sql += " WHERE estado = ?"
        params.append(estado)
    sql += " ORDER BY creado DESC, id DESC LIMIT ?"
    params.append(int(limite))
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_propuesta(f) for f in filas]


def actualizar_propuesta_parrilla(
    propuesta_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita una propuesta (allowlist `_CAMPOS_EDITABLES_PROPUESTA`); None si el id no existe.

    `operaciones` puede llegar como lista (se serializa a JSON) o como str ya serializado.
    Pone `actualizado` a ahora.
    """
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_PROPUESTA}
    if "operaciones" in cambios and not isinstance(cambios["operaciones"], str):
        cambios["operaciones"] = a_json_lista(cambios["operaciones"] or [])
    if not cambios:
        return obtener_propuesta_parrilla(propuesta_id)
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = list(cambios.values())
    params.append(ahora_iso())
    params.append(propuesta_id)
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE parrilla_propuesta SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            f"{_SELECT_PROPUESTA} WHERE id = ?", (propuesta_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_propuesta(fila) if fila is not None else None


def aplicar_propuesta_parrilla(
    propuesta_id: str,
    operaciones: list[dict[str, Any]],
    *,
    nombres_miembros: dict[str, str],
    origen: str = "import-doc",
    marca: str = "",
) -> dict[str, Any]:
    """Aplica TODAS las `operaciones` (ya validadas) en UNA transaccion y marca aplicada.

    Reusa las MISMAS tablas que la rota (`rota_eventos`/`rota_turnos`) con un SOLO `_conectar()`
    para que el diff sea atomico (todo o nada): si algo revienta, `_ConexionPg` hace rollback y
    NADA queda escrito. Cada fila creada se etiqueta con `origen`/`origen_ref` (provenance).
    `nombres_miembros` resuelve el nombre vivo del miembro (el snapshot de la op puede estar
    desactualizado). Devuelve un resumen `{eventos_creados, turnos_creados, turnos_modificados,
    ids:{...}}`. NO re-valida (la API ya lo hizo contra la BD viva ANTES de llamar aqui).

    RANGO / FRANJA POR NOMBRE (PERMISIVO): cada `crear_turno` trae `franja` (NOMBRE de slot,
    p.ej. "Mañana") y una fecha cualquiera. Calcula su semana (`lunes`) y resuelve el NOMBRE ->
    el `franja_id` de esa semana (match normalizado case/space-insensitive). Si el nombre NO
    existe esa semana, CREA la franja en la misma transaccion (un día puede tener 3+ franjas y
    el documento puede traer slots nuevos), con el horario `franja_inicio/fin` del documento si
    vino. NO rechaza por plantilla. Cacheamos el mapa nombre->id por semana.
    """
    ahora = ahora_iso()
    eventos_creados: list[str] = []
    tareas_creadas: list[str] = []
    turnos_creados: list[str] = []
    turnos_modificados: list[str] = []
    # Cache por semana del mapa {nombre_normalizado -> franja_id} (inicializa defaults una vez).
    franjas_por_semana: dict[str, dict[str, str]] = {}

    def _franja_id_de(
        con: Any, semana: str, nombre: str, *, inicio: str = "", fin: str = ""
    ) -> str:
        """Resuelve `nombre` de slot -> `franja_id` de `semana`. PERMISIVO: si el nombre no
        existe en esa semana, CREA la franja (un día puede tener 3+ franjas y el documento
        puede traer slots nuevos), usando `inicio`/`fin` si vienen o un horario por defecto.
        `es_descanso` se infiere del nombre. No rechaza nada por plantilla."""
        if semana not in franjas_por_semana:
            # Cargamos las franjas YA existentes de la semana (sin inicializar: no imponemos la
            # plantilla por defecto; solo creamos las que el documento realmente use).
            filas = con.execute(
                "SELECT id, nombre FROM rota_franjas WHERE lunes = ?", (semana,)
            ).fetchall()
            franjas_por_semana[semana] = {
                str(f["nombre"]).strip().lower(): f["id"] for f in filas
            }
        clave = (nombre or "").strip().lower()
        fid = franjas_por_semana[semana].get(clave)
        if fid:
            return fid
        # No existe: la creamos en ESTA transacción (orden = nº de franjas ya en la semana).
        nuevo_id = uuid.uuid4().hex[:12]
        es_descanso = "descanso" in clave
        con.execute(
            "INSERT INTO rota_franjas (id, lunes, nombre, inicio, fin, orden, es_descanso) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                nuevo_id,
                semana,
                nombre.strip(),
                (inicio or "").strip() or "00:00",
                (fin or "").strip() or "23:59",
                len(franjas_por_semana[semana]),
                es_descanso,
            ),
        )
        franjas_por_semana[semana][clave] = nuevo_id
        return fid or nuevo_id

    con = _conectar()
    try:
        for op in operaciones:
            tipo = op.get("tipo")
            if tipo == "crear_evento":
                eid = uuid.uuid4().hex[:12]
                con.execute(
                    "INSERT INTO rota_eventos "
                    "(id, titulo, fecha, hora, contenido, nota, tipo_cobertura, prioridad, "
                    "cambiado, actualizado, creado, origen, origen_ref, marca) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        eid,
                        str(op.get("titulo", "")),
                        str(op.get("fecha", "")),
                        str(op.get("hora") or ""),
                        str(op.get("contenido") or ""),
                        str(op.get("nota") or ""),
                        str(op.get("tipo_cobertura") or "transmision"),
                        str(op.get("prioridad") or "media"),
                        0,
                        ahora,
                        ahora,
                        origen,
                        propuesta_id,
                        marca or "",
                    ),
                )
                eventos_creados.append(eid)
            elif tipo == "crear_tarea":
                # Encargo suelto (clase='tarea'): se inserta en `contenido` DENTRO de la misma
                # transacción (build fila + INSERT sin commit, como los lotes de piezas).
                # Nace SIN responsable («por coger»); el equipo lo asigna luego.
                fila = _fila_publicacion_nueva(
                    clase="tarea",
                    titulo=str(op.get("titulo", "")),
                    descripcion=str(op.get("detalle") or ""),
                    prioridad=str(op.get("prioridad") or "media"),
                    fecha_objetivo=str(op.get("fecha_objetivo") or ""),
                    marca=marca or "",
                    origen=origen,
                )
                _insertar_publicacion(con, fila)
                tareas_creadas.append(str(fila["id"]))
            elif tipo == "crear_turno":
                tid = uuid.uuid4().hex[:12]
                miembro_id = str(op.get("miembro_id", ""))
                semana = _lunes_iso_de(op.get("fecha", ""))
                # Resuelve el NOMBRE de slot -> franja_id de ESA semana (CREA la franja si no
                # existe, con el horario del documento si vino).
                franja_id = _franja_id_de(
                    con,
                    semana,
                    str(op.get("franja", "")),
                    inicio=str(op.get("franja_inicio") or ""),
                    fin=str(op.get("franja_fin") or ""),
                )
                con.execute(
                    "INSERT INTO rota_turnos "
                    "(id, semana, fecha, miembro_id, miembro_nombre, franja_id, estado, "
                    "override, motivo, nota_relevo, creado, actualizado, origen, origen_ref) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        tid,
                        semana,
                        str(op.get("fecha", "")),
                        miembro_id,
                        nombres_miembros.get(miembro_id, str(op.get("miembro_nombre") or "")),
                        franja_id,
                        ESTADO_ROTA_PROPUESTO,
                        0,
                        str(op.get("motivo") or ""),
                        str(op.get("nota_relevo") or ""),
                        ahora,
                        ahora,
                        origen,
                        propuesta_id,
                    ),
                )
                turnos_creados.append(tid)
            elif tipo == "modificar_turno":
                turno_id = str(op.get("turno_id", ""))
                cambios_op = op.get("cambios") or {}
                asignaciones: list[str] = []
                valores: list[Any] = []
                if cambios_op.get("miembro_id") not in (None, ""):
                    mid = str(cambios_op["miembro_id"])
                    asignaciones.append("miembro_id = ?")
                    valores.append(mid)
                    asignaciones.append("miembro_nombre = ?")
                    valores.append(
                        nombres_miembros.get(mid, str(cambios_op.get("miembro_nombre") or ""))
                    )
                elif cambios_op.get("miembro_nombre") not in (None, ""):
                    asignaciones.append("miembro_nombre = ?")
                    valores.append(str(cambios_op["miembro_nombre"]))
                if cambios_op.get("estado") not in (None, ""):
                    asignaciones.append("estado = ?")
                    valores.append(str(cambios_op["estado"]))
                if cambios_op.get("override") is not None:
                    asignaciones.append("override = ?")
                    valores.append(1 if cambios_op["override"] else 0)
                if cambios_op.get("motivo") is not None:
                    asignaciones.append("motivo = ?")
                    valores.append(str(cambios_op["motivo"]))
                if cambios_op.get("nota_relevo") is not None:
                    asignaciones.append("nota_relevo = ?")
                    valores.append(str(cambios_op["nota_relevo"]))
                # Provenance del cambio (no toca filas de alta manual: solo las que tocamos aqui).
                asignaciones.append("origen = ?")
                valores.append(origen)
                asignaciones.append("origen_ref = ?")
                valores.append(propuesta_id)
                asignaciones.append("actualizado = ?")
                valores.append(ahora)
                valores.append(turno_id)
                con.execute(
                    f"UPDATE rota_turnos SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
                    tuple(valores),
                )
                turnos_modificados.append(turno_id)
        # Marca la propuesta como aplicada DENTRO de la misma transaccion (atomico con el diff).
        con.execute(
            "UPDATE parrilla_propuesta SET estado = ?, actualizado = ? WHERE id = ?",
            ("aplicada", ahora, propuesta_id),
        )
        con.commit()
    finally:
        con.close()
    return {
        "eventos_creados": len(eventos_creados),
        "tareas_creadas": len(tareas_creadas),
        "turnos_creados": len(turnos_creados),
        "turnos_modificados": len(turnos_modificados),
        "ids": {
            "eventos": eventos_creados,
            "tareas": tareas_creadas,
            "turnos": turnos_creados,
            "turnos_modificados": turnos_modificados,
        },
    }


def _lunes_iso_de(fecha_iso: str) -> str:
    """Lunes (ISO) de la semana que contiene `fecha_iso`; "" si no parsea. Sin dep a `rota`."""
    try:
        d = date.fromisoformat(fecha_iso)
    except (ValueError, TypeError):
        return ""
    return (d - timedelta(days=d.weekday())).isoformat()
