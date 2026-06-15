"""Cliente HTTP síncrono contra la API de **Postproxy** (canal de publicación alternativo).

Postproxy (https://api.postproxy.dev/api/) es un canal de publicación alternativo a
Metricool. Este módulo agrupa las llamadas de GESTIÓN de la conexión (grupos de
perfiles, perfiles, conexión OAuth de una red, desconexión); la PUBLICACIÓN de un post
vive aparte en `publicacion.postproxy`.

Contrato (header `Authorization: Bearer <api_key>` en TODAS):
    GET    /api/profile_groups                         -> [{id, name, profiles_count}]
    POST   /api/profile_groups                         -> {id, name, profiles_count}
    GET    /api/profiles?profile_group_id=<id>         -> [{id, name, platform, status, ...}]
    POST   /api/profile_groups/:id/initialize_connection -> {url, success}
    DELETE /api/profiles/:id                           -> desconecta un perfil

REGLAS DE ESTILO (espejo de `api/conexiones._listar_perfiles`):
  - Funciones PURAS con un PUNTO INYECTABLE por operación (los tests parchean el
    `_HACER_*` para NUNCA tocar la red).
  - Devuelven `(ok: bool, mensaje: str, datos)` — NUNCA lanzan por un fallo de red/HTTP
    (se traduce a `ok=False` + mensaje en español). Una entrada inválida (api_key vacía)
    sí se valida arriba.
  - El parseo es DEFENSIVO (varios alias por campo), porque la forma exacta no está
    fijada por un swagger versionado.
  - El `api_key` NUNCA se registra ni aparece en ningún mensaje de salida.
"""

from __future__ import annotations

import httpx

from ._http import log

BASE = "https://api.postproxy.dev/api"
TIMEOUT = 30.0

# Plataformas válidas del catálogo Postproxy (las que admite `initialize_connection`).
PLATAFORMAS: tuple[str, ...] = (
    "facebook",
    "instagram",
    "tiktok",
    "linkedin",
    "youtube",
    "twitter",
    "threads",
    "pinterest",
    "bluesky",
    "telegram",
    "google_business",
)


def _headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


# --------------------------------------------------------------------------- #
# Punto INYECTABLE único: la ÚNICA función que toca la red. Los tests la parchean
# (`_HACER_PETICION`) para NUNCA abrir un socket. Devuelve (status_code, json|None).
# --------------------------------------------------------------------------- #
def _peticion(
    metodo: str,
    ruta: str,
    api_key: str,
    *,
    params: dict | None = None,
    json: dict | None = None,
) -> tuple[int, object]:
    """Hace UNA petición HTTP a Postproxy y devuelve `(status_code, cuerpo_json|None)`.

    Único seam de red del módulo. NO lanza por status: el llamante decide. Solo propaga
    `httpx.HTTPError` (caída de red), que cada operación traduce a `(False, mensaje, ...)`.
    El `api_key` viaja SOLO en la cabecera; nunca se loguea.
    """
    url = f"{BASE}{ruta}"
    with httpx.Client(timeout=TIMEOUT) as cli:
        r = cli.request(metodo, url, headers=_headers(api_key), params=params, json=json)
    log.debug("%s %s -> %s", metodo, ruta, r.status_code)
    cuerpo: object = None
    try:
        cuerpo = r.json()
    except ValueError:
        cuerpo = None
    return r.status_code, cuerpo


# El seam que parchean los tests. Reasignable a nivel de módulo.
_HACER_PETICION = _peticion


def _verificar_api_key(api_key: str) -> tuple[bool, str]:
    """Valida que la api_key no esté vacía (sin tocar la red). (ok, mensaje)."""
    if not isinstance(api_key, str) or not api_key.strip():
        return False, "Falta la API key de Postproxy."
    return True, ""


# --------------------------------------------------------------------------- #
# Parseo defensivo                                                             #
# --------------------------------------------------------------------------- #
def _str(valor: object) -> str | None:
    if valor in (None, ""):
        return None
    return str(valor)


