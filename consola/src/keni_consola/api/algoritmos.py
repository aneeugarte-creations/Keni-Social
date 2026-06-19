"""API Algoritmos: inteligencia de plataforma (cambios de algoritmo + tendencias por red).

Superficie de SOLO LECTURA + curacion ligera. Lista las noticias ya ingeridas y
clasificadas (de los blogs oficiales y agregadores), permite refrescarlas, gestionar las
fuentes y PROPONER una actualizacion a la ficha editorial de cada plataforma (sin
escribirla: la decide el equipo). El panel reusa `listar_noticias_algoritmo` para destacar
las mas importantes.

  - `GET  /api/algoritmos`                 -> noticias + fuentes + huecos + vocabulario.
  - `POST /api/algoritmos/refrescar`       -> ingiere los feeds (todas o `{fuente}`).
  - `POST /api/algoritmos/inicializar`         -> crea las fuentes recomendadas que falten.
  - `POST /api/algoritmos/fuentes`         -> alta de fuente `{nombre,url,plataforma,tipo}`.
  - `PUT  /api/algoritmos/fuentes/{id}`    -> edicion parcial.
  - `DELETE /api/algoritmos/fuentes/{id}`  -> baja (borra tambien sus noticias).
  - `POST /api/algoritmos/{id}/texto` -> marca aplicada + devuelve el borrador de ficha.
  - `POST /api/algoritmos/{id}/archivar`   -> archiva/desarchiva una noticia.

SEGURIDAD: la URL de la fuente pasa por el MISMO guard SSRF que el RSS (`rss.validar_url`).
`plataforma`/`tipo` se validan contra el vocabulario controlado. SQL parametrizado en `db`;
errores en español, sin tracebacks.
"""

from __future__ import annotations

from typing import Any

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import algoritmos, repos
from .._http_json import leer_json
from . import rss

# Cuantas noticias devolver por defecto en el listado de la pagina (las mas importantes).
_LIMITE_DEFECTO = 80


def _flag(request: Request, nombre: str) -> bool:
    """Lee un query param booleano (`1`/`true`/`si`/`yes` => True; ausente/otro => False)."""
    return (request.query_params.get(nombre) or "").strip().lower() in ("1", "true", "si", "yes")


def _fuente_a_dict(fuente: dict[str, Any]) -> dict[str, Any]:
    """Serializa una fuente resolviendo las etiquetas humanas de plataforma/tipo."""
    return {
        **fuente,
        "plataforma_nombre": algoritmos.PLATAFORMAS.get(fuente.get("plataforma", "general"), ""),
        "tipo_nombre": algoritmos.TIPOS.get(fuente.get("tipo", "agregador"), ""),
    }


def _noticia_a_dict(noticia: dict[str, Any]) -> dict[str, Any]:
    """Serializa una noticia resolviendo la etiqueta humana de la plataforma."""
    return {
        **noticia,
        "plataforma_nombre": algoritmos.PLATAFORMAS.get(noticia.get("plataforma", "general"), ""),
    }


def _vocabulario() -> dict[str, Any]:
    """Listas de plataformas/tipos para los selectores de la UI (orden de inserción)."""
    return {
        "plataformas": [{"id": k, "nombre": v} for k, v in algoritmos.PLATAFORMAS.items()],
        "tipos": [{"id": k, "nombre": v} for k, v in algoritmos.TIPOS.items()],
        "niveles": list(algoritmos.NIVELES),
    }


async def listar(request: Request) -> Response:
    """GET /api/algoritmos: noticias filtrables + fuentes + huecos + vocabulario.

    Filtros (query): `plataforma`, `nivel`, `solo_cambios=1`, `incluir_archivadas=1`,
    `limite`. Las noticias salen ordenadas por importancia (luego fecha).
    """
    plataforma = request.query_params.get("plataforma") or None
    if plataforma is not None and not algoritmos.es_plataforma(plataforma):
        return JSONResponse({"error": "Plataforma no permitida."}, status_code=400)
    nivel = request.query_params.get("nivel") or None
    if nivel is not None and nivel not in algoritmos.NIVELES:
        return JSONResponse({"error": "Nivel no permitido."}, status_code=400)
    limite_crudo = request.query_params.get("limite")
    try:
        limite = int(limite_crudo) if limite_crudo else _LIMITE_DEFECTO
    except ValueError:
        limite = _LIMITE_DEFECTO
    limite = max(1, min(limite, 500))

    return JSONResponse(
        await run_in_threadpool(
            _listar,
            plataforma,
            nivel,
            _flag(request, "solo_cambios"),
            _flag(request, "incluir_archivadas"),
            limite,
        )
    )


