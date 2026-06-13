"""Reloj canónico del sistema: timestamps TEXT en UTC SIN offset (naive-UTC).

PROBLEMA QUE CIERRA: los timestamps se persisten como TEXT y se comparan/ordenan
LEXICOGRÁFICAMENTE en SQL (`creado < ?`, `ts < ?`, índices UNIQUE sobre el texto
crudo). El repo mezclaba dos formatos incompatibles para ese orden:
  - naive `datetime.now().isoformat(timespec="seconds")` (el ~80% de los datos), y
  - aware `datetime.now(UTC).isoformat()` con sufijo "+00:00" (y a veces microsegundos).
"2026-06-09T12:00:00" y "2026-06-09T12:00:00+00:00" NO ordenan bien entre sí como texto.

CANON ELEGIDO (el que minimiza la migración: los contenedores corren en UTC, así que
el formato naive existente YA ES UTC):

    YYYY-MM-DDTHH:MM:SS   — UTC, sin offset, precisión de segundos.

Todo timestamp NUEVO que se compare/ordene contra otras filas debe generarse con
`ahora_iso()` (o formatearse con `iso_utc()` si ya se tiene un datetime). Los valores
viejos con "+00:00"/microsegundos los normaliza la migración idempotente de
`_db_core._normalizar_timestamps_texto`.

EXCEPCIONES documentadas:
  - `fecha_programada` usa precisión de MINUTOS (`YYYY-MM-DDTHH:MM`), porque es el
    formato que generan las franjas/cadencias y el picker de la UI; su canon vive en
    `api/publicaciones._normalizar_fecha_programada`.
  - Algunas columnas `creado` de DESEMPATE (fuentes_rss/fuentes_algoritmo/
    sugerencias_editoriales/evergreen_ideas/lotes e items de insumos) usan naive-UTC
    con MICROSEGUNDOS a propósito: el listado ordena `creado DESC` y dos altas en el
    mismo segundo quedaban en orden indefinido. El formato es COMPATIBLE con el canon
    para el orden lexicográfico (la fracción extiende al mismo prefijo, sin offset),
    así que NO se normalizan ni deben ganar "+00:00" jamás.

Módulo SIN dependencias internas (solo stdlib): importable desde db, dominio y api.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

# Jornada del equipo AMX (piloto): zona del centro de México, que NO observa DST desde 2022
# (offset FIJO UTC-6). Se modela como offset fijo a propósito —no `zoneinfo`— para no
# depender de la base IANA del sistema (las imágenes `python:3.12-slim` no traen `tzdata`).
_TZ_CDMX = timezone(timedelta(hours=-6))


def ahora_iso() -> str:
    """Instante ACTUAL en el formato canónico: ISO UTC sin offset, segundos.

    Es UTC real (no la zona local del proceso): `datetime.now(UTC)` con el tzinfo
    despojado. En los contenedores (que corren en UTC) coincide con el histórico
    `datetime.now().isoformat(timespec="seconds")`; en una máquina con otra zona
    corrige el sesgo que el naive local introducía.
    """
    return datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="seconds")


def iso_utc(dt: datetime) -> str:
    """Formatea `dt` al canon (UTC sin offset, segundos). Naive se ASUME UTC.

    Convención del sistema (igual que `programador._a_utc`): un datetime sin zona ES
    UTC. Uno aware se convierte a UTC antes de despojar el offset.
    """
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt.isoformat(timespec="seconds")


def iso_o_vacio(valor: Any) -> str:
    """Serializa un valor de fecha al canon TEXT histórico que la API venía emitiendo.

    Cierra la brecha que abrió la migración de columnas de fecha TEXT → tipos nativos de
    Postgres (timestamptz/date, ver migración 0033). Con `dict_row`, una columna `timestamptz`
    vuelve como `datetime` (aware UTC) y una `date` como `date`; los serializadores de la API
    (`_fila_a_*`, listados de jobs/gasto/eventos) deben volver a emitir EXACTAMENTE el mismo
    string ISO que antes para no romper el contrato de forma de respuesta (ni el keyset del
    feed, que compara el `creado` serializado como cursor):

      - `datetime`  -> canon UTC sin offset, segundos (`iso_utc`):  "YYYY-MM-DDTHH:MM:SS".
      - `date`      -> ISO de fecha:                                "YYYY-MM-DD".
      - `None`/`''` -> "" (el sentinel "sin valor" del esquema heredado; p. ej. un job aún sin
                       `claimed_at`, que antes era '' y ahora es NULL).
      - `str`       -> tal cual (compat: BD aún TEXT, o un valor ya canónico).
    """
    if valor is None or valor == "":
        return ""
    if isinstance(valor, datetime):
        return iso_utc(valor)
    if isinstance(valor, date):
        return valor.isoformat()
    return str(valor)


def hoy_utc() -> date:
    """Fecha ACTUAL en UTC (no la zona local del proceso), para columnas `YYYY-MM-DD`.

    Las fechas-día persistidas/comparadas (`fecha`, `fecha_objetivo`, cortes `>= ?`)
    siguen el mismo convenio que los timestamps: el día se mide en UTC. En los
    contenedores (UTC) coincide con el histórico `date.today()`; en una máquina con
    otra zona elimina el desfase alrededor de la medianoche.
    """
    return datetime.now(UTC).date()


def inicio_dia_cdmx_iso_utc(momento: datetime | None = None) -> str:
    """Medianoche de HOY en CDMX (America/Mexico_City), como timestamp ISO-UTC canónico.

    Corte del PLAN DIARIO: lo «generado/publicado hoy» se mide por la JORNADA LOCAL del
    equipo (la parrilla del día), no por una ventana móvil de 24 h. Así el contador vuelve
    a 0 en la medianoche de México y la admisión reabre los cupos del día siguiente.

    Convención de `momento` igual que `iso_utc`: `None` = ahora; un naive se ASUME UTC; un
    aware se respeta. Se floor-ea a la medianoche en zona MX y se devuelve en el canon (UTC
    sin offset, segundos) para comparar contra `creado >= ?` (que es UTC naive). Ej.: con MX
    en UTC-6, la medianoche MX del 2026-06-11 es «2026-06-11T06:00:00».
    """
    if momento is None:
        dt = datetime.now(UTC)
    elif momento.tzinfo is None:
        dt = momento.replace(tzinfo=UTC)
    else:
        dt = momento
    medianoche_mx = dt.astimezone(_TZ_CDMX).replace(hour=0, minute=0, second=0, microsecond=0)
    return medianoche_mx.astimezone(UTC).replace(tzinfo=None).isoformat(timespec="seconds")
