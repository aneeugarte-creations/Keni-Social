"""Score de prioridad dinamico para la "lista viva" del dia (H3).

PROBLEMA QUE RESUELVE
=====================
El tablero kanban ordena por prioridad fija (alta/media/baja) + fecha. La "lista viva" que pide
Angel debe RE-ORDENARSE sola cada vez que entra algo: un tema obligatorio con fecha encima debe
subir; uno evergreen sin fecha, bajar. Aqui un SCORE determinista combina las senales que el
contenido YA tiene (compromiso, prioridad, cercania de la fecha objetivo, flujo, frescura).

DECISION (documentada): el score se aplica en la VISTA DEL DIA (Panel-9am), NO cambia el orden
del tablero kanban compartido (que el equipo ya conoce). Asi la "lista del dia" se reordena
sola sin alterar la operativa del tablero. Los PESOS son defaults sensatos y explicitos; se
afinan con el equipo sin tocar la forma de la funcion.

PURO y testeable: depende solo de sus argumentos (incluido `hoy`, que se inyecta). El llamante
resuelve los nombres de etiqueta (ids -> nombres) y pasa `hoy = date.today()`.
"""

from __future__ import annotations

from datetime import date
from typing import Any

# Etiqueta que marca un contenido "obligatorio por compromiso" (la pone el importador / a mano).
ETIQUETA_COMPROMISO = "compromiso"

# Pesos por defecto (explicitos y afinables). El compromiso DOMINA: un must-do siempre arriba.
PESO_PRIORIDAD: dict[str, int] = {"alta": 100, "media": 50, "baja": 10}
PESO_FLUJO: dict[str, int] = {"importante": 60, "evento": 40, "evergreen": 5}
BONUS_COMPROMISO = 200


def _norm(texto: object) -> str:
    return " ".join(("" if texto is None else str(texto)).strip().lower().split())


def _fecha_iso(valor: object) -> date | None:
    """Primeros 10 chars -> date, o None si no parsea (tolera fecha con hora detras)."""
    s = ("" if valor is None else str(valor)).strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def peso_fecha(fecha_objetivo: object, hoy: date) -> int:
    """Cuanto pesa la cercania de la fecha objetivo: vencido/hoy urge, lejano pesa poco."""
    f = _fecha_iso(fecha_objetivo)
    if f is None:
        return 0
    dias = (f - hoy).days
    if dias < 0:
        return 150  # vencido: lo mas urgente
    if dias == 0:
        return 120  # hoy
    if dias <= 3:
        return 80
    if dias <= 7:
        return 40
    return 10


def peso_frescura(creado: object, hoy: date) -> int:
    """Bonus pequeno por recencia: lo recien entrado destaca un poco en la lista viva."""
    c = _fecha_iso(creado)
    if c is None:
        return 0
    dias = (hoy - c).days
    if dias <= 0:
        return 20
    if dias <= 1:
        return 15
    if dias <= 3:
        return 8
    if dias <= 7:
        return 3
    return 0


def score_contenido(
    item: dict[str, Any], *, etiquetas: list[str] | None = None, hoy: date
) -> int:
    """Score de un contenido del tablero. `etiquetas` = NOMBRES (no ids) ya resueltos.

    Mayor score = mas arriba en la lista del dia. Determinista; depende solo de sus argumentos.
    """
    etiquetas = etiquetas or []
    score = PESO_PRIORIDAD.get(item.get("prioridad") or "media", PESO_PRIORIDAD["media"])
    score += PESO_FLUJO.get(item.get("flujo") or "", 0)
    score += peso_fecha(item.get("fecha_objetivo") or "", hoy)
    score += peso_frescura(item.get("creado") or "", hoy)
    if any(_norm(e) == ETIQUETA_COMPROMISO for e in etiquetas):
        score += BONUS_COMPROMISO
    return score


def ordenar_por_score(
    items: list[dict[str, Any]],
    *,
    etiquetas_por_item: dict[str, list[str]] | None = None,
    hoy: date,
) -> list[dict[str, Any]]:
    """Devuelve `items` ordenados por score descendente (estable: empates conservan el orden).

    `etiquetas_por_item`: id de contenido -> lista de NOMBRES de etiqueta. `sorted` es estable,
    asi que dos items con el mismo score mantienen el orden de entrada (que ya viene del tablero
    por prioridad+fecha). No muta la lista de entrada.
    """
    etiquetas_por_item = etiquetas_por_item or {}
    return sorted(
        items,
        key=lambda it: score_contenido(
            it, etiquetas=etiquetas_por_item.get(it.get("id", ""), []), hoy=hoy
        ),
        reverse=True,
    )
