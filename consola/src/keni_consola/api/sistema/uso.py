"""Uso de las cuentas de Claude del servidor: LECTURA del último snapshot, ACOTADO por usuario.

A diferencia de `cuenta.py` (que PROXEA al control del `daemons` y dispara `claude -p /usage`
en vivo), este endpoint solo LEE la tabla `cuenta_uso` que el muestreo de fondo
(`cuenta_uso_daemon`) mantiene POR CUENTA (A/B). Así el indicador siempre-visible de la barra
lateral consulta un dato barato y persistido, sin ejecutar `claude` ni depender del `daemons`.

Endpoint (bajo `/api/sistema`, CONTRATO con el frontend):
  - GET /api/sistema/uso -> {cuentas: [{cuenta, etiqueta, marcas, conectada, semana_pct,
      sesion_5h_pct, sonnet_pct, reset_semana_iso, reset_semana_txt, actualizado_ts, al_100,
      alerta_roja}, ...]}

Cualquier usuario AUTENTICADO lo consulta, pero solo recibe LAS CUENTAS DE SUS MARCAS (suelo de
autorización): admin/superadmin reciben ambas; un editor la(s) cuenta(s) de sus marcas
(`ruteo_cuentas.cuentas_visibles`). Editor sin marcas (o token de mantenimiento, sin usuario) ->
`{cuentas: []}` (el front no pinta nada). Cada cuenta trae `marcas` (ids canónicos) para que el
frontend DECIDA cuál mostrar según el selector de marca activo (solo la cuenta de la marca activa;
ambas en "Todas").

`alerta_roja` por cuenta (la señal que enciende el indicador en rojo) = cuenta DESCONECTADA o
semana al 100%+. Sin snapshot todavía (cold start) se trata como desconectada: `alerta_roja=true`.
"""

from __future__ import annotations

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ... import permisos, repos, ruteo_cuentas


def _forma_respuesta(fila: dict | None) -> dict:
    """Construye la forma del contrato a partir de la fila de `cuenta_uso` (PURA).

    Sin fila (nunca se muestreó esa cuenta) -> todo nulo, cuenta no conectada y `alerta_roja=true`.
    Los `*_pct` viajan como int|null; los resets vacíos ('') se normalizan a null.
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


def _forma_cuenta(cuenta: str, fila: dict | None) -> dict:
    """La forma del contrato de UNA cuenta: snapshot + `cuenta` + `etiqueta` + `marcas` (ids).

    `marcas` (ids canónicos de las marcas que sirve la cuenta) deja al frontend casar el selector de
    marca activo contra la cuenta; `etiqueta` es su nombre legible (los mismos nombres unidos).
    """
    return {
        "cuenta": cuenta,
        "etiqueta": ruteo_cuentas.etiqueta_de_cuenta(cuenta),
        "marcas": ruteo_cuentas.marcas_de_cuenta(cuenta),
        **_forma_respuesta(fila),
    }


async def uso(request: Request) -> Response:
    """GET /api/sistema/uso: snapshot del uso de las cuentas que el usuario puede ver. NO ejecuta `claude`."""
    es_admin = permisos.es_admin(request) or permisos.es_superadmin(request)
    visibles = ruteo_cuentas.cuentas_visibles(
        es_admin=es_admin, marcas=permisos.marcas_asignadas(request)
    )
    if not visibles:
        return JSONResponse({"cuentas": []})
    snapshots = await run_in_threadpool(repos.leer_uso_cuentas)
    return JSONResponse({"cuentas": [_forma_cuenta(c, snapshots.get(c)) for c in visibles]})
