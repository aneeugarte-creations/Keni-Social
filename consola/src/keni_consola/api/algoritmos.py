"""API Algoritmos: inteligencia de plataforma (cambios de algoritmo + tendencias por red).

Superficie de SOLO LECTURA + curacion ligera. Lista las noticias ya ingeridas y
clasificadas (de los blogs oficiales y agregadores), permite refrescarlas, gestionar las
fuentes y PROPONER una actualizacion a la ficha editorial de cada plataforma (sin
escribirla: la decide el equipo). El panel reusa `listar_noticias_algoritmo` para destacar
las mas importantes.

  - `GET  /api/algoritmos`                 -> noticias + fuentes + huecos + vocabulario.
  - `POST /api/algoritmos/refrescar`       -> ingiere los feeds (todas o `{fuente}`).
  - `POST /api/algoritmos/sembrar`         -> crea las fuentes recomendadas que falten.
  - `POST /api/algoritmos/fuentes`         -> alta de fuente `{nombre,url,plataforma,tipo}`.
  - `PUT  /api/algoritmos/fuentes/{id}`    -> edicion parcial.
  - `DELETE /api/algoritmos/fuentes/{id}`  -> baja (borra tambien sus noticias).
  - `POST /api/algoritmos/{id}/texto` -> marca aplicada + devuelve el borrador de ficha.
  - `POST /api/algoritmos/{id}/archivar`   -> archiva/desarchiva una noticia.
  - `GET  /api/algoritmos/sugerencias`     -> sugerencias editoriales del digest + nº nuevas.
  - `POST /api/algoritmos/sugerencias/generar`          -> lanza el digest AHORA (background).
  - `POST /api/algoritmos/sugerencias/{id}/aplicar`     -> aplica a la ficha + marca aplicada.
  - `POST /api/algoritmos/sugerencias/{id}/descartar`   -> descarta la sugerencia.

SEGURIDAD: la URL de la fuente pasa por el MISMO guard SSRF que el RSS (`rss.validar_url`).
`plataforma`/`tipo` se validan contra el vocabulario controlado. SQL parametrizado en `db`;
errores en español, sin tracebacks.
"""

from __future__ import annotations

import threading
from datetime import date
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import algoritmos, libtexto, repos, sugerencias_editoriales
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

    noticias = repos.listar_noticias_algoritmo(
        plataforma=plataforma,
        nivel=nivel,
        solo_cambios=_flag(request, "solo_cambios"),
        incluir_archivadas=_flag(request, "incluir_archivadas"),
        limite=limite,
    )
    fuentes = repos.listar_fuentes_algoritmo()
    return JSONResponse(
        {
            "noticias": [_noticia_a_dict(n) for n in noticias],
            "fuentes": [_fuente_a_dict(f) for f in fuentes],
            "pendientes": algoritmos.fuentes_pendientes(),
            **_vocabulario(),
        }
    )


async def refrescar(request: Request) -> Response:
    """POST /api/algoritmos/refrescar: ingiere los feeds. Cuerpo `{fuente?}` opcional.

    Sin `fuente`, refresca TODAS las activas. Degradacion honesta: cada fuente que falla
    se anota con su error y no rompe las demas. Devuelve el resumen de la ingesta.
    """
    datos = await leer_json(request)
    solo = datos.get("fuente")
    solo = solo.strip() if isinstance(solo, str) and solo.strip() else None
    if solo and repos.obtener_fuente_algoritmo(solo) is None:
        return JSONResponse({"error": "Esa fuente ya no existe."}, status_code=404)
    resumen = algoritmos.refrescar(solo_fuente=solo)
    return JSONResponse({"resumen": resumen})


async def sembrar(request: Request) -> Response:
    """POST /api/algoritmos/sembrar: crea las fuentes recomendadas que falten (idempotente)."""
    creadas = algoritmos.sembrar()
    return JSONResponse(
        {"creadas": [_fuente_a_dict(f) for f in creadas], "total": len(creadas)}
    )


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

    fuente = repos.crear_fuente_algoritmo(nombre.strip(), url, plataforma=plataforma, tipo=tipo)
    return JSONResponse({"fuente": _fuente_a_dict(fuente)})