def _int(valor: object) -> int | None:
    try:
        return int(valor)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _lista(cuerpo: object) -> list:
    """Normaliza el cuerpo a una lista (acepta lista directa o dict con la lista anidada)."""
    if isinstance(cuerpo, list):
        return cuerpo
    if isinstance(cuerpo, dict):
        for clave in ("data", "results", "profile_groups", "profiles", "items"):
            valor = cuerpo.get(clave)
            if isinstance(valor, list):
                return valor
    return []


def _parsear_grupo(g: object) -> dict | None:
    """Parsea DEFENSIVAMENTE un profile_group a `{id, name, profiles_count}`."""
    if not isinstance(g, dict):
        return None
    gid = None
    for clave in ("id", "profile_group_id", "_id"):
        gid = _str(g.get(clave))
        if gid:
            break
    if gid is None:
        return None
    nombre = None
    for clave in ("name", "nombre", "title"):
        v = g.get(clave)
        if isinstance(v, str) and v.strip():
            nombre = v.strip()
            break
    return {
        "id": gid,
        "name": nombre or gid,
        "profiles_count": _int(g.get("profiles_count")) or 0,
    }


def _parsear_perfil(p: object) -> dict | None:
    """Parsea DEFENSIVAMENTE un perfil a la forma del contrato.

    `{id, name, platform, status, profile_group_id, post_count, avatar_url, expires_at}`.
    Descarta los que no tengan id; cada campo cae a None si falta.
    """
    if not isinstance(p, dict):
        return None
    pid = None
    for clave in ("id", "profile_id", "_id"):
        pid = _str(p.get(clave))
        if pid:
            break
    if pid is None:
        return None
    plataforma = None
    for clave in ("platform", "plataforma", "network"):
        v = p.get(clave)
        if isinstance(v, str) and v.strip():
            plataforma = v.strip()
            break
    nombre = None
    for clave in ("name", "nombre", "username", "handle"):
        v = p.get(clave)
        if isinstance(v, str) and v.strip():
            nombre = v.strip()
            break
    estado = None
    v = p.get("status") or p.get("estado")
    if isinstance(v, str) and v.strip():
        estado = v.strip()
    return {
        "id": pid,
        "name": nombre,
        "platform": plataforma,
        "status": estado,
        "profile_group_id": _str(p.get("profile_group_id") or p.get("profileGroupId")),
        "post_count": _int(p.get("post_count") or p.get("postCount")),
        "avatar_url": _str(p.get("avatar_url") or p.get("avatarUrl")),
        "expires_at": _str(p.get("expires_at") or p.get("expiresAt")),
    }


# --------------------------------------------------------------------------- #
# Operaciones                                                                  #
# --------------------------------------------------------------------------- #
def _traducir_error(codigo: int, accion: str) -> str:
    """Mensaje en español según el status code (sin filtrar detalles del cuerpo)."""
    if codigo in (401, 403):
        return "Postproxy rechazó la API key."
    if codigo == 404:
        return f"Postproxy no encontró el recurso al {accion}."
    if codigo == 422:
        return f"Postproxy rechazó los datos al {accion}."
    return f"Postproxy devolvió un error ({codigo}) al {accion}."


def listar_grupos(api_key: str) -> tuple[bool, str, list[dict]]:
    """GET /profile_groups -> `(ok, mensaje, [{id, name, profiles_count}])`."""
    ok, msg = _verificar_api_key(api_key)
    if not ok:
        return False, msg, []
    try:
        codigo, cuerpo = _HACER_PETICION("GET", "/profile_groups", api_key)
    except httpx.HTTPError:
        return False, "No se pudo contactar con Postproxy.", []
    if codigo != 200:
        return False, _traducir_error(codigo, "listar los grupos"), []
    grupos = [g for g in (_parsear_grupo(x) for x in _lista(cuerpo)) if g]
    return True, "Grupos encontrados.", grupos


def crear_grupo(api_key: str, nombre: str) -> tuple[bool, str, dict | None]:
    """POST /profile_groups -> `(ok, mensaje, {id, name, profiles_count})`.

    Requiere una API key de cuenta completa (Postproxy puede devolver 403 si no lo es).
    """
    ok, msg = _verificar_api_key(api_key)
    if not ok:
        return False, msg, None
    if not isinstance(nombre, str) or not nombre.strip():
        return False, "Falta el nombre del grupo de perfiles.", None
    cuerpo_req = {"profile_group": {"name": nombre.strip()}}
    try:
        codigo, cuerpo = _HACER_PETICION("POST", "/profile_groups", api_key, json=cuerpo_req)
    except httpx.HTTPError:
        return False, "No se pudo contactar con Postproxy.", None
    if codigo not in (200, 201):
        return False, _traducir_error(codigo, "crear el grupo"), None
    grupo = _parsear_grupo(cuerpo)
    if grupo is None:
        return False, "Postproxy no devolvió un grupo válido.", None
    return True, "Grupo creado.", grupo


