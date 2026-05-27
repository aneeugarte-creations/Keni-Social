"""Dominio APROBACION de equipo (#9, Fase 3): transiciones del flujo de revision.

Capa de logica PURA sobre las publicaciones. No persiste ni lee HTTP: recibe el
dict publico de una publicacion + el autor de la peticion y decide si una transicion
de revision es valida, devolviendo los CAMPOS a aplicar (o un error en espanol). El
handler (`api/aprobacion.py`) la consume y delega la escritura en `repos`.

FLUJO (sobre los estados ya existentes, ver `estados.ESTADOS_PUBLICACION`):

    borrador --enviar--> en_revision --aprobar--> aprobado --programar--> programado
                              |
                              +--rechazar--> borrador

REGLA DE EQUIPO (separacion de funciones, ~16 personas): quien APRUEBA/RECHAZA no
puede ser el mismo que envio la pieza a revision, SALVO que sea admin (un admin puede
desatascar su propia pieza). Asi la aprobacion es de "otro par de ojos", el corazon de
"el humano aprueba" (frontera del producto: el sistema no publica solo).

Los campos de revision (`revisor_id`, `revisor_nombre`, `revisado_en`,
`enviado_a_revision_en`) son ADITIVOS y retrocompatibles: una pieza legada sin ellos
se lee con "" (sin revisor), nunca rompe la lectura ni el flujo.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..estados import ESTADO_APROBADO, ESTADO_EN_REVISION, ROL_ADMIN

# Campos de revision que viven en el YAML de la publicacion (ademas de `estado`).
# Aditivos: ausentes en piezas legadas => "" al leer (ver `ficheros._parsear_publicacion`).
CAMPOS_REVISION: tuple[str, ...] = (
    "enviado_a_revision_en",
    "revisor_id",
    "revisor_nombre",
    "revisado_en",
)


def _ahora_iso() -> str:
    """Fecha-hora ISO a segundos (mismo formato que el resto del dominio)."""
    return datetime.now().isoformat(timespec="seconds")


def _es_admin(autor: dict[str, Any] | None, rol: str | None) -> bool:
    """True si la peticion la hace un admin (puede saltarse la regla de 'otro par de ojos').

    `rol` lo resuelve el handler desde `request.state.usuario`; el acceso por TOKEN de
    bootstrap (sin usuario) cuenta como mantenimiento con plenos permisos = admin.
    """
    if autor is None:  # token de bootstrap / sin sesion => mantenimiento (admin)
        return True
    return rol == ROL_ADMIN


def enviar_a_revision(
    pub: dict[str, Any], autor: dict[str, str] | None
) -> tuple[dict[str, Any] | None, str | None]:
    """Envia una pieza a revision: `borrador` -> `en_revision`.

    Devuelve `(campos, None)` con los campos a aplicar, o `(None, mensaje)` si la
    transicion no es valida (la pieza no esta en borrador). `autor` puede ser None
    (token de bootstrap): se registra autoria vacia, igual que en el resto del flujo.
    """
    estado = pub.get("estado")
    if estado != "borrador":
        return None, "Solo se puede enviar a revisión una pieza en borrador."
    autor = autor or {}
    return (
        {
            "estado": ESTADO_EN_REVISION,
            "enviado_a_revision_en": _ahora_iso(),
            # Una pieza que vuelve a revision arranca limpia de revisor previo.
            "revisor_id": "",
            "revisor_nombre": "",
            "revisado_en": "",
            # Atribucion de autoria al enviar (no pisa al autor original si ya existe).
            "autor_id": pub.get("autor_id") or autor.get("id", ""),
            "autor_nombre": pub.get("autor_nombre") or autor.get("usuario", ""),
        },
        None,
    )


def aprobar(
    pub: dict[str, Any], autor: dict[str, str] | None, *, rol: str | None
) -> tuple[dict[str, Any] | None, str | None]:
    """Aprueba una pieza en revision: `en_revision` -> `aprobado`, fijando el revisor.

    Regla de equipo: el revisor NO puede ser el autor que la envio, salvo admin. Devuelve
    `(campos, None)` o `(None, mensaje)`.
    """
    estado = pub.get("estado")
    if estado != ESTADO_EN_REVISION:
        return None, "Solo se puede aprobar una pieza que está en revisión."
    error = _revisor_distinto_del_autor(pub, autor, rol)
    if error is not None:
        return None, error
    autor = autor or {}
    return (
        {
            "estado": ESTADO_APROBADO,
            "revisor_id": autor.get("id", ""),
            "revisor_nombre": autor.get("usuario", ""),
            "revisado_en": _ahora_iso(),
        },
        None,
    )


def rechazar(
    pub: dict[str, Any], autor: dict[str, str] | None, *, rol: str | None
) -> tuple[dict[str, Any] | None, str | None]:
    """Rechaza (devuelve a borrador) una pieza en revision: `en_revision` -> `borrador`.

    Misma regla de equipo que `aprobar`: quien rechaza no puede ser el autor (salvo
    admin). Registra al revisor que la devolvio y la marca de tiempo.
    """
    estado = pub.get("estado")
    if estado != ESTADO_EN_REVISION:
        return None, "Solo se puede rechazar una pieza que está en revisión."
    error = _revisor_distinto_del_autor(pub, autor, rol)
    if error is not None:
        return None, error
    autor = autor or {}
    return (
        {
            "estado": "borrador",
            "revisor_id": autor.get("id", ""),
            "revisor_nombre": autor.get("usuario", ""),
            "revisado_en": _ahora_iso(),
        },
        None,
    )


def _revisor_distinto_del_autor(
    pub: dict[str, Any], autor: dict[str, str] | None, rol: str | None
) -> str | None:
    """None si quien revisa puede hacerlo; mensaje de error si seria auto-aprobacion.

    El autor de la pieza no puede aprobar/rechazar su propia pieza (otro par de ojos),
    salvo que sea admin. El acceso por token (autor None) es mantenimiento => permitido.
    """
    if _es_admin(autor, rol):
        return None
    autor_id = (autor or {}).get("id", "")
    if autor_id and autor_id == (pub.get("autor_id") or ""):
        return "No puedes aprobar ni rechazar tu propia pieza; debe revisarla otra persona."
    return None
