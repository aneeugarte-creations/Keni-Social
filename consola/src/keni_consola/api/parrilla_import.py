"""API: importacion de la PARRILLA/ROTA desde un documento (#parrilla-import).

En `/operacion/parrilla/turnos` el usuario suelta un documento (PDF, imagen/captura, Word,
Excel, texto). Un `claude -p` READ-ONLY lo lee y PROPONE operaciones (eventos/turnos nuevos,
modificaciones) como JSON. La propuesta se ESTACIONA (estado `generando` -> `pendiente`); el
frontend la previsualiza sobre el calendario real y, al ACEPTAR, el back aplica el diff en UNA
transaccion. Claude NUNCA escribe en el calendario: solo emite JSON; el codigo Python valida y
aplica.

Endpoints:
  - `POST   /api/parrilla/importar`               (multipart: archivo + semana) -> {propuesta_id, gen_id}
  - `GET    /api/parrilla/propuestas[?estado]`    lista propuestas (recientes primero).
  - `GET    /api/parrilla/propuestas/{id}`        detalle (estado del job + operaciones + conflictos).
  - `POST   /api/parrilla/propuestas/{id}/aplicar`   re-valida contra BD viva y aplica (409 si choca).
  - `POST   /api/parrilla/propuestas/{id}/descartar` marca descartada.

El `estado` de una propuesta REFLEJA el del job mientras genera: el GET de detalle consulta la
generacion (`gen_id`) y, si sigue `ejecutando`, devuelve `estado='generando'`; si el job acabo
en error, `estado='error'`. El post-procesado del worker es quien guarda las operaciones y pasa
la propuesta a `pendiente` (o `error`).
"""

from __future__ import annotations

from typing import Any

from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import auth, generaciones, media, repos
from .. import rota as dominio_rota
from ..dominio import parrilla_import as pi
from ..dominio import parrilla_import_job as job
from ..seguridad import autor_de_peticion


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _roster() -> dict[str, str]:
    """Roster valido id->nombre (usuarios con cobertura), MISMO criterio que la rota."""
    return {
        u["id"]: u["usuario"]
        for u in auth.listar_usuarios()
        if u.get("cobertura")
    }


def _estado_efectivo(propuesta: dict[str, Any]) -> str:
    """Estado de la propuesta que REFLEJA el del job mientras genera.

    Si la propuesta esta en `generando`, miramos la generacion (`gen_id`): si el job sigue
    `ejecutando`, seguimos en `generando`; si acabo en `error`, devolvemos `error`. Una vez el
    worker guardo el resultado (estado `pendiente`/`error`/`aplicada`/`descartada`), ese estado
    persistido manda. Esto permite que el frontend sondee el detalle sin un endpoint aparte.
    """
    estado = propuesta.get("estado") or ""
    if estado != pi.ESTADO_GENERANDO:
        return estado
    gen_id = propuesta.get("gen_id") or ""
    if not gen_id:
        return estado
    gen = generaciones.obtener(gen_id)
    if gen is None:
        return estado
    if gen.get("estado") == generaciones.ESTADO_ERROR:
        return pi.ESTADO_ERROR
    return pi.ESTADO_GENERANDO


def _propuesta_publica(propuesta: dict[str, Any], *, incluir_ops: bool = False) -> dict[str, Any]:
    """Forma estable de una propuesta para el listado (sin las operaciones, que pesan)."""
    base = {
        "id": propuesta["id"],
        "creado": propuesta.get("creado", ""),
        "actualizado": propuesta.get("actualizado", ""),
        "estado": _estado_efectivo(propuesta),
        "autor_id": propuesta.get("autor_id", ""),
        "autor_nombre": propuesta.get("autor_nombre", ""),
        "doc_nombre": propuesta.get("doc_nombre", ""),
        "doc_tipo": propuesta.get("doc_tipo", ""),
        "semana": propuesta.get("semana", ""),
        "gen_id": propuesta.get("gen_id", ""),
        "resumen": propuesta.get("resumen", ""),
        "error": propuesta.get("error", ""),
    }
    if incluir_ops:
        base["operaciones"] = propuesta.get("operaciones")
    return base


