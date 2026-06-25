"""Imports y helpers COMPARTIDOS por varios submódulos de `api/metricas/`.

Este módulo NO exporta `RUTAS` (su nombre va con `_`, así que el descubridor de
`api/__init__.py` ni lo escanea —vive dentro del subpaquete—). Reúne lo que más de
un submódulo de la API de métricas necesita: la fachada `servicio`, los puentes a
los módulos de la Consola (`marcas`, `permisos`, caches…), el logger y los helpers
transversales de rango/marca. Los submódulos importan de aquí EXPLÍCITAMENTE.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from keni_metricas import servicio
from keni_shared.metricas import engagement_pct
from starlette.requests import Request
from starlette.responses import Response

from ... import (
    marcas,
    metricas_cache,
    metricas_categoria,
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
    "metricas_categoria",
    "metricas_pieza",
    "permisos",
    "repos",
    # Logger y constante de rangos.
    "_log",
    "RANGOS_VALIDOS",
    "RANGOS_PRESET_UI",
    "REDES_VALIDAS",
    "FORMATOS_VALIDOS",
    # Helpers transversales.
    "_gate_marca_metricas",
    "_etiqueta_rango",
    "_nombre_marca_id",
    "_validar_rango",
    "_validar_red",
    "_validar_redes",
    "_conjunto_redes",
    "_validar_formatos",
    "_conjunto_formatos",
    "_formato_canonico",
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

# Presets ofrecidos en el desplegable (subconjunto de los validos: sin "7d"/"30d",
# identicos a "semana"/"mes"). Solo lo usa `opciones` para poblar el selector; la
# validacion de entrada sigue contra RANGOS_VALIDOS, asi "7d"/"30d" se aceptan aunque
# no se ofrezcan.
RANGOS_PRESET_UI = servicio.RANGOS_PRESET_UI


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
    normaliza a `mes:AAAA-MM`. Un rango basura cualquiera cae a 'mes' (compat con el
    comportamiento previo, sin romper la vista).
    """
    if rango in RANGOS_VALIDOS:
        return rango
    if rango.startswith(("mes:", "rango:")):
        return rango
    if len(rango) == 7 and rango[:4].isdigit() and rango[4] == "-" and rango[5:].isdigit():
        return f"mes:{rango}"
    return "mes"


# Redes (ids de plataforma) que el dashboard puede filtrar. Misma lista que la
# auditoría de cobertura y el filtro de top/peores: el universo de redes de analítica.
REDES_VALIDAS: frozenset[str] = frozenset(
    {"facebook", "instagram", "x", "tiktok", "youtube"}
)


def _validar_red(raw: str | None) -> str | None:
    """Valida el filtro `?red=`: None/'' = todas (sin filtro); id válido = esa red.

    Un valor NO vacío y desconocido lanza ValueError (→400, mismo estilo que
    `resolver_rango`): así un id mal escrito falla limpio en vez de devolver un
    agregado silencioso que el operador creería filtrado.
    """
    red = (raw or "").strip()
    if not red:
        return None
    if red not in REDES_VALIDAS:
        validas = ", ".join(sorted(REDES_VALIDAS))
        raise ValueError(f"Red desconocida {red!r}. Usa una de: {validas}.")
    return red


def _validar_redes(raw: str | None) -> tuple[str, ...]:
    """Valida el filtro `?red=` que puede traer VARIAS redes separadas por coma.

    None/'' = todas (sin filtro) → tupla vacía. Cada id se valida; uno desconocido lanza
    ValueError (→400), igual que `_validar_red`. Devuelve las redes ÚNICAS en orden de
    aparición. Así el dashboard combina redes a antojo (`?red=instagram,youtube`).
    """
    crudo = (raw or "").strip()
    if not crudo:
        return ()
    elegidas: list[str] = []
    for parte in crudo.split(","):
        red = parte.strip()
        if not red:
            continue
        if red not in REDES_VALIDAS:
            validas = ", ".join(sorted(REDES_VALIDAS))
            raise ValueError(f"Red desconocida {red!r}. Usa una de: {validas}.")
        if red not in elegidas:
            elegidas.append(red)
    return tuple(elegidas)


def _conjunto_redes(red: "str | Iterable[str] | None") -> set[str]:
    """Normaliza un argumento de filtro de red a un CONJUNTO. None/''/() = vacío (= todas).

    Acepta un único id (str), una colección de ids, o None, para que las funciones de
    filtro funcionen igual con una red o con varias sin cambiar sus llamadas existentes.
    """
    if red is None:
        return set()
    if isinstance(red, str):
        return {red} if red else set()
    return {r for r in red if r}


# Formatos (ids CANÓNICOS de pieza) que el dashboard puede filtrar. Fuente ÚNICA de
# verdad: la del backend de métricas (`servicio.FORMATOS_VALIDOS`), para no duplicar el
# contrato entre la API HTTP y el servicio que filtra las piezas.
FORMATOS_VALIDOS: frozenset[str] = servicio.FORMATOS_VALIDOS


def _formato_canonico(raw: str) -> str:
    """Normaliza el formato crudo de una pieza a su id canónico (delega en el servicio).

    Es el MISMO mapa que aplica el servicio al filtrar las piezas, para que validar el
    filtro y filtrar las piezas hablen exactamente el mismo idioma de formato.
    """
    return servicio.formato_canonico(raw)


def _validar_formatos(raw: str | None) -> tuple[str, ...]:
    """Valida el filtro `?formato=` que puede traer VARIOS formatos separados por coma.

    None/'' = todos (sin filtro) → tupla vacía. Cada id debe ser un formato canónico
    válido; uno desconocido lanza ValueError (→400), igual que `_validar_redes`. Devuelve
    los formatos ÚNICOS en orden de aparición (`?formato=reel,carrusel`).
    """
    crudo = (raw or "").strip()
    if not crudo:
        return ()
    elegidos: list[str] = []
    for parte in crudo.split(","):
        fmt = parte.strip()
        if not fmt:
            continue
        if fmt not in FORMATOS_VALIDOS:
            validos = ", ".join(sorted(FORMATOS_VALIDOS))
            raise ValueError(f"Formato desconocido {fmt!r}. Usa uno de: {validos}.")
        if fmt not in elegidos:
            elegidos.append(fmt)
    return tuple(elegidos)


def _conjunto_formatos(formato: "str | Iterable[str] | None") -> set[str]:
    """Normaliza un argumento de filtro de formato a un CONJUNTO. None/''/() = vacío.

    Acepta un único id (str), una colección de ids, o None, para que las funciones de
    filtro funcionen igual con uno o varios formatos sin cambiar sus llamadas.
    """
    if formato is None:
        return set()
    if isinstance(formato, str):
        return {formato} if formato else set()
    return {f for f in formato if f}


def _rango_opcional(raw: str | None) -> str | None:
    """Rango para /estado y /refrescar: preset o token válido, si no None (sin combo)."""
    if not raw:
        return None
    if raw in RANGOS_VALIDOS or raw.startswith(("mes:", "rango:")):
        return raw
    return None
