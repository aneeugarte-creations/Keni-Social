"""Persistencia — dominio editor. Implementación de db.py (ver barrel `db.py`)."""
from __future__ import annotations

from ._db_comun import (
    Any,
    IntegrityError,
    _conectar,
    datetime,
    uuid,
)

# --------------------------------------------------------------------------- #
# Biblioteca de MEDIOS interna (ola "activos")                                  #
# --------------------------------------------------------------------------- #
# Tabla `biblioteca_media`: cataloga objetos del almacen de media (`media.py`) por su
# nombre (`objeto`, uuid+ext del servidor) con metadatos editoriales y etiquetas (JSON de
# strings). El binario lo guarda/sirve `media.py`; aqui solo el catalogo reutilizable.

_COLS_BIBLIOTECA_MEDIA = (
    "id",
    "objeto",
    "tipo",
    "titulo",
    "descripcion",
    "marca",
    "etiquetas",
    "credito",
    "aprobado",
    "autor_id",
    "autor_nombre",
    "creado",
    "actualizado",
)
_SELECT_BIBLIOTECA_MEDIA = (
    f"SELECT {', '.join(_COLS_BIBLIOTECA_MEDIA)} FROM biblioteca_media"
)

# Campos editables via `actualizar_media_biblioteca` (lista blanca). `id`, `objeto`,
# `autor_*`, `creado` y `actualizado` no son editables (el objeto NO se reasigna; se
# cataloga uno nuevo si cambia el binario).
_CAMPOS_EDITABLES_BIBLIOTECA_MEDIA: tuple[str, ...] = (
    "tipo",
    "titulo",
    "descripcion",
    "marca",
    "etiquetas",
    "credito",
    "aprobado",
)


def _fila_a_media_biblioteca(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `biblioteca_media` en dict (con defaults defensivos)."""
    item: dict[str, Any] = {col: fila[col] for col in _COLS_BIBLIOTECA_MEDIA}
    item["aprobado"] = bool(fila["aprobado"])
    item["etiquetas"] = fila["etiquetas"] or "[]"
    item["tipo"] = fila["tipo"] or "imagen"
    return item


def crear_media_biblioteca(
    *,
    objeto: str,
    tipo: str = "imagen",
    titulo: str = "",
    descripcion: str = "",
    marca: str = "",
    etiquetas: str = "[]",
    credito: str = "",
    aprobado: bool = True,
    autor: dict[str, str] | None = None,
    id: str = "",
    creado: str = "",
    actualizado: str = "",
) -> dict[str, Any]:
    """Cataloga un objeto de media en la biblioteca y lo devuelve. NO valida (lo hace la API)."""
    autor = autor or {}
    ahora = datetime.now().isoformat(timespec="seconds")
    fila = {
        "id": id or uuid.uuid4().hex[:12],
        "objeto": objeto or "",
        "tipo": tipo or "imagen",
        "titulo": titulo or "",
        "descripcion": descripcion or "",
        "marca": marca or "",
        "etiquetas": etiquetas or "[]",
        "credito": credito or "",
        "aprobado": 1 if aprobado else 0,
        "autor_id": autor.get("id", "") or "",
        "autor_nombre": autor.get("usuario", "") or "",
        "creado": creado or ahora,
        "actualizado": actualizado or ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_BIBLIOTECA_MEDIA)
        con.execute(
            f"INSERT INTO biblioteca_media ({', '.join(_COLS_BIBLIOTECA_MEDIA)}) "
            f"VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_BIBLIOTECA_MEDIA),
        )
        con.commit()
    finally:
        con.close()
    return _fila_a_media_biblioteca(fila)


def listar_media_biblioteca(
    *,
    marca: str | None = None,
    tipo: str | None = None,
    solo_aprobados: bool = False,
) -> list[dict[str, Any]]:
    """Items de la biblioteca de medios, filtros combinables (AND). Mas recientes primero."""
    clausulas: list[str] = []
    params: list[Any] = []
    if marca:
        clausulas.append("marca = ?")
        params.append(marca)
    if tipo:
        clausulas.append("tipo = ?")
        params.append(tipo)
    if solo_aprobados:
        clausulas.append("aprobado = 1")
    sql = _SELECT_BIBLIOTECA_MEDIA
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)
    sql += " ORDER BY creado DESC, id DESC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_media_biblioteca(f) for f in filas]


def obtener_media_biblioteca(media_id: str) -> dict[str, Any] | None:
    """Un item de la biblioteca por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_BIBLIOTECA_MEDIA} WHERE id = ?", (media_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_media_biblioteca(fila) if fila is not None else None