def _operaciones_con_conflicto(
    operaciones: list[dict[str, Any]] | None, semana: str, nombres: dict[str, str]
) -> list[dict[str, Any]]:
    """Anota cada operacion con su `conflicto` (+ datos de overlay) contra el estado VIVO.

    Construye el contexto de la semana desde la BD (turnos/franjas actuales) y usa el dominio
    puro `calcular_conflicto` para que el frontend pinte nuevo/cambio/conflicto sin re-derivar.
    """
    ops = operaciones or []
    ctx = job.construir_contexto(semana, nombres_miembros=nombres)
    anotadas: list[dict[str, Any]] = []
    for op in ops:
        info = pi.calcular_conflicto(op, ctx)
        anotadas.append({**op, **info})
    return anotadas


# --------------------------------------------------------------------------- #
# POST /api/parrilla/importar                                                  #
# --------------------------------------------------------------------------- #


async def importar(request: Request) -> Response:
    """POST /api/parrilla/importar (multipart): sube un documento y lanza la propuesta.

    Campos: `archivo` (file, obligatorio), `semana` (AAAA-MM-DD del lunes objetivo). Guarda el
    documento en el almacen de media, crea una `parrilla_propuesta` (estado `generando`) y
    ENCOLA un job `claude -p` READ-ONLY que lee el doc y propone operaciones. Responde de
    INMEDIATO con `{propuesta_id, gen_id}`; el frontend sondea el detalle hasta `pendiente`.
    """
    try:
        form = await request.form()
    except Exception:  # noqa: BLE001 -- multipart malformado => mensaje claro
        return JSONResponse({"error": "Formulario inválido."}, status_code=400)

    archivo = form.get("archivo")
    if not isinstance(archivo, UploadFile) or not (archivo.filename or ""):
        return JSONResponse({"error": "Falta el documento a importar."}, status_code=400)

    semana_crudo = str(form.get("semana") or "").strip()
    semana = dominio_rota.lunes_de_semana_iso(semana_crudo) if semana_crudo else ""
    if not semana:
        return JSONResponse(
            {"error": "Indica la semana objetivo (AAAA-MM-DD)."}, status_code=400
        )

    try:
        doc_nombre, doc_ext = await media.guardar_documento_subido(archivo)
    except media.MediaError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    autor = autor_de_peticion(request)
    propuesta = repos.crear_propuesta_parrilla(
        semana=semana,
        doc_nombre=doc_nombre,
        doc_tipo=doc_ext,
        autor_id=(autor or {}).get("id", ""),
        autor_nombre=(autor or {}).get("usuario", ""),
        estado=pi.ESTADO_GENERANDO,
    )

    try:
        gen = job.lanzar(
            propuesta_id=propuesta["id"],
            doc_nombre=doc_nombre,
            doc_ext=doc_ext,
            semana=semana,
            nombres_miembros=_roster(),
            autor=autor,
        )
    except generaciones.ColaLlenaError:
        repos.actualizar_propuesta_parrilla(
            propuesta["id"],
            {
                "estado": pi.ESTADO_ERROR,
                "error": "Hay demasiadas generaciones en curso; inténtalo en unos segundos.",
            },
        )
        return JSONResponse(
            {"error": "Hay demasiadas generaciones en curso; inténtalo en unos segundos."},
            status_code=429,
        )
    except job.ParrillaImportError as e:
        repos.actualizar_propuesta_parrilla(
            propuesta["id"], {"estado": pi.ESTADO_ERROR, "error": str(e)}
        )
        return JSONResponse({"error": str(e)}, status_code=400)

    gen_id = gen.get("id", "")
    repos.actualizar_propuesta_parrilla(propuesta["id"], {"gen_id": gen_id})
    return JSONResponse(
        {"propuesta_id": propuesta["id"], "gen_id": gen_id}, status_code=202
    )


# --------------------------------------------------------------------------- #
# GET listado / detalle                                                        #
# --------------------------------------------------------------------------- #


async def listar_propuestas(request: Request) -> Response:
    """GET /api/parrilla/propuestas[?estado]: propuestas mas recientes primero."""
    estado = (request.query_params.get("estado") or "").strip() or None
    if estado is not None and estado not in pi.ESTADOS_PROPUESTA:
        validos = " o ".join(f'"{e}"' for e in pi.ESTADOS_PROPUESTA)
        return JSONResponse({"error": f"Estado inválido. Usa {validos}."}, status_code=400)
    propuestas = repos.listar_propuestas_parrilla(estado=estado)
    return JSONResponse(
        {"propuestas": [_propuesta_publica(p) for p in propuestas]}
    )


