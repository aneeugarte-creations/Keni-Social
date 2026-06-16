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
  - La pieza se RECHAZA cuando acumula `UMBRAL_RECHAZO` niveles `rechazado` (dos "dislikes"
    de dos personas distintas, ESPEJO de los dos OK del feed). Un SOLO rechazo NO para la
    cadena: deja disponible el siguiente nivel para que otra persona decida. En una cadena
    de 1 solo nivel basta 1 rechazo (no hay un segundo que pedir).
  - La pieza esta TOTALMENTE aprobada cuando TODOS los niveles estan `aprobado`.
  - Una decision PROPIA se puede DESHACER (`deshacer_decision`): el revisor retira su OK o su
    dislike y su nivel vuelve a `pendiente`. Es lo que da el toggle del feed (un dislike tras
    un like quita el like; el siguiente dislike lo marca). Solo la decision propia, y solo si
    es la mas alta decidida (no se deja un hueco en una cadena que se decide por orden).
  - Separacion de funciones (como el flujo legado #9): el decisor de un nivel NO puede
    ser el autor que pidio la revision, salvo admin. "Otro par de ojos" por nivel.

`estado_cadena(cadena)` resume la cadena en uno de: "sin_cadena" (vacia), "pendiente"
(quedan niveles por decidir), "aprobado" (todos aprobados) o "rechazado" (acumula el
umbral de rechazos). Es lo que la UI pinta y lo que el resto del flujo puede consultar.
"""

from __future__ import annotations

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
from ..tiempo import ahora_iso


def _ahora_iso() -> str:
    return ahora_iso()


# Cuantos niveles `rechazado` hacen falta para RECHAZAR la pieza: dos "dislikes" de dos
# personas distintas, ESPEJO de los dos OK del feed. En una cadena mas corta no se puede
# exigir mas rechazos que niveles tiene (1 nivel => basta 1 rechazo): el umbral efectivo es
# `min(UMBRAL_RECHAZO, len(cadena))`. Un solo rechazo NO para la cadena.
UMBRAL_RECHAZO = 2

# Campos que devuelven un nivel a `pendiente` (sin decisor ni sello): los aplica `deshacer`
# para RETIRAR la decision propia de un revisor (quitar su OK o su dislike). Son justo las
# columnas que `repos.actualizar_aprobacion` permite escribir.
CAMPOS_NIVEL_PENDIENTE: dict[str, Any] = {
    "decision": DECISION_PENDIENTE,
    "decisor_id": "",
    "decisor_nombre": "",
    "comentario": "",
    "decidido_en": "",
}


def umbral_rechazo(cadena: list[dict[str, Any]]) -> int:
    """Rechazos necesarios para rechazar ESTA cadena: `min(UMBRAL_RECHAZO, nº de niveles)`.

    Garantiza que una cadena de 1 nivel siga rechazandose con 1 rechazo (no hay un segundo
    que pedir) mientras la cadena por defecto del feed (dos niveles) exige los dos dislikes.
    """
    return min(UMBRAL_RECHAZO, len(cadena)) if cadena else 0


def cadena_simple() -> list[str]:
    """Etiquetas de la cadena de aprobacion por defecto al mandar a revision (los dos OK).

    Defecto razonable para una PUBLICACION suelta: DOS niveles `pendiente` ("Edición" y
    "Coordinación") = los dos OK del equipo que la pieza necesita. Cada uno lo da una persona
    distinta (nunca el autor, salvo admin); con los dos, la pieza pasa sola a `aprobado`. Si
    el revisión editorial actua como aprobador automatico, el llamante antepone el nivel de IA.
    Expresado sobre el mismo modelo multinivel (cadena vacia = sin aprobacion; cadena de N
    = N niveles).
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


def contar_rechazados(cadena: list[dict[str, Any]]) -> int:
    """Cuenta cuantos niveles de la cadena estan en `rechazado` (los "dislikes" acumulados)."""
    return sum(1 for n in cadena if n.get("decision") == DECISION_RECHAZADO)


def estado_cadena(cadena: list[dict[str, Any]]) -> str:
    """Resume una cadena de niveles en su estado global.

    "sin_cadena" si esta vacia; "rechazado" cuando los rechazos acumulados alcanzan el umbral
    (`umbral_rechazo`: dos dislikes, o uno en cadenas de 1 nivel); "aprobado" si TODOS los
    niveles lo estan; "pendiente" en cualquier otro caso (aun caben decisiones, incluido el
    caso en que ya hay UN rechazo pero falta el segundo para parar la cadena).
    """
    if not cadena:
        return "sin_cadena"
    if contar_rechazados(cadena) >= umbral_rechazo(cadena):
        return DECISION_RECHAZADO
    if all(n.get("decision") == DECISION_APROBADO for n in cadena):
        return DECISION_APROBADO
    return DECISION_PENDIENTE


def contar_aprobados(cadena: list[dict[str, Any]]) -> int:
    """Cuenta cuantos niveles de la cadena estan en `aprobado` (PURA).

    Es la metrica que alimenta el GATE de gobernanza "minimo N aprobaciones" (item A): una
    pieza no se puede PROGRAMAR si no acumula al menos `MINIMO_APROBACIONES` niveles aprobados,
    aunque su estado editorial ya sea `aprobado` (p. ej. una cadena simple de 1 solo nivel).
    Cuenta TODOS los niveles aprobados, incluidos los automaticos (verificación / pre-aprobacion): son
    aprobaciones validas y trazables. No distingue humano vs auto aqui (eso lo deja a la UI).
    """
    return sum(1 for n in cadena if n.get("decision") == DECISION_APROBADO)


def contar_aprobaciones_humanas(cadena: list[dict[str, Any]]) -> int:
    """Cuenta los niveles aprobados por una PERSONA (excluye verificación / pre-aprobacion automatica).

    Es la metrica de "aprobaciones reales que se perderian" al editar el contenido de una pieza:
    solo cuentan los OK HUMANOS (decisor con id propio, no el reservado AUTO ni vacio). La usa el
    RESET de aprobaciones-al-editar para resetear solo cuando hay un OK humano que perder, sin
    churnar piezas que apenas llevan el verificación automatico.
    """
    return sum(
        1
        for n in cadena
        if n.get("decision") == DECISION_APROBADO
        and (n.get("decisor_id") or "") not in ("", DECISOR_AUTO_ID, DECISOR_CRITICA_ID)
    )


def cumple_minimo_aprobaciones(
    cadena: list[dict[str, Any]], minimo: int
) -> tuple[bool, int]:
    """¿La cadena acumula al menos `minimo` aprobaciones? Devuelve `(cumple, aprobados)`.

    `minimo <= 0` desactiva el gate (siempre cumple). El llamante (api/aprobacion.programar)
    usa `aprobados` para construir el mensaje "X de N" del 409 cuando NO cumple.
    """
    aprobados = contar_aprobados(cadena)
    if minimo <= 0:
        return True, aprobados
    return aprobados >= minimo, aprobados


def nivel_actual(cadena: list[dict[str, Any]]) -> dict[str, Any] | None:
    """El primer nivel `pendiente` por orden (el que toca decidir); None si no queda.

    Mientras la cadena no sea TERMINAL (ni aprobada ni rechazada por umbral), devuelve el
    siguiente nivel pendiente: un rechazo aislado (sub-umbral) NO la para, el siguiente
    nivel sigue disponible para que otra persona decida (asi se acumula el segundo dislike).
    Si la cadena ya esta aprobada o rechazada por umbral, devuelve None (no hay mas decisiones
    utiles). Tambien None en un empate sin niveles pendientes (p. ej. un OK y un dislike en
    una cadena de dos): no quedan niveles que decidir y lo desatasca un coordinador (forzar).
    """
    if estado_cadena(cadena) in (DECISION_APROBADO, DECISION_RECHAZADO):
        return None
    ordenada = sorted(cadena, key=lambda n: n.get("nivel", 0))
    for nivel in ordenada:
        if nivel.get("decision") == DECISION_PENDIENTE:
            return nivel
    return None


def deshacer_decision(
    cadena: list[dict[str, Any]], decisor_id: str
) -> tuple[str | None, str | None]:
    """Retira la decision PROPIA de `decisor_id`: devuelve `(nivel_id, None)` o `(None, error)`.

    El llamante aplica `CAMPOS_NIVEL_PENDIENTE` al `nivel_id` para devolver ese nivel a
    `pendiente` (quitar el OK o el dislike del revisor). Reglas:
      - Solo se deshace la decision PROPIA (un nivel cuyo `decisor_id` sea el del revisor; los
        automaticos AUTO/verificación no se deshacen). Sin sesion (`decisor_id` vacio) no hay nada que
        deshacer.
      - Como la cadena se decide POR ORDEN, solo se permite deshacer si NO hay un nivel
        SUPERIOR ya decidido por alguien: deshacer uno inferior dejaria un hueco. En el flujo
        normal del feed (cada quien decide un nivel) esto se cumple solo.
    """
    if not decisor_id:
        return None, "No hay sesión para deshacer una decisión."
    ordenada = sorted(cadena, key=lambda n: n.get("nivel", 0))
    mios = [
        n
        for n in ordenada
        if n.get("decisor_id") == decisor_id
        and n.get("decision") in (DECISION_APROBADO, DECISION_RECHAZADO)
    ]
    if not mios:
        return None, "No tienes ninguna decisión que deshacer en esta pieza."
    nivel = mios[-1]  # el mas alto que decidio esta persona (decide a lo sumo uno)
    hay_superior_decidido = any(
        n.get("nivel", 0) > nivel.get("nivel", 0)
        and n.get("decision") != DECISION_PENDIENTE
        for n in ordenada
    )
    if hay_superior_decidido:
        return None, "Ya hay una decisión posterior en la cadena; no puedes deshacer la tuya."
    return nivel.get("id", ""), None


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
    cargo_decisor: str = "",
) -> tuple[dict[str, Any] | None, str | None]:
    """Decide (aprueba/rechaza) UN nivel de la cadena. Devuelve `(campos, None)` o `(None, error)`.

    Valida que: la decision sea aprobado/rechazado; el nivel sea el que TOCA (el primer
    pendiente por orden); el nivel no este ya decidido; el decisor no sea el autor de la
    pieza (salvo admin); y, si el nivel exige un `cargo_requerido` (item C), que el cargo
    del decisor lo satisfaga (salvo admin, que puede desatascar). `campos` son los cambios
    a aplicar al registro del nivel.
    """
    if decision not in (DECISION_APROBADO, DECISION_RECHAZADO):
        return None, "La decisión debe ser aprobar o rechazar."
    if nivel.get("decision") != DECISION_PENDIENTE:
        return None, "Ese nivel ya fue decidido."
    actual = nivel_actual(cadena)
    if actual is None or actual.get("id") != nivel.get("id"):
        return None, "Aún no toca decidir este nivel; faltan niveles anteriores."
    decisor_id = (decisor or {}).get("id", "")
    # Dos OK = dos PERSONAS distintas: quien ya decidio un nivel de ESTA cadena no puede dar
    # tambien el otro OK (el "segundo par de ojos" no vale si es la misma persona). Esta regla se
    # aplica SIEMPRE, incluso al ADMIN: desatasca otras cosas (aprobar pieza propia, cargo), pero
    # NO puede dar los dos OK el mismo. Los decisores automaticos (id reservado "auto") y el acceso
    # por token (sin identidad, decisor_id="") no entran (no hay persona que deduplicar).
    if decisor_id != DECISOR_AUTO_ID and decisor_id and any(
        n.get("id") != nivel.get("id") and n.get("decisor_id") == decisor_id
        for n in cadena
    ):
        return None, "Ya diste tu OK en esta pieza; el otro OK lo da otra persona."
    if not _es_admin(rol, decisor):
        if decisor_id and autor_pieza_id and decisor_id == autor_pieza_id:
            return None, "No puedes aprobar tu propia pieza; debe revisarla otra persona."
        cargo_req = (nivel.get("cargo_requerido") or "").strip()
        if cargo_req and not cargo_satisface(cargo_req, cargo_decisor):
            return None, (
                f"Este nivel solo lo puede decidir alguien con el cargo «{cargo_req}»."
            )
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