def existe_media_objeto(objeto: str) -> bool:
    """True si ya hay un item de biblioteca catalogando ese `objeto` (UNIQUE)."""
    con = _conectar()
    try:
        fila = con.execute(
            "SELECT 1 FROM biblioteca_media WHERE objeto = ?", (objeto,)
        ).fetchone()
    finally:
        con.close()
    return fila is not None


def actualizar_media_biblioteca(
    media_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita parcialmente; None si el id no existe. Filtra a la lista blanca."""
    cambios = {
        k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_BIBLIOTECA_MEDIA
    }
    if "aprobado" in cambios:
        cambios["aprobado"] = 1 if cambios["aprobado"] else 0
    if not cambios:
        return obtener_media_biblioteca(media_id)
    ahora = datetime.now().isoformat(timespec="seconds")
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = [*cambios.values(), ahora, media_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE biblioteca_media SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            f"{_SELECT_BIBLIOTECA_MEDIA} WHERE id = ?", (media_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_media_biblioteca(fila) if fila is not None else None


def borrar_media_biblioteca(media_id: str) -> dict[str, Any] | None:
    """Borra un item de la biblioteca; devuelve el item borrado (para limpiar el binario) o None."""
    item = obtener_media_biblioteca(media_id)
    if item is None:
        return None
    con = _conectar()
    try:
        con.execute("DELETE FROM biblioteca_media WHERE id = ?", (media_id,))
        con.commit()
    finally:
        con.close()
    return item



# --------------------------------------------------------------------------- #
# Activos de marca (editor profesional: kit visual reutilizable por marca)       #
# --------------------------------------------------------------------------- #

_COLS_MARCA_ACTIVOS = (
    "id",
    "marca",
    "tipo",
    "nombre",
    "objeto",
    "metadatos",
    "lineas",
    "aprobado",
    "autor_id",
    "autor_nombre",
    "creado",
    "actualizado",
)
_SELECT_MARCA_ACTIVOS = f"SELECT {', '.join(_COLS_MARCA_ACTIVOS)} FROM marca_activos"

# Campos editables via `actualizar_marca_activo` (lista blanca). `id`, `marca`, `objeto`,
# `autor_*` y `creado` no son editables (un activo nuevo se cataloga aparte).
_CAMPOS_EDITABLES_MARCA_ACTIVOS: tuple[str, ...] = (
    "tipo",
    "nombre",
    "metadatos",
    "lineas",
    "aprobado",
)


def _fila_a_marca_activo(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `marca_activos` en dict (con defaults defensivos)."""
    item: dict[str, Any] = {col: fila[col] for col in _COLS_MARCA_ACTIVOS}
    item["aprobado"] = bool(fila["aprobado"])
    item["metadatos"] = fila["metadatos"] or "{}"
    item["lineas"] = fila["lineas"] or "[]"
    item["tipo"] = fila["tipo"] or "arte"
    return item


def crear_marca_activo(
    *,
    marca: str,
    tipo: str = "arte",
    nombre: str = "",
    objeto: str = "",
    metadatos: str = "{}",
    lineas: str = "[]",
    aprobado: bool = True,
    autor: dict[str, str] | None = None,
    id: str = "",
    creado: str = "",
    actualizado: str = "",
) -> dict[str, Any]:
    """Cataloga un activo de marca y lo devuelve. NO valida (lo hace la API)."""
    autor = autor or {}
    ahora = datetime.now().isoformat(timespec="seconds")
    fila = {
        "id": id or uuid.uuid4().hex[:12],
        "marca": marca or "",
        "tipo": tipo or "arte",
        "nombre": nombre or "",
        "objeto": objeto or "",
        "metadatos": metadatos or "{}",
        "lineas": lineas or "[]",
        "aprobado": 1 if aprobado else 0,
        "autor_id": autor.get("id", "") or "",
        "autor_nombre": autor.get("usuario", "") or "",
        "creado": creado or ahora,
        "actualizado": actualizado or ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_MARCA_ACTIVOS)
        con.execute(
            f"INSERT INTO marca_activos ({', '.join(_COLS_MARCA_ACTIVOS)}) VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_MARCA_ACTIVOS),
        )
        con.commit()
    finally:
        con.close()
    return _fila_a_marca_activo(fila)


def listar_marca_activos(
    *, marca: str | None = None, tipo: str | None = None, solo_aprobados: bool = False
) -> list[dict[str, Any]]:
    """Activos de marca, filtros combinables (AND). Mas recientes primero."""
    clausulas: list[str] = []
    params: list[Any] = []
    if marca:
        clausulas.append("marca = ?")
        params.append(marca)
    if tipo:
        clausulas.append("tipo = ?")
        params.append(tipo)
    if solo_aprobados:
        clausulas.append("aprobado = 1")
    sql = _SELECT_MARCA_ACTIVOS
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)
    sql += " ORDER BY creado DESC, id DESC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_marca_activo(f) for f in filas]


