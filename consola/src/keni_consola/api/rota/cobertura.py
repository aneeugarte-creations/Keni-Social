"""API Rota · cobertura DERIVADA (no persistida): para un evento, quien lo cubre."""
from __future__ import annotations

from typing import Any

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ... import repos
from ... import rota as dominio
from ...estados import (
    TIPO_COBERTURA_NO_CUBRIR,
)
from ._comun import (
    _evento_a_dict,
    _franja_semana_a_dict,
    _franjas_de_semana,
    _lunes_param,
    _marca_param,
    _nombres_equipo,
)


def _cobertura_para_evento(
    evento: dict[str, Any],
    turnos: list[dict[str, Any]],
    nombres: dict[str, str],
    franjas_semana: list[dict[str, Any]],
    franjas_por_id: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Calcula la cobertura derivada de UN evento usando `dominio.cobertura_de_evento`."""
    cubridores = dominio.cobertura_de_evento(evento, turnos, franjas_semana)
    franjas_por_id = franjas_por_id or {f["id"]: f for f in franjas_semana}
    return {
        **_evento_a_dict(evento),
        "cobertura": [
            {
                "turno_id": t["id"],
                "miembro_id": t["miembro_id"],
                "miembro_nombre": nombres.get(
                    t["miembro_id"], t.get("miembro_nombre", "")
                ),
                "franja_id": t.get("franja_id", "") or "",
                "franja_nombre": (
                    franjas_por_id.get(t.get("franja_id", "") or "", {}).get("nombre", "")
                ),
                "override": bool(t.get("override", False)),
            }
            for t in cubridores
        ],
    }


async def cobertura_semana(request: Request) -> Response:
    """GET /api/rota/cobertura[?lunes]: cobertura derivada de los eventos de la semana.

    Devuelve `{lunes, eventos: [{...evento, cobertura: [{miembro_id, miembro_nombre,
    franja_id, franja_nombre, turno_id, override}, ...]}], franjas}`. NO persiste nada;
    cruza turnos x eventos x franjas vivas de la semana. Sin `lunes` valido -> 400.

    GRID POR MARCA: `?marca=` acota la rejilla ENTERA (eventos, turnos y franjas) a esa marca;
    ausente/vacio -> "Todas" (todas las marcas agregadas: la UI apila las columnas/turnos
    etiquetando cada uno con su marca). `franjas_config` se devuelve para la marca activa (o
    los defaults en "Todas").
    """
    lunes = _lunes_param(request)
    if not lunes:
        return JSONResponse(
            {"error": "Indica el lunes de la semana (AAAA-MM-DD)."}, status_code=400
        )
    marca, error = _marca_param(request)
    if error is not None:
        return error
    cuerpo = await run_in_threadpool(_cobertura_semana, lunes, marca)
    return JSONResponse(cuerpo)


def _cobertura_semana(lunes: str, marca: str | None) -> dict[str, Any]:
    inicio, fin = dominio.rango_semana(lunes)
    eventos = repos.listar_eventos_rota(desde=inicio, hasta=fin, marca=marca)
    # Filtra los `no_cubrir` por defecto (no se cubren por convencion editorial).
    eventos = [e for e in eventos if (e.get("tipo_cobertura") or "transmision") != TIPO_COBERTURA_NO_CUBRIR]
    turnos = repos.listar_turnos_rota(semana=lunes, marca=marca)
    nombres = _nombres_equipo()
    franjas_cfg = repos.obtener_franjas_config(marca or "")
    franjas_lista, franjas_por_id = _franjas_de_semana(lunes, marca)
    return {
        "lunes": lunes,
        "inicio": inicio,
        "fin": fin,
        "franjas_config": franjas_cfg,
        "franjas": [_franja_semana_a_dict(f) for f in franjas_lista],
        "eventos": [
            _cobertura_para_evento(e, turnos, nombres, franjas_lista, franjas_por_id)
            for e in eventos
        ],
    }


async def cobertura_evento(request: Request) -> Response:
    """GET /api/rota/cobertura/evento/{evento_id}: cobertura derivada de UN evento."""
    evento_id = request.path_params["evento_id"]
    status, cuerpo = await run_in_threadpool(_cobertura_evento, evento_id)
    return JSONResponse(cuerpo, status_code=status)


def _cobertura_evento(evento_id: str) -> tuple[int, dict[str, Any]]:
    evento = repos.obtener_evento_rota(evento_id)
    if evento is None:
        return 404, {"error": "El evento no existe."}
    semana = dominio.lunes_de_semana_iso(evento.get("fecha", ""))
    # GRID POR MARCA: la cobertura del evento se cruza con la rejilla de SU marca (turnos y
    # franjas de esa marca); sin marca (evento legado) cae al comportamiento agregado.
    marca_ev = evento.get("marca", "") or None
    turnos = repos.listar_turnos_rota(semana=semana, marca=marca_ev) if semana else []
    nombres = _nombres_equipo()
    franjas_cfg = repos.obtener_franjas_config(marca_ev or "")
    franjas_lista, franjas_por_id = _franjas_de_semana(semana, marca_ev) if semana else ([], {})
    return 200, {
        "evento": _cobertura_para_evento(
            evento, turnos, nombres, franjas_lista, franjas_por_id
        ),
        "franjas_config": franjas_cfg,
        "franjas": [_franja_semana_a_dict(f) for f in franjas_lista],
    }