async def detalle_propuesta(request: Request) -> Response:
    """GET /api/parrilla/propuestas/{id}: detalle con estado del job + operaciones + conflictos.

    Cada operacion lleva un `conflicto` (bool) calculado en el server contra el estado VIVO de
    la semana, y (para `modificar_turno`) los valores actuales de la fila referenciada, para que
    el frontend renderice el overlay (nuevo / cambio / conflicto) sin re-derivarlo.
    """
    propuesta_id = request.path_params["propuesta_id"]
    propuesta = repos.obtener_propuesta_parrilla(propuesta_id)
    if propuesta is None:
        return JSONResponse({"error": "La propuesta no existe."}, status_code=404)
    estado = _estado_efectivo(propuesta)
    operaciones = _operaciones_con_conflicto(
        propuesta.get("operaciones"), propuesta.get("semana", ""), _roster()
    )
    cuerpo = _propuesta_publica(propuesta)
    cuerpo["estado"] = estado
    cuerpo["operaciones"] = operaciones
    return JSONResponse(cuerpo)


# --------------------------------------------------------------------------- #
# POST aplicar / descartar                                                     #
# --------------------------------------------------------------------------- #


async def aplicar_propuesta(request: Request) -> Response:
    """POST /api/parrilla/propuestas/{id}/aplicar: re-valida contra la BD viva y aplica.

    Re-construye el contexto de la semana (las filas pudieron cambiar desde que se generó) y
    re-valida con el dominio puro. Si hay errores de validacion o CONFLICTOS (celda ocupada /
    turno desaparecido), devuelve 409 SIN aplicar. Si todo cuadra, aplica TODAS las operaciones
    en UNA transaccion (`origen='import-doc'`) y marca la propuesta `aplicada`.
    """
    propuesta_id = request.path_params["propuesta_id"]
    propuesta = repos.obtener_propuesta_parrilla(propuesta_id)
    if propuesta is None:
        return JSONResponse({"error": "La propuesta no existe."}, status_code=404)
    if _estado_efectivo(propuesta) != pi.ESTADO_PENDIENTE:
        return JSONResponse(
            {"error": "Solo se puede aplicar una propuesta en estado pendiente."},
            status_code=409,
        )

    semana = propuesta.get("semana", "")
    nombres = _roster()
    ctx = job.construir_contexto(semana, nombres_miembros=nombres)

    # Re-valida contra el estado ACTUAL (las filas pudieron cambiar tras generar la propuesta).
    validas, errores = pi.validar_operaciones(propuesta.get("operaciones") or [], ctx)
    if errores:
        return JSONResponse(
            {
                "error": "La propuesta ya no es válida contra el estado actual.",
                "errores": errores,
            },
            status_code=409,
        )

    # Conflictos (celda ocupada / turno desaparecido): no aplicamos si hay alguno.
    conflictivas = [
        {**op, **pi.calcular_conflicto(op, ctx)}
        for op in validas
    ]
    con_conflicto = [op for op in conflictivas if op.get("conflicto")]
    if con_conflicto:
        return JSONResponse(
            {
                "error": "Hay conflictos con el calendario actual; revísalos antes de aplicar.",
                "conflictos": con_conflicto,
            },
            status_code=409,
        )

    resumen = repos.aplicar_propuesta_parrilla(
        propuesta_id, validas, nombres_miembros=nombres, origen=pi.ORIGEN
    )
    return JSONResponse({"aplicada": True, **resumen})


async def descartar_propuesta(request: Request) -> Response:
    """POST /api/parrilla/propuestas/{id}/descartar: marca la propuesta descartada."""
    propuesta_id = request.path_params["propuesta_id"]
    propuesta = repos.obtener_propuesta_parrilla(propuesta_id)
    if propuesta is None:
        return JSONResponse({"error": "La propuesta no existe."}, status_code=404)
    actualizada = repos.actualizar_propuesta_parrilla(
        propuesta_id, {"estado": pi.ESTADO_DESCARTADA}
    )
    return JSONResponse(_propuesta_publica(actualizada or propuesta))


RUTAS = [
    Route("/api/parrilla/importar", importar, methods=["POST"]),
    Route("/api/parrilla/propuestas", listar_propuestas, methods=["GET"]),
    Route("/api/parrilla/propuestas/{propuesta_id}", detalle_propuesta, methods=["GET"]),
    Route(
        "/api/parrilla/propuestas/{propuesta_id}/aplicar",
        aplicar_propuesta,
        methods=["POST"],
    ),
    Route(
        "/api/parrilla/propuestas/{propuesta_id}/descartar",
        descartar_propuesta,
        methods=["POST"],
    ),
]
