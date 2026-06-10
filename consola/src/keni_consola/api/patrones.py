"""API Patrones: perfil de patrones medidos por marca + verificación de voz (ADR 0009).

Expone en HTTP lo que ya consumen el pipeline de copy y el verificador de voz:

  - `GET /api/patrones`            -> marcas del catálogo y si tienen perfil derivado.
  - `GET /api/patrones?marca=<id>` -> el perfil completo de esa marca (bandas top/fondo
    por red + reglas de lint), o 404 si la marca aún no tiene perfil (sin datos no se
    inventa).
  - `POST /api/patrones/verificar-voz` (JSON `{marca, texto, redes?, copy_unico?}`) ->
    los avisos del lint determinista de voz para ese texto, por red. Es la MISMA
    verificación que corre el post-procesado del copy (`dominio.copy.verificar_voz`),
    expuesta para revisar un borrador A MANO (o desde el MCP) antes de enviarlo.

SOLO LECTURA + cómputo puro: nada de esto muta estado ni llama a la red.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import marcas, patrones_marca, redes
from .._http_json import leer_json


async def perfil(request: Request) -> Response:
    """GET /api/patrones[?marca=]: el perfil de una marca, o el índice de marcas con perfil."""
    marca = (request.query_params.get("marca") or "").strip()
    if not marca:
        indice = [
            {"marca": m, "tiene_perfil": patrones_marca.cargar_perfil(m) is not None}
            for m, _ in marcas.opciones()
        ]
        return JSONResponse({"marcas": indice})
    if not marcas.es_marca(marca):
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)
    datos = patrones_marca.cargar_perfil(marca)
    if datos is None:
        return JSONResponse(
            {"error": "Esa marca aún no tiene perfil de patrones (sin datos suficientes)."},
            status_code=404,
        )
    return JSONResponse({"perfil": datos})


async def verificar_voz(request: Request) -> Response:
    """POST /api/patrones/verificar-voz: lint de voz de un texto contra el perfil de su marca.

    Cuerpo `{marca, texto, redes?: [ids], copy_unico?: bool}`. Sin `redes`, se verifica
    contra TODAS las redes del catálogo que tengan reglas en el perfil. `copy_unico`
    (def True) aplica además el contrato del copy unificado (sin hashtags). Devuelve
    `{avisos, dentro_de_patron}`; sin perfil para la marca, avisos solo de contrato.
    """
    datos = await leer_json(request)
    marca = datos.get("marca")
    if not isinstance(marca, str) or not marcas.es_marca(marca):
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)
    texto = datos.get("texto")
    if not isinstance(texto, str) or not texto.strip():
        return JSONResponse({"error": "Falta el texto a verificar."}, status_code=400)
    copy_unico = bool(datos.get("copy_unico", True))
    crudas = datos.get("redes")
    if crudas is None:
        ids_redes = redes.ids()
    elif isinstance(crudas, list) and all(isinstance(r, str) for r in crudas):
        invalidas = [r for r in crudas if not redes.es_red(r)]
        if invalidas:
            return JSONResponse(
                {"error": f"Red(es) desconocida(s): {', '.join(invalidas)}."}, status_code=400
            )
        ids_redes = crudas
    else:
        return JSONResponse({"error": "`redes` debe ser una lista de ids de red."}, status_code=400)

    piezas = [{"red": r, "contenido": texto} for r in ids_redes]
    avisos = patrones_marca.avisos_de_piezas(marca, piezas, copy_unico=copy_unico)
    return JSONResponse({"avisos": avisos, "dentro_de_patron": not avisos})


RUTAS = [
    Route("/api/patrones", perfil, methods=["GET"]),
    Route("/api/patrones/verificar-voz", verificar_voz, methods=["POST"]),
]
