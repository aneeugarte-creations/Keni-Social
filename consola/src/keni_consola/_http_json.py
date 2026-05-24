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
