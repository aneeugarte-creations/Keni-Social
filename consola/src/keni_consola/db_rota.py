"""Persistencia — dominio rota. Implementación de db.py (ver barrel `db.py`)."""
from __future__ import annotations

from ._db_comun import (
    _NOMBRE_FRANJA_DESCANSO,
    _NOMBRE_FRANJA_MANANA,
    _NOMBRE_FRANJA_TARDE,
    ESTADO_ROTA_APROBADO,
    ESTADO_ROTA_PROPUESTO,
    ESTADO_SWAP_PROPUESTO,
    ESTADOS_ROTA,
    PRIORIDAD_EVENTO_DEFECTO,
    PRIORIDADES_EVENTO,
    TIPO_COBERTURA_TRANSMISION,
    TIPOS_AUSENCIA,
    TIPOS_COBERTURA,
    Any,
    IntegrityError,
    _conectar,
    _sembrar_franjas_por_defecto_en,
    date,
    datetime,
    timedelta,
    uuid,
)

# --------------------------------------------------------------------------- #
# Rota: eventos/transmisiones + turnos (horarios persona×dia×franja)            #
# --------------------------------------------------------------------------- #
#
# Sustituye el Excel manual de Elias. Dos entidades operacionales INDEPENDIENTES (ver
# comentario "cambio de modelo" en la DDL): el EVENTO (calendario de transmisiones) y el
# TURNO (horario del miembro en (fecha, franja)). Un turno NO va atado a un evento. La
# "cobertura" (quien cubre un evento) es una vista DERIVADA: para un evento, sus coberturas
# son los miembros cuyo turno coincide con la franja+fecha del evento (`mapear_franja` en
# `rota.py`). Pueden existir turnos sin eventos y eventos sin turnos.
#
# Antes el codigo tenia dos tablas: `rota_turnos` (cobertura, mal modelada) y
# `rota_turnos` (horario). El feedback del usuario aclaro que la cobertura no es un
# concepto persistido: un turno cubre todos los eventos que caen en su franja+fecha. La
# migracion (`_migrar_modelo_turnos`) convierte la cobertura legada en turnos del nuevo modelo
# y unifica todo en una unica tabla `rota_turnos`.

# Columnas de `rota_eventos`. La ola B (#144) anade tipo_cobertura/prioridad/cambiado/
# actualizado: `cambiado`/`actualizado` son GESTIONADAS POR EL SISTEMA (no editables a
# pelo: `cambiado` lo derivamos al reprogramar y `actualizado` se refresca en cada edicion),
# por eso quedan fuera de `_CAMPOS_EDITABLES_EVENTO_ROTA`.
_COLS_EVENTO_ROTA = (
    "id",
    "titulo",
    "fecha",
    "hora",
    "contenido",
    "nota",
    "tipo_cobertura",
    "prioridad",
    "cambiado",
    "actualizado",
    "creado",
    "marca",
)
_SELECT_EVENTO_ROTA = f"SELECT {', '.join(_COLS_EVENTO_ROTA)} FROM rota_eventos"
_CAMPOS_EDITABLES_EVENTO_ROTA = (
    "titulo",
    "fecha",
    "hora",
    "contenido",
    "nota",
    "tipo_cobertura",
    "prioridad",
    "marca",
)


def _fila_a_evento_rota(fila: Any) -> dict[str, Any]:
    evento = {col: fila[col] for col in _COLS_EVENTO_ROTA}
    # `cambiado` se persiste como 0/1; lo exponemos como bool para la capa API/UI.
    evento["cambiado"] = bool(fila["cambiado"])
    # Defensa retrocompatible: una fila migrada con NULL/"" cae al valor por defecto.
    evento["tipo_cobertura"] = fila["tipo_cobertura"] or TIPO_COBERTURA_TRANSMISION
    evento["prioridad"] = fila["prioridad"] or PRIORIDAD_EVENTO_DEFECTO
    # `marca` puede ser NULL en filas muy antiguas (antes de la columna); normalizar a "".
    evento["marca"] = fila["marca"] or ""
    return evento


# --- Eventos / transmisiones --------------------------------------------------


def crear_evento_rota(
    titulo: str,
    *,
    fecha: str = "",
    hora: str = "",
    contenido: str = "",
    nota: str = "",
    tipo_cobertura: str = TIPO_COBERTURA_TRANSMISION,
    prioridad: str = PRIORIDAD_EVENTO_DEFECTO,
    marca: str = "",
) -> dict[str, Any]:
    """Inserta un evento/transmision y lo devuelve. NO valida (lo hace la API).

    Nace `cambiado=0` (sin reprogramar) y con `actualizado`=`creado` (alta = primera version).
    `marca` es el id canonico de la marca a la que pertenece el evento ("" = sin marca asignada).
    """
    ahora = datetime.now().isoformat(timespec="seconds")
    fila = {
        "id": uuid.uuid4().hex[:12],
        "titulo": titulo,
        "fecha": fecha or "",
        "hora": hora or "",
        "contenido": contenido or "",
        "nota": nota or "",
        "tipo_cobertura": tipo_cobertura if tipo_cobertura in TIPOS_COBERTURA else TIPO_COBERTURA_TRANSMISION,
        "prioridad": prioridad if prioridad in PRIORIDADES_EVENTO else PRIORIDAD_EVENTO_DEFECTO,
        "cambiado": 0,
        "actualizado": ahora,
        "creado": ahora,
        "marca": marca or "",
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_EVENTO_ROTA)
        con.execute(
            f"INSERT INTO rota_eventos ({', '.join(_COLS_EVENTO_ROTA)}) VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_EVENTO_ROTA),
        )
        con.commit()
    finally:
        con.close()
    fila["cambiado"] = bool(fila["cambiado"])
    return fila


