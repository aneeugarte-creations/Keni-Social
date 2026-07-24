"""Config — accesores del dominio jobs. Parte de config.py (ver barrel)."""
from __future__ import annotations

from ._comun import (
    _VERDADEROS,
    ENV_CUENTA_AVISO_CADUCIDAD_H,
    ENV_GASTO_IA_RETENCION_DIAS,
    ENV_GATE_METER_STALE_H,
    ENV_GENERACION_PAUSADA,
    ENV_JOBS_MAX_INTENTOS,
    ENV_MAX_JOBS,
    ENV_PRESUPUESTO_MARGEN_MANUAL,
    ENV_PRESUPUESTO_TOKENS_INVESTIGACION_IN_DIA,
    ENV_PRESUPUESTO_TOKENS_INVESTIGACION_OUT_DIA,
    ENV_PRESUPUESTO_TOKENS_PRODUCCION_IN_DIA,
    ENV_PRESUPUESTO_TOKENS_PRODUCCION_OUT_DIA,
    ENV_PRESUPUESTO_USD_DIA,
    ENV_PROMPT_AVISO_CHARS,
    ENV_PROMPT_MAX_CHARS,
    ENV_WORKER_CARRILES,
    ENV_WORKER_EXTERNO,
    ENV_WORKER_SONDEO_SEGUNDOS,
    CUENTA_AVISO_CADUCIDAD_H_DEF,
    GASTO_IA_RETENCION_DIAS_DEF,
    GATE_METER_STALE_H_DEF,
    JOBS_MAX_INTENTOS_DEF,
    MAX_JOBS_DEF,
    PRESUPUESTO_MARGEN_MANUAL_DEF,
    PRESUPUESTO_TOKENS_INVESTIGACION_IN_DIA_DEF,
    PRESUPUESTO_TOKENS_INVESTIGACION_OUT_DIA_DEF,
    PRESUPUESTO_TOKENS_PRODUCCION_IN_DIA_DEF,
    PRESUPUESTO_TOKENS_PRODUCCION_OUT_DIA_DEF,
    PRESUPUESTO_USD_DIA_DEF,
    PROMPT_AVISO_CHARS_DEF,
    PROMPT_MAX_CHARS_DEF,
    WORKER_SONDEO_SEGUNDOS_DEF,
    _crudo,
    _entero,
)

# --------------------------------------------------------------------------- #
# Accesores: concurrencia de jobs                                              #
# --------------------------------------------------------------------------- #


def max_jobs() -> int:
    """Maximo de jobs `claude` simultaneos (`KENI_MAX_JOBS`, def 4, minimo 1).

    Es el UNICO limite de la cola: cuantos `claude -p` corren a la vez. La cola NO tiene
    tope (R-NO-LIMIT); los jobs que no caben simplemente ESPERAN un slot, nada se rechaza
    por tamano de cola. El tope voluntario de presupuesto/pausa vive aparte (`presupuesto_ia`).
    """
    return _entero(ENV_MAX_JOBS, MAX_JOBS_DEF, minimo=1)


# --------------------------------------------------------------------------- #
# Accesores: economia de tokens (presupuesto diario + kill switch)             #
# --------------------------------------------------------------------------- #
#
# La generacion corre `claude -p` con la MISMA suscripcion que usa el equipo a diario: una
# rafaga de jobs de fondo puede agotar los tokens de TODOS sin que nadie lo vea venir.
# Estos knobs (editables en caliente via el store de ajustes) gobiernan el corte automatico
# (`presupuesto_ia.py`) y la pausa manual de la generacion. Todos se leen EN CALIENTE.


def presupuesto_tokens_investigacion_in_dia() -> int:
    """Tope DIARIO de tokens de ENTRADA del motor de INVESTIGACION (`KENI_PRESUPUESTO_TOKENS_INVESTIGACION_IN_DIA`, def 0).

    Tokens de input del dia UTC de las generaciones de investigacion. `0` = SIN limite. El corte
    efectivo del motor es el MAS restrictivo de su tope IN, su tope OUT y el cap global de USD
    (ver `presupuesto_ia.nivel_proceso`).
    """
    return _entero(ENV_PRESUPUESTO_TOKENS_INVESTIGACION_IN_DIA, PRESUPUESTO_TOKENS_INVESTIGACION_IN_DIA_DEF, minimo=0)


