"""Persistencia — dominio comercial. Implementación de db.py (ver barrel `db.py`)."""
from __future__ import annotations

from ._db_comun import (
    Any,
    _conectar,
    date,
    datetime,
    json,
    uuid,
)

# --------------------------------------------------------------------------- #
# Publicaciones comerciales (seguimiento de UNA pieza por su link)             #
# --------------------------------------------------------------------------- #
#
# A diferencia de las `publicaciones` editoriales (que viven en YAML), esto monitoriza
# el rendimiento de una pieza ya publicada: se registra su link, se le toman snapshots
# periodicos de interacciones/alcance (serie temporal) y, al llegar el KPI, se arma su
# reporte. Es dato OPERACIONAL append-only: no encaja como un fichero por entidad, por
# eso vive en SQLite.

# Columnas de `comercial_publicaciones` en orden de declaracion (reusadas en SELECT/INSERT).
_COLS_COMERCIAL = (
    "id",
    "url",
    "id_post_metricool",
    "titulo",
    "marca",
    "cliente",
    "campania",
    "red",
    "formato",
    "metrica_objetivo",
    "objetivo",
    "estado",
    "publicado",
    "notas",
    "aviso_en",
    "fecha_creacion",
    "fecha_actualizacion",
)
_SELECT_COMERCIAL = f"SELECT {', '.join(_COLS_COMERCIAL)} FROM comercial_publicaciones"

# Campos que la edicion parcial puede tocar (url y fechas/aviso son inmutables desde la API).
_CAMPOS_EDITABLES_COMERCIAL = (
    "titulo",
    "marca",
    "cliente",
    "campania",
    "red",
    "formato",
    "metrica_objetivo",
    "objetivo",
    "estado",
    "publicado",
    "notas",
)


def _fila_a_comercial(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `comercial_publicaciones` en un dict (`objetivo` como int)."""
    pub = {col: fila[col] for col in _COLS_COMERCIAL}
    pub["objetivo"] = int(fila["objetivo"] or 0)
    return pub


def crear_publicacion_comercial(
    url: str = "",
    *,
    id_post_metricool: str = "",
    titulo: str = "",
    marca: str = "",
    cliente: str = "",
    campania: str = "",
    red: str = "",
    formato: str = "",
    metrica_objetivo: str = "interacciones",
    objetivo: int = 0,
    estado: str = "activa",
    publicado: str = "",
    notas: str = "",
) -> dict[str, Any]:
    """Inserta una publicacion comercial a monitorear y la devuelve.

    La pieza se identifica por su `id_post_metricool` (el post real de Metricool); `url`
    es derivada/opcional (la trae el propio post). NO valida marca/red/estado/metrica (lo
    hace la API contra sus allowlists). `aviso_en` nace vacio; se rellena la primera vez
    que el valor supera el objetivo.
    """
    ahora = datetime.now().isoformat(timespec="seconds")
    fila = {
        "id": uuid.uuid4().hex[:12],
        "url": url,
        "id_post_metricool": id_post_metricool,
        "titulo": titulo,
        "marca": marca,
        "cliente": cliente,
        "campania": campania,
        "red": red,
        "formato": formato or "",
        "metrica_objetivo": metrica_objetivo or "interacciones",
        "objetivo": int(objetivo or 0),
        "estado": estado or "activa",
        "publicado": publicado or date.today().isoformat(),
        "notas": notas,
        "aviso_en": "",
        "fecha_creacion": ahora,
        "fecha_actualizacion": ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_COMERCIAL)
        con.execute(
            f"INSERT INTO comercial_publicaciones ({', '.join(_COLS_COMERCIAL)}) "
            f"VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_COMERCIAL),
        )
        con.commit()
    finally:
        con.close()
    return fila


def listar_publicaciones_comerciales(
    estado: str | None = None,
    cliente: str | None = None,
    campania: str | None = None,
) -> list[dict[str, Any]]:
    """Publicaciones comerciales (mas recientes primero), con filtros opcionales."""
    clausulas: list[str] = []
    params: list[Any] = []
    if estado:
        clausulas.append("estado = ?")
        params.append(estado)
    if cliente:
        clausulas.append("cliente = ?")
        params.append(cliente)
    if campania:
        clausulas.append("campania = ?")
        params.append(campania)
    sql = _SELECT_COMERCIAL
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)
    # Desempate por `id` (uuid, PK presente en ambos backends) en vez del `rowid` de
    # SQLite (que Postgres no tiene). Solo influye cuando dos piezas comparten
    # `fecha_creacion` (mismo segundo): un orden estable y portable, no autoritativo.
    sql += " ORDER BY fecha_creacion DESC, id DESC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_comercial(f) for f in filas]


def obtener_publicacion_comercial(publicacion_id: str) -> dict[str, Any] | None:
    """Una publicacion comercial por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_COMERCIAL} WHERE id = ?", (publicacion_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_comercial(fila) if fila is not None else None


