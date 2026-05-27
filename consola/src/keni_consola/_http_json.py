"""Helper compartido para leer el body JSON de una peticion de la consola.

Varias features (Proyectos, Carpetas, Configuracion, Skills...) repiten el mismo
patron: intentar `await request.json()` envuelto en un try/except y, si el body
no es un objeto JSON valido, tratarlo como vacio. Esto lo centraliza para que el
manejo sea identico en toda la consola (y se pueda endurecer en un solo sitio).

Diseno: NUNCA lanza. Un body ausente, malformado o que no sea un objeto JSON
(p.ej. una lista o un numero) se traduce a `{}`. Asi el llamante valida los
campos que necesita con un unico camino ("falta X") en vez de gestionar parseos.

USO (lo consumiran las features en otra ola):

    from .._http_json import leer_json

    datos = await leer_json(request)        # siempre un dict
    marca = datos.get("marca")
    if not isinstance(marca, str):
        return JSONResponse({"error": "Falta marca."}, status_code=400)
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request


async def leer_json(request: Request) -> dict[str, Any]:
    """Lee el body de `request` como JSON y devuelve un `dict`.

    Si el body falta, esta malformado o no es un objeto JSON, devuelve `{}` en vez
    de lanzar. El llamante valida los campos que espera sobre el dict resultante.
    """
    try:
        datos = await request.json()
    except Exception:  # noqa: BLE001 -- body invalido/ausente => dict vacio, sin lanzar
        return {}
    if not isinstance(datos, dict):
        return {}
    return datos


def _entero_query(valor: str | None, *, minimo: int = 0) -> int | None:
    """Parsea un parametro de query como entero >= `minimo`; None si ausente/invalido."""
    if valor is None or valor == "":
        return None
    try:
        n = int(valor)
    except (TypeError, ValueError):
        return None
    return n if n >= minimo else None


def paginacion_query(request: Request) -> tuple[int | None, int]:
    """Lee `?limite=&desplazamiento=` y devuelve `(limite, desplazamiento)`.

    Politica RETROCOMPATIBLE (envelope aditivo): si NO viene `limite`, devuelve
    `(None, 0)` => el dominio devuelve el conjunto COMPLETO (comportamiento previo);
    el handler igual incluye `paginacion` con `total` real. `limite` debe ser >= 1
    (un `limite` ausente/0/negativo/no-numerico => sin paginar). `desplazamiento` cae
    a 0 si falta o es invalido. Offset-based (el envelope queda listo para `cursor`).
    """
    qp = request.query_params
    limite = _entero_query(qp.get("limite"), minimo=1)
    desplazamiento = _entero_query(qp.get("desplazamiento"), minimo=0) or 0
    return limite, desplazamiento


def envoltura_paginacion(total: int, limite: int | None, desplazamiento: int) -> dict[str, int]:
    """Construye el bloque `paginacion:{total, limite, desplazamiento}` del envelope.

    `limite` se reporta como el valor efectivo: si no se paginó (`None`), se reporta
    `total` (el cliente ve que la pagina abarca todo el conjunto).
    """
    return {
        "total": total,
        "limite": total if limite is None else limite,
        "desplazamiento": desplazamiento,
    }
