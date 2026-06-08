"""Persistencia — dominio parrilla. Implementación de db.py (ver barrel `db.py`)."""
from __future__ import annotations

from ._db_comun import (
    ESTADO_ROTA_PROPUESTO,
    ESTADOS_PIEZA,
    Any,
    _conectar,
    date,
    datetime,
    json,
    timedelta,
    uuid,
)

# --------------------------------------------------------------------------- #
# Piezas de la parrilla (#150, PARRILLA 2026.xlsx)                              #
# --------------------------------------------------------------------------- #
#
# En el Excel de Tescu cada FILA es un POST INDIVIDUAL, no un evento. Una transmision
# como "LIV GOLF Andalucia R1" genera 4 piezas (pre-evento FB/IG/X, reel IG/TK, historia
# "5:15 LINK VIVO", post-evento). Tambien hay campanas EVERGREEN sin evento (Alvaro Fidalgo,
# Real Oviedo, MUNDIAL, Paty Cantu): piezas con `programa` y sin `evento_id`. El workflow de
# produccion del Excel (Material entregado / Contenido entregado / Publicado / Enlace) se
# persiste tal cual; la validacion (estado en allowlist, evento real, responsable real) la
# hace la capa API. `red_social`/`tipo_pieza` son campos LIBRES (Tescu pone "FB, IG, X",
# "HISTORIA", "IG, TK (REEL)", "WEB"; "IMAGEN" / "VIDEO" / "REEL" / "NOTA" / "FIJAR"): no
# encajan en una allowlist cerrada todavia.

_COLS_PIEZA_ROTA = (
    "id",
    "evento_id",
    "programa",
    "red_social",
    "tipo_pieza",
    "contenido_sugerido",
    "dia",
    "hora_post",
    "estado",
    "material_entregado",
    "contenido_entregado",
    "publicado",
    "enlace",
    "responsable_id",
    "responsable_nombre",
    "notas",
    "salida",
    "comentarios",
    "fecha_entrega_material",
    "always_on",
    "creado",
    "actualizado",
)
_SELECT_PIEZA_ROTA = f"SELECT {', '.join(_COLS_PIEZA_ROTA)} FROM rota_piezas"

# Campos editables via `actualizar_pieza_rota` (lista blanca). `id`, `creado` y
# `actualizado` no son editables; este ultimo lo gestiona el sistema. `responsable_id` y
# `responsable_nombre` se pasan como par desde la API (se valida `responsable_id` contra
# un usuario REAL antes de llegar aqui). `always_on` es booleano (0/1).
_CAMPOS_EDITABLES_PIEZA_ROTA: tuple[str, ...] = (
    "evento_id",
    "programa",
    "red_social",
    "tipo_pieza",
    "contenido_sugerido",
    "dia",
    "hora_post",
    "estado",
    "material_entregado",
    "contenido_entregado",
    "publicado",
    "enlace",
    "responsable_id",
    "responsable_nombre",
    "notas",
    "salida",
    "comentarios",
    "fecha_entrega_material",
    "always_on",
)


