"""Auto-programación: una pieza APROBADA pasa SOLA a `programado` en su próximo hueco.

El último OK humano cierra la cadena de aprobación y la pieza queda `aprobado`. En vez de
dejarla esperando una programación manual, aquí se ENCOLA al próximo hueco libre de sus franjas
(la misma lógica del botón "encolar": `api.publicaciones.calcular_hueco_para`), respetando los
MISMOS gates que la programación manual (`api.aprobacion.programar`):

  - Gate A (gobernanza): si la pieza tiene CADENA, debe cumplir el mínimo de aprobaciones
    (`config.min_aprobaciones`). Al cerrarse la cadena lo cumple por definición; el barrido de
    piezas ya-aprobadas también lo comprueba. Una pieza `aprobado` SIN cadena (atajo admin) no
    tiene nada que contar y pasa el gate.
  - Gate B (verificación): cero comentarios sin resolver (una objeción pendiente bloquea programar).
  - Debe existir una franja aplicable a su (marca, red). Si no hay hueco, la pieza se queda
    `aprobado` (no se inventa fecha): saldrá programada en cuanto se configure una franja.

NO publica: deja la pieza en `programado` con su `fecha_programada`; el programador del server la
prepara (DRY-RUN) al vencer, y el posteo real sigue gated por `KENI_PUBLICAR_REAL`.

Se invoca SÍNCRONO en la ruta de aprobación (justo tras cerrar la cadena), no desde un daemon:
la aprobación ocurre por la UI, así que encolar ahí es inmediato y no depende de ningún flag de
demonio. Gateado por `KENI_AUTO_PROGRAMAR` (def ON; ver `config.auto_programar_activo`). No crea
esquema nuevo: solo cambia `estado`/`fecha_programada`, como el encolado manual.
"""

from __future__ import annotations

import logging
from typing import Any

from . import config, repos
from .dominio import colaboracion
from .estados import ESTADO_APROBADO

_log = logging.getLogger("keni_consola.auto_programar")


def programar_si_aprobada(publicacion_id: str) -> dict[str, Any] | None:
    """Si la pieza está `aprobado` y pasa los gates, la encola a su próximo hueco.

    Devuelve la publicación ya `programado` si la encoló; `None` si no aplicaba (no está
    aprobada, flag apagado, gate sin cumplir o sin franja/hueco). Idempotente y best-effort:
    solo actúa sobre piezas en `aprobado`, así que reinvocarla no reprograma una ya programada.
    """
    if not config.auto_programar_activo():
        return None

    pub = repos.obtener_publicacion(publicacion_id)
    if pub is None or pub.get("estado") != ESTADO_APROBADO:
        return None

    # Gate A (gobernanza): mínimo de aprobaciones, SOLO si la pieza tiene cadena configurada.
    cadena = repos.listar_aprobaciones(publicacion_id)
    if cadena:
        cumple, _ = colaboracion.cumple_minimo_aprobaciones(cadena, config.min_aprobaciones())
        if not cumple:
            return None

    # Gate B (verificación): un comentario sin resolver es una objeción pendiente; no programar.
    plat = repos.obtener_contenido_plataforma(publicacion_id)
    if repos.comentarios_sin_resolver((plat or {}).get("contenido_id", "") or "", publicacion_id):
        return None

    # Próximo hueco libre de sus franjas (reusa la lógica del encolado manual). Import perezoso:
    # `api.publicaciones` es capa API; importarlo a nivel de módulo enredaría el grafo de imports.
    # `_encolar_en_hueco_libre` calcula el hueco Y escribe con el BACKSTOP de unicidad de slot
    # (índice parcial `idx_parrilla_slot_uniq`) + reintento: si otra pieza (o el encolado manual
    # de un humano) toma el slot a la vez, recalcula y reintenta en vez de doble-reservarlo.
    from .api.publicaciones import _encolar_en_hueco_libre

    # CAS `estado_esperado=ESTADO_APROBADO`: la AUTO-programación solo escribe `programado` si la
    # pieza SIGUE `aprobado` en el momento de la escritura. Entre la lectura de arriba y aquí otro
    # flujo (edición que la resetea a borrador, "deshacer aprobación", reprograma manual) pudo
    # moverla; sin el CAS la RESUCITARÍAMOS a `programado`, pisando el estado/fecha del humano y
    # haciendo mentir al calendario. El encolado MANUAL no pasa CAS (override deliberado).
    actualizada, hubo_hueco = _encolar_en_hueco_libre(pub, estado_esperado=ESTADO_APROBADO)
    if not hubo_hueco:
        return None  # sin franja aplicable: se queda aprobado (sin inventar fecha).

    # `actualizada is None` con `hubo_hueco=True`: o se borró en la carrera, o el CAS no aplicó (la
    # pieza dejó de estar `aprobado`). En ambos casos NO la programamos: best-effort, sin error.
    if actualizada is not None:
        _log.info(
            "Auto-programada pieza %s en %s.",
            publicacion_id, actualizada.get("fecha_programada"),
        )
    return actualizada


def barrer_aprobadas() -> int:
    """Encola TODAS las piezas hoy en `aprobado` que tengan hueco. Devuelve cuántas programó.

    Para programar las que ya están aprobadas (la auto-programación síncrona solo coge las que
    se aprueban a partir de ahora). Las que no tengan franja/hueco se quedan `aprobado`.
    """
    if not config.auto_programar_activo():
        return 0
    programadas = 0
    for pub in repos.listar_publicaciones(estado=ESTADO_APROBADO):
        if programar_si_aprobada(pub["id"]) is not None:
            programadas += 1
    if programadas:
        _log.info("Auto-programación: %d pieza(s) aprobada(s) encoladas.", programadas)
    return programadas
