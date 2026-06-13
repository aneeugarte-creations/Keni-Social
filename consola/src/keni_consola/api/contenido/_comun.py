"""Imports y helpers COMPARTIDOS por varios submódulos de `api/contenido/`.

Este módulo NO exporta `RUTAS` (su nombre va con `_`, así que el descubridor de
`api/__init__.py` ni lo escanea —vive dentro del subpaquete—). Reúne lo que más de
un handler del tablero necesita: los puentes a los módulos de la Consola
(`marcas`, `redes`, `repos`, `permisos`…), las constantes de límites/estados, el
logger y los helpers transversales de red/serialización/validación de marca y
responsable. Los submódulos importan de aquí EXPLÍCITAMENTE.
"""

from __future__ import annotations

import logging

from starlette.requests import Request

from ... import (
    auth,
    auto_responsable,
    autogen_copy,
    config,
    generaciones,
    importador_calendario,
    marcas,
    media,
    metricas_pieza,
    permisos,
    redes,
    repos,
    rutas,
    transcripcion,
)
from ..._http_json import leer_json
from ...dominio import asistente, estudio_imagen, eventos, jobspec, placeholders
from ...estados import (
    CLASES_CONTENIDO,
    ESTADOS_CONTENIDO,
    ESTADOS_CONTENIDO_PLATAFORMA,
    FLUJOS_CONTENIDO,
    ORIGEN_EQUIPO,
    PRIORIDADES_CONTENIDO,
    TIPOS_CONTENIDO,
)
from ...seguridad import autor_de_peticion
from ...tiempo import hoy_utc

__all__ = [
    # Puentes a módulos de la Consola que usan los submódulos.
    "auth",
    "auto_responsable",
    "autogen_copy",
    "config",
    "generaciones",
    "importador_calendario",
    "marcas",
    "media",
    "metricas_pieza",
    "permisos",
    "redes",
    "repos",
    "rutas",
    "transcripcion",
    "leer_json",
    "asistente",
    "estudio_imagen",
    "eventos",
    "jobspec",
    "placeholders",
    "autor_de_peticion",
    # Constantes de estados/clases.
    "CLASES_CONTENIDO",
    "ESTADOS_CONTENIDO",
    "ESTADOS_CONTENIDO_PLATAFORMA",
    "FLUJOS_CONTENIDO",
    "ORIGEN_EQUIPO",
    "PRIORIDADES_CONTENIDO",
    "TIPOS_CONTENIDO",
    # Logger y constantes locales.
    "_log",
    "_RED_WEB",
    "_ESTADOS_CERRADOS",
    "_MAX_TITULO",
    "_MAX_TEXTO",
    # Helpers transversales.
    "_orden_red",
    "_red_valida",
    "_red_nombre",
    "_usuarios_asignables",
    "_resolver_responsable",
    "_plataforma_a_dict",
    "_contenido_a_dict",
    "_validar_marca",
    "_enfocar_items_por_marca",
]

_log = logging.getLogger("keni_consola.api.contenido")

# Canal extra del tablero que NO es una red social del catalogo (no entra en Metricool):
# "web" cubre la nota en el sitio. Se admite como `red` de una fila por plataforma.
_RED_WEB = "web"

# Estados terminales para los que un deadline vencido ya no es relevante.
_ESTADOS_CERRADOS = ("publicado", "hecha")

_MAX_TITULO = 300
_MAX_TEXTO = 8000


def _orden_red(red: str) -> int:
    """Indice de orden canonico de una red (las del catalogo primero, "web"/otros al final)."""
    ids = redes.ids()
    return ids.index(red) if red in ids else len(ids)


def _red_valida(red: str) -> bool:
    return redes.es_red(red) or red == _RED_WEB


def _red_nombre(red: str) -> str:
    return "Web" if red == _RED_WEB else redes.nombre_por_id(red)


def _usuarios_asignables(marca: str | None = None) -> list[dict[str, str]]:
    """Usuarios candidatos a RESPONSABLE: los de cobertura, ACOTADOS a la `marca` activa
    (cada marca tiene SU equipo; sin marca = todos, p.ej. la vista «Todas» del admin).

    Misma regla que el tablero de tareas: un contenido lo asume quien hace coberturas.
    """
    return [
        {"id": u["id"], "usuario": u["usuario"]}
        for u in auth.listar_usuarios()
        if u.get("cobertura") and (not marca or marca in (u.get("marcas") or []))
    ]


def _resolver_responsable(
    responsable_id: object,
) -> tuple[dict[str, str] | None, bool]:
    """Resuelve un `responsable_id` del cliente a `{"id","usuario"}`. Ver api/tareas."""
    if responsable_id in (None, ""):
        return None, True
    if not isinstance(responsable_id, str):
        return None, False
    usuario = auth.obtener_usuario_por_id(responsable_id)
    if usuario is None:
        return None, False
    return {"id": usuario["id"], "usuario": usuario["usuario"]}, True


def _plataforma_a_dict(plat: dict) -> dict:
    """Serializa una fila por plataforma anadiendo el nombre legible de la red."""
    return {**plat, "red_nombre": _red_nombre(plat.get("red", ""))}


def _contenido_a_dict(
    item: dict, plataformas: list[dict], etiquetas: list[str] | None = None
) -> dict:
    """Serializa un item del tablero con sus plataformas (ordenadas), etiquetas y `vencido`."""
    hoy = hoy_utc().isoformat()
    entrega = item.get("fecha_entrega") or ""
    vencido = bool(
        entrega and entrega < hoy and item.get("estado") not in _ESTADOS_CERRADOS
    )
    plats = sorted(plataformas, key=lambda p: (_orden_red(p.get("red", "")), p.get("creado", "")))
    return {
        **item,
        "marca_nombre": marcas.etiqueta_de(item["marca"]) if item.get("marca") else "",
        "vencido": vencido,
        "plataformas": [_plataforma_a_dict(p) for p in plats],
        "etiquetas": list(etiquetas or []),
    }


def _validar_marca(marca: object) -> tuple[str | None, str | None]:
    if marca in (None, ""):
        return "", None
    if not isinstance(marca, str) or not marcas.es_marca(marca):
        return None, "Marca no permitida."
    return marca, None


def _enfocar_items_por_marca(
    request: Request, items: list[dict], marca_explicita: str | None
) -> list[dict]:
    """Enfoca un listado de contenidos en las marcas preferentes de la sesion (FOCO POR DEFECTO).

    NO es una restriccion: solo reduce la mezcla de contexto cuando NO se pide marca explicita.
    Si se pide una marca (cualquiera, de cualquier marca), se respeta tal cual (foco
    sobreescrito). Sin preferencia (admin/token/sin marcas asignadas) devuelve la lista intacta.
    Las filas sin marca se conservan. Pasar una `marca` explicita siempre puede ver otra marca.
    """
    if marca_explicita:
        return items
    preferentes = permisos.marcas_preferentes(request)
    if preferentes is None:
        return items
    return [it for it in items if not it.get("marca") or it.get("marca") in preferentes]
