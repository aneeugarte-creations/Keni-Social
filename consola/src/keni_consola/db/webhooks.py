"""Persistencia — dominio webhooks. Implementación de db.py (ver barrel `db.py`)."""
from __future__ import annotations

from ._comun import (
    Any,
    IntegrityError,
    _conectar,
    json,
    uuid,
)
from ..tiempo import ahora_iso, iso_o_vacio

# --------------------------------------------------------------------------- #
# Webhooks salientes + bitacora de eventos internos (OPERACIONAL: Postgres)      #
# --------------------------------------------------------------------------- #
# `webhooks` = suscripciones a eventos internos del tablero (pieza aprobada / contenido
# vencido). `eventos_internos` = bitacora de lo EMITIDO (auditoria + idempotencia del
# barrido de vencimientos). El reparto a la red lo hace `dominio/eventos.py`; aqui solo
# se persiste. SAFE BY DEFAULT: sin webhooks activos no sale nada a la red.

_COLS_WEBHOOK = (
    "id",
    "nombre",
    "url",
    "eventos",
    "formato",
    "secreto",
    "activo",
    "ultimo_estado",
    "ultimo_en",
    "autor_id",
    "autor_nombre",
    "creado",
    "actualizado",
)
_SELECT_WEBHOOK = f"SELECT {', '.join(_COLS_WEBHOOK)} FROM webhooks"
# Campos editables (lista blanca). `id`/`creado`/`autor_*` no se editan; `ultimo_*` los
# estampa el repartidor, no la API.
_CAMPOS_EDITABLES_WEBHOOK: tuple[str, ...] = (
    "nombre",
    "url",
    "eventos",
    "formato",
    "secreto",
    "activo",
    "ultimo_estado",
    "ultimo_en",
)


def _fila_a_webhook(fila: Any) -> dict[str, Any]:
    """Convierte una fila de `webhooks` en dict (`eventos` como lista, `activo` como bool).

    NUNCA expone el `secreto` (credencial): se devuelve `tiene_secreto` (bool) en su lugar.
    """
    wh: dict[str, Any] = {col: fila[col] for col in _COLS_WEBHOOK}
    wh["activo"] = bool(fila["activo"])
    try:
        eventos = json.loads(wh["eventos"]) if wh["eventos"] else []
    except (ValueError, TypeError):
        eventos = []
    wh["eventos"] = eventos if isinstance(eventos, list) else []
    wh["tiene_secreto"] = bool(wh.pop("secreto", ""))
    return wh


def crear_webhook(
    *,
    nombre: str = "",
    url: str = "",
    eventos: list[str] | None = None,
    formato: str = "generico",
    secreto: str = "",
    activo: bool = True,
    autor: dict[str, str] | None = None,
    id: str = "",
) -> dict[str, Any]:
    """Inserta una suscripcion de webhook y la devuelve (sin exponer el secreto). NO valida."""
    autor = autor or {}
    ahora = ahora_iso()
    fila = {
        "id": id or uuid.uuid4().hex[:12],
        "nombre": nombre or "",
        "url": url or "",
        "eventos": json.dumps(list(eventos or [])),
        "formato": formato or "generico",
        "secreto": secreto or "",
        "activo": 1 if activo else 0,
        "ultimo_estado": "",
        "ultimo_en": "",
        "autor_id": autor.get("id", "") or "",
        "autor_nombre": autor.get("usuario", "") or "",
        "creado": ahora,
        "actualizado": ahora,
    }
    con = _conectar()
    try:
        marcadores = ", ".join("?" for _ in _COLS_WEBHOOK)
        con.execute(
            f"INSERT INTO webhooks ({', '.join(_COLS_WEBHOOK)}) VALUES ({marcadores})",
            tuple(fila[col] for col in _COLS_WEBHOOK),
        )
        con.commit()
    finally:
        con.close()
    return _fila_a_webhook(fila)


def listar_webhooks(*, solo_activos: bool = False) -> list[dict[str, Any]]:
    """Lista las suscripciones de webhook (sin exponer secretos). Orden estable por creacion."""
    sql = _SELECT_WEBHOOK
    if solo_activos:
        sql += " WHERE activo = 1"
    sql += " ORDER BY creado ASC, id ASC"
    con = _conectar()
    try:
        filas = con.execute(sql).fetchall()
    finally:
        con.close()
    return [_fila_a_webhook(f) for f in filas]


def listar_webhooks_para(evento: str) -> list[dict[str, Any]]:
    """Webhooks ACTIVOS que escuchan `evento` (lista vacia => escucha todos). Incluye el secreto.

    Uso INTERNO del repartidor: a diferencia de `listar_webhooks`, devuelve el `secreto`
    crudo (lo necesita para firmar). NO exponer este resultado por la API.
    """
    con = _conectar()
    try:
        filas = con.execute(f"{_SELECT_WEBHOOK} WHERE activo = 1").fetchall()
    finally:
        con.close()
    salida: list[dict[str, Any]] = []
    for f in filas:
        try:
            eventos = json.loads(f["eventos"]) if f["eventos"] else []
        except (ValueError, TypeError):
            eventos = []
        if eventos and evento not in eventos:
            continue
        salida.append({col: f[col] for col in _COLS_WEBHOOK})
    return salida


