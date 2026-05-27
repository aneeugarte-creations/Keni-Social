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
    `{"error": "...", "tipo": "..."}` con status 500, SIN filtrar detalles internos
    ni el stack al cliente. Es ADITIVO: los endpoints que ya devuelven su propio
    `{"error": ...}` siguen igual; esto solo atrapa lo que hoy cae a un 500 por defecto.

  - `error(mensaje, status)`: helper que devuelve la respuesta de error ESTANDAR del
    proyecto (`{"error": <mensaje en espanol>}` + status). Es el destino al que las
    ~250 respuestas `{"error": ...}` en linea migraran de forma INCREMENTAL (no en
    este cambio; ver nota en `error`).
"""

from __future__ import annotations

import logging
import os
import time

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Nombre del logger raiz del paquete. Todo el logging de la consola cuelga de aqui,
# asi un unico `configurar_logging()` fija nivel y handler para todo el paquete.
NOMBRE_LOGGER = "keni_consola"

# Env var que controla el nivel de log. Acepta nombres estandar (DEBUG, INFO,
# WARNING, ERROR, CRITICAL); cualquier otro valor cae a INFO.
ENV_NIVEL = "KENI_CONSOLA_LOG_LEVEL"

_logger = logging.getLogger(NOMBRE_LOGGER)
_log_peticiones = logging.getLogger(f"{NOMBRE_LOGGER}.peticiones")


def _nivel_desde_env() -> int:
    """Devuelve el nivel de logging segun `KENI_CONSOLA_LOG_LEVEL` (def: INFO)."""
    crudo = os.environ.get(ENV_NIVEL, "INFO").strip().upper()
    nivel = logging.getLevelName(crudo)
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


class RegistroPeticiones:
    """Middleware ASGI: una linea de log por peticion (metodo, ruta, estado, ms).

    PRIVACIDAD (critico): solo registra `method`, `path` (SIN query string),
    `status_code` y `duration_ms`. Nunca el body, las cabeceras, la query ni nada
    que pueda contener tokens/credenciales. Solo actua sobre `scope["type"] ==
    "http"`; el resto (lifespan, websocket) pasa intacto.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        metodo = scope.get("method", "?")
        # `path` NO incluye la query string (esa va en scope["query_string"], que a
        # proposito NO tocamos: podria llevar secretos).
        ruta = scope.get("path", "?")
        inicio = time.perf_counter()
        estado: int = 0

        async def send_envuelto(message: Message) -> None:
            nonlocal estado
            if message["type"] == "http.response.start":
                estado = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_envuelto)
        finally:
            dur_ms = (time.perf_counter() - inicio) * 1000.0
            _log_peticiones.info(
                "%s %s -> %s (%.1f ms)", metodo, ruta, estado or "?", dur_ms
            )


# --------------------------------------------------------------------------- #
# Manejador central de excepciones                                             #
# --------------------------------------------------------------------------- #

# Mensaje generico al cliente: jamas exponemos el detalle interno ni el stack.
_MENSAJE_500 = "Ocurrio un error inesperado en el servidor."


async def manejar_excepcion(request: Request, exc: Exception) -> Response:
    """Manejador central de `Exception`: loguea el traceback y responde JSON 500.

    Registra el error CON traceback en el servidor (para auditar en beta) y devuelve
    una respuesta consistente `{"error": ..., "tipo": ...}` con status 500, SIN
    filtrar el mensaje real ni el stack al cliente. `tipo` es solo el NOMBRE de la
    clase de excepcion (p.ej. "ValueError"), util para depurar sin revelar detalles.
    """
    _logger.error(
        "Excepcion no controlada en %s %s",
        request.method,
        request.url.path,  # sin query string: puede llevar secretos
        exc_info=exc,
    )
    return JSONResponse(
        {"error": _MENSAJE_500, "tipo": type(exc).__name__},
        status_code=500,
    )


# --------------------------------------------------------------------------- #
# Helper de respuesta de error estandar                                        #
# --------------------------------------------------------------------------- #


def error(mensaje: str, status: int = 400) -> JSONResponse:
    """Respuesta de error ESTANDAR de la consola: `{"error": <mensaje>}` + status.

    Reproduce EXACTAMENTE la forma de las ~250 respuestas `{"error": ...}` en linea
    que ya existen en `api/*.py`, para que la migracion a este helper sea un swap
    1:1 sin cambiar el contrato del API. La migracion de esos sitios es INCREMENTAL
    y NO forma parte de este cambio (issue #123): el helper se introduce ahora y los
    sitios se iran cambiando despues, area por area.
    """
    return JSONResponse({"error": mensaje}, status_code=status)
