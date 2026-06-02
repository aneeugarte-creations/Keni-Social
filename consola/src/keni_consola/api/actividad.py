"""API ACTIVIDAD: vista UNIFICADA de la actividad de IA (generaciones + runs).

Reune los DOS registros donde vive la "verdad" de lo que la IA produce —las
GENERACIONES (`generaciones.py`: copy, rss, autogen, hashtags, imagen, verificacion,
qa-editorial, prompt) y los RUNS de agente (`agentes.py`)— en una sola lista de
items normalizados, con filtros, paginacion y agregados. La normalizacion/mezcla/
agregacion es DOMINIO PURO (`consola.actividad`); aqui solo se LEEN ambos orígenes
(via `generaciones.listar(...)` y el dominio `agentes`, NUNCA por HTTP) y se sirven.

Endpoints:
  - `GET /api/actividad?limite=&offset=&fuente=&tipo=`
      -> `{"items": [...], "total": <int>}`
  - `GET /api/actividad/agregados`
      -> `{"total": {...}, "por_tipo": [...], "por_dia": [...]}`

Solo LECTURA. Errores en espanol; sin tracebacks crudos.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import actividad, agentes, generaciones
from .._http_json import _entero_query

# Tope por defecto de items por pagina (alineado con el contrato del frontend).
_LIMITE_DEF = 50

# Fuentes y tipos validos para filtrar (un filtro vacio no filtra por ese eje). El `tipo`
# admite los tipos de generacion + "run" + "pipeline" (la generación de copy que lanza el
# pipeline de contenido: trabajo real `claude -p` CON tokens/coste/tiempo). Los MARCADORES
# de etapa (CI/CD/QA, `tipo='pipeline_etapa'`, SIN coste) NO se listan ni se muestran aquí:
# son para la pestaña Pipelines y se EXCLUYEN del feed (ver `_es_marcador_pipeline`), para no
# ensuciar Actividad con filas a 0.
_FUENTES = frozenset({"generacion", "run"})
_TIPOS = frozenset({*generaciones.TIPOS, "autogen", "run", "pipeline"})


def _es_marcador_pipeline(gen: dict) -> bool:
    """True si la generación es un MARCADOR de etapa del pipeline (CI/CD/QA) — fuera de Actividad.

    Los marcadores no son trabajo con coste (el trabajo real es la generación de copy
    `tipo='pipeline'`, que SÍ se muestra). Excluye el tipo propio `pipeline_etapa` y, por
    retrocompat, los marcadores VIEJOS (`tipo='pipeline'` con `etiqueta` de etapa, anteriores
    a separar el tipo).
    """
    tipo = gen.get("tipo")
    if tipo == "pipeline_etapa":
        return True
    if tipo == "pipeline":
        return (gen.get("etiqueta", "") or "").startswith(("CI · ", "CD · ", "QA · "))
    return False


def _filtro(valor: str | None, validos: frozenset[str]) -> str:
    """Normaliza un filtro de query: devuelve el valor si es valido, "" si no."""
    v = (valor or "").strip()
    return v if v in validos else ""


def _origenes() -> tuple[list, list]:
    """Lee TODAS las generaciones y TODOS los runs (sin recortar) para combinar/agregar.

    Las generaciones se piden con `limite=None` (conjunto completo; la paginacion la
    aplica el dominio sobre la mezcla). Los runs vienen del dominio `agentes`
    (`listar_runs_globales`) con sus metricas y su agente denormalizado.
    """
    gens = [g for g in generaciones.listar(limite=None) if not _es_marcador_pipeline(g)]
    runs = agentes.listar_runs_globales()
    return gens, runs


async def listar(request: Request) -> Response:
    """Actividad unificada (generaciones + runs), filtrada, ordenada y paginada.

    Query: `limite` (def 50), `offset` (def 0), `fuente` (""|generacion|run),
    `tipo` (""|copy|rss|autogen|hashtags|imagen|verificacion|qa-editorial|prompt|run).
    """
    qp = request.query_params
    limite = _entero_query(qp.get("limite"), minimo=1)
    offset = _entero_query(qp.get("offset"), minimo=0) or 0
    fuente = _filtro(qp.get("fuente"), _FUENTES)
    tipo = _filtro(qp.get("tipo"), _TIPOS)

    gens, runs = _origenes()
    items, total = actividad.combinar(
        gens, runs,
        fuente=fuente, tipo=tipo, offset=offset,
        limite=_LIMITE_DEF if limite is None else limite,
    )
    return JSONResponse({"items": items, "total": total})


async def agregados(request: Request) -> Response:
    """Agregados de la actividad: total + por_tipo (incluye 'run') + por_dia."""
    gens, runs = _origenes()
    return JSONResponse(actividad.agregados(gens, runs))


RUTAS = [
    Route("/api/actividad", listar, methods=["GET"]),
    Route("/api/actividad/agregados", agregados, methods=["GET"]),
]