def listar_eventos_rota(
    desde: str | None = None,
    hasta: str | None = None,
    *,
    solo_cambiados: bool = False,
    tipo_cobertura: str | None = None,
    marca: str | None = None,
) -> list[dict[str, Any]]:
    """Eventos de la rota, en orden cronologico. Filtros opcionales (todos combinables).

    `desde`/`hasta` acotan por rango de fechas (ISO). `solo_cambiados` deja solo los
    REPROGRAMADOS (`cambiado=1`, los que Elias debe re-avisar). `tipo_cobertura` filtra por
    tipo de cobertura (transmision|imagenes|no_cubrir); la API ya valida el valor.
    `marca` filtra por id canonico de marca; None o "" -> sin filtro (devuelve todas).
    """
    clausulas: list[str] = []
    params: list[Any] = []
    if desde:
        clausulas.append("fecha >= ?")
        params.append(desde)
    if hasta:
        clausulas.append("fecha <= ?")
        params.append(hasta)
    if solo_cambiados:
        clausulas.append("cambiado = ?")
        params.append(1)
    if tipo_cobertura:
        clausulas.append("tipo_cobertura = ?")
        params.append(tipo_cobertura)
    if marca:
        clausulas.append("marca = ?")
        params.append(marca)
    sql = _SELECT_EVENTO_ROTA
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)
    sql += " ORDER BY fecha ASC, hora ASC, titulo ASC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_evento_rota(f) for f in filas]


