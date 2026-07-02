"""API SUGERENCIA DE HORA: el mejor momento para publicar una pieza (marca/red).

Objetivo de producto ("el equipo solo crea piezas; la operativa es automatica"): un boton
"Sugerir mejor hora" de 1 clic que propone una fecha-hora optima, combinando:

  - el HISTORICO de engagement de la marca/red (de `metricas_cache` -> Metricool, UNICA
    fuente: la serie diaria de interacciones, que da el "que dia rinde mejor"), y
  - las FRANJAS de pieza configuradas (colas `(dia_semana, hora)` aplicables) con sus
    HUECOS libres (se evitan los datetimes ya `programado`, igual que el encolado normal).

La logica PURA vive en `dominio.planificacion`; aqui solo se traen los datos (cache de
metricas + franjas + ocupados) y se serializa. SOLO LECTURA: no programa nada; devuelve la
sugerencia para que la UI la acepte con un clic (y entonces use el flujo normal de programar).

  POST /api/planificacion/sugerir-hora   {marca, red, rango?}
      -> {sugerencia: {fecha, score, motivo, con_historico}} | {sugerencia: null, motivo}

`marca` es el id CANONICO del catalogo (slug-guion, como en el tablero); se traduce a
`id_metricas` para leer la cache. `red` una red canonica. `rango` (opcional) el periodo del
historico (def "mes"). Degradacion honesta: si no hay franjas aplicables, `sugerencia: null`
con motivo; si no hay historico, cae al proximo hueco libre marcandolo en el motivo.
"""

from __future__ import annotations

from datetime import datetime

from keni_metricas import servicio
from keni_shared import marcas
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import metricas_cache, redes, repos
from .._http_json import leer_json
from ..dominio import planificacion
from . import franjas as api_franjas


def _ocupados_programados() -> set[str]:
    """Datetimes ISO ('YYYY-MM-DDTHH:MM') ya ocupados por piezas en estado `programado`.

    Mismo criterio que `api.piezas.calcular_hueco_para`: no proponer un hueco que
    ya tiene otra pieza programada encima.
    """
    return {
        otra["fecha_programada"]
        for otra in repos.listar_piezas(estado="programado")
        if otra.get("fecha_programada")
    }


def _perfil_dia_de_cache(marca_canonica: str, rango: str) -> dict[int, float]:
    """Perfil de engagement por dia de la semana desde la cache de metricas (best-effort).

    Traduce la marca CANONICA a su `id_metricas` (la frontera de metricas habla guion_bajo)
    y lee la serie diaria cacheada (TIPO_TENDENCIA, lazy fill). Cualquier fallo de la fuente
    degrada a perfil VACIO (sin señal de dia), no rompe la sugerencia.
    """
    id_metricas = marcas.id_metricas_de(marca_canonica) if marca_canonica else None
    try:
        payload, _generado = metricas_cache.tendencia(rango, id_metricas)
    except Exception:  # noqa: BLE001 -- sin historico no es un error: degrada a perfil vacio
        return {}
    puntos = payload.get("puntos", []) if isinstance(payload, dict) else []
    if not isinstance(puntos, list):
        return {}
    return planificacion.perfil_por_dia_semana(puntos)


async def sugerir(request: Request) -> Response:
    """POST /api/planificacion/sugerir-hora: propone la mejor fecha-hora (marca/red).

    Cuerpo `{marca, red, rango?}`. Devuelve `{sugerencia}` (o `{sugerencia: null, motivo}`
    si no hay franjas aplicables). No programa: la UI aplica la fecha con 1 clic y luego usa
    el flujo normal de programado.
    """
    datos = await leer_json(request)

    marca = datos.get("marca", "") or ""
    if not isinstance(marca, str) or not marcas.es_marca(marca):
        return JSONResponse(
            {"error": "Indica una marca válida del catálogo."}, status_code=400
        )
    red = datos.get("red", "") or ""
    if not isinstance(red, str) or not redes.es_red(red):
        return JSONResponse({"error": "Indica una red válida."}, status_code=400)

    rango_crudo = datos.get("rango", "mes")
    rango = servicio.RANGOS_VALIDOS[0]
    if isinstance(rango_crudo, str) and rango_crudo in servicio.RANGOS_VALIDOS:
        rango = rango_crudo

    cuerpo = await run_in_threadpool(_sugerir, marca, red, rango)
    return JSONResponse(cuerpo)


def _sugerir(marca: str, red: str, rango: str) -> dict:
    franjas = repos.listar_franjas()
    aplican = api_franjas.franjas_aplicables(franjas, marca, red)
    if not aplican:
        return {
            "sugerencia": None,
            "motivo": (
                "No hay franjas configuradas para esta marca/red. "
                "Crea una franja horaria para poder sugerir un momento."
            ),
        }

    perfil = _perfil_dia_de_cache(marca, rango)
    sugerencia = planificacion.sugerir_mejor_hora(
        franjas_aplican=aplican,
        perfil_dia=perfil,
        ahora=datetime.now(),
        ocupados=_ocupados_programados(),
    )
    if sugerencia is None:
        return {
            "sugerencia": None,
            "motivo": "No hay huecos libres próximos en las franjas de esta marca/red.",
        }
    return {"sugerencia": sugerencia.a_dict(), "motivo": ""}


RUTAS = [
    Route("/api/planificacion/sugerir-hora", sugerir, methods=["POST"]),
]