def obtener_webhook(webhook_id: str) -> dict[str, Any] | None:
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_WEBHOOK} WHERE id = ?", (webhook_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_webhook(fila) if fila is not None else None


def obtener_webhook_con_secreto(webhook_id: str) -> dict[str, Any] | None:
    """Una suscripcion por id CON su secreto crudo (uso interno: probar/repartir). None si no existe.

    A diferencia de `obtener_webhook`, expone el `secreto` para firmar la entrega. NO
    devolver este dict por la API.
    """
    con = _conectar()
    try:
        fila = con.execute(
            f"{_SELECT_WEBHOOK} WHERE id = ?", (webhook_id,)
        ).fetchone()
    finally:
        con.close()
    return {col: fila[col] for col in _COLS_WEBHOOK} if fila is not None else None


def actualizar_webhook(
    webhook_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita parcialmente una suscripcion; None si no existe. Filtra a la lista blanca."""
    cambios = {k: v for k, v in campos.items() if k in _CAMPOS_EDITABLES_WEBHOOK}
    if "eventos" in cambios and isinstance(cambios["eventos"], list):
        cambios["eventos"] = json.dumps(cambios["eventos"])
    if "activo" in cambios:
        cambios["activo"] = 1 if cambios["activo"] else 0
    if not cambios:
        return obtener_webhook(webhook_id)
    ahora = ahora_iso()
    asignaciones = [f"{k} = ?" for k in cambios]
    asignaciones.append("actualizado = ?")
    params: list[Any] = [*cambios.values(), ahora, webhook_id]
    con = _conectar()
    try:
        cur = con.execute(
            f"UPDATE webhooks SET {', '.join(asignaciones)} WHERE id = ?",  # noqa: S608 -- allowlist
            tuple(params),
        )
        con.commit()
        if cur.rowcount == 0:
            return None
        fila = con.execute(
            f"{_SELECT_WEBHOOK} WHERE id = ?", (webhook_id,)
        ).fetchone()
    finally:
        con.close()
    return _fila_a_webhook(fila) if fila is not None else None


def borrar_webhook(webhook_id: str) -> bool:
    con = _conectar()
    try:
        cur = con.execute("DELETE FROM webhooks WHERE id = ?", (webhook_id,))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def registrar_evento_interno(
    *,
    tipo: str,
    publicacion_id: str = "",
    pieza_id: str = "",
    clave_idempotencia: str = "",
    payload: dict[str, Any] | None = None,
) -> bool:
    """Registra un evento interno en la bitacora. False si su `clave_idempotencia` ya existia.

    La clave de idempotencia (UNIQUE) evita re-emitir el mismo vencimiento en cada barrido:
    si el INSERT choca con la constraint, devolvemos False sin tocar nada. Una clave vacia
    NO desduplica (cada llamada inserta): usala para eventos de transicion (siempre unicos).
    """
    ahora = ahora_iso()
    fila = {
        "id": uuid.uuid4().hex[:12],
        "tipo": tipo,
        "publicacion_id": publicacion_id or "",
        "pieza_id": pieza_id or "",
        # Sin clave explicita, una unica por id: nunca desduplica (cada emision se registra).
        "clave_idempotencia": clave_idempotencia or uuid.uuid4().hex,
        "payload": json.dumps(payload or {}, ensure_ascii=False),
        "creado": ahora,
    }
    con = _conectar()
    try:
        con.execute(
            "INSERT INTO eventos_internos "
            "(id, tipo, publicacion_id, pieza_id, clave_idempotencia, payload, creado) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                fila["id"], fila["tipo"], fila["publicacion_id"], fila["pieza_id"],
                fila["clave_idempotencia"], fila["payload"], fila["creado"],
            ),
        )
        con.commit()
        return True
    except IntegrityError:
        # UNIQUE (clave_idempotencia): el evento ya se emitio antes, no se repite.
        # `_ConexionPg` ya hizo rollback (paridad con el resto de call sites).
        return False
    finally:
        con.close()


def listar_eventos_internos(*, limite: int = 50) -> list[dict[str, Any]]:
    """Ultimos eventos internos emitidos (bitacora), mas recientes primero."""
    limite = max(1, min(int(limite), 500))
    con = _conectar()
    try:
        filas = con.execute(
            "SELECT id, tipo, publicacion_id, pieza_id, clave_idempotencia, payload, creado "
            "FROM eventos_internos ORDER BY creado DESC, id DESC LIMIT ?",
            (limite,),
        ).fetchall()
    finally:
        con.close()
    salida: list[dict[str, Any]] = []
    for f in filas:
        try:
            payload = json.loads(f["payload"]) if f["payload"] else {}
        except (ValueError, TypeError):
            payload = {}
        salida.append(
            {
                "id": f["id"],
                "tipo": f["tipo"],
                "publicacion_id": f["publicacion_id"],
                "pieza_id": f["pieza_id"],
                "payload": payload,
                # `creado` es timestamptz (migracion 0033): se re-emite al canon ISO (lo que
                # `api/alertas` y `api/webhooks` consumen como string).
                "creado": iso_o_vacio(f["creado"]),
            }
        )
    return salida