def _listar(
    plataforma: str | None,
    nivel: str | None,
    solo_cambios: bool,
    incluir_archivadas: bool,
    limite: int,
) -> dict:
    noticias = repos.listar_noticias_algoritmo(
        plataforma=plataforma,
        nivel=nivel,
        solo_cambios=solo_cambios,
        incluir_archivadas=incluir_archivadas,
        limite=limite,
    )
    fuentes = repos.listar_fuentes_algoritmo()
    return {
        "noticias": [_noticia_a_dict(n) for n in noticias],
        "fuentes": [_fuente_a_dict(f) for f in fuentes],
        "pendientes": algoritmos.fuentes_pendientes(),
        **_vocabulario(),
    }


async def refrescar(request: Request) -> Response:
    """POST /api/algoritmos/refrescar: ingiere los feeds. Cuerpo `{fuente?}` opcional.

    Sin `fuente`, refresca TODAS las activas. Degradacion honesta: cada fuente que falla
    se anota con su error y no rompe las demas. Devuelve el resumen de la ingesta.
    """
    datos = await leer_json(request)
    solo = datos.get("fuente")
    solo = solo.strip() if isinstance(solo, str) and solo.strip() else None
    status, cuerpo = await run_in_threadpool(_refrescar, solo)
    return JSONResponse(cuerpo, status_code=status)


def _refrescar(solo: str | None) -> tuple[int, dict]:
    if solo and repos.obtener_fuente_algoritmo(solo) is None:
        return 404, {"error": "Esa fuente ya no existe."}
    resumen = algoritmos.refrescar(solo_fuente=solo)
    return 200, {"resumen": resumen}


def _inicializar() -> dict:
    creadas = algoritmos.inicializar()
    return {"creadas": [_fuente_a_dict(f) for f in creadas], "total": len(creadas)}


async def inicializar(request: Request) -> Response:
    """POST /api/algoritmos/inicializar: crea las fuentes recomendadas que falten (idempotente)."""
    return JSONResponse(await run_in_threadpool(_inicializar))


def _validar_plataforma(valor: Any) -> tuple[str | None, str | None]:
    if valor is None or valor == "":
        return "general", None
    if not algoritmos.es_plataforma(valor):
        return None, "Plataforma no permitida."
    return valor, None


def _validar_tipo(valor: Any) -> tuple[str | None, str | None]:
    if valor is None or valor == "":
        return "agregador", None
    if not algoritmos.es_tipo(valor):
        return None, "Tipo de fuente no permitido."
    return valor, None


async def crear_fuente(request: Request) -> Response:
    """POST /api/algoritmos/fuentes: alta `{nombre, url, plataforma?, tipo?}` -> `{fuente}`.

    Valida URL + guard SSRF (mismo que el RSS) y el vocabulario de plataforma/tipo.
    """
    datos = await leer_json(request)
    nombre = datos.get("nombre")
    if not isinstance(nombre, str) or not nombre.strip():
        return JSONResponse({"error": "El nombre de la fuente es obligatorio."}, status_code=400)
    url, error = rss.validar_url(datos.get("url"))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)
    plataforma, error = _validar_plataforma(datos.get("plataforma"))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)
    tipo, error = _validar_tipo(datos.get("tipo"))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)

    fuente = await run_in_threadpool(
        repos.crear_fuente_algoritmo, nombre.strip(), url, plataforma=plataforma, tipo=tipo
    )
    return JSONResponse({"fuente": _fuente_a_dict(fuente)})


def _actualizar_fuente(fuente_id: str, datos: dict) -> tuple[int, dict]:
    if repos.obtener_fuente_algoritmo(fuente_id) is None:
        return 404, {"error": "Esa fuente ya no existe."}
    campos: dict[str, Any] = {}
    if "nombre" in datos:
        nombre = datos.get("nombre")
        if not isinstance(nombre, str) or not nombre.strip():
            return 400, {"error": "El nombre de la fuente es obligatorio."}
        campos["nombre"] = nombre.strip()
    if "url" in datos:
        url, error = rss.validar_url(datos.get("url"))
        if error is not None:
            return 400, {"error": error}
        campos["url"] = url
    if "plataforma" in datos:
        plataforma, error = _validar_plataforma(datos.get("plataforma"))
        if error is not None:
            return 400, {"error": error}
        campos["plataforma"] = plataforma
    if "tipo" in datos:
        tipo, error = _validar_tipo(datos.get("tipo"))
        if error is not None:
            return 400, {"error": error}
        campos["tipo"] = tipo
    if "activo" in datos:
        campos["activo"] = bool(datos.get("activo"))

    fuente = repos.actualizar_fuente_algoritmo(fuente_id, campos)
    if fuente is None:
        return 404, {"error": "Esa fuente ya no existe."}
    return 200, {"fuente": _fuente_a_dict(fuente)}


