"""API Estado: autodiagnostico del sistema en JSON (el DOCTOR de la consola).

Chequeos en una sola respuesta, todos calculados AQUI sobre las sondas reales del
sistema (consolida las sondas del banner del front + conexion de metricas):

  - MAQUINA de contenido (`maquina:*`, admin=False): cola de generacion, presupuesto
    de IA, kill switch y daemons de fondo. Reusan las sondas compartidas de
    `api/sistema.py` (`sonda_daemons`), `api/actividad.snapshot_cola` y
    `presupuesto_ia.estado()` — sin duplicar ningun juicio.
  - INFRAESTRUCTURA (`infra:*`, admin=True): disco, backups y S3, via las sondas de
    `api/sistema.py` (`_discos`, `sonda_backups`, `sonda_s3_salud`).
  - METRICAS (`metricas:metricool`, admin=True): conexion a Metricool POR MARCA, la
    MISMA fuente y el MISMO juicio que `GET /api/conexiones/metricool`
    (`api.conexiones.estado_marcas_metricool`).

CONTRATO de cada chequeo: `{id, estado, nombre, detalle, icono, admin, siguiente_paso}`.
  - `id`: estable ("maquina:*" / "infra:*" / "metricas:*"). El front puede anclar
    logica a el sin depender del nombre humano.
  - `estado`: "ok" | "aviso" | "error". `icono` es el emoji equivalente.
  - `detalle`: mensaje humano. `siguiente_paso`: accion concreta cuando NO esta ok
    (None si ok), con la ruta REAL en la UI cuando el remedio vive ahi.
  - `admin`: True para los chequeos de INFRAESTRUCTURA/METRICAS (su remedio es de
    operador) y False para los de la MAQUINA de contenido (le importan a todo el
    equipo). El front filtra por rol con este flag; ningun detalle expone secretos.

Se mantienen el `resumen` global y el `siguiente_paso` de cabecera (frases propias,
calculadas sobre TODOS los chequeos).

Los chequeos son DEFENSIVOS: un fallo de BD/disco/config degrada ese chequeo a
"aviso"/"error" con mensaje legible, nunca tumba el endpoint. Las sondas se parchean
en sus modulos (`api.sistema`, `api.actividad`, `api.conexiones`, `presupuesto_ia`).
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import presupuesto_ia
from . import actividad as api_actividad
from . import conexiones as api_conexiones
from . import sistema as api_sistema

# Iconos por estado (mismo lenguaje visual en toda la lista).
_ICONOS = {"ok": "✅", "aviso": "⚠️", "error": "❌"}


def _chequeo(
    id_: str,
    nombre: str,
    estado: str,
    detalle: str,
    *,
    admin: bool,
    siguiente_paso: str | None = None,
) -> dict:
    """Serializa UN chequeo al contrato del endpoint (paso solo cuando no esta ok)."""
    return {
        "id": id_,
        "estado": estado,
        "nombre": nombre,
        "detalle": detalle,
        "icono": _ICONOS.get(estado, ""),
        "admin": admin,
        "siguiente_paso": siguiente_paso if estado != "ok" else None,
    }


# --------------------------------------------------------------------------- #
# Chequeos de la MAQUINA de contenido (admin=False: le importan a todo el equipo)
# --------------------------------------------------------------------------- #


def _chequeo_cola() -> dict:
    """Cola de generacion: profundidad. La cola NO tiene tope (R-NO-LIMIT): nunca "llena".

    El unico limite es la CONCURRENCIA (`max_jobs`); el exceso ESPERA, nada se rechaza por
    tamano de cola. El chequeo informa cuanto hay en curso (corriendo + esperando), no avisa
    de saturacion (no existe). Sigue degradando a `aviso` si la BD no responde.
    """
    try:
        snap = api_actividad.snapshot_cola()
    except Exception:  # noqa: BLE001 -- sonda defensiva: un blip de BD no tumba el doctor
        return _chequeo(
            "maquina:cola", "Cola de generación", "aviso",
            "No se pudo consultar la cola de generación.",
            admin=False,
            siguiente_paso="Comprueba que la base de datos responde y recarga el diagnóstico.",
        )
    return _chequeo(
        "maquina:cola", "Cola de generación", "ok",
        f"{snap['reclamados']} en curso y {snap['pendientes']} esperando "
        f"(concurrencia máx {snap['max_jobs']}; el exceso espera, sin rechazo).",
        admin=False,
    )


def _chequeos_presupuesto() -> list[dict]:
    """Presupuesto diario de tokens (dos escalones) + kill switch de generacion."""
    try:
        est = presupuesto_ia.estado()
    except Exception:  # noqa: BLE001 -- sonda defensiva
        return [
            _chequeo(
                "maquina:presupuesto", "Presupuesto de IA", "aviso",
                "No se pudo consultar el presupuesto de generación.",
                admin=False,
                siguiente_paso="Comprueba que la base de datos responde y recarga el diagnóstico.",
            )
        ]
    salida: list[dict] = []
    nivel = est.get("nivel")
    if nivel == presupuesto_ia.NIVEL_AGOTADO:
        salida.append(_chequeo(
            "maquina:presupuesto", "Presupuesto de IA", "error",
            "Presupuesto de IA AGOTADO (margen incluido): corte total de la generación.",
            admin=False,
            siguiente_paso="Sube el presupuesto diario en el Monitor o espera al reinicio del día (UTC).",
        ))
    elif nivel == presupuesto_ia.NIVEL_SOLO_MANUAL:
        salida.append(_chequeo(
            "maquina:presupuesto", "Presupuesto de IA", "aviso",
            "Presupuesto de IA al límite: solo siguen los lanzamientos manuales.",
            admin=False,
            siguiente_paso="Sube el presupuesto diario en el Monitor o deja que el fondo espere al día siguiente.",
        ))
    else:
        presupuesto = int(est.get("presupuesto_tokens_dia") or 0)
        presupuesto_usd = float(est.get("presupuesto_usd_dia") or 0.0)
        pct = est.get("pct_usado")
        pct_usd = est.get("pct_usado_usd")
        partes = []
        if presupuesto > 0 and pct is not None:
            partes.append(f"{pct}% de los tokens")
        if presupuesto_usd > 0 and pct_usd is not None:
            partes.append(f"{pct_usd}% del coste (USD)")
        detalle = (
            f"Gasto de hoy: {' y '.join(partes)} del presupuesto diario."
            if partes
            else "Sin presupuesto diario configurado (sin límite)."
        )
        salida.append(_chequeo(
            "maquina:presupuesto", "Presupuesto de IA", "ok", detalle, admin=False,
        ))
    # Gate diario por % POR CUENTA: cualquier cuenta que haya alcanzado su umbral del día pausa SUS
    # marcas. Reportamos las cuentas gateadas (puede haber una o las dos).
    cuentas = est.get("gate_diario_cuentas") or {}
    gateadas = [g for g in cuentas.values() if g.get("pausado_por_pct")]
    if bool(est.get("pausada")):
        salida.append(_chequeo(
            "maquina:pausa", "Generación con IA", "aviso",
            "Generación PAUSADA por el kill switch: no se encola ni se ejecuta nada nuevo.",
            admin=False,
            siguiente_paso="Reactívala en el Monitor (ajuste «Generación con IA: pausada»).",
        ))
    elif gateadas:
        detalle_cuentas = "; ".join(
            f"cuenta {str(g.get('cuenta') or '?').upper()}: {g.get('consumo_hoy_pct')}% "
            f"(umbral {g.get('umbral_pct')}%)"
            for g in gateadas
        )
        salida.append(_chequeo(
            "maquina:pausa", "Generación con IA", "aviso",
            f"Generación PAUSADA por consumo del día en {len(gateadas)} cuenta(s): {detalle_cuentas}. "
            "Las marcas de esa(s) cuenta(s) no encolan ni ejecutan nada nuevo.",
            admin=False,
            siguiente_paso="Un administrador puede aceptar +10% en el Monitor (Economía) para reanudar la cuenta afectada.",
        ))
    else:
        salida.append(_chequeo(
            "maquina:pausa", "Generación con IA", "ok",
            "Generación activa (kill switch apagado).",
            admin=False,
        ))
    return salida


def _chequeo_daemons() -> dict:
    """Daemons de fondo: error SOLO si uno que deberia correr no late.

    El juicio por daemon es de `api_sistema.sonda_daemons` (fuente unica, la misma
    del panel Sistema): "inactivo" = apagado por su toggle/ajuste — sin latido de
    barrido es lo ESPERADO, no un problema (se menciona como informacion en el ok);
    "atrasado" = deberia estar activo y no late (hilo muerto o proceso caido).
    """
    try:
        sonda = api_sistema.sonda_daemons()
    except Exception:  # noqa: BLE001 -- sonda defensiva
        sonda = {"daemons": [], "error": "No se pudieron leer los latidos de los daemons."}
    if sonda.get("error"):
        return _chequeo(
            "maquina:daemons", "Daemons de fondo", "aviso",
            str(sonda["error"]),
            admin=False,
            siguiente_paso="Comprueba que la base de datos responde y recarga el diagnóstico.",
        )
    daemons = sonda.get("daemons") or []
    atrasados = [str(d.get("daemon", "?")) for d in daemons if d.get("estado") == "atrasado"]
    con_error = [str(d.get("daemon", "?")) for d in daemons if d.get("estado") == "error"]
    inactivos = sum(1 for d in daemons if d.get("estado") == "inactivo")
    # "en_espera" = interruptor propio ON pero la máquina apagada: no corre, pero NO es un fallo
    # (igual que "inactivo", se menciona como información en el ok, no dispara aviso/error).
    en_espera = sum(1 for d in daemons if d.get("estado") == "en_espera")
    if atrasados:
        return _chequeo(
            "maquina:daemons", "Daemons de fondo", "error",
            f"Sin latido (hilo muerto o proceso caído): {', '.join(atrasados)}.",
            admin=False,
            siguiente_paso=(
                "Revisa los logs del servicio `daemons` en el servidor y reinícialo "
                "si el proceso está caído."
            ),
        )
    if con_error:
        return _chequeo(
            "maquina:daemons", "Daemons de fondo", "aviso",
            f"Último barrido en error: {', '.join(con_error)}.",
            admin=False,
            siguiente_paso="Mira el detalle del barrido en el panel Sistema (sección Daemons).",
        )
    activos = len(daemons) - inactivos - en_espera
    if not daemons:
        detalle = "Sin daemons registrados todavía (ninguno ha latido)."
    else:
        detalle = f"{activos} daemon(s) latiendo con normalidad."
        if inactivos:
            detalle += f" {inactivos} apagado(s) por ajuste (no es un problema)."
        if en_espera:
            detalle += f" {en_espera} en espera de la máquina (no es un problema)."
    return _chequeo("maquina:daemons", "Daemons de fondo", "ok", detalle, admin=False)


def _chequeos_maquina() -> list[dict]:
    """Chequeos de la maquina de contenido (cola, presupuesto, pausa, daemons)."""
    return [_chequeo_cola(), *_chequeos_presupuesto(), _chequeo_daemons()]


# --------------------------------------------------------------------------- #
# Chequeos de INFRAESTRUCTURA (admin=True: su remedio es de operador)          #
# --------------------------------------------------------------------------- #


def _chequeo_disco() -> dict:
    """Uso de disco de los volumenes relevantes (umbral compartido con el panel Sistema)."""
    try:
        discos = api_sistema._discos()
    except Exception:  # noqa: BLE001 -- sonda defensiva
        return _chequeo(
            "infra:disco", "Espacio en disco", "aviso",
            "No se pudo medir el uso de disco.",
            admin=True,
            siguiente_paso="Revisa el panel Sistema (recursos) y el estado de la máquina.",
        )
    llenos = [d for d in discos if d["porcentaje"] >= api_sistema.UMBRAL_DISCO_AVISO_PCT]
    criticos = [d for d in discos if d["porcentaje"] >= api_sistema.UMBRAL_DISCO_ERROR_PCT]
    if llenos:
        detalle = "; ".join(
            f"disco «{d['etiqueta']}» al {d['porcentaje']:.0f}%" for d in llenos
        )
        return _chequeo(
            "infra:disco", "Espacio en disco",
            "error" if criticos else "aviso",
            detalle[:1].upper() + detalle[1:] + ".",
            admin=True,
            siguiente_paso="Libera espacio en ese volumen (media vieja, backups, logs) o amplíalo.",
        )
    resumen = ", ".join(f"{d['etiqueta']} {d['porcentaje']:.0f}%" for d in discos)
    return _chequeo(
        "infra:disco", "Espacio en disco", "ok",
        f"Uso dentro del umbral ({resumen})." if resumen else "Sin volúmenes que medir.",
        admin=True,
    )


def _chequeo_backups() -> dict:
    """Backups locales del host: error si el ultimo fallo; aviso si >26h sin dump."""
    try:
        sonda = api_sistema.sonda_backups()
    except Exception:  # noqa: BLE001 -- sonda defensiva
        sonda = {"configurado": False, "estado": None, "atrasado": False}
    if not sonda.get("configurado"):
        return _chequeo(
            "infra:backups", "Backups locales", "ok",
            "Sin backups locales configurados en esta máquina (normal fuera de hosted).",
            admin=True,
        )
    paso = "Revisa el timer keni-backup del host (journalctl) y su estado.json, y relanza el backup."
    est = sonda.get("estado")
    if isinstance(est, dict) and not est.get("ok", True):
        return _chequeo(
            "infra:backups", "Backups locales", "error",
            f"El último backup FALLÓ en «{est.get('paso') or '?'}».",
            admin=True,
            siguiente_paso=paso,
        )
    if sonda.get("atrasado"):
        return _chequeo(
            "infra:backups", "Backups locales", "aviso",
            "Backup atrasado: más de 26 h sin un dump nuevo.",
            admin=True,
            siguiente_paso=paso,
        )
    return _chequeo(
        "infra:backups", "Backups locales", "ok",
        "Backups al día (hay dump de las últimas 26 h).",
        admin=True,
    )


def _chequeo_s3() -> dict:
    """Salud del object storage (S3/Garage): solo head_bucket, sin medir uso."""
    try:
        sonda = api_sistema.sonda_s3_salud()
    except Exception:  # noqa: BLE001 -- sonda defensiva
        sonda = {"configurado": True, "salud": "err", "error": None}
    if not sonda.get("configurado"):
        return _chequeo(
            "infra:s3", "Almacenamiento S3", "ok",
            "Sin object storage cableado: la media vive en disco local.",
            admin=True,
        )
    if sonda.get("salud") != "ok":
        return _chequeo(
            "infra:s3", "Almacenamiento S3", "error",
            sonda.get("error") or "El almacenamiento S3 no responde (error de salud).",
            admin=True,
            siguiente_paso="Prueba la conexión en Sistema → Almacenamiento y revisa endpoint/credenciales.",
        )
    return _chequeo(
        "infra:s3", "Almacenamiento S3", "ok",
        "El object storage (S3/Garage) responde.",
        admin=True,
    )


def _chequeos_infra() -> list[dict]:
    """Chequeos de infraestructura (disco, backups, S3)."""
    return [_chequeo_disco(), _chequeo_backups(), _chequeo_s3()]


# --------------------------------------------------------------------------- #
# Chequeo de METRICAS (Metricool por marca, admin=True)                        #
# --------------------------------------------------------------------------- #

# Donde se arregla una conexion de Metricool en la UI (ruta real del drawer).
_PASO_METRICOOL = (
    "Conéctala en Monitor → Ajustes → Conexiones (credencial de Metricool por marca)."
)


def _chequeo_metricool() -> dict:
    """Conexion de metricas: marcas del catalogo conectadas a Metricool.

    MISMA fuente y MISMO juicio que `GET /api/conexiones/metricool`
    (`api_conexiones.estado_marcas_metricool`): una marca esta conectada si tiene
    `user_token` + `user_id` + `blog_id` reales en el config de metricas. Sin
    conexiones es AVISO (las metricas no cargaran); con alguna marca suelta, aviso
    nombrandola. Un config ilegible es ERROR (hay algo roto que arreglar).
    """
    try:
        marcas = api_conexiones.estado_marcas_metricool()
    except Exception:  # noqa: BLE001 -- config corrupto/ilegible: chequeo en error, nunca 500
        return _chequeo(
            "metricas:metricool", "Métricas (Metricool)", "error",
            "No se pudo leer la configuración de métricas (config.toml ilegible o corrupto).",
            admin=True,
            siguiente_paso=(
                "Revisa el config.toml de keni-metricas en el volumen de datos o "
                "re-guarda una conexión en Monitor → Ajustes → Conexiones."
            ),
        )
    total = len(marcas)
    conectadas = [m for m in marcas if m.get("conectado")]
    sueltas = [str(m.get("etiqueta") or m.get("marca")) for m in marcas if not m.get("conectado")]
    if total == 0:
        return _chequeo(
            "metricas:metricool", "Métricas (Metricool)", "aviso",
            "No hay marcas en el catálogo: nada que conectar a Metricool.",
            admin=True,
            siguiente_paso="Da de alta las marcas en el catálogo (keni-shared) y reinicia el servicio.",
        )
    if not conectadas:
        return _chequeo(
            "metricas:metricool", "Métricas (Metricool)", "aviso",
            f"Ninguna de las {total} marcas del catálogo está conectada a Metricool: las métricas no cargarán.",
            admin=True,
            siguiente_paso=_PASO_METRICOOL,
        )
    if sueltas:
        return _chequeo(
            "metricas:metricool", "Métricas (Metricool)", "aviso",
            f"{len(conectadas)} de {total} marcas conectadas a Metricool; sin conexión: {', '.join(sueltas)}.",
            admin=True,
            siguiente_paso=_PASO_METRICOOL,
        )
    return _chequeo(
        "metricas:metricool", "Métricas (Metricool)", "ok",
        f"Metricool conectado: {total} de {total} marcas del catálogo.",
        admin=True,
    )


# --------------------------------------------------------------------------- #
# Resumen global + endpoint                                                    #
# --------------------------------------------------------------------------- #


def _resumen_global(chequeos: list[dict]) -> str:
    """Una frase de cabecera, en lenguaje no tecnico, segun el estado global."""
    errores = sum(1 for c in chequeos if c["estado"] == "error")
    avisos = sum(1 for c in chequeos if c["estado"] == "aviso")
    if errores:
        return (
            f"Hay {errores} problema(s) que requieren atención. "
            "Revisa los chequeos marcados de abajo."
        )
    if avisos:
        return f"Sistema operativo, con {avisos} aviso(s) que conviene mirar."
    return "Todo en orden: la consola opera con normalidad."


def _cierre_global(chequeos: list[dict]) -> str:
    """El "que hacer ahora" de cabecera: remite al paso accionable de cada chequeo."""
    if any(c["estado"] != "ok" for c in chequeos):
        return (
            "Qué hacer ahora: cada chequeo marcado trae su siguiente paso; "
            "empieza por los errores."
        )
    return "Qué hacer ahora: nada, todos los chequeos están en orden."


async def estado(request: Request) -> Response:
    try:
        chequeos = _chequeos_maquina() + _chequeos_infra() + [_chequeo_metricool()]
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo al cliente
        return JSONResponse(
            {"error": "No se pudo ejecutar el autodiagnóstico. Vuelve a intentarlo en un momento."},
            status_code=500,
        )
    return JSONResponse(
        {
            "resultados": chequeos,
            "resumen": _resumen_global(chequeos),
            "siguiente_paso": _cierre_global(chequeos),
        }
    )


RUTAS = [Route("/api/estado", estado)]
