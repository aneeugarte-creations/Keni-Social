"""Reparto de NOTIFICACIONES in-app para CAMBIOS DE TURNO (swaps).

Mismo "cajon de la campana" que `dominio/notificaciones`, pero para el ciclo de vida de
un cambio de turno: el DESTINATARIO se entera de que le proponen un cambio, el APROBADOR
(admin) de que hay uno esperando su OK, y AMBAS partes del desenlace. Es la senal que
retira el "oye, me cubres el turno?" del chat de WhatsApp: el equipo se entera in-app sin
que nadie tenga que avisar por fuera (mision keni: menos chat ad-hoc, mas flujo).

Reglas del reparto:
  - Al ACTOR que dispara el evento NO se le auto-notifica (se excluye siempre).
  - Solicitud  -> al destinatario ("tienes algo que responder").
  - Aceptado   -> a los admin ("falta tu aprobacion").
  - Rechazado por el destinatario -> al solicitante.
  - Decision de admin (aplicado/rechazado_admin) -> a solicitante Y destinatario.
  - Cancelado  -> al destinatario (que ya lo tenia en su lista).

Todo es BEST-EFFORT: un fallo aqui NUNCA debe tumbar la accion que lo provoco (crear,
aceptar, rechazar, aprobar o cancelar el swap). Cada entrada publica atrapa y loguea.

La campana esta ACOTADA a la marca del swap (la rejilla a la que pertenece su turno); el
`enlace` lleva a la pestana «Cambios y ausencias» de Turnos.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from .. import auth, repos
from ..estados import ROL_ADMIN

log = logging.getLogger("keni_consola.notificaciones_turnos")

# Un unico tipo para todo el ciclo del swap (el `resumen` lleva el detalle). El front cae
# al icono de campana si no lo conoce; le damos icono propio en `CampanaNotificaciones`.
TIPO_CAMBIO_TURNO = "cambio_turno"

# Aviso al admin de que una AUSENCIA deja turnos sin cubrir (la otra cara del cruce
# ausencia<->turno). El front cae al icono de campana si no lo conoce.
TIPO_AUSENCIA_DESCUBIERTO = "ausencia_descubierto"

# Deep-link a la pestana de cambios/ausencias (el shell de Turnos la abre por `?tab=`).
ENLACE_CAMBIOS = "/operacion/turnos?tab=cambios-ausencias"

# Deep-link al Calendario: la rejilla donde el coordinador reasigna el turno descubierto.
ENLACE_CALENDARIO = "/operacion/turnos?tab=calendario"


def _ids_admin() -> set[str]:
    """Ids de los usuarios con rol admin (los aprobadores de un cambio de turno)."""
    try:
        return {u["id"] for u in auth.listar_usuarios() if u.get("rol") == ROL_ADMIN}
    except Exception:  # noqa: BLE001 -- leer usuarios no debe romper el reparto
        log.exception("No se pudieron listar admins para notificar el cambio de turno.")
        return set()


def _actor_id(actor: dict[str, Any] | None) -> str:
    return (actor or {}).get("id", "") or ""


def _emitir(
    destinatarios: Iterable[str],
    *,
    marca_id: str,
    resumen: str,
    actor: dict[str, Any] | None = None,
    excluir: Iterable[str] = (),
    tipo: str = TIPO_CAMBIO_TURNO,
    enlace: str = ENLACE_CAMBIOS,
) -> int:
    """Crea UNA notificacion por destinatario unico (salta vacios/excluidos)."""
    vistos: set[str] = {x for x in excluir if x}
    creadas = 0
    for uid in destinatarios:
        if not uid or uid in vistos:
            continue
        vistos.add(uid)
        try:
            repos.crear_notificacion(
                usuario_id=uid,
                marca_id=marca_id,
                tipo=tipo,
                actor=actor,
                resumen=resumen,
                enlace=enlace,
            )
            creadas += 1
        except Exception:  # noqa: BLE001 -- una noti fallida no frena al resto
            log.exception("No se pudo crear notificacion de turno para %s.", uid)
    return creadas


# --------------------------------------------------------------------------- #
# Entradas de alto nivel (las llaman los handlers de api/rota/swaps)           #
# --------------------------------------------------------------------------- #


def tras_solicitud(swap: dict[str, Any], actor: dict[str, Any] | None = None) -> None:
    """A propuso un cambio: avisa al DESTINATARIO de que tiene algo que responder."""
    try:
        solicitante = swap.get("solicitante_nombre") or "Un compañero"
        _emitir(
            {swap.get("destinatario_id", "")},
            marca_id=swap.get("marca", "") or "",
            resumen=f"{solicitante} te propone un cambio de turno",
            actor=actor,
            excluir={_actor_id(actor)},
        )
    except Exception:  # noqa: BLE001 -- notificar nunca rompe el solicitar
        log.exception("Fallo notificando la solicitud de cambio %s.", swap.get("id"))


def tras_respuesta_destinatario(
    swap: dict[str, Any], decision: str, actor: dict[str, Any] | None = None
) -> None:
    """B respondio. `aceptado` -> avisa a los admin (falta su OK); `rechazado` -> avisa a A."""
    try:
        marca_id = swap.get("marca", "") or ""
        destinatario = swap.get("destinatario_nombre") or "Tu compañero"
        excluir = {_actor_id(actor)}
        if decision == "aceptado":
            _emitir(
                _ids_admin(),
                marca_id=marca_id,
                resumen=f"{destinatario} aceptó un cambio de turno: falta tu aprobación",
                actor=actor,
                excluir=excluir,
            )
        elif decision == "rechazado":
            _emitir(
                {swap.get("solicitante_id", "")},
                marca_id=marca_id,
                resumen=f"{destinatario} rechazó tu cambio de turno",
                actor=actor,
                excluir=excluir,
            )
    except Exception:  # noqa: BLE001 -- notificar nunca rompe el aceptar/rechazar
        log.exception("Fallo notificando la respuesta al cambio %s.", swap.get("id"))


def tras_decision_admin(
    swap: dict[str, Any], decision: str, actor: dict[str, Any] | None = None
) -> None:
    """El admin decidio: avisa a AMBAS partes (solicitante y destinatario)."""
    try:
        if decision == "aplicado":
            resumen = "Tu cambio de turno fue aprobado y aplicado"
        elif decision == "rechazado_admin":
            resumen = "Tu cambio de turno fue rechazado por administración"
        else:
            return
        _emitir(
            {swap.get("solicitante_id", ""), swap.get("destinatario_id", "")},
            marca_id=swap.get("marca", "") or "",
            resumen=resumen,
            actor=actor,
            excluir={_actor_id(actor)},
        )
    except Exception:  # noqa: BLE001 -- notificar nunca rompe el aprobar/rechazar
        log.exception("Fallo notificando la decisión de admin del cambio %s.", swap.get("id"))


def tras_cancelacion(swap: dict[str, Any], actor: dict[str, Any] | None = None) -> None:
    """A cancelo su solicitud: avisa al DESTINATARIO (que ya la tenia en su lista)."""
    try:
        solicitante = swap.get("solicitante_nombre") or "Un compañero"
        _emitir(
            {swap.get("destinatario_id", "")},
            marca_id=swap.get("marca", "") or "",
            resumen=f"{solicitante} canceló su solicitud de cambio de turno",
            actor=actor,
            excluir={_actor_id(actor)},
        )
    except Exception:  # noqa: BLE001 -- notificar nunca rompe el cancelar
        log.exception("Fallo notificando la cancelación del cambio %s.", swap.get("id"))


def tras_ausencia_con_huecos(
    *,
    miembro_nombre: str,
    n_huecos: int,
    marcas: Iterable[str],
    actor: dict[str, Any] | None = None,
) -> None:
    """Una ausencia deja `n_huecos` turnos de cobertura sin cubrir: avisa a los admin.

    Persiste el aviso en la campana —una por marca afectada— en vez de fiarlo al toast
    efimero de quien la registro: el coordinador se entera del descubierto in-app y lo
    resuelve, en vez de toparselo el dia del partido. Al ACTOR que la registro no se le
    auto-notifica (ya vio el aviso al guardar). Best-effort: jamas tumba el alta de la
    ausencia.
    """
    if n_huecos <= 0:
        return
    try:
        nombre = miembro_nombre or "Un compañero"
        plural = "" if n_huecos == 1 else "s"
        resumen = f"La ausencia de {nombre} deja {n_huecos} turno{plural} sin cubrir"
        admins = _ids_admin()
        excluir = {_actor_id(actor)}
        for marca_id in {m or "" for m in marcas}:
            _emitir(
                admins,
                marca_id=marca_id,
                resumen=resumen,
                actor=actor,
                excluir=excluir,
                tipo=TIPO_AUSENCIA_DESCUBIERTO,
                enlace=ENLACE_CALENDARIO,
            )
    except Exception:  # noqa: BLE001 -- notificar nunca rompe el registrar la ausencia
        log.exception("Fallo notificando el hueco por ausencia de %s.", miembro_nombre)
