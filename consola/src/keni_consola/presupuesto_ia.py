"""Economia de tokens de la generacion: presupuesto diario, corte automatico y kill switch.

POR QUE EXISTE: la generacion corre `claude -p` con la MISMA suscripcion que usa el equipo
a diario (OAuth, ADR 0001). Una ráfaga de noticias puede saturar la cola de jobs de fondo
y AGOTAR los tokens de todos sin que nadie lo vea venir. Este modulo es el guardian:

  - LEDGER: cada generacion CERRADA (terminal) deja su gasto en la tabla `gasto_ia`
    (Postgres, UPSERT por gen_id = idempotente ante reintentos/re-encolados). Lo escribe el
    hook de cierre del almacen de generaciones (`generaciones._almacen`), asi cubre TODOS
    los caminos (claude, imagen, procesos) sin tocar cada lanzador.
  - PRESUPUESTO: el corte GLOBAL es el cap de COSTE en USD por dia UTC (`KENI_PRESUPUESTO_USD_DIA`,
    mejor proxy del gasto: un token de input cacheado pesa mucho menos que uno de salida); 0 =
    apagado. Los topes de TOKENS son POR MOTOR (entrada/salida, ADR 0011) y cortan SOLO su motor.
    El "presupuesto global de tokens" que expone `estado()` es la SUMA informativa de esos 4 topes,
    sin enforcement propio. Editables EN CALIENTE via el store de ajustes (compartido
    back/worker/daemons por /data).
  - CORTE AUTOMATICO en dos escalones (gradual):
      * gastado >= presupuesto            -> SOLO_MANUAL: el fondo (pipeline/autogen) se
        deja de encolar y de reclamar; lo manual del equipo sigue.
      * gastado >= presupuesto * (1+m%)   -> AGOTADO: corte TOTAL (tampoco manual). El
        margen `m` es `KENI_PRESUPUESTO_MARGEN_MANUAL` (def 20%).
  - KILL SWITCH humano: `KENI_GENERACION_PAUSADA` (toggle del Monitor) -> PAUSADO: no se
    encola nada y el worker no reclama nada; lo que corre termina y lo encolado espera.

QUIEN PREGUNTA: `cola.encolar` (gate de admision, excepciones 429 claras), `worker._bucle`
(gate de reclamo: la ráfaga YA encolada tambien se corta) y la API del monitor
(`/api/actividad/cola` expone `estado()` para humanos y agentes).

CACHE: el worker pregunta en cada iteracion del bucle y el SUM del dia en Postgres no es
gratis. `nivel()`/`estado()` cachean la lectura unos segundos (`_CACHE_TTL_S`); el cierre de
una generacion invalida la cache local (la de OTROS procesos caduca sola por TTL: un corte
puede tardar ese puñado de segundos extra en propagarse, irrelevante a esta escala).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from . import config, gate_diario, ruteo_cuentas
from .tiempo import ahora_iso

_log = logging.getLogger("keni_consola.presupuesto_ia")

# Niveles de corte, de mas abierto a mas cerrado. CONTRATO con el monitor/los agentes.
NIVEL_NORMAL = "normal"            # todo corre
NIVEL_SOLO_MANUAL = "solo_manual"  # presupuesto agotado: el fondo se corta, lo manual sigue
NIVEL_AGOTADO = "agotado"          # presupuesto + margen superados: corte TOTAL
NIVEL_PAUSADO = "pausado"          # kill switch humano: corte TOTAL inmediato

# TTL de la cache del gasto del dia (s). El worker sondea en cada iteracion del bucle;
# unos segundos de cache recortan el QPS contra Postgres sin retrasar el corte de forma
# perceptible (el gasto solo crece al CERRARSE generaciones, no token a token).
_CACHE_TTL_S = 3.0

_CACHE_LOCK = threading.Lock()
_CACHE_GASTO: dict[str, Any] | None = None
_CACHE_DIA = ""
_CACHE_EXPIRA = 0.0

# Cache paralela del gasto del dia DESGLOSADO por proceso (motor): la usan el desglose de la
# Economia (`estado().por_proceso`) y el corte por motor (`nivel_proceso`). Mismo TTL/criterio
# best-effort que `_gasto_hoy`.
_CACHE_PROC_GASTO: dict[str, dict[str, Any]] | None = None
_CACHE_PROC_DIA = ""
_CACHE_PROC_EXPIRA = 0.0

# Motores de la maquina (ADR 0011). Literales aqui para no acoplar este modulo al paquete
# `generaciones` (que lo importa); casan con `generaciones.PROCESO_*` y las claves del ledger.
PROCESO_INVESTIGACION = "investigacion"
PROCESO_PRODUCCION = "produccion"

# Ultimo nivel observado por ESTE proceso: cada TRANSICION deja un log WARNING (entrar en
# corte) o INFO (volver a normal) — la señal operativa que consume la observabilidad (los
# gates en si son silenciosos: rechazan/esperan sin loguear por peticion).
_ULTIMO_NIVEL: str | None = None


def _hoy_utc() -> str:
    """Dia UTC actual (YYYY-MM-DD), el bucket del presupuesto."""
    return ahora_iso()[:10]


# Segundos de un dia completo, base de la fraccion del dia transcurrida.
_SEGUNDOS_DIA = 86400


def _fraccion_dia_utc() -> float:
    """Fraccion del dia UTC de HOY ya transcurrida (0.0 a 1.0).

    Misma nocion de "hoy" que `_hoy_utc`/`_gasto_hoy` (dia UTC via `ahora_iso`), para que la
    proyeccion case con el bucket del gasto. Se deriva del timestamp ISO canonico (HH:MM:SS),
    asi parchear `ahora_iso` en tests fija tambien la fraccion.
    """
    hms = ahora_iso()[11:19]  # "HH:MM:SS" del canon UTC
    try:
        h, m, s = (int(p) for p in hms.split(":"))
    except (ValueError, TypeError):
        return 0.0
    return (h * 3600 + m * 60 + s) / _SEGUNDOS_DIA


def invalidar_cache() -> None:
    """Invalida la cache del gasto (global y por proceso) y el nivel observado.

    La llaman el cierre de cada generacion y los tests.
    """
    global _CACHE_EXPIRA, _CACHE_PROC_EXPIRA, _ULTIMO_NIVEL
    with _CACHE_LOCK:
        _CACHE_EXPIRA = 0.0
        _CACHE_PROC_EXPIRA = 0.0
        _ULTIMO_NIVEL = None


def _gasto_hoy(marca: str = "") -> dict[str, Any]:
    """Gasto agregado del dia UTC actual, cacheado `_CACHE_TTL_S` segundos.

    `marca` ("" = GLOBAL, agregado de todas; un id = solo esa marca, para el corte POR MARCA). El
    camino GLOBAL (la mayoria de lecturas: gate del worker, nivel global) usa la cache; una marca
    concreta se lee SIN cache (lecturas acotadas, sobre todo de la UI y de la admision de esa
    marca): asi no multiplicamos la cache por marca ni arriesgamos servir el gasto de otra.

    Best-effort: si Postgres no responde, devuelve el ultimo valor cacheado (global) o un gasto
    vacio. PREFERIMOS NO CORTAR ante un blip de la BD: el presupuesto es un guardian de economia,
    no un cinturon de seguridad funcional; un falso corte pararia la maquina entera por un parpadeo.
    """
    global _CACHE_GASTO, _CACHE_DIA, _CACHE_EXPIRA
    dia = _hoy_utc()
    if not marca:
        with _CACHE_LOCK:
            if _CACHE_GASTO is not None and _CACHE_DIA == dia and time.monotonic() < _CACHE_EXPIRA:
                return _CACHE_GASTO
    from . import repos

    try:
        gasto = repos.gasto_ia_del_dia(dia, marca)
    except Exception:  # noqa: BLE001 -- blip de BD: no cortar por un fallo de lectura
        _log.warning("presupuesto_ia: fallo al leer el gasto del dia", exc_info=True)
        if not marca:
            with _CACHE_LOCK:
                if _CACHE_GASTO is not None and _CACHE_DIA == dia:
                    return _CACHE_GASTO
        return {"tokens": 0, "tokens_in": 0, "tokens_out": 0, "coste_usd": 0.0, "generaciones": 0}
    if not marca:
        with _CACHE_LOCK:
            _CACHE_GASTO = gasto
            _CACHE_DIA = dia
            _CACHE_EXPIRA = time.monotonic() + _CACHE_TTL_S
    return gasto


def _gasto_vacio_por_proceso() -> dict[str, dict[str, Any]]:
    """Desglose por proceso a CEROS (ambos motores presentes). Forma de respaldo ante blip de BD."""
    cero = {"tokens_in": 0, "tokens_out": 0, "tokens": 0, "coste_usd": 0.0, "generaciones": 0}
    return {PROCESO_INVESTIGACION: dict(cero), PROCESO_PRODUCCION: dict(cero)}


def _gasto_por_proceso_hoy(marca: str = "") -> dict[str, dict[str, Any]]:
    """Gasto del dia UTC actual DESGLOSADO por proceso, cacheado `_CACHE_TTL_S` segundos.

    Mismo criterio best-effort y mismo trato de `marca` que `_gasto_hoy`: el camino GLOBAL ("")
    usa la cache; una marca concreta se lee sin cache. Garantiza siempre los dos motores
    (`investigacion`/`produccion`).
    """
    global _CACHE_PROC_GASTO, _CACHE_PROC_DIA, _CACHE_PROC_EXPIRA
    dia = _hoy_utc()
    if not marca:
        with _CACHE_LOCK:
            if (
                _CACHE_PROC_GASTO is not None
                and _CACHE_PROC_DIA == dia
                and time.monotonic() < _CACHE_PROC_EXPIRA
            ):
                return _CACHE_PROC_GASTO
    from . import repos

    try:
        gasto = repos.gasto_ia_del_dia_por_proceso(dia, marca)
    except Exception:  # noqa: BLE001 -- blip de BD: no cortar por un fallo de lectura
        _log.warning("presupuesto_ia: fallo al leer el gasto por proceso del dia", exc_info=True)
        if not marca:
            with _CACHE_LOCK:
                if _CACHE_PROC_GASTO is not None and _CACHE_PROC_DIA == dia:
                    return _CACHE_PROC_GASTO
        return _gasto_vacio_por_proceso()
    if not marca:
        with _CACHE_LOCK:
            _CACHE_PROC_GASTO = gasto
            _CACHE_PROC_DIA = dia
            _CACHE_PROC_EXPIRA = time.monotonic() + _CACHE_TTL_S
    return gasto


def _topes_motor(proceso: str) -> tuple[int, int]:
    """Topes DIARIOS GLOBALES (in, out) de tokens del motor (env); 0 = sin limite en ese lado."""
    if proceso == PROCESO_INVESTIGACION:
        return (
            config.presupuesto_tokens_investigacion_in_dia(),
            config.presupuesto_tokens_investigacion_out_dia(),
        )
    if proceso == PROCESO_PRODUCCION:
        return (
            config.presupuesto_tokens_produccion_in_dia(),
            config.presupuesto_tokens_produccion_out_dia(),
        )
    return (0, 0)


def _topes_motor_marca(proceso: str, marca: str) -> tuple[int, int]:
    """Topes DIARIOS (in, out) de tokens PROPIOS de una marca para el motor; 0 = sin tope de marca.

    Análogo por-marca de `_topes_motor`: independientes del global, el corte toma el MÁS
    restrictivo entre marca y global (ver `nivel_proceso`)."""
    if not marca:
        return (0, 0)
    if proceso == PROCESO_INVESTIGACION:
        return (
            config.presupuesto_tokens_investigacion_in_dia_marca(marca),
            config.presupuesto_tokens_investigacion_out_dia_marca(marca),
        )
    if proceso == PROCESO_PRODUCCION:
        return (
            config.presupuesto_tokens_produccion_in_dia_marca(marca),
            config.presupuesto_tokens_produccion_out_dia_marca(marca),
        )
    return (0, 0)


def _suma_topes_motor() -> int:
    """SUMA de los 4 topes por motor (investigacion in+out + produccion in+out).

    Es el "presupuesto global de tokens" INFORMATIVO que expone `estado()`: NO corta a nivel global
    (el corte global es solo USD + parada), solo agrega los topes que SI cortan por motor. 0 = todos
    los topes apagados, sin limite de tokens.
    """
    inv_in, inv_out = _topes_motor(PROCESO_INVESTIGACION)
    prod_in, prod_out = _topes_motor(PROCESO_PRODUCCION)
    return inv_in + inv_out + prod_in + prod_out


def _mas_severo(a: str, b: str) -> str:
    """El mas restrictivo de dos niveles (por su severidad creciente)."""
    return a if _SEVERIDAD.get(a, 0) >= _SEVERIDAD.get(b, 0) else b


def _escalon(gastado: float, presupuesto: float, margen: float) -> str:
    """Escalon de corte de UN presupuesto: agotado (>= presup*margen), solo_manual (>= presup) o normal."""
    if gastado >= presupuesto * margen:
        return NIVEL_AGOTADO
    if gastado >= presupuesto:
        return NIVEL_SOLO_MANUAL
    return NIVEL_NORMAL


def nivel(marca: str = "") -> str:
    """Nivel de corte VIGENTE (el kill switch manda; luego el escalon del cap de USD).

    El corte GLOBAL tiene dos escalones (solo_manual / agotado) sobre el cap de COSTE en USD
    (`presupuesto_usd_dia`, mejor proxy del gasto real). En 0 queda apagado: sin cap USD no hay
    corte automatico global (solo `normal`/`pausado`); los topes de tokens por motor cortan aparte
    via `nivel_proceso`. `marca` ("" = global) añade el corte PROPIO de esa marca (su parada de
    emergencia y su cap USD), tomando el MAS restrictivo con el global. La TRANSICION solo se
    loguea para el corte GLOBAL (una marca no debe contaminar la señal operativa global).
    """
    if marca:
        return _nivel_global(marca)
    return _con_transicion(_nivel_global())


def _nivel_global(marca: str = "") -> str:
    """Nivel de corte GLOBAL (kill switch + escalones del cap de USD), SIN log de transicion.

    Lo reusan `nivel()` (que añade el log de transicion) y `nivel_proceso()` (que lo combina con
    el tope del motor). No loguea para que el corte por motor no contamine la señal del global.

    El corte es el cap de COSTE en USD (`presupuesto_usd_dia`) mas la parada manual. `marca`
    ("" = solo global) añade el corte PROPIO de la marca: su parada de emergencia
    (`generacion_pausada_marca`) pausa esa marca igual que la global, y su cap USD
    (`presupuesto_usd_dia_marca`) corta segun el gasto SOLO de esa marca. El nivel devuelto es el
    MAS restrictivo entre global y marca. Los topes de TOKENS por motor cortan via `nivel_proceso`.
    """
    if config.generacion_pausada() or (marca and config.generacion_pausada_marca(marca)):
        return NIVEL_PAUSADO
    # Gate DIARIO por % del limite SEMANAL POR CUENTA: corte TOTAL (auto y manual) de las marcas de
    # una cuenta cuando el consumo del dia de ESA cuenta alcanza su umbral. Solo aplica con `marca`
    # (=> cuenta concreta via `ruteo_cuentas`): asi cae en la ADMISION, donde se conoce la marca, y
    # pausa solo las marcas de la cuenta gateada. Sin marca (gate de reclamo global, jobs sin marca)
    # NO corta por % — no hay cuenta concreta; el kill switch global sigue aparte. Inerte mientras
    # la fuente del % de la cuenta no exista (devuelve False).
    if marca and gate_diario.pausado_por_pct(ruteo_cuentas.cuenta_de_marca(marca)):
        return NIVEL_PAUSADO
    margen = 1 + config.presupuesto_margen_manual_pct() / 100.0
    nivel_vigente = NIVEL_NORMAL
    presupuesto_usd = config.presupuesto_usd_dia()
    if presupuesto_usd > 0:
        gasto = _gasto_hoy()
        nivel_vigente = _escalon(float(gasto.get("coste_usd", 0.0)), presupuesto_usd, margen)
    if marca:
        presupuesto_marca = config.presupuesto_usd_dia_marca(marca)
        if presupuesto_marca > 0:
            gasto_marca = _gasto_hoy(marca)
            nivel_vigente = _mas_severo(
                nivel_vigente,
                _escalon(float(gasto_marca.get("coste_usd", 0.0)), presupuesto_marca, margen),
            )
    return nivel_vigente


def nivel_proceso(proceso: str, marca: str = "") -> str:
    """Nivel de corte EFECTIVO de un motor (investigacion|produccion): el MAS restrictivo.

    Combina el nivel GLOBAL —ya ponderado con el cap/parada de `marca` si viene— con los TOPES de
    tokens del motor, separando ENTRADA y SALIDA. Los topes son de DOS niveles, ambos cortan (el
    más restrictivo): los GLOBALES (ADR 0011, gasto global del motor) y, si viene `marca`, los
    PROPIOS de la marca (gasto del motor SOLO de esa marca). Cada tope en 0 no añade corte por ese
    lado. NO loguea transiciones.
    """
    glob = _nivel_global(marca)
    if glob == NIVEL_PAUSADO:
        return NIVEL_PAUSADO
    margen = 1 + config.presupuesto_margen_manual_pct() / 100.0
    nivel_vigente = glob

    def _aplica(topes: tuple[int, int], gasto: dict[str, Any]) -> None:
        nonlocal nivel_vigente
        tope_in, tope_out = topes
        if tope_in > 0:
            nivel_vigente = _mas_severo(
                nivel_vigente, _escalon(int(gasto.get("tokens_in", 0)), tope_in, margen)
            )
        if tope_out > 0:
            nivel_vigente = _mas_severo(
                nivel_vigente, _escalon(int(gasto.get("tokens_out", 0)), tope_out, margen)
            )

    _aplica(_topes_motor(proceso), _gasto_por_proceso_hoy().get(proceso, {}))
    if marca:
        _aplica(_topes_motor_marca(proceso, marca), _gasto_por_proceso_hoy(marca).get(proceso, {}))
    return nivel_vigente


def bloqueo_admision(
    nivel_actual: str,
    *,
    gasta_tokens: bool,
    es_fondo: bool,
    proceso: str | None = None,
    marca: str | None = None,
) -> str | None:
    """El nivel de corte que BLOQUEA un job con estas características, o None si pasa.

    FUENTE ÚNICA de la regla del presupuesto: la comparten el gate de ADMISIÓN
    (`cola.encolar`, que mapea el nivel devuelto a la excepción 429 correspondiente) y el gate
    de RECLAMO (`worker._bucle`, que la consulta para un job manual y otro de fondo y decide si
    reclamar y con qué prioridad mínima). Así la política vive en UN solo sitio:

      - PAUSADO (kill switch humano): NADA entra/corre, ni manual ni procesos.
      - un job de PROCESO (render ffmpeg / ASR) NO gasta tokens de la suscripción: exento del
        corte por presupuesto (solo lo frena el kill switch).
      - AGOTADO (presupuesto + margen): no pasa NADA que gaste tokens, ni siquiera lo manual.
      - SOLO_MANUAL (presupuesto agotado): el FONDO que gasta tokens cede; lo manual sigue.

    `nivel_actual` es el nivel GLOBAL VIGENTE (`nivel()`), que el llamante calcula UNA vez (para
    no repetir la lectura cacheada del gasto por cada consulta).

    `proceso` (motor del job, si se conoce en el call site): cuando viene y el job GASTA tokens,
    el corte efectivo del job es el MAS restrictivo entre el nivel global y el del motor
    (`nivel_proceso`), de modo que el tope propio del motor tambien corta. Sin `proceso` (o en un
    call site que no lo conoce, p. ej. el gate de reclamo del worker, que decide antes de fijar
    un job concreto) cae al comportamiento GLOBAL de siempre.

    `marca` (marca del job, si se conoce): cuando viene, el corte efectivo añade el control PROPIO
    de esa marca (su parada de emergencia y su cap USD), de nuevo tomando el MAS restrictivo. Así
    la parada/tope de una marca corta su trabajo (fondo y manual) sin tocar al resto. El llamante
    pasa `nivel_actual = nivel(marca)` para que la parte global ya venga ponderada con la marca.
    """
    nivel_efectivo = nivel_actual
    if gasta_tokens and nivel_actual != NIVEL_PAUSADO and (proceso or marca):
        nivel_efectivo = _mas_severo(nivel_actual, nivel_proceso(proceso or "", marca or ""))
    if nivel_efectivo == NIVEL_PAUSADO:
        return NIVEL_PAUSADO
    if not gasta_tokens:
        return None
    if nivel_efectivo == NIVEL_AGOTADO:
        return NIVEL_AGOTADO
    if es_fondo and nivel_efectivo == NIVEL_SOLO_MANUAL:
        return NIVEL_SOLO_MANUAL
    return None


def bloqueo_inline(proceso: str = "", marca: str = "", *, es_fondo: bool = True) -> str | None:
    """El nivel que BLOQUEA una generacion INLINE (sincrona, FUERA de la cola), o None si pasa.

    Mismo gate que la admision de la cola (`bloqueo_admision`), pero para los caminos que
    ejecutan `claude -p` SIN encolar y por tanto NO pasan por `cola.encolar` ni por el reclamo
    del worker: los pasos Haiku del pool de noticias (fusionar, clasificar, priorizar, traducir).
    Sin este gate esos pasos ignorarian la parada de emergencia y los caps de presupuesto.

    `proceso`/`marca` afinan el corte (tope del motor / control de la marca, el mas restrictivo);
    `es_fondo` distingue el trabajo automatico (cede en SOLO_MANUAL) del manual. Calcula `nivel`
    una vez con la marca ya ponderada, igual que hacen los call sites de la cola.
    """
    return bloqueo_admision(
        nivel(marca),
        gasta_tokens=True,
        es_fondo=es_fondo,
        proceso=proceso or None,
        marca=marca or None,
    )


# Severidad creciente de los niveles (para distinguir endurecer de relajar al loguear).
_SEVERIDAD = {NIVEL_NORMAL: 0, NIVEL_SOLO_MANUAL: 1, NIVEL_AGOTADO: 2, NIVEL_PAUSADO: 3}


def _con_transicion(nuevo: str) -> str:
    """Devuelve `nuevo` dejando un log SOLO si el nivel cambio desde la ultima lectura."""
    global _ULTIMO_NIVEL
    with _CACHE_LOCK:
        anterior, _ULTIMO_NIVEL = _ULTIMO_NIVEL, nuevo
    if anterior is None or anterior == nuevo:
        return nuevo
    if _SEVERIDAD.get(nuevo, 0) > _SEVERIDAD.get(anterior, 0):
        _log.warning("presupuesto_ia: corte de generacion %s -> %s", anterior, nuevo)
    else:
        _log.info("presupuesto_ia: generacion reanudada %s -> %s", anterior, nuevo)
    return nuevo


def estado(marca: str = "") -> dict[str, Any]:
    """Snapshot COMPLETO para el monitor/los agentes: presupuesto, gasto del dia y nivel.

    Forma (CONTRATO de `/api/actividad/cola`):
      {marca, nivel, pausada, presupuesto_tokens_dia, presupuesto_usd_dia, margen_manual_pct,
       gastado: {tokens, tokens_in, tokens_out, coste_usd, generaciones}, restante_tokens,
       pct_usado, pct_usado_usd, proyeccion_usd_dia, pct_proyectado_usd, dia,
       por_proceso: {investigacion: {...}, produccion: {...}},
       gate_diario: {cuenta, consumo_hoy_pct, umbral_pct, aceptados_hoy, pausado_por_pct, ...}|None,
       gate_diario_cuentas: {a: {...}, b: {...}}}

    Gate diario por % del limite SEMANAL POR CUENTA: `gate_diario` es el bloque de la CUENTA de esta
    marca (su aviso/aceptar) cuando hay marca; None en vista global. `gate_diario_cuentas` trae las
    DOS cuentas (para el modo "Todas" del UI). Un `pausado_por_pct=True` en la cuenta de la marca es
    la razon de un `nivel == pausado` con `pausada` (kill switch) en False: el UI distingue asi el
    corte por % del kill switch manual.

    `proyeccion_usd_dia` es el coste estimado a fin de dia (coste actual / fraccion del dia UTC
    transcurrida); None al arranque del dia (fraccion <= 1%). `pct_proyectado_usd` es esa
    proyeccion sobre el cap de USD; None sin cap o sin proyeccion.

    `marca` ("" = GLOBAL; un id = vista POR MARCA): con marca, `gastado`/`por_proceso` traen el
    gasto SOLO de esa marca y los controles son los PROPIOS de la marca (su parada, su cap USD y
    sus topes de tokens por motor IN/OUT); `nivel` es el efectivo de la marca (el mas restrictivo
    con el global).

    `presupuesto_tokens_dia` es INFORMATIVO: la SUMA de los 4 topes por motor del ámbito (globales,
    o de la marca en vista de marca); NO corta a nivel global (eso es solo USD + parada).
    `restante_tokens`/`pct_usado` son None si esa suma es 0; `pct_usado_usd` es None sin cap de USD.
    """
    gasto = _gasto_hoy(marca)
    if marca:
        inv = _topes_motor_marca(PROCESO_INVESTIGACION, marca)
        prod = _topes_motor_marca(PROCESO_PRODUCCION, marca)
        presupuesto = inv[0] + inv[1] + prod[0] + prod[1]
    else:
        presupuesto = _suma_topes_motor()
    presupuesto_usd = config.presupuesto_usd_dia_marca(marca) if marca else config.presupuesto_usd_dia()
    gastado = int(gasto.get("tokens", 0))
    coste = float(gasto.get("coste_usd", 0.0))
    restante = max(0, presupuesto - gastado) if presupuesto > 0 else None
    pct = round(100.0 * gastado / presupuesto, 1) if presupuesto > 0 else None
    pct_usd = round(100.0 * coste / presupuesto_usd, 1) if presupuesto_usd > 0 else None
    # Proyeccion de gasto a fin de dia: extrapola el coste actual al dia completo segun la
    # fraccion del dia UTC ya transcurrida. Al arranque del dia (fraccion ~0) NO se proyecta
    # (None): dividir por casi-cero dispararia la cifra a valores absurdos.
    fraccion = _fraccion_dia_utc()
    proyeccion_usd = round(coste / fraccion, 4) if fraccion > 0.01 else None
    pct_proyectado_usd = (
        round(100.0 * proyeccion_usd / presupuesto_usd, 1)
        if proyeccion_usd is not None and presupuesto_usd > 0
        else None
    )
    gasto_proc = _gasto_por_proceso_hoy(marca)
    return {
        "marca": marca,
        "nivel": nivel(marca),
        "pausada": config.generacion_pausada_marca(marca) if marca else config.generacion_pausada(),
        "presupuesto_tokens_dia": presupuesto,
        "presupuesto_usd_dia": presupuesto_usd,
        "margen_manual_pct": config.presupuesto_margen_manual_pct(),
        "gastado": gasto,
        "restante_tokens": restante,
        "pct_usado": pct,
        "pct_usado_usd": pct_usd,
        "proyeccion_usd_dia": proyeccion_usd,
        "pct_proyectado_usd": pct_proyectado_usd,
        "dia": _hoy_utc(),
        "por_proceso": {
            PROCESO_INVESTIGACION: _bloque_proceso(PROCESO_INVESTIGACION, gasto_proc, marca),
            PROCESO_PRODUCCION: _bloque_proceso(PROCESO_PRODUCCION, gasto_proc, marca),
        },
        # Gate diario por % POR CUENTA: `gate_diario` es el bloque de la cuenta de ESTA marca (su
        # aviso/aceptar) cuando hay marca; None en vista global (sin cuenta concreta).
        # `gate_diario_cuentas` trae las DOS cuentas (estado_todas) para el modo "Todas" del UI.
        "gate_diario": gate_diario.estado(ruteo_cuentas.cuenta_de_marca(marca)) if marca else None,
        "gate_diario_cuentas": gate_diario.estado_todas(),
    }


def _bloque_proceso(
    proceso: str, gasto_proc: dict[str, dict[str, Any]], marca: str = ""
) -> dict[str, Any]:
    """Bloque `por_proceso[<motor>]` de `estado()`: gasto desglosado + topes in/out + nivel del motor.

    Los topes son los del ÁMBITO: en vista global los del motor (ADR 0011); en vista POR MARCA los
    PROPIOS de la marca (`KENI_PRESUPUESTO_TOKENS_<MOTOR>_<IN|OUT>_DIA::<marca>`), con su gasto y %.
    """
    g = gasto_proc.get(proceso, {})
    tin = int(g.get("tokens_in", 0))
    tout = int(g.get("tokens_out", 0))
    tokens = int(g.get("tokens", tin + tout))
    tope_in, tope_out = _topes_motor_marca(proceso, marca) if marca else _topes_motor(proceso)
    restante_in = max(0, tope_in - tin) if tope_in > 0 else None
    pct_in = round(100.0 * tin / tope_in, 1) if tope_in > 0 else None
    restante_out = max(0, tope_out - tout) if tope_out > 0 else None
    pct_out = round(100.0 * tout / tope_out, 1) if tope_out > 0 else None
    return {
        "tokens_in": tin,
        "tokens_out": tout,
        "tokens": tokens,
        "coste_usd": float(g.get("coste_usd", 0.0)),
        "generaciones": int(g.get("generaciones", 0)),
        "presupuesto_tokens_in_dia": tope_in,
        "presupuesto_tokens_out_dia": tope_out,
        "restante_in": restante_in,
        "pct_in": pct_in,
        "restante_out": restante_out,
        "pct_out": pct_out,
        "nivel": nivel_proceso(proceso, marca),
    }


def registrar_cierre(registro: dict[str, Any]) -> None:
    """Vuelca al ledger el gasto de una generacion CERRADA (la llama el hook del almacen).

    Extrae tokens/coste de `registro["metricas"]` (los acumula el runner desde el stream de
    `claude`; los jobs de imagen/proceso no los traen y NO dejan fila: no gastan tokens de
    la suscripcion). Best-effort: nunca propaga (el cierre del job no debe fallar por el
    ledger). El `dia` es el del CIERRE (cuando se gasto), no el del encolado.
    """
    gen_id = str(registro.get("id") or "")
    metricas = registro.get("metricas")
    if not gen_id or not isinstance(metricas, dict):
        return
    try:
        tokens_in = int(metricas.get("tokens_in") or 0)
        tokens_out = int(metricas.get("tokens_out") or 0)
        coste = float(metricas.get("total_cost_usd") or 0.0)
    except (TypeError, ValueError):
        return
    # Modelo concreto que gasto (lo sella el lanzador de imagen en `metricas.modelo`; en
    # claude viaja por su propia via). Permite estimar el coste medio por imagen POR MODELO.
    modelo = str(metricas.get("modelo") or "")
    if tokens_in <= 0 and tokens_out <= 0 and coste <= 0:
        return  # sin consumo medible (imagen/proceso/fallo temprano): no ensuciar el ledger
    dia = (str(registro.get("fecha_fin") or "") or ahora_iso())[:10]
    from . import repos

    try:
        prompt_chars = int(registro.get("prompt_chars") or 0)
    except (TypeError, ValueError):
        prompt_chars = 0
    # Prompt caching (mide el ahorro): tokens de cache leidos/creados del run. La mayoria no los
    # trae (=> 0); se vuelcan al ledger para poder agregar el ahorro por dia.
    try:
        cache_read = int(metricas.get("cache_read") or 0)
        cache_creation = int(metricas.get("cache_creation") or 0)
    except (TypeError, ValueError):
        cache_read = cache_creation = 0
    # Proceso de la maquina (ADR 0011): prefiere el sellado del registro y, si falta, lo deduce
    # de tipo/etiqueta (`proceso_de`). Asi el ledger separa el gasto de investigacion vs produccion.
    from .generaciones import proceso_de

    proceso = proceso_de(registro)
    try:
        repos.registrar_gasto_ia(
            gen_id,
            dia=dia,
            tipo=str(registro.get("tipo") or ""),
            marca=str(registro.get("marca") or ""),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            coste_usd=coste,
            prompt_chars=prompt_chars,
            cache_read=cache_read,
            cache_creation=cache_creation,
            modelo=modelo,
            proceso=proceso,
            # ETAPA explicita si el registro la trae (fases inline del pool, que comparten
            # tipo='pipeline'); vacio => la economia la deriva de tipo/proceso.
            etapa=str(registro.get("etapa") or ""),
        )
    except Exception:  # noqa: BLE001 -- el ledger nunca debe romper el cierre de un job
        _log.warning("presupuesto_ia: fallo al registrar el gasto de %s", gen_id, exc_info=True)
        return
    invalidar_cache()
