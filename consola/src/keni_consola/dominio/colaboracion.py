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
    CADENA_APROBACION_SIMPLE,
    DECISION_APROBADO,
    DECISION_PENDIENTE,
    DECISION_RECHAZADO,
    ESTADO_APROBADO,
    ESTADO_EN_REVISION,
    ROL_ADMIN,
)


def _ahora_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def cadena_simple() -> list[str]:
    """Etiquetas de la cadena de aprobacion SIMPLE (longitud 1 = "otro par de ojos").

    Defecto razonable para una PUBLICACION suelta: un unico nivel `pendiente` que un
    revisor (distinto del autor, salvo admin) aprueba o rechaza. Equivale al viejo flujo
    lineal borrador→en_revision→aprobado, pero expresado como una cadena de un solo nivel
    sobre el mismo modelo multinivel (cadena vacia = sin aprobacion; cadena de N = N niveles).
    """
    return list(CADENA_APROBACION_SIMPLE)


def estado_publicacion_para(estado_global: str) -> str | None:
    """Traduce el estado GLOBAL de la cadena al `estado` editorial de la PUBLICACION.

    Es el puente PURO entre el modelo de aprobacion (cadena multinivel) y los estados que
    el programador entiende (`programador.py` lee `aprobado`/`programado`): cuando la cadena
    queda totalmente `aprobado`, la pieza pasa a `aprobado`; mientras quedan niveles por
    decidir, esta `en_revision`; un `rechazado` la devuelve a `borrador`. Una cadena vacia
    ("sin_cadena") no toca el estado editorial: devuelve None (sin aprobacion configurada).

    Devuelve el estado editorial a aplicar, o None si la cadena no debe alterarlo.
    """
    if estado_global == DECISION_APROBADO:
        return ESTADO_APROBADO
    if estado_global == DECISION_PENDIENTE:
        return ESTADO_EN_REVISION
    if estado_global == DECISION_RECHAZADO:
        return "borrador"
    return None  # "sin_cadena": ninguna aprobacion configurada, no se toca el estado.


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


# --------------------------------------------------------------------------- #
# Fase3 (auto-planificacion): PRE-APROBACION de piezas de BAJO RIESGO          #
# --------------------------------------------------------------------------- #
#
# "El equipo solo crea piezas; la operativa es automatica": para piezas de BAJO RIESGO no
# deberia hacer falta que un humano pulse "aprobar" en CADA nivel de la cadena. Esta logica
# PURA decide que niveles se pueden auto-aprobar al CREAR la cadena, dejando SIEMPRE el
# ULTIMO nivel a una decision humana (el "par de ojos" final no se salta nunca).
#
# CONSERVADOR Y GATEADO: solo aplica si el llamante pasa `activa=True` (flag admin
# `KENI_AUTO_PREAPROBACION`, def OFF) Y la pieza es de bajo riesgo. Si no, no auto-aprueba
# nada (todos los niveles nacen `pendiente`, comportamiento de siempre). TRAZABLE: el decisor
# auto se sella con un id/nombre reservado ("auto") para que la UI distinga lo automatico.

# Identidad reservada del decisor AUTOMATICO (trazabilidad: la UI puede pintarlo distinto).
DECISOR_AUTO_ID = "auto"
DECISOR_AUTO_NOMBRE = "Pre-aprobación automática"


def es_pieza_bajo_riesgo(
    plataforma: dict[str, Any] | None, contenido: dict[str, Any] | None
) -> bool:
    """True si una pieza es de BAJO RIESGO para la pre-aprobacion (PURA, sin efectos).

    Dos casos CONSERVADORES (ambos editorialmente seguros):
      1. SOLO canal web / NO-social: la fila por plataforma es del canal "web" (la nota en el
         sitio), que NO entra en las redes sociales (Metricool) ni en las skills de copy. Un
         error aqui no llega a una red social.
      2. EVERGREEN REUTILIZADO SIN CAMBIOS: el contenido padre es `flujo='evergreen'` (always-on,
         ya validado en su dia) y la fila NO tiene copy nuevo pendiente (`falta_copy` es falso),
         es decir, se reutiliza tal cual sin reescritura.

    Cualquier otra pieza (importante del dia, evento, copy nuevo en una red social) NO es de
    bajo riesgo: devuelve False y la cadena se decide a mano como siempre.
    """
    plataforma = plataforma or {}
    contenido = contenido or {}

    red = (plataforma.get("red") or "").strip().lower()
    # Caso 1: canal web (no-social). El unico canal del tablero que no es una red social.
    if red == "web":
        return True

    # Caso 2: evergreen reutilizado sin copy nuevo pendiente.
    flujo = (contenido.get("flujo") or "").strip().lower()
    falta_copy = bool(plataforma.get("falta_copy", False))
    return flujo == "evergreen" and not falta_copy


def autoaprobaciones_iniciales(
    cadena: list[dict[str, Any]],
    *,
    activa: bool,
    bajo_riesgo: bool,
) -> list[tuple[str, dict[str, Any]]]:
    """Niveles a auto-aprobar al CREAR la cadena de una pieza de bajo riesgo (PURA).

    Devuelve una lista de `(nivel_id, campos)` con los niveles que deben quedar `aprobado`
    automaticamente, en ORDEN. Reglas (todas conservadoras):
      - Si `activa` es False o `bajo_riesgo` es False -> lista VACIA (no se auto-aprueba nada).
      - El ULTIMO nivel NUNCA se auto-aprueba: la decision final siempre es humana. Por eso
        una cadena de 1 SOLO nivel tampoco se toca (su unico nivel ES el final).
      - Se auto-aprueban TODOS los niveles MENOS el ultimo, por orden ascendente de `nivel`.

    `campos` son los mismos que escribiria una decision manual (decision/decisor/comentario/
    sello), pero con el decisor reservado AUTO para que quede TRAZA de que fue automatico.
    El llamante (api/colaboracion) los aplica con `repos.actualizar_aprobacion`.
    """
    if not activa or not bajo_riesgo:
        return []
    ordenada = sorted(cadena, key=lambda n: n.get("nivel", 0))
    if len(ordenada) <= 1:
        return []  # un solo nivel = el final; no se salta el ultimo par de ojos
    sello = _ahora_iso()
    decididos: list[tuple[str, dict[str, Any]]] = []
    for nivel in ordenada[:-1]:  # todos menos el ultimo
        nivel_id = nivel.get("id", "")
        if not nivel_id:
            continue
        decididos.append(
            (
                nivel_id,
                {
                    "decision": DECISION_APROBADO,
                    "decisor_id": DECISOR_AUTO_ID,
                    "decisor_nombre": DECISOR_AUTO_NOMBRE,
                    "comentario": "Pre-aprobado automáticamente (pieza de bajo riesgo).",
                    "decidido_en": sello,
                },
            )
        )
    return decididos
