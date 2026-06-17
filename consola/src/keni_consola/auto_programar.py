"""Auto-programación: una pieza con sus 2 likes pasa SOLA a `programado` en su próximo hueco.

COLAPSO 2026-06: ya no hay estado de reposo `aprobado`. Una pieza queda `en_revision` hasta
que junta los 2 likes (los OK humanos); en ese momento, en vez de esperar una programación
manual, se ENCOLA al próximo hueco libre de sus franjas (la misma lógica del botón "encolar":
`api.piezas.calcular_hueco_para`), respetando los gates de la programación manual:

  - Gate A (gobernanza): la pieza debe tener su cadena de likes CUMPLIENDO el mínimo
    (`config.min_aprobaciones`, def 2 = "cuatro ojos"). Sin cadena o sin los likes -> no programa.
  - Gate B (verificación): cero comentarios sin resolver (una objeción pendiente bloquea programar;
    incluye los de la Crítica IA).
  - Debe existir una franja aplicable a su (marca, red). Si no hay hueco, la pieza se queda
    `en_revision` (no se inventa fecha): saldrá programada en cuanto se configure una franja.

NO publica: deja la pieza en `programado` con su `fecha_programada`; el programador del server la
prepara (DRY-RUN) al vencer, y el posteo real sigue gated por `KENI_PUBLICAR_REAL`.

Se invoca SÍNCRONO en la ruta de aprobación (justo tras registrarse el último like), no desde un
daemon: la aprobación ocurre por la UI, así que encolar ahí es inmediato. Gateado por
`KENI_AUTO_PROGRAMAR` (def ON; ver `config.auto_programar_activo`). No crea esquema: solo cambia
`estado`/`fecha_programada`, como el encolado manual.
"""

from __future__ import annotations

import logging
from typing import Any

from . import config, repos
from .dominio import colaboracion
from .estados import ESTADO_EN_REVISION

_log = logging.getLogger("keni_consola.auto_programar")


def programar_si_aprobada(pieza_id: str) -> dict[str, Any] | None:
    """Si la pieza está `en_revision` con sus 2 likes y pasa los gates, la encola a su hueco.

    Devuelve la publicación ya `programado` si la encoló; `None` si no aplicaba (no está en
    revisión, le faltan likes, flag apagado, comentario sin resolver o sin franja/hueco).
    Idempotente y best-effort: solo actúa sobre piezas `en_revision` con el mínimo de likes,
    así que reinvocarla no reprograma una ya programada.
    """
    if not config.auto_programar_activo():
        return None

    pub = repos.obtener_pieza(pieza_id)
    if pub is None or pub.get("estado") != ESTADO_EN_REVISION:
        return None

    # Gate A (gobernanza): la pieza debe tener su cadena de likes cumpliendo el mínimo (los 2 OK).
    # Sin cadena (no se mandó a revisión por el flujo) o sin los likes acumulados -> no programa.
    cadena = repos.listar_aprobaciones(pieza_id)
    if not cadena:
        return None
    cumple, _ = colaboracion.cumple_minimo_aprobaciones(cadena, config.min_aprobaciones())
    if not cumple:
        return None

    # Gate B (verificación): un comentario sin resolver es una objeción pendiente; no programar.
    plat = repos.obtener_pieza_fila(pieza_id)
    if repos.comentarios_sin_resolver((plat or {}).get("publicacion_id", "") or "", pieza_id):
        return None

    # Próximo hueco libre de sus franjas (reusa la lógica del encolado manual). Import perezoso:
    # `api.piezas` es capa API; importarlo a nivel de módulo enredaría el grafo de imports.
    # `_encolar_en_hueco_libre` calcula el hueco Y escribe con el BACKSTOP de unicidad de slot
    # (índice parcial `idx_parrilla_slot_uniq`) + reintento: si otra pieza (o el encolado manual
    # de un humano) toma el slot a la vez, recalcula y reintenta en vez de doble-reservarlo.
    from .api.piezas import _encolar_en_hueco_libre

    # CAS `estado_esperado=ESTADO_EN_REVISION`: la AUTO-programación solo escribe `programado` si la
    # pieza SIGUE `en_revision` en el momento de la escritura. Entre la lectura de arriba y aquí otro
    # flujo (edición que la resetea a borrador, "deshacer like", reprograma manual) pudo moverla;
    # sin el CAS la RESUCITARÍAMOS a `programado`, pisando el estado/fecha del humano y haciendo
    # mentir al calendario. El encolado MANUAL no pasa CAS (override deliberado).
    actualizada, hubo_hueco = _encolar_en_hueco_libre(pub, estado_esperado=ESTADO_EN_REVISION)
    if not hubo_hueco:
        return None  # sin franja aplicable: se queda en_revision (sin inventar fecha).

    # `actualizada is None` con `hubo_hueco=True`: o se borró en la carrera, o el CAS no aplicó (la
    # pieza dejó de estar `en_revision`). En ambos casos NO la programamos: best-effort, sin error.
    if actualizada is not None:
        _log.info(
            "Auto-programada pieza %s en %s.",
            pieza_id, actualizada.get("fecha_programada"),
        )
    return actualizada
