"""API de WEBHOOKS salientes + bitacora de eventos internos del tablero.

Un webhook es una suscripcion a eventos internos (pieza aprobada / publicada / contenido
vencido): cuando uno se dispara, la Consola hace POST JSON a la `url` del webhook, firmado
con HMAC-SHA256 (`X-Keni-Signature`) si tiene secreto. Esto cierra el lazo con el equipo:
un Incoming Webhook de Slack (`formato='slack'`) avisa al canal de redes en cuanto una
pieza queda aprobada o un contenido vence.

Endpoints (todos bajo `/api/webhooks`):
  - GET    /api/webhooks            -> suscripciones (SIN secretos) + catalogo + bitacora.
  - POST   /api/webhooks            -> alta de una suscripcion (admin).
  - PATCH  /api/webhooks/{id}       -> edita (url/eventos/formato/secreto/activo).
  - DELETE /api/webhooks/{id}       -> baja.
  - POST   /api/webhooks/{id}/probar -> envia un evento de PRUEBA a ese webhook.

SEGURIDAD:
  - GESTION solo admin (gestionar webhooks = abrir la red de salida): el editor ve, no toca.
  - El `secreto` NUNCA se devuelve (solo `tiene_secreto`); se escribe pero no se lee.
  - La `url` se valida: debe ser http(s). Validacion de SSRF basica (no se permiten
    esquemas raros); el destino real lo controla el admin (allowlist viva).
  - SQL parametrizado en `repos`/`db`.
"""

from __future__ import annotations

from urllib.parse import urlparse

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import repos
from .._http_json import leer_json
from ..dominio import eventos
from ..estados import ROL_ADMIN
from ..seguridad import autor_de_peticion

_MAX_NOMBRE = 120
_MAX_URL = 2000
_MAX_SECRETO = 200


def _rol_de_peticion(request: Request) -> str | None:
    usuario = getattr(request.state, "usuario", None)
    if isinstance(usuario, dict):
        return usuario.get("rol")
    return None


def _es_admin(request: Request) -> bool:
    """True si la peticion es de un admin o entro por token de mantenimiento (sin usuario)."""
    usuario = getattr(request.state, "usuario", None)
    if usuario is None:  # token de mantenimiento => plenos permisos
        return True
    return _rol_de_peticion(request) == ROL_ADMIN


def _url_valida(url: object) -> bool:
    """True si `url` es una http(s) bien formada (defensa anti-esquemas raros)."""
    if not isinstance(url, str) or not url.strip():
        return False
    try:
        p = urlparse(url.strip())
    except ValueError:
        return False
    return p.scheme in ("http", "https") and bool(p.netloc)


def _validar_eventos(valor: object) -> tuple[list[str] | None, str | None]:
    """Normaliza la lista de eventos. `[]`/ausente => escucha TODOS. Rechaza tipos desconocidos."""
    if valor in (None, ""):
        return [], None
    if not isinstance(valor, list):
        return None, "Los eventos deben ser una lista."
    limpios: list[str] = []
    for e in valor:
        if not isinstance(e, str) or e not in eventos.TIPOS_EVENTO:
            return None, f"Evento no válido: {e!r}."
        if e not in limpios:
            limpios.append(e)
    return limpios, None


async def listar(request: Request) -> Response:
    """GET /api/webhooks: suscripciones (sin secretos) + catalogo de eventos + bitacora."""
    return JSONResponse(
        {
            "webhooks": repos.listar_webhooks(),
            "catalogo": {
                "eventos": list(eventos.TIPOS_EVENTO),
                "formatos": list(eventos.FORMATOS_WEBHOOK),
            },
            "eventos_recientes": repos.listar_eventos_internos(limite=30),
        }
    )


