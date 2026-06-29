"""API Ajustes: flags de automatización y tuning editables EN CALIENTE por un admin (#).

Expone el catálogo declarativo (`keni_consola.ajustes_catalogo`) y persiste los cambios en
el store editable (`keni_consola.ajustes`), que `config._crudo` consulta ANTES que el
entorno (precedencia STORE > ENV > DEFECTO). Así un admin enciende/apaga la automatización o
afina los parámetros desde la UI sin redeploy ni tocar env vars; las claves no editadas
siguen cayendo a env/defecto exactamente como hoy.

Endpoints (bajo `/api/ajustes`, CONTRATO con el frontend):

  - GET  /api/ajustes   -> {"grupos": [{"id", "titulo", "ajustes": [AJUSTE, ...]}, ...]}
                           AJUSTE = {clave, tipo, etiqueta, ayuda, grupo, peligroso,
                                     valor (tipado), fuente ('store'|'env'|'defecto'),
                                     defecto (tipado), opciones? (select), min?/max? (int/float)}
  - POST /api/ajustes   body {"clave", "valor"} (escribe) o {"clave", "reset": true} (borra
                           del store -> cae a env/defecto). -> {"ajuste": AJUSTE_actualizado}.
                           400 si la clave no es del catálogo o el valor es inválido.

Autorización: SOLO rol admin (mismo gating que `api/usuarios.py`, vía `keni_consola.permisos`).
El token de mantenimiento NO cuenta como admin: por sí solo recibe 403.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import ajustes, ajustes_catalogo, permisos
from .._http_json import leer_json

_MSG_SOLO_ADMIN = "Solo un administrador puede cambiar los ajustes."


def _es_admin(request: Request) -> bool:
    """True solo si la petición la hace una sesión de un usuario real con rol admin.

    Delega en el helper único (`keni_consola.permisos.es_admin`), igual que `api/usuarios`.
    """
    return permisos.es_admin(request)


def _rechazo_no_admin() -> Response:
    return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)


def _grupos() -> list[dict]:
    """Catálogo serializado, agrupado y en el orden estable del contrato."""
    catalogo = ajustes_catalogo.catalogo()
    grupos = []
    for gid, titulo in ajustes_catalogo.GRUPOS:
        items = [
            ajustes_catalogo.a_dict(a) for a in catalogo if a.grupo == gid
        ]
        grupos.append({"id": gid, "titulo": titulo, "ajustes": items})
    return grupos


async def listar(request: Request) -> Response:
    """GET /api/ajustes: catálogo agrupado con valor efectivo + fuente de cada ajuste."""
    if not _es_admin(request):
        return _rechazo_no_admin()
    return JSONResponse({"grupos": _grupos()})


async def guardar(request: Request) -> Response:
    """POST /api/ajustes: escribe `{clave, valor}` o resetea `{clave, reset: true}`.

    Solo claves del catálogo. Valida tipo/min/max/select. `reset` borra la clave del store
    (vuelve a env/defecto). Devuelve el ajuste actualizado (con su nuevo valor + fuente).
    """
    if not _es_admin(request):
        return _rechazo_no_admin()
    datos = await leer_json(request)

    clave = datos.get("clave")
    if not isinstance(clave, str) or not clave.strip():
        return JSONResponse({"error": "Indica la clave del ajuste."}, status_code=400)
    clave = clave.strip()
    ajuste = ajustes_catalogo.por_clave(clave)
    if ajuste is None:
        return JSONResponse(
            {"error": f"Ajuste desconocido: {clave!r}."}, status_code=400
        )

    if datos.get("reset") is True:
        try:
            ajustes.borrar(clave)
        except OSError as e:
            return JSONResponse(
                {"error": f"No se pudo restablecer el ajuste: {e}"}, status_code=400
            )
        return JSONResponse({"ajuste": ajustes_catalogo.a_dict(ajuste)})

    if "valor" not in datos:
        return JSONResponse(
            {"error": "Indica el 'valor' a guardar o usa 'reset' para restablecer."},
            status_code=400,
        )
    a_guardar, error = ajustes_catalogo.validar_valor(ajuste, datos.get("valor"))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)
    try:
        ajustes.guardar(clave, a_guardar)
    except OSError as e:
        return JSONResponse(
            {"error": f"No se pudo guardar el ajuste: {e}"}, status_code=400
        )
    return JSONResponse({"ajuste": ajustes_catalogo.a_dict(ajuste)})


RUTAS = [
    Route("/api/ajustes", listar, methods=["GET"]),
    Route("/api/ajustes", guardar, methods=["POST"]),
]
