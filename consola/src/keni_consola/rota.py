"""Logica de DOMINIO de la parrilla y rota de horarios del equipo (F4 · #144).

Modulo PURO (sin I/O ni dependencias de persistencia): aqui vive el PROPONEDOR de
la rota y las reglas de rotacion, para poder probarlas a fondo sin tocar SQLite ni
la red. La capa de persistencia (`db.py`) y la API (`api/rota.py`) construyen sus
entradas y consumen estas funciones.

EL PROBLEMA (de Elias, B2+B4): "los sabados los reparto rotando... con los horarios
de los partidos y de los eventos" + "que el equipo pueda ver con anticipacion su
horario de la proxima semana". Keni PROPONE; Elias ajusta y APRUEBA.

REGLA CRITICA DE ROTACION: la misma persona NO cubre dos sabados seguidos, salvo
override explicito (cobertura estrategica que decide Elias). El proponedor recibe
quien cubrio el sabado de la semana ANTERIOR y lo excluye del sabado de esta semana;
rota al resto del equipo de forma equilibrada (round-robin por carga).

FRONTERA: este modulo solo PROPONE asignaciones (estado `propuesto`). Nada se publica
al equipo hasta que Elias las APRUEBA (estado `aprobado`), lo cual ocurre en la capa
de persistencia/API, no aqui.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

# Dia de la semana (Python: lunes=0 ... domingo=6). El sabado es el dia que rota.
SABADO = 5


@dataclass(frozen=True)
class Miembro:
    """Un miembro del equipo disponible para la rota (id estable + nombre legible)."""

    id: str
    nombre: str


@dataclass(frozen=True)
class Evento:
    """Un evento/transmision a cubrir: cuando es y QUE sacar de el.

    `fecha` es ISO (YYYY-MM-DD). `hora` es texto libre ("16:00", "16:00–18:00").
    `contenido` es "que sacar" de esa transmision (el campo clave del Excel de Elias).
    """

    id: str
    titulo: str
    fecha: str
    hora: str = ""
    contenido: str = ""


@dataclass
class TurnoPropuesto:
    """Una asignacion propuesta: un miembro cubre un evento. Vincula ambos.

    `override` marca una cobertura forzada que ROMPE la rotacion (la fija Elias). El
    proponedor nunca pone `override=True`; lo hace la edicion manual posterior.
    """

    evento_id: str
    miembro_id: str
    override: bool = False
    motivo: str = ""


@dataclass
class PropuestaRota:
    """Resultado del proponedor: los turnos + las notas de rotacion (para la UI)."""

    turnos: list[TurnoPropuesto] = field(default_factory=list)
    # Quien queda asignado al sabado de esta semana (para encadenar la siguiente).
    sabado_asignado: str = ""
    # Avisos legibles (p. ej. "no habia equipo suficiente para rotar"); nunca rompe.
    avisos: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Utilidades de fechas (semana lunes-domingo, deteccion de sabado)             #
# --------------------------------------------------------------------------- #


def _parsear_fecha(iso: str) -> date | None:
    """Parsea una fecha ISO (YYYY-MM-DD); None si no es valida (no rompe)."""
    try:
        return date.fromisoformat(iso)
    except (ValueError, TypeError):
        return None


def lunes_de_semana(d: date) -> date:
    """Lunes de la semana ISO que contiene `d` (la semana va lunes->domingo)."""
    return d - timedelta(days=d.weekday())


def lunes_de_semana_iso(iso: str) -> str:
    """Lunes (ISO) de la semana que contiene la fecha `iso`; "" si la fecha no parsea."""
    d = _parsear_fecha(iso)
    return lunes_de_semana(d).isoformat() if d is not None else ""


def es_sabado(iso: str) -> bool:
    """True si la fecha ISO cae en sabado (el dia que rota)."""
    d = _parsear_fecha(iso)
    return d is not None and d.weekday() == SABADO


def rango_semana(lunes_iso: str) -> tuple[str, str]:
    """`(lunes, domingo)` ISO de la semana cuyo lunes es `lunes_iso`.

    Si `lunes_iso` no parsea, devuelve `("", "")`.
    """
    lunes = _parsear_fecha(lunes_iso)
    if lunes is None:
        return "", ""
    # Normalizamos por si nos dieran un dia que no es lunes.
    lunes = lunes_de_semana(lunes)
    return lunes.isoformat(), (lunes + timedelta(days=6)).isoformat()


def eventos_de_semana(eventos: list[Evento], lunes_iso: str) -> list[Evento]:
    """Eventos cuya fecha cae dentro de la semana (lunes->domingo) de `lunes_iso`.

    Ordenados por fecha y luego hora (cronologico, como en el Excel). Eventos con
    fecha invalida se descartan (no se inventan turnos sobre fechas rotas).
    """
    inicio_iso, fin_iso = rango_semana(lunes_iso)
    if not inicio_iso:
        return []
    inicio = date.fromisoformat(inicio_iso)
    fin = date.fromisoformat(fin_iso)
    dentro = [
        e for e in eventos if (d := _parsear_fecha(e.fecha)) is not None and inicio <= d <= fin
    ]
    return sorted(dentro, key=lambda e: (e.fecha, e.hora, e.titulo))


# --------------------------------------------------------------------------- #
# Proponedor de la rota                                                         #
# --------------------------------------------------------------------------- #


def proponer_rota(
    eventos: list[Evento],
    equipo: list[Miembro],
    lunes_iso: str,
    *,
    sabado_previo: str = "",
) -> PropuestaRota:
    """PROPONE una rota para la semana de `lunes_iso`. NO la publica (solo propone).

    Reglas:
      - Vincula cada evento de la semana a UN miembro (turno) y, por el evento, a
        QUE contenido sacar (el evento ya lo lleva).
      - ROTACION DE SABADOS: el miembro que cubrio el sabado de la semana anterior
        (`sabado_previo`, un id de miembro) NO cubre el sabado de esta semana, salvo
        que no haya nadie mas disponible (entonces se avisa, no se inventa rotacion).
      - Reparto equilibrado: round-robin por carga (al menos cargado primero), de
        forma determinista para que la propuesta sea reproducible.

    Devuelve `PropuestaRota` con los turnos (estado conceptual `propuesto`), el id del
    miembro que queda en el sabado de esta semana (para encadenar la siguiente) y los
    avisos legibles. Si no hay equipo, devuelve una propuesta vacia con un aviso.
    """
    propuesta = PropuestaRota()
    semana = eventos_de_semana(eventos, lunes_iso)
    if not equipo:
        if semana:
            propuesta.avisos.append(
                "No hay miembros de equipo para proponer la rota. Da de alta usuarios."
            )
        return propuesta
    if not semana:
        return propuesta

    # Carga acumulada por miembro (para repartir equilibrado y determinista).
    carga: dict[str, int] = {m.id: 0 for m in equipo}
    # Orden estable del equipo (por nombre y luego id) para empates reproducibles.
    equipo_ordenado = sorted(equipo, key=lambda m: (m.nombre.lower(), m.id))

    def menos_cargado(excluir: set[str]) -> Miembro | None:
        """Miembro con menos carga, excluyendo `excluir`; None si no queda nadie.

        Empata por orden estable (nombre, id). Determinista.
        """
        candidatos = [m for m in equipo_ordenado if m.id not in excluir]
        if not candidatos:
            return None
        return min(candidatos, key=lambda m: (carga[m.id], m.nombre.lower(), m.id))

    for evento in semana:
        sabado = es_sabado(evento.fecha)
        excluir: set[str] = set()
        # Solo el sabado aplica la regla de no-repeticion contra la semana previa.
        if sabado and sabado_previo and sabado_previo in carga:
            excluir.add(sabado_previo)

        elegido = menos_cargado(excluir)
        if elegido is None and excluir:
            # Equipo de una sola persona (o todos excluidos): no se puede rotar el
            # sabado sin override. Lo asignamos igualmente y AVISAMOS (honestidad);
            # no inventamos un miembro que no existe.
            elegido = menos_cargado(set())
            if elegido is not None and sabado:
                propuesta.avisos.append(
                    "No hay equipo suficiente para rotar el sábado: se repite a la misma "
                    "persona. Marca un override si es intencional."
                )
        if elegido is None:
            continue  # no deberia ocurrir (hay equipo), pero nunca rompemos

        carga[elegido.id] += 1
        propuesta.turnos.append(
            TurnoPropuesto(evento_id=evento.id, miembro_id=elegido.id, override=False)
        )
        if sabado:
            propuesta.sabado_asignado = elegido.id

    return propuesta


def viola_rotacion_sabado(
    sabado_previo: str, sabado_actual: str, *, override: bool
) -> bool:
    """True si asignar `sabado_actual` repite a la persona del sabado previo SIN override.

    Es la regla de aceptacion en forma de predicado puro: la API la usa para decidir si
    una edicion manual necesita marcar `override` (cobertura estrategica de Elias).
    """
    if override:
        return False
    return bool(sabado_previo) and sabado_previo == sabado_actual