# --------------------------------------------------------------------------- #
# Nivel "Crítica IA" (post-aprobacion): el critico con vision vota AL FINAL     #
# --------------------------------------------------------------------------- #
#
# A diferencia de la PRE-aprobacion de arriba (auto-aprueba niveles de bajo riesgo ANTES de los
# humanos), la Critica IA es un nivel que se anade AL FINAL de la cadena (detras de los dos OK
# humanos), gateado por `KENI_CRITICA_IA`. Cuando los humanos cierran su parte, un `claude -p`
# con vision critica la pieza y VOTA este nivel: aprueba => la pieza se programa; rechaza =>
# dislike de IA + comentario sin resolver que frena la programacion. El humano tiene la ultima
# palabra (al editar se reinicia la cadena; un coordinador puede `forzar`).
#
# El nivel se MARCA con un `cargo_requerido` reservado (`CARGO_IA_CRITICO`) que ningun cargo
# humano satisface: asi la regla de cargos existente (`decidir` + `cargo_satisface`) impide que
# una persona lo decida por el feed, y el front/worker lo identifican por ese mismo marcador.
ETIQUETA_CRITICA_IA = "Crítica IA"
CARGO_IA_CRITICO = "ia-critico"
DECISOR_CRITICA_ID = "ia-critico"
DECISOR_CRITICA_NOMBRE = "Crítica IA"


