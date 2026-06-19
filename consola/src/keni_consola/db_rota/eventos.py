"""Persistencia — rota: eventos/transmisiones (tabla `rota_eventos`)."""
from __future__ import annotations

from ._comun import (
    PRIORIDAD_EVENTO_DEFECTO,
    PRIORIDADES_EVENTO,
    TIPO_COBERTURA_TRANSMISION,
    TIPOS_COBERTURA,
    Any,
    _conectar,
    ahora_iso,
    uuid,
)

# --------------------------------------------------------------------------- #
# Rota: eventos/transmisiones + turnos (horarios persona×dia×franja)            #
# --------------------------------------------------------------------------- #
#
# Dos entidades operacionales INDEPENDIENTES: el EVENTO (calendario de transmisiones)
# y el TURNO (horario del miembro en (fecha, franja)). Un turno NO va atado a un evento.
# La "cobertura" (quien cubre un evento) es una vista DERIVADA: para un evento, sus coberturas
# son los miembros cuyo turno coincide con la franja+fecha del evento (`mapear_franja` en
# `rota.py`). Pueden existir turnos sin eventos y eventos sin turnos.

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
    "serie_id",
)
_SELECT_EVENTO_ROTA = f"SELECT {', '.join(_COLS_EVENTO_ROTA)} FROM rota_eventos"
_COLS_SERIE_EVENTO = ("id", "dias_semana", "repetir_hasta", "fecha_base", "marca", "creado")
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
    evento["marca"] = fila["marca"] or ""
    evento["serie_id"] = fila["serie_id"] or ""
    return evento


def _nueva_fila_evento(
    titulo: str,
    *,
    fecha: str,
    hora: str,
    contenido: str,
    nota: str,
    tipo_cobertura: str,
    prioridad: str,
    marca: str,
    serie_id: str,
    ahora: str,
) -> dict[str, Any]:
    """Construye la fila de un evento NUEVO (id propio, `cambiado=0`, `actualizado`=`creado`)."""
    return {
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
        "serie_id": serie_id or "",
    }


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
    serie_id: str = "",
) -> dict[str, Any]:
    """Inserta un evento/transmision y lo devuelve. NO valida (lo hace la API).

    Nace `cambiado=0` (sin reprogramar) y con `actualizado`=`creado` (alta = primera version).
    `marca` es el id canonico de la marca a la que pertenece el evento ("" = sin marca asignada).
    `serie_id` agrupa las ocurrencias de un evento recurrente ("" = evento suelto).
    """
    fila = _nueva_fila_evento(
        titulo,
        fecha=fecha,
        hora=hora,
        contenido=contenido,
        nota=nota,
        tipo_cobertura=tipo_cobertura,
        prioridad=prioridad,
        marca=marca,
        serie_id=serie_id,
        ahora=ahora_iso(),
    )
    marcadores = ", ".join("?" for _ in _COLS_EVENTO_ROTA)
    con = _conectar()
    try:
        con.execute(
            f"INSERT INTO rota_eventos ({', '.join(_COLS_EVENTO_ROTA)}) VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_EVENTO_ROTA),
        )
        con.commit()
    finally:
        con.close()
    fila["cambiado"] = bool(fila["cambiado"])
    return fila