def presupuesto_tokens_investigacion_out_dia() -> int:
    """Tope DIARIO de tokens de SALIDA del motor de INVESTIGACION (`KENI_PRESUPUESTO_TOKENS_INVESTIGACION_OUT_DIA`, def 0).

    Tokens de output del dia UTC de las generaciones de investigacion. `0` = SIN limite. El corte
    efectivo del motor es el MAS restrictivo de su tope IN, su tope OUT y el cap global de USD
    (ver `presupuesto_ia.nivel_proceso`).
    """
    return _entero(ENV_PRESUPUESTO_TOKENS_INVESTIGACION_OUT_DIA, PRESUPUESTO_TOKENS_INVESTIGACION_OUT_DIA_DEF, minimo=0)


def presupuesto_tokens_produccion_in_dia() -> int:
    """Tope DIARIO de tokens de ENTRADA del motor de PRODUCCION (`KENI_PRESUPUESTO_TOKENS_PRODUCCION_IN_DIA`, def 0).

    Tokens de input del dia UTC de las generaciones de produccion. `0` = SIN limite. El corte
    efectivo del motor es el MAS restrictivo de su tope IN, su tope OUT y el cap global de USD
    (ver `presupuesto_ia.nivel_proceso`).
    """
    return _entero(ENV_PRESUPUESTO_TOKENS_PRODUCCION_IN_DIA, PRESUPUESTO_TOKENS_PRODUCCION_IN_DIA_DEF, minimo=0)


def presupuesto_tokens_produccion_out_dia() -> int:
    """Tope DIARIO de tokens de SALIDA del motor de PRODUCCION (`KENI_PRESUPUESTO_TOKENS_PRODUCCION_OUT_DIA`, def 0).

    Tokens de output del dia UTC de las generaciones de produccion. `0` = SIN limite. El corte
    efectivo del motor es el MAS restrictivo de su tope IN, su tope OUT y el cap global de USD
    (ver `presupuesto_ia.nivel_proceso`).
    """
    return _entero(ENV_PRESUPUESTO_TOKENS_PRODUCCION_OUT_DIA, PRESUPUESTO_TOKENS_PRODUCCION_OUT_DIA_DEF, minimo=0)


def presupuesto_usd_dia() -> float:
    """Presupuesto DIARIO de coste en USD de generacion (`KENI_PRESUPUESTO_USD_DIA`, def 0).

    Suma de `coste_usd` (ya calculado por job con tarifas correctas) de todas las generaciones
    cerradas en el dia UTC. `0` = SIN limite (corte por USD apagado; el corte por tokens y el
    kill switch manual siguen). Mejor proxy del gasto real que el conteo de tokens: pondera
    input/output/cache por su tarifa en vez de sumarlos con peso igual.
    """
    crudo = _crudo(ENV_PRESUPUESTO_USD_DIA)
    if not crudo:
        return PRESUPUESTO_USD_DIA_DEF
    try:
        valor = float(crudo)
    except ValueError:
        return PRESUPUESTO_USD_DIA_DEF
    return max(0.0, valor)


def gate_medidor_caducidad_h() -> int:
    """Horas de CADUCIDAD del medidor `/usage` para el gate diario (`KENI_GATE_METER_STALE_H`, def 6).

    Si la ultima lectura VALIDA del medidor de una cuenta es mas vieja que este plazo, el gate
    diario (`gate_diario.pausado_por_pct`) corta el FONDO de esa cuenta (fail-closed): sin medidor
    fiable no hay forma de saber cuanto cupo queda, y seguir generando a ciegas puede agotar la
    suscripcion. `0` = apagado (comportamiento legado: sin dato el gate no corta). La recuperacion
    es automatica en cuanto el muestreo vuelve a dejar una lectura fresca. Editable en caliente
    (store de ajustes > env > defecto).
    """
    return _entero(ENV_GATE_METER_STALE_H, GATE_METER_STALE_H_DEF, minimo=0)


