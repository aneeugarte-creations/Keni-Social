"""Dominio de CADENCIA por red: scheduling por MARGEN entre posts (no por huecos fijos).

Sustituye al modelo de franjas-caja para alto volumen. Una CADENCIA es, por (marca?, red?):
un MARGEN mínimo entre posts (minutos), una VENTANA horaria activa (`hora_inicio`..`hora_fin`,
24h) y los DÍAS activos (0=lunes..6=domingo). El repartidor coloca cada pieza en el próximo
hueco LIBRE espaciado por el margen dentro de la ventana, día a día: "lo que entre" en cada
día (≈ floor(duración/margen)+1) y luego rueda al siguiente día activo.

VENTANA NOCTURNA (`hora_fin` < `hora_inicio`): la ventana CRUZA la medianoche y termina al
día siguiente (p. ej. 16:00–05:00). Imprescindible operando en CDMX sobre un almacén UTC:
la tarde-noche de México (UTC-6) cae a caballo de la medianoche UTC, así que una ventana
"solo mismo día" no puede representar el horario real de las marcas. El DÍA activo de un
hueco es el día en que la ventana EMPIEZA (sus huecos de madrugada pertenecen a esa ventana
aunque caigan en la fecha siguiente). `hora_fin == hora_inicio` sigue siendo inválida
(ambigua: ¿ventana vacía o de 24 h?).

Lógica PURA y DETERMINISTA (recibe `ahora` inyectado): la consumen `api/publicaciones.py`
(encolar) y `auto_programar.py` (auto-programación) sin acoplarse a Starlette ni al reloj.

`hora`: "HH:MM" 24h. Convención de instantes igual que el resto del backend (naive = UTC).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .franjas import hora_valida

# Tope de búsqueda (días) del próximo hueco: defensa ante una parrilla saturada.
_HORIZONTE_DIAS = 366


def cadencia_aplicable(
    cadencias: list[dict[str, Any]], marca: str, red: str
) -> dict[str, Any] | None:
    """Cadencia ACTIVA más específica que aplica a una (marca, red), o None.

    Prioridad por especificidad (igual que las franjas): (marca Y red) > (marca o red) >
    general (ambas ''). Solo se consideran las `activo`. Devuelve UNA (la más específica).
    """
    activas = [c for c in cadencias if c.get("activo")]

    def primera(pred: Any) -> dict[str, Any] | None:
        for c in activas:
            if pred(c):
                return c
        return None

    return (
        primera(lambda c: c["marca"] == marca and c["red"] == red)
        or primera(lambda c: c["marca"] == marca and c["red"] == "")
        or primera(lambda c: c["red"] == red and c["marca"] == "")
        or primera(lambda c: c["marca"] == "" and c["red"] == "")
    )


def _minutos(hora: str) -> int:
    hh, mm = (int(p) for p in hora.split(":"))
    return hh * 60 + mm


def cadencia_valida(cadencia: dict[str, Any]) -> bool:
    """True si la cadencia tiene margen>0, ventana válida (fin≠inicio) y al menos un día.

    `fin < inicio` es VÁLIDA: ventana nocturna que cruza la medianoche (ver módulo).
    Solo `fin == inicio` se rechaza (ambigua entre vacía y 24 h).
    """
    margen = cadencia.get("margen_min")
    ini = cadencia.get("hora_inicio")
    fin = cadencia.get("hora_fin")
    dias = cadencia.get("dias") or []
    if not isinstance(margen, int) or margen <= 0:
        return False
    if not hora_valida(ini) or not hora_valida(fin):
        return False
    if _minutos(fin) == _minutos(ini):
        return False
    if not dias or not all(isinstance(d, int) and 0 <= d <= 6 for d in dias):
        return False
    return True


def _duracion_min(cadencia: dict[str, Any]) -> int:
    """Minutos de ventana activa; una ventana nocturna (fin<inicio) suma el tramo de madrugada."""
    delta = _minutos(cadencia["hora_fin"]) - _minutos(cadencia["hora_inicio"])
    return delta if delta > 0 else delta + 24 * 60


def proximo_hueco_cadencia(
    cadencia: dict[str, Any],
    ahora: datetime,
    ocupados: set[str],
) -> str | None:
    """Próximo hueco FUTURO (ISO 'YYYY-MM-DDTHH:MM') según la cadencia, libre.

    Genera los huecos del modelo: por cada día activo, desde `hora_inicio` sumando `margen`
    hasta agotar la DURACIÓN de la ventana (en una nocturna los últimos huecos caen ya en la
    fecha siguiente). Devuelve el primero ESTRICTAMENTE futuro respecto a `ahora` que no esté
    en `ocupados` (los `fecha_programada` de otras piezas de la MISMA marca/red). None si la
    cadencia no es válida o no hay hueco dentro del horizonte. Determinista.
    """
    if not cadencia_valida(cadencia):
        return None
    margen = int(cadencia["margen_min"])
    inicio_min = _minutos(cadencia["hora_inicio"])
    duracion = _duracion_min(cadencia)
    dias = set(cadencia["dias"])

    base = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    # Arranca un día ANTES de `ahora`: la cola de una ventana nocturna iniciada ayer puede
    # tener huecos de madrugada todavía futuros hoy.
    for d in range(-1, _HORIZONTE_DIAS):
        dia = base + timedelta(days=d)
        if dia.weekday() not in dias:
            continue
        t = inicio_min
        while t <= inicio_min + duracion:
            cand = dia + timedelta(minutes=t)
            if cand > ahora:
                clave = cand.strftime("%Y-%m-%dT%H:%M")
                if clave not in ocupados:
                    return clave
            t += margen
    return None
