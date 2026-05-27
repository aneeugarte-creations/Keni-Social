"""Utilidades comunes de la auth: tiempo UTC y duracion de sesion.

Modulo interno del paquete `auth`: no expone contrato propio, lo reusan
`usuarios.py` (fechas de creacion/acceso, bloqueo) y `sesiones.py` (expiracion
deslizante). Vive aparte para que esos dos no se importen entre si por una fecha.
"""

from __future__ import annotations

from datetime import UTC, datetime

from .. import config

# Env var (opcional) para la duracion de la sesion en horas (def 12h). Nombre/default
# canonicos en `config` (fuente unica); re-exportados aqui por compat de referencias.
ENV_SESION_HORAS = config.ENV_SESION_HORAS
SESION_HORAS_DEF = config.SESION_HORAS_DEF


def ahora() -> datetime:
    """Instante actual en UTC (con tzinfo), para comparar fechas sin ambiguedad."""
    return datetime.now(UTC)


def iso(momento: datetime) -> str:
    """Serializa un datetime a ISO-8601 (segundos), para guardar en SQLite."""
    return momento.astimezone(UTC).isoformat(timespec="seconds")


def parsear_iso(texto: str) -> datetime | None:
    """Parsea un ISO-8601 guardado; None si esta vacio o es ilegible."""
    if not texto:
        return None
    try:
        momento = datetime.fromisoformat(texto)
    except ValueError:
        return None
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=UTC)
    return momento


def horas_sesion() -> int:
    """Duracion de la sesion en horas (env `KENI_CONSOLA_SESION_HORAS`, def 12)."""
    return config.sesion_horas()
