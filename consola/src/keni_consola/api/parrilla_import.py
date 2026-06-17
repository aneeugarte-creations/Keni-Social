"""API: importacion de la PARRILLA/ROTA desde un documento (#parrilla-import).

En `/operacion/parrilla/turnos` el usuario suelta un documento (PDF, imagen/captura, Word,
Excel, texto). Un `claude -p` READ-ONLY lo lee y PROPONE operaciones (eventos/turnos nuevos,
modificaciones) como JSON. La propuesta se ESTACIONA (estado `generando` -> `pendiente`); el
frontend la previsualiza sobre el calendario real y, al ACEPTAR, el back aplica el diff en UNA
transaccion. Claude NUNCA escribe en el calendario: solo emite JSON; el codigo Python valida y
aplica.

Un documento puede cubrir VARIAS semanas (incluso un AÑO entero); las operaciones se validan
y aplican contra el estado real de CADA semana que tocan, no de una sola.

Endpoints:
  - `POST   /api/parrilla/importar`               (multipart: archivo; `semana` opcional) -> {propuesta_id, gen_id}
  - `GET    /api/parrilla/propuestas[?estado]`    lista propuestas (recientes primero).
  - `GET    /api/parrilla/propuestas/{id}`        detalle (estado del job + operaciones + conflictos + `rango`).
  - `POST   /api/parrilla/propuestas/{id}/aplicar`   re-valida contra BD viva y aplica (409 si choca).
  - `POST   /api/parrilla/propuestas/{id}/descartar` marca descartada.

El `estado` de una propuesta REFLEJA el del job mientras genera: el GET de detalle consulta la
generacion (`gen_id`) y, si sigue `ejecutando`, devuelve `estado='generando'`; si el job acabo
en error, `estado='error'`. El post-procesado del worker es quien guarda las operaciones y pasa
la propuesta a `pendiente` (o `error`).
"""

from __future__ import annotations

import logging
from typing import Any

from starlette.background import BackgroundTask
from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import auth, generaciones, marcas, media, repos
from .. import rota as dominio_rota
from ..dominio import extraccion_url
from ..dominio import parrilla_import as pi
from ..dominio import parrilla_import_job as job
from ..seguridad import autor_de_peticion

_log = logging.getLogger("keni_consola.parrilla_import")

# Descarga de un ENLACE en segundo plano: como NO bloquea la petición (corre tras responder, en
# un hilo), puede esperar más que el tope por defecto de `extraccion_url` (15 s, pensado para
# peticiones síncronas) y REINTENTAR con backoff los fallos transitorios (lento/cortó), igual que
# el motor de feeds de Fuentes. Una página lenta/intermitente desde el datacenter ya no se pierde.
_TIMEOUT_ENLACE = 25.0
_REINTENTOS_ENLACE = 3


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _roster() -> dict[str, str]:
    """Roster id->nombre del equipo COMPLETO (todos los usuarios), para no limitar a quién se
    puede asignar un turno al importar. NO filtramos por `cobertura`: el documento puede
    referenciar a cualquiera del equipo (los 16), y claude solo mapea a gente que ya existe."""
    return {u["id"]: u["usuario"] for u in auth.listar_usuarios()}


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
    operaciones: list[dict[str, Any]] | None, nombres: dict[str, str]
) -> list[dict[str, Any]]:
    """Anota cada operacion con su `conflicto` (+ datos de overlay) contra el estado VIVO.

    Construye el contexto del RANGO desde la BD (franjas/turnos de TODAS las semanas tocadas por
    las fechas de las operaciones) y usa el dominio puro `calcular_conflicto` para que el
    frontend pinte nuevo/cambio/conflicto sin re-derivar.
    """
    ops = operaciones or []
    ctx = job.construir_contexto_validacion(ops, nombres_miembros=nombres)
    anotadas: list[dict[str, Any]] = []
    for op in ops:
        info = pi.calcular_conflicto(op, ctx)
        anotadas.append({**op, **info})
    return anotadas


