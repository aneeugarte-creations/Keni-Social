"""API Configuracion: leer y cambiar la fuente de datos y el alcance (marcas).

Consume la fachada estable `keni_metricas.servicio`: lee el estado del config
(fuente, alcance, marcas elegibles, presencia de credenciales) y escribe SOLO
`fuente` + `marcas` (la fachada hace el merge no destructivo + escritura atomica).
Ya no importa internals (`config`/`asistente`).

Las credenciales NUNCA se editan ni se muestran por la API: solo se reporta su
PRESENCIA/AUSENCIA por bloque (meta/youtube/x/tiktok). La ESCRITURA de tokens vive
en `api/conexiones.py`, no aqui.
"""

from __future__ import annotations

from keni_metricas import servicio
from keni_metricas.servicio import FUENTES_DISPONIBLES, ConfigInvalida
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import marcas, preferencias
from .._http_json import leer_json


def _etiqueta_humana(marca_id: str, nombre: str) -> str:
    """Nombre legible (con acentos) de una marca; cae al nombre del config o al id.

    Las marcas del config/fuente vienen en forma `id_metricas` (guion_bajo): se
    resuelven por esa frontera, no por el id canonico.
    """
    marca = marcas.marca_por_id_metricas(marca_id)
    if marca is not None:
        return marca.etiqueta
    return nombre or marca_id


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #


async def obtener_config(request: Request) -> Response:
    try:
        estado = servicio.instantanea_config()
    except ConfigInvalida as e:
        return JSONResponse(
            {"error": f"No se pudo leer tu configuración: {e}"}, status_code=400
        )

    return JSONResponse(
        {
            "fuente": estado["fuente"],
            "fuentes_validas": list(FUENTES_DISPONIBLES),
            "marcas": estado["marcas"],
            "marcas_disponibles": [
                {"id": mid, "nombre": _etiqueta_humana(mid, nombre)}
                for mid, nombre in estado["marcas_disponibles"]
            ],
            "credenciales_presentes": estado["credenciales_presentes"],
        }
    )


async def guardar_config(request: Request) -> Response:
    datos = await leer_json(request)

    fuente = datos.get("fuente")
    if not isinstance(fuente, str) or fuente not in FUENTES_DISPONIBLES:
        validas = ", ".join(FUENTES_DISPONIBLES)
        return JSONResponse(
            {"error": f"Fuente inválida. Usa una de: {validas}."}, status_code=400
        )
    # `real` (adaptadores por plataforma) es un fallback histórico desactivado: dejaría
    # el rendimiento por pieza sin datos (desfase con el tablero). No se ofrece desde la
    # Consola; quien lo necesite lo activa a propósito en el config + flag. La fuente
    # única de producción es `metricool` (con `muestra` para demo).
    if fuente == "real":
        return JSONResponse(
            {
                "error": "La fuente 'real' está desactivada (dejaría el rendimiento por "
                "pieza sin datos). Usa 'metricool' (fuente única) o 'muestra' (demo)."
            },
            status_code=400,
        )

    marcas_crudas = datos.get("marcas", [])
    if not isinstance(marcas_crudas, list) or not all(isinstance(m, str) for m in marcas_crudas):
        return JSONResponse(
            {"error": "El alcance debe ser una lista de marcas."}, status_code=400
        )

    try:
        estado = servicio.instantanea_config()
    except ConfigInvalida as e:
        return JSONResponse(
            {"error": f"No se pudo leer tu configuración: {e}"}, status_code=400
        )

    ids_validos = [mid for mid, _ in estado["marcas_disponibles"]]
    alcance_ids = servicio.normalizar_alcance(marcas_crudas, ids_validos)
    desconocidas = [m for m in marcas_crudas if m.strip() and m.strip() not in ids_validos]
    if desconocidas:
        etiquetas = ", ".join(marcas.etiqueta_por_id_metricas(m) for m in desconocidas)
        return JSONResponse(
            {"error": f"Marcas desconocidas: {etiquetas}."}, status_code=400
        )

    try:
        servicio.guardar_fuente_y_alcance(fuente, alcance_ids)
    except OSError as e:
        return JSONResponse(
            {"error": f"No se pudo guardar la configuración: {e}"}, status_code=400
        )

    alcance = (
        ", ".join(marcas.etiqueta_por_id_metricas(mid) for mid in alcance_ids)
        if alcance_ids
        else "todas las marcas"
    )
    legible = {"metricool": "Metricool", "muestra": "Muestra", "real": "Real"}.get(fuente, fuente)
    return JSONResponse(
        {"mensaje": f"Configuración guardada. Fuente: {legible}. Alcance: {alcance}."}
    )


