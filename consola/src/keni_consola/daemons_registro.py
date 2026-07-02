"""Registro DECLARATIVO de los daemons de fondo: qué DEBE existir, no qué late.

La tabla `daemon_latidos` solo conoce a los daemons que YA han latido alguna vez: un hilo
que muere al arrancar, o una BD recién migrada, simplemente NO aparece en el panel, y
"roto en silencio" se confunde con "no existe". Este módulo declara la lista COMPLETA de
daemons que el proceso de fondo (`keni_consola.daemons`) cablea, para que la sonda del
panel (`api.sistema.daemons.sonda_daemons`) pinte "sin_datos" a los registrados que aún
no tienen fila de latido — distinto de "inactivo" (apagado a propósito: su bucle late
igualmente con activo=0) y de "atrasado" (llegó a latir y dejó de hacerlo).

QUÉ ES FUENTE ÚNICA AQUÍ: la EXISTENCIA y el cableado de cada daemon (qué `iniciar_*` de
`daemons.py` lo arranca, cómo deja latido/resultado y su cadencia orientativa). El resto
de metadatos por daemon (etiqueta, descripción, gate/clave de ajuste, clasificación,
barrible) siguen viviendo en `latidos` — aquí no se duplican para que no deriven.

Un test (`tests/test_daemons_registro.py`) recorre el AST de `daemons.py` y verifica la
correspondencia en AMBOS sentidos (cada `iniciar_*` cableado tiene entrada aquí y cada
entrada tiene su `iniciar_*`): no se puede añadir un daemon nuevo sin registrarlo.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DaemonRegistrado:
    """Una fila del registro: un daemon que `daemons.py` arranca y que debe latir.

    - `nombre`: nombre canónico con el que late en `daemon_latidos` (tras `latidos._ALIAS`
      o el `nombre=` explícito de su `bucle_gateado`). Es también su clave en
      `daemon_barridos` (fuente del resultado de cada barrido) y en el resto de fuentes
      únicas de `latidos` (etiqueta, descripción, `clave_gate_de`…).
    - `iniciador`: la función `iniciar_*` de `daemons.py` que lo arranca (un iniciador
      puede arrancar varios daemons: el pipeline abre investigación/producción/portal).
    - `latido_propio`: True si su bucle late solo (ciclo en cada tick, aunque su gate esté
      OFF). False si su latido depende del barrido de OTRO daemon (p. ej. `caducidad`
      corre dentro del barrido de la ingesta): sin ese anfitrión activo puede quedarse
      legítimamente en "sin_datos".
    - `cadencia`: descripción ORIENTATIVA de cada cuánto barre (para leer el registro sin
      abrir cada módulo). La cadencia REAL vive en su fila de latido (`intervalo_seg`/
      `tick_seg`) y el umbral de atraso lo deriva la sonda de ahí, no de aquí.
    """

    nombre: str
    iniciador: str
    cadencia: str
    latido_propio: bool = True


# La tabla: TODO daemon que `daemons.py` cablea, en el orden en que los arranca.
REGISTRO: tuple[DaemonRegistrado, ...] = (
    DaemonRegistrado("programador", "iniciar_programador", "cada ~1 min"),
    DaemonRegistrado("metricas", "iniciar_refresco_metricas", "periódico (horas)"),
    DaemonRegistrado("metricas_piezas", "iniciar_refresco_piezas", "periódico (minutos)"),
    DaemonRegistrado("alertas_rendimiento", "iniciar_alertas_rendimiento", "cada pocas horas"),
    DaemonRegistrado("investigacion", "iniciar_pipeline", "cada pocos min (con backoff)"),
    DaemonRegistrado("produccion", "iniciar_pipeline", "cada pocos min (con backoff)"),
    DaemonRegistrado("portal", "iniciar_pipeline", "cada pocos min (con backoff)"),
    DaemonRegistrado("algoritmos", "iniciar_refresco_algoritmos", "cada pocas horas"),
    DaemonRegistrado("media_gc", "iniciar_media_gc", "diario"),
    DaemonRegistrado("patrones", "iniciar_refresco_patrones", "cada N días"),
    DaemonRegistrado("noticias_gc", "iniciar_noticias_gc", "periódico (horas)"),
    DaemonRegistrado("ingesta", "iniciar_ingesta", "cada pocos min (cadencia por feed)"),
    # El reloj de caducidad del pool corre DENTRO del barrido de la ingesta (~cada 15 min):
    # late con nombre propio pero no tiene bucle propio.
    DaemonRegistrado("caducidad", "iniciar_ingesta", "~cada 15 min", latido_propio=False),
    DaemonRegistrado("trends", "iniciar_trends", "periódico (minutos)"),
    DaemonRegistrado("limpiador", "iniciar_limpiador", "cada pocos min"),
    DaemonRegistrado("cuenta_uso_daemon", "iniciar_muestreo_uso", "cada pocos min"),
)

# Iniciadores de `daemons.py` que NO dejan filas en `daemon_latidos` (y por eso no tienen
# entrada en REGISTRO): el listener de control es un servidor de eventos, no un bucle de
# barridos. El test de completitud los descuenta explícitamente.
INICIADORES_SIN_DAEMON = frozenset({"iniciar_control"})


def esperados() -> tuple[str, ...]:
    """Nombres de TODOS los daemons registrados, en el orden de arranque."""
    return tuple(d.nombre for d in REGISTRO)


def iniciadores() -> frozenset[str]:
    """Las funciones `iniciar_*` de `daemons.py` que el registro declara."""
    return frozenset(d.iniciador for d in REGISTRO)


def por_nombre(nombre: str) -> DaemonRegistrado | None:
    """La entrada del registro para `nombre`, o None si no está registrado."""
    for d in REGISTRO:
        if d.nombre == nombre:
            return d
    return None
