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

from datetime import UTC, date, datetime


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


def hoy_utc() -> date:
    """Fecha ACTUAL en UTC (no la zona local del proceso), para columnas `YYYY-MM-DD`.

    Las fechas-día persistidas/comparadas (`fecha`, `fecha_objetivo`, cortes `>= ?`)
    siguen el mismo convenio que los timestamps: el día se mide en UTC. En los
    contenedores (UTC) coincide con el histórico `date.today()`; en una máquina con
    otra zona elimina el desfase alrededor de la medianoche.
    """
    return datetime.now(UTC).date()
