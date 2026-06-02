"""Dominio de FRANJAS: logica PURA de scheduling de huecos de publicacion.

Una FRANJA es una plantilla de hueco recurrente: (marca?, red?, dia_semana, hora).
Las publicaciones se ENCOLAN buscando el proximo hueco futuro de las franjas que
apliquen a su (marca, red). Aqui vive la logica de NEGOCIO (aplicabilidad + calculo del
proximo hueco + validacion de hora), separada del router `api/franjas.py` (transporte):
es PURA y DETERMINISTA (recibe "ahora" inyectado, sin reloj real), reutilizable por
`api/publicaciones.py` y `api/sugerencias_hora.py` sin acoplarse a Starlette.

dia_semana: 0=lunes .. 6=domingo (igual que `datetime.weekday()`).
hora:       "HH:MM" en 24h.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

# "HH:MM" 24h: 00:00..23:59.
_RE_HORA = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

# Horizonte de busqueda del proximo hueco (dias). Con franjas validas siempre se
# encuentra hueco dentro de una semana, salvo que TODOS esten ocupados; este tope
# evita un bucle infinito teorico (defensa en profundidad).
_HORIZONTE_DIAS = 366


def hora_valida(hora: Any) -> bool:
    """True si `hora` es un string 'HH:MM' 24h valido."""
    return isinstance(hora, str) and _RE_HORA.match(hora) is not None


def franjas_aplicables(
    franjas: list[dict[str, Any]], marca: str, red: str
) -> list[dict[str, Any]]:
    """Franjas que aplican a una (marca, red), con prioridad por especificidad.

    Prioridad (la primera con resultados gana, no se mezclan niveles):
      1. franjas con ESA marca Y ESA red,
      2. si no hay, franjas que coincidan en marca (red='') o en red (marca=''),
         o generales (ambas ''),
    Devuelve la lista del nivel ganador (puede estar vacia si no aplica ninguna).
    """
    especificas = [f for f in franjas if f["marca"] == marca and f["red"] == red]
    if especificas:
        return especificas
    parciales = [
        f
        for f in franjas
        if (f["marca"] == marca and f["red"] == "")
        or (f["red"] == red and f["marca"] == "")
        or (f["marca"] == "" and f["red"] == "")
    ]
    return parciales


def _candidato(ahora: datetime, dia_semana: int, hora: str) -> datetime:
    """Primer datetime >= `ahora` que cae en `dia_semana` a la `hora` ('HH:MM')."""
    hh, mm = (int(p) for p in hora.split(":"))
    # Dias hasta el proximo `dia_semana` (0..6) a partir de hoy.
    delta_dias = (dia_semana - ahora.weekday()) % 7
    candidato = (ahora + timedelta(days=delta_dias)).replace(
        hour=hh, minute=mm, second=0, microsecond=0
    )
    if candidato <= ahora:
        # Ese hueco ya paso hoy: salta a la proxima semana.
        candidato += timedelta(days=7)
    return candidato


def proximo_hueco(
    franjas_aplican: list[dict[str, Any]],
    ahora: datetime,
    ocupados: set[str],
) -> str | None:
    """Proximo hueco FUTURO (ISO 'YYYY-MM-DDTHH:MM') de las franjas dadas, libre.

    - Considera SOLO las `franjas_aplican` (ya filtradas por aplicabilidad).
    - Estrictamente FUTURO respecto a `ahora` (los huecos <= ahora se descartan).
    - Evita los datetimes en `ocupados` (ISO 'YYYY-MM-DDTHH:MM' de otras publicaciones
      ya `programado`): avanza a la siguiente repeticion semanal de esa misma franja.
    - Devuelve el datetime mas temprano disponible, o None si no aplica ninguna franja.

    Determinista: depende solo de sus argumentos (no del reloj real).
    """
    if not franjas_aplican:
        return None
    mejor: datetime | None = None
    for franja in franjas_aplican:
        candidato = _candidato(ahora, franja["dia_semana"], franja["hora"])
        # Avanza semana a semana hasta encontrar un hueco no ocupado (con tope). El
        # avance se hace ANTES de comprobar el limite: asi un slot ocupado en la propia
        # frontera del horizonte recibe su reemplazo (no se devuelve un hueco ocupado ni
        # se cae a None habiendo hueco mas alla del primer candidato).
        limite = ahora + timedelta(days=_HORIZONTE_DIAS)
        while candidato.strftime("%Y-%m-%dT%H:%M") in ocupados:
            candidato += timedelta(days=7)
            if candidato > limite:
                break
        if candidato > limite:
            continue
        if mejor is None or candidato < mejor:
            mejor = candidato
    return mejor.strftime("%Y-%m-%dT%H:%M") if mejor is not None else None
