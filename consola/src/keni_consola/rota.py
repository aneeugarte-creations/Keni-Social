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

from .estados import (
    FRANJA_DESCANSO,
    FRANJA_MATUTINO,
    FRANJA_VESPERTINO,
    FRANJAS_TRABAJO,
)

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


def viola_rotacion_sabado_trabajo(
    sabados_previos: set[str], miembro: str, *, override: bool, franja: str
) -> bool:
    """True si poner a `miembro` a TRABAJAR el sabado repite su sabado previo SIN override.

    Gemela de `viola_rotacion_sabado` pero para el HORARIO de trabajo: un miembro puede
    haber trabajado el sabado de la semana anterior (`sabados_previos`, ids que cubrieron
    una franja de trabajo). Asignarle de nuevo una franja de TRABAJO (matutino/vespertino,
    no `descanso`) sin override repite el sabado y viola la rotacion. `descanso` nunca
    viola (no trabaja ese dia).
    """
    if override:
        return False
    if franja not in FRANJAS_TRABAJO:
        return False
    return bool(miembro) and miembro in sabados_previos


# --------------------------------------------------------------------------- #
# Gestion de turnos: horario de TRABAJO del equipo (F4 · #144, ola A)           #
# --------------------------------------------------------------------------- #
#
# Distinto de la COBERTURA de eventos (arriba): aqui se reparte el TURNO DE TRABAJO de
# cada persona por dia (matutino/vespertino/descanso), respetando ausencias/vacaciones
# y rotando los sabados, tal como Elias lo lleva hoy en su Excel:
#   - "Luis es de 8 de la manana a 4 de la tarde, y Tescu de 4 a 12 de la noche; uno descansa"
#   - "los sabados los reparto rotando: no hay un sabado igual"
#   - "voy casi un mes adelante con los horarios del equipo... las vacaciones, esto por el acomodo"
# El modulo es PURO: la persistencia/API resuelven las ausencias y el sabado previo y
# llaman aqui. Nada se publica al equipo hasta que Elias APRUEBA (estado `aprobado`).


@dataclass(frozen=True)
class Ausencia:
    """Un periodo en que un miembro NO esta disponible (vacaciones/descanso/baja/otro).

    `desde`/`hasta` son fechas ISO (YYYY-MM-DD), RANGO INCLUSIVO. `tipo` es informativo
    para el proponedor (cualquier ausencia que cubra una fecha excluye al miembro ese dia).
    """

    miembro_id: str
    desde: str
    hasta: str
    tipo: str = "otro"


@dataclass
class TurnoTrabajoPropuesto:
    """Una asignacion de horario propuesta: `miembro` trabaja `franja` el dia `fecha`.

    `franja` es matutino/vespertino/descanso. `override` marca una asignacion forzada que
    ROMPE la rotacion de sabados (la fija Elias); el proponedor nunca pone `override=True`.
    """

    fecha: str
    miembro_id: str
    franja: str
    override: bool = False
    motivo: str = ""


@dataclass
class PropuestaHorario:
    """Resultado del proponedor de horario: turnos de la semana + notas de rotacion."""

    turnos: list[TurnoTrabajoPropuesto] = field(default_factory=list)
    # Ids de quienes quedan TRABAJANDO el sabado de esta semana (para encadenar la siguiente).
    sabado_asignados: list[str] = field(default_factory=list)
    # Avisos legibles (p. ej. "no habia equipo suficiente para cubrir manana y tarde").
    avisos: list[str] = field(default_factory=list)


def dias_de_semana(lunes_iso: str) -> list[str]:
    """Las 7 fechas ISO (lunes->domingo) de la semana cuyo lunes es `lunes_iso`.

    Lista vacia si `lunes_iso` no parsea. Normaliza por si dieran un dia que no es lunes.
    """
    inicio_iso, _ = rango_semana(lunes_iso)
    if not inicio_iso:
        return []
    inicio = date.fromisoformat(inicio_iso)
    return [(inicio + timedelta(days=i)).isoformat() for i in range(7)]


def miembro_ausente(ausencias: list[Ausencia], miembro_id: str, fecha_iso: str) -> bool:
    """True si alguna ausencia de `miembro_id` cubre `fecha_iso` (rango inclusivo).

    Ausencias con fechas invalidas se ignoran (no se inventan exclusiones sobre fechas
    rotas). Predicado puro reutilizable por el proponedor y por la serializacion de la UI.
    """
    d = _parsear_fecha(fecha_iso)
    if d is None:
        return False
    for a in ausencias:
        if a.miembro_id != miembro_id:
            continue
        desde = _parsear_fecha(a.desde)
        hasta = _parsear_fecha(a.hasta)
        if desde is None or hasta is None:
            continue
        if desde <= d <= hasta:
            return True
    return False