def es_nivel_critica_ia(nivel: dict[str, Any]) -> bool:
    """True si `nivel` es el nivel automatico "Crítica IA" (marcado por su cargo reservado)."""
    return (nivel.get("cargo_requerido") or "").strip().lower() == CARGO_IA_CRITICO


def es_etiqueta_critica_ia(etiqueta: str) -> bool:
    """True si la etiqueta nombra al nivel automatico "Crítica IA" (comparacion laxa)."""
    return (etiqueta or "").strip().lower() == ETIQUETA_CRITICA_IA.strip().lower()


def cargo_de_nivel(etiqueta: str, *, con_cargos: bool) -> str:
    """Cargo a sellar en un nivel segun su etiqueta ("" = sin requisito).

    El nivel "Crítica IA" SIEMPRE lleva el cargo reservado `CARGO_IA_CRITICO` (aunque la cadena
    no exija cargos humanos), para que la regla de cargos impida que una persona lo decida. Los
    demas niveles llevan el cargo del organigrama solo si `con_cargos` (Coordinación→coordinador…).
    """
    if es_etiqueta_critica_ia(etiqueta):
        return CARGO_IA_CRITICO
    return cargo_requerido_para(etiqueta) if con_cargos else ""


def nivel_critica_ia(cadena: list[dict[str, Any]]) -> dict[str, Any] | None:
    """El nivel "Crítica IA" de la cadena, o None si la cadena no lo lleva (flag OFF)."""
    for nivel in cadena:
        if es_nivel_critica_ia(nivel):
            return nivel
    return None