def _rango_de_operaciones(operaciones: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Resumen `{desde, hasta, semanas, total}` del rango temporal cubierto por las operaciones.

    `desde`/`hasta` son la fecha minima/maxima (ISO) de las ops; `semanas` los lunes ISO de las
    semanas tocadas (ordenados); `total` el numero de operaciones. Lo consume el frontend para
    mostrar un resumen y navegar las semanas. `desde`/`hasta` quedan "" si no hay fechas.
    """
    ops = operaciones or []
    fechas = sorted(
        f for f in (str(o.get("fecha", "") or "") for o in ops) if f
    )
    semanas = sorted(job.semanas_de_operaciones(ops))
    return {
        "desde": fechas[0] if fechas else "",
        "hasta": fechas[-1] if fechas else "",
        "semanas": semanas,
        "total": len(ops),
    }


# --------------------------------------------------------------------------- #
# POST /api/parrilla/importar                                                  #
# --------------------------------------------------------------------------- #


async def importar(request: Request) -> Response:
    """POST /api/parrilla/importar (multipart): sube un documento y lanza la propuesta.

    Campos: `archivo` (file, obligatorio). `semana` es OPCIONAL (mera pista; ya no ata la
    propuesta a una sola semana: el documento puede traer un año entero). Guarda el documento en
    el almacen de media, crea una `parrilla_propuesta` (estado `generando`, `semana=""`) y ENCOLA
    un job `claude -p` READ-ONLY que lee el doc y propone operaciones en CUALQUIER fecha. Responde
    de INMEDIATO con `{propuesta_id, gen_id}`; el frontend sondea el detalle hasta `pendiente`.
    """
    try:
        form = await request.form()
    except Exception:  # noqa: BLE001 -- multipart malformado => mensaje claro
        return JSONResponse({"error": "Formulario inválido."}, status_code=400)

    # `semana` es solo una pista opcional: ya no se exige ni ata la propuesta a una semana.
    semana_crudo = str(form.get("semana") or "").strip()
    semana = dominio_rota.lunes_de_semana_iso(semana_crudo) if semana_crudo else ""
    # MARCA del workspace que importa: se estampa en los eventos creados al aplicar, para que la
    # lista de Tareas (filtrada por marca) los muestre. Vacío si no es una marca válida.
    marca_crudo = str(form.get("marca") or "").strip()
    marca = marca_crudo if marca_crudo and marcas.es_marca(marca_crudo) else ""
    # Modo: "eventos" (por defecto) extrae eventos a cubrir; "tareas" extrae encargos sueltos
    # (clase='tarea', no van al calendario); "turnos" extrae una parrilla de trabajo y mete a
    # cada persona en la franja del equipo que le corresponde. Cambia el prompt y la salida.
    modo_crudo = str(form.get("modo") or "").strip()
    modo = modo_crudo if modo_crudo in ("tareas", "turnos") else "eventos"
    autor = autor_de_peticion(request)

    archivo = form.get("archivo")
    url_crudo = str(form.get("url") or "").strip()
    texto_pegado = str(form.get("texto") or "").strip()

    # TRES entradas a la MISMA propuesta: fichero, enlace o texto pegado. Se resuelven a un
    # `doc_nombre`/`doc_tipo` y a una función de encolado; el resto del flujo (propuesta →
    # job → sondeo → aplicar) es idéntico.
    if isinstance(archivo, UploadFile) and (archivo.filename or ""):
        try:
            doc_nombre, doc_ext = await media.guardar_documento_subido(archivo)
        except media.MediaError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        propuesta = repos.crear_propuesta_parrilla(
            semana=semana,
            doc_nombre=doc_nombre,
            doc_tipo=doc_ext,
            marca=marca,
            autor_id=(autor or {}).get("id", ""),
            autor_nombre=(autor or {}).get("usuario", ""),
            estado=pi.ESTADO_GENERANDO,
        )

        def _encolar() -> dict[str, Any]:
            return job.lanzar(
                propuesta_id=propuesta["id"],
                doc_nombre=doc_nombre,
                doc_ext=doc_ext,
                nombres_miembros=_roster(),
                autor=autor,
                modo=modo,
                marca=marca,
            )

    elif url_crudo:
        url_limpia, err = extraccion_url.validar_url(url_crudo)
        if err or url_limpia is None:
            return JSONResponse({"error": err or "Enlace no válido."}, status_code=400)
        # Vídeo/streaming: no hay artículo que leer. Chequeo BARATO (solo el host), así que se
        # resuelve YA con un 422 claro, sin crear propuesta ni bajar nada.
        if extraccion_url.es_host_de_video(url_limpia):
            return JSONResponse(
                {
                    "error": "Ese enlace es de un video o transmisión: no se puede leer como nota. "
                    "Pega el texto del evento a mano.",
                },
                status_code=422,
            )
        # La DESCARGA de la página (red, puede tardar o colgarse) NO bloquea la petición: creamos
        # la propuesta (estado generando), respondemos al INSTANTE y bajamos+encolamos en segundo
        # plano —igual que «Cajones del día» hace el trabajo pesado fuera del handler—. El frontend
        # sondea la propuesta hasta `pendiente` o `error`; ya no ve un timeout de la petición.
        propuesta = repos.crear_propuesta_parrilla(
            semana=semana,
            doc_nombre=url_limpia[:200],
            doc_tipo="enlace",
            marca=marca,
            autor_id=(autor or {}).get("id", ""),
            autor_nombre=(autor or {}).get("usuario", ""),
            estado=pi.ESTADO_GENERANDO,
        )
        pid = propuesta["id"]
        roster = _roster()

        def _descargar_y_encolar() -> None:
            """Baja el enlace y encola el job (fuera de la petición).

            DOS intentos para no rendirse ante un 403/bloqueo (muchas notas/medios bloquean el
            fetch del datacenter): 1) el SERVIDOR lee la página (rápido, con guard SSRF ya hecho);
            2) si falla, encolamos con la URL y la WEB habilitada para que el asistente la lea
            (WebFetch desde otra infra) o identifique el evento (WebSearch). Solo si el ENCOLADO
            falla queda la propuesta en `error`."""
            permitir_web = False
            try:
                titulo_url, cuerpo_url = extraccion_url.extraer_texto(
                    url_limpia, timeout=_TIMEOUT_ENLACE, reintentos=_REINTENTOS_ENLACE
                )
                texto = f"{titulo_url}\n\n{cuerpo_url}".strip() if titulo_url else cuerpo_url
            except Exception as e:  # noqa: BLE001 -- 403/bloqueo/timeout: caemos al fallback web
                _log.info(
                    "import enlace: el servidor no pudo leer %s (%s); fallback a web", pid, e
                )
                texto = url_limpia
                permitir_web = True
            try:
                gen = job.lanzar_desde_texto(
                    propuesta_id=pid,
                    texto=texto,
                    nombres_miembros=roster,
                    autor=autor,
                    modo=modo,
                    permitir_web=permitir_web,
                    marca=marca,
                )
            except generaciones.ColaLlenaError:
                repos.actualizar_propuesta_parrilla(
                    pid,
                    {
                        "estado": pi.ESTADO_ERROR,
                        "error": "Hay demasiadas generaciones en curso; inténtalo en unos segundos.",
                    },
                )
                return
            except job.ParrillaImportError as e:
                repos.actualizar_propuesta_parrilla(
                    pid, {"estado": pi.ESTADO_ERROR, "error": str(e)}
                )
                return
            repos.actualizar_propuesta_parrilla(pid, {"gen_id": gen.get("id", "")})

        return JSONResponse(
            {"propuesta_id": pid, "gen_id": ""},
            status_code=202,
            background=BackgroundTask(_descargar_y_encolar),
        )

    elif texto_pegado:
        propuesta = repos.crear_propuesta_parrilla(
            semana=semana,
            doc_nombre="Texto pegado",
            doc_tipo="texto",
            marca=marca,
            autor_id=(autor or {}).get("id", ""),
            autor_nombre=(autor or {}).get("usuario", ""),
            estado=pi.ESTADO_GENERANDO,
        )

        def _encolar() -> dict[str, Any]:
            # FRASE escrita a mano: el texto es el NOMBRE de un evento (p. ej. «la velada del año
            # VI»), no una transcripción con fecha. Habilitamos la web (`permitir_web`) para que el
            # job lo IDENTIFIQUE y DATE online; el camino de ENLACE NO lo hace (ya trae el artículo).
            return job.lanzar_desde_texto(
                propuesta_id=propuesta["id"],
                texto=texto_pegado,
                nombres_miembros=_roster(),
                autor=autor,
                modo=modo,
                permitir_web=True,
                marca=marca,
            )

    else:
        return JSONResponse(
            {"error": "Falta el documento, el enlace o el texto a importar."}, status_code=400
        )

    try:
        gen = _encolar()
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
    la semana que toca, y (para `modificar_turno`) los valores actuales de la fila referenciada,
    para que el frontend renderice el overlay (nuevo / cambio / conflicto) sin re-derivarlo.
    Ademas devuelve `rango` ({desde, hasta, semanas, total}) calculado de las fechas de las ops,
    para que el frontend muestre un resumen y navegue las semanas cubiertas.
    """
    propuesta_id = request.path_params["propuesta_id"]
    propuesta = repos.obtener_propuesta_parrilla(propuesta_id)
    if propuesta is None:
        return JSONResponse({"error": "La propuesta no existe."}, status_code=404)
    estado = _estado_efectivo(propuesta)
    ops_crudas = propuesta.get("operaciones")
    operaciones = _operaciones_con_conflicto(ops_crudas, _roster())
    cuerpo = _propuesta_publica(propuesta)
    cuerpo["estado"] = estado
    cuerpo["operaciones"] = operaciones
    cuerpo["rango"] = _rango_de_operaciones(ops_crudas)
    return JSONResponse(cuerpo)


