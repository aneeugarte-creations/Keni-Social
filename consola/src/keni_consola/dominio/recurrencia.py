"""Dominio de RECURRENCIA de eventos de la rota: expansión PURA de una serie.

Una serie recurrente se define por `(fecha_base, dias_semana, repetir_hasta)` y se
MATERIALIZA en fechas concretas: una fila `rota_eventos` por ocurrencia (la cobertura
se deriva de los turnos que solapan cada fecha, así que cada ocurrencia funciona sola).

Convenio de día de semana: 0=lunes … 6=domingo (igual que `datetime.weekday()`), el
mismo que `dominio.franjas`. La lógica es PURA y determinista (sin reloj ni BD), para
poder testearla aislada.
"""
from __future__ import annotations

from datetime import date, timedelta

# Tope de seguridad: una serie no materializa más de ~1 año de ocurrencias. Evita que
# un `repetir_hasta` lejano (o ausente) genere miles de filas sin querer.
HORIZONTE_MAXIMO_DIAS = 366

_DIAS_SEMANA_VALIDOS = frozenset(range(7))


def normalizar_dias_semana(dias: object) -> list[int]:
    """Días de semana saneados: enteros 0..6, sin duplicados y ordenados.

    Acepta cualquier iterable (lista del request); descarta lo que no sea un entero
    0..6 (un `bool` NO cuenta como entero válido aquí). Lista vacía = sin recurrencia.
    """
    if not isinstance(dias, (list, tuple, set, frozenset)):
        return []
    limpios: set[int] = set()
    for d in dias:
        if isinstance(d, bool):
            continue
        if isinstance(d, int) and d in _DIAS_SEMANA_VALIDOS:
            limpios.add(d)
    return sorted(limpios)


def dias_semana_a_csv(dias: list[int]) -> str:
    """Serializa los días (0..6) a CSV ("0,1,2,3,4") para la columna de la serie."""
    return ",".join(str(d) for d in normalizar_dias_semana(dias))


def csv_a_dias_semana(csv: str) -> list[int]:
    """Parsea el CSV de la columna de la serie de vuelta a días normalizados."""
    if not csv:
        return []
    crudos: list[int] = []
    for trozo in csv.split(","):
        trozo = trozo.strip()
        if trozo.isdigit():
            crudos.append(int(trozo))
    return normalizar_dias_semana(crudos)


def _parse_iso(valor: object) -> date | None:
    """`date` desde un ISO 'AAAA-MM-DD', o None si no es una fecha válida."""
    if not isinstance(valor, str):
        return None
    try:
        return date.fromisoformat(valor)
    except ValueError:
        return None


def fechas_recurrencia(
    fecha_base: str,
    dias_semana: object,
    repetir_hasta: str,
    *,
    tope_dias: int = HORIZONTE_MAXIMO_DIAS,
) -> list[str]:
    """Fechas ISO (ordenadas y únicas) que materializan la serie.

    Incluye SIEMPRE `fecha_base` (es el evento que el usuario está creando, exista o no
    su día de semana en el patrón) y añade cada fecha de `(fecha_base, repetir_hasta]`
    cuyo weekday ∈ `dias_semana`. Se acota a `tope_dias` desde la base.

    Devuelve `[]` si `fecha_base` no es una fecha válida. Sin `dias_semana` (vacío) o sin
    `repetir_hasta` válido devuelve solo `[fecha_base]` (un único evento, sin recurrencia).
    """
    base = _parse_iso(fecha_base)
    if base is None:
        return []
    dias = set(normalizar_dias_semana(dias_semana))
    limite = base + timedelta(days=max(0, tope_dias))
    fin = _parse_iso(repetir_hasta)
    if fin is None or fin > limite:
        fin = limite

    fechas: set[date] = {base}
    if dias:
        dia = base + timedelta(days=1)
        while dia <= fin:
            if dia.weekday() in dias:
                fechas.add(dia)
            dia += timedelta(days=1)
    return [f.isoformat() for f in sorted(fechas)]