async def actualizar_fuente(request: Request) -> Response:
    """PUT /api/algoritmos/fuentes/{id}: edicion parcial `{nombre?,url?,plataforma?,tipo?,activo?}`."""
    fuente_id = request.path_params["fuente_id"]
    if repos.obtener_fuente_algoritmo(fuente_id) is None:
        return JSONResponse({"error": "Esa fuente ya no existe."}, status_code=404)
    datos = await leer_json(request)
    campos: dict[str, Any] = {}
    if "nombre" in datos:
        nombre = datos.get("nombre")
        if not isinstance(nombre, str) or not nombre.strip():
            return JSONResponse({"error": "El nombre de la fuente es obligatorio."}, status_code=400)
        campos["nombre"] = nombre.strip()
    if "url" in datos:
        url, error = rss.validar_url(datos.get("url"))
        if error is not None:
            return JSONResponse({"error": error}, status_code=400)
        campos["url"] = url
    if "plataforma" in datos:
        plataforma, error = _validar_plataforma(datos.get("plataforma"))
        if error is not None:
            return JSONResponse({"error": error}, status_code=400)
        campos["plataforma"] = plataforma
    if "tipo" in datos:
        tipo, error = _validar_tipo(datos.get("tipo"))
        if error is not None:
            return JSONResponse({"error": error}, status_code=400)
        campos["tipo"] = tipo
    if "activo" in datos:
        campos["activo"] = bool(datos.get("activo"))

    fuente = repos.actualizar_fuente_algoritmo(fuente_id, campos)
    if fuente is None:
        return JSONResponse({"error": "Esa fuente ya no existe."}, status_code=404)
    return JSONResponse({"fuente": _fuente_a_dict(fuente)})


async def borrar_fuente(request: Request) -> Response:
    """DELETE /api/algoritmos/fuentes/{id}: baja de la fuente y sus noticias."""
    fuente_id = request.path_params["fuente_id"]
    if not repos.borrar_fuente_algoritmo(fuente_id):
        return JSONResponse({"error": "Esa fuente ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Fuente borrada."})


async def a_texto(request: Request) -> Response:
    """POST /api/algoritmos/{id}/texto: marca aplicada + devuelve el borrador de ficha.

    NO escribe la ficha editorial (verdad curada por humanos): devuelve un bloque markdown
    listo para pegar/confirmar en la Texto y marca la noticia como aplicada para no
    re-proponerla. Devuelve `{noticia, propuesta, plataforma}`.
    """
    noticia_id = request.path_params["noticia_id"]
    noticia = repos.obtener_noticia_algoritmo(noticia_id)
    if noticia is None:
        return JSONResponse({"error": "Esa noticia ya no existe."}, status_code=404)
    propuesta = algoritmos.texto_propuesta_ficha(noticia)
    actualizada = repos.marcar_noticia_algoritmo(noticia_id, aplicada=True)
    return JSONResponse(
        {
            "noticia": _noticia_a_dict(actualizada or noticia),
            "propuesta": propuesta,
            "plataforma": noticia.get("plataforma", "general"),
        }
    )


async def archivar(request: Request) -> Response:
    """POST /api/algoritmos/{id}/archivar: archiva/desarchiva `{archivada?: true}`."""
    noticia_id = request.path_params["noticia_id"]
    if repos.obtener_noticia_algoritmo(noticia_id) is None:
        return JSONResponse({"error": "Esa noticia ya no existe."}, status_code=404)
    datos = await leer_json(request)
    archivada = datos.get("archivada", True)
    noticia = repos.marcar_noticia_algoritmo(noticia_id, archivada=bool(archivada))
    return JSONResponse({"noticia": _noticia_a_dict(noticia) if noticia else None})


# --------------------------------------------------------------------------- #
# Sugerencias editoriales (generadas por el digest diario)                      #
# --------------------------------------------------------------------------- #


async def listar_sugerencias(request: Request) -> Response:
    """GET /api/algoritmos/sugerencias?estado=: propuestas editoriales + contador de nuevas."""
    estado = request.query_params.get("estado") or None
    if estado is not None and estado not in repos.ESTADOS_SUGERENCIA_EDITORIAL:
        return JSONResponse({"error": "Estado no permitido."}, status_code=400)
    sugerencias = repos.listar_sugerencias_editoriales(estado=estado, limite=200)
    return JSONResponse(
        {
            "sugerencias": [_sugerencia_a_dict(s) for s in sugerencias],
            "total": len(sugerencias),
            "nuevas": repos.contar_sugerencias_editoriales(estado="nueva"),
        }
    )


def _sugerencia_a_dict(s: dict[str, Any]) -> dict[str, Any]:
    """Serializa una sugerencia con la etiqueta humana de la plataforma."""
    return {
        **s,
        "plataforma_nombre": algoritmos.PLATAFORMAS.get(s.get("plataforma", "general"), ""),
    }


