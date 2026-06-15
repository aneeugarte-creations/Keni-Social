"""Score de prioridad dinamico para la "lista viva" del dia (H3).

PROBLEMA QUE RESUELVE
=====================
El tablero kanban ordena por prioridad fija (alta/media/baja) + fecha. La "lista viva" que pide
un content manager debe RE-ORDENARSE sola cada vez que entra algo: un tema obligatorio con fecha encima debe
subir; uno evergreen sin fecha, bajar. Aqui un SCORE determinista combina las senales que el
contenido YA tiene (compromiso, evergreen list, prioridad, cercania de la fecha objetivo, flujo,
frescura).

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

# Etiqueta de la "evergreen list" del equipo (lo que el equipo quiere postear). La pone el importador.
ETIQUETA_EVERGREEN = "evergreen"

# Pesos por defecto (explicitos y afinables). El compromiso DOMINA: un must-do siempre arriba.
PESO_PRIORIDAD: dict[str, int] = {"alta": 100, "media": 50, "baja": 10}
PESO_FLUJO: dict[str, int] = {"importante": 60, "evento": 40, "evergreen": 5}
BONUS_COMPROMISO = 200
# Bonus moderado para la evergreen list: por DEBAJO del compromiso, por encima de lo normal.
BONUS_EVERGREEN = 80

# --------------------------------------------------------------------------- #
# Señal de VIRALIDAD del Radar (Fase 5, loop de aprendizaje)                    #
# --------------------------------------------------------------------------- #
# El Radar mide cuanto "revienta" un tema (`radar.Tema.senal` = trafico aprox. REAL de
# Google Trends). Cuando una pieza nace del Radar, esa señal se PERSISTE en el contenido
# (`senal_viralidad`), para que el score la use al ordenar la lista del dia. Una pieza sin
# señal (la mayoria: alta manual, RSS) tiene 0 y NO cambia su score (degrada con elegancia).
#
# La señal es un trafico enorme (decenas de miles), asi que entra por TRAMOS log-uniformes
# acotados (no en bruto, que aplastaria todo lo demas): un tema muy viral sube por encima de
# lo normal, pero por DEBAJO del compromiso (el must-do humano sigue mandando). Tope acotado.
BONUS_VIRALIDAD_MAX = 60
# Tramos (umbral de señal -> bonus). Ordenados de mayor a menor; el primero que se supera gana.
_TRAMOS_VIRALIDAD: tuple[tuple[int, int], ...] = (
    (500_000, 60),
    (100_000, 45),
    (50_000, 30),
    (10_000, 15),
    (1_000, 5),
)


def peso_viralidad(senal: object) -> int:
    """Bonus por la señal de viralidad persistida (`senal_viralidad`). 0 si no hay/invalida.

    PURA y acotada: la señal cruda (trafico de Trends) entra por TRAMOS (no lineal) para que
    un trending fuerte destaque sin aplastar al resto ni superar al compromiso. <=0 => 0.
    """
    try:
        valor = int(senal)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    if valor <= 0:
        return 0
    for umbral, bonus in _TRAMOS_VIRALIDAD:
        if valor >= umbral:
            return bonus
    return 0


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


# Tras cuantos dias de atraso un vencido DEJA de ser "lo mas urgente" y empieza a decaer:
# una pieza con fecha vencida hace semanas ya no es urgente, es basura vieja que no debe
# quedarse clavada arriba de la lista del dia para siempre.
_VENCIDO_DIAS_PLENO = 7


def peso_fecha(fecha_objetivo: object, hoy: date) -> int:
    """Cuanto pesa la cercania de la fecha objetivo: vencido/hoy urge, lejano pesa poco.

    Un vencido RECIENTE (hasta `_VENCIDO_DIAS_PLENO` dias) es lo mas urgente (150); a partir
    de ahi DECAE por tramos (100 → 40 → 10): lo vencido hace semanas baja en vez de quedarse
    arriba indefinidamente.
    """
    f = _fecha_iso(fecha_objetivo)
    if f is None:
        return 0
    dias = (f - hoy).days
    if dias < 0:
        atraso = -dias
        if atraso <= _VENCIDO_DIAS_PLENO:
            return 150  # vencido reciente: lo mas urgente
        if atraso <= 14:
            return 100
        if atraso <= 30:
            return 40
        return 10  # vencido hace mas de un mes: ya no urge, pesa como lo lejano
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
    item: dict[str, Any],
    *,
    etiquetas: list[str] | None = None,
    hoy: date,
) -> int:
    """Score de un contenido del tablero. `etiquetas` = NOMBRES (no ids) ya resueltos.

    Mayor score = mas arriba en la lista del dia. Determinista; depende solo de sus argumentos.

    Fase 5 (loop de aprendizaje), ADITIVO y DEGRADABLE:
      - `senal_viralidad` del item (señal del Radar persistida): suma `peso_viralidad`. Ausente
        o 0 (la mayoria de piezas) => no cambia nada.
    (El antiguo `bonus_metricas` por marca se RETIRO: nunca tuvo un llamador productivo —
    codigo muerto desde su introduccion. La señal de rendimiento por metricas vive hoy en el
    ranking de historias del pool: `agrupar.puntuar` + `KENI_RENDIMIENTO_RANKING`.)
    """
    etiquetas = etiquetas or []
    score = PESO_PRIORIDAD.get(item.get("prioridad") or "media", PESO_PRIORIDAD["media"])
    score += PESO_FLUJO.get(item.get("flujo") or "", 0)
    score += peso_fecha(item.get("fecha_objetivo") or "", hoy)
    score += peso_frescura(item.get("creado") or "", hoy)
    score += peso_viralidad(item.get("senal_viralidad"))
    if any(_norm(e) == ETIQUETA_COMPROMISO for e in etiquetas):
        score += BONUS_COMPROMISO
    if any(_norm(e) == ETIQUETA_EVERGREEN for e in etiquetas):
        score += BONUS_EVERGREEN
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
            it,
            etiquetas=etiquetas_por_item.get(it.get("id", ""), []),
            hoy=hoy,
        ),
        reverse=True,
    )
