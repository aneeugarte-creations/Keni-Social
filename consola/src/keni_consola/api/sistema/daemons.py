"""Daemons de fondo del panel de ADMIN (latidos persistidos por `latidos.py`).

  - GET  /api/sistema/daemons                   -> estado de los daemons de fondo.
  - GET  /api/sistema/daemons/{daemon}/barridos -> historial de barridos recientes del daemon.
  - POST /api/sistema/daemons/{daemon}/barrer   -> solicita un barrido INMEDIATO.

La sonda `sonda_daemons` la comparten el endpoint admin y el doctor (`/api/estado`).
"""

from __future__ import annotations

from datetime import datetime

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ... import ajustes_catalogo, daemons_registro, db, latidos
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


def _gate_configurado(clave: str | None) -> bool | None:
    """Valor GUARDADO del flag propio de un daemon (lo que el switch del panel debe reflejar).

    Es el on/off CONFIGURADO de su `clave_gate` (store > env > defecto, vía el catálogo de
    ajustes), SIN ANDearlo con el maestro de la máquina: por eso el switch se mantiene encendido
    aunque la máquina esté apagada (el daemon queda «en espera», no «apagado»). None si el daemon
    no tiene gate (siempre-on) o su clave no es editable. Best-effort: ante cualquier fallo del
    catálogo devuelve None (el front cae a usar `activo`)."""
    if not clave:
        return None
    try:
        ajuste = ajustes_catalogo.por_clave(clave)
        if ajuste is None:
            return None
        valor, _fuente = ajustes_catalogo.valor_y_fuente(ajuste)
        return bool(valor)
    except Exception as e:  # noqa: BLE001 -- la sonda nunca se cae por leer un ajuste
        _logger.debug("No se pudo leer el gate configurado de %r: %s", clave, e)
        return None


def _ajustes_de(daemon: str) -> list[dict]:
    """Ajustes del catálogo que gobiernan el daemon, serializados para editar en su detalle.

    Resuelve cada clave de `latidos.ajustes_de` contra el catálogo (a_dict = valor efectivo +
    fuente + tipo/min/max/opciones). Salta en silencio las claves que no existan en el catálogo
    (defensivo: nunca rompe la sonda). Mantiene el orden declarado en `latidos.AJUSTES`."""
    salida: list[dict] = []
    for clave in latidos.ajustes_de(daemon):
        try:
            ajuste = ajustes_catalogo.por_clave(clave)
            if ajuste is not None:
                salida.append(ajustes_catalogo.a_dict(ajuste))
        except Exception as e:  # noqa: BLE001 -- una clave problemática no tumba la lista
            _logger.debug("No se pudo serializar el ajuste %r de %r: %s", clave, daemon, e)
    return salida


