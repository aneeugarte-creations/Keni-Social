"""API Rota · copia de semana + panel de carga por miembro."""
from __future__ import annotations

import re
from typing import Any

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ... import repos
from ... import rota as dominio
from ..._http_json import leer_json
from ._comun import _equipo, _franjas_de_semana, _lunes_param, _marca_cuerpo, _marca_param


async def copiar_semana(request: Request) -> Response:
    """POST /api/rota/copiar-semana: replica los turnos de una semana a otra (offset +N dias).

    Cuerpo: `{de_lunes, a_lunes, marca, reemplazar?: bool}`. NO copia eventos (cada semana tiene
    los suyos); copia EXCLUSIVAMENTE la rejilla (franjas + turnos) de UNA marca. Con
    `reemplazar=true`, primero borra los turnos de esa marca en `a_lunes`. Devuelve `{copiados: N}`.

    GRID POR MARCA: copiar exige una marca concreta (no "Todas": cada rejilla se copia aparte).
    """
    datos = await leer_json(request)
    de_lunes = dominio.lunes_de_semana_iso(str(datos.get("de_lunes", "")).strip())
    a_lunes = dominio.lunes_de_semana_iso(str(datos.get("a_lunes", "")).strip())
    reemplazar = bool(datos.get("reemplazar", False))

    if not de_lunes or not a_lunes:
        return JSONResponse(
            {"error": "Indica los lunes origen y destino (AAAA-MM-DD)."}, status_code=400
        )
    if de_lunes == a_lunes:
        return JSONResponse(
            {"error": "La semana origen y la destino no pueden ser la misma."},
            status_code=400,
        )
    marca, error = _marca_cuerpo(datos)
    if error is not None:
        return error

    n = await run_in_threadpool(
        repos.copiar_turnos_rota, de_lunes, a_lunes, reemplazar=reemplazar, marca=marca
    )
    return JSONResponse({"copiados": n})


_MES_RE = re.compile(r"^\d{4}-\d{2}$")


async def copiar_mes(request: Request) -> Response:
    """POST /api/rota/copiar-mes: siembra el mes destino con el rol de un mes origen, semana a
    semana (alineado por dia de semana: lunes<->lunes).

    Cuerpo: `{a_mes: "YYYY-MM", de_mes?: "YYYY-MM", marca, reemplazar?: bool}`. `de_mes` elige el mes
    origen; ausente -> el MES ANTERIOR al destino. NO copia eventos; copia la rejilla (franjas +
    turnos) de UNA marca. Con `reemplazar=true`, sobrescribe cada semana destino antes de copiar (si
    no, rellena lo que falte). Es el punto de partida: luego el coordinador edita. Devuelve
    `{copiados: N}`.

    GRID POR MARCA: exige una marca concreta (no "Todas": cada rejilla se copia aparte).
    """
    datos = await leer_json(request)
    a_mes = str(datos.get("a_mes", "")).strip()
    de_mes = str(datos.get("de_mes", "")).strip() or None
    reemplazar = bool(datos.get("reemplazar", False))

    if not _MES_RE.match(a_mes):
        return JSONResponse({"error": "Indica el mes destino (AAAA-MM)."}, status_code=400)
    if de_mes is not None and not _MES_RE.match(de_mes):
        return JSONResponse({"error": "Indica el mes origen (AAAA-MM)."}, status_code=400)
    if de_mes is not None and de_mes == a_mes:
        return JSONResponse(
            {"error": "El mes origen y el destino no pueden ser el mismo."}, status_code=400
        )
    marca, error = _marca_cuerpo(datos)
    if error is not None:
        return error

    n = await run_in_threadpool(
        repos.copiar_mes_rota, a_mes, de_mes=de_mes, reemplazar=reemplazar, marca=marca
    )
    return JSONResponse({"copiados": n})


async def carga_semana(request: Request) -> Response:
    """GET /api/rota/carga?lunes=AAAA-MM-DD: panel de carga por miembro.

    Devuelve `{miembros: [...]}` con el resumen de carga: eventos cubiertos (DERIVADO de
    turnos × eventos), dias trabajados, si toca sabado, descansos. Ordenado por el mas
    cargado primero. Datos puros del dominio (`dominio.resumen_carga`).

    `?marca=` acota los eventos contados a una marca (consistente con `cobertura_semana`);
    ausente -> todas las marcas.
    """
    lunes = _lunes_param(request)
    if not lunes:
        return JSONResponse(
            {"error": "Indica el lunes de la semana (AAAA-MM-DD)."}, status_code=400
        )
    marca, error = _marca_param(request)
    if error is not None:
        return error
    cuerpo = await run_in_threadpool(_carga_semana, lunes, marca)
    return JSONResponse(cuerpo)


def _carga_semana(lunes: str, marca: str | None) -> dict[str, Any]:
    equipo = _equipo()
    turnos = repos.listar_turnos_rota(semana=lunes, marca=marca)
    inicio, fin = dominio.rango_semana(lunes)
    eventos = repos.listar_eventos_rota(desde=inicio, hasta=fin, marca=marca)
    franjas_lista, _por_id = _franjas_de_semana(lunes, marca)
    cargas = dominio.resumen_carga(
        equipo,
        turnos,
        eventos,
        franjas_lista,
        lunes_iso=lunes,
    )
    return {
        "lunes": lunes,
        "miembros": [
            {
                "miembro_id": c.miembro_id,
                "nombre": c.nombre,
                "eventos": c.eventos,
                "dias_trabajados": c.dias_trabajados,
                "sabado": c.sabado,
                "descansos": c.descansos,
            }
            for c in cargas
        ],
    }
