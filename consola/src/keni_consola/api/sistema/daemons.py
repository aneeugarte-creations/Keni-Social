"""Daemons de fondo del panel de ADMIN (latidos persistidos por `latidos.py`).

  - GET  /api/sistema/daemons                   -> estado de los daemons de fondo.
  - GET  /api/sistema/daemons/{daemon}/barridos -> historial de barridos recientes del daemon.
  - POST /api/sistema/daemons/{daemon}/barrer   -> solicita un barrido INMEDIATO.

La sonda `sonda_daemons` la comparten el endpoint admin y el doctor (`/api/estado`).
"""

from __future__ import annotations

from datetime import datetime

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ... import db, latidos
from ..._http_json import _entero_query
from ...tiempo import ahora_iso
from ._comun import _es_admin, _logger, _rechazo_no_admin

# Umbral de ATRASO de un daemon: su bucle late cada `tick_seg` (gateados: <=60s; bucles
# fijos: su intervalo). Si `visto` es mas viejo que 2 ticks + margen, el hilo esta muerto
# o el proceso daemons caido => "atrasado". El suelo evita falsos positivos con ticks
# muy cortos (jitter de BD/arranque).
_MARGEN_ATRASO_SEG = 90.0
_UMBRAL_ATRASO_MIN_SEG = 120.0


def _edad_segundos(iso: str, ahora: datetime) -> float | None:
    """Edad en segundos de un timestamp canon (naive-UTC) frente a `ahora`; None si vacio."""
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return None
    return max(0.0, (ahora - dt).total_seconds())


def sonda_daemons() -> dict:
    """SONDA del estado de los daemons de fondo a partir de sus latidos persistidos.

    Devuelve `{daemons: [...], error}` donde cada entrada agrega al registro crudo de
    `daemon_latidos` la `edad_seg` del ultimo latido, el `umbral_atraso_seg` aplicado y
    un `estado` listo para pintar: "ok" (late y su ultimo barrido fue bien), "error"
    (late pero su ultimo barrido fallo), "inactivo" (apagado por su toggle/gate) o
    "atrasado" (deberia estar corriendo y no late: hilo muerto, proceso daemons caido o
    BD inaccesible para el). CRITERIO: un daemon con el gate OFF (`activo=0` en su ultimo
    latido) esta APAGADO A PROPOSITO — que no late no es un problema, asi que "inactivo"
    manda sobre "atrasado"; solo un daemon que deberia estar activo puede salir atrasado.
    Las filas de daemons RETIRADOS (`latidos.RETIRADOS`, p. ej. renombrados en un deploy)
    se ignoran: nadie las actualizara jamas. Defensiva: un fallo de BD degrada a lista
    vacia con `error` legible, nunca propaga. La comparten el endpoint admin
    (`GET /api/sistema/daemons`) y el doctor (`/api/estado`, chequeo `maquina:daemons`).
    """
    try:
        filas = db.listar_latidos()
    except Exception as e:  # noqa: BLE001 -- sonda defensiva: el panel nunca se cae
        _logger.warning("No se pudieron leer los latidos de daemons: %s", e)
        return {"daemons": [], "error": "No se pudieron leer los latidos de los daemons."}
    ahora = datetime.fromisoformat(ahora_iso())
    salida = []
    for f in filas:
        if f["daemon"] in latidos.RETIRADOS:
            continue
        edad = _edad_segundos(f["visto"], ahora)
        umbral = max(2.0 * f["tick_seg"], _UMBRAL_ATRASO_MIN_SEG) + _MARGEN_ATRASO_SEG
        if not f["activo"]:
            estado = "inactivo"
        elif edad is None or edad > umbral:
            estado = "atrasado"
        elif f["ultimo_error"] and f["ultimo_error"] >= (f["ultimo_ok"] or ""):
            # Canon ISO naive-UTC: comparar como texto respeta el orden temporal.
            estado = "error"
        else:
            estado = "ok"
        salida.append(
            {
                **f,
                "edad_seg": edad,
                "umbral_atraso_seg": umbral,
                "estado": estado,
                # `barrible`: su bucle corre sobre `bucle_gateado` y consume el flag de
                # barrido forzado; los bucles legados no lo miran, asi que el front solo
                # ofrece "Barrer ahora" a los barribles.
                "barrible": f["daemon"] in latidos.BARRIBLES,
                # `grupo` y `gasta_tokens`: clasificacion del daemon (motor/papel + si
                # consume claude) para el dashboard de Workers. Fuente unica en `latidos`,
                # asi el front agrupa sin hardcodear nombres.
                "grupo": latidos.grupo_de(f["daemon"]),
                "gasta_tokens": latidos.gasta_tokens(f["daemon"]),
                # `clase` ("ia"|"maquina"|"sistema") y `motor` ("investigacion"|"produccion"|null):
                # clasificacion AFINADA del daemon para el dashboard de Workers (cuanta IA de cara
                # adentro vs maquina NO-IA vs infraestructura). Fuente unica en `latidos`, contrato
                # ADITIVO (no toca grupo/gasta_tokens/clave_gate/barrible).
                "clase": latidos.clase_de(f["daemon"]),
                "motor": latidos.motor_de(f["daemon"]),
                # `clave_gate`: la clave de ajuste (KENI_*) que enciende/apaga el daemon
                # desde su fila (toggle in-place; el front la pasa a POST /api/ajustes).
                # null = SIEMPRE-ON sin toggle (limpiador/programador/metricas/...). Fuente
                # unica en `latidos`, asi el front no hardcodea el mapeo daemon->clave.
                "clave_gate": latidos.clave_gate_de(f["daemon"]),
            }
        )
    return {"daemons": salida, "error": None}