def crear_serie_eventos(
    titulo: str,
    *,
    fechas: list[str],
    hora: str = "",
    contenido: str = "",
    nota: str = "",
    tipo_cobertura: str = TIPO_COBERTURA_TRANSMISION,
    prioridad: str = PRIORIDAD_EVENTO_DEFECTO,
    marca: str = "",
    dias_semana_csv: str = "",
    repetir_hasta: str = "",
) -> dict[str, Any]:
    """Materializa una serie recurrente: una fila `rota_eventos` por fecha, todas con el mismo
    `serie_id`, mas la regla en `rota_evento_series`. Todo en UNA transaccion.

    `fechas` son las ocurrencias ya expandidas (las calcula `dominio.recurrencia`, no este modulo).
    Devuelve `{"serie_id": str, "eventos": [evento, ...]}` en el orden de `fechas`. No valida.
    """
    ahora = ahora_iso()
    serie_id = uuid.uuid4().hex[:12]
    filas = [
        _nueva_fila_evento(
            titulo,
            fecha=fecha,
            hora=hora,
            contenido=contenido,
            nota=nota,
            tipo_cobertura=tipo_cobertura,
            prioridad=prioridad,
            marca=marca,
            serie_id=serie_id,
            ahora=ahora,
        )
        for fecha in fechas
    ]
    serie = {
        "id": serie_id,
        "dias_semana": dias_semana_csv or "",
        "repetir_hasta": repetir_hasta or "",
        "fecha_base": fechas[0] if fechas else "",
        "marca": marca or "",
        "creado": ahora,
    }
    marcadores_ev = ", ".join("?" for _ in _COLS_EVENTO_ROTA)
    marcadores_se = ", ".join("?" for _ in _COLS_SERIE_EVENTO)
    insert_ev = f"INSERT INTO rota_eventos ({', '.join(_COLS_EVENTO_ROTA)}) VALUES ({marcadores_ev})"
    con = _conectar()
    try:
        con.execute(
            f"INSERT INTO rota_evento_series ({', '.join(_COLS_SERIE_EVENTO)}) VALUES ({marcadores_se})",
            tuple(serie[col] for col in _COLS_SERIE_EVENTO),
        )
        # La conexion expone `execute`: insertamos una ocurrencia por sentencia, todas en la
        # misma transaccion (commit unico al final). Una serie son <= ~366 ocurrencias.
        for fila in filas:
            con.execute(insert_ev, tuple(fila[col] for col in _COLS_EVENTO_ROTA))
        con.commit()
    finally:
        con.close()
    for fila in filas:
        fila["cambiado"] = bool(fila["cambiado"])
    return {"serie_id": serie_id, "eventos": filas}


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
    REPROGRAMADOS (`cambiado=1`, los que el coordinador de la rota debe re-avisar). `tipo_cobertura` filtra por
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
        el coordinador de la rota) -> se LIMPIA a 0, y limpiar GANA aunque en el mismo request se hubiera
        reprogramado (el coordinador de la rota dice "ya está visto").
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

    ahora = ahora_iso()
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


def obtener_serie_evento(serie_id: str) -> dict[str, Any] | None:
    """Devuelve la regla de la serie (`rota_evento_series`) o None si no existe."""
    if not serie_id:
        return None
    con = _conectar()
    try:
        fila = con.execute(
            f"SELECT {', '.join(_COLS_SERIE_EVENTO)} FROM rota_evento_series WHERE id = ?",
            (serie_id,),
        ).fetchone()
    finally:
        con.close()
    return {col: fila[col] for col in _COLS_SERIE_EVENTO} if fila is not None else None


def borrar_serie_eventos(serie_id: str, *, desde: str | None = None) -> int:
    """Borra las ocurrencias de una serie; devuelve cuantas filas se borraron.

    `desde=None` borra TODA la serie (y su regla); `desde='AAAA-MM-DD'` borra solo las
    ocurrencias con `fecha >= desde` (alcance "este y los siguientes") y conserva la regla
    (la serie sigue viva hacia atras). Sin serie_id no borra nada.
    """
    if not serie_id:
        return 0
    con = _conectar()
    try:
        if desde:
            cur = con.execute(
                "DELETE FROM rota_eventos WHERE serie_id = ? AND fecha >= ?",
                (serie_id, desde),
            )
        else:
            cur = con.execute("DELETE FROM rota_eventos WHERE serie_id = ?", (serie_id,))
            con.execute("DELETE FROM rota_evento_series WHERE id = ?", (serie_id,))
        con.commit()
        return cur.rowcount
    finally:
        con.close()
