"""Gate DIARIO de consumo: corta TODA la generacion cuando el % del limite SEMANAL de la cuenta
de Claude consumido HOY (UTC) alcanza el umbral del dia, con reanudacion humana-en-el-bucle.

POR QUE EXISTE: la generacion corre `claude -p` (ADR 0001) con la suscripcion COMPARTIDA del
equipo, que tiene un limite SEMANAL. El gasto en USD (presupuesto_ia) es un proxy del coste, no
del cupo real de la cuenta. Este gate vigila el cupo REAL: reparte el limite semanal en 7 dias
(un septimo por dia, ~14,3%) y, cuando el consumo del dia alcanza ese umbral, PAUSA toda la
generacion (automatica Y manual) y pide criterio humano. Es "avisar del consumo" con corte
humano-en-el-bucle, monitorizado por %: aceptar sube el umbral del dia +10% y reanuda; al cruzar
el nuevo umbral, vuelve a pausar y pedir aceptar.

FUENTE DEL % (seam unico, `consumo_semanal_hoy_pct`): el % semanal real de la cuenta lo persiste
una FUNDACION aparte (rama feat/uso-cuenta-foundation) que muestrea `cuenta_claude.uso()` (el
medidor "Current week (all models)" pct + su reset) y guarda snapshots. Este modulo NO muestrea:
solo LEE, tras un unico accesor con fallback seguro (None => NO cortar). El cableado a los repos
de la fundacion lo hace el orquestador al integrar (ver el TODO del accesor).

ESTADO DIARIO (mutable, pequeno): por dia UTC se persiste cuantos "+10%" se han aceptado en el
store de ajustes compartido (`ajustes.py`, TOML en /data: lo ven back/worker/daemons en caliente,
mismo patron que el kill switch). El umbral vigente se DERIVA: `BASE + aceptados * PASO`. Al
cambiar de dia UTC el contador se ignora (reset implicito): un valor de ayer no cuenta para hoy.

INTEGRACION: `presupuesto_ia._nivel_global` consulta `pausado_por_pct()` y, si corta, devuelve
NIVEL_PAUSADO. Asi TODOS los call sites que ya consultan `nivel()`/`bloqueo_admision`
(cola.encolar, worker, gates inline) heredan el corte sin tocarlos. `estado()` expone el detalle
para que el UI distinga este "pausado por % diario" del kill switch manual.
"""

from __future__ import annotations

import json
import logging

from . import ajustes
from .tiempo import ahora_iso

_log = logging.getLogger("keni_consola.gate_diario")

# Umbral BASE del dia: un septimo del limite SEMANAL (100% / 7 dias ~= 14,3 puntos porcentuales
# del semanal por dia). Cada "Aceptar +10%" sube el umbral del dia en PASO puntos porcentuales.
BASE_UMBRAL_PCT = 100.0 / 7.0
PASO_PCT = 10.0

# Clave del store de ajustes donde vive el estado diario: un JSON `{"dia": "YYYY-MM-DD",
# "aceptados": int}`. Un solo valor mantiene dia y contador consistentes (escritura atomica del
# store). No es una clave del catalogo de ajustes: nadie la lee como config, solo este modulo.
CLAVE_ESTADO = "KENI_GATE_DIARIO_ESTADO"


def _hoy_utc() -> str:
    """Dia UTC actual (YYYY-MM-DD), el bucket del estado diario (mismo "hoy" que presupuesto_ia)."""
    return ahora_iso()[:10]