async def daemons_latidos(request: Request) -> Response:
    """GET /api/sistema/daemons: estado de los daemons de fondo (solo admin).

    Sirve tal cual la `sonda_daemons` compartida (contrato intacto con el frontend).
    """
    if not _es_admin(request):
        return _rechazo_no_admin()
    return JSONResponse(sonda_daemons())


async def daemons_barridos(request: Request) -> Response:
    """GET /api/sistema/daemons/{daemon}/barridos?limite=: historial de barridos (admin).

    Devuelve los barridos recientes (nuevo primero) del daemon desde `daemon_barridos`:
    `{daemon, barridos: [{id, daemon, ts_inicio, duracion_ms, ok, resumen, error_txt}, ...]}`.
    404 si el daemon no existe (no esta registrado en `daemon_latidos` o esta retirado): solo
    quien late tiene historial. `limite` se acota a la cota dura del historial por daemon.
    """
    if not _es_admin(request):
        return _rechazo_no_admin()
    daemon = str(request.path_params.get("daemon") or "").strip()
    try:
        registrados = {f["daemon"] for f in db.listar_latidos()}
    except Exception as e:  # noqa: BLE001 -- BD caida: degradar legible, no 500 crudo
        _logger.warning("No se pudieron leer los latidos para el historial de barridos: %s", e)
        return JSONResponse(
            {"error": "No se pudo consultar el registro de daemons."}, status_code=503
        )
    if daemon not in registrados or daemon in latidos.RETIRADOS:
        return JSONResponse(
            {"error": f"No hay ningún daemon registrado con el nombre {daemon!r}."},
            status_code=404,
        )
    limite = _entero_query(request.query_params.get("limite"), minimo=1) or 50
    return JSONResponse({"daemon": daemon, "barridos": db.listar_barridos(daemon, limite)})


async def daemons_barrer(request: Request) -> Response:
    """POST /api/sistema/daemons/{daemon}/barrer: solicita un barrido INMEDIATO (admin).

    Operacion sin SSH: el back y el servicio `daemons` son contenedores distintos, asi que
    la solicitud se PERSISTE en `daemon_latidos.barrido_solicitado` y el bucle del daemon
    (`daemon_util.bucle_gateado`) la consume en su siguiente tick corto (<= ~1 min),
    ejecutando el barrido YA y limpiando el flag.

    Validacion contra los daemons REGISTRADOS (filas de `daemon_latidos` no retiradas:
    quien late es quien puede barrer) Y contra `latidos.BARRIBLES`: solo los bucles
    sobre `bucle_gateado` CONSUMEN el flag; en un legado (programador/metricas/
    metricas_piezas/comercial) la solicitud quedaria suelta para siempre, asi que se
    rechaza en vez de aceptarla y mentir. Codigos: 404 daemon desconocido/retirado;
    409 si no admite barrido forzado (no barrible) o si su gate esta apagado por ajuste
    (el bucle ignoraria la solicitud: enciendelo primero); 200 -> {solicitado: true,
    daemon}.
    """
    if not _es_admin(request):
        return _rechazo_no_admin()
    daemon = str(request.path_params.get("daemon") or "").strip()
    try:
        filas = {f["daemon"]: f for f in db.listar_latidos()}
    except Exception as e:  # noqa: BLE001 -- BD caida: degradar legible, no 500 crudo
        _logger.warning("No se pudieron leer los latidos para forzar un barrido: %s", e)
        return JSONResponse(
            {"error": "No se pudo consultar el registro de daemons."}, status_code=503
        )
    fila = filas.get(daemon)
    if fila is None or daemon in latidos.RETIRADOS:
        return JSONResponse(
            {"error": f"No hay ningún daemon registrado con el nombre {daemon!r}."},
            status_code=404,
        )
    if daemon not in latidos.BARRIBLES:
        # Su bucle NO consume `barrido_solicitado`: aceptar dejaria el flag suelto.
        return JSONResponse(
            {
                "error": f"El daemon {daemon!r} no admite barrido forzado: su bucle "
                "no consume la solicitud."
            },
            status_code=409,
        )
    if not fila["activo"]:
        return JSONResponse(
            {
                "error": f"El daemon {daemon!r} está apagado por su ajuste; "
                "enciéndelo antes de forzar un barrido."
            },
            status_code=409,
        )
    db.solicitar_barrido(daemon)
    _logger.info("Barrido forzado de %r solicitado por un administrador.", daemon)
    return JSONResponse({"solicitado": True, "daemon": daemon})