def _aplicar_a_ficha(plataforma: str, detalle: str) -> str:
    """Anade el detalle de la sugerencia a la ficha editorial de la plataforma (crea si falta).

    Devuelve el id del documento de texto afectado. La escritura es la MISMA que hace el
    editor a mano (modulo `texto`): un humano la dispara con su clic; nunca el sistema solo.
    """
    fid = sugerencias_editoriales.ficha_id_de(plataforma)
    seccion = (
        f"## Actualización editorial ({date.today().isoformat()}) — desde noticias de algoritmo\n\n"
        f"{detalle.strip()}\n"
    )
    doc = libtexto.obtener(fid)
    if doc is not None:
        cuerpo = (doc.cuerpo or "").rstrip()
        nuevo = f"{cuerpo}\n\n{seccion}" if cuerpo else seccion
        libtexto.guardar(fid, cuerpo=nuevo)
        return fid
    creado = libtexto.crear(
        titulo=plataforma.capitalize(), tipo="editorial", carpeta="plataformas",
        clase="plataforma", cuerpo=seccion,
    )
    return creado.id


async def aplicar_sugerencia(request: Request) -> Response:
    """POST /api/algoritmos/sugerencias/{id}/aplicar: aplica a la ficha (editorial) y marca aplicada.

    Para `tipo='editorial'` ANADE el detalle a la ficha editorial de la plataforma (la crea si
    no existe). Para `tipo='limite'` NO toca codigo (los limites son constantes): solo marca la
    sugerencia como atendida y devuelve una nota. Idempotente: una sugerencia ya resuelta no se
    re-aplica.
    """
    sug_id = request.path_params["sugerencia_id"]
    sug = repos.obtener_sugerencia_editorial(sug_id)
    if sug is None:
        return JSONResponse({"error": "Esa sugerencia ya no existe."}, status_code=404)
    if sug["estado"] != "nueva":
        return JSONResponse({"error": "Esa sugerencia ya estaba resuelta."}, status_code=400)

    ficha_id = ""
    nota = ""
    if sug["tipo"] == "editorial":
        try:
            ficha_id = _aplicar_a_ficha(sug["plataforma"], sug["detalle"])
        except libtexto.TextoError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
    else:
        nota = (
            "El límite de caracteres es una constante del sistema: aplica el cambio en el "
            "código (keni_shared/limites_plataforma.py). La sugerencia queda marcada como atendida."
        )
    actualizada = repos.actualizar_estado_sugerencia_editorial(sug_id, "aplicada")
    return JSONResponse(
        {"sugerencia": _sugerencia_a_dict(actualizada or sug), "ficha_id": ficha_id, "nota": nota}
    )


async def descartar_sugerencia(request: Request) -> Response:
    """POST /api/algoritmos/sugerencias/{id}/descartar: marca la sugerencia como descartada."""
    sug_id = request.path_params["sugerencia_id"]
    if repos.obtener_sugerencia_editorial(sug_id) is None:
        return JSONResponse({"error": "Esa sugerencia ya no existe."}, status_code=404)
    actualizada = repos.actualizar_estado_sugerencia_editorial(sug_id, "descartada")
    return JSONResponse({"sugerencia": _sugerencia_a_dict(actualizada) if actualizada else None})


async def generar_sugerencias(request: Request) -> Response:
    """POST /api/algoritmos/sugerencias/generar: lanza el digest AHORA en segundo plano.

    Encola un `claude -p` por plataforma con noticias importantes pendientes (el worker lo
    ejecuta) y persiste las propuestas. Responde de inmediato; el front refresca para verlas.
    """
    threading.Thread(
        target=sugerencias_editoriales.ejecutar_barrido,
        name="sugerencias-editoriales-manual",
        daemon=True,
    ).start()
    return JSONResponse(
        {"mensaje": "Generando sugerencias en segundo plano; aparecerán en unos minutos."}
    )


RUTAS = [
    Route("/api/algoritmos", listar, methods=["GET"]),
    Route("/api/algoritmos/refrescar", refrescar, methods=["POST"]),
    Route("/api/algoritmos/sembrar", sembrar, methods=["POST"]),
    Route("/api/algoritmos/sugerencias", listar_sugerencias, methods=["GET"]),
    Route("/api/algoritmos/sugerencias/generar", generar_sugerencias, methods=["POST"]),
    Route("/api/algoritmos/sugerencias/{sugerencia_id}/aplicar", aplicar_sugerencia, methods=["POST"]),
    Route("/api/algoritmos/sugerencias/{sugerencia_id}/descartar", descartar_sugerencia, methods=["POST"]),
    Route("/api/algoritmos/fuentes", crear_fuente, methods=["POST"]),
    Route("/api/algoritmos/fuentes/{fuente_id}", actualizar_fuente, methods=["PUT"]),
    Route("/api/algoritmos/fuentes/{fuente_id}", borrar_fuente, methods=["DELETE"]),
    Route("/api/algoritmos/{noticia_id}/texto", a_texto, methods=["POST"]),
    Route("/api/algoritmos/{noticia_id}/archivar", archivar, methods=["POST"]),
]