def humanos_aprobados_ia_pendiente(cadena: list[dict[str, Any]]) -> bool:
    """True si TODOS los niveles humanos estan aprobados y el nivel IA sigue PENDIENTE.

    Es la condicion que dispara el encolado del critico: los dos OK humanos ya estan, y solo
    falta que la Critica IA vote. Si no hay nivel IA (flag OFF) devuelve False (no aplica).
    """
    ia = nivel_critica_ia(cadena)
    if ia is None or ia.get("decision") != DECISION_PENDIENTE:
        return False
    humanos = [n for n in cadena if not es_nivel_critica_ia(n)]
    return bool(humanos) and all(
        n.get("decision") == DECISION_APROBADO for n in humanos
    )

# --------------------------------------------------------------------------- #
# ROLES en la cadena: cargo requerido por nivel (item C)                       #
# --------------------------------------------------------------------------- #
#
# Cada nivel de la cadena puede exigir un CARGO concreto del organigrama (`auth/usuarios.cargo`,
# allowlist en `estados.CARGOS_USUARIO`): p. ej. "Coordinación" la decide un coordinador y
# "Dirección" un director. Es una guarda EDITORIAL ortogonal a la separacion de funciones
# ("otro par de ojos") y al rol de permisos (admin/editor). Mapa por defecto razonable a
# partir del organigrama del cliente; lo demas no exige cargo (cualquiera del equipo decide).
CARGO_POR_ETIQUETA: dict[str, str] = {
    "coordinación": "coordinador",
    "coordinacion": "coordinador",
    "dirección": "director",
    "direccion": "director",
}


def cargo_requerido_para(etiqueta: str) -> str:
    """Cargo que se EXIGE para decidir un nivel con esa etiqueta ("" = sin requisito).

    Normaliza la etiqueta (minusculas, sin acentos via el mapa) y devuelve el cargo del mapa
    por defecto, o "" si la etiqueta no tiene requisito. PURA: la API la usa al CREAR la cadena
    para sellar `cargo_requerido` en cada nivel; los cargos especificos (coordinador_redes,
    coordinador_youtube...) los puede afinar el llamante, aqui damos el defecto del organigrama.
    """
    return CARGO_POR_ETIQUETA.get((etiqueta or "").strip().lower(), "")


def cargo_satisface(cargo_requerido: str, cargo_decisor: str) -> bool:
    """¿El `cargo_decisor` satisface el `cargo_requerido` de un nivel? (PURA).

    Sin requisito ("") -> siempre True (cualquiera decide). Con requisito, el cargo del decisor
    debe COINCIDIR exactamente, o ser una ESPECIALIZACION que empiece por el cargo generico
    (p. ej. requisito "coordinador" lo satisface "coordinador_redes"/"coordinador_youtube";
    requisito "director" exige "director"). Comparacion en minusculas.
    """
    req = (cargo_requerido or "").strip().lower()
    if not req:
        return True
    cargo = (cargo_decisor or "").strip().lower()
    if not cargo:
        return False
    return cargo == req or cargo.startswith(req + "_")


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
