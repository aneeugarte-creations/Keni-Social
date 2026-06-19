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
    "creado",
    "actualizado",
)
_SELECT_AUDIO_TRANSCRIPCIONES = (
    f"SELECT {', '.join(_COLS_AUDIO_TRANSCRIPCIONES)} FROM audio_transcripciones"
)
_CAMPOS_EDITABLES_AUDIO_TRANSCRIPCIONES: tuple[str, ...] = (
    "nombre",
    "idioma",
    "estado",
    "duracion_ms",
    "segmentos",
    "texto",
    "resumen",
    "error",
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
    id: str = "",
    creado: str = "",
    actualizado: str = "",
) -> dict[str, Any]:
    """Crea una transcripcion de audio y la devuelve. NO valida media_id (lo hace la API)."""
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
    *, marca: str | None = None, estado: str | None = None
) -> list[dict[str, Any]]:
    """Transcripciones de audio, filtros combinables (AND). Mas recientes primero."""
    clausulas: list[str] = []
    params: list[Any] = []
    if marca:
        clausulas.append("marca = ?")
        params.append(marca)
    if estado:
        clausulas.append("estado = ?")
        params.append(estado)
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
    """Borra una transcripcion de audio; True si existia, False si no."""
    con = _conectar()
    try:
        cur = con.execute(
            "DELETE FROM audio_transcripciones WHERE id = ?", (transcripcion_id,)
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()
