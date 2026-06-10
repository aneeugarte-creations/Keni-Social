"""Etapa de AVANCE del pipeline: las piezas COMPLETAS pasan SOLAS a revisión.

El pipeline produce hasta dejar la pieza completa (copy + foto real) y ahí se paraba:
la transición borrador -> en_revision era un clic humano por pieza ("Enviar a revisión"),
así que la producción automática se acumulaba en "En borrador" (cientos de piezas) y la
cola de aprobación se quedaba vacía. Esta etapa hace ese clic: un borrador COMPLETO entra
solo a la cola de revisión con su cadena simple, exactamente igual que si lo enviara una
persona (mismo CAS, misma cadena de "dale el OK").

EL GATE HUMANO NO CAMBIA: nada se aprueba ni publica solo. Solo se mueve la pieza a la
cola donde el equipo da (o niega) sus OK. Por eso esta etapa NO tiene toggle: corre
INCONDICIONALMENTE —«borrador» dejó de ser un estado donde descanse una pieza completa—,
bajo el único maestro general (`KENI_MAQUINA`). No gasta IA, no publica y es reversible
(una devolución la saca de la cola). No hay exclusión por marca.

REGLAS DE SELECCIÓN (`piezas_para_avance`, pura):
  - Estado `borrador` y COMPLETA de verdad: la misma derivación que pinta el feed
    (`etapa_ia == "lista_para_revisar"`, del contenido real, no de flags almacenados).
  - TAMBIÉN las devueltas: "borrador" no es un estado donde vivir — una pieza completa
    pertenece a la cola de revisión (decisión de producto, 10-jun). Tras una devolución
    (dos dislikes) la pieza descansa el REPOSO y vuelve sola a la cola con su cadena
    fresca, igual que si la re-enviara una persona; quien la devuelve tiene ese margen
    para editarla (o descartarla) antes de que reaparezca.
  - REPOSO: sin ediciones en los últimos minutos (`_REPOSO_MINUTOS`), para no arrancar
    de las manos una pieza que alguien está editando ahora mismo.
  - Marca no excluida de la etapa.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from .. import config, repos
from ..dominio import colaboracion
from ..dominio.publicaciones import publicacion_a_dict
from ..estados import ESTADO_EN_REVISION
from ..tiempo import ahora_iso

__all__ = ["ejecutar_avance", "piezas_para_avance"]

_log = logging.getLogger("keni_consola.pipeline_contenido")

# Minutos sin ediciones antes de mover una pieza: si `fecha_actualizacion` es más reciente,
# alguien (o la propia tubería) sigue trabajándola y se espera al siguiente barrido.
_REPOSO_MINUTOS = 10

# Cap de envíos por barrido: acota el trabajo de un tick (el daemon barre cada pocos
# segundos, así que un backlog grande se drena en minutos igualmente).
_MAX_POR_BARRIDO = 50


def _en_reposo(pub: dict[str, Any], ahora: str) -> bool:
    """True si la pieza lleva al menos `_REPOSO_MINUTOS` sin ediciones (o sin timestamp legible)."""
    ts = str(pub.get("fecha_actualizacion") or pub.get("fecha_creacion") or "").strip()
    if not ts:
        return True
    try:
        return datetime.fromisoformat(ahora) - datetime.fromisoformat(ts) >= timedelta(
            minutes=_REPOSO_MINUTOS
        )
    except (TypeError, ValueError):
        return True


def piezas_para_avance(
    pubs: list[dict[str, Any]], *, ahora: str, maximo: int = _MAX_POR_BARRIDO
) -> list[dict[str, Any]]:
    """Filtra los borradores que deben pasar a revisión (PURA; reglas en el módulo)."""
    elegidas: list[dict[str, Any]] = []
    for pub in pubs:
        if pub.get("estado") != "borrador":
            continue
        if not _en_reposo(pub, ahora):
            continue
        # Completa DE VERDAD (copy + asset del formato): la misma derivación del feed.
        if publicacion_a_dict(pub).get("etapa_ia") != "lista_para_revisar":
            continue
        elegidas.append(pub)
        if len(elegidas) >= maximo:
            break
    return elegidas


def _enviar(pub: dict[str, Any]) -> bool:
    """Transición borrador -> en_revision + cadena simple (idéntico al envío humano).

    Mismo CAS que `api/aprobacion.enviar_a_revision`: si otro flujo movió la pieza entre
    el snapshot y la escritura, no toca nada (False; no es un error). El autor de la pieza
    queda como remitente (vive en el contenido padre, fijado al crearla).
    """
    actualizada = repos.transicionar_estado_publicacion(
        pub["id"],
        "borrador",
        ESTADO_EN_REVISION,
        {
            "enviado_a_revision_en": ahora_iso(),
            "revisor_id": "",
            "revisor_nombre": "",
            "revisado_en": "",
        },
    )
    if actualizada is None:
        return False
    # Import tardío: `api.colaboracion` (punto único de montaje de cadenas) importa la pila
    # HTTP; los tests del pipeline no la pagan hasta que de verdad se envía algo.
    from ..api.colaboracion import montar_cadena_aprobacion

    plat = repos.obtener_contenido_plataforma(pub["id"])
    montar_cadena_aprobacion(pub["id"], plat or {}, colaboracion.cadena_simple(), con_cargos=False)
    return True


def ejecutar_avance() -> list[dict[str, Any]]:
    """Etapa de AVANCE del barrido (tras arte): borradores completos -> cola de revisión.

    Incondicional bajo el único maestro `KENI_MAQUINA` (sin toggle propio ni exclusión por
    marca). Best-effort: un fallo por pieza se loguea y se sigue. Devuelve las piezas enviadas.
    """
    if not config.maquina_activa():
        return []
    try:
        pubs = repos.listar_publicaciones(estado="borrador")
    except Exception:  # noqa: BLE001 -- sin tablero, la etapa no actúa
        _log.exception("pipeline: no se pudieron leer los borradores para la etapa de avance.")
        return []
    enviadas: list[dict[str, Any]] = []
    for pub in piezas_para_avance(pubs, ahora=ahora_iso()):
        try:
            if _enviar(pub):
                enviadas.append(pub)
        except Exception:  # noqa: BLE001 -- una pieza que falla no aborta la etapa
            _log.exception(
                "pipeline: falló el avance a revisión de la pieza %s (marca %s).",
                pub.get("id", ""),
                pub.get("marca", ""),
            )
    return enviadas
