"""API Reciclaje proactivo (/api/reciclaje): candidatas de ARCHIVO a retomar.

Capa PROACTIVA sobre el reciclaje manual que ya vive en `api/publicaciones.py`
(`POST /api/publicaciones/{id}/reciclar`). Aqui NO se recicla nada: solo se LISTAN
las piezas publicadas que la heuristica considera dignas de retomarse, cada una con
su `motivo` y un texto explicable. La UI muestra la lista y, al pulsar, dispara el
reciclado existente (mismo endpoint de siempre), sin duplicar logica.

La heuristica (sin ML, auditable) vive en `dominio.reciclaje`. Este router NO consulta
el almacen de C (`publicaciones`) por su cuenta: el dominio de reciclaje pide el universo
de piezas a la funcion-contrato de LECTURA que C expone
(`dominio.publicaciones.listar_para_reciclaje`, ADR 0005 §Seams #2). El router solo lee
los filtros de query, dispara la heuristica y serializa la respuesta.

  GET /api/reciclaje/sugerencias?marca=&red=  -> {sugerencias: [...], parametros: {...}}

Errores en espanol, sin tracebacks (contrato del paquete `api`).
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from ..dominio import reciclaje


async def sugerencias(request: Request) -> Response:
    """Lista las candidatas de reciclaje (archivo que merece retomarse).

    Filtros opcionales `?marca=&red=` acotan el universo de piezas. Devuelve las
    candidatas ya ordenadas (efemeride > perenne > recurrente) con su motivo, mas
    los `parametros` de la heuristica para que la UI los pueda explicar.
    """
    qp = request.query_params
    marca = qp.get("marca") or None
    red = qp.get("red") or None
    # El universo de piezas (cualquier estado) lo sirve el CONTRATO de lectura de C
    # (`dominio.publicaciones.listar_para_reciclaje`, via `dominio.reciclaje`): la
    # heuristica necesita ver borradores/programadas para no reproponer lo ya reciclado
    # y las publicadas para el cruce de temas recurrentes. El router no toca el almacen.
    candidatas = reciclaje.sugerencias_de_reciclaje(marca=marca, red=red)
    return JSONResponse(
        {
            "sugerencias": candidatas,
            "parametros": {
                "ventana_efemeride_dias": reciclaje.VENTANA_EFEMERIDE_DIAS,
                "edad_minima_perenne_dias": reciclaje.EDAD_MINIMA_PERENNE_DIAS,
                "edad_minima_antiguedad_dias": reciclaje.EDAD_MINIMA_ANTIGUEDAD_DIAS,
                "umbral_engagement_rendimiento": reciclaje.UMBRAL_ENGAGEMENT_RENDIMIENTO,
            },
        }
    )


RUTAS = [
    Route("/api/reciclaje/sugerencias", sugerencias, methods=["GET"]),
]