def _fila_a_pieza_rota(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `rota_piezas` en un dict (booleanos como bool, no 0/1)."""
    pieza: dict[str, Any] = {col: fila[col] for col in _COLS_PIEZA_ROTA}
    pieza["material_entregado"] = bool(fila["material_entregado"])
    pieza["contenido_entregado"] = bool(fila["contenido_entregado"])
    pieza["publicado"] = bool(fila["publicado"])
    pieza["always_on"] = bool(fila["always_on"])
    pieza["estado"] = fila["estado"] or "pendiente"
    return pieza


def crear_pieza_rota(
    *,
    evento_id: str = "",
    programa: str = "",
    red_social: str = "",
    tipo_pieza: str = "",
    contenido_sugerido: str = "",
    dia: str = "",
    hora_post: str = "",
    estado: str = "pendiente",
    material_entregado: bool = False,
    contenido_entregado: bool = False,
    publicado: bool = False,
    enlace: str = "",
    responsable_id: str = "",
    responsable_nombre: str = "",
    notas: str = "",
    salida: str = "",
    comentarios: str = "",
    fecha_entrega_material: str = "",
    always_on: bool = False,
) -> dict[str, Any]:
    """Inserta una pieza de la parrilla y la devuelve. NO valida (lo hace la API).

    Una pieza puede estar atada a un evento (`evento_id`) o ser SUELTA (campana evergreen),
    en cuyo caso el `evento_id` queda vacio y la identifica `programa` (p. ej. "Alvaro
    Fidalgo", "MUNDIAL"). La API obliga a que al menos uno entre `evento_id`, `programa` o
    `contenido_sugerido` este relleno para que la pieza represente algo.

    `salida` es el canal AMPLIO (TV, RADIO, OOH, PROGRAMA, YT, WEB...; distinto de
    `red_social` que es FB/IG/X/TK). `comentarios` es texto libre PRE/durante; `notas` es
    post-mortem. `fecha_entrega_material` es el deadline interno antes de `dia`. `always_on`
    marca piezas evergreen sin fecha (la `dia` se permite vacia en ese caso).
    """
    ahora = datetime.now().isoformat(timespec="seconds")
    fila = {
        "id": uuid.uuid4().hex[:12],
        "evento_id": evento_id or "",
        "programa": programa or "",
        "red_social": red_social or "",
        "tipo_pieza": tipo_pieza or "",
        "contenido_sugerido": contenido_sugerido or "",
        "dia": dia or "",
        "hora_post": hora_post or "",
        "estado": estado if estado in ESTADOS_PIEZA else "pendiente",
        "material_entregado": 1 if material_entregado else 0,
        "contenido_entregado": 1 if contenido_entregado else 0,
        "publicado": 1 if publicado else 0,
        "enlace": enlace or "",
        "responsable_id": responsable_id or "",
        "responsable_nombre": responsable_nombre or "",
        "notas": notas or "",
        "salida": salida or "",
        "comentarios": comentarios or "",
        "fecha_entrega_material": fecha_entrega_material or "",
        "always_on": 1 if always_on else 0,
        "creado": ahora,
        "actualizado": ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_PIEZA_ROTA)
        con.execute(
            f"INSERT INTO rota_piezas ({', '.join(_COLS_PIEZA_ROTA)}) VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_PIEZA_ROTA),
        )
        con.commit()
    finally:
        con.close()
    fila["material_entregado"] = bool(fila["material_entregado"])
    fila["contenido_entregado"] = bool(fila["contenido_entregado"])
    fila["publicado"] = bool(fila["publicado"])
    fila["always_on"] = bool(fila["always_on"])
    return fila


def listar_piezas_rota(
    *,
    evento_id: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
    red: str | None = None,
    tipo: str | None = None,
    estado: str | None = None,
    responsable_id: str | None = None,
    programa: str | None = None,
) -> list[dict[str, Any]]:
    """Piezas de la parrilla, ordenadas por dia y orden de creacion. Filtros combinables.

    `desde`/`hasta` acotan por `dia` (ISO inclusivo). `red`/`tipo`/`programa` filtran texto
    EXACTO (los campos son libres; la UI manda el valor exacto). `estado` y `responsable_id`
    filtran como cabe esperar. `evento_id=""` lista las piezas SUELTAS (sin evento).
    """
    clausulas: list[str] = []
    params: list[Any] = []
    if evento_id is not None:
        clausulas.append("evento_id = ?")
        params.append(evento_id)
    if desde:
        clausulas.append("dia >= ?")
        params.append(desde)
    if hasta:
        clausulas.append("dia <= ?")
        params.append(hasta)
    if red:
        clausulas.append("red_social = ?")
        params.append(red)
    if tipo:
        clausulas.append("tipo_pieza = ?")
        params.append(tipo)
    if estado:
        clausulas.append("estado = ?")
        params.append(estado)
    if responsable_id is not None:
        clausulas.append("responsable_id = ?")
        params.append(responsable_id)
    if programa is not None:
        clausulas.append("programa = ?")
        params.append(programa)
    sql = _SELECT_PIEZA_ROTA
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)
    # Por `dia` ASC (las piezas SIN fechar caen al final con DIA="") y luego por orden de
    # creacion para un orden estable (uuid corto desempata si crearon en el mismo segundo).
    sql += " ORDER BY dia ASC, creado ASC, id ASC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_pieza_rota(f) for f in filas]


def obtener_pieza_rota(pieza_id: str) -> dict[str, Any] | None:
    """Una pieza por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_PIEZA_ROTA} WHERE id = ?", (pieza_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_pieza_rota(fila) if fila is not None else None


def actualizar_pieza_rota(
    pieza_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita parcialmente una pieza; None si el id no existe.

    `campos` se filtra a `_CAMPOS_EDITABLES_PIEZA_ROTA` (defensa en profundidad: nunca se
    escriben columnas arbitrarias). Los booleanos se normalizan a 0/1. `actualizado` se
    refresca SIEMPRE que haya cambios reales. La validacion (estado en allowlist, evento
    real, responsable real, enlace acotado) la hace la capa API.
    """
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_PIEZA_ROTA}
    if not cambios:
        return obtener_pieza_rota(pieza_id)
    for col in ("material_entregado", "contenido_entregado", "publicado", "always_on"):
        if col in cambios:
            cambios[col] = 1 if cambios[col] else 0
    ahora = datetime.now().isoformat(timespec="seconds")
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = [*cambios.values(), ahora, pieza_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE rota_piezas SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- columnas de allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            f"{_SELECT_PIEZA_ROTA} WHERE id = ?", (pieza_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_pieza_rota(fila) if fila is not None else None


def borrar_pieza_rota(pieza_id: str) -> bool:
    """Borra una pieza; True si existia, False si no.

    NO arrastra cascada desde `rota_eventos`: borrar un evento NO borra sus piezas (decision
    de la API). Las piezas huerfanas tras borrar el evento siguen accesibles via su programa.
    """
    con = _conectar()
    try:
        cur = con.execute("DELETE FROM rota_piezas WHERE id = ?", (pieza_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def borrar_piezas_rota_lote(ids: list[str]) -> int:
    """Borra varias piezas en una sola sentencia (rowcount). 0 si la lista venia vacia."""
    if not ids:
        return 0
    marcadores = ", ".join("?" for _ in ids)
    con = _conectar()
    try:
        cur = con.execute(
            f"DELETE FROM rota_piezas WHERE id IN ({marcadores})",  # noqa: S608 -- placeholders
            tuple(ids),
        )
        con.commit()
        return cur.rowcount
    finally:
        con.close()


def duplicar_pieza_rota(
    pieza_id: str, *, dia: str | None = None, evento_id: str | None = None
) -> dict[str, Any] | None:
    """Crea una pieza nueva clonando los campos editoriales de `pieza_id`.

    DECISION DE NEGOCIO: el clon RESETEA el WORKFLOW de produccion (material/contenido/
    publicado/enlace -> vacios y `estado` -> "pendiente"): duplicar una pieza es repetir el
    TRABAJO, no copiar la pieza ya publicada. `comentarios` y `notas` tampoco viajan (son
    contexto del POST original, no del clon). `dia`/`evento_id` se pueden sobrescribir con
    los argumentos (caso comun: "Jornada 17 -> Jornada 18"). Devuelve la pieza nueva (con id
    propio y timestamps frescos), o None si el `pieza_id` no existe.
    """
    original = obtener_pieza_rota(pieza_id)
    if original is None:
        return None
    return crear_pieza_rota(
        evento_id=evento_id if evento_id is not None else original.get("evento_id", ""),
        programa=original.get("programa", ""),
        red_social=original.get("red_social", ""),
        tipo_pieza=original.get("tipo_pieza", ""),
        contenido_sugerido=original.get("contenido_sugerido", ""),
        dia=dia if dia is not None else original.get("dia", ""),
        hora_post=original.get("hora_post", ""),
        # Workflow reset: el clon arranca como pendiente y sin material/contenido/publicado.
        estado="pendiente",
        material_entregado=False,
        contenido_entregado=False,
        publicado=False,
        enlace="",
        responsable_id=original.get("responsable_id", ""),
        responsable_nombre=original.get("responsable_nombre", ""),
        notas="",  # post-mortem del original; no aplica al clon.
        salida=original.get("salida", ""),
        comentarios="",  # contexto pre/durante del original; no aplica al clon.
        fecha_entrega_material=original.get("fecha_entrega_material", ""),
        always_on=bool(original.get("always_on", False)),
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
) -> dict[str, Any]:
    """Crea una propuesta en estado `generando` y la devuelve. NO valida (lo hace la API)."""
    ahora = datetime.now().isoformat(timespec="seconds")
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
        cambios["operaciones"] = json.dumps(cambios["operaciones"] or [], ensure_ascii=False)
    if not cambios:
        return obtener_propuesta_parrilla(propuesta_id)
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = list(cambios.values())
    params.append(datetime.now().isoformat(timespec="seconds"))
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
    ahora = datetime.now().isoformat(timespec="seconds")
    eventos_creados: list[str] = []
    turnos_creados: list[str] = []
    turnos_modificados: list[str] = []
    # Cache por semana del mapa {nombre_normalizado -> franja_id} (siembra defaults una vez).
    franjas_por_semana: dict[str, dict[str, str]] = {}

    def _franja_id_de(
        con: Any, semana: str, nombre: str, *, inicio: str = "", fin: str = ""
    ) -> str:
        """Resuelve `nombre` de slot -> `franja_id` de `semana`. PERMISIVO: si el nombre no
        existe en esa semana, CREA la franja (un día puede tener 3+ franjas y el documento
        puede traer slots nuevos), usando `inicio`/`fin` si vienen o un horario por defecto.
        `es_descanso` se infiere del nombre. No rechaza nada por plantilla."""
        if semana not in franjas_por_semana:
            # Cargamos las franjas YA existentes de la semana (sin sembrar: no imponemos la
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
                    "cambiado, actualizado, creado, origen, origen_ref) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                    ),
                )
                eventos_creados.append(eid)
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
        "turnos_creados": len(turnos_creados),
        "turnos_modificados": len(turnos_modificados),
        "ids": {
            "eventos": eventos_creados,
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


# --------------------------------------------------------------------------- #
# Insumos del día (cajones) — tabla `insumos_lote` + `insumos_item`            #
# Contrato: docs/maquina-contenido/01-insumos-del-dia.md                       #
# --------------------------------------------------------------------------- #

_COLS_INSUMO_LOTE = (
    "id", "fecha", "cajon", "marca", "origen_texto", "origen_archivo",
    "estado", "error", "total_items", "creado_por", "creado",
)
_SELECT_INSUMO_LOTE = f"SELECT {', '.join(_COLS_INSUMO_LOTE)} FROM insumos_lote"

_COLS_INSUMO_ITEM = (
    "id", "lote_id", "fecha", "cajon", "marca", "linea",
    "titulo", "resumen", "hora", "lugar", "estado_material",
    "tipo", "idioma", "usado", "contenido_id", "orden", "creado",
)
_SELECT_INSUMO_ITEM = f"SELECT {', '.join(_COLS_INSUMO_ITEM)} FROM insumos_item"

_CAMPOS_EDITABLES_INSUMO_ITEM: tuple[str, ...] = (
    "titulo", "resumen", "marca", "linea", "hora", "lugar", "estado_material", "tipo",
)


def _fila_a_insumo_lote(fila: Any) -> dict[str, Any]:
    """Fila de `insumos_lote` -> dict público (`usado` y enteros normalizados)."""
    return {
        "id": fila["id"],
        "fecha": fila["fecha"] or "",
        "cajon": fila["cajon"] or "",
        "marca": fila["marca"] or "",
        "origen_texto": fila["origen_texto"] or "",
        "origen_archivo": fila["origen_archivo"] or "",
        "estado": fila["estado"] or "listo",
        "error": fila["error"] or "",
        "total_items": int(fila["total_items"] or 0),
        "creado_por": fila["creado_por"] or "",
        "creado": fila["creado"] or "",
    }


def _fila_a_insumo_item(fila: Any) -> dict[str, Any]:
    """Fila de `insumos_item` -> dict público (`usado` como bool)."""
    return {
        "id": fila["id"],
        "lote_id": fila["lote_id"] or "",
        "fecha": fila["fecha"] or "",
        "cajon": fila["cajon"] or "",
        "marca": fila["marca"] or "",
        "linea": fila["linea"] or "",
        "titulo": fila["titulo"] or "",
        "resumen": fila["resumen"] or "",
        "hora": fila["hora"] or "",
        "lugar": fila["lugar"] or "",
        "estado_material": fila["estado_material"] or "",
        "tipo": fila["tipo"] or "nota",
        "idioma": fila["idioma"] or "es",
        "usado": bool(fila["usado"]),
        "contenido_id": fila["contenido_id"] or "",
        "orden": int(fila["orden"] or 0),
        "creado": fila["creado"] or "",
    }


def crear_insumo_lote(
    *,
    fecha: str,
    cajon: str,
    marca: str = "",
    origen_texto: str = "",
    origen_archivo: str = "",
    estado: str = "listo",
    error: str = "",
    total_items: int = 0,
    creado_por: str = "",
) -> dict[str, Any]:
    """Crea un lote de insumos y lo devuelve."""
    ahora = datetime.now().isoformat(timespec="microseconds")
    lote_id = uuid.uuid4().hex[:16]
    fila = {
        "id": lote_id,
        "fecha": fecha or "",
        "cajon": cajon or "",
        "marca": marca or "",
        "origen_texto": origen_texto or "",
        "origen_archivo": origen_archivo or "",
        "estado": estado or "listo",
        "error": error or "",
        "total_items": int(total_items),
        "creado_por": creado_por or "",
        "creado": ahora,
    }
    marcadores = ", ".join("?" for _ in _COLS_INSUMO_LOTE)
    con = _conectar()
    try:
        con.execute(
            f"INSERT INTO insumos_lote ({', '.join(_COLS_INSUMO_LOTE)}) VALUES ({marcadores})",
            tuple(fila[c] for c in _COLS_INSUMO_LOTE),
        )
        con.commit()
    finally:
        con.close()
    return obtener_insumo_lote(lote_id) or _fila_a_insumo_lote(fila)


def actualizar_insumo_lote(lote_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    """Edita parcialmente un lote (estado/error/total_items). None si no existe."""
    permitidos = {"estado", "error", "total_items"}
    cambios = {k: v for k, v in campos.items() if k in permitidos}
    if not cambios:
        return obtener_insumo_lote(lote_id)
    asignaciones = [f"{k} = ?" for k in cambios]
    params: list[Any] = [*cambios.values(), lote_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE insumos_lote SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
    finally:
        con.close()
    return obtener_insumo_lote(lote_id)


def obtener_insumo_lote(lote_id: str) -> dict[str, Any] | None:
    """Un lote por id; None si no existe."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_INSUMO_LOTE} WHERE id = ?", (lote_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_insumo_lote(fila) if fila is not None else None


def borrar_insumo_lote(lote_id: str) -> bool:
    """Borra el lote y todos sus ítems; True si existía, False si no."""
    con = _conectar()
    try:
        con.execute("DELETE FROM insumos_item WHERE lote_id = ?", (lote_id,))
        cur = con.execute("DELETE FROM insumos_lote WHERE id = ?", (lote_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def crear_insumo_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Inserta múltiples ítems en lote (bulk); devuelve los dicts insertados.

    Cada dict debe contener al menos: `lote_id`, `fecha`, `cajon`, `titulo`.
    Los campos ausentes reciben sus valores por defecto.
    """
    ahora = datetime.now().isoformat(timespec="microseconds")
    marcadores = ", ".join("?" for _ in _COLS_INSUMO_ITEM)
    insertados: list[dict[str, Any]] = []
    con = _conectar()
    try:
        for i, item in enumerate(items):
            item_id = uuid.uuid4().hex[:16]
            fila = {
                "id": item_id,
                "lote_id": item.get("lote_id") or "",
                "fecha": item.get("fecha") or "",
                "cajon": item.get("cajon") or "",
                "marca": item.get("marca") or "",
                "linea": item.get("linea") or "",
                "titulo": item.get("titulo") or "",
                "resumen": item.get("resumen") or "",
                "hora": item.get("hora") or "",
                "lugar": item.get("lugar") or "",
                "estado_material": item.get("estado_material") or "",
                "tipo": item.get("tipo") or "nota",
                "idioma": item.get("idioma") or "es",
                "usado": 0,
                "contenido_id": "",
                "orden": item.get("orden", i),
                "creado": ahora,
            }
            con.execute(
                f"INSERT INTO insumos_item ({', '.join(_COLS_INSUMO_ITEM)}) VALUES ({marcadores})",
                tuple(fila[c] for c in _COLS_INSUMO_ITEM),
            )
            insertados.append(_fila_a_insumo_item(fila))
        con.commit()
    finally:
        con.close()
    return insertados


def listar_insumo_items(
    *,
    fecha: str | None = None,
    cajon: str | None = None,
    marca: str | None = None,
    lote_id: str | None = None,
) -> list[dict[str, Any]]:
    """Lista ítems con filtros opcionales, ordenados por (orden ASC, creado ASC)."""
    sql = _SELECT_INSUMO_ITEM
    params: list[Any] = []
    condiciones: list[str] = []
    if fecha is not None:
        condiciones.append("fecha = ?")
        params.append(fecha)
    if cajon is not None:
        condiciones.append("cajon = ?")
        params.append(cajon)
    if marca is not None:
        condiciones.append("marca = ?")
        params.append(marca)
    if lote_id is not None:
        condiciones.append("lote_id = ?")
        params.append(lote_id)
    if condiciones:
        sql += " WHERE " + " AND ".join(condiciones)
    sql += " ORDER BY orden ASC, creado ASC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_insumo_item(f) for f in filas]


def obtener_insumo_item(item_id: str) -> dict[str, Any] | None:
    """Un ítem por id; None si no existe."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_INSUMO_ITEM} WHERE id = ?", (item_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_insumo_item(fila) if fila is not None else None


def actualizar_insumo_item(item_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    """Edita parcialmente un ítem (campos editables del contrato). None si no existe."""
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_INSUMO_ITEM}
    if not cambios:
        return obtener_insumo_item(item_id)
    asignaciones = [f"{k} = ?" for k in cambios]
    params: list[Any] = [*cambios.values(), item_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE insumos_item SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
    finally:
        con.close()
    return obtener_insumo_item(item_id)


def marcar_insumo_item_usado(
    item_id: str, *, contenido_id: str
) -> dict[str, Any] | None:
    """Marca un ítem como usado y guarda el `contenido_id`. None si no existe."""
    con = _conectar()
    try:
        cur = con.execute(
            "UPDATE insumos_item SET usado = 1, contenido_id = ? WHERE id = ?",
            (contenido_id, item_id),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
    finally:
        con.close()
    return obtener_insumo_item(item_id)


def listar_lotes(
    *,
    fecha: str | None = None,
    cajon: str | None = None,
) -> list[dict[str, Any]]:
    """Lista lotes con filtros opcionales (fecha/cajón), más recientes primero."""
    sql = _SELECT_INSUMO_LOTE
    params: list[Any] = []
    condiciones: list[str] = []
    if fecha is not None:
        condiciones.append("fecha = ?")
        params.append(fecha)
    if cajon is not None:
        condiciones.append("cajon = ?")
        params.append(cajon)
    if condiciones:
        sql += " WHERE " + " AND ".join(condiciones)
    sql += " ORDER BY creado DESC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_insumo_lote(f) for f in filas]


def dias_con_insumos() -> list[dict[str, Any]]:
    """Fechas distintas con insumos + total de ítems y desglose por cajón.

    Devuelve lista de dicts `{fecha, total, por_cajon:{portal,corresponsales,reporteros,eventos_claro}}`,
    ordenada por fecha desc. Cuenta ítems (no lotes) para reflejar el volumen editorial real.
    """
    cajones_fijos = ("portal", "corresponsales", "reporteros", "eventos_claro")
    con = _conectar()
    try:
        filas = con.execute(
            "SELECT fecha, cajon, COUNT(*) AS n FROM insumos_item GROUP BY fecha, cajon"
        ).fetchall()
    finally:
        con.close()

    # Agrupa por fecha.
    por_fecha: dict[str, dict[str, int]] = {}
    for f in filas:
        fecha = f["fecha"] or ""
        cajon = f["cajon"] or ""
        n = int(f["n"] or 0)
        if fecha not in por_fecha:
            por_fecha[fecha] = {}
        por_fecha[fecha][cajon] = por_fecha[fecha].get(cajon, 0) + n

    resultado: list[dict[str, Any]] = []
    for fecha in sorted(por_fecha.keys(), reverse=True):
        conteos = por_fecha[fecha]
        por_cajon = {c: conteos.get(c, 0) for c in cajones_fijos}
        resultado.append({
            "fecha": fecha,
            "total": sum(por_cajon.values()),
            "por_cajon": por_cajon,
        })
    return resultado