async def crear(request: Request) -> Response:
    """POST /api/webhooks: da de alta una suscripcion (solo admin)."""
    if not _es_admin(request):
        return JSONResponse(
            {"error": "Solo un administrador puede gestionar webhooks."}, status_code=403
        )
    datos = await leer_json(request)

    if not _url_valida(datos.get("url")):
        return JSONResponse({"error": "La URL debe ser http(s) válida."}, status_code=400)

    lista_eventos, err = _validar_eventos(datos.get("eventos"))
    if err is not None:
        return JSONResponse({"error": err}, status_code=400)

    formato = datos.get("formato", "generico") or "generico"
    if formato not in eventos.FORMATOS_WEBHOOK:
        return JSONResponse({"error": "Formato no válido."}, status_code=400)

    def _texto(clave: str, maximo: int) -> str:
        v = datos.get(clave, "")
        return v.strip()[:maximo] if isinstance(v, str) else ""

    wh = repos.crear_webhook(
        nombre=_texto("nombre", _MAX_NOMBRE),
        url=datos["url"].strip()[:_MAX_URL],
        eventos=lista_eventos,
        formato=formato,
        secreto=_texto("secreto", _MAX_SECRETO),
        activo=bool(datos.get("activo", True)),
        autor=autor_de_peticion(request),
    )
    return JSONResponse({"webhook": wh})


async def actualizar(request: Request) -> Response:
    """PATCH /api/webhooks/{id}: edita una suscripcion (solo admin)."""
    if not _es_admin(request):
        return JSONResponse(
            {"error": "Solo un administrador puede gestionar webhooks."}, status_code=403
        )
    webhook_id = request.path_params["webhook_id"]
    datos = await leer_json(request)
    campos: dict[str, object] = {}

    if "url" in datos:
        if not _url_valida(datos.get("url")):
            return JSONResponse({"error": "La URL debe ser http(s) válida."}, status_code=400)
        campos["url"] = datos["url"].strip()[:_MAX_URL]
    if "eventos" in datos:
        lista_eventos, err = _validar_eventos(datos.get("eventos"))
        if err is not None:
            return JSONResponse({"error": err}, status_code=400)
        campos["eventos"] = lista_eventos
    if "formato" in datos:
        formato = datos.get("formato") or "generico"
        if formato not in eventos.FORMATOS_WEBHOOK:
            return JSONResponse({"error": "Formato no válido."}, status_code=400)
        campos["formato"] = formato
    if "nombre" in datos:
        v = datos.get("nombre")
        campos["nombre"] = v.strip()[:_MAX_NOMBRE] if isinstance(v, str) else ""
    if "secreto" in datos:  # "" borra el secreto (deja de firmar); un valor lo cambia
        v = datos.get("secreto")
        campos["secreto"] = v.strip()[:_MAX_SECRETO] if isinstance(v, str) else ""
    if "activo" in datos:
        campos["activo"] = bool(datos["activo"])

    if not campos:
        return JSONResponse({"error": "Indica algún campo a actualizar."}, status_code=400)

    wh = repos.actualizar_webhook(webhook_id, campos)
    if wh is None:
        return JSONResponse({"error": "Ese webhook ya no existe."}, status_code=404)
    return JSONResponse({"webhook": wh})


async def borrar(request: Request) -> Response:
    """DELETE /api/webhooks/{id}: baja una suscripcion (solo admin)."""
    if not _es_admin(request):
        return JSONResponse(
            {"error": "Solo un administrador puede gestionar webhooks."}, status_code=403
        )
    webhook_id = request.path_params["webhook_id"]
    if not repos.borrar_webhook(webhook_id):
        return JSONResponse({"error": "Ese webhook ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Webhook borrado."})


async def probar(request: Request) -> Response:
    """POST /api/webhooks/{id}/probar: envia un evento de PRUEBA a ese webhook (solo admin).

    Reparto SINCRONO (para devolver el resultado de la entrega) de un payload `pieza.aprobada`
    de ejemplo. NO toca el tablero ni la bitacora: es una prueba de conectividad/firma.
    """
    if not _es_admin(request):
        return JSONResponse(
            {"error": "Solo un administrador puede gestionar webhooks."}, status_code=403
        )
    webhook_id = request.path_params["webhook_id"]
    crudo = repos.obtener_webhook_con_secreto(webhook_id)
    if crudo is None:
        return JSONResponse({"error": "Ese webhook ya no existe."}, status_code=404)
    ok, estado = eventos.probar_webhook(crudo)
    return JSONResponse({"ok": ok, "estado": estado})


RUTAS = [
    Route("/api/webhooks", listar, methods=["GET"]),
    Route("/api/webhooks", crear, methods=["POST"]),
    Route("/api/webhooks/{webhook_id}", actualizar, methods=["PATCH"]),
    Route("/api/webhooks/{webhook_id}", borrar, methods=["DELETE"]),
    Route("/api/webhooks/{webhook_id}/probar", probar, methods=["POST"]),
]
