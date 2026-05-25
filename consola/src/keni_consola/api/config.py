"""API Configuracion: leer y cambiar la fuente de datos y el alcance (marcas).

Reutiliza la logica de `keni_metricas.config` (lectura) y `keni_metricas.asistente`
(merge no destructivo + escritura atomica 0600). NO edita esos modulos: solo
orquesta + serializa a JSON.

Las credenciales NUNCA se editan ni se muestran por la API: solo se reporta su
PRESENCIA/AUSENCIA por bloque (meta/youtube/x/tiktok).
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from keni_metricas import asistente
from keni_metricas.config import (
    FUENTES_VALIDAS,
    ConfigInvalida,
    cargar_config,
    construir_fuente,
    ruta_config,
)
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import marcas
from .._http_json import leer_json

# Bloques de credenciales que el sistema reconoce (mismo mapa que el asistente),
# en orden estable. Aqui solo informamos presencia/ausencia, nunca el valor.
_BLOQUES_CREDENCIALES: tuple[str, ...] = ("meta", "youtube", "x", "tiktok")


def _marcas_disponibles(cfg) -> list[tuple[str, str]]:  # noqa: ANN001 -- Config del paquete
    """Marcas elegibles para el alcance: las declaradas en el config + las de la
    fuente activa. Devuelve pares (id, nombre) sin duplicados, orden estable.
    """
    pares: list[tuple[str, str]] = []
    vistos: set[str] = set()

    for c in cfg.cuentas:
        if c.id not in vistos:
            vistos.add(c.id)
            pares.append((c.id, c.nombre))

    # Sin el alcance actual (marcas=[]) listamos TODAS las marcas de la fuente, asi
    # el usuario puede ampliar su alcance aunque ya lo tenga acotado.
    try:
        cfg_sin_alcance = dataclasses.replace(cfg, marcas=[])
        fuente = construir_fuente(cfg_sin_alcance)
        for c in fuente.cuentas():
            if c.id not in vistos:
                vistos.add(c.id)
                pares.append((c.id, c.nombre))
    except Exception:  # noqa: BLE001 -- sin fuente valida seguimos con lo del config
        pass

    return pares


def _presencia_credenciales(cfg) -> dict[str, bool]:  # noqa: ANN001
    """Por cada bloque conocido: True si trae un token real (no vacio ni placeholder).

    Nunca devuelve el valor; solo presencia/ausencia.
    """
    creds = cfg.credenciales if isinstance(cfg.credenciales, dict) else {}
    salida: dict[str, bool] = {}
    for bloque in _BLOQUES_CREDENCIALES:
        valores = creds.get(bloque) if isinstance(creds.get(bloque), dict) else {}
        campo = asistente.CAMPO_TOKEN.get(bloque)
        token = valores.get(campo) if campo else None
        salida[bloque] = bool(token) and token != asistente.PLACEHOLDER_TOKEN
    return salida


def _etiqueta_humana(marca_id: str, nombre: str) -> str:
    """Nombre legible (con acentos) de una marca; cae al nombre del config o al id.

    Las marcas del config/fuente vienen en forma `id_metricas` (guion_bajo): se
    resuelven por esa frontera, no por el id canonico.
    """
    marca = marcas.marca_por_id_metricas(marca_id)
    if marca is not None:
        return marca.etiqueta
    return nombre or marca_id


def _guardar_fuente_y_marcas(ruta: Path, fuente: str, marcas_ids: list[str]) -> None:
    """Escribe SOLO `fuente` y `marcas` preservando el resto del config (merge atomico)."""
    existente = asistente.leer_config_existente(ruta)
    nuevo: dict = {"fuente": fuente}
    if marcas_ids:
        nuevo["marcas"] = list(marcas_ids)
    fusionado = asistente.fusionar_config(existente, nuevo)
    if not marcas_ids:
        fusionado.pop("marcas", None)
    asistente.escribir_config_atomico(ruta, fusionado)


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #


async def obtener_config(request: Request) -> Response:
    try:
        cfg = cargar_config()
    except ConfigInvalida as e:
        return JSONResponse(
            {"error": f"No se pudo leer tu configuración: {e}"}, status_code=400
        )

    disponibles = _marcas_disponibles(cfg)
    return JSONResponse(
        {
            "fuente": cfg.fuente,
            "fuentes_validas": sorted(FUENTES_VALIDAS),
            "marcas": list(cfg.marcas),
            "marcas_disponibles": [
                {"id": mid, "nombre": _etiqueta_humana(mid, nombre)}
                for mid, nombre in disponibles
            ],
            "credenciales_presentes": _presencia_credenciales(cfg),
        }
    )


async def guardar_config(request: Request) -> Response:
    datos = await leer_json(request)

    fuente = datos.get("fuente")
    if not isinstance(fuente, str) or fuente not in FUENTES_VALIDAS:
        validas = ", ".join(sorted(FUENTES_VALIDAS))
        return JSONResponse(
            {"error": f"Fuente inválida. Usa una de: {validas}."}, status_code=400
        )

    marcas_crudas = datos.get("marcas", [])
    if not isinstance(marcas_crudas, list) or not all(isinstance(m, str) for m in marcas_crudas):
        return JSONResponse(
            {"error": "El alcance debe ser una lista de marcas."}, status_code=400
        )

    try:
        cfg = cargar_config()
    except ConfigInvalida as e:
        return JSONResponse(
            {"error": f"No se pudo leer tu configuración: {e}"}, status_code=400
        )

    ids_validos = [mid for mid, _ in _marcas_disponibles(cfg)]
    alcance_ids = asistente.normalizar_alcance(marcas_crudas, ids_validos=ids_validos)
    desconocidas = [m for m in marcas_crudas if m.strip() and m.strip() not in ids_validos]
    if desconocidas:
        etiquetas = ", ".join(marcas.etiqueta_por_id_metricas(m) for m in desconocidas)
        return JSONResponse(
            {"error": f"Marcas desconocidas: {etiquetas}."}, status_code=400
        )

    try:
        _guardar_fuente_y_marcas(ruta_config(), fuente, alcance_ids)
    except OSError as e:
        return JSONResponse(
            {"error": f"No se pudo guardar la configuración: {e}"}, status_code=400
        )

    alcance = (
        ", ".join(marcas.etiqueta_por_id_metricas(mid) for mid in alcance_ids)
        if alcance_ids
        else "todas las marcas"
    )
    legible = {"muestra": "Muestra", "real": "Real"}.get(fuente, fuente)
    return JSONResponse(
        {"mensaje": f"Configuración guardada. Fuente: {legible}. Alcance: {alcance}."}
    )


RUTAS = [
    Route("/api/config", obtener_config, methods=["GET"]),
    Route("/api/config", guardar_config, methods=["POST"]),
]
