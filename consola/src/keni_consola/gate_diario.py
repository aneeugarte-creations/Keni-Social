"""Gate DIARIO de consumo POR CUENTA de Claude: corta la generacion de las marcas de UNA cuenta
cuando el % de SU limite SEMANAL consumido HOY (jornada CDMX) alcanza el umbral del dia, con
reanudacion humana-en-el-bucle e INDEPENDIENTE por cuenta.

POR QUE EXISTE: la generacion corre `claude -p` (ADR 0001) con suscripciones de equipo que tienen
limite SEMANAL. Hay DOS cuentas (A/B; el reparto de marcas vive en `ruteo_cuentas`), cada una con
SU propio cupo semanal. El gasto en USD (presupuesto_ia) es un proxy del coste, no del cupo real.
Este gate vigila el cupo REAL de CADA cuenta: reparte el cupo semanal que le QUEDA entre los dias
que faltan para SU reset (no un septimo fijo) y, cuando el consumo del dia de ESA cuenta alcanza ese
cupo, PAUSA la generacion de SUS marcas (automatica Y manual) y pide criterio humano a su gente. La
otra cuenta sigue su ritmo aparte. Aceptar +10% sube el umbral del dia de ESA cuenta y reanuda; al
cruzar el nuevo umbral, vuelve a pausar y pedir aceptar.

FUENTE DEL % (seam unico, `consumo_semanal_hoy_pct(cuenta)`): el % semanal real de cada cuenta lo
persiste una FUNDACION aparte que muestrea el medidor "Current week (all models)" POR CUENTA y
guarda snapshots. Este modulo NO muestrea: solo LEE, tras un unico accesor con fallback seguro
(None => NO cortar). El cableado a los repos por cuenta lo hace el orquestador al integrar (ver el
TODO del accesor): hasta entonces el accesor devuelve None y el gate queda inerte (no corta).

ESTADO DIARIO (mutable, pequeno) POR CUENTA: por dia CDMX y por cuenta se persiste cuantos "+10%" se
han aceptado, en el store de ajustes compartido (`ajustes.py`, TOML en /data: lo ven
back/worker/daemons en caliente, mismo patron que el kill switch). El umbral vigente de la cuenta
se DERIVA: `cupo_del_dia + aceptados * PASO` (cupo = lo que queda / dias hasta el reset). Al cambiar
de dia CDMX el contador se ignora (reset implicito):
un valor de ayer no cuenta para hoy. Cada cuenta tiene su propia clave -> su corte y su aceptar son
independientes.

INTEGRACION: `presupuesto_ia._nivel_global(marca)` mapea `marca -> cuenta` (`ruteo_cuentas`) y
consulta `pausado_por_pct(cuenta)`; si corta, devuelve NIVEL_PAUSADO. Asi el corte por % cae en la
ADMISION (`cola.encolar(marca=...)`, donde se conoce la marca) y pausa SOLO las marcas de la cuenta
gateada. `estado(cuenta)`/`estado_todas()` exponen el detalle para que el UI muestre el aviso de la
cuenta correcta.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime

from . import ajustes
from .dominio import jobspec
from .tiempo import dia_cdmx, hoy_cdmx

_log = logging.getLogger("keni_consola.gate_diario")

# Reparto PLANO de respaldo: un septimo del limite SEMANAL (100% / 7 dias ~= 14,3 pp/dia). Es el
# cupo del dia SOLO cuando aun no se conoce el reset o la base del dia de la cuenta; con esos datos
# el cupo se calcula adaptativo (lo que queda / dias hasta el reset, ver `_umbral_base_pct`). Cada
# "Aceptar +10%" sube el umbral del dia en PASO puntos porcentuales.
BASE_UMBRAL_PCT = 100.0 / 7.0
PASO_PCT = 10.0

# Prefijo del store de ajustes donde vive el estado diario POR CUENTA: una clave por cuenta
# (`KENI_GATE_DIARIO_ESTADO::<cuenta>`) con un JSON `{"dia": "YYYY-MM-DD", "aceptados": int}`. Un
# solo valor por cuenta mantiene dia y contador consistentes (escritura atomica del store). No es
# una clave del catalogo de ajustes: nadie la lee como config, solo este modulo.
CLAVE_ESTADO = "KENI_GATE_DIARIO_ESTADO"


def _clave(cuenta: str) -> str:
    """Clave del store del estado diario de UNA cuenta (`KENI_GATE_DIARIO_ESTADO::<cuenta>`)."""
    return f"{CLAVE_ESTADO}::{cuenta}"


def _hoy_cdmx() -> str:
    """Dia CDMX actual (YYYY-MM-DD), el bucket del estado diario (mismo "hoy" que presupuesto_ia)."""
    return dia_cdmx()


def consumo_semanal_hoy_pct(cuenta: str) -> float | None:
    """ACCESOR UNICO de la fuente del %: puntos porcentuales del limite SEMANAL de `cuenta`
    consumidos HOY (jornada CDMX).

    CONTRATO:
      - Devuelve `pct_semanal_actual - pct_semanal_al_inicio_del_dia` (CDMX) de ESA cuenta: cuanto de
        su cupo semanal se ha gastado HOY (jornada CDMX), en puntos porcentuales del semanal (p. ej. 14.3 = se
        consumio hoy un septimo del cupo de la semana). Nunca negativo en uso normal; si el medidor
        retrocede (reset semanal a mitad de dia) la fundacion decide como reanclar el inicio del
        dia — este modulo solo consume el numero ya calculado.
      - None => sin dato fiable de esa cuenta (el muestreo aun no persistio snapshots, cuenta
        desconectada, o no hay medidor semanal). FALLBACK SEGURO: con None el gate de esa cuenta NO
        corta (`pausado_por_pct` devuelve False). Preferimos no cortar ante falta de dato: un falso
        corte pararia las marcas de esa cuenta sin motivo.

    FUENTE: el muestreo de fondo POR CUENTA persiste, para cada cuenta, el medidor "Current week
    (all models)" actual (`semana_pct`) y su valor AL INICIO DEL DIA CDMX (`semana_pct_inicio_dia`,
    reanclado por la fundacion en el rollover/reset); el consumo de hoy es su resta. NO muestrea
    aqui (no duplica).

    Implementacion: `repos.leer_uso_cuenta(cuenta)` (la fila de ESA cuenta del muestreo de fondo
    POR CUENTA). Best-effort: ante un fallo de lectura devuelve None (no corta).
    """
    fila = _leer_fila(cuenta)
    if not fila or not fila.get("conectada"):
        return None
    actual = fila.get("semana_pct")
    base = fila.get("semana_pct_inicio_dia")
    if actual is None or base is None:
        return None
    return max(0.0, float(actual) - float(base))


def _leer_fila(cuenta: str) -> dict | None:
    """Ultima fila del muestreo de fondo de `cuenta` (o None si no hay / blip de BD). Best-effort:
    ante un fallo de lectura devuelve None para no cortar las marcas de la cuenta."""
    from . import repos  # perezoso: evita el ciclo de import (presupuesto_ia -> gate_diario)

    try:
        return repos.leer_uso_cuenta(cuenta)
    except Exception:  # noqa: BLE001 -- un blip de BD no debe cortar las marcas de la cuenta
        _log.warning("gate_diario: fallo al leer el uso de %s; no corto", cuenta, exc_info=True)
        return None


def _dias_hasta_reset(reset_iso: str, hoy: date) -> int:
    """Dias CDMX desde `hoy` (incluido) hasta el dia del reset semanal de la cuenta; minimo 1.

    Reparte el cupo restante entre los dias que de verdad faltan. `reset_iso` es el instante del
    reset (`reset_semana_iso` del muestreo, ISO-UTC). Sin fecha fiable cae a 7 (la semana entera),
    recuperando el reparto plano de antes.
    """
    if not reset_iso:
        return 7
    try:
        reset = datetime.fromisoformat(reset_iso.replace("Z", "+00:00"))
    except ValueError:
        return 7
    return max(1, (hoy_cdmx(reset) - hoy).days)


def _umbral_base_pct(semana_pct_inicio_dia: float | None, reset_iso: str, hoy: date) -> float:
    """Cupo del dia (pp del semanal): el % del cupo SEMANAL que QUEDABA al inicio del dia, repartido
    entre los dias que faltan hasta el reset.

    `(100 - consumido_al_inicio_del_dia) / dias_hasta_reset`. Asi un dia flojo deja mas margen al
    siguiente y uno intenso lo aprieta, convergiendo a agotar el cupo justo en la renovacion (en vez
    de un septimo fijo que ignora si la semana va sobrada o pasada). Sin base fiable -> reparto
    plano (`BASE_UMBRAL_PCT`).
    """
    if semana_pct_inicio_dia is None:
        return BASE_UMBRAL_PCT
    restante = max(0.0, 100.0 - float(semana_pct_inicio_dia))
    return restante / _dias_hasta_reset(reset_iso, hoy)


def _umbral_base_cuenta(cuenta: str) -> float:
    """Cupo base del dia de `cuenta` leyendo su fila de uso (reset + base del dia). Sin fila ->
    reparto plano (`BASE_UMBRAL_PCT`)."""
    fila = _leer_fila(cuenta)
    if not fila:
        return BASE_UMBRAL_PCT
    return _umbral_base_pct(
        fila.get("semana_pct_inicio_dia"), str(fila.get("reset_semana_iso") or ""), hoy_cdmx()
    )


def _estado_persistido(cuenta: str) -> tuple[str, int]:
    """(dia, aceptados) del store para `cuenta`, o ("", 0) si no hay nada / esta corrupto."""
    crudo = ajustes.obtener(_clave(cuenta))
    if not crudo:
        return ("", 0)
    try:
        datos = json.loads(crudo)
        dia = str(datos.get("dia") or "")
        aceptados = int(datos.get("aceptados") or 0)
    except (ValueError, TypeError, AttributeError):
        return ("", 0)
    return (dia, max(0, aceptados))


def aceptados_hoy(cuenta: str) -> int:
    """Cuantos "+10%" se han aceptado HOY (CDMX) en `cuenta`. 0 si el estado guardado es de otro dia."""
    dia, aceptados = _estado_persistido(cuenta)
    return aceptados if dia == _hoy_cdmx() else 0


def umbral_vigente(cuenta: str) -> float:
    """Umbral del dia de `cuenta` (pp del semanal): cupo base del dia (lo que queda del cupo semanal
    repartido entre los dias hasta el reset) + aceptados_hoy(cuenta) * PASO."""
    return _umbral_base_cuenta(cuenta) + aceptados_hoy(cuenta) * PASO_PCT


def pausado_por_pct(cuenta: str) -> bool:
    """True si el consumo del dia de `cuenta` alcanza su umbral vigente => PAUSA sus marcas.

    Con la fuente del % en None (sin dato) devuelve False: NO cortar (fallback seguro).
    """
    consumo = consumo_semanal_hoy_pct(cuenta)
    if consumo is None:
        return False
    return consumo >= umbral_vigente(cuenta)


def aceptar_mas(cuenta: str) -> dict:
    """Sube +10% el umbral del dia de `cuenta` (registra un "aceptar" del dia CDMX) y devuelve su
    `estado(cuenta)`.

    Reancla el contador al dia de hoy: si el estado guardado era de un dia anterior, parte de 0 y
    suma 1 (el primer aceptar del dia). Escritura atomica via el store de ajustes compartido. Solo
    afecta a ESA cuenta: la otra conserva su umbral.
    """
    hoy = _hoy_cdmx()
    aceptados = aceptados_hoy(cuenta) + 1
    ajustes.guardar(_clave(cuenta), json.dumps({"dia": hoy, "aceptados": aceptados}))
    _log.info(
        "gate_diario: aceptado +%.0f%% (cuenta %s, dia %s, aceptados=%d)",
        PASO_PCT, cuenta, hoy, aceptados,
    )
    return estado(cuenta)


def estado(cuenta: str) -> dict:
    """Snapshot del gate diario de UNA cuenta para el UI/los agentes (CONTRATO):

      {cuenta: str, consumo_hoy_pct: float|None, umbral_pct: float, aceptados_hoy: int,
       pausado_por_pct: bool, base_umbral_pct: float, paso_pct: float, dia: str}

    `consumo_hoy_pct` es None mientras la fuente del % de esa cuenta no exista (rollout): con None el
    gate esta inerte y `pausado_por_pct` es False. `base_umbral_pct` es el cupo base del dia (lo que
    queda del cupo semanal repartido entre los dias hasta el reset) y `umbral_pct` ese cupo + los
    +10% aceptados. El UI muestra "Aceptar continuar (+10%)" para la cuenta cuando `pausado_por_pct`.
    `cuenta` rotula a quien pertenece el bloque (y a quien aplica aceptar).
    """
    consumo = consumo_semanal_hoy_pct(cuenta)
    base = _umbral_base_cuenta(cuenta)
    umbral = base + aceptados_hoy(cuenta) * PASO_PCT
    return {
        "cuenta": cuenta,
        "consumo_hoy_pct": round(consumo, 1) if consumo is not None else None,
        "umbral_pct": round(umbral, 1),
        "aceptados_hoy": aceptados_hoy(cuenta),
        "pausado_por_pct": consumo is not None and consumo >= umbral,
        "base_umbral_pct": round(base, 1),
        "paso_pct": PASO_PCT,
        "dia": _hoy_cdmx(),
    }


def estado_todas() -> dict[str, dict]:
    """`{cuenta: estado(cuenta)}` de TODAS las cuentas (`jobspec.CUENTAS`).

    Lo consume el frontend para el modo "Todas" del selector de marca (puede pintar el aviso de cada
    cuenta que este gateada) y el diagnostico del sistema (reporta cualquier cuenta pausada por %).
    """
    return {cuenta: estado(cuenta) for cuenta in jobspec.CUENTAS}