def listar_perfiles(api_key: str, profile_group_id: str) -> tuple[bool, str, list[dict]]:
    """GET /profiles?profile_group_id=<id> -> `(ok, mensaje, [perfil, ...])`."""
    ok, msg = _verificar_api_key(api_key)
    if not ok:
        return False, msg, []
    if not isinstance(profile_group_id, str) or not profile_group_id.strip():
        return False, "Falta el grupo de perfiles.", []
    try:
        codigo, cuerpo = _HACER_PETICION(
            "GET", "/profiles", api_key, params={"profile_group_id": profile_group_id.strip()}
        )
    except httpx.HTTPError:
        return False, "No se pudo contactar con Postproxy.", []
    if codigo != 200:
        return False, _traducir_error(codigo, "listar los perfiles"), []
    perfiles = [p for p in (_parsear_perfil(x) for x in _lista(cuerpo)) if p]
    return True, "Perfiles encontrados.", perfiles


def initialize_connection(
    api_key: str, group_id: str, platform: str, redirect_url: str
) -> tuple[bool, str, str | None]:
    """POST /profile_groups/:id/initialize_connection -> `(ok, mensaje, url_oauth)`.

    Devuelve la URL de la pantalla OAuth que el usuario debe abrir para conectar la red.
    """
    ok, msg = _verificar_api_key(api_key)
    if not ok:
        return False, msg, None
    if not isinstance(group_id, str) or not group_id.strip():
        return False, "Falta el grupo de perfiles.", None
    if platform not in PLATAFORMAS:
        validas = ", ".join(PLATAFORMAS)
        return False, f"Plataforma no válida. Válidas: {validas}.", None
    if not isinstance(redirect_url, str) or not redirect_url.strip():
        return False, "Falta la URL de redirección.", None
    ruta = f"/profile_groups/{group_id.strip()}/initialize_connection"
    cuerpo_req = {"platform": platform, "redirect_url": redirect_url.strip()}
    try:
        codigo, cuerpo = _HACER_PETICION("POST", ruta, api_key, json=cuerpo_req)
    except httpx.HTTPError:
        return False, "No se pudo contactar con Postproxy.", None
    if codigo not in (200, 201):
        return False, _traducir_error(codigo, "iniciar la conexión"), None
    url = None
    if isinstance(cuerpo, dict):
        url = _str(cuerpo.get("url") or cuerpo.get("redirect_url"))
    if not url:
        return False, "Postproxy no devolvió la URL de conexión.", None
    return True, "Conexión iniciada.", url


def desconectar_perfil(api_key: str, perfil_id: str) -> tuple[bool, str]:
    """DELETE /profiles/:id -> `(ok, mensaje)`. Desconecta un perfil."""
    ok, msg = _verificar_api_key(api_key)
    if not ok:
        return False, msg
    if not isinstance(perfil_id, str) or not perfil_id.strip():
        return False, "Falta el identificador del perfil."
    ruta = f"/profiles/{perfil_id.strip()}"
    try:
        codigo, _ = _HACER_PETICION("DELETE", ruta, api_key)
    except httpx.HTTPError:
        return False, "No se pudo contactar con Postproxy."
    if codigo not in (200, 202, 204):
        return False, _traducir_error(codigo, "desconectar el perfil")
    return True, "Perfil desconectado."


def probar(api_key: str) -> tuple[bool, str]:
    """Valida la api_key con una llamada BARATA de lectura (GET /profile_groups).

    `(ok, mensaje)`. No crea ni modifica nada. La api_key nunca aparece en el mensaje.
    """
    ok, msg, _ = listar_grupos(api_key)
    if ok:
        return True, "La API key de Postproxy funciona."
    return False, msg
