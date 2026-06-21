"""API de la TEXTO: documentos (prompts + linea editorial) + lanzar generacion.

CRUD del almacen unico de documentos markdown (`texto`) + el endpoint de LANZAR un
prompt sobre un target (contenido pegado / archivo / url / area de la Consola), que compone
el prompt (prompt + linea editorial adjunta + contexto) y ENCOLA un trabajo de `claude -p`
reutilizando la infra de generaciones (`dominio.prompts_lanzar`). El frontend sondea
`GET /api/generaciones/{id}` hasta el estado terminal.

La app descubre este modulo por su variable `RUTAS` (ver `api/__init__.py`); no se toca
`app.py`. Errores como JSON en espanol. `ColaLlenaError` se deja PROPAGAR: el manejador
central de `app.py` la traduce a 429.

ESTRUCTURA (refactor de pura reubicacion; CERO cambio de comportamiento). El modulo se
troceo en un paquete por areas; este `__init__.py` es la FACHADA que re-exporta la
superficie publica y ENSAMBLA `RUTAS` identico (paths/metodos/orden):
  - `docs`        : CRUD de documentos + papelera + linea editorial (editoriales/validacion/
                    marcas).
  - `pieza` : historial/version/revertir (git) + pieza inmutable + solicitudes.
  - `pipelines`   : atribución editorial + variables + la "maquina" + estrategia.
  - `lanzar`      : `lanzar` (JSON) y `lanzar-archivo` (multipart): disparo de generacion.
  - `_comun`      : helpers compartidos (`_doc_json`, `_MAX_TEXTO`).

ORDEN DE RUTAS: las estaticas (`/papelera`, `/editoriales`, `/validacion`, `/marcas`,
`/lanzar`, `/lanzar-archivo`, `/maquina`, `/estrategia`) van ANTES que la parametrica
`/{doc_id:path}` (que captura barras) para que Starlette las case primero.
"""

from __future__ import annotations

from starlette.routing import Route

from ._comun import _MAX_TEXTO, _doc_json
from .docs import (
    _facetas,
    borrar,
    crear,
    editoriales,
    guardar,
    listar,
    marcas_disponibles,
    obtener,
    papelera_listar,
    papelera_restaurar,
    validacion,
)
from .lanzar import (
    _EXTS_TEXTO,
    _MAX_SUBIDA,
    _RE_EXT,
    _TROZO,
    _adjuntos_lista,
    _bloque_de_target,
    _extension_segura,
    _guardar_subida,
    _redes_lista,
    lanzar,
    lanzar_archivo,
)
from .pipelines import (
    _ETAPA_PIPELINE,
    _MAQUINAS,
    _PILARES_ESTRATEGIA,
    _PIPELINE_EDITORIAL_POR_PROMPT,
    _doc_id_de_etapa,
    contexto_inyectado,
    estrategia,
    maquina,
    variables,
)
from .pieza import (
    _MSG_SOLO_ADMIN_PUBLICAR,
    _autor_nombre,
    _resolver_sha,
    _sha_a_publicar,
    _solicitud_json,
    descartar,
    historial,
    publicar,
    revertir,
    solicitar,
    solicitud_aprobar,
    solicitud_rechazar,
    solicitudes_listar,
    version,
)

__all__ = [
    # Helpers compartidos
    "_doc_json",
    "_MAX_TEXTO",
    # docs
    "listar",
    "crear",
    "obtener",
    "guardar",
    "borrar",
    "papelera_listar",
    "papelera_restaurar",
    "editoriales",
    "validacion",
    "marcas_disponibles",
    "_facetas",
    # pipelines
    "variables",
    "maquina",
    "estrategia",
    "contexto_inyectado",
    "_MAQUINAS",
    "_ETAPA_PIPELINE",
    "_PILARES_ESTRATEGIA",
    "_PIPELINE_EDITORIAL_POR_PROMPT",
    "_doc_id_de_etapa",
    # pieza
    "historial",
    "version",
    "revertir",
    "descartar",
    "publicar",
    "solicitar",
    "solicitudes_listar",
    "solicitud_aprobar",
    "solicitud_rechazar",
    "_MSG_SOLO_ADMIN_PUBLICAR",
    "_autor_nombre",
    "_resolver_sha",
    "_sha_a_publicar",
    "_solicitud_json",
    # lanzar
    "lanzar",
    "lanzar_archivo",
    "_adjuntos_lista",
    "_redes_lista",
    "_bloque_de_target",
    "_extension_segura",
    "_guardar_subida",
    "_MAX_SUBIDA",
    "_TROZO",
    "_EXTS_TEXTO",
    "_RE_EXT",
    "RUTAS",
]

# Rutas: estaticas y multi-segmento ANTES que la parametrica `/{doc_id:path}` (captura barras).
RUTAS = [
    Route("/api/prompts", listar, methods=["GET"]),
    Route("/api/prompts", crear, methods=["POST"]),
    Route("/api/prompts/papelera", papelera_listar, methods=["GET"]),
    Route("/api/prompts/papelera/{pid}/restaurar", papelera_restaurar, methods=["POST"]),
    Route("/api/prompts/editoriales", editoriales, methods=["GET"]),
    Route("/api/prompts/validacion", validacion, methods=["GET"]),
    Route("/api/prompts/marcas", marcas_disponibles, methods=["GET"]),
    Route("/api/prompts/lanzar", lanzar, methods=["POST"]),
    Route("/api/prompts/lanzar-archivo", lanzar_archivo, methods=["POST"]),
    # Publicación: catálogo de variables, flujo de la máquina (tres máquinas,
    # ADR 0011), estrategia de marca y solicitudes.
    Route("/api/prompts/variables", variables, methods=["GET"]),
    Route("/api/prompts/maquina", maquina, methods=["GET"]),
    Route("/api/prompts/estrategia", estrategia, methods=["GET"]),
    Route("/api/prompts/solicitudes", solicitudes_listar, methods=["GET"]),
    Route("/api/prompts/solicitudes/{sid}/aprobar", solicitud_aprobar, methods=["POST"]),
    Route("/api/prompts/solicitudes/{sid}/rechazar", solicitud_rechazar, methods=["POST"]),
    # Multi-segmento de versionado: el sufijo literal ancla la captura del `doc_id:path`.
    Route("/api/prompts/{doc_id:path}/contexto", contexto_inyectado, methods=["GET"]),
    Route("/api/prompts/{doc_id:path}/historial", historial, methods=["GET"]),
    Route("/api/prompts/{doc_id:path}/version/{sha}", version, methods=["GET"]),
    Route("/api/prompts/{doc_id:path}/revertir/{sha}", revertir, methods=["POST"]),
    Route("/api/prompts/{doc_id:path}/descartar", descartar, methods=["POST"]),
    Route("/api/prompts/{doc_id:path}/publicar", publicar, methods=["POST"]),
    Route("/api/prompts/{doc_id:path}/solicitar", solicitar, methods=["POST"]),
    Route("/api/prompts/{doc_id:path}", obtener, methods=["GET"]),
    Route("/api/prompts/{doc_id:path}", guardar, methods=["PUT"]),
    Route("/api/prompts/{doc_id:path}", borrar, methods=["DELETE"]),
]