def cuenta_aviso_caducidad_h() -> int:
    """Antelacion (h) del aviso de credencial por caducar (`KENI_CUENTA_AVISO_CADUCIDAD_H`, def 2).

    Con la credencial de una cuenta de Claude a menos de este plazo de caducar, el muestreo emite
    `cuenta.credencial_expira` (webhook/Slack + aviso in-app a los admin) para que alguien la
    re-autentique ANTES de que la generacion se pare: el login es interactivo, no se arregla solo.
    `0` = sin aviso previo (solo se avisa cuando YA ha caducado). Editable en caliente.
    """
    return _entero(ENV_CUENTA_AVISO_CADUCIDAD_H, CUENTA_AVISO_CADUCIDAD_H_DEF, minimo=0)


def presupuesto_margen_manual_pct() -> int:
    """Margen extra (%) SOLO para lanzamientos manuales tras el corte del fondo.

    `KENI_PRESUPUESTO_MARGEN_MANUAL`, def 20: agotado el presupuesto, lo manual sigue
    funcionando hasta `presupuesto * (1 + margen/100)`; superado eso, corte TOTAL.
    """
    return _entero(ENV_PRESUPUESTO_MARGEN_MANUAL, PRESUPUESTO_MARGEN_MANUAL_DEF, minimo=0)


def jobs_max_intentos() -> int:
    """Intentos maximos de ejecucion de un job de la cola (`KENI_JOBS_MAX_INTENTOS`, def 3).

    Cuenta el intento normal MAS los re-reclamos de un job sin dueño (worker muerto a mitad). Al
    agotarse, el re-reclamo DESCARTA el job (registro en error con motivo `interrumpido`) en
    vez de re-ejecutarlo para siempre: un job que mata al worker (OOM por un prompt enorme,
    bug del runner) no debe convertirse en un crash-loop que ademas consume tokens en cada iteracion.
    """
    return _entero(ENV_JOBS_MAX_INTENTOS, JOBS_MAX_INTENTOS_DEF, minimo=1)


# Piso de la retencion del ledger crudo cuando esta encendida: el lector de MAYOR horizonte
# sobre el crudo es la pagina Economia (el endpoint clampa a 31 dias); 35 deja margen para que
# ningun panel pierda dias por una retencion mal configurada.
GASTO_IA_RETENCION_DIAS_MIN = 35


def gasto_ia_retencion_dias() -> int:
    """Dias que las filas CRUDAS del ledger `gasto_ia` se conservan tal cual
    (`KENI_GASTO_IA_RETENCION_DIAS`, def 90; 0 = sin purga).

    Mas alla de la ventana, `db_jobs.purgar_gasto_ia` COMPACTA lo viejo en el agregado diario
    `gasto_ia_diario` (mismas sumas y conteos por dia/proceso/tipo/etapa/marca) y borra el crudo.
    Los lectores del dia vivo (freno de presupuesto, tarjeta de Economia), la pagina Economia
    (<= 31 dias) y el monitor (14 dias) leen SIEMPRE dentro de la ventana; los promedios
    historicos por etapa suman crudo + agregado, asi que sus numeros no cambian. Un valor > 0
    se eleva al piso `GASTO_IA_RETENCION_DIAS_MIN` (35) para que ninguna configuracion agresiva
    recorte lo que los paneles muestran.
    """
    dias = _entero(ENV_GASTO_IA_RETENCION_DIAS, GASTO_IA_RETENCION_DIAS_DEF, minimo=0)
    if dias == 0:
        return 0
    return max(dias, GASTO_IA_RETENCION_DIAS_MIN)


