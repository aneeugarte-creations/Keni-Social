"""API Publicaciones: CRUD de posts a gestionar (titulo, marca, red, estado, fechas).

El SPA gestiona el ciclo de vida de cada pieza: nace como borrador (a mano o desde
una generacion por red de Skills), se edita, se aprueba, se programa y se publica.
Persistencia en SQLite (`consola.db`, via `consola.db`). Nada se publica de verdad
aqui: solo se administra el estado editorial.

SEGURIDAD / VALIDACION (no duplica logica; reusa las fuentes de verdad):
  - `marca` SOLO puede ser una marca del catalogo unico (`consola.marcas`), por
    su `id` canonico (slug-guion), el mismo `value` que usa la generacion de copy.
  - `red` SOLO puede ser una red canonica (`consola.redes`).
  - `estado` SOLO puede ser uno de `repos.ESTADOS_PUBLICACION`.
  - SQL parametrizado en `consola.db`; los errores salen como JSON en espanol, sin
    tracebacks crudos.

`marca_nombre` y `red_nombre` se resuelven EN SERVIDOR (la UI solo muestra nombres).
"""

from __future__ import annotations

from starlette.routing import Route

from ._comun import (
    _CAMPOS_CONTENIDO_FALTA,
    _CAMPOS_ESPEJO,
    _RESET_APROBACIONES,
    _inyectar_flags_falta,
    _limpiar_cadena,
    _pierde_aprobaciones,
    _publicacion_a_dict,
)
from .composicion import aplicar_plantilla, componer_slide, compuesta, integrar_foto
from .crud import (
    _ESTADO_NOMBRE,
    _MARCAS,
    _MARCAS_IDS,
    _TRANSICIONES_PUT,
    _feed_pagina_defecto,
    _ids_de_lote,
    _normalizar_fecha_programada,
    _parsear_bool_query,
    _validar_nueva,
    actualizar,
    borrar,
    borrar_lote,
    cadenas_lote,
    clonar,
    crear,
    crear_lote,
    detalle,
    duplicar,
    listar,
    opciones,
    programar_metricool,
)
from .espejo import _propagar_espejo
from .programacion import (
    _encolar_en_hueco_libre,
    calcular_hueco_para,
    categoria_de_pieza,
    encolar,
)

__all__ = [
    "RUTAS",
    # CRUD
    "opciones",
    "listar",
    "crear",
    "crear_lote",
    "detalle",
    "actualizar",
    "borrar",
    "borrar_lote",
    "cadenas_lote",
    "duplicar",
    "clonar",
    "programar_metricool",
    # Programación
    "encolar",
    "categoria_de_pieza",
    "calcular_hueco_para",
    "_encolar_en_hueco_libre",
    # Composición
    "integrar_foto",
    "aplicar_plantilla",
    "componer_slide",
    "compuesta",
    # Espejo
    "_propagar_espejo",
    # Helpers compartidos / consumidos por tests
    "_publicacion_a_dict",
    "_CAMPOS_ESPEJO",
    "_CAMPOS_CONTENIDO_FALTA",
    "_inyectar_flags_falta",
    "_RESET_APROBACIONES",
    "_pierde_aprobaciones",
    "_limpiar_cadena",
    "_ESTADO_NOMBRE",
    "_MARCAS",
    "_MARCAS_IDS",
    "_TRANSICIONES_PUT",
    "_normalizar_fecha_programada",
    "_validar_nueva",
    "_parsear_bool_query",
    "_feed_pagina_defecto",
    "_ids_de_lote",
]


# El orden importa: las rutas literales batch (`cadenas`, `borrar-lote`, `{id}/compuesta`) van
# ANTES de la genérica `/{publicacion_id}` para que no se interpreten como un id.
RUTAS = [
    Route("/api/publicaciones/opciones", opciones, methods=["GET"]),
    # Batch del feed: ANTES de "/{publicacion_id}" para que "cadenas" no matchee como id.
    Route("/api/publicaciones/cadenas", cadenas_lote, methods=["GET"]),
    Route("/api/publicaciones/borrar-lote", borrar_lote, methods=["POST"]),
    Route("/api/publicaciones/{publicacion_id}/compuesta", compuesta, methods=["GET"]),
    Route("/api/publicaciones", listar, methods=["GET"]),
    Route("/api/publicaciones", crear, methods=["POST"]),
    Route("/api/publicaciones/lote", crear_lote, methods=["POST"]),
    Route("/api/publicaciones/{publicacion_id}/encolar", encolar, methods=["POST"]),
    Route("/api/publicaciones/{publicacion_id}/duplicar", duplicar, methods=["POST"]),
    Route("/api/publicaciones/{publicacion_id}/clonar", clonar, methods=["POST"]),
    Route("/api/publicaciones/{publicacion_id}/metricool", programar_metricool, methods=["POST"]),
    Route("/api/publicaciones/{publicacion_id}/integrar-foto", integrar_foto, methods=["POST"]),
    Route("/api/publicaciones/{publicacion_id}/aplicar-plantilla", aplicar_plantilla, methods=["POST"]),
    Route("/api/publicaciones/{publicacion_id}/componer-slide", componer_slide, methods=["POST"]),
    Route("/api/publicaciones/{publicacion_id}", detalle, methods=["GET"]),
    Route("/api/publicaciones/{publicacion_id}", actualizar, methods=["PUT"]),
    Route("/api/publicaciones/{publicacion_id}", borrar, methods=["DELETE"]),
]
