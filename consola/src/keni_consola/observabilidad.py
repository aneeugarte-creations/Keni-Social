"""Observabilidad de la Consola Keni: logging, middleware de peticiones y errores.

Issue #123: la app no tenia logging de peticiones, casi no tenia loggers, no habia
manejador central de excepciones y los errores salian como ~250 respuestas
`{"error": ...}` en linea. Esto centraliza el NUCLEO:

  - `configurar_logging()`: configura el logger raiz del paquete una sola vez. El
    nivel se lee de la env var `KENI_CONSOLA_LOG_LEVEL` (def: INFO). Lo cablea el
    arranque real (`__main__.py`); los tests usan `caplog` sin tocar la config global.

  - `RegistroPeticiones`: middleware ASGI que registra UNA linea por peticion con
    metodo, ruta, codigo de estado y duracion en ms. PRIVACIDAD: NUNCA registra el
    body, la query string, las cabeceras ni nada que pueda contener tokens o
    credenciales. Solo metodo + ruta (sin query) + estado + duracion.

  - `manejar_excepcion`: manejador central de `Exception`. Registra el traceback en
    el SERVIDOR y devuelve una respuesta JSON consistente
    `{"error": "...", "request_id": "..."}` con status 500, SIN filtrar detalles
    internos (ni el nombre de la clase) ni el stack al cliente. Es ADITIVO: los endpoints que ya devuelven su propio
    `{"error": ...}` siguen igual; esto solo atrapa lo que hoy cae a un 500 por defecto.

  - `error(mensaje, status)`: helper que devuelve la respuesta de error ESTANDAR del
    proyecto (`{"error": <mensaje en espanol>}` + status, mas el `request_id` de
    correlacion si lo hay). Es el destino al que las ~250 respuestas `{"error": ...}`
    en linea migran de forma INCREMENTAL.

ID DE CORRELACION (#123): cada peticion recibe un `request_id` corto (lo genera el
middleware si el cliente/proxy no manda `X-Request-ID`). Ese id:
  - se incluye en la linea de log de la peticion (`[<rid>] METODO ruta -> estado (ms)`);
  - se guarda en `request.state.request_id` Y en un `ContextVar` (`request_id_actual()`),
    para que CUALQUIER handler o hilo de trabajo (p.ej. una generacion, #137) lo pueda
    leer y CORRELACIONAR sus logs sin pasarlo a mano por toda la pila;
  - viaja al cliente en la cabecera `X-Request-ID` de la respuesta y en el cuerpo JSON de
    error (`{"error", "request_id"}`), asi un usuario que reporta un fallo da un id que
    casa 1:1 con la traza del servidor.
"""

from __future__ import annotations

import contextvars
import logging
import time
import uuid

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from . import config

# Nombre del logger raiz del paquete. Todo el logging de la consola cuelga de aqui,
# asi un unico `configurar_logging()` fija nivel y handler para todo el paquete.
NOMBRE_LOGGER = "keni_consola"

# Env var que controla el nivel de log. Acepta nombres estandar (DEBUG, INFO,
# WARNING, ERROR, CRITICAL); cualquier otro valor cae a INFO. Nombre canonico en `config`
# (fuente unica); re-exportado aqui porque los tests referencian `observabilidad.ENV_NIVEL`.
ENV_NIVEL = config.ENV_LOG_LEVEL

# Cabecera estandar del id de correlacion (entrada desde un proxy, salida al cliente).
CABECERA_REQUEST_ID = "X-Request-ID"

_logger = logging.getLogger(NOMBRE_LOGGER)
_log_peticiones = logging.getLogger(f"{NOMBRE_LOGGER}.peticiones")

# ContextVar del id de correlacion de la peticion EN CURSO. El middleware lo fija al
# entrar; cualquier handler (o un hilo que herede el contexto, p.ej. via
# `contextvars.copy_context`) lo lee con `request_id_actual()` para CORRELACIONAR sus
# logs sin tener que pasar el id a mano por toda la pila. Default "" (fuera de peticion).
_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("keni_request_id", default="")


def nuevo_request_id() -> str:
    """Genera un id de correlacion corto (12 hex) para una peticion."""
    return uuid.uuid4().hex[:12]