def obtener_marca_activo(activo_id: str) -> dict[str, Any] | None:
    """Un activo de marca por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(f"{_SELECT_MARCA_ACTIVOS} WHERE id = ?", (activo_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_marca_activo(fila) if fila is not None else None


def actualizar_marca_activo(activo_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    """Edita parcialmente; None si el id no existe. Filtra a la lista blanca."""
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_MARCA_ACTIVOS}
    if "aprobado" in cambios:
        cambios["aprobado"] = 1 if cambios["aprobado"] else 0
    if not cambios:
        return obtener_marca_activo(activo_id)
    ahora = datetime.now().isoformat(timespec="seconds")
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = [*cambios.values(), ahora, activo_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE marca_activos SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(f"{_SELECT_MARCA_ACTIVOS} WHERE id = ?", (activo_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_marca_activo(fila) if fila is not None else None


def borrar_marca_activo(activo_id: str) -> dict[str, Any] | None:
    """Borra un activo de marca; devuelve el borrado (para limpiar el binario) o None."""
    item = obtener_marca_activo(activo_id)
    if item is None:
        return None
    con = _conectar()
    try:
        con.execute("DELETE FROM marca_activos WHERE id = ?", (activo_id,))
        con.commit()
    finally:
        con.close()
    return item



# --------------------------------------------------------------------------- #
# Plantillas de diseño (editor profesional: N plantillas reutilizables por marca) #
# --------------------------------------------------------------------------- #

_COLS_PLANTILLAS_DISENO = (
    "id",
    "marca",
    "nombre",
    "categoria",
    "tipo",
    "documento",
    "miniatura",
    "lineas",
    "activo",
    "autor_id",
    "autor_nombre",
    "creado",
    "actualizado",
)
_SELECT_PLANTILLAS_DISENO = f"SELECT {', '.join(_COLS_PLANTILLAS_DISENO)} FROM plantillas_diseno"

_CAMPOS_EDITABLES_PLANTILLAS_DISENO: tuple[str, ...] = (
    "nombre",
    "categoria",
    "tipo",
    "documento",
    "miniatura",
    "lineas",
    "activo",
)


def _fila_a_plantilla_diseno(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `plantillas_diseno` en dict (con defaults defensivos)."""
    item: dict[str, Any] = {col: fila[col] for col in _COLS_PLANTILLAS_DISENO}
    item["activo"] = bool(fila["activo"])
    item["documento"] = fila["documento"] or "{}"
    item["lineas"] = fila["lineas"] or "[]"
    item["categoria"] = fila["categoria"] or "post"
    item["tipo"] = fila["tipo"] if fila["tipo"] in ("foto", "miniatura") else "foto"
    return item