def consumo_semanal_hoy_pct() -> float | None:
    """ACCESOR UNICO de la fuente del %: puntos porcentuales del limite SEMANAL de la cuenta de
    Claude consumidos HOY (UTC).

    CONTRATO:
      - Devuelve `pct_semanal_actual - pct_semanal_al_inicio_del_dia` (UTC): cuanto del cupo
        semanal se ha gastado HOY, en puntos porcentuales del semanal (p. ej. 14.3 = se consumio
        hoy un septimo del cupo de la semana). Nunca negativo en uso normal; si el medidor
        retrocede (reset semanal a mitad de dia) la fundacion decide como reanclar el inicio del
        dia — este modulo solo consume el numero ya calculado.
      - None => sin dato fiable (el muestreo aun no persistio snapshots, cuenta desconectada, o no
        hay medidor semanal). FALLBACK SEGURO: con None el gate NO corta (`pausado_por_pct` devuelve
        False). Preferimos no cortar ante falta de dato: un falso corte pararia la maquina entera.

    FUENTE: la tabla `cuenta_uso` que mantiene el muestreo de fondo (`cuenta_uso_daemon`), via
    `repos.leer_uso_cuenta()`. Persiste el medidor "Current week (all models)" actual
    (`semana_pct`) y su valor AL INICIO DEL DIA UTC (`semana_pct_inicio_dia`, reanclado por la
    fundacion en el rollover/reset); el consumo de hoy es su resta. NO muestrea aqui (no duplica).
    """
    from . import repos  # perezoso: evita el ciclo de import (presupuesto_ia -> gate_diario)

    try:
        fila = repos.leer_uso_cuenta()
    except Exception:  # noqa: BLE001 -- un blip de BD no debe cortar la maquina
        _log.warning("gate_diario: fallo al leer el uso de la cuenta; no corto", exc_info=True)
        return None
    if not fila or not fila.get("conectada"):
        return None
    actual = fila.get("semana_pct")
    base = fila.get("semana_pct_inicio_dia")
    if actual is None or base is None:
        return None
    return max(0.0, float(actual) - float(base))


def _estado_persistido() -> tuple[str, int]:
    """(dia, aceptados) del store, o ("", 0) si no hay nada / esta corrupto. Lectura tolerante."""
    crudo = ajustes.obtener(CLAVE_ESTADO)
    if not crudo:
        return ("", 0)
    try:
        datos = json.loads(crudo)
        dia = str(datos.get("dia") or "")
        aceptados = int(datos.get("aceptados") or 0)
    except (ValueError, TypeError, AttributeError):
        return ("", 0)
    return (dia, max(0, aceptados))


def aceptados_hoy() -> int:
    """Cuantos "+10%" se han aceptado HOY (UTC). 0 si el estado guardado es de otro dia (reset)."""
    dia, aceptados = _estado_persistido()
    return aceptados if dia == _hoy_utc() else 0


def umbral_vigente() -> float:
    """Umbral del dia (puntos porcentuales del semanal): BASE + aceptados_hoy * PASO."""
    return BASE_UMBRAL_PCT + aceptados_hoy() * PASO_PCT


def pausado_por_pct() -> bool:
    """True si el consumo del dia alcanza el umbral vigente => PAUSA toda la generacion.

    Con la fuente del % en None (sin dato) devuelve False: NO cortar (fallback seguro).
    """
    consumo = consumo_semanal_hoy_pct()
    if consumo is None:
        return False
    return consumo >= umbral_vigente()


def aceptar_mas() -> dict:
    """Sube el umbral del dia +10% (registra un "aceptar" del dia UTC) y devuelve el `estado()`.

    Reancla el contador al dia de hoy: si el estado guardado era de un dia anterior, parte de 0
    y suma 1 (el primer aceptar del dia). Escritura atomica via el store de ajustes compartido.
    """
    hoy = _hoy_utc()
    aceptados = aceptados_hoy() + 1
    ajustes.guardar(CLAVE_ESTADO, json.dumps({"dia": hoy, "aceptados": aceptados}))
    _log.info("gate_diario: aceptado +%.0f%% (dia %s, aceptados=%d)", PASO_PCT, hoy, aceptados)
    return estado()


def estado() -> dict:
    """Snapshot del gate diario para el UI/los agentes (CONTRATO, expuesto bajo `gate_diario`):

      {consumo_hoy_pct: float|None, umbral_pct: float, aceptados_hoy: int,
       pausado_por_pct: bool, base_umbral_pct: float, paso_pct: float, dia: str}

    `consumo_hoy_pct` es None mientras la fuente del % no exista (rollout): con None el gate esta
    inerte y `pausado_por_pct` es False. `umbral_pct` es el umbral vigente del dia (sube +10% por
    cada aceptar). El UI muestra la pantalla "Aceptar continuar (+10%)" cuando `pausado_por_pct`.
    """
    consumo = consumo_semanal_hoy_pct()
    umbral = umbral_vigente()
    return {
        "consumo_hoy_pct": round(consumo, 1) if consumo is not None else None,
        "umbral_pct": round(umbral, 1),
        "aceptados_hoy": aceptados_hoy(),
        "pausado_por_pct": consumo is not None and consumo >= umbral,
        "base_umbral_pct": round(BASE_UMBRAL_PCT, 1),
        "paso_pct": PASO_PCT,
        "dia": _hoy_utc(),
    }
