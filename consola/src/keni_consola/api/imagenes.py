"""API Estudio de imagen: generar variantes, editar (determinista) y expandir (outpainting).

Superficie de primera clase que sustituye a la skill `estudio-imagen`. Cada endpoint que
"produce pixeles" responde de INMEDIATO con un registro de generacion (tipo "imagen") y el
frontend SONDEA `GET /api/generaciones/{id}`; al completarse recoge `resultado` con
`{id, url, imagenes:[...]}`. Reutiliza `generaciones.lanzar_job_imagen` (runner generico de
un callable en un hilo) y el almacen de media. El dominio (`dominio.estudio_imagen`) hace el
trabajo real y es mockeable: los tests nunca tocan la red ni Pillow.

Asociar el arte a una pieza NO vive aqui: se hace con el seam existente
`PUT /api/publicaciones/{id}` (`{imagen}`). Subir/servir siguen en `/api/media`.

SEGURIDAD: entradas validadas (op, formato, marca, numeros) antes de tocar el motor; sin
shell; errores en espanol sin tracebacks.
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import generaciones, marcas, media
from .._http_json import leer_json
from ..dominio import estudio_imagen
from ..seguridad import autor_de_peticion

# Tope de variantes generativas por peticion (coste): 1..4, def. 2.
_MAX_VARIANTES = 4


def _autor(request: Request) -> dict[str, str]:
    a = autor_de_peticion(request) or {}
    return {"autor_id": a.get("id", ""), "autor_nombre": a.get("usuario", "")}


def _lanzar(request: Request, etiqueta: str, generar) -> dict[str, Any]:  # noqa: ANN001
    """Crea un registro de generacion (tipo imagen) y lanza `generar` en segundo plano."""
    gen = generaciones.crear({"tipo": "imagen", "marca": "", "etiqueta": etiqueta, **_autor(request)})
    try:
        generaciones.lanzar_job_imagen(gen["id"], generar=generar)
    except Exception:  # noqa: BLE001 -- nunca traceback crudo; reflejamos el error en el registro
        generaciones.actualizar(
            gen["id"],
            {"estado": generaciones.ESTADO_ERROR, "error": "No se pudo iniciar la operacion.",
             "fecha_fin": generaciones.ahora_iso()},
        )
    return generaciones.obtener(gen["id"]) or gen


async def generar(request: Request) -> Response:
    """Genera N variantes de imagen (IA) -> `{generaciones:[...]}` (una por variante)."""
    datos = await leer_json(request)
    prompt = datos.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return JSONResponse({"error": "Describe la imagen que quieres generar."}, status_code=400)
    if not media.proveedor_configurado():
        return JSONResponse(
            {"error": "La generacion de imagen no esta configurada. Anade una clave de "
                      "proveedor de imagen para activarla."},
            status_code=400,
        )
    marca = datos.get("marca") if isinstance(datos.get("marca"), str) else ""
    if marca and not marcas.es_marca(marca):
        return JSONResponse({"error": "Marca desconocida."}, status_code=400)
    formato = datos.get("formato") if datos.get("formato") in estudio_imagen.FORMATOS else "feed"
    prompt_id = datos.get("prompt_id")
    prompt_id = prompt_id if isinstance(prompt_id, str) and prompt_id.strip() else estudio_imagen.PROMPT_IMAGEN_DEFECTO
    try:
        variantes = int(datos.get("variantes", 2))
    except (TypeError, ValueError):
        variantes = 2
    variantes = max(1, min(_MAX_VARIANTES, variantes))

    prompt_final = estudio_imagen.componer_prompt(prompt.strip(), marca, formato, prompt_id)

    def _hacer() -> dict[str, Any]:
        return estudio_imagen.generar_variante(prompt_final)

    etiqueta = f"Imagen · {prompt.strip()[:40]}"
    gens = [_lanzar(request, etiqueta, _hacer) for _ in range(variantes)]
    return JSONResponse({"generaciones": gens})


def _num(datos: dict[str, Any], clave: str) -> float | None:
    try:
        return float(datos[clave])
    except (KeyError, TypeError, ValueError):
        return None


async def editar(request: Request) -> Response:
    """Operacion DETERMINISTA (recortar/redimensionar/comprimir/extender/placa) -> `{generacion}`."""
    datos = await leer_json(request)
    op = datos.get("op")
    if op not in estudio_imagen.OPS_EDITAR:
        return JSONResponse(
            {"error": f"Operacion no soportada. Usa una de: {', '.join(estudio_imagen.OPS_EDITAR)}."},
            status_code=400,
        )
    imagen = datos.get("imagen") if isinstance(datos.get("imagen"), str) else ""
    if not imagen and op != "placa":
        return JSONResponse({"error": "Falta la imagen sobre la que operar."}, status_code=400)

    formato = datos.get("formato") if datos.get("formato") in estudio_imagen.FORMATOS else "feed"
    params: dict[str, Any] = {"formato": formato}
    if op == "redimensionar":
        lado = _num(datos, "max")
        if lado is None or lado <= 0:
            return JSONResponse({"error": "Indica el lado maximo (px) para redimensionar."}, status_code=400)
        params["max"] = int(lado)
    elif op == "comprimir":
        peso = _num(datos, "peso_max_mb") or 2.0
        params["peso_max_mb"] = max(0.1, peso)
        fmt = datos.get("formato_archivo")
        params["formato_archivo"] = fmt if fmt in ("jpg", "webp") else "jpg"
    elif op == "extender":
        metodo = datos.get("metodo")
        params["metodo"] = metodo if metodo in ("borde", "color") else "borde"
        params["forzar"] = bool(datos.get("forzar"))
    elif op == "placa":
        texto = datos.get("texto")
        if not isinstance(texto, str) or not texto.strip():
            return JSONResponse({"error": "Escribe el texto de la placa."}, status_code=400)
        marca = datos.get("marca")
        if marca not in estudio_imagen._MARCAS_VISUALES:
            return JSONResponse(
                {"error": "La placa solo esta disponible para: "
                          + ", ".join(estudio_imagen._MARCAS_VISUALES) + "."},
                status_code=400,
            )
        params.update({"texto": texto.strip(), "marca": marca})
        cita = datos.get("fuente_cita")
        if isinstance(cita, str) and cita.strip():
            params["fuente_cita"] = cita.strip()

    def _hacer() -> dict[str, Any]:
        return estudio_imagen.editar(imagen, op, params)

    return JSONResponse({"generacion": _lanzar(request, f"Editar · {op}", _hacer)})


async def expandir(request: Request) -> Response:
    """Outpainting GENERATIVO (fiel al sujeto) a un formato -> `{generacion}`."""
    datos = await leer_json(request)
    imagen = datos.get("imagen") if isinstance(datos.get("imagen"), str) else ""
    if not imagen:
        return JSONResponse({"error": "Falta la imagen que quieres expandir."}, status_code=400)
    if not media.proveedor_configurado():
        return JSONResponse(
            {"error": "La expansion de imagen necesita un proveedor de imagen configurado."},
            status_code=400,
        )
    formato = datos.get("formato") if datos.get("formato") in estudio_imagen.FORMATOS else "feed"
    marca = datos.get("marca") if isinstance(datos.get("marca"), str) else ""
    if marca and not marcas.es_marca(marca):
        return JSONResponse({"error": "Marca desconocida."}, status_code=400)
    strength = _num(datos, "strength")
    if strength is not None:
        strength = max(0.0, min(1.0, strength))
    lado = datos.get("lado")
    lado = lado if lado in ("auto", "arriba", "abajo", "izquierda", "derecha") else "auto"

    def _hacer() -> dict[str, Any]:
        return estudio_imagen.expandir(imagen, formato=formato, marca=marca, strength=strength, lado=lado)

    return JSONResponse({"generacion": _lanzar(request, f"Expandir · {formato}", _hacer)})


async def revisar(request: Request) -> Response:
    """Revision legal/editorial de una imagen (gate humano, `claude` la VE) -> `{generacion}`.

    NO bloquea publicar: lanza un job `claude` que aplica las reglas de imagen de la Biblioteca
    y devuelve un checklist ✅/⚠️/❌; el frontend SONDEA `GET /api/generaciones/{id}` y muestra
    el texto en vivo (`salida`). El registro es de tipo "qa-editorial" (revision editorial).
    """
    datos = await leer_json(request)
    imagen = datos.get("imagen") if isinstance(datos.get("imagen"), str) else ""
    if not imagen.strip():
        return JSONResponse({"error": "Falta la imagen que quieres revisar."}, status_code=400)
    marca = datos.get("marca") if isinstance(datos.get("marca"), str) else ""
    if marca and not marcas.es_marca(marca):
        return JSONResponse({"error": "Marca desconocida."}, status_code=400)
    try:
        gen = estudio_imagen.revisar(
            imagen.strip(), marca=marca, autor=autor_de_peticion(request)
        )
    except estudio_imagen.EstudioError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"generacion": gen})


RUTAS = [
    Route("/api/imagenes/generar", generar, methods=["POST"]),
    Route("/api/imagenes/editar", editar, methods=["POST"]),
    Route("/api/imagenes/expandir", expandir, methods=["POST"]),
    Route("/api/imagenes/revisar", revisar, methods=["POST"]),
]