def request_id_actual() -> str:
    """Id de correlacion de la peticion en curso (o "" fuera de una peticion)."""
    return _request_id.get()


def fijar_request_id(rid: str) -> contextvars.Token:
    """Fija el id de correlacion en el contexto; devuelve el token para restaurarlo."""
    return _request_id.set(rid)


def restaurar_request_id(token: contextvars.Token) -> None:
    """Restaura el id de correlacion previo (reset del ContextVar)."""
    _request_id.reset(token)


def _nivel_desde_env() -> int:
    """Devuelve el nivel de logging segun `KENI_CONSOLA_LOG_LEVEL` (def: INFO)."""
    nivel = logging.getLevelName(config.log_level())
    # getLevelName devuelve un int para nombres validos y un str ("Level X") si no.
    return nivel if isinstance(nivel, int) else logging.INFO


def configurar_logging() -> logging.Logger:
    """Configura (una sola vez) el logger del paquete y devuelve el logger raiz.

    Idempotente: si ya tiene handlers, solo reajusta el nivel. Pensado para el
    arranque real (`__main__.py`). Los tests NO necesitan llamarlo: usan `caplog`,
    que captura por su cuenta y no depende de los handlers configurados aqui.
    """
    nivel = _nivel_desde_env()
    _logger.setLevel(nivel)
    if not _logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        _logger.addHandler(handler)
        # No propagamos al root para no duplicar lineas si alguien configura el root.
        _logger.propagate = False
    return _logger


# --------------------------------------------------------------------------- #
# Middleware de registro de peticiones                                         #
# --------------------------------------------------------------------------- #


def _request_id_entrante(scope: Scope) -> str:
    """Reusa el `X-Request-ID` que mande un proxy/cliente; si no, genera uno nuevo.

    Reusar el id entrante encadena la traza con la del proxy (Traefik) cuando este lo
    propaga. Se REPARA (solo hex/guion, <= 64 chars) para que un valor ajeno no inyecte
    nada raro en los logs; si no es valido, se genera uno limpio.
    """
    for nombre, valor in scope.get("headers", []):
        if nombre == b"x-request-id":
            crudo = valor.decode("latin-1", "replace").strip()
            reparado = "".join(c for c in crudo if c.isalnum() or c in "-_")[:64]
            if reparado:
                return reparado
            break
    return nuevo_request_id()


