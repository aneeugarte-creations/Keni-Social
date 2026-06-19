"""Persistencia — dominio editor: gestor de AUDIO (transcripciones audio→texto). Ver barrel `db.py`."""
from __future__ import annotations

from ..tiempo import ahora_iso
from ._comun import Any, _conectar, uuid

# --------------------------------------------------------------------------- #
# Gestor de audio: transcripciones (audio→texto con whisper.cpp v3 turbo)       #
# --------------------------------------------------------------------------- #

# Estados de una transcripcion: 'pendiente' (encolada) -> 'transcribiendo' (ASR en curso) ->
# 'transcrito' (borrador con timestamps) -> 'editado' (correccion humana / agentes de Claude) |
# 'error' (el ASR fallo; el motivo queda en `error`).
ESTADOS_AUDIO_TRANSCRIPCION = ("pendiente", "transcribiendo", "transcrito", "editado", "error")

_COLS_AUDIO_TRANSCRIPCIONES = (
    "id",
    "marca",
    "nombre",
    "media_id",
    "idioma",
    "estado",
    "duracion_ms",
    "segmentos",
    "texto",
    "resumen",
    "error",
    "gen_id",
    "tratamientos",
    "autor_id",
    "creado",
    "actualizado",
)
_SELECT_AUDIO_TRANSCRIPCIONES = (
    f"SELECT {', '.join(_COLS_AUDIO_TRANSCRIPCIONES)} FROM audio_transcripciones"
)
# `marca` editable: permite mover un audio entre PERSONAL ('') y una marca.
_CAMPOS_EDITABLES_AUDIO_TRANSCRIPCIONES: tuple[str, ...] = (
    "marca",
    "nombre",
    "idioma",
    "estado",
    "duracion_ms",
    "segmentos",
    "texto",
    "resumen",
    "error",
    "gen_id",
    "tratamientos",
    "autor_id",
)


def _fila_a_audio_transcripcion(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `audio_transcripciones` en dict (con defaults defensivos)."""
    item: dict[str, Any] = {col: fila[col] for col in _COLS_AUDIO_TRANSCRIPCIONES}
    item["idioma"] = fila["idioma"] or "es-MX"
    item["estado"] = (
        fila["estado"] if fila["estado"] in ESTADOS_AUDIO_TRANSCRIPCION else "pendiente"
    )
    item["duracion_ms"] = int(fila["duracion_ms"] or 0)
    return item


def crear_audio_transcripcion(
    *,
    marca: str,
    nombre: str = "",
    media_id: str = "",
    idioma: str = "es-MX",
    estado: str = "pendiente",
    duracion_ms: int = 0,
    segmentos: str = "",
    texto: str = "",
    resumen: str = "",
    error: str = "",
    gen_id: str = "",
    tratamientos: str = "",
    autor_id: str = "",
    id: str = "",
    creado: str = "",
    actualizado: str = "",
) -> dict[str, Any]:
    """Crea una transcripcion de audio y la devuelve. NO valida media_id (lo hace la API).

    `marca`='' => audio PERSONAL (privado de `autor_id`); `marca`<>'' => de marca (colaborativo).
    """
    ahora = ahora_iso()
    fila = {
        "id": id or uuid.uuid4().hex[:12],
        "marca": marca or "",
        "nombre": nombre or "",
        "media_id": media_id or "",
        "idioma": idioma or "es-MX",
        "estado": estado if estado in ESTADOS_AUDIO_TRANSCRIPCION else "pendiente",
        "duracion_ms": int(duracion_ms or 0),
        "segmentos": segmentos or "",
        "texto": texto or "",
        "resumen": resumen or "",
        "error": error or "",
        "gen_id": gen_id or "",
        "tratamientos": tratamientos or "",
        "autor_id": autor_id or "",
        "creado": creado or ahora,
        "actualizado": actualizado or ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_AUDIO_TRANSCRIPCIONES)
        con.execute(
            f"INSERT INTO audio_transcripciones ({', '.join(_COLS_AUDIO_TRANSCRIPCIONES)}) "
            f"VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_AUDIO_TRANSCRIPCIONES),
        )
        con.commit()
    finally:
        con.close()
    return _fila_a_audio_transcripcion(fila)


def listar_audio_transcripciones(
    *, marca: str | None = None, estado: str | None = None, visible_para: str | None = None
) -> list[dict[str, Any]]:
    """Transcripciones de audio, filtros combinables (AND). Mas recientes primero.

    `visible_para` (id de usuario) acota la VISIBILIDAD: incluye los audios de marca (colaborativos)
    y SOLO los personales (`marca`='') de ese usuario. Sin `visible_para`, solo los de marca.
    """
    clausulas: list[str] = []
    params: list[Any] = []
    if marca:
        clausulas.append("marca = ?")
        params.append(marca)
    if estado:
        clausulas.append("estado = ?")
        params.append(estado)
    if visible_para:
        clausulas.append("(marca <> '' OR autor_id = ?)")
        params.append(visible_para)
    else:
        clausulas.append("marca <> ''")
    sql = _SELECT_AUDIO_TRANSCRIPCIONES
    if clausulas:
        sql += " WHERE " + " AND ".join(clausulas)
    sql += " ORDER BY creado DESC, id DESC"
    con = _conectar()
    try:
        filas = con.execute(sql, tuple(params)).fetchall()
    finally:
        con.close()
    return [_fila_a_audio_transcripcion(f) for f in filas]


def obtener_audio_transcripcion(transcripcion_id: str) -> dict[str, Any] | None:
    """Una transcripcion de audio por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_AUDIO_TRANSCRIPCIONES} WHERE id = ?", (transcripcion_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_audio_transcripcion(fila) if fila is not None else None


