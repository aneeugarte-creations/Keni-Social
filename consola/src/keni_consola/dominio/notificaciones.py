"""Reparto de NOTIFICACIONES in-app (el "cajon" de la campana, junto al selector de marca).

La persistencia vive en `db.py`/`repos` (tabla `notificaciones`); aqui decidimos A QUIEN
notificar cuando pasa algo en una pieza. Reglas (acordadas con el equipo AMX):

  - Te SUSCRIBES a una pieza si eres su autor, comentaste, la aprobaste/rechazaste, o te
    mencionaron (@) en un comentario suyo. `interesados_en` calcula ese conjunto al vuelo
    (sin tabla de suscripcion aparte): autor + comentaristas + decisores + mencionados.
  - El COORDINADOR de la marca recibe TODO lo que se aprueba en su marca (este suscrito o no).
  - El DIRECTOR no se suscribe automaticamente: solo le llega si lo MENCIONAN.
  - Al ACTOR que dispara el evento NO se le auto-notifica.
  - El cajon esta ACOTADO a la marca: cada notificacion lleva su `marca_id` y el front solo
    muestra la marca activa.

Todo es BEST-EFFORT: un fallo aqui NUNCA debe tumbar la accion que lo provoco (comentar,
aprobar, publicar). Cada entrada publica atrapa y loguea.

TIPOS: `mencion` · `comentario` · `aprobacion` · `rechazo` · `publicacion` · `asignacion`.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from .. import auth, repos

log = logging.getLogger("keni_consola.notificaciones")

TIPOS: tuple[str, ...] = (
    "mencion",
    "comentario",
    "aprobacion",
    "rechazo",
    "publicacion",
    "asignacion",
)


def _nombre_actor(actor: dict[str, Any] | None) -> str:
    actor = actor or {}
    return (actor.get("usuario") or actor.get("nombre") or "").strip()


def _titulo(contenido: dict[str, Any] | None) -> str:
    return ((contenido or {}).get("titulo") or "").strip() or "una pieza"


def _resumen(tipo: str, actor_nombre: str, titulo: str, red_nombre: str = "") -> str:
    """Frase corta en espanol para la UI del cajon."""
    quien = actor_nombre or "Alguien"
    pieza = f"«{titulo}»"
    if tipo == "mencion":
        return f"{quien} te mencionó en {pieza}"
    if tipo == "comentario":
        return f"{quien} comentó en {pieza}"
    if tipo == "aprobacion":
        return f"{quien} dio su OK a {pieza}"
    if tipo == "rechazo":
        return f"{quien} rechazó {pieza}"
    if tipo == "publicacion":
        cola = f" en {red_nombre}" if red_nombre else ""
        return f"Se publicó {pieza}{cola}"
    if tipo == "asignacion":
        return f"{quien} te asignó {pieza}"
    return f"{quien}: {pieza}"


def interesados_en(
    contenido_id: str, contenido: dict[str, Any] | None = None
) -> set[str]:
    """Ids de usuarios SUSCRITOS a una pieza: autor + comentaristas + decisores + mencionados."""
    ids: set[str] = set()
    cont = contenido or repos.obtener_contenido(contenido_id) or {}
    if cont.get("autor_id"):
        ids.add(cont["autor_id"])
    for c in repos.listar_comentarios(contenido_id):
        if c.get("autor_id"):
            ids.add(c["autor_id"])
        for m in c.get("menciones") or []:
            if m:
                ids.add(m)
    for plat in repos.listar_contenido_plataforma(contenido_id):
        for nivel in repos.listar_aprobaciones(plat.get("id", "")):
            decisor = nivel.get("decisor_id") or ""
            if decisor and decisor != "auto":
                ids.add(decisor)
    return ids


def _coordinadores_de_marca(marca_id: str) -> set[str]:
    """Ids de los COORDINADORES de una marca (cargo `coordinador*` y la marca asignada)."""
    if not marca_id:
        return set()
    out: set[str] = set()
    try:
        usuarios = auth.listar_usuarios()
    except Exception:  # noqa: BLE001 -- leer usuarios no debe romper el reparto
        log.exception("No se pudieron listar usuarios para coordinadores de %r.", marca_id)
        return out
    for u in usuarios:
        cargo = (u.get("cargo") or "").strip().lower()
        if marca_id in (u.get("marcas") or []) and cargo.startswith("coordinador"):
            out.add(u["id"])
    return out


def _repartir(
    destinatarios: Iterable[str],
    *,
    marca_id: str,
    tipo: str,
    resumen: str,
    contenido_id: str = "",
    plataforma_id: str = "",
    actor: dict[str, Any] | None = None,
    enlace: str = "",
    excluir: Iterable[str] = (),
) -> int:
    """Crea UNA notificacion por destinatario unico (salta vacios y excluidos). Best-effort."""
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
                contenido_id=contenido_id,
                plataforma_id=plataforma_id,
                actor=actor,
                resumen=resumen,
                enlace=enlace,
            )
            creadas += 1
        except Exception:  # noqa: BLE001 -- una noti fallida no frena al resto
            log.exception("No se pudo crear notificacion %s para %s.", tipo, uid)
    return creadas


# --------------------------------------------------------------------------- #
# Entradas de alto nivel (las llaman los api/*; todas best-effort)             #
# --------------------------------------------------------------------------- #


def tras_comentario(
    contenido: dict[str, Any],
    comentario: dict[str, Any],
    actor: dict[str, Any] | None,
) -> None:
    """Un comentario nuevo: notifica a los MENCIONADOS (mencion) y al resto de interesados."""
    try:
        contenido_id = contenido.get("id", "") or ""
        marca_id = contenido.get("marca", "") or ""
        titulo = _titulo(contenido)
        nombre = _nombre_actor(actor)
        actor_id = (actor or {}).get("id", "") or ""
        plataforma_id = comentario.get("plataforma_id", "") or ""
        menciones = {m for m in (comentario.get("menciones") or []) if m}

        # 1) Mencionados: prioridad mencion (incluye al director si lo etiquetan).
        _repartir(
            menciones,
            marca_id=marca_id,
            tipo="mencion",
            resumen=_resumen("mencion", nombre, titulo),
            contenido_id=contenido_id,
            plataforma_id=plataforma_id,
            actor=actor,
            excluir={actor_id},
        )
        # 2) Resto de suscritos: comentario (sin duplicar a los ya mencionados ni al actor).
        _repartir(
            interesados_en(contenido_id, contenido),
            marca_id=marca_id,
            tipo="comentario",
            resumen=_resumen("comentario", nombre, titulo),
            contenido_id=contenido_id,
            plataforma_id=plataforma_id,
            actor=actor,
            excluir={actor_id} | menciones,
        )
    except Exception:  # noqa: BLE001 -- notificar nunca rompe el comentar
        log.exception("Fallo notificando el comentario de %s.", contenido.get("id"))


def tras_decision(
    plataforma: dict[str, Any],
    contenido: dict[str, Any],
    decision: str,
    actor: dict[str, Any] | None,
) -> None:
    """Una decision de aprobacion: OK -> interesados + coordinador; rechazo -> interesados."""
    try:
        contenido_id = contenido.get("id", "") or ""
        marca_id = contenido.get("marca", "") or ""
        titulo = _titulo(contenido)
        nombre = _nombre_actor(actor)
        actor_id = (actor or {}).get("id", "") or ""
        plataforma_id = plataforma.get("id", "") or ""
        interesados = interesados_en(contenido_id, contenido)

        if decision == "aprobado":
            destinatarios = interesados | _coordinadores_de_marca(marca_id)
            _repartir(
                destinatarios,
                marca_id=marca_id,
                tipo="aprobacion",
                resumen=_resumen("aprobacion", nombre, titulo),
                contenido_id=contenido_id,
                plataforma_id=plataforma_id,
                actor=actor,
                excluir={actor_id},
            )
        elif decision == "rechazado":
            _repartir(
                interesados,
                marca_id=marca_id,
                tipo="rechazo",
                resumen=_resumen("rechazo", nombre, titulo),
                contenido_id=contenido_id,
                plataforma_id=plataforma_id,
                actor=actor,
                excluir={actor_id},
            )
    except Exception:  # noqa: BLE001 -- notificar nunca rompe el OK/rechazo
        log.exception("Fallo notificando la decision de %s.", plataforma.get("id"))


def tras_publicacion(
    *,
    contenido_id: str,
    plataforma_id: str,
    marca_id: str,
    titulo: str,
    red_nombre: str = "",
) -> None:
    """Una pieza se publico: notifica a todos sus interesados (sin actor: la dispara el sistema)."""
    try:
        _repartir(
            interesados_en(contenido_id),
            marca_id=marca_id,
            tipo="publicacion",
            resumen=_resumen("publicacion", "", titulo or "una pieza", red_nombre),
            contenido_id=contenido_id,
            plataforma_id=plataforma_id,
        )
    except Exception:  # noqa: BLE001 -- notificar nunca rompe la publicacion
        log.exception("Fallo notificando la publicacion de %s.", contenido_id)


def tras_asignacion(
    contenido: dict[str, Any],
    actor: dict[str, Any] | None,
) -> None:
    """El manager EMPUJA una pieza a alguien: avisa SOLO al nuevo responsable (no al actor).

    Es la señal que retira el «oye, te paso esto» del chat: el asignado se entera in-app de
    que le tocó algo sin que nadie tenga que avisarle por WhatsApp. Si la pieza queda sin
    responsable (liberada) NO notifica —eso es `soltar`—; y si el manager se la asigna a sí
    mismo tampoco, porque el actor se excluye. Best-effort: un fallo aquí no frena la asignación.
    """
    try:
        destinatario = (contenido.get("responsable_id") or "").strip()
        if not destinatario:
            return
        _repartir(
            {destinatario},
            marca_id=contenido.get("marca", "") or "",
            tipo="asignacion",
            resumen=_resumen("asignacion", _nombre_actor(actor), _titulo(contenido)),
            contenido_id=contenido.get("id", "") or "",
            actor=actor,
            excluir={(actor or {}).get("id", "") or ""},
        )
    except Exception:  # noqa: BLE001 -- notificar nunca rompe la asignación
        log.exception("Fallo notificando la asignación de %s.", contenido.get("id"))