class RegistroPeticiones:
    """Middleware ASGI: una linea de log por peticion (rid, metodo, ruta, estado, ms).

    Genera (o reusa de `X-Request-ID`) un id de CORRELACION por peticion, lo deja en
    `scope["state"]["request_id"]` (lo lee `request.state.request_id`) y en el ContextVar
    `request_id_actual()`, y lo devuelve al cliente en la cabecera `X-Request-ID`. Asi un
    fallo se puede rastrear de punta a punta con un solo id.

    PRIVACIDAD (critico): solo registra `request_id`, `method`, `path` (SIN query string),
    `status_code` y `duration_ms`. Nunca el body, las cabeceras (salvo el propio request
    id, que no es secreto), la query ni nada que pueda contener tokens/credenciales. Solo
    actua sobre `scope["type"] == "http"`; el resto (lifespan, websocket) pasa intacto.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        rid = _request_id_entrante(scope)
        # Disponible para los handlers via `request.state.request_id`. Starlette expone
        # `request.state` desde `scope["state"]`; lo inicializamos por si no existe aun.
        estado_scope = scope.setdefault("state", {})
        if isinstance(estado_scope, dict):
            estado_scope["request_id"] = rid
        token = fijar_request_id(rid)

        metodo = scope.get("method", "?")
        # `path` NO incluye la query string (esa va en scope["query_string"], que a
        # proposito NO tocamos: podria llevar secretos).
        ruta = scope.get("path", "?")
        inicio = time.perf_counter()
        estado: int = 0
        ttfb_ms: float = 0.0  # latencia al PRIMER BYTE (http.response.start)

        async def send_envuelto(message: Message) -> None:
            nonlocal estado, ttfb_ms
            if message["type"] == "http.response.start":
                estado = message["status"]
                ttfb_ms = (time.perf_counter() - inicio) * 1000.0
                # Devolvemos el id de correlacion al cliente (cabecera): un usuario que
                # reporta un fallo da este id y casa 1:1 con la traza del servidor.
                cabeceras = message.setdefault("headers", [])
                cabeceras.append((b"x-request-id", rid.encode("latin-1")))
            await send(message)

        try:
            await self.app(scope, receive, send_envuelto)
        finally:
            dur_ms = (time.perf_counter() - inicio) * 1000.0
            _log_peticiones.info(
                "[%s] %s %s -> %s (%.1f ms)", rid, metodo, ruta, estado or "?", dur_ms
            )
            # Agregador de latencias por ruta del panel Sistema (best-effort, jamas
            # lanza). Usa el TTFB, no la duracion total: una SSE abierta horas no debe
            # contaminar los percentiles. Si no hubo response.start (cliente corto la
            # conexion antes de la respuesta), cae a la duracion total.
            from . import rendimiento

            rendimiento.registrar(metodo, ruta, estado, ttfb_ms or dur_ms)
            restaurar_request_id(token)


# --------------------------------------------------------------------------- #
# Manejador central de excepciones                                             #
# --------------------------------------------------------------------------- #

# Mensaje generico al cliente: jamas exponemos el detalle interno ni el stack.
_MENSAJE_500 = "Ocurrio un error inesperado en el servidor."


async def manejar_excepcion(request: Request, exc: Exception) -> Response:
    """Manejador central de `Exception`: loguea el traceback y responde JSON 500.

    Registra el error CON traceback Y el id de correlacion en el servidor (para auditar
    en beta) y devuelve una respuesta consistente `{"error", "request_id"}` con status
    500, SIN filtrar el mensaje real ni el stack al cliente. El NOMBRE de la clase de
    excepcion queda SOLO en el log del servidor (via `exc_info`): exponerlo en el cuerpo
    filtra detalle interno. `request_id` permite al usuario reportar el fallo y casarlo
    con la traza del servidor.
    """
    rid = getattr(request.state, "request_id", "") or request_id_actual()
    _logger.error(
        "[%s] Excepcion no controlada en %s %s",
        rid or "-",
        request.method,
        request.url.path,  # sin query string: puede llevar secretos
        exc_info=exc,
    )
    cuerpo: dict[str, str] = {"error": _MENSAJE_500}
    # Cabecera explicita aqui: el 500 lo emite `ServerErrorMiddleware` (el mas externo,
    # POR ENCIMA del middleware de peticiones), asi que la inyeccion de cabecera de
    # `RegistroPeticiones` NO lo alcanza. La ponemos directamente para que el id viaje
    # tambien en la cabecera, no solo en el cuerpo.
    cabeceras = {CABECERA_REQUEST_ID: rid} if rid else None
    if rid:
        cuerpo["request_id"] = rid
    return JSONResponse(cuerpo, status_code=500, headers=cabeceras)


# --------------------------------------------------------------------------- #
# Helper de respuesta de error estandar                                        #
# --------------------------------------------------------------------------- #


def error(mensaje: str, status: int = 400) -> JSONResponse:
    """Respuesta de error ESTANDAR de la consola: `{"error": <mensaje>}` + status.

    Mantiene la clave `error` (mensaje en espanol) EXACTAMENTE como las ~250 respuestas
    `{"error": ...}` en linea que ya existen en `api/*.py`, para que migrar a este helper
    sea un swap 1:1 sin romper el contrato del API. ADEMAS, si hay un id de correlacion en
    el contexto de la peticion (#123), lo AÑADE como `request_id` (clave extra, aditiva):
    un cliente que solo lee `error`/`status` no nota el cambio, pero el id queda disponible
    para correlacionar el fallo con la traza del servidor. Si no hay id (fuera de peticion,
    p.ej. en tests del helper aislado), devuelve solo `{"error": ...}`.

    La migracion de los sitios `{"error": ...}` en linea al helper es INCREMENTAL.
    """
    cuerpo: dict[str, str] = {"error": mensaje}
    rid = request_id_actual()
    if rid:
        cuerpo["request_id"] = rid
    return JSONResponse(cuerpo, status_code=status)
