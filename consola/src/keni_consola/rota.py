"""Logica de DOMINIO de la parrilla y rota de horarios del equipo (F4 · #144).

Modulo PURO (sin I/O ni dependencias de persistencia): aqui viven las reglas y
predicados de rotacion, para poder probarlas a fondo sin tocar SQLite ni la red.
La capa de persistencia (`db.py`) y la API (`api/rota.py`) construyen sus entradas
y consumen estas funciones.

DECISION DE PRODUCTO: Elias (Claro Sports / UnoTV) asigna su rota A MANO por criterio
estrategico ("los sabados los reparto rotando, pero a veces no se cumple, por temas
estrategicos"). La consola NO propone reparto automatico: solo le muestra los huecos,
si se repiten sabados y la carga por persona; Elias decide y APRUEBA antes de
publicarla al equipo. Aqui solo vive lo que respalda esa toma de decision.

REGLA DE ROTACION (predicado): la misma persona NO cubre dos sabados seguidos, salvo
override explicito. El predicado `viola_rotacion_sabado(*)` se usa en la edicion manual
de turnos (PATCH `/api/rota/turnos/{id}` y `/api/rota/horario/turnos/{id}`) para exigir
el override cuando Elias decide repetir intencionalmente. Su variante para el HORARIO
de trabajo (`viola_rotacion_sabado_trabajo`) aplica la misma idea al turno laboral del
sabado (matutino/vespertino).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .estados import FRANJAS_TRABAJO

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


@dataclass(frozen=True)
class Ausencia:
    """Un periodo en que un miembro NO esta disponible (vacaciones/descanso/baja/otro).

    `desde`/`hasta` son fechas ISO (YYYY-MM-DD), RANGO INCLUSIVO. `tipo` es informativo;
    la UI lo muestra como no disponible y la edicion de turnos lo respeta.
    """

    miembro_id: str
    desde: str
    hasta: str
    tipo: str = "otro"


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


def dias_de_semana(lunes_iso: str) -> list[str]:
    """Las 7 fechas ISO (lunes->domingo) de la semana cuyo lunes es `lunes_iso`.

    Lista vacia si `lunes_iso` no parsea. Normaliza por si dieran un dia que no es lunes.
    """
    inicio_iso, _ = rango_semana(lunes_iso)
    if not inicio_iso:
        return []
    inicio = date.fromisoformat(inicio_iso)
    return [(inicio + timedelta(days=i)).isoformat() for i in range(7)]


# --------------------------------------------------------------------------- #
# Predicados de rotacion (usados por la edicion manual de turnos)               #
# --------------------------------------------------------------------------- #


def miembro_ausente(ausencias: list[Ausencia], miembro_id: str, fecha_iso: str) -> bool:
    """True si alguna ausencia de `miembro_id` cubre `fecha_iso` (rango inclusivo).

    Ausencias con fechas invalidas se ignoran (no se inventan exclusiones sobre fechas
    rotas). Predicado puro reutilizable por la serializacion de la UI (marcar el dia
    como "Ausente") y por la edicion manual de turnos.
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