def crear_plantilla_diseno(
    *,
    marca: str,
    nombre: str = "",
    categoria: str = "post",
    tipo: str = "foto",
    documento: str = "{}",
    miniatura: str = "",
    lineas: str = "[]",
    activo: bool = True,
    autor: dict[str, str] | None = None,
    id: str = "",
    creado: str = "",
    actualizado: str = "",
) -> dict[str, Any]:
    """Crea una plantilla de diseño y la devuelve. NO valida el documento (lo hace la API)."""
    autor = autor or {}
    ahora = datetime.now().isoformat(timespec="seconds")
    fila = {
        "id": id or uuid.uuid4().hex[:12],
        "marca": marca or "",
        "nombre": nombre or "",
        "categoria": categoria or "post",
        "tipo": tipo if tipo in ("foto", "miniatura") else "foto",
        "documento": documento or "{}",
        "miniatura": miniatura or "",
        "lineas": lineas or "[]",
        "activo": 1 if activo else 0,
        "autor_id": autor.get("id", "") or "",
        "autor_nombre": autor.get("usuario", "") or "",
        "creado": creado or ahora,
        "actualizado": actualizado or ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_PLANTILLAS_DISENO)
        con.execute(
            f"INSERT INTO plantillas_diseno ({', '.join(_COLS_PLANTILLAS_DISENO)}) VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_PLANTILLAS_DISENO),
        )
        con.commit()
    finally:
        con.close()
    return _fila_a_plantilla_diseno(fila)


def listar_plantillas_diseno(
    *,
    marca: str | None = None,
    categoria: str | None = None,
    tipo: str | None = None,
    solo_activas: bool = False,
) -> list[dict[str, Any]]:
    """Plantillas de diseño, filtros combinables (AND). Mas recientes primero."""
    clausulas: list[str] = []
    params: list[Any] = []
    if marca:
        clausulas.append("marca = ?")
        params.append(marca)
    if categoria:
        clausulas.append("categoria = ?")
        params.append(categoria)
    if tipo:
        clausulas.append("tipo = ?")
        params.append(tipo)
    if solo_activas:
        clausulas.append("activo = 1")
    sql = _SELECT_PLANTILLAS_DISENO
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)
    sql += " ORDER BY creado DESC, id DESC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_plantilla_diseno(f) for f in filas]


def obtener_plantilla_diseno(plantilla_id: str) -> dict[str, Any] | None:
    """Una plantilla de diseño por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(f"{_SELECT_PLANTILLAS_DISENO} WHERE id = ?", (plantilla_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_plantilla_diseno(fila) if fila is not None else None


def actualizar_plantilla_diseno(plantilla_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    """Edita parcialmente; None si el id no existe. Filtra a la lista blanca."""
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_PLANTILLAS_DISENO}
    if "activo" in cambios:
        cambios["activo"] = 1 if cambios["activo"] else 0
    if not cambios:
        return obtener_plantilla_diseno(plantilla_id)
    ahora = datetime.now().isoformat(timespec="seconds")
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = [*cambios.values(), ahora, plantilla_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE plantillas_diseno SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(f"{_SELECT_PLANTILLAS_DISENO} WHERE id = ?", (plantilla_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_plantilla_diseno(fila) if fila is not None else None


def borrar_plantilla_diseno(plantilla_id: str) -> dict[str, Any] | None:
    """Borra una plantilla de diseño; devuelve la borrada o None."""
    item = obtener_plantilla_diseno(plantilla_id)
    if item is None:
        return None
    con = _conectar()
    try:
        con.execute("DELETE FROM plantillas_diseno WHERE id = ?", (plantilla_id,))
        con.commit()
    finally:
        con.close()
    return item



# --------------------------------------------------------------------------- #
# Motor de video: composiciones + subtitulos (Ola VIDEO)                        #
# --------------------------------------------------------------------------- #

# Estados validos de una composicion: 'borrador' (en edicion) | 'listo' (lista para producir).
ESTADOS_VIDEO_COMPOSICION = ("borrador", "listo")

_COLS_VIDEO_COMPOSICIONES = (
    "id",
    "contenido_id",
    "marca",
    "titulo",
    "estado",
    "documento",
    "creado",
    "actualizado",
)
_SELECT_VIDEO_COMPOSICIONES = (
    f"SELECT {', '.join(_COLS_VIDEO_COMPOSICIONES)} FROM video_composiciones"
)
_CAMPOS_EDITABLES_VIDEO_COMPOSICIONES: tuple[str, ...] = (
    "contenido_id",
    "marca",
    "titulo",
    "estado",
    "documento",
)


def _fila_a_video_composicion(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `video_composiciones` en dict (con defaults defensivos)."""
    item: dict[str, Any] = {col: fila[col] for col in _COLS_VIDEO_COMPOSICIONES}
    item["documento"] = fila["documento"] or "{}"
    item["titulo"] = fila["titulo"] or ""
    item["estado"] = fila["estado"] if fila["estado"] in ESTADOS_VIDEO_COMPOSICION else "borrador"
    return item


