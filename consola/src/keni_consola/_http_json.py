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

import os
from typing import Any

from starlette.exceptions import HTTPException
from starlette.requests import Request

# Tope del BODY JSON aceptado (bytes). Un body sin limite dejaba al servidor parsear
# payloads arbitrarios (memoria + CPU) en cualquier endpoint que use `leer_json`.
# Configurable por entorno (`KENI_JSON_MAX_BYTES`); default 2 MB, de sobra para
# cualquier cuerpo legitimo de la consola (los binarios van por /api/media, no por JSON).
_JSON_MAX_BYTES_DEF = 2 * 1024 * 1024


def _json_max_bytes() -> int:
    """Tope de bytes del body JSON (env `KENI_JSON_MAX_BYTES`, fallback 2 MB)."""
    try:
        n = int(os.environ.get("KENI_JSON_MAX_BYTES", "") or _JSON_MAX_BYTES_DEF)
    except (TypeError, ValueError):
        return _JSON_MAX_BYTES_DEF
    return n if n >= 1 else _JSON_MAX_BYTES_DEF


async def leer_json(request: Request) -> dict[str, Any]:
    """Lee el body de `request` como JSON y devuelve un `dict`.

    Si el body falta, esta malformado o no es un objeto JSON, devuelve `{}` en vez
    de lanzar. El llamante valida los campos que espera sobre el dict resultante.

    EXCEPCION (unica) al "nunca lanza": un body MAS GRANDE que el tope del servidor
    (`KENI_JSON_MAX_BYTES`, def 2 MB) se rechaza con 413 via `HTTPException` ANTES de
    parsear (primero por `Content-Length` si viene, y siempre por el tamaño real leido).
    Tratarlo como `{}` seria mentirle al cliente ("falta el campo X" en vez de "tu
    payload es enorme") y el parseo en si ya es el coste que se quiere evitar.
    """
    tope = _json_max_bytes()
    largo = request.headers.get("content-length")
    try:
        if largo is not None and int(largo) > tope:
            raise HTTPException(
                status_code=413, detail="El cuerpo JSON supera el tamaño máximo permitido."
            )
    except (TypeError, ValueError):
        pass  # Content-Length ilegible: decide el tamaño real del body, abajo.
    try:
        cuerpo = await request.body()
    except Exception:  # noqa: BLE001 -- body ilegible => dict vacio, sin lanzar
        return {}
    if len(cuerpo) > tope:
        raise HTTPException(
            status_code=413, detail="El cuerpo JSON supera el tamaño máximo permitido."
        )
    try:
        # `request.json()` reutiliza el body ya leido (Starlette lo cachea en `_body`).
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


# Cap de SERVIDOR para los listados grandes (publicaciones/contenido): sin `?limite=`
# explicito, los endpoints devolvian el conjunto COMPLETO (full scan + serializacion sin
# tope). 1000 no rompe a ningun cliente actual del piloto (universos muy por debajo) y
# acota el peor caso; el SPA pagina la vista de lista por su cuenta.
_TOPE_LISTADO_DEF = 1000


def tope_listado() -> int:
    """Cap de filas de un listado grande (env `KENI_LISTADO_MAX`, fallback 1000)."""
    try:
        n = int(os.environ.get("KENI_LISTADO_MAX", "") or _TOPE_LISTADO_DEF)
    except (TypeError, ValueError):
        return _TOPE_LISTADO_DEF
    return n if n >= 1 else _TOPE_LISTADO_DEF


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


def cursor_query(request: Request) -> tuple[str, str] | None:
    """Lee `?cursor=<creado>|<id>` (keyset) y devuelve `(creado, id)` o None.

    El cursor codifica la ULTIMA clave vista del listado ordenado por
    `(creado DESC, id DESC)` como `"<creado>|<id>"`. Ausente, vacio o mal formado
    (sin separador `|`, o con alguna mitad vacia) => None (sin paginar por keyset; el
    handler cae al modo offset/completo de siempre). Tolerante por diseño: nunca lanza.
    """
    crudo = request.query_params.get("cursor")
    if not crudo:
        return None
    creado, sep, ident = crudo.partition("|")
    if not sep or not creado or not ident:
        return None
    return creado, ident


def envoltura_paginacion(
    total: int,
    limite: int | None,
    desplazamiento: int,
    *,
    cursor_siguiente: str | None = None,
) -> dict[str, int | str]:
    """Construye el bloque `paginacion:{total, limite, desplazamiento}` del envelope.

    `limite` se reporta como el valor efectivo: si no se paginó (`None`), se reporta
    `total` (el cliente ve que la pagina abarca todo el conjunto).

    `cursor_siguiente` (keyset): clave `"<creado>|<id>"` para pedir la SIGUIENTE pagina,
    o None si no hay mas (ultima pagina) o no se pagina por keyset. Se OMITE de la
    respuesta cuando es None (campo opcional aditivo; no afecta a los callers offset).
    """
    env: dict[str, int | str] = {
        "total": total,
        "limite": total if limite is None else limite,
        "desplazamiento": desplazamiento,
    }
    if cursor_siguiente is not None:
        env["cursor_siguiente"] = cursor_siguiente
    return env