def sonda_daemons() -> dict:
    """SONDA del estado de los daemons de fondo a partir de sus latidos persistidos.

    Devuelve `{daemons: [...], error}` donde cada entrada agrega al registro crudo de
    `daemon_latidos` la `edad_seg` del ultimo latido, el `umbral_atraso_seg` aplicado y
    un `estado` listo para pintar: "ok" (late y su ultimo barrido fue bien), "error"
    (late pero su ultimo barrido fallo), "inactivo" (apagado por su toggle/gate), "en_espera"
    (su interruptor PROPIO esta ON pero el maestro de la maquina esta OFF: no corre, pero no es
    un fallo ni esta apagado), "atrasado" (deberia estar corriendo y no late: hilo muerto,
    proceso daemons caido o BD inaccesible para el) o "sin_datos" (registrado en
    `daemons_registro` pero SIN fila de latido todavia: BD recien migrada o hilo que nunca
    llego a arrancar; ver `_sin_datos`). CRITERIO: el estado se juzga con DOS
    señales — `gate_activo` (el flag PROPIO configurado, lo que refleja el switch) y `activo`
    (efectivo: flag propio AND la maquina). Con el flag propio OFF -> "inactivo"; con el flag ON
    pero sin correr -> "en_espera" (enmascarado por la maquina); solo un daemon que deberia estar
    activo de verdad puede salir "atrasado".
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
        clave_gate = latidos.clave_gate_de(f["daemon"])
        gate_activo = _gate_configurado(clave_gate)  # flag PROPIO configurado, o None (siempre-on)
        if gate_activo is False:
            # Su interruptor propio está APAGADO a propósito — que no late no es un problema.
            estado = "inactivo"
        elif not f["activo"]:
            # Efectivamente no corre. Si su flag propio está ON (gate_activo True), es la MÁQUINA
            # la que lo enmascara => "en espera" (no apagado). Si no tiene flag propio (None) y aun
            # así no está activo, es un siempre-on que no debería pasar por aquí: cae a "inactivo".
            estado = "en_espera" if gate_activo is True else "inactivo"
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
                # `etiqueta` (nombre humano del daemon) y `prompts` (los docs de la Prompts que
                # gobiernan un agente IA, [] si no es IA): lo que necesita la página Agentes para
                # NO hardcodear el nombre ni el mapeo de prompts en el front. Fuente única en
                # `latidos`.
                "etiqueta": latidos.etiqueta_de(f["daemon"]),
                # `descripcion`: frase de PARA QUÉ SIRVE el daemon (fuente única en `latidos`).
                # La consumen tanto el panel (línea bajo el nombre) como el bloque de descripción
                # de la página de detalle: un solo campo, una sola fuente. El `ultimo_resumen`
                # (qué hizo el último barrido) ya entra por `**f`.
                "descripcion": latidos.descripcion_de(f["daemon"]),
                "prompts": latidos.prompts_de(f["daemon"]),
                # `clave_gate`: la clave de ajuste (KENI_*) que enciende/apaga el daemon
                # desde su fila (toggle in-place; el front la pasa a POST /api/ajustes).
                # null = SIEMPRE-ON sin toggle (limpiador/programador/metricas/...). Fuente
                # unica en `latidos`, asi el front no hardcodea el mapeo daemon->clave.
                "clave_gate": clave_gate,
                # `gate_activo`: valor GUARDADO de ese flag propio (lo que el SWITCH refleja), SIN
                # ANDearlo con la maquina. Asi el switch se mantiene encendido aunque la maquina
                # este apagada (estado "en_espera") y deja de rebotar a OFF. null = siempre-on.
                "gate_activo": gate_activo,
                # `ajustes`: sus knobs editables (catálogo serializado) para operarlo sin salir
                # de su detalle. Fuente unica en `latidos`.
                "ajustes": _ajustes_de(f["daemon"]),
            }
        )
    salida.extend(_sin_datos({f["daemon"] for f in filas}))
    return {"daemons": salida, "error": None}


def _sin_datos(presentes: set[str]) -> list[dict]:
    """Filas sintéticas para los daemons REGISTRADOS (`daemons_registro`) sin fila de latido.

    `daemon_latidos` solo conoce a quien YA latió: un hilo que murió al arrancar o una BD
    recién migrada serían invisibles para el panel. El registro declarativo dice qué DEBE
    existir, y a lo registrado-pero-mudo se le pinta estado "sin_datos" — distinto de
    "inactivo" (apagado a propósito: su bucle late igualmente con activo=0) y de
    "atrasado" (llegó a latir y dejó de). Misma FORMA que una fila real (el front no
    distingue), con los campos de latido vacíos, `barrible` False (sin bucle confirmado
    vivo, nadie consumiría la solicitud) y el gate evaluado igual que en una fila real.
    """
    salida: list[dict] = []
    for nombre in daemons_registro.esperados():
        if nombre in presentes or nombre in latidos.RETIRADOS:
            continue
        clave_gate = latidos.clave_gate_de(nombre)
        salida.append(
            {
                "daemon": nombre,
                "visto": "",
                "activo": False,
                "intervalo_seg": 0.0,
                "tick_seg": 0.0,
                "ultimo_barrido": "",
                "ultimo_ok": "",
                "ultimo_error": "",
                "error_txt": "",
                "duracion_ms": 0,
                "barridos": 0,
                "errores": 0,
                "barrido_solicitado": "",
                "ultimo_resumen": "",
                "edad_seg": None,
                "umbral_atraso_seg": 0.0,
                "estado": "sin_datos",
                "barrible": False,
                "grupo": latidos.grupo_de(nombre),
                "gasta_tokens": latidos.gasta_tokens(nombre),
                "clase": latidos.clase_de(nombre),
                "motor": latidos.motor_de(nombre),
                "etiqueta": latidos.etiqueta_de(nombre),
                "descripcion": latidos.descripcion_de(nombre),
                "prompts": latidos.prompts_de(nombre),
                "clave_gate": clave_gate,
                "gate_activo": _gate_configurado(clave_gate),
                "ajustes": _ajustes_de(nombre),
            }
        )
    return salida


async def daemons_latidos(request: Request) -> Response:
    """GET /api/sistema/daemons: estado de los daemons de fondo (solo admin).

    Sirve tal cual la `sonda_daemons` compartida (contrato intacto con el frontend).
    """
    if not _es_admin(request):
        return _rechazo_no_admin()
    return JSONResponse(await run_in_threadpool(sonda_daemons))


def _barridos(daemon: str, limite: int) -> tuple[int, dict]:
    try:
        registrados = {f["daemon"] for f in db.listar_latidos()}
    except Exception as e:  # noqa: BLE001 -- BD caida: degradar legible, no 500 crudo
        _logger.warning("No se pudieron leer los latidos para el historial de barridos: %s", e)
        return 503, {"error": "No se pudo consultar el registro de daemons."}
    # Conocidos = quien YA late + lo declarado en el registro (un daemon registrado sin
    # latido aún responde con historial vacío, no 404: su detalle debe poder abrirse).
    conocidos = registrados | set(daemons_registro.esperados())
    if daemon not in conocidos or daemon in latidos.RETIRADOS:
        return 404, {"error": f"No hay ningún daemon registrado con el nombre {daemon!r}."}
    return 200, {"daemon": daemon, "barridos": db.listar_barridos(daemon, limite)}


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
    limite = _entero_query(request.query_params.get("limite"), minimo=1) or 50
    status, cuerpo = await run_in_threadpool(_barridos, daemon, limite)
    return JSONResponse(cuerpo, status_code=status)


def _barrer(daemon: str) -> tuple[int, dict]:
    try:
        filas = {f["daemon"]: f for f in db.listar_latidos()}
    except Exception as e:  # noqa: BLE001 -- BD caida: degradar legible, no 500 crudo
        _logger.warning("No se pudieron leer los latidos para forzar un barrido: %s", e)
        return 503, {"error": "No se pudo consultar el registro de daemons."}
    fila = filas.get(daemon)
    if fila is None or daemon in latidos.RETIRADOS:
        return 404, {"error": f"No hay ningún daemon registrado con el nombre {daemon!r}."}
    if daemon not in latidos.BARRIBLES:
        # Su bucle NO consume `barrido_solicitado`: aceptar dejaria el flag suelto.
        return 409, {
            "error": f"El daemon {daemon!r} no admite barrido forzado: su bucle "
            "no consume la solicitud."
        }
    if not fila["activo"]:
        # No corre de verdad: o su flag propio está OFF, o está «en espera» (flag ON pero la
        # máquina apagada). En ambos casos el bucle no consumiría la solicitud, así que se rechaza.
        en_espera = _gate_configurado(latidos.clave_gate_de(daemon)) is True
        motivo = (
            "está en espera (su interruptor está encendido pero la máquina de contenido está "
            "apagada); enciende la máquina"
            if en_espera
            else "está apagado por su ajuste; enciéndelo"
        )
        return 409, {"error": f"El daemon {daemon!r} {motivo} antes de forzar un barrido."}
    db.solicitar_barrido(daemon)
    _logger.info("Barrido forzado de %r solicitado por un administrador.", daemon)
    return 200, {"solicitado": True, "daemon": daemon}


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
    status, cuerpo = await run_in_threadpool(_barrer, daemon)
    return JSONResponse(cuerpo, status_code=status)