def crear_video_composicion(
    *,
    marca: str,
    documento: str = "{}",
    contenido_id: str = "",
    titulo: str = "",
    estado: str = "borrador",
    id: str = "",
    creado: str = "",
    actualizado: str = "",
) -> dict[str, Any]:
    """Crea una composicion de video y la devuelve. NO valida el documento (lo hace la API/shared)."""
    ahora = datetime.now().isoformat(timespec="seconds")
    fila = {
        "id": id or uuid.uuid4().hex[:12],
        "contenido_id": contenido_id or "",
        "marca": marca or "",
        "titulo": titulo or "",
        "estado": estado if estado in ESTADOS_VIDEO_COMPOSICION else "borrador",
        "documento": documento or "{}",
        "creado": creado or ahora,
        "actualizado": actualizado or ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_VIDEO_COMPOSICIONES)
        con.execute(
            f"INSERT INTO video_composiciones ({', '.join(_COLS_VIDEO_COMPOSICIONES)}) VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_VIDEO_COMPOSICIONES),
        )
        con.commit()
    finally:
        con.close()
    return _fila_a_video_composicion(fila)


def listar_video_composiciones(
    *, marca: str | None = None, contenido_id: str | None = None
) -> list[dict[str, Any]]:
    """Composiciones de video, filtros combinables (AND). Mas recientes primero."""
    clausulas: list[str] = []
    params: list[Any] = []
    if marca:
        clausulas.append("marca = ?")
        params.append(marca)
    if contenido_id:
        clausulas.append("contenido_id = ?")
        params.append(contenido_id)
    sql = _SELECT_VIDEO_COMPOSICIONES
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)
    sql += " ORDER BY creado DESC, id DESC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_video_composicion(f) for f in filas]


