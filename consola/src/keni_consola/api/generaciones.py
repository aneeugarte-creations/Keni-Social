"""API Generaciones: sondeo de los trabajos de IA en segundo plano.

Toda generacion (copy, RSS->copy, imagen) se lanza desde su endpoint de
siempre (`/api/prompts/lanzar`, `/api/rss/generar`, `/api/media/generar`), que ahora
responde de INMEDIATO con un registro de generacion
`{estado: "ejecutando"}` en vez de bloquear. El frontend SONDEA aqui hasta el estado
terminal:

  - `GET /api/generaciones`         -> listado reciente (para una vista de actividad).
  - `GET /api/generaciones/{id}`    -> una generacion (estado + salida en vivo + metricas
                                       + `resultado` cuando completa). 404 si no existe.
  - `GET /api/generaciones/{id}/stream` -> la MISMA generacion como SSE (text/event-stream):
                                       empuja eventos `estado` cuando hay avance y un evento
                                       final `terminal` al acabar. El SPA lo prefiere al
                                       sondeo (menos peticiones, menos latencia percibida) y
                                       DEGRADA al sondeo de 1.2 s si SSE no esta disponible.
  - `POST /api/generaciones/{id}/cancelar` -> cancela un job en curso: mata el
                                       ARBOL del subproceso `claude` y deja el registro
                                       en estado terminal. 404 si no existe.

La logica vive en el dominio `consola.generaciones`; aqui solo se serializa a JSON.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from .. import generaciones
from .._http_json import envoltura_paginacion, paginacion_query
from ..observabilidad import error


async def listar(request: Request) -> Response:
    """Generaciones recientes (recientes primero) con paginacion.

    Envelope RETROCOMPATIBLE: mantiene la clave `generaciones` y AÑADE `paginacion`.
    Sin `?limite=`, preserva el comportamiento previo (las N mas recientes, def 50) con
    un `total` exacto; con `?limite=&desplazamiento=` pagina el conjunto completo.
    """
    limite, desplazamiento = paginacion_query(request)
    if limite is None:
        # Sin parametros: comportamiento previo (las `_LISTADO_MAX` mas recientes).
        items = generaciones.listar()
    else:
        items = generaciones.listar(limite=limite, desplazamiento=desplazamiento)
    total = generaciones.contar()
    return JSONResponse(
        {
            "generaciones": items,
            "paginacion": envoltura_paginacion(total, limite, desplazamiento),
        }
    )


async def obtener(request: Request) -> Response:
    """Una generacion por id. -> `{generacion}` | 404 si no existe."""
    gen_id = request.path_params.get("generacion_id")
    generacion = generaciones.obtener(gen_id)
    if generacion is None:
        return error("No se encontró esa generación.", status=404)
    return JSONResponse({"generacion": generacion})


# --------------------------------------------------------------------------- #
# SSE: progreso de una generacion en vivo                                      #
# --------------------------------------------------------------------------- #

# Cadencia de lectura SERVER-SIDE del registro YAML (la misma lectura que `obtener`).
# Mas fina que el sondeo del SPA (1.2 s): el cliente percibe el avance casi en vivo
# con UNA conexion en vez de ~0.8 req/s por cliente.
_STREAM_TICK_SEG = 0.4
# Heartbeat (comentario SSE `:ping`) para que Traefik/proxies no corten la conexion
# por inactividad mientras el modelo piensa sin emitir avance visible.
_STREAM_PING_SEG = 15.0
# Timeout DURO del stream: ningun job legitimo vive mas que el wall-timeout de claude;
# pasado este tope cerramos y el cliente reconecta (EventSource) o degrada a sondeo.
_STREAM_TIMEOUT_SEG = 15 * 60.0


def _evento_sse(nombre: str, datos: dict) -> str:
    """Serializa un evento SSE con nombre y payload JSON (una sola linea `data:`).

    `json.dumps` NUNCA emite saltos de linea crudos (van escapados como `\\n` dentro
    del string JSON), asi que una sola linea `data:` es siempre un frame SSE valido.
    """
    return f"event: {nombre}\ndata: {json.dumps(datos, ensure_ascii=False)}\n\n"


def _huella(g: dict) -> tuple:
    """Huella de AVANCE de una generacion: si no cambia, no se emite evento."""
    return (
        g.get("estado"),
        g.get("fase"),
        len(g.get("salida") or ""),
        len(g.get("razonamiento") or ""),
        bool(g.get("metricas")),
        bool(g.get("resultado")),
        g.get("error"),
    )


async def stream_estado(request: Request) -> Response:
    """SSE del progreso de una generacion. 404 si no existe al abrir.

    Bucle server-side: lee el registro (misma lectura que `obtener`, en threadpool
    porque parsea YAML de disco) cada ~0.4 s y emite:
      - `estado`   -> `{generacion}` SOLO cuando hay avance (cambia la huella).
      - `terminal` -> `{generacion}` al llegar a estado terminal; luego cierra.
      - `:ping`    -> comentario heartbeat cada ~15 s sin avance.
    Cierra limpio si el cliente desconecta o al timeout duro (15 min). Si el registro
    desaparece en pleno stream (borrado), emite `terminal` con `generacion: null` y cierra.

    AUTENTICACION: como sus hermanos, la aporta el middleware global (`SeguridadConsola`
    protege todo `/api`); `EventSource` no puede mandar cabeceras pero la cookie de
    sesion viaja sola en same-origin, que es exactamente la via prevista.
    """
    gen_id = request.path_params.get("generacion_id")
    inicial = await run_in_threadpool(generaciones.obtener, gen_id)
    if inicial is None:
        return error("No se encontró esa generación.", status=404)

    async def eventos() -> AsyncIterator[str]:
        transcurrido = 0.0
        sin_ping = 0.0
        huella_previa: tuple | None = None
        while True:
            if await request.is_disconnected():
                return
            g = await run_in_threadpool(generaciones.obtener, gen_id)
            if g is None:
                # Borrada en pleno stream: terminal "vacio" y cierre limpio.
                yield _evento_sse("terminal", {"generacion": None})
                return
            huella = _huella(g)
            if huella != huella_previa:
                huella_previa = huella
                yield _evento_sse("estado", {"generacion": g})
                sin_ping = 0.0
            if g.get("estado") in generaciones._ESTADOS_TERMINALES:
                yield _evento_sse("terminal", {"generacion": g})
                return
            if transcurrido >= _STREAM_TIMEOUT_SEG:
                return  # timeout duro: el cliente reconecta o degrada a sondeo
            if sin_ping >= _STREAM_PING_SEG:
                yield ":ping\n\n"
                sin_ping = 0.0
            await asyncio.sleep(_STREAM_TICK_SEG)
            transcurrido += _STREAM_TICK_SEG
            sin_ping += _STREAM_TICK_SEG

    return StreamingResponse(
        eventos(),
        media_type="text/event-stream",
        headers={
            # SSE no debe cachearse ni bufferizarse en ningun salto intermedio.
            # `X-Accel-Buffering: no` cubre un eventual nginx delante (hoy /api va
            # directo Traefik->back, pero el header es inocuo y defensivo).
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def cancelar(request: Request) -> Response:
    """Cancela un job de generacion EN CURSO.

    Mata el ARBOL del subproceso `claude` y deja el registro en estado terminal
    (`error`/`motivo=cancelado`, lo fija el hilo del job). -> `{generacion}` con el
    estado actual. 404 si la generacion no existe. Si ya habia terminado (sin job en
    curso) devuelve el registro tal cual: la cancelacion es idempotente.

    La generacion es subprocess `claude -p` (ADR 0001), asi que cancelar = matar el arbol
    del proceso local; lo dispara el usuario desde la SPA (un boton "Cancelar").
    """
    gen_id = request.path_params.get("generacion_id")
    generacion = generaciones.obtener(gen_id)
    if generacion is None:
        return error("No se encontró esa generación.", status=404)
    generaciones.cancelar(gen_id)
    return JSONResponse({"generacion": generaciones.obtener(gen_id) or generacion})


RUTAS = [
    Route("/api/generaciones", listar, methods=["GET"]),
    Route("/api/generaciones/{generacion_id}", obtener, methods=["GET"]),
    Route("/api/generaciones/{generacion_id}/stream", stream_estado, methods=["GET"]),
    Route("/api/generaciones/{generacion_id}/cancelar", cancelar, methods=["POST"]),
]
