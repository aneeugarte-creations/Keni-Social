"""Asignación de MARCAS a CUENTAS de Claude (A/B): lectura y edición del reparto, solo admin.

El reparto (qué marca gasta contra qué cuenta) lo decide `ruteo_cuentas`: un reparto por defecto
del piloto + override por marca en el store (`KENI_CUENTA_CLAUDE::<marca>`). Aquí solo se expone
ese mapa al panel de Sistema y se persiste el override que el admin elige, para mover una marca de
una cuenta a otra (p. ej. sacar a una marca de una cuenta agotada). El ruteo del trabajo —tanto la
investigación como el copy— lee de `ruteo_cuentas`, así que el cambio surte efecto en los próximos
jobs sin tocar infraestructura.

Endpoints (bajo `/api/sistema`, CONTRATO con el frontend):
  - GET  /api/sistema/cuenta-marcas -> {cuentas:[{cuenta,etiqueta}], defecto, marcas:[{id,nombre,
      cuenta,por_defecto}]}
  - POST /api/sistema/cuenta-marcas  {marca, cuenta:"a"|"b"|""}  -> mismo cuerpo que el GET ya
      aplicado. `cuenta` vacío LIMPIA el override (la marca vuelve a su reparto por defecto).

Solo SESIÓN admin/superadmin (el reparto gobierna el gasto de toda la operación); el resto -> 403.
"""

from __future__ import annotations

from keni_shared import marcas
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ... import ruteo_cuentas
from ...dominio import jobspec
from ._comun import _es_admin, _rechazo_no_admin


def _mapa() -> dict:
    """Forma del contrato: las dos cuentas (con etiqueta) y cada marca con su cuenta efectiva."""
    cuentas = [
        {"cuenta": c, "etiqueta": ruteo_cuentas.etiqueta_de_cuenta(c)} for c in jobspec.CUENTAS
    ]
    marcas_mapa = [
        {
            "id": mid,
            "nombre": marcas.etiqueta_de(mid),
            "cuenta": ruteo_cuentas.cuenta_de_marca(mid),
            "por_defecto": ruteo_cuentas.override_de_marca(mid) is None,
        }
        for mid in marcas.ids()
    ]
    return {
        "cuentas": cuentas,
        "defecto": ruteo_cuentas.cuenta_por_defecto(),
        "marcas": marcas_mapa,
    }


async def cuenta_marcas(request: Request) -> Response:
    """GET /api/sistema/cuenta-marcas: reparto actual de marcas por cuenta (solo admin)."""
    if not _es_admin(request):
        return _rechazo_no_admin()
    return JSONResponse(await run_in_threadpool(_mapa))


async def asignar_cuenta_marca(request: Request) -> Response:
    """POST /api/sistema/cuenta-marcas: mueve una marca a una cuenta (o limpia su override)."""
    if not _es_admin(request):
        return _rechazo_no_admin()
    try:
        datos = await request.json()
    except Exception:  # noqa: BLE001 -- cuerpo ausente/ilegible -> 400 claro
        return JSONResponse({"error": "Cuerpo JSON inválido."}, status_code=400)
    marca = str((datos or {}).get("marca") or "").strip()
    cuenta = str((datos or {}).get("cuenta") or "").strip().lower()
    if not marca or marca not in set(marcas.ids()):
        return JSONResponse({"error": "Marca desconocida."}, status_code=400)
    if cuenta and cuenta not in jobspec.CUENTAS:
        return JSONResponse({"error": "Cuenta inválida (esperado 'a' o 'b')."}, status_code=400)
    await run_in_threadpool(ruteo_cuentas.asignar_marca, marca, cuenta or None)
    return JSONResponse(await run_in_threadpool(_mapa))