def obtener_video_composicion(composicion_id: str) -> dict[str, Any] | None:
    """Una composicion de video por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_VIDEO_COMPOSICIONES} WHERE id = ?", (composicion_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_video_composicion(fila) if fila is not None else None


def actualizar_video_composicion(composicion_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    """Edita parcialmente; None si el id no existe. Filtra a la lista blanca."""
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_VIDEO_COMPOSICIONES}
    # `estado` fuera del enum se descarta (no rompe; conserva el anterior), igual que subtitulos.
    if "estado" in cambios and cambios["estado"] not in ESTADOS_VIDEO_COMPOSICION:
        del cambios["estado"]
    if not cambios:
        return obtener_video_composicion(composicion_id)
    ahora = datetime.now().isoformat(timespec="seconds")
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = [*cambios.values(), ahora, composicion_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE video_composiciones SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            f"{_SELECT_VIDEO_COMPOSICIONES} WHERE id = ?", (composicion_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_video_composicion(fila) if fila is not None else None


def borrar_video_composicion(composicion_id: str) -> bool:
    """Borra una composicion de video y sus subtitulos asociados; True si existia, False si no.

    `video_subtitulos` no tiene FK declarada (mismo estilo que el resto del esquema), asi que la
    limpieza de la pista de subtitulos es explicita, igual que `borrar_publicacion_comercial`.
    """
    con = _conectar()
    try:
        con.execute(
            "DELETE FROM video_subtitulos WHERE composicion_id = ?", (composicion_id,)
        )
        cur = con.execute("DELETE FROM video_composiciones WHERE id = ?", (composicion_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


# Estados validos de un subtitulo de video (contrato; ver G-video-engine.md).
ESTADOS_VIDEO_SUBTITULO = ("pendiente", "transcrito", "editado", "listo")

_COLS_VIDEO_SUBTITULOS = (
    "id",
    "composicion_id",
    "idioma",
    "estado",
    "segmentos",
    "ass",
    "transcrito_en",
    "actualizado",
)
_SELECT_VIDEO_SUBTITULOS = f"SELECT {', '.join(_COLS_VIDEO_SUBTITULOS)} FROM video_subtitulos"
_CAMPOS_EDITABLES_VIDEO_SUBTITULOS: tuple[str, ...] = (
    "idioma",
    "estado",
    "segmentos",
    "ass",
    "transcrito_en",
)


def _fila_a_video_subtitulo(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `video_subtitulos` en dict (con defaults defensivos)."""
    item: dict[str, Any] = {col: fila[col] for col in _COLS_VIDEO_SUBTITULOS}
    item["idioma"] = fila["idioma"] or "es-MX"
    item["estado"] = fila["estado"] if fila["estado"] in ESTADOS_VIDEO_SUBTITULO else "pendiente"
    return item


def crear_video_subtitulo(
    *,
    composicion_id: str,
    idioma: str = "es-MX",
    estado: str = "pendiente",
    segmentos: str = "",
    ass: str = "",
    transcrito_en: str = "",
    id: str = "",
    actualizado: str = "",
) -> dict[str, Any]:
    """Crea una fila de subtitulos para una composicion y la devuelve."""
    ahora = datetime.now().isoformat(timespec="seconds")
    fila = {
        "id": id or uuid.uuid4().hex[:12],
        "composicion_id": composicion_id or "",
        "idioma": idioma or "es-MX",
        "estado": estado if estado in ESTADOS_VIDEO_SUBTITULO else "pendiente",
        "segmentos": segmentos or "",
        "ass": ass or "",
        "transcrito_en": transcrito_en or "",
        "actualizado": actualizado or ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_VIDEO_SUBTITULOS)
        con.execute(
            f"INSERT INTO video_subtitulos ({', '.join(_COLS_VIDEO_SUBTITULOS)}) VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_VIDEO_SUBTITULOS),
        )
        con.commit()
    finally:
        con.close()
    return _fila_a_video_subtitulo(fila)


def listar_video_subtitulos(
    *, composicion_id: str | None = None, estado: str | None = None
) -> list[dict[str, Any]]:
    """Subtitulos de video, filtros combinables (AND). Mas recientes primero."""
    clausulas: list[str] = []
    params: list[Any] = []
    if composicion_id:
        clausulas.append("composicion_id = ?")
        params.append(composicion_id)
    if estado:
        clausulas.append("estado = ?")
        params.append(estado)
    sql = _SELECT_VIDEO_SUBTITULOS
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)
    sql += " ORDER BY actualizado DESC, id DESC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_video_subtitulo(f) for f in filas]