def obtener_evento_rota(evento_id: str) -> dict[str, Any] | None:
    con = _conectar()
    try:
        fila = con.execute(f"{_SELECT_EVENTO_ROTA} WHERE id = ?", (evento_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_evento_rota(fila) if fila is not None else None


# Campos cuya EDICION reprograma el evento: si cambia su valor, `cambiado` se pone a 1
# (hay que volver a avisar al equipo). Son los datos "logisticos" que el equipo de
# programacion mueve constantemente ("tres cambios en horarios para el fin de semana").
_CAMPOS_REPROGRAMAN_EVENTO: tuple[str, ...] = ("fecha", "hora", "tipo_cobertura")


def actualizar_evento_rota(evento_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    """Edita parcialmente un evento; None si el id no existe.

    Reglas de SEGUIMIENTO DE CAMBIOS (ola B, #144):
      - `actualizado` SIEMPRE se refresca (toda edicion deja marca temporal).
      - Si la edicion cambia `fecha`, `hora` o `tipo_cobertura` -> `cambiado=1` automatico
        (se reprogramo: el equipo debe re-enterarse). Solo si el valor REALMENTE cambia.
      - Si el request trae `cambiado=False` explicito (la accion "ya avisé / visto" de
        Elias) -> se LIMPIA a 0, y limpiar GANA aunque en el mismo request se hubiera
        reprogramado (Elias dice "ya está visto").
    Solo se escriben los campos editables; `cambiado`/`actualizado` los gestiona el sistema.
    """
    actual = obtener_evento_rota(evento_id)
    if actual is None:
        return None

    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_EVENTO_ROTA}

    # ¿Se reprogramo? Solo cuenta un cambio REAL de fecha/hora/tipo_cobertura.
    reprogramado = any(
        k in cambios and cambios[k] != actual.get(k) for k in _CAMPOS_REPROGRAMAN_EVENTO
    )
    nuevo_cambiado = 1 if reprogramado else int(bool(actual["cambiado"]))
    # La accion explicita "marcar avisado" (cambiado=False) limpia y GANA al reprograma.
    if "cambiado" in campos and not campos["cambiado"]:
        nuevo_cambiado = 0
    elif "cambiado" in campos and campos["cambiado"]:
        nuevo_cambiado = 1

    ahora = datetime.now().isoformat(timespec="seconds")
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("cambiado = ?")
    asignaciones.append("actualizado = ?")
    params: list[Any] = [*cambios.values(), nuevo_cambiado, ahora, evento_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE rota_eventos SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- columnas de allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(f"{_SELECT_EVENTO_ROTA} WHERE id = ?", (evento_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_evento_rota(fila) if fila is not None else None


def borrar_evento_rota(evento_id: str) -> bool:
    """Borra un evento. True si existia.

    NO arrastra cascada sobre `rota_turnos` (los turnos son horarios del miembro, viven
    independientes del evento; un evento borrado simplemente deja de cubrirse via la vista
    derivada de cobertura).
    """
    con = _conectar()
    try:
        cur = con.execute("DELETE FROM rota_eventos WHERE id = ?", (evento_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


# --- Turnos (horario persona×dia×franja) --------------------------------------
#
# Un TURNO es el horario que un miembro tiene en una (fecha, franja). NO va asociado a un
# evento. Cubre todos los eventos que caigan en su franja (cobertura derivada, no persistida).
# Forma identica a la antigua `rota_turnos` (modelo viejo) tras la migracion.

_COLS_TURNO_ROTA = (
    "id",
    "semana",
    "fecha",
    "miembro_id",
    "miembro_nombre",
    "franja_id",
    "estado",
    "override",
    "motivo",
    "nota_relevo",
    "creado",
    "actualizado",
    # GRID POR MARCA: el turno pertenece a la rejilla de UNA marca.
    "marca",
)
_SELECT_TURNO_ROTA = f"SELECT {', '.join(_COLS_TURNO_ROTA)} FROM rota_turnos"

# Campos editables via `actualizar_turno_rota` (allowlist). `id`/`semana`/`creado` no son
# editables aqui (la semana se deriva de la fecha si esta cambia). `actualizado` lo gestiona
# el sistema.
_CAMPOS_EDITABLES_TURNO_ROTA: tuple[str, ...] = (
    "fecha",
    "miembro_id",
    "miembro_nombre",
    "franja_id",
    "estado",
    "override",
    "motivo",
    "nota_relevo",
    # GRID POR MARCA: `marca` sigue a `franja_id` (la API la deriva de la franja) para que
    # mover un turno a otra franja mantenga turno.marca == franja.marca. La API no la acepta
    # como campo suelto del body; la fija desde la franja en `_validar_y_resolver_turno`.
    "marca",
)


def _fila_a_turno_rota(fila: Any) -> dict[str, Any]:
    turno = {col: fila[col] for col in _COLS_TURNO_ROTA}
    turno["override"] = bool(fila["override"])
    return turno


def crear_turno_rota(
    semana: str,
    fecha: str,
    *,
    miembro_id: str = "",
    miembro_nombre: str = "",
    franja_id: str = "",
    estado: str = ESTADO_ROTA_PROPUESTO,
    override: bool = False,
    motivo: str = "",
    nota_relevo: str = "",
    franja: str | None = None,
    marca: str = "",
) -> dict[str, Any]:
    """Inserta un TURNO (horario en `(fecha, franja_id)` para `miembro_id`) y lo devuelve.

    NO valida (lo hace la API). NO comprueba unicidad (semana, fecha, miembro_id,
    franja_id); eso es responsabilidad del endpoint POST (que devuelve 409 si choca).

    GRID POR MARCA: `marca` ata el turno a la rejilla de esa marca.

    RETROCOMPAT: acepta `franja` (literal 'matutino'/'vespertino'/'descanso') traduciendolo
    a `franja_id` via las franjas por defecto de la semana DE ESA MARCA. Mismo contrato que el
    shim de `repos.crear_turno_rota`; codigo NUEVO debe pasar `franja_id` directamente.
    """
    if franja_id == "" and franja is not None:
        franja_norm = (franja or "").strip().lower()
        # Sembramos en la conexion local (sin pasar por `repos` para evitar ciclos).
        con_t = _conectar()
        try:
            mapa = _sembrar_franjas_por_defecto_en(con_t, semana, marca)
            con_t.commit()
        finally:
            con_t.close()
        if franja_norm == "matutino":
            franja_id = mapa.get(_NOMBRE_FRANJA_MANANA, "")
        elif franja_norm == "vespertino":
            franja_id = mapa.get(_NOMBRE_FRANJA_TARDE, "")
        elif franja_norm == "descanso":
            franja_id = mapa.get(_NOMBRE_FRANJA_DESCANSO, "")
    ahora = datetime.now().isoformat(timespec="seconds")
    fila = {
        "id": uuid.uuid4().hex[:12],
        "semana": semana,
        "fecha": fecha or "",
        "miembro_id": miembro_id or "",
        "miembro_nombre": miembro_nombre or "",
        "franja_id": franja_id or "",
        "estado": estado if estado in ESTADOS_ROTA else ESTADO_ROTA_PROPUESTO,
        "override": 1 if override else 0,
        "motivo": motivo or "",
        "nota_relevo": nota_relevo or "",
        "creado": ahora,
        "actualizado": ahora,
        "marca": marca or "",
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_TURNO_ROTA)
        con.execute(
            f"INSERT INTO rota_turnos ({', '.join(_COLS_TURNO_ROTA)}) VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_TURNO_ROTA),
        )
        con.commit()
    finally:
        con.close()
    fila["override"] = bool(fila["override"])
    return fila


def listar_turnos_rota(
    semana: str | None = None, marca: str | None = None
) -> list[dict[str, Any]]:
    """Turnos del horario; filtros opcionales por `semana` (lunes ISO) y `marca`.

    GRID POR MARCA: `marca` acota a la rejilla de esa marca; `None` ("Todas") NO filtra y
    devuelve todas (la UI las apila etiquetando cada turno con su marca).
    """
    sql = _SELECT_TURNO_ROTA
    clausulas: list[str] = []
    params: list[Any] = []
    if semana:
        clausulas.append("semana = ?")
        params.append(semana)
    if marca:
        clausulas.append("marca = ?")
        params.append(marca)
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)
    sql += " ORDER BY semana ASC, fecha ASC, franja_id ASC, creado ASC, id ASC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_turno_rota(f) for f in filas]


def obtener_turno_rota(turno_id: str) -> dict[str, Any] | None:
    con = _conectar()
    try:
        fila = con.execute(f"{_SELECT_TURNO_ROTA} WHERE id = ?", (turno_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_turno_rota(fila) if fila is not None else None


def existe_turno_para(
    miembro_id: str, fecha: str, franja_id: str
) -> dict[str, Any] | None:
    """Devuelve el turno actual de `(miembro_id, fecha, franja_id)`; None si no hay.

    Sirve para que el endpoint POST detecte choque (devolver 409 antes de insertar duplicado).
    """
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_TURNO_ROTA} WHERE miembro_id = ? AND fecha = ? AND franja_id = ? LIMIT 1",
            (miembro_id, fecha, franja_id),
        ).fetchone()
    finally:
        con.close()
    return _fila_a_turno_rota(fila) if fila is not None else None


def actualizar_turno_rota(turno_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    """Edita un turno (allowlist `_CAMPOS_EDITABLES_TURNO_ROTA`); None si el id no existe.

    Pone `actualizado` a ahora. `override` se normaliza a 0/1. Si la fecha cambia, la semana
    NO se recalcula aqui (la API decide si tambien envia `semana` ajustada cuando hace falta).
    """
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_TURNO_ROTA}
    if "override" in cambios:
        cambios["override"] = 1 if cambios["override"] else 0
    if not cambios:
        return obtener_turno_rota(turno_id)
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = list(cambios.values())
    params.append(datetime.now().isoformat(timespec="seconds"))
    params.append(turno_id)
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE rota_turnos SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(f"{_SELECT_TURNO_ROTA} WHERE id = ?", (turno_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_turno_rota(fila) if fila is not None else None


def borrar_turnos_semana_rota(semana: str) -> int:
    """Borra TODOS los turnos de una semana. Devuelve cuantos borro."""
    con = _conectar()
    try:
        cur = con.execute("DELETE FROM rota_turnos WHERE semana = ?", (semana,))
        con.commit()
        return cur.rowcount
    finally:
        con.close()


def borrar_turno_rota(turno_id: str) -> bool:
    """Borra un turno individual; True si existia, False si no."""
    con = _conectar()
    try:
        cur = con.execute("DELETE FROM rota_turnos WHERE id = ?", (turno_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def borrar_turnos_rota_lote(ids: list[str]) -> int:
    """Borra varios turnos en una sola sentencia. 0 si `ids` venia vacio."""
    if not ids:
        return 0
    marcadores = ", ".join("?" for _ in ids)
    con = _conectar()
    try:
        cur = con.execute(
            f"DELETE FROM rota_turnos WHERE id IN ({marcadores})",  # noqa: S608 -- placeholders
            tuple(ids),
        )
        con.commit()
        return cur.rowcount
    finally:
        con.close()


def aprobar_semana_rota(semana: str, marca: str | None = None) -> int:
    """Marca los turnos de una semana como `aprobado` (publica al equipo).

    GRID POR MARCA: con `marca` aprueba SOLO la rejilla de esa marca; `None` aprueba todas
    (la API exige marca concreta — aprobar en "Todas" no tiene sentido). Idempotente.
    """
    ahora = datetime.now().isoformat(timespec="seconds")
    clausulas = ["semana = ?"]
    params: list[Any] = [ESTADO_ROTA_APROBADO, ahora, semana]
    if marca:
        clausulas.append("marca = ?")
        params.append(marca)
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE rota_turnos SET estado = ?, actualizado = ? WHERE {' AND '.join(clausulas)}",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        return cur.rowcount
    finally:
        con.close()


def desaprobar_semana_rota(semana: str, marca: str | None = None) -> int:
    """Marca los turnos de una semana como `propuesto` (vuelve a borrador).

    Inverso de `aprobar_semana_rota`. GRID POR MARCA: con `marca` revierte SOLO esa rejilla.
    Idempotente.
    """
    ahora = datetime.now().isoformat(timespec="seconds")
    clausulas = ["semana = ?"]
    params: list[Any] = [ESTADO_ROTA_PROPUESTO, ahora, semana]
    if marca:
        clausulas.append("marca = ?")
        params.append(marca)
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE rota_turnos SET estado = ?, actualizado = ? WHERE {' AND '.join(clausulas)}",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        return cur.rowcount
    finally:
        con.close()


def crear_turnos_rota_lote(turnos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Inserta varios turnos en una sola transaccion. Devuelve la lista de turnos creados.

    Cada dict en `turnos` puede tener: `semana`, `fecha`, `miembro_id`, `miembro_nombre`,
    `franja`, `estado`, `override`, `motivo`, `nota_relevo`. La API valida CADA entrada
    antes de pasarla aqui; aqui solo se persiste con defensas minimas (uuid, `actualizado`).

    NO comprueba unicidad: si dos turnos chocan en (semana, fecha, miembro_id, franja), se
    persisten ambos (el endpoint lote es responsable de cribar antes). Lista vacia -> sin op.
    """
    if not turnos:
        return []
    ahora = datetime.now().isoformat(timespec="seconds")
    filas: list[dict[str, Any]] = []
    for entrada in turnos:
        estado = entrada.get("estado") or ESTADO_ROTA_PROPUESTO
        filas.append(
            {
                "id": uuid.uuid4().hex[:12],
                "semana": entrada.get("semana", ""),
                "fecha": entrada.get("fecha", "") or "",
                "miembro_id": entrada.get("miembro_id", "") or "",
                "miembro_nombre": entrada.get("miembro_nombre", "") or "",
                "franja_id": entrada.get("franja_id", "") or "",
                "estado": estado if estado in ESTADOS_ROTA else ESTADO_ROTA_PROPUESTO,
                "override": 1 if entrada.get("override") else 0,
                "motivo": entrada.get("motivo", "") or "",
                "nota_relevo": entrada.get("nota_relevo", "") or "",
                "creado": ahora,
                "actualizado": ahora,
                "marca": entrada.get("marca", "") or "",
            }
        )
    marcadores = ", ".join("?" for _ in _COLS_TURNO_ROTA)
    sql = (
        f"INSERT INTO rota_turnos ({', '.join(_COLS_TURNO_ROTA)}) VALUES ({marcadores})"
    )
    con = _conectar()
    try:
        for fila in filas:
            con.execute(sql, tuple(fila[col] for col in _COLS_TURNO_ROTA))
        con.commit()
    finally:
        con.close()
    # Devolvemos los turnos creados con `override` como bool (formato API).
    for fila in filas:
        fila["override"] = bool(fila["override"])
    return filas


def duplicar_turno_rota(
    turno_id: str,
    *,
    fecha: str | None = None,
    miembro_id: str | None = None,
    miembro_nombre: str | None = None,
    franja_id: str | None = None,
    semana: str | None = None,
) -> dict[str, Any] | None:
    """Clona un turno con overrides opcionales. None si el id no existe.

    Caso comun: "rellena la semana siguiente con el turno de Luis del lunes". El estado se
    reinicia a `propuesto` (Elias re-aprueba antes de publicar). `motivo` y `nota_relevo`
    NO viajan (son del turno ORIGINAL, no del clon).
    """
    original = obtener_turno_rota(turno_id)
    if original is None:
        return None
    return crear_turno_rota(
        semana if semana is not None else original["semana"],
        fecha if fecha is not None else original["fecha"],
        miembro_id=miembro_id if miembro_id is not None else original["miembro_id"],
        miembro_nombre=miembro_nombre if miembro_nombre is not None else original["miembro_nombre"],
        franja_id=franja_id if franja_id is not None else original["franja_id"],
        estado=ESTADO_ROTA_PROPUESTO,
        override=bool(original.get("override", False)),
        motivo="",
        nota_relevo="",
        # GRID POR MARCA: el clon hereda la marca de la rejilla del turno original.
        marca=original.get("marca", "") or "",
    )



# --------------------------------------------------------------------------- #
# Ausencias / vacaciones                                                       #
# --------------------------------------------------------------------------- #

_COLS_AUSENCIA_ROTA = (
    "id",
    "miembro_id",
    "miembro_nombre",
    "tipo",
    "desde",
    "hasta",
    "motivo",
    "creado",
)
_SELECT_AUSENCIA_ROTA = f"SELECT {', '.join(_COLS_AUSENCIA_ROTA)} FROM rota_ausencias"


def _fila_a_ausencia_rota(fila: Any) -> dict[str, Any]:
    return {col: fila[col] for col in _COLS_AUSENCIA_ROTA}


# --- Ausencias / vacaciones ---------------------------------------------------


def crear_ausencia_rota(
    miembro_id: str,
    desde: str,
    hasta: str,
    *,
    miembro_nombre: str = "",
    tipo: str = "otro",
    motivo: str = "",
) -> dict[str, Any]:
    """Inserta una ausencia (rango inclusivo) y la devuelve. NO valida (lo hace la API)."""
    ahora = datetime.now().isoformat(timespec="seconds")
    fila = {
        "id": uuid.uuid4().hex[:12],
        "miembro_id": miembro_id or "",
        "miembro_nombre": miembro_nombre or "",
        "tipo": tipo if tipo in TIPOS_AUSENCIA else "otro",
        "desde": desde or "",
        "hasta": hasta or "",
        "motivo": motivo or "",
        "creado": ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_AUSENCIA_ROTA)
        con.execute(
            f"INSERT INTO rota_ausencias ({', '.join(_COLS_AUSENCIA_ROTA)}) "
            f"VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_AUSENCIA_ROTA),
        )
        con.commit()
    finally:
        con.close()
    return fila


def listar_ausencias_rota(
    miembro_id: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
) -> list[dict[str, Any]]:
    """Ausencias de la rota, mas recientes primero. Filtros opcionales por miembro y solape de rango.

    `desde`/`hasta` filtran las ausencias que SOLAPAN con ese rango (ausencia.hasta >= desde
    AND ausencia.desde <= hasta): util para resolver las ausencias relevantes a una semana.
    """
    clausulas: list[str] = []
    params: list[Any] = []
    if miembro_id:
        clausulas.append("miembro_id = ?")
        params.append(miembro_id)
    if desde:
        clausulas.append("hasta >= ?")
        params.append(desde)
    if hasta:
        clausulas.append("desde <= ?")
        params.append(hasta)
    sql = _SELECT_AUSENCIA_ROTA
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)
    sql += " ORDER BY desde DESC, id DESC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_ausencia_rota(f) for f in filas]


def obtener_ausencia_rota(ausencia_id: str) -> dict[str, Any] | None:
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_AUSENCIA_ROTA} WHERE id = ?", (ausencia_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_ausencia_rota(fila) if fila is not None else None


def actualizar_ausencia_rota(
    ausencia_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita parcialmente una ausencia (tipo/desde/hasta/motivo); None si el id no existe."""
    editables = ("tipo", "desde", "hasta", "motivo")
    cambios = {k: v for k, v in campos.items() if k in editables}
    if not cambios:
        return obtener_ausencia_rota(ausencia_id)
    asignaciones = [f"{k} = ?" for k in cambios]
    params: list[Any] = list(cambios.values())
    params.append(ausencia_id)
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE rota_ausencias SET {', '.join(asignaciones)} WHERE id = ?",
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            f"{_SELECT_AUSENCIA_ROTA} WHERE id = ?", (ausencia_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_ausencia_rota(fila) if fila is not None else None


def borrar_ausencia_rota(ausencia_id: str) -> bool:
    """Borra una ausencia; True si existia, False si no."""
    con = _conectar()
    try:
        cur = con.execute("DELETE FROM rota_ausencias WHERE id = ?", (ausencia_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()



# --------------------------------------------------------------------------- #
# Catalogo de programas (#150, PARRILLA 2026.xlsx)                              #
# --------------------------------------------------------------------------- #
#
# En el Excel cada HOJA evergreen ("Álvaro Fidalgo", "Real Oviedo", "Anfitriones", "PATY
# CANTU", "MUNDIAL", "LA SELECCIÓN EN TUS MANOS", "IDEAS SIN DERECHOS") es un PROGRAMA.
# Hasta ahora `rota_piezas.programa` era texto libre; pasamos a un catalogo con color y
# fechas de campana (inicio/fin) para que la UI pueda colorear y filtrar la parrilla.
#
# IMPORTANTE: las piezas siguen referenciando al programa POR NOMBRE (no por id) para que
# una pieza huerfana de un programa borrado siga apareciendo en la parrilla con su texto
# original. Al RENOMBRAR un programa, la API ejecuta una cascada (UPDATE rota_piezas SET
# programa = ? WHERE programa = ?) en la MISMA transaccion: ver `actualizar_programa_rota`.

_COLS_PROGRAMA_ROTA = (
    "id",
    "nombre",
    "descripcion",
    "color",
    "inicio",
    "fin",
    "activo",
    "creado",
    "actualizado",
)
_SELECT_PROGRAMA_ROTA = f"SELECT {', '.join(_COLS_PROGRAMA_ROTA)} FROM rota_programas"

# Campos editables via `actualizar_programa_rota` (allowlist; `id`/`creado`/`actualizado`
# los gestiona el sistema). `nombre` es editable pero exige cascada en `rota_piezas`.
_CAMPOS_EDITABLES_PROGRAMA_ROTA: tuple[str, ...] = (
    "nombre",
    "descripcion",
    "color",
    "inicio",
    "fin",
    "activo",
)


def _fila_a_programa_rota(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `rota_programas` en dict (`activo` como bool)."""
    p: dict[str, Any] = {col: fila[col] for col in _COLS_PROGRAMA_ROTA}
    p["activo"] = bool(fila["activo"])
    return p


def _programa_por_nombre(con: Any, nombre: str) -> dict[str, Any] | None:
    """Busca un programa por nombre EXACTO (case-insensitive). None si no hay.

    Usa LOWER(nombre) en SQL para que "MUNDIAL" no choque con "Mundial". La capa API
    impone la unicidad case-insensitive antes de insertar.
    """
    fila = con.execute(
        f"{_SELECT_PROGRAMA_ROTA} WHERE LOWER(nombre) = LOWER(?)", (nombre,)
    ).fetchone()
    return _fila_a_programa_rota(fila) if fila is not None else None


def existe_programa_por_nombre(nombre: str) -> bool:
    """True si hay un programa con ese nombre (case-insensitive). Util para la API."""
    if not nombre:
        return False
    con = _conectar()
    try:
        return _programa_por_nombre(con, nombre) is not None
    finally:
        con.close()


def contar_piezas_por_programa(nombre: str) -> int:
    """Cuantas piezas en `rota_piezas` referencian ese `programa` (case-insensitive)."""
    if not nombre:
        return 0
    con = _conectar()
    try:
        fila = con.execute(
            "SELECT COUNT(*) AS n FROM rota_piezas WHERE LOWER(programa) = LOWER(?)",
            (nombre,),
        ).fetchone()
    finally:
        con.close()
    return int(fila["n"] or 0) if fila is not None else 0


def crear_programa_rota(
    nombre: str,
    *,
    descripcion: str = "",
    color: str = "",
    inicio: str = "",
    fin: str = "",
    activo: bool = True,
) -> dict[str, Any]:
    """Inserta un programa nuevo y lo devuelve. NO valida (lo hace la API).

    `nombre` se persiste tal cual lo manda la API; la unicidad case-insensitive la
    garantiza la capa API antes de llegar aqui (un INSERT chocaria con el UNIQUE del
    DDL en caso de duplicado exacto).
    """
    ahora = datetime.now().isoformat(timespec="seconds")
    fila = {
        "id": uuid.uuid4().hex[:12],
        "nombre": nombre,
        "descripcion": descripcion or "",
        "color": color or "",
        "inicio": inicio or "",
        "fin": fin or "",
        "activo": 1 if activo else 0,
        "creado": ahora,
        "actualizado": ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_PROGRAMA_ROTA)
        con.execute(
            f"INSERT INTO rota_programas ({', '.join(_COLS_PROGRAMA_ROTA)}) "
            f"VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_PROGRAMA_ROTA),
        )
        con.commit()
    finally:
        con.close()
    fila["activo"] = bool(fila["activo"])
    return fila


def listar_programas_rota(*, activo: bool | None = None) -> list[dict[str, Any]]:
    """Programas del catalogo, ordenados por nombre. `activo` filtra; None = todos."""
    sql = _SELECT_PROGRAMA_ROTA
    params: tuple[Any, ...] = ()
    if activo is not None:
        sql += " WHERE activo = ?"
        params = (1 if activo else 0,)
    sql += " ORDER BY LOWER(nombre) ASC, id ASC"
    con = _conectar()
    try:
        filas = con.execute(sql, params).fetchall()
    finally:
        con.close()
    return [_fila_a_programa_rota(f) for f in filas]


def obtener_programa_rota(programa_id: str) -> dict[str, Any] | None:
    """Un programa por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_PROGRAMA_ROTA} WHERE id = ?", (programa_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_programa_rota(fila) if fila is not None else None


def actualizar_programa_rota(
    programa_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita parcialmente un programa; None si el id no existe.

    Si el cambio incluye `nombre` y es distinto al actual, hace CASCADA sobre
    `rota_piezas` (UPDATE `programa` por el nombre antiguo) en LA MISMA TRANSACCION:
    ningun escenario deja piezas referenciando a un nombre que ya no existe.

    NOTA: la unicidad case-insensitive y el control de existencia los valida la capa API
    ANTES de llamar (defensa en profundidad: el UNIQUE del DDL es el ultimo cerrojo).
    """
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_PROGRAMA_ROTA}
    if not cambios:
        return obtener_programa_rota(programa_id)
    if "activo" in cambios:
        cambios["activo"] = 1 if cambios["activo"] else 0
    ahora = datetime.now().isoformat(timespec="seconds")
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = [*cambios.values(), ahora, programa_id]
    con = _conectar()
    try:
        # 1) Cargar el nombre ACTUAL para detectar el rename y disparar la cascada.
        fila_actual = con.execute(
            "SELECT nombre FROM rota_programas WHERE id = ?", (programa_id,)
        ).fetchone()
        if fila_actual is None:
            return None
        nombre_actual = fila_actual["nombre"]
        nuevo_nombre = cambios.get("nombre")
        # 2) UPDATE del programa.
        con.execute(
            f"UPDATE rota_programas SET {', '.join(asignaciones)} WHERE id = ?",
            tuple(params),
        )
        # 3) Cascada en piezas si el nombre cambio realmente.
        if isinstance(nuevo_nombre, str) and nuevo_nombre and nuevo_nombre != nombre_actual:
            con.execute(
                "UPDATE rota_piezas SET programa = ?, actualizado = ? WHERE programa = ?",
                (nuevo_nombre, ahora, nombre_actual),
            )
        con.commit()
        fila = con.execute(
            f"{_SELECT_PROGRAMA_ROTA} WHERE id = ?", (programa_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_programa_rota(fila) if fila is not None else None


def borrar_programa_rota(programa_id: str) -> bool:
    """Borra un programa; True si existia, False si no.

    NO arrastra cascada sobre `rota_piezas`: la capa API decide si bloquea el borrado
    cuando hay piezas usando el nombre (con `?forzar=true` se permite igualmente y las
    piezas siguen mostrando el nombre textual). Esto vive en `api/rota.py`.
    """
    con = _conectar()
    try:
        cur = con.execute("DELETE FROM rota_programas WHERE id = ?", (programa_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()



# --------------------------------------------------------------------------- #
# Franjas por semana (#XYZ "Mundial"): CRUD de `rota_franjas`                  #
# --------------------------------------------------------------------------- #
#
# Cada semana tiene sus propias franjas (nombre libre, rangos HH:MM, solapes permitidos,
# soporte a franjas que cruzan medianoche). Se siembran 2 por defecto ("Mañana", "Tarde")
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


def sembrar_franjas_por_defecto(lunes: str, marca: str = "") -> list[dict[str, Any]]:
    """Idempotente: siembra ("Mañana", "Tarde", "Descanso") para `(marca, lunes)` si faltan.

    Devuelve la lista de franjas de ESA marca tras el sembrado (orden ASC). Si ya estan las
    tres, no toca nada.

    GRID POR MARCA: siembra la rejilla de UNA marca. La API NO siembra en "Todas" (sin marca
    concreta no hay rejilla que sembrar).
    """
    if not lunes:
        return []
    con = _conectar()
    try:
        _sembrar_franjas_por_defecto_en(con, lunes, marca)
        con.commit()
    finally:
        con.close()
    return listar_franjas_semana(lunes, marca or None)



# --------------------------------------------------------------------------- #
# Solicitudes de cambio de turno entre companeros (#175)                       #
# --------------------------------------------------------------------------- #
#
# Cuando un CM (solicitante A) necesita cubrir un asunto personal le pide a un
# companero (B) intercambiar el turno de un dia por el de otro. B acepta/rechaza, y si
# acepta, Elias (admin) aprueba o rechaza. La aprobacion EJECUTA el swap en
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



# --------------------------------------------------------------------------- #
# Config de franjas (#185): singleton id='default'                              #
# --------------------------------------------------------------------------- #


_COLS_CONFIG_FRANJAS = (
    "matutino_inicio",
    "matutino_fin",
    "vespertino_inicio",
    "vespertino_fin",
    "actualizado",
)


def obtener_franjas_config(marca: str = "") -> dict[str, str]:
    """Lee la config de franjas DE UNA MARCA. Si no existe, devuelve los DEFAULTS del dominio.

    GRID POR MARCA: la config es por marca — `rota_config_franjas.id` guarda el id de la marca.
    Sin marca (vista "Todas" / legado) cae al singleton `'default'`. No SELECT-INSERT race: si
    la fila aun no esta, la crea el PATCH del admin; mientras, `mapear_franja` usa los defaults.
    """
    con = _conectar()
    try:
        fila = con.execute(
            f"SELECT {', '.join(_COLS_CONFIG_FRANJAS)} FROM rota_config_franjas "
            "WHERE id = ?",
            (marca or "default",),
        ).fetchone()
    finally:
        con.close()
    if fila is None:
        return {
            "matutino_inicio": "08:00",
            "matutino_fin": "16:00",
            "vespertino_inicio": "16:00",
            "vespertino_fin": "24:00",
            "actualizado": "",
        }
    return {col: fila[col] for col in _COLS_CONFIG_FRANJAS}


def guardar_franjas_config(
    matutino_inicio: str,
    matutino_fin: str,
    vespertino_inicio: str,
    vespertino_fin: str,
    marca: str = "",
) -> dict[str, str]:
    """Hace UPSERT de la config de franjas DE UNA MARCA. Devuelve la fila resultante.

    GRID POR MARCA: `rota_config_franjas.id` guarda el id de la marca; sin marca cae al
    singleton `'default'`. Cada marca define los rangos por defecto de su rejilla.
    """
    ahora = datetime.now().isoformat(timespec="seconds")
    clave = marca or "default"
    con = _conectar()
    try:
        # INSERT ... ON CONFLICT DO UPDATE (Postgres): si la fila existe, actualiza.
        con.execute(
            "INSERT INTO rota_config_franjas "
            "(id, matutino_inicio, matutino_fin, vespertino_inicio, vespertino_fin, "
            " actualizado) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (id) DO UPDATE SET "
            "matutino_inicio = EXCLUDED.matutino_inicio, "
            "matutino_fin = EXCLUDED.matutino_fin, "
            "vespertino_inicio = EXCLUDED.vespertino_inicio, "
            "vespertino_fin = EXCLUDED.vespertino_fin, "
            "actualizado = EXCLUDED.actualizado",
            (
                clave,
                matutino_inicio,
                matutino_fin,
                vespertino_inicio,
                vespertino_fin,
                ahora,
            ),
        )
        con.commit()
    finally:
        con.close()
    return obtener_franjas_config(marca)


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
    ahora = datetime.now().isoformat(timespec="seconds")
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
    params.append(datetime.now().isoformat(timespec="seconds"))
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
      - None si el `swap_id` no existe.
    """
    ahora = datetime.now().isoformat(timespec="seconds")
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
        fila = con.execute(
            f"{_SELECT_SWAP_TURNO} WHERE id = ?", (swap_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_swap_turno(fila) if fila is not None else None



# --------------------------------------------------------------------------- #
# Asignacion flexible (rama rota-asignacion-flexible): helpers de lote + copiar #
# --------------------------------------------------------------------------- #
#
# Soporte para las herramientas de la consola sobre asignacion a mano: edicion
# masiva de turnos (multi-select), copia de la semana anterior, y panel de carga.
# La asignacion es 100% manual; ningun algoritmo de reparto vive aqui.


def actualizar_turnos_rota_lote(
    ids: list[str], campos: dict[str, Any]
) -> tuple[int, list[dict[str, Any]]]:
    """UPDATE masivo sobre `rota_turnos` para los `ids` dados. Devuelve `(n, turnos)`.

    `campos` solo aplica las claves editables (mismas que `actualizar_turno_rota`). `n`
    es el rowcount del UPDATE; `turnos` son los registros tras el cambio (SELECT por ids,
    para que la API devuelva el estado fresco sin tirar de los call sites uno a uno).

    Si `ids` viene vacio o no hay campos editables, no toca BD y devuelve `(0, [])`.
    """
    if not ids:
        return 0, []
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_TURNO_ROTA}
    if not cambios:
        return 0, []
    if "override" in cambios:
        cambios["override"] = 1 if cambios["override"] else 0
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = list(cambios.values())
    params.append(datetime.now().isoformat(timespec="seconds"))
    marcadores = ", ".join("?" for _ in ids)
    sql_update = (
        f"UPDATE rota_turnos SET {', '.join(asignaciones)} "
        f"WHERE id IN ({marcadores})"  # noqa: S608 -- columnas de allowlist
    )
    sql_select = f"{_SELECT_TURNO_ROTA} WHERE id IN ({marcadores})"  # noqa: S608
    con = _conectar()
    try:
        cur = con.execute(sql_update, tuple(params) + tuple(ids))
        con.commit()
        filas = con.execute(sql_select, tuple(ids)).fetchall()
    finally:
        con.close()
    return cur.rowcount, [_fila_a_turno_rota(f) for f in filas]


def copiar_turnos_rota(
    de_lunes: str, a_lunes: str, *, reemplazar: bool = False, marca: str | None = None
) -> int:
    """Copia los turnos (horario persona×dia×franja) de `de_lunes` a `a_lunes`.

    Para cada turno de la semana origen, crea uno nuevo en la semana destino con `fecha`
    desplazada +N dias (N = `a_lunes - de_lunes`). Tambien CLONA las definiciones de
    franjas de la semana origen a la destino (mismo nombre/inicio/fin/orden) si la semana
    destino aun no tiene una franja con ese nombre — asi los turnos clonados se enlazan a
    una franja real en la semana destino. Los IDs son nuevos (uuid); el `estado` arranca
    como `propuesto` (Elias re-aprueba antes de publicar). Si `reemplazar=True`, primero
    borra los turnos existentes de `a_lunes` (las franjas NO se borran: no son turnos).

    GRID POR MARCA: con `marca` copia SOLO la rejilla de esa marca (franjas y turnos); el
    clon (franjas y turnos destino) hereda esa marca. La API exige marca concreta para copiar.

    Devuelve cuantas filas de turnos se crearon. Si `de_lunes` o `a_lunes` no son fechas
    validas, devuelve 0 sin tocar BD.
    """
    try:
        d_de = date.fromisoformat(de_lunes)
        d_a = date.fromisoformat(a_lunes)
    except (ValueError, TypeError):
        return 0
    delta = (d_a - d_de).days
    marca_val = marca or ""
    con = _conectar()
    try:
        # PASO 1: clonar las definiciones de franjas a la semana destino (si no estan ya).
        # Las franjas son "plantilla" de cobertura por semana; al copiar la semana entera,
        # las franjas viajan tambien con su nombre/inicio/fin/orden. El mapeo es por
        # NOMBRE: si la semana destino ya tiene "Mañana", reusamos su id. Acotado a la marca.
        clausula_marca = " AND marca = ?" if marca else ""
        franjas_origen = con.execute(
            "SELECT id, nombre, inicio, fin, orden, es_descanso FROM rota_franjas "
            f"WHERE lunes = ?{clausula_marca} ORDER BY orden ASC, nombre ASC",  # noqa: S608 -- fragmento fijo
            (de_lunes, marca) if marca else (de_lunes,),
        ).fetchall()
        franjas_destino = con.execute(
            f"SELECT id, nombre FROM rota_franjas WHERE lunes = ?{clausula_marca}",  # noqa: S608 -- fragmento fijo
            (a_lunes, marca) if marca else (a_lunes,),
        ).fetchall()
        id_destino_por_nombre = {f["nombre"]: f["id"] for f in franjas_destino}
        # Mapeo id_origen -> id_destino (insertando las que falten).
        id_dest_por_origen: dict[str, str] = {}
        for fo in franjas_origen:
            if fo["nombre"] in id_destino_por_nombre:
                id_dest_por_origen[fo["id"]] = id_destino_por_nombre[fo["nombre"]]
                continue
            nuevo_id = uuid.uuid4().hex[:12]
            con.execute(
                "INSERT INTO rota_franjas (id, lunes, nombre, inicio, fin, orden, es_descanso, marca) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (marca, lunes, nombre) DO NOTHING",
                (
                    nuevo_id,
                    a_lunes,
                    fo["nombre"],
                    fo["inicio"],
                    fo["fin"],
                    fo["orden"],
                    bool(fo["es_descanso"]),
                    marca_val,
                ),
            )
            id_dest_por_origen[fo["id"]] = nuevo_id
            id_destino_por_nombre[fo["nombre"]] = nuevo_id

        if reemplazar:
            con.execute(
                f"DELETE FROM rota_turnos WHERE semana = ?{clausula_marca}",  # noqa: S608 -- fragmento fijo
                (a_lunes, marca) if marca else (a_lunes,),
            )
        filas = con.execute(
            f"{_SELECT_TURNO_ROTA} WHERE semana = ?{clausula_marca} ORDER BY fecha ASC, franja_id ASC",  # noqa: S608 -- fragmento fijo
            (de_lunes, marca) if marca else (de_lunes,),
        ).fetchall()
        creadas = 0
        ahora = datetime.now().isoformat(timespec="seconds")
        marcadores = ", ".join("?" for _ in _COLS_TURNO_ROTA)
        for f in filas:
            fila = _fila_a_turno_rota(f)
            # Desplaza la fecha +delta dias; si no parsea, salta esa fila.
            try:
                nueva_fecha = (date.fromisoformat(fila["fecha"]) + timedelta(days=delta)).isoformat()
            except (ValueError, TypeError):
                continue
            franja_id_dest = id_dest_por_origen.get(fila["franja_id"], "")
            if not franja_id_dest:
                # Sin franja destino no podemos enlazar el turno: lo saltamos (defensa).
                continue
            nuevo = {
                "id": uuid.uuid4().hex[:12],
                "semana": a_lunes,
                "fecha": nueva_fecha,
                "miembro_id": fila["miembro_id"],
                "miembro_nombre": fila["miembro_nombre"],
                "franja_id": franja_id_dest,
                "estado": ESTADO_ROTA_PROPUESTO,
                "override": 1 if fila["override"] else 0,
                "motivo": fila["motivo"],
                "nota_relevo": fila["nota_relevo"],
                "creado": ahora,
                "actualizado": ahora,
                # GRID POR MARCA: el clon hereda la marca de la rejilla copiada (o la del origen).
                "marca": marca_val or fila.get("marca", ""),
            }
            con.execute(
                f"INSERT INTO rota_turnos ({', '.join(_COLS_TURNO_ROTA)}) "
                f"VALUES ({marcadores})",
                tuple(nuevo[col] for col in _COLS_TURNO_ROTA),
            )
            creadas += 1
        con.commit()
    finally:
        con.close()
    return creadas



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
    ahora = datetime.now().isoformat(timespec="seconds")
    con = _conectar()
    try:
        fila_existente = con.execute(
            "SELECT id FROM rota_coordinacion WHERE fecha = ? AND franja_id = ?",
            (fecha, franja_id),
        ).fetchone()
        if fila_existente is not None:
            con.execute(
                "UPDATE rota_coordinacion SET coordinador_id = ?, lunes = ?, marca = ?, "
                "actualizado = ? WHERE id = ?",
                (coordinador_id, lunes, marca or "", ahora, fila_existente["id"]),
            )
            con.commit()
            fila = con.execute(
                f"{_SELECT_COORDINACION} WHERE id = ?", (fila_existente["id"],)
            ).fetchone()
            return _fila_a_coordinacion(fila)
        nuevo_id = uuid.uuid4().hex[:12]
        con.execute(
            "INSERT INTO rota_coordinacion "
            "(id, lunes, fecha, franja_id, coordinador_id, creado, actualizado, marca) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (nuevo_id, lunes, fecha, franja_id, coordinador_id, ahora, ahora, marca or ""),
        )
        con.commit()
        fila = con.execute(
            f"{_SELECT_COORDINACION} WHERE id = ?", (nuevo_id,)
        ).fetchone()
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
