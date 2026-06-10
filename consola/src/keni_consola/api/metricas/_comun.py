"""Imports y helpers COMPARTIDOS por varios submódulos de `api/metricas/`.

Este módulo NO exporta `RUTAS` (su nombre va con `_`, así que el descubridor de
`api/__init__.py` ni lo escanea —vive dentro del subpaquete—). Reúne lo que más de
un submódulo de la API de métricas necesita: la fachada `servicio`, los puentes a
los módulos de la Consola (`marcas`, `permisos`, caches…), el logger y los helpers
transversales de rango/marca. Los submódulos importan de aquí EXPLÍCITAMENTE.
"""

from __future__ import annotations

import logging

from keni_metricas import servicio
from keni_shared.metricas import engagement_pct
from starlette.requests import Request
from starlette.responses import Response

from ... import (
    marcas,
    metricas_cache,
    metricas_linea,
    metricas_pieza,
    permisos,
    repos,
)

__all__ = [
    # Re-exports (fachada + puentes a la Consola) que usan los submódulos.
    "servicio",
    "engagement_pct",
    "marcas",
    "metricas_cache",
    "metricas_linea",
    "metricas_pieza",
    "permisos",
    "repos",
    # Logger y constante de rangos.
    "_log",
    "RANGOS_VALIDOS",
    # Helpers transversales.
    "_gate_marca_metricas",
    "_etiqueta_rango",
    "_nombre_marca_id",
    "_validar_rango",
    "_rango_opcional",
]

_log = logging.getLogger("keni_consola.api.metricas")


def _gate_marca_metricas(
    request: Request, marca_metricas: str | None
) -> tuple[str | None, Response | None]:
    """Resuelve el FOCO POR DEFECTO de una peticion de metricas por marca. NUNCA bloquea.

    La marca NO acota lo que alguien puede ver: el equipo es multidisciplinar y consulta las
    metricas de CUALQUIER marca. Esto es solo un FOCO POR DEFECTO para reducir la mezcla de
    contexto cuando no se pide marca. Devuelve `(marca_efectiva, None)` (el `rechazo` siempre
    es None; se conserva la tupla por compatibilidad con los call sites). La frontera de
    metricas habla en `id_metricas` (guion_bajo); `marcas_preferentes` da ids CANONICOS.

      - Con marca EXPLICITA: se respeta tal cual (cualquier marca), sin bloqueo.
      - SIN marca y sesion con UNA marca preferente: se enfoca en la suya (la fachada acepta
        UNA sola marca). Sobreescribible pasando `?marca=`.
      - SIN marca y sesion con VARIAS o sin preferencia (admin/token): None = "todas".
    """
    if marca_metricas:
        return marca_metricas, None
    preferentes = permisos.marcas_preferentes(request)
    if preferentes is not None and len(preferentes) == 1:
        canonico = next(iter(preferentes))
        return marcas.id_metricas_de(canonico), None
    return None, None  # varias preferentes o sin preferencia: todas


# Rangos validos: contrato de la fachada (no se importa el schema directamente).
RANGOS_VALIDOS = servicio.RANGOS_VALIDOS


# Etiqueta legible de un rango (preset o token mes:/rango:). Delega en la fachada para
# que presets y tokens (mes:AAAA-MM, rango:AAAA-MM-DD_AAAA-MM-DD) tengan una sola fuente.
def _etiqueta_rango(rango: str) -> str:
    return servicio.etiqueta_rango(rango)


def _nombre_marca_id(cuenta_id: str, nombres: dict[str, str]) -> str:
    """Nombre legible: prioriza el catalogo unico de marcas, cae al nombre de la
    fuente de datos y luego al propio id.

    `cuenta_id` viene de la fuente de metricas, asi que esta en forma `id_metricas`
    (guion_bajo): se resuelve por esa frontera, no por el id canonico.
    """
    etiqueta = marcas.etiqueta_por_id_metricas(cuenta_id)
    if etiqueta != cuenta_id:
        return etiqueta
    return nombres.get(cuenta_id) or cuenta_id


def _validar_rango(rango: str) -> str:
    """Acepta presets y tokens de fecha; lo demás cae a 'mes'.

    Los tokens (`mes:AAAA-MM`, `rango:AAAA-MM-DD_AAAA-MM-DD`) pasan tal cual: la fachada
    valida su formato y lanza ValueError (→400) si está mal. Un `AAAA-MM` desnudo se
    normaliza a `mes:AAAA-MM` — antes caía al fallback y "mayo 2026" devolvía en silencio
    los últimos 30 días (números de otro periodo, peor que un error). Un rango basura
    cualquiera cae a 'mes' (compat con el comportamiento previo, sin romper la vista).
    """
    if rango in RANGOS_VALIDOS:
        return rango
    if rango.startswith(("mes:", "rango:")):
        return rango
    if len(rango) == 7 and rango[:4].isdigit() and rango[4] == "-" and rango[5:].isdigit():
        return f"mes:{rango}"
    return "mes"


def _rango_opcional(raw: str | None) -> str | None:
    """Rango para /estado y /refrescar: preset o token válido, si no None (sin combo)."""
    if not raw:
        return None
    if raw in RANGOS_VALIDOS or raw.startswith(("mes:", "rango:")):
        return raw
    return None