def actualizar_publicacion_comercial(
    publicacion_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita parcialmente una publicacion comercial; None si el id no existe.

    Solo toca los campos de `_CAMPOS_EDITABLES_COMERCIAL`; ignora el resto. Pone
    `fecha_actualizacion` a ahora. NO valida (lo hace la API).
    """
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_COMERCIAL}
    if "objetivo" in cambios:
        cambios["objetivo"] = int(cambios["objetivo"] or 0)
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("fecha_actualizacion = ?")
    params: list[Any] = list(cambios.values())
    params.append(datetime.now().isoformat(timespec="seconds"))
    params.append(publicacion_id)
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE comercial_publicaciones SET {', '.join(asignaciones)} WHERE id = ?",
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            f"{_SELECT_COMERCIAL} WHERE id = ?", (publicacion_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_comercial(fila) if fila is not None else None


def marcar_aviso_comercial(publicacion_id: str, ts: str) -> None:
    """Marca el instante en que la pieza alcanzo su objetivo (solo la PRIMERA vez).

    El `WHERE aviso_en = ''` lo hace idempotente: una vez avisada, no se re-marca.
    """
    con = _conectar()
    try:
        con.execute(
            "UPDATE comercial_publicaciones SET aviso_en = ? WHERE id = ? AND aviso_en = ''",
            (ts, publicacion_id),
        )
        con.commit()
    finally:
        con.close()


def borrar_publicacion_comercial(publicacion_id: str) -> bool:
    """Borra una publicacion comercial y sus snapshots; True si existia, False si no."""
    con = _conectar()
    try:
        con.execute(
            "DELETE FROM comercial_snapshots WHERE publicacion_id = ?", (publicacion_id,)
        )
        cur = con.execute(
            "DELETE FROM comercial_publicaciones WHERE id = ?", (publicacion_id,)
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


# --- Snapshots (serie temporal de interacciones/alcance por publicacion) ------

# Metricas GRANULARES por pieza que el snapshot captura ademas de las "base"
# (interacciones/visualizaciones/alcance). Son el desglose que la fuente (Metricool, via
# `servicio.construir_metricas_pieza`) expone por pieza. Una sola tupla mantiene DRY el
# INSERT y los SELECT: anadir una metrica nueva = anadir aqui + a `_DDL_ESQUEMA` +
# `_COLUMNAS_COMERCIAL_SNAPSHOTS_AMPLIADAS`. Todas son enteros con DEFAULT 0 (dato ausente
# -> 0; la UI distingue "sin dato" por interacciones/encontrado, no por estos ceros).
_METRICAS_GRANULARES_SNAPSHOT: tuple[str, ...] = (
    "likes",
    "comentarios",
    "compartidos",
    "guardados",
    "video_views",
    "tiempo_medio_vis_s",
    "clics_enlace",
    "seguidores_netos_atribuidos",
)
# Orden de columnas del SELECT de la serie (base + granulares).
_COLS_SNAPSHOT_LECTURA: tuple[str, ...] = (
    "ts",
    "interacciones",
    "visualizaciones",
    "alcance",
    *_METRICAS_GRANULARES_SNAPSHOT,
)
_SELECT_SNAPSHOT = ", ".join(_COLS_SNAPSHOT_LECTURA)


def _fila_a_snapshot(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `comercial_snapshots` en un dict (ts texto, resto enteros)."""
    snap: dict[str, Any] = {"ts": fila["ts"]}
    for col in _COLS_SNAPSHOT_LECTURA[1:]:
        snap[col] = int(fila[col] or 0)
    return snap


def registrar_snapshot_comercial(
    publicacion_id: str,
    ts: str,
    interacciones: int,
    alcance: int,
    visualizaciones: int = 0,
    *,
    granulares: dict[str, Any] | None = None,
) -> bool:
    """Inserta un snapshot (idempotente por `(publicacion_id, ts)`).

    Devuelve True si inserto una fila nueva, False si ya habia un snapshot en ese `ts`
    (el indice UNICO lo evita; asi re-capturar en el mismo minuto no duplica puntos).

    `granulares` (opcional) trae el desglose por pieza (likes/comentarios/compartidos/
    guardados/video_views/tiempo_medio_vis_s/clics_enlace/seguidores_netos_atribuidos);
    cada campo ausente o `None` se persiste como 0 (defensivo). El llamante normal es
    `comercial._capturar_en`, que lo arma desde el dict de `metricas_pieza.recalcular`.
    """
    granulares = granulares or {}
    cols = ("id", "publicacion_id", "ts", "interacciones", "visualizaciones", "alcance",
            *_METRICAS_GRANULARES_SNAPSHOT)
    valores = [
        uuid.uuid4().hex[:12],
        publicacion_id,
        ts,
        int(interacciones),
        int(visualizaciones),
        int(alcance),
        *(int(granulares.get(campo) or 0) for campo in _METRICAS_GRANULARES_SNAPSHOT),
    ]
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in cols)
        cur = con.execute(
            f"INSERT OR IGNORE INTO comercial_snapshots ({', '.join(cols)}) "
            f"VALUES ({marcadores})",
            tuple(valores),
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# Campañas comerciales (agrupan piezas por hashtag(s) configurables)           #
# --------------------------------------------------------------------------- #
#
# Una campaña no monitoriza piezas sueltas: define un FILTRO (marcas + lista de hashtags) y
# su analítica se computa al vuelo sobre el listado de piezas del periodo (por cada marca),
# cruzando por los hashtags del caption. `marcas` (ids de marca) y `hashtags` (tags sin '#',
# con su casing) se persisten como arrays JSON; la normalización/validación la hace la capa
# de negocio (`campanias.py`), no la DB. Las campañas son MULTIMARCA.

_COLS_CAMPANIA = (
    "id",
    "marcas",
    "nombre",
    "hashtags",
    "activa",
    "fecha_creacion",
    "fecha_actualizacion",
)
_SELECT_CAMPANIA = f"SELECT {', '.join(_COLS_CAMPANIA)} FROM comercial_campanias"
_CAMPOS_EDITABLES_CAMPANIA = ("nombre", "marcas", "hashtags", "activa")


def _lista_json(valor: Any) -> list[str]:
    """Parsea un array JSON de strings (defensivo: lista vacía si no es válido)."""
    try:
        datos = json.loads(valor or "[]")
    except (ValueError, TypeError):
        return []
    return [str(x) for x in datos] if isinstance(datos, list) else []


def _fila_a_campania(fila: Any) -> dict[str, Any]:
    """Convierte una fila en dict (marcas/hashtags como listas, activa bool)."""
    cam = {col: fila[col] for col in _COLS_CAMPANIA}
    cam["marcas"] = _lista_json(fila["marcas"])
    cam["hashtags"] = _lista_json(fila["hashtags"])
    cam["activa"] = bool(fila["activa"])
    return cam


def crear_campania_comercial(
    *,
    marcas: list[str],
    nombre: str,
    hashtags: list[str],
    activa: bool = True,
) -> dict[str, Any]:
    """Inserta una campaña comercial (multimarca) y la devuelve. NO valida (lo hace `campanias.py`)."""
    ahora = datetime.now().isoformat(timespec="seconds")
    fila = {
        "id": uuid.uuid4().hex[:12],
        "marcas": json.dumps(list(marcas), ensure_ascii=False),
        "nombre": nombre,
        "hashtags": json.dumps(list(hashtags), ensure_ascii=False),
        "activa": 1 if activa else 0,
        "fecha_creacion": ahora,
        "fecha_actualizacion": ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_CAMPANIA)
        con.execute(
            f"INSERT INTO comercial_campanias ({', '.join(_COLS_CAMPANIA)}) "
            f"VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_CAMPANIA),
        )
        con.commit()
    finally:
        con.close()
    return _fila_a_campania(fila)


def listar_campanias_comerciales(marca: str | None = None) -> list[dict[str, Any]]:
    """Campañas comerciales (más recientes primero).

    `marca` (opcional) filtra a las campañas que INCLUYEN esa marca. Como `marcas` es un
    array JSON, el filtro se hace en Python tras leer (el volumen de campañas es pequeño).
    """
    sql = f"{_SELECT_CAMPANIA} ORDER BY fecha_creacion DESC, id DESC"
    con = _conectar()
    try:
        filas = con.execute(sql).fetchall()
    finally:
        con.close()
    cams = [_fila_a_campania(f) for f in filas]
    if marca:
        cams = [c for c in cams if marca in c["marcas"]]
    return cams


def obtener_campania_comercial(campania_id: str) -> dict[str, Any] | None:
    """Una campaña comercial por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_CAMPANIA} WHERE id = ?", (campania_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_campania(fila) if fila is not None else None


def actualizar_campania_comercial(
    campania_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita parcialmente una campaña; None si el id no existe.

    Solo toca `nombre`/`marcas`/`hashtags`/`activa`. `marcas`/`hashtags` (si vienen) se
    serializan a JSON; `activa` a 0/1. NO valida (lo hace `campanias.py`).
    """
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_CAMPANIA}
    for clave in ("marcas", "hashtags"):
        if clave in cambios:
            cambios[clave] = json.dumps(list(cambios[clave] or []), ensure_ascii=False)
    if "activa" in cambios:
        cambios["activa"] = 1 if cambios["activa"] else 0
    if not cambios:
        return obtener_campania_comercial(campania_id)
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("fecha_actualizacion = ?")
    params: list[Any] = list(cambios.values())
    params.append(datetime.now().isoformat(timespec="seconds"))
    params.append(campania_id)
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE comercial_campanias SET {', '.join(asignaciones)} WHERE id = ?",
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            f"{_SELECT_CAMPANIA} WHERE id = ?", (campania_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_campania(fila) if fila is not None else None


def borrar_campania_comercial(campania_id: str) -> bool:
    """Borra una campaña; True si existía, False si no."""
    con = _conectar()
    try:
        cur = con.execute(
            "DELETE FROM comercial_campanias WHERE id = ?", (campania_id,)
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()