def proponer_horario(
    equipo: list[Miembro],
    lunes_iso: str,
    *,
    ausencias: list[Ausencia] | None = None,
    sabados_previos: set[str] | None = None,
) -> PropuestaHorario:
    """PROPONE el horario de TRABAJO de la semana de `lunes_iso`. NO lo publica (propone).

    Reglas (deterministas y reproducibles):
      - Para cada dia lunes->domingo asigna a cada miembro DISPONIBLE una franja de modo
        que el dia quede cubierto: cuando el equipo lo permite, >=1 `matutino` y >=1
        `vespertino`; el resto `descansa`. Un miembro con una AUSENCIA que cubra ese dia
        NO se asigna (queda excluido; la UI lo muestra como no disponible).
      - ROTACION DE SABADOS: quien TRABAJO el sabado de la semana anterior
        (`sabados_previos`, ids) NO entra a trabajar este sabado salvo que no quede nadie
        mas (entonces se AVISA, no se inventa rotacion). Descansa por defecto.
      - Reparto EQUILIBRADO: round-robin por carga acumulada de jornadas (menos cargado
        primero), con orden estable (nombre, id) para empates reproducibles.

    Emite `avisos` HONESTOS cuando el equipo es demasiado pequeno para cubrir manana+tarde
    o para rotar el sabado, en vez de inventar personas. Si no hay equipo, devuelve una
    propuesta vacia con un aviso.
    """
    propuesta = PropuestaHorario()
    ausencias = ausencias or []
    sabados_previos = sabados_previos or set()
    dias = dias_de_semana(lunes_iso)
    if not dias:
        return propuesta
    if not equipo:
        propuesta.avisos.append(
            "No hay miembros de equipo para proponer el horario. Da de alta usuarios."
        )
        return propuesta

    # Carga acumulada de JORNADAS por miembro (para repartir equilibrado y determinista).
    carga: dict[str, int] = {m.id: 0 for m in equipo}
    # Orden estable del equipo (por nombre y luego id) para empates reproducibles.
    equipo_ordenado = sorted(equipo, key=lambda m: (m.nombre.lower(), m.id))

    def por_carga(miembros: list[Miembro]) -> list[Miembro]:
        """`miembros` ordenados por carga acumulada (menos cargado primero), estable."""
        return sorted(miembros, key=lambda m: (carga[m.id], m.nombre.lower(), m.id))

    aviso_cobertura = False
    aviso_sabado = False

    for fecha in dias:
        sabado = es_sabado(fecha)
        disponibles = [
            m for m in equipo_ordenado if not miembro_ausente(ausencias, m.id, fecha)
        ]

        # El sabado, quien trabajo el sabado previo NO entra (rotacion), salvo que sin el
        # no quede nadie disponible. Entonces se avisa y se repite (no se inventa equipo).
        trabajables = disponibles
        if sabado and sabados_previos:
            sin_previos = [m for m in disponibles if m.id not in sabados_previos]
            if sin_previos:
                trabajables = sin_previos
            elif disponibles:
                aviso_sabado = True  # hay que repetir a alguien del sabado anterior

        if not trabajables:
            # Nadie disponible ese dia (todos de vacaciones/baja): no hay turnos. La UI lo
            # mostrara como dia sin cobertura; el aviso lo informa.
            aviso_cobertura = True
            continue

        ordenados = por_carga(trabajables)
        # Asignamos manana y tarde a los dos menos cargados (si los hay); el resto descansa.
        # Con un solo disponible, cubre la manana y se avisa (no hay tarde).
        del_dia: list[tuple[str, str]] = []  # (miembro_id, franja)
        if len(ordenados) >= 2:
            del_dia.append((ordenados[0].id, FRANJA_MATUTINO))
            del_dia.append((ordenados[1].id, FRANJA_VESPERTINO))
            for m in ordenados[2:]:
                del_dia.append((m.id, FRANJA_DESCANSO))
        else:
            del_dia.append((ordenados[0].id, FRANJA_MATUTINO))
            aviso_cobertura = True  # no hay con quien cubrir el vespertino ese dia

        for miembro_id, franja in del_dia:
            propuesta.turnos.append(
                TurnoTrabajoPropuesto(fecha=fecha, miembro_id=miembro_id, franja=franja)
            )
            if franja in FRANJAS_TRABAJO:
                carga[miembro_id] += 1
                if sabado:
                    propuesta.sabado_asignados.append(miembro_id)

    if aviso_cobertura:
        propuesta.avisos.append(
            "No hay equipo suficiente para cubrir mañana y tarde todos los días: revisa la "
            "propuesta. Da de alta más usuarios o ajusta las ausencias."
        )
    if aviso_sabado:
        propuesta.avisos.append(
            "No hay equipo suficiente para rotar el sábado: se repite a quien trabajó el "
            "sábado anterior. Marca un override si es intencional."
        )
    return propuesta
