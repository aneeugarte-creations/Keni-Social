"""API Alertas de rendimiento (/api/alertas): bitacora EDITORIAL de lo que merece atencion.

El daemon `alertas_rendimiento.py` emite a la bitacora de eventos internos
(`db.eventos_internos`) dos tipos de aviso PROACTIVO sobre las piezas publicadas:

  - `pieza.bajo_rendimiento`    una pieza publicada cae por debajo del umbral de engagement.

Los webhooks (`/api/webhooks`, SOLO ADMIN) tambien los exponen; este endpoint los expone al
EQUIPO (cualquier usuario autenticado): es LECTURA de avisos del propio tablero, no
gestion de secretos. La barrera de sesion la aplica el middleware `SeguridadConsola`;
aqui no se relaja nada (igual que `/api/reciclaje` u otros endpoints de lectura).

  GET /api/alertas[?limite=N]  -> {"alertas": [{id, tipo, publicacion_id, pieza_id,
                                                payload, creado}, ...]}

Lee la bitacora (`repos.listar_eventos_internos`) y FILTRA a los dos tipos de alerta de
rendimiento (los `TIPOS_ALERTA`), descartando el resto de eventos internos (aprobaciones,
piezas, vencimientos). `?limite=` acota cuantas filas se leen (def 50, max 200).

Errores en espanol, sin tracebacks (contrato del paquete `api`).
"""

from __future__ import annotations

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import repos

# Tipos de evento interno que SON alertas de rendimiento (subconjunto de
# `dominio.eventos.TIPOS_EVENTO`). Se nombran aqui de forma explicita para no acoplar el
# filtro al orden/contenido completo de `TIPOS_EVENTO`.
TIPOS_ALERTA: frozenset[str] = frozenset(
    {"pieza.bajo_rendimiento"}
)

_LIMITE_DEF = 50
_LIMITE_MAX = 200


def _limite(crudo: str | None) -> int:
    """Normaliza `?limite=` a un entero en [1, _LIMITE_MAX] (def `_LIMITE_DEF`)."""
    if not crudo:
        return _LIMITE_DEF
    try:
        valor = int(crudo)
    except (TypeError, ValueError):
        return _LIMITE_DEF
    return max(1, min(valor, _LIMITE_MAX))


def _listar(limite: int) -> dict:
    # Lee mas de la bitacora (otros tipos diluyen) y recorta tras filtrar. El tope duro de
    # `repos.listar_eventos_internos` (500) acota el coste; con doble del limite basta de
    # sobra para el volumen real del piloto.
    crudos = repos.listar_eventos_internos(limite=min(_LIMITE_MAX * 2, limite * 4))
    alertas = [e for e in crudos if e.get("tipo") in TIPOS_ALERTA][:limite]
    return {"alertas": alertas}


async def listar(request: Request) -> Response:
    """GET /api/alertas[?limite=N]: alertas de rendimiento (bajo rendimiento).

    Lee la bitacora de eventos internos y FILTRA a los tipos de alerta. Para no perder
    alertas cuando la bitacora trae muchos eventos de otros tipos, leemos un poco mas que
    el limite pedido y luego recortamos al limite ya filtrado.
    """
    limite = _limite(request.query_params.get("limite"))
    cuerpo = await run_in_threadpool(_listar, limite)
    return JSONResponse(cuerpo)


RUTAS = [
    Route("/api/alertas", listar, methods=["GET"]),
]
