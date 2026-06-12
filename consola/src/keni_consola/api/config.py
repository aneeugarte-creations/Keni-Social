"""API Configuracion: leer y cambiar la fuente de datos y el alcance (marcas).

Consume la fachada estable `keni_metricas.servicio`: lee el estado del config
(fuente, alcance, marcas elegibles, presencia de credenciales) y escribe SOLO
`fuente` + `marcas` (la fachada hace el merge no destructivo + escritura atomica).
Ya no importa internals (`config`/`asistente`).

Las credenciales NUNCA se editan ni se muestran por la API: solo se reporta su
PRESENCIA/AUSENCIA por bloque (meta/youtube/x/tiktok). La ESCRITURA de tokens vive
en `api/conexiones.py`, no aqui.

DEPRECADO(consolidación): GET/POST /api/config están muertos (ninguna página los
consume) y GET/POST /api/config/esfuerzo son un SHIM sobre el ajuste `KENI_ESFUERZO`
del catálogo (`ajustes_catalogo.py`). Todo este módulo se elimina en fase 4 (el front
migra a /api/ajustes en fase 3).
"""

from __future__ import annotations

from keni_metricas import servicio
from keni_metricas.servicio import ConfigInvalida
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


# Fuentes elegibles DESDE LA APP: solo la real de pago. El paquete de métricas conoce
# más ("muestra" para tests, "real" como fallback histórico), pero la Consola no las
# ofrece: nada sintético ni de demostración de cara al equipo.
_FUENTES_APP: tuple[str, ...] = ("metricool",)

# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #


# DEPRECADO(consolidación): GET /api/config no lo consume ninguna página del front (la
# fuente/alcance se gestionan en Conexiones); se elimina en fase 4 junto a su POST.
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
            "fuentes_validas": list(_FUENTES_APP),
            "marcas": estado["marcas"],
            "marcas_disponibles": [
                {"id": mid, "nombre": _etiqueta_humana(mid, nombre)}
                for mid, nombre in estado["marcas_disponibles"]
            ],
            "credenciales_presentes": estado["credenciales_presentes"],
        }
    )


# DEPRECADO(consolidación): POST /api/config no lo consume ninguna página del front; se
# elimina en fase 4 junto a su GET.
async def guardar_config(request: Request) -> Response:
    datos = await leer_json(request)

    # Desde la Consola SOLO se acepta `metricool`: `muestra` (datos sintéticos) y `real`
    # (adaptadores por plataforma, fallback histórico) existen como modos técnicos del
    # paquete de métricas (tests / opt-in manual en el config), pero la app no debe poder
    # apuntarse a cifras inventadas ni a una fuente que desfasa el tablero.
    fuente = datos.get("fuente")
    if not isinstance(fuente, str) or fuente not in _FUENTES_APP:
        validas = ", ".join(_FUENTES_APP)
        return JSONResponse(
            {"error": f"Fuente inválida. Usa una de: {validas}."}, status_code=400
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
    legible = {"metricool": "Metricool"}.get(fuente, fuente)
    return JSONResponse(
        {"mensaje": f"Configuración guardada. Fuente: {legible}. Alcance: {alcance}."}
    )


# --------------------------------------------------------------------------- #
# Esfuerzo de generacion (claude --effort) — SHIM DEPRECADO sobre el catálogo  #
# --------------------------------------------------------------------------- #
#
# DEPRECADO(consolidación): el esfuerzo es ya un ajuste del catálogo (`KENI_ESFUERZO`,
# select del grupo `tuning`; GET/POST /api/ajustes). Estos dos endpoints quedan como SHIM
# de retrocompatibilidad para el front actual (SeccionEsfuerzo) hasta la Fase 3; se
# eliminan en fase 4. Leen/escriben el ajuste nuevo vía `preferencias` (que además cae al
# TOML legado en lectura si nadie escribió aún el ajuste — migración suave documentada allí).

# Descripciones largas de cada nivel (solo las usa este shim; las etiquetas viven en
# `preferencias.ESFUERZO_ETIQUETAS`, compartidas con el catálogo de ajustes).
_ESFUERZO_DESCRIPCIONES: dict[str, str] = {
    "": "Usa el esfuerzo por defecto del modelo. Equilibrado y recomendado.",
    "low": "Responde antes y piensa menos. Para borradores rápidos.",
    "medium": "Equilibrio entre rapidez y calidad.",
    "high": "Piensa más: mejor calidad, algo más lento.",
    "xhigh": "Razonamiento extenso para tareas difíciles.",
    "max": "Máximo razonamiento. El más lento y costoso.",
}


def _opciones_esfuerzo() -> list[dict[str, str]]:
    """Opciones que pinta la UI vieja: id/etiqueta (fuente única) + descripción del shim."""
    return [
        {
            "id": nivel,
            "etiqueta": preferencias.ESFUERZO_ETIQUETAS[nivel],
            "descripcion": _ESFUERZO_DESCRIPCIONES[nivel],
        }
        for nivel in ("", *preferencias.ESFUERZOS_VALIDOS)
    ]


def _etiqueta_esfuerzo(nivel: str) -> str:
    """Etiqueta humana de un nivel de esfuerzo (cae a «Predeterminado»)."""
    return preferencias.ESFUERZO_ETIQUETAS.get(nivel, "Predeterminado")


async def obtener_esfuerzo(request: Request) -> Response:
    """GET: nivel de esfuerzo actual + catálogo de opciones para la UI.

    SHIM deprecado: lee el ajuste `KENI_ESFUERZO` del catálogo (con fallback al TOML
    legado, ver `preferencias.obtener_esfuerzo`). Mismo contrato de respuesta de siempre.
    """
    return JSONResponse(
        {
            "esfuerzo": preferencias.obtener_esfuerzo(),
            "opciones": _opciones_esfuerzo(),
        }
    )


async def guardar_esfuerzo(request: Request) -> Response:
    """POST `{esfuerzo}`: guarda el nivel. Vacío => predeterminado del modelo.

    SHIM deprecado: escribe el ajuste `KENI_ESFUERZO` en el store de ajustes (la única
    fuente de verdad nueva) vía `preferencias.guardar_esfuerzo`, que además retira el
    valor del almacén viejo (migración definitiva). Mismo contrato de respuesta.
    """
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
