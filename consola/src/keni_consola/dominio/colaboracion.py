"""Dominio COLABORACION: logica PURA de la aprobacion multinivel de una pieza.

Capa de logica sin persistencia ni HTTP: recibe la cadena de niveles de aprobacion de
una `contenido_plataforma` (lista de dicts tal cual la guarda `db`) + quien decide, y
decide si una decision es valida, que campos aplicar al nivel y como queda el ESTADO
GLOBAL de la cadena. El handler (`api/colaboracion.py`) la consume y delega la escritura
en `repos`.

MODELO (inspirado en Planable › multi-level approval): una pieza tiene una CADENA de
niveles ordenados (p. ej. Edicion -> Coordinacion -> Direccion). Cada nivel arranca
`pendiente`; un decisor lo `aprueba` o lo `rechaza`. Reglas:

  - Se decide POR ORDEN: solo el primer nivel `pendiente` (el mas bajo aun sin decidir)
    acepta decision. No se puede aprobar Direccion si Coordinacion sigue pendiente.
  - Un `rechazado` en cualquier nivel PARA la cadena (la pieza vuelve a la redaccion).
  - La pieza esta TOTALMENTE aprobada cuando TODOS los niveles estan `aprobado`.
  - Separacion de funciones (como el flujo legado #9): el decisor de un nivel NO puede
    ser el autor que pidio la revision, salvo admin. "Otro par de ojos" por nivel.

`estado_cadena(cadena)` resume la cadena en uno de: "sin_cadena" (vacia), "pendiente"
(quedan niveles por decidir), "aprobado" (todos aprobados) o "rechazado" (alguno
rechazado). Es lo que la UI pinta y lo que el resto del flujo puede consultar.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..estados import (
    DECISION_APROBADO,
    DECISION_PENDIENTE,
    DECISION_RECHAZADO,
    ROL_ADMIN,
)


def _ahora_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def estado_cadena(cadena: list[dict[str, Any]]) -> str:
    """Resume una cadena de niveles en su estado global.

    "sin_cadena" si esta vacia; "rechazado" si algun nivel lo esta; "aprobado" si TODOS
    lo estan; "pendiente" en cualquier otro caso (quedan niveles por decidir).
    """
    if not cadena:
        return "sin_cadena"
    decisiones = [n.get("decision") for n in cadena]
    if DECISION_RECHAZADO in decisiones:
        return DECISION_RECHAZADO
    if all(d == DECISION_APROBADO for d in decisiones):
        return DECISION_APROBADO
    return DECISION_PENDIENTE


def nivel_actual(cadena: list[dict[str, Any]]) -> dict[str, Any] | None:
    """El primer nivel `pendiente` por orden (el que toca decidir); None si no queda.

    Si algun nivel ya esta `rechazado`, la cadena esta parada: devuelve None (no hay
    siguiente decision util hasta que se reinicie la cadena).
    """
    if any(n.get("decision") == DECISION_RECHAZADO for n in cadena):
        return None
    ordenada = sorted(cadena, key=lambda n: n.get("nivel", 0))
    for nivel in ordenada:
        if nivel.get("decision") == DECISION_PENDIENTE:
            return nivel
    return None


def _es_admin(rol: str | None, autor: dict[str, Any] | None) -> bool:
    """True si la peticion la hace un admin (o el acceso por token sin sesion = mantenimiento)."""
    if autor is None:
        return True
    return rol == ROL_ADMIN


def decidir(
    nivel: dict[str, Any],
    cadena: list[dict[str, Any]],
    decision: str,
    decisor: dict[str, str] | None,
    *,
    rol: str | None,
    comentario: str = "",
    autor_pieza_id: str = "",
) -> tuple[dict[str, Any] | None, str | None]:
    """Decide (aprueba/rechaza) UN nivel de la cadena. Devuelve `(campos, None)` o `(None, error)`.

    Valida que: la decision sea aprobado/rechazado; el nivel sea el que TOCA (el primer
    pendiente por orden); el nivel no este ya decidido; y el decisor no sea el autor de la
    pieza (salvo admin). `campos` son los cambios a aplicar al registro del nivel.
    """
    if decision not in (DECISION_APROBADO, DECISION_RECHAZADO):
        return None, "La decisión debe ser aprobar o rechazar."
    if nivel.get("decision") != DECISION_PENDIENTE:
        return None, "Ese nivel ya fue decidido."
    actual = nivel_actual(cadena)
    if actual is None or actual.get("id") != nivel.get("id"):
        return None, "Aún no toca decidir este nivel; faltan niveles anteriores."
    if not _es_admin(rol, decisor):
        decisor_id = (decisor or {}).get("id", "")
        if decisor_id and autor_pieza_id and decisor_id == autor_pieza_id:
            return None, "No puedes aprobar tu propia pieza; debe revisarla otra persona."
    decisor = decisor or {}
    return (
        {
            "decision": decision,
            "decisor_id": decisor.get("id", "") or "",
            "decisor_nombre": decisor.get("usuario", "") or "",
            "comentario": (comentario or "").strip(),
            "decidido_en": _ahora_iso(),
        },
        None,
    )