def obtener_video_subtitulo(subtitulo_id: str) -> dict[str, Any] | None:
    """Un subtitulo de video por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_VIDEO_SUBTITULOS} WHERE id = ?", (subtitulo_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_video_subtitulo(fila) if fila is not None else None


def actualizar_video_subtitulo(subtitulo_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    """Edita parcialmente; None si el id no existe. Filtra a la lista blanca."""
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_VIDEO_SUBTITULOS}
    if "estado" in cambios and cambios["estado"] not in ESTADOS_VIDEO_SUBTITULO:
        cambios.pop("estado")
    if not cambios:
        return obtener_video_subtitulo(subtitulo_id)
    ahora = datetime.now().isoformat(timespec="seconds")
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = [*cambios.values(), ahora, subtitulo_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE video_subtitulos SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            f"{_SELECT_VIDEO_SUBTITULOS} WHERE id = ?", (subtitulo_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_video_subtitulo(fila) if fila is not None else None



# --------------------------------------------------------------------------- #
# Bloques (almacén de capas reutilizables)                                       #
# --------------------------------------------------------------------------- #

_COLS_BLOQUES = (
    "id",
    "marca",
    "nombre",
    "capas",
    "lineas",
    "miniatura",
    "autor_id",
    "autor_nombre",
    "creado",
    "actualizado",
)
_SELECT_BLOQUES = f"SELECT {', '.join(_COLS_BLOQUES)} FROM bloques"
_CAMPOS_EDITABLES_BLOQUES: tuple[str, ...] = ("nombre", "capas", "lineas", "miniatura")


def _fila_a_bloque(fila: Any) -> dict[str, Any]:
    item: dict[str, Any] = {col: fila[col] for col in _COLS_BLOQUES}
    item["capas"] = fila["capas"] or "[]"
    item["lineas"] = fila["lineas"] or "[]"
    return item


def crear_bloque(
    *,
    marca: str = "",
    nombre: str = "",
    capas: str = "[]",
    lineas: str = "[]",
    miniatura: str = "",
    autor: dict[str, str] | None = None,
    id: str = "",
    creado: str = "",
    actualizado: str = "",
) -> dict[str, Any]:
    """Crea un bloque (grupo de capas reutilizable) y lo devuelve."""
    autor = autor or {}
    ahora = datetime.now().isoformat(timespec="seconds")
    fila = {
        "id": id or uuid.uuid4().hex[:12],
        "marca": marca or "",
        "nombre": nombre or "",
        "capas": capas or "[]",
        "lineas": lineas or "[]",
        "miniatura": miniatura or "",
        "autor_id": autor.get("id", "") or "",
        "autor_nombre": autor.get("usuario", "") or "",
        "creado": creado or ahora,
        "actualizado": actualizado or ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_BLOQUES)
        con.execute(
            f"INSERT INTO bloques ({', '.join(_COLS_BLOQUES)}) VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_BLOQUES),
        )
        con.commit()
    finally:
        con.close()
    return _fila_a_bloque(fila)


def listar_bloques(*, marca: str | None = None) -> list[dict[str, Any]]:
    """Bloques, filtro opcional por marca. Mas recientes primero."""
    sql = _SELECT_BLOQUES
    params: list[Any] = []
    if marca:
        sql += " WHERE marca = ?"
        params.append(marca)
    sql += " ORDER BY creado DESC, id DESC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_bloque(f) for f in filas]


def obtener_bloque(bloque_id: str) -> dict[str, Any] | None:
    con = _conectar()
    try:
        fila = con.execute(f"{_SELECT_BLOQUES} WHERE id = ?", (bloque_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_bloque(fila) if fila is not None else None


def actualizar_bloque(bloque_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_BLOQUES}
    if not cambios:
        return obtener_bloque(bloque_id)
    ahora = datetime.now().isoformat(timespec="seconds")
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = [*cambios.values(), ahora, bloque_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE bloques SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(f"{_SELECT_BLOQUES} WHERE id = ?", (bloque_id,)).fetchone()
    finally:
        con.close()
    return _fila_a_bloque(fila) if fila is not None else None


def borrar_bloque(bloque_id: str) -> dict[str, Any] | None:
    item = obtener_bloque(bloque_id)
    if item is None:
        return None
    con = _conectar()
    try:
        con.execute("DELETE FROM bloques WHERE id = ?", (bloque_id,))
        con.commit()
    finally:
        con.close()
    return item



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