def actualizar_audio_transcripcion(
    transcripcion_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita parcialmente; None si el id no existe. Filtra a la lista blanca."""
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_AUDIO_TRANSCRIPCIONES}
    # `estado` fuera del enum se descarta (no rompe; conserva el anterior), igual que video.
    if "estado" in cambios and cambios["estado"] not in ESTADOS_AUDIO_TRANSCRIPCION:
        del cambios["estado"]
    if not cambios:
        return obtener_audio_transcripcion(transcripcion_id)
    ahora = ahora_iso()
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = [*cambios.values(), ahora, transcripcion_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE audio_transcripciones SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            f"{_SELECT_AUDIO_TRANSCRIPCIONES} WHERE id = ?", (transcripcion_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_audio_transcripcion(fila) if fila is not None else None


def borrar_audio_transcripcion(transcripcion_id: str) -> bool:
    """Borra una transcripcion de audio (y sus artefactos); True si existia, False si no."""
    con = _conectar()
    try:
        con.execute(
            "DELETE FROM audio_artefactos WHERE transcripcion_id = ?", (transcripcion_id,)
        )
        cur = con.execute(
            "DELETE FROM audio_transcripciones WHERE id = ?", (transcripcion_id,)
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# Artefactos de un audio (srt / texto / tratamientos de Claude)                 #
# --------------------------------------------------------------------------- #

# Tipos de artefacto. 'srt' (subtitulos, por defecto, solo lectura) y 'texto' (plano) los genera el
# motor; el resto son tratamientos de Claude. 'corregido' es seguimiento de 'preguntas'.
TIPOS_ARTEFACTO = (
    "srt", "texto", "limpio", "resumen", "preguntas", "ideas", "clips", "capitulado", "corregido",
)
# generando (job de Claude en curso) -> listo | error. Los srt/texto nacen 'listo'.
ESTADOS_ARTEFACTO = ("generando", "listo", "error")

_COLS_AUDIO_ARTEFACTOS = (
    "id",
    "transcripcion_id",
    "tipo",
    "titulo",
    "contenido",
    "formato",
    "estado",
    "gen_id",
    "error",
    "origen_id",
    "origen_version",
    "respuestas",
    "creado",
    "actualizado",
)
_SELECT_AUDIO_ARTEFACTOS = f"SELECT {', '.join(_COLS_AUDIO_ARTEFACTOS)} FROM audio_artefactos"
# `contenido`/`estado`/`titulo`/`respuestas` los edita el humano o el post-procesado; el resto
# (incl. la herencia `origen_*`, que fija el linaje al crear) es inmutable.
_CAMPOS_EDITABLES_AUDIO_ARTEFACTOS: tuple[str, ...] = (
    "titulo",
    "contenido",
    "formato",
    "estado",
    "gen_id",
    "error",
    "respuestas",
)


def _fila_a_audio_artefacto(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `audio_artefactos` en dict (con defaults defensivos)."""
    item: dict[str, Any] = {col: fila[col] for col in _COLS_AUDIO_ARTEFACTOS}
    item["formato"] = fila["formato"] or "txt"
    item["estado"] = fila["estado"] if fila["estado"] in ESTADOS_ARTEFACTO else "listo"
    return item


def crear_audio_artefacto(
    *,
    transcripcion_id: str,
    tipo: str,
    titulo: str = "",
    contenido: str = "",
    formato: str = "txt",
    estado: str = "listo",
    gen_id: str = "",
    error: str = "",
    origen_id: str = "",
    origen_version: str = "",
    respuestas: str = "",
    id: str = "",
    creado: str = "",
    actualizado: str = "",
) -> dict[str, Any]:
    """Crea un artefacto de un audio y lo devuelve. `origen_*` fijan su herencia (ver esquema)."""
    ahora = ahora_iso()
    fila = {
        "id": id or uuid.uuid4().hex[:12],
        "transcripcion_id": transcripcion_id or "",
        "tipo": tipo or "",
        "titulo": titulo or "",
        "contenido": contenido or "",
        "formato": formato or "txt",
        "estado": estado if estado in ESTADOS_ARTEFACTO else "listo",
        "gen_id": gen_id or "",
        "error": error or "",
        "origen_id": origen_id or "",
        "origen_version": origen_version or "",
        "respuestas": respuestas or "",
        "creado": creado or ahora,
        "actualizado": actualizado or ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_AUDIO_ARTEFACTOS)
        con.execute(
            f"INSERT INTO audio_artefactos ({', '.join(_COLS_AUDIO_ARTEFACTOS)}) VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_AUDIO_ARTEFACTOS),
        )
        con.commit()
    finally:
        con.close()
    return _fila_a_audio_artefacto(fila)


def listar_audio_artefactos(transcripcion_id: str) -> list[dict[str, Any]]:
    """Artefactos de un audio, en orden de creacion (el srt primero por ser el mas antiguo)."""
    con = _conectar()
    try:
        filas = con.execute(
            f"{_SELECT_AUDIO_ARTEFACTOS} WHERE transcripcion_id = ? ORDER BY creado ASC, id ASC",
            (transcripcion_id,),
        ).fetchall()
    finally:
        con.close()
    return [_fila_a_audio_artefacto(f) for f in filas]


def obtener_audio_artefacto(artefacto_id: str) -> dict[str, Any] | None:
    """Un artefacto por id (None si no existe)."""
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_AUDIO_ARTEFACTOS} WHERE id = ?", (artefacto_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_audio_artefacto(fila) if fila is not None else None


def actualizar_audio_artefacto(artefacto_id: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    """Edita parcialmente; None si el id no existe. Filtra a la lista blanca."""
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_AUDIO_ARTEFACTOS}
    if "estado" in cambios and cambios["estado"] not in ESTADOS_ARTEFACTO:
        del cambios["estado"]
    if not cambios:
        return obtener_audio_artefacto(artefacto_id)
    ahora = ahora_iso()
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = [*cambios.values(), ahora, artefacto_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE audio_artefactos SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            f"{_SELECT_AUDIO_ARTEFACTOS} WHERE id = ?", (artefacto_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_audio_artefacto(fila) if fila is not None else None


def borrar_audio_artefacto(artefacto_id: str) -> bool:
    """Borra un artefacto; True si existia, False si no."""
    con = _conectar()
    try:
        cur = con.execute("DELETE FROM audio_artefactos WHERE id = ?", (artefacto_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()