def prompt_max_chars() -> int:
    """Tope DURO del prompt de una generacion (`KENI_PROMPT_MAX_CHARS`, def 200000; 0 = sin tope).

    Economia de contexto: un prompt patologico (feeds concatenados sin verificación, un documento
    gigante) consumiria decenas de miles de tokens de la suscripcion compartida en UNA generacion.
    Superarlo rechaza el encolado con un mensaje claro (`PromptExcesivoError` -> 429).
    """
    return _entero(ENV_PROMPT_MAX_CHARS, PROMPT_MAX_CHARS_DEF, minimo=0)


def prompt_aviso_chars() -> int:
    """Umbral de AVISO del tamano del prompt (`KENI_PROMPT_AVISO_CHARS`, def 80000; 0 = sin aviso).

    No corta nada: deja un warning correlacionado al gen-id para detectar la deriva del
    contexto (prompts cada vez mas gordos) ANTES de chocar con el tope duro.
    """
    return _entero(ENV_PROMPT_AVISO_CHARS, PROMPT_AVISO_CHARS_DEF, minimo=0)


def generacion_pausada() -> bool:
    """KILL SWITCH humano de la generacion (`KENI_GENERACION_PAUSADA`, def off).

    Encendido: NO se encola NADA nuevo (fondo ni manual; 429 claro) y el worker DEJA de
    reclamar jobs (lo ya encolado espera; lo que corre termina). Editable en caliente desde
    la UI (store de ajustes compartido por back/worker/daemons via /data): es el control
    manual cuando la suscripcion compartida esta al limite o algo se desboca.
    """
    return _crudo(ENV_GENERACION_PAUSADA).lower() in _VERDADEROS


# --------------------------------------------------------------------------- #
# Presupuesto + parada de emergencia POR MARCA (overrides KENI_*::<marca>)      #
# --------------------------------------------------------------------------- #
#
# Cada marca puede llevar su PROPIO tope de coste USD/día y su PROPIA parada de emergencia, sobre
# la misma maquinaria de overrides por-marca de las etapas (`config.produccion.clave_por_marca`,
# clave `KENI_*::<marca>` en el store). Son INDEPENDIENTES del control global: el corte efectivo de
# un job de la marca es el MÁS restrictivo entre su control de marca y el global (ver
# `presupuesto_ia`). Sin override la marca no añade límite (solo aplica el global).


def presupuesto_usd_dia_marca(marca: str) -> float:
    """Tope de coste USD/día PROPIO de una marca (`KENI_PRESUPUESTO_USD_DIA::<marca>`, def 0).

    `0`/ausente = SIN tope de marca (solo aplica el cap global). Independiente del global: el corte
    de un job de la marca toma el MÁS restrictivo de ambos.
    """
    from .produccion import clave_por_marca

    if not marca:
        return 0.0
    crudo = _crudo(clave_por_marca(ENV_PRESUPUESTO_USD_DIA, marca))
    if not crudo:
        return 0.0
    try:
        return max(0.0, float(crudo))
    except ValueError:
        return 0.0


def generacion_pausada_marca(marca: str) -> bool:
    """Parada de emergencia PROPIA de una marca (`KENI_GENERACION_PAUSADA::<marca>`, def off).

    Encendida corta TODA la generación de ESA marca (fondo y manual) sin tocar al resto. Ortogonal
    al kill switch global: basta con que UNO de los dos (global o de marca) esté activo.
    """
    from .produccion import clave_por_marca

    if not marca:
        return False
    return _crudo(clave_por_marca(ENV_GENERACION_PAUSADA, marca)).lower() in _VERDADEROS


def _tope_tokens_dia_marca(env: str, marca: str) -> int:
    """Tope de tokens/día PROPIO de una marca para un env de tope (`<ENV>::<marca>`, def 0).

    `0`/ausente = la marca no añade tope por ese lado (solo aplica el global). Es el análogo
    por-marca de los topes por motor; el corte toma el MÁS restrictivo entre marca y global."""
    from .produccion import clave_por_marca

    if not marca:
        return 0
    return _entero(clave_por_marca(env, marca), 0, minimo=0)


def presupuesto_tokens_investigacion_in_dia_marca(marca: str) -> int:
    """Tope de tokens de ENTRADA/día de Investigación PROPIO de una marca (def 0 = sin tope)."""
    return _tope_tokens_dia_marca(ENV_PRESUPUESTO_TOKENS_INVESTIGACION_IN_DIA, marca)