# --------------------------------------------------------------------------- #
# Esfuerzo de generacion (claude --effort) — preferencia local del equipo      #
# --------------------------------------------------------------------------- #

# Opciones que pinta la UI. El backend es la fuente de verdad de id/etiqueta/ayuda;
# el id "" es el predeterminado del modelo (no se pasa `--effort`). Orden estable.
_ESFUERZO_OPCIONES: tuple[dict[str, str], ...] = (
    {
        "id": "",
        "etiqueta": "Predeterminado",
        "descripcion": "Usa el esfuerzo por defecto del modelo. Equilibrado y recomendado.",
    },
    {
        "id": "low",
        "etiqueta": "Bajo",
        "descripcion": "Responde antes y piensa menos. Para borradores rápidos.",
    },
    {
        "id": "medium",
        "etiqueta": "Medio",
        "descripcion": "Equilibrio entre rapidez y calidad.",
    },
    {
        "id": "high",
        "etiqueta": "Alto",
        "descripcion": "Piensa más: mejor calidad, algo más lento.",
    },
    {
        "id": "xhigh",
        "etiqueta": "Muy alto",
        "descripcion": "Razonamiento extenso para tareas difíciles.",
    },
    {
        "id": "max",
        "etiqueta": "Máximo",
        "descripcion": "Máximo razonamiento. El más lento y costoso.",
    },
)


def _etiqueta_esfuerzo(nivel: str) -> str:
    """Etiqueta humana de un nivel de esfuerzo (cae a «Predeterminado»)."""
    for opcion in _ESFUERZO_OPCIONES:
        if opcion["id"] == nivel:
            return opcion["etiqueta"]
    return "Predeterminado"


async def obtener_esfuerzo(request: Request) -> Response:
    """GET: nivel de esfuerzo actual + catálogo de opciones para la UI."""
    return JSONResponse(
        {
            "esfuerzo": preferencias.obtener_esfuerzo(),
            "opciones": [dict(o) for o in _ESFUERZO_OPCIONES],
        }
    )


async def guardar_esfuerzo(request: Request) -> Response:
    """POST `{esfuerzo}`: guarda el nivel (atómico). Vacío => predeterminado del modelo."""
    datos = await leer_json(request)
    nivel = datos.get("esfuerzo", "")
    if not isinstance(nivel, str):
        return JSONResponse({"error": "El esfuerzo debe ser un texto."}, status_code=400)

    try:
        guardado = preferencias.guardar_esfuerzo(nivel)
    except ValueError:
        validos = ", ".join(preferencias.ESFUERZOS_VALIDOS)
        return JSONResponse(
            {"error": f"Esfuerzo inválido. Usa uno de: {validos} (o vacío para el predeterminado)."},
            status_code=400,
        )
    except OSError as e:
        return JSONResponse(
            {"error": f"No se pudo guardar el esfuerzo: {e}"}, status_code=400
        )

    return JSONResponse(
        {
            "esfuerzo": guardado,
            "mensaje": f"Esfuerzo de generación guardado: {_etiqueta_esfuerzo(guardado)}.",
        }
    )


RUTAS = [
    Route("/api/config", obtener_config, methods=["GET"]),
    Route("/api/config", guardar_config, methods=["POST"]),
    Route("/api/config/esfuerzo", obtener_esfuerzo, methods=["GET"]),
    Route("/api/config/esfuerzo", guardar_esfuerzo, methods=["POST"]),
]