async def actualizar_fuente(request: Request) -> Response:
    """PUT /api/algoritmos/fuentes/{id}: edicion parcial `{nombre?,url?,plataforma?,tipo?,activo?}`."""
    fuente_id = request.path_params["fuente_id"]
    datos = await leer_json(request)
    status, cuerpo = await run_in_threadpool(_actualizar_fuente, fuente_id, datos)
    return JSONResponse(cuerpo, status_code=status)


def _borrar_fuente(fuente_id: str) -> tuple[int, dict]:
    if not repos.borrar_fuente_algoritmo(fuente_id):
        return 404, {"error": "Esa fuente ya no existe."}
    return 200, {"mensaje": "Fuente borrada."}


async def borrar_fuente(request: Request) -> Response:
    """DELETE /api/algoritmos/fuentes/{id}: baja de la fuente y sus noticias."""
    fuente_id = request.path_params["fuente_id"]
    status, cuerpo = await run_in_threadpool(_borrar_fuente, fuente_id)
    return JSONResponse(cuerpo, status_code=status)


async def a_texto(request: Request) -> Response:
    """POST /api/algoritmos/{id}/texto: marca aplicada + devuelve el borrador de ficha.

    NO escribe la ficha editorial (verdad curada por humanos): devuelve un bloque markdown
    listo para pegar/confirmar en la Texto y marca la noticia como aplicada para no
    re-proponerla. Devuelve `{noticia, propuesta, plataforma}`.
    """
    noticia_id = request.path_params["noticia_id"]
    status, cuerpo = await run_in_threadpool(_a_texto, noticia_id)
    return JSONResponse(cuerpo, status_code=status)


def _a_texto(noticia_id: str) -> tuple[int, dict]:
    noticia = repos.obtener_noticia_algoritmo(noticia_id)
    if noticia is None:
        return 404, {"error": "Esa noticia ya no existe."}
    propuesta = algoritmos.texto_propuesta_ficha(noticia)
    actualizada = repos.marcar_noticia_algoritmo(noticia_id, aplicada=True)
    return 200, {
        "noticia": _noticia_a_dict(actualizada or noticia),
        "propuesta": propuesta,
        "plataforma": noticia.get("plataforma", "general"),
    }


def _archivar(noticia_id: str, archivada: bool) -> tuple[int, dict]:
    if repos.obtener_noticia_algoritmo(noticia_id) is None:
        return 404, {"error": "Esa noticia ya no existe."}
    noticia = repos.marcar_noticia_algoritmo(noticia_id, archivada=archivada)
    return 200, {"noticia": _noticia_a_dict(noticia) if noticia else None}


async def archivar(request: Request) -> Response:
    """POST /api/algoritmos/{id}/archivar: archiva/desarchiva `{archivada?: true}`."""
    noticia_id = request.path_params["noticia_id"]
    datos = await leer_json(request)
    archivada = datos.get("archivada", True)
    status, cuerpo = await run_in_threadpool(_archivar, noticia_id, bool(archivada))
    return JSONResponse(cuerpo, status_code=status)


RUTAS = [
    Route("/api/algoritmos", listar, methods=["GET"]),
    Route("/api/algoritmos/refrescar", refrescar, methods=["POST"]),
    Route("/api/algoritmos/inicializar", inicializar, methods=["POST"]),
    Route("/api/algoritmos/fuentes", crear_fuente, methods=["POST"]),
    Route("/api/algoritmos/fuentes/{fuente_id}", actualizar_fuente, methods=["PUT"]),
    Route("/api/algoritmos/fuentes/{fuente_id}", borrar_fuente, methods=["DELETE"]),
    Route("/api/algoritmos/{noticia_id}/texto", a_texto, methods=["POST"]),
    Route("/api/algoritmos/{noticia_id}/archivar", archivar, methods=["POST"]),
]