def presupuesto_tokens_investigacion_out_dia_marca(marca: str) -> int:
    """Tope de tokens de SALIDA/día de Investigación PROPIO de una marca (def 0 = sin tope)."""
    return _tope_tokens_dia_marca(ENV_PRESUPUESTO_TOKENS_INVESTIGACION_OUT_DIA, marca)


def presupuesto_tokens_produccion_in_dia_marca(marca: str) -> int:
    """Tope de tokens de ENTRADA/día de Producción PROPIO de una marca (def 0 = sin tope)."""
    return _tope_tokens_dia_marca(ENV_PRESUPUESTO_TOKENS_PRODUCCION_IN_DIA, marca)


def presupuesto_tokens_produccion_out_dia_marca(marca: str) -> int:
    """Tope de tokens de SALIDA/día de Producción PROPIO de una marca (def 0 = sin tope)."""
    return _tope_tokens_dia_marca(ENV_PRESUPUESTO_TOKENS_PRODUCCION_OUT_DIA, marca)



# --------------------------------------------------------------------------- #
# Accesores: cola + worker de generacion (ADR 0002)                            #
# --------------------------------------------------------------------------- #
#
# DOS modos de ejecucion del worker que consume la cola de generacion:
#   - LOCAL / un solo proceso (def): el back arranca el worker EN PROCESO (hilo de
#     fondo). La UX de una sola maquina no cambia: no hace falta un servicio aparte y
#     `claude` esta en el mismo entorno.
#   - HOSTED: un servicio `worker` SEPARADO consume la misma cola. Se activa con
#     `KENI_WORKER_EXTERNO` afirmativo en el back (asi NO arranca su worker in-proceso) y
#     el contenedor `worker` corre `python -m keni_consola.worker` (que SI tiene `claude`).


def worker_externo() -> bool:
    """True si hay un servicio `worker` SEPARADO (hosted) que consume la cola.

    `KENI_WORKER_EXTERNO` afirmativo => el back NO arranca su worker in-proceso (lo hace
    el contenedor `worker`). Def OFF: el back arranca el worker in-proceso (perfil local /
    un solo proceso), preservando la UX de una sola maquina sin servicio aparte.
    """
    return _crudo(ENV_WORKER_EXTERNO).lower() in _VERDADEROS


def worker_carriles() -> set[str]:
    """Carriles de cola que ESTE worker reclama (`KENI_WORKER_CARRILES`, lista por comas).

    Reparte el trabajo de las DOS cuentas de Claude entre workers: el worker A monta `cuenta-a`
    ademas de `inferencia,proceso`; el worker B solo `cuenta-b` (cada uno con su `CLAUDE_CONFIG_DIR`).
    Vacio/ausente = TODOS los carriles de CONTENIDO (inferencia, proceso, cuenta-a, cuenta-b): el
    perfil de UNA sola maquina/cuenta no orfana ningun job. NUNCA incluye `dev`/`transcripcion`
    (esos los reclaman sus servicios dedicados).
    """
    from ..dominio import jobspec

    crudo = _crudo(ENV_WORKER_CARRILES)
    if not crudo:
        return {
            jobspec.CARRIL_INFERENCIA, jobspec.CARRIL_PROCESO,
            jobspec.CARRIL_CUENTA_A, jobspec.CARRIL_CUENTA_B,
        }
    return {c.strip() for c in crudo.split(",") if c.strip()}


def worker_sondeo_segundos() -> float:
    """Intervalo de sondeo de la cola por el worker (`KENI_WORKER_SONDEO_SEGUNDOS`, def 0.5, min 0.05)."""
    crudo = _crudo(ENV_WORKER_SONDEO_SEGUNDOS)
    if not crudo:
        return WORKER_SONDEO_SEGUNDOS_DEF
    try:
        valor = float(crudo)
    except ValueError:
        return WORKER_SONDEO_SEGUNDOS_DEF
    return max(0.05, valor)
