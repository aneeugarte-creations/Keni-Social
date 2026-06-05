"""API de Agentes de investigacion (Ola 6).

Los agentes investigan por marca/linea/tema y depositan candidatos fechados para
revision humana. El humano acepta (-> tablero) o descarta. NUNCA publican solos.

Endpoints:
  GET    /api/investigacion/briefs                -> {briefs:[...]}
  POST   /api/investigacion/briefs                -> {brief}
  PUT    /api/investigacion/briefs/{id}           -> {brief}
  DELETE /api/investigacion/briefs/{id}           -> {ok:true}
  POST   /api/investigacion/correr                -> {candidatos:[...], errores:[...]}
  GET    /api/investigacion/candidatos?fecha=&marca=&estado= -> {candidatos:[...]}
  POST   /api/investigacion/candidatos/{id}/aceptar -> {candidato, contenido_id}
  POST   /api/investigacion/candidatos/{id}/descartar -> {candidato}
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import autogen_copy, marcas, repos
from .._http_json import leer_json
from ..dominio import investigacion_agente
from ..seguridad import autor_de_peticion

_log = logging.getLogger("keni_consola.api.investigacion")

_MARCAS_IDS = {m[0] for m in marcas.opciones()}
_MAX_TITULO = 500
_MAX_TEXTO = 2000
_ESTADOS_CANDIDATO = frozenset({"nuevo", "aceptado", "descartado"})


# --------------------------------------------------------------------------- #
# Helpers de validacion                                                        #
# --------------------------------------------------------------------------- #


def _validar_marca(valor: Any) -> tuple[str, str | None]:
    """Valida id de marca; '' es valido (sin marca). (marca, error_o_None)."""
    if valor is None:
        return "", None
    if not isinstance(valor, str):
        return "", "La marca debe ser texto."
    valor = valor.strip()
    if valor and valor not in _MARCAS_IDS:
        return "", "Marca no permitida."
    return valor, None


# --------------------------------------------------------------------------- #
# GET /api/investigacion/briefs                                                #
# --------------------------------------------------------------------------- #


async def listar_briefs(request: Request) -> Response:
    """`GET /api/investigacion/briefs` -> `{briefs: [Brief...]}`."""
    solo_activos = str(request.query_params.get("activos", "")).lower() in ("1", "true", "si")
    briefs = repos.listar_inv_briefs(solo_activos=solo_activos)
    return JSONResponse({"briefs": briefs})


# --------------------------------------------------------------------------- #
# POST /api/investigacion/briefs                                               #
# --------------------------------------------------------------------------- #


async def crear_brief(request: Request) -> Response:
    """`POST /api/investigacion/briefs` -> `{brief}`."""
    datos = await leer_json(request)
    nombre = str(datos.get("nombre") or "").strip()
    instrucciones = str(datos.get("instrucciones") or "").strip()
    if not instrucciones:
        return JSONResponse({"error": "Las instrucciones del brief son obligatorias."}, status_code=400)
    if not nombre:
        nombre = instrucciones[:80]

    marca, err = _validar_marca(datos.get("marca"))
    if err:
        return JSONResponse({"error": err}, status_code=400)

    linea = str(datos.get("linea") or "").strip()[:300]
    idiomas = str(datos.get("idiomas") or "").strip()[:200]

    brief = repos.crear_inv_brief(
        nombre=nombre[:300],
        marca=marca,
        linea=linea,
        instrucciones=instrucciones[:5000],
        idiomas=idiomas,
    )
    return JSONResponse({"brief": brief})


# --------------------------------------------------------------------------- #
# PUT /api/investigacion/briefs/{id}                                           #
# --------------------------------------------------------------------------- #


async def actualizar_brief(request: Request) -> Response:
    """`PUT /api/investigacion/briefs/{id}` (parcial) -> `{brief}`."""
    brief_id = request.path_params["brief_id"]
    datos = await leer_json(request)

    campos: dict[str, Any] = {}
    if "nombre" in datos:
        campos["nombre"] = str(datos["nombre"] or "").strip()[:300]
    if "instrucciones" in datos:
        campos["instrucciones"] = str(datos["instrucciones"] or "").strip()[:5000]
    if "linea" in datos:
        campos["linea"] = str(datos["linea"] or "").strip()[:300]
    if "idiomas" in datos:
        campos["idiomas"] = str(datos["idiomas"] or "").strip()[:200]
    if "activo" in datos:
        campos["activo"] = bool(datos["activo"])
    if "marca" in datos:
        marca, err = _validar_marca(datos["marca"])
        if err:
            return JSONResponse({"error": err}, status_code=400)
        campos["marca"] = marca

    brief = repos.actualizar_inv_brief(brief_id, campos)
    if brief is None:
        return JSONResponse({"error": "Brief no encontrado."}, status_code=404)
    return JSONResponse({"brief": brief})


# --------------------------------------------------------------------------- #
# DELETE /api/investigacion/briefs/{id}                                       #
# --------------------------------------------------------------------------- #


async def borrar_brief(request: Request) -> Response:
    """`DELETE /api/investigacion/briefs/{id}` -> `{ok: true}`."""
    brief_id = request.path_params["brief_id"]
    ok = repos.borrar_inv_brief(brief_id)
    if not ok:
        return JSONResponse({"error": "Brief no encontrado."}, status_code=404)
    return JSONResponse({"ok": True})


# --------------------------------------------------------------------------- #
# POST /api/investigacion/correr                                               #
# --------------------------------------------------------------------------- #


async def correr(request: Request) -> Response:
    """`POST /api/investigacion/correr` -> `{candidatos:[...], errores:[...]}`.

    Cuerpo: `{brief_id}` (brief guardado) o ad-hoc `{marca?, linea, instrucciones}`.
    Corre el agente en threadpool (no bloquea el event loop), inserta los candidatos
    con `estado=nuevo` fechados HOY. Propone; NUNCA crea tablero ni publica.
    """
    datos = await leer_json(request)
    hoy = date.today().isoformat()

    # Resuelve el brief: guardado (por id) o ad-hoc (inline).
    brief_id = str(datos.get("brief_id") or "").strip()
    if brief_id:
        brief = repos.obtener_inv_brief(brief_id)
        if brief is None:
            return JSONResponse({"error": "Brief no encontrado."}, status_code=404)
    else:
        # Brief ad-hoc: se construye al vuelo pero no se persiste.
        instrucciones = str(datos.get("instrucciones") or "").strip()
        if not instrucciones:
            return JSONResponse(
                {"error": "Indica `brief_id` o `instrucciones` para la investigacion."},
                status_code=400,
            )
        marca, err = _validar_marca(datos.get("marca"))
        if err:
            return JSONResponse({"error": err}, status_code=400)
        brief = {
            "id": "",
            "nombre": str(datos.get("nombre") or instrucciones[:80]).strip(),
            "marca": marca,
            "linea": str(datos.get("linea") or "").strip(),
            "instrucciones": instrucciones[:5000],
            "idiomas": str(datos.get("idiomas") or "").strip(),
            "activo": True,
        }

    # Ejecuta el agente en threadpool para no bloquear el event loop.
    loop = asyncio.get_running_loop()
    candidatos_norm, errores = await loop.run_in_executor(
        None,
        lambda: investigacion_agente.correr_brief(brief, fecha=hoy),
    )

    if not candidatos_norm:
        return JSONResponse({"candidatos": [], "errores": errores})

    # Inserta en bulk con estado=nuevo.
    insertados = repos.crear_inv_candidatos(candidatos_norm)
    _log.info(
        "Investigacion '%s': %d candidato(s) para %s.",
        brief.get("nombre", "?"), len(insertados), hoy,
    )
    return JSONResponse({"candidatos": insertados, "errores": errores})


# --------------------------------------------------------------------------- #
# GET /api/investigacion/candidatos                                            #
# --------------------------------------------------------------------------- #


async def listar_candidatos(request: Request) -> Response:
    """`GET /api/investigacion/candidatos?fecha=&marca=&estado=` -> `{candidatos:[...]}`.

    Por defecto `fecha=hoy`. Filtros opcionales: marca, estado.
    """
    q = request.query_params
    fecha = q.get("fecha") or date.today().isoformat()
    marca = q.get("marca") or None
    estado = q.get("estado") or None
    brief_id = q.get("brief_id") or None

    # Valida marca si se provee.
    if marca and marca not in _MARCAS_IDS:
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)
    # Valida estado si se provee.
    if estado and estado not in _ESTADOS_CANDIDATO:
        return JSONResponse(
            {"error": f"Estado no permitido. Validos: {', '.join(sorted(_ESTADOS_CANDIDATO))}."},
            status_code=400,
        )

    candidatos = repos.listar_inv_candidatos(
        fecha=fecha, marca=marca, estado=estado, brief_id=brief_id
    )
    return JSONResponse({"candidatos": candidatos})


# --------------------------------------------------------------------------- #
# POST /api/investigacion/candidatos/{id}/aceptar                              #
# --------------------------------------------------------------------------- #


async def aceptar_candidato(request: Request) -> Response:
    """`POST /api/investigacion/candidatos/{id}/aceptar` -> `{candidato, contenido_id}`.

    Reutiliza el camino desde-radar/aportar: `repos.crear_contenido(origen='investigacion')`
    + plataformas por red, best-effort copy en background. Marca estado=aceptado + contenido_id.
    NUNCA publica; el tablero resultante sigue el flujo normal de revision.
    """
    candidato_id = request.path_params["candidato_id"]
    candidato = repos.obtener_inv_candidato(candidato_id)
    if candidato is None:
        return JSONResponse({"error": "Candidato no encontrado."}, status_code=404)
    if candidato["estado"] == "aceptado":
        contenido_id = candidato["contenido_id"]
        return JSONResponse({"candidato": candidato, "contenido_id": contenido_id})

    datos = await leer_json(request)
    redes_iniciales: list[str] = []
    redes_raw = datos.get("redes", [])
    if isinstance(redes_raw, list):
        from .. import redes as redes_mod  # import perezoso
        ids_redes = set(redes_mod.ids())
        redes_iniciales = [r for r in redes_raw if isinstance(r, str) and r in ids_redes]

    generar_copy = datos.get("generar", True)

    # Crea el item del tablero reutilizando el mismo camino que desde-radar/aportar.
    item = repos.crear_contenido(
        clase="contenido",
        flujo="importante",
        titulo=candidato["titulo"][:_MAX_TITULO],
        descripcion=(
            f"{candidato['resumen']}\n\n"
            f"Por que es relevante: {candidato['por_que']}\n\n"
            f"Fuente: {candidato['fuente']} {candidato['enlace']}"
        ).strip()[:_MAX_TEXTO],
        marca=candidato["marca"],
        prioridad="media",
        fecha_objetivo=candidato["fecha"] or date.today().isoformat(),
        autor=autor_de_peticion(request),
        origen="investigacion",
        tipo_contenido="fuente",
    )
    for red in dict.fromkeys(redes_iniciales):
        repos.crear_contenido_plataforma(
            contenido_id=item["id"], red=red, falta_copy=True, falta_imagen=True,
        )

    # Copy en background: best-effort, gateado por marca y por el flag `generar`.
    genero = False
    if candidato["marca"] and generar_copy:
        try:
            genero = autogen_copy.lanzar_para_topic(item) is not None
        except Exception:  # noqa: BLE001 -- la generacion es opcional
            genero = False

    # Marca el candidato como aceptado y vincula el contenido creado.
    candidato = repos.actualizar_inv_candidato(
        candidato_id, estado="aceptado", contenido_id=item["id"]
    ) or candidato

    return JSONResponse({
        "candidato": candidato,
        "contenido_id": item["id"],
        "copy_en_proceso": genero,
    })


# --------------------------------------------------------------------------- #
# POST /api/investigacion/candidatos/{id}/descartar                            #
# --------------------------------------------------------------------------- #


async def descartar_candidato(request: Request) -> Response:
    """`POST /api/investigacion/candidatos/{id}/descartar` -> `{candidato}`."""
    candidato_id = request.path_params["candidato_id"]
    candidato = repos.actualizar_inv_candidato(candidato_id, estado="descartado")
    if candidato is None:
        return JSONResponse({"error": "Candidato no encontrado."}, status_code=404)
    return JSONResponse({"candidato": candidato})


# --------------------------------------------------------------------------- #
# Rutas auto-descubiertas                                                      #
# --------------------------------------------------------------------------- #

RUTAS = [
    Route("/api/investigacion/briefs", listar_briefs, methods=["GET"]),
    Route("/api/investigacion/briefs", crear_brief, methods=["POST"]),
    Route("/api/investigacion/briefs/{brief_id}", actualizar_brief, methods=["PUT"]),
    Route("/api/investigacion/briefs/{brief_id}", borrar_brief, methods=["DELETE"]),
    Route("/api/investigacion/correr", correr, methods=["POST"]),
    Route("/api/investigacion/candidatos", listar_candidatos, methods=["GET"]),
    Route("/api/investigacion/candidatos/{candidato_id}/aceptar", aceptar_candidato, methods=["POST"]),
    Route("/api/investigacion/candidatos/{candidato_id}/descartar", descartar_candidato, methods=["POST"]),
]