# --------------------------------------------------------------------------- #
# POST aplicar / descartar                                                     #
# --------------------------------------------------------------------------- #


async def aplicar_propuesta(request: Request) -> Response:
    """POST /api/parrilla/propuestas/{id}/aplicar: re-valida contra la BD viva y aplica.

    Re-construye el contexto del RANGO (las semanas tocadas por las fechas; las filas pudieron
    cambiar desde que se generó) y re-valida con el dominio puro. Si hay errores de validacion o
    CONFLICTOS (celda ocupada / turno desaparecido), devuelve 409 SIN aplicar. Si todo cuadra,
    aplica TODAS las operaciones en UNA transaccion (`origen='import-doc'`, inicializando las franjas
    por defecto de cada semana nueva) y marca la propuesta `aplicada`.
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

    operaciones = propuesta.get("operaciones") or []
    nombres = _roster()
    ctx = job.construir_contexto_validacion(operaciones, nombres_miembros=nombres)

    # Re-valida contra el estado ACTUAL (las filas pudieron cambiar tras generar la propuesta).
    validas, errores = pi.validar_operaciones(operaciones, ctx)
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

    try:
        resumen = repos.aplicar_propuesta_parrilla(
            propuesta_id,
            validas,
            nombres_miembros=nombres,
            origen=pi.ORIGEN,
            # Estampa la marca del workspace que importó en los eventos creados, para que la
            # lista de Tareas (filtrada por marca) los muestre. Vacío en imports legados.
            marca=str(propuesta.get("marca") or ""),
        )
    except ValueError as e:
        # Una franja (slot) no resoluble para su semana: el diff entero se descartó (rollback).
        return JSONResponse({"error": str(e)}, status_code=409)
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
