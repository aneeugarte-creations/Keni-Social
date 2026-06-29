"""Uso de la cuenta de Claude del servidor (panel ADMIN): LECTURA del último snapshot.

A diferencia de `cuenta.py` (que PROXEA al control del `daemons` y dispara `claude -p /usage`
en vivo), este endpoint solo LEE la tabla `cuenta_uso` que el muestreo de fondo
(`cuenta_uso_daemon`) mantiene. Así el indicador siempre-visible de la barra lateral y el gate
diario consultan un dato barato y persistido, sin ejecutar `claude` ni depender del `daemons`.

Endpoint (bajo `/api/sistema`, CONTRATO con el frontend):
  - GET /api/sistema/uso -> {conectada, semana_pct, sesion_5h_pct, sonnet_pct,
      reset_semana_iso, reset_semana_txt, actualizado_ts, al_100, alerta_roja}

`alerta_roja` (la señal que enciende el indicador en rojo) = cuenta DESCONECTADA o semana al
100%+. Sin snapshot todavía (cold start) se trata como desconectada: `alerta_roja=true`.
"""

from __future__ import annotations

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ... import repos
from ._comun import _es_admin, _rechazo_no_admin


def _forma_respuesta(fila: dict | None) -> dict:
    """Construye la forma del contrato a partir de la fila de `cuenta_uso` (PURA).

    Sin fila (nunca se muestreó) -> todo nulo, cuenta no conectada y `alerta_roja=true`. Los
    `*_pct` viajan como int|null; los resets vacíos ('') se normalizan a null.
    """
    if fila is None:
        return {
            "conectada": False,
            "semana_pct": None,
            "sesion_5h_pct": None,
            "sonnet_pct": None,
            "reset_semana_iso": None,
            "reset_semana_txt": None,
            "actualizado_ts": None,
            "al_100": False,
            "alerta_roja": True,
        }
    conectada = bool(fila.get("conectada"))
    semana_pct = fila.get("semana_pct")
    al_100 = semana_pct is not None and semana_pct >= 100
    alerta_roja = (not conectada) or al_100
    return {
        "conectada": conectada,
        "semana_pct": semana_pct,
        "sesion_5h_pct": fila.get("sesion_5h_pct"),
        "sonnet_pct": fila.get("sonnet_pct"),
        "reset_semana_iso": (fila.get("reset_semana_iso") or None),
        "reset_semana_txt": (fila.get("reset_semana_txt") or None),
        "actualizado_ts": fila.get("actualizado_ts"),
        "al_100": al_100,
        "alerta_roja": alerta_roja,
    }


async def uso(request: Request) -> Response:
    """GET /api/sistema/uso: último snapshot del uso de la cuenta (admin). NO ejecuta `claude`."""
    if not _es_admin(request):
        return _rechazo_no_admin()
    fila = await run_in_threadpool(repos.leer_uso_cuenta)
    return JSONResponse(_forma_respuesta(fila))
