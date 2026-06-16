"""Handlers del padre del tablero: listar, crear, actualizar y borrar un contenido.

El item de `contenido` es el padre del tablero; aquí viven el listado (con foco por
marca, filtros y catálogos) y el CRUD del item. Las filas por plataforma, etiquetas,
métricas, importación y puerta creativa viven en sus propios submódulos.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ...db_publicacion import ConflictoVersion
from ...dominio import notificaciones
from ...estados import CLASE_TAREA, ROLES_COBERTURA
from ...permisos import es_admin
from ...tiempo import hoy_utc
from ._comun import (
    _MAX_TEXTO,
    _MAX_TITULO,
    _RED_WEB,
    CLASES_PUBLICACION,
    ESTADOS_PUBLICACION,
    ESTADOS_PIEZA,
    FLUJOS_CONTENIDO,
    PRIORIDADES_CONTENIDO,
    TIPOS_CONTENIDO,
    _contenido_a_dict,
    _enfocar_items_por_marca,
    _red_nombre,
    _red_valida,
    _resolver_responsable,
    _usuarios_asignables,
    _validar_marca,
    auto_responsable,
    autor_de_peticion,
    leer_json,
    marcas,
    placeholders,
    redes,
    repos,
)


def _eventos_proximos() -> list[dict]:
    """Eventos de la rota desde hoy en adelante (para atar un contenido a un evento)."""
    eventos = repos.listar_eventos_rota(desde=hoy_utc().isoformat())
    return [
        {
            "id": e["id"],
            "titulo": e.get("titulo", ""),
            "fecha": e.get("fecha", ""),
            "hora": e.get("hora", ""),
        }
        for e in eventos
    ]


def _etiqueta_catalogo(et: dict) -> dict:
    """Forma reducida de una etiqueta para los catálogos/chips del tablero."""
    return {
        "id": et["id"],
        "nombre": et["nombre"],
        "clase": et["clase"],
        "marca": et.get("marca", ""),
        "color": et.get("color", ""),
    }


def _catalogos(marca: str | None = None) -> dict:
    """Catalogos para los selects del tablero (los `usuarios` se acotan al equipo de la marca)."""
    return {
        "usuarios": _usuarios_asignables(marca),
        "marcas": [{"id": mid, "nombre": nombre} for mid, nombre in marcas.opciones()],
        "redes": [*redes.opciones(), {"id": _RED_WEB, "nombre": "Web", "limite": None}],
        "flujos": list(FLUJOS_CONTENIDO),
        "prioridades": list(PRIORIDADES_CONTENIDO),
        "estados_contenido": list(ESTADOS_PUBLICACION),
        "estados_plataforma": list(ESTADOS_PIEZA),
        "eventos": _eventos_proximos(),
        # Solo etiquetas ACTIVAS para el selector; el catálogo completo vive en /api/etiquetas.
        "etiquetas": [_etiqueta_catalogo(e) for e in repos.listar_etiquetas(solo_activas=True)],
        # Variables `{...}` que el copy puede llevar y se autocompletan (placeholders).
        "variables": placeholders.catalogo(),
    }


async def listar(request: Request) -> Response:
    """GET /api/publicaciones: tablero completo (items + plataformas) y catalogos.

    Filtros opcionales por query: `clase`, `flujo`, `marca` (workspace), `evento_id`
    (cobertura de un evento de la rota), `responsable_id`, `estado`, `desde`, `hasta`
    (por `fecha_objetivo`), `etiqueta` (id de una etiqueta).
    """
    q = request.query_params
    items = repos.listar_publicacion(
        clase=q.get("clase") or None,
        flujo=q.get("flujo") or None,
        marca=q.get("marca") or None,
        evento_id=q.get("evento_id") or None,
        responsable_id=q.get("responsable_id") if "responsable_id" in q else None,
        estado=q.get("estado") or None,
        desde=q.get("desde") or None,
        hasta=q.get("hasta") or None,
    )
    # FOCO POR DEFECTO (no es restriccion): si la sesion tiene marcas preferentes y NO se pidio
    # una marca explicita, el listado se ENFOCA en SUS marcas para reducir la mezcla de contexto.
    # Es siempre sobreescribible: con `?marca=` (cualquiera) se ve esa marca. `listar_publicacion`
    # solo acepta UNA marca, asi que el foco se aplica POST-filtrando en memoria (universo del
    # piloto, asumible). Sin preferencia (admin/token/sin marcas) NO filtra: ve todo.
    items = _enfocar_items_por_marca(request, items, q.get("marca") or None)
    # Filtro por etiqueta: acota a los contenidos que la llevan (una sola lectura del N:M).
    etiqueta_id = q.get("etiqueta") or None
    if etiqueta_id:
        con_etiqueta = repos.ids_contenido_con_etiqueta(etiqueta_id)
        items = [it for it in items if it["id"] in con_etiqueta]
    # Una sola lectura de las plataformas y etiquetas, agrupadas por contenido. Si el GET
    # acota por `?marca=` (workspace), el filtro se empuja al SQL via la marca denormalizada
    # de `pieza`.
    por_contenido: dict[str, list[dict]] = {}
    for plat in repos.listar_piezas_fila(marca=q.get("marca") or None):
        por_contenido.setdefault(plat["publicacion_id"], []).append(plat)
    etiquetas_de = repos.etiquetas_por_contenido()
    return JSONResponse(
        {
            "contenidos": [
                _contenido_a_dict(
                    it, por_contenido.get(it["id"], []), etiquetas_de.get(it["id"], [])
                )
                for it in items
            ],
            "catalogos": _catalogos(q.get("marca") or None),
        }
    )


def _etiquetas_validas(valor: object) -> tuple[list[str], str | None]:
    """Valida una lista de ids de etiqueta del cliente contra el catálogo existente.

    Devuelve `(ids_existentes, error)`. Una etiqueta que ya no existe -> error 400 (el
    cliente está desincronizado). Lista vacía/ausente es válida (sin etiquetas).
    """
    if valor in (None, ""):
        return [], None
    if not isinstance(valor, list):
        return [], "Las etiquetas deben ser una lista."
    ids = [e for e in valor if isinstance(e, str) and e]
    for etiqueta_id in ids:
        if repos.obtener_etiqueta(etiqueta_id) is None:
            return [], "Alguna etiqueta ya no existe."
    return ids, None


async def crear(request: Request) -> Response:
    """POST /api/publicaciones: crea un item (padre) y, opcionalmente, sus filas por plataforma.

    Cuerpo: `titulo` (obligatorio), `clase` ('contenido'|'tarea'), `flujo`, `marca`,
    `evento_id`, `programa`, `prioridad`, `descripcion`, `fecha_objetivo`, `hora_objetivo`,
    `fecha_entrega`, `responsable_id`, `notas`, y `redes` (lista de ids para crear una fila
    por plataforma por cada una).
    """
    datos = await leer_json(request)
    titulo = datos.get("titulo")
    if not isinstance(titulo, str) or not titulo.strip():
        return JSONResponse({"error": "El contenido necesita un título."}, status_code=400)
    if len(titulo) > _MAX_TITULO:
        return JSONResponse({"error": "El título es demasiado largo."}, status_code=400)

    clase = datos.get("clase", "contenido")
    if clase not in CLASES_PUBLICACION:
        return JSONResponse({"error": "Clase inválida."}, status_code=400)

    flujo = datos.get("flujo", "") or ""
    if flujo and flujo not in FLUJOS_CONTENIDO:
        return JSONResponse({"error": "Flujo inválido."}, status_code=400)

    prioridad = datos.get("prioridad", "media") or "media"
    if prioridad not in PRIORIDADES_CONTENIDO:
        return JSONResponse({"error": "Prioridad inválida."}, status_code=400)

    marca, err = _validar_marca(datos.get("marca"))
    if err:
        return JSONResponse({"error": err}, status_code=400)

    evento_id = datos.get("evento_id", "") or ""
    if not isinstance(evento_id, str):
        evento_id = ""
    evento_id = evento_id.strip()
    if evento_id and repos.obtener_evento_rota(evento_id) is None:
        return JSONResponse({"error": "Ese evento ya no está en la rota"}, status_code=400)

    responsable, valido = _resolver_responsable(datos.get("responsable_id"))
    if not valido:
        return JSONResponse({"error": "El responsable no es un usuario válido."}, status_code=400)

    # --- «La lista» (reparto PULL, todas las marcas) -------------------------------------
    # Si el cliente NO fijó `responsable_id`, la pieza queda LIBRE («por cubrir») y el equipo
    # la coge desde Cobertura; nadie nace asignado por la máquina. `responsable_automatico`
    # devuelve None hoy (es el gancho de un eventual PUSH por marca). Override manual: si el
    # cliente mandó `responsable_id`, se respeta y NO se toca.
    if responsable is None and marca:
        responsable = auto_responsable.responsable_automatico(marca)
    # --- fin bloque «la lista» -----------------------------------------------------------

    # FORMATO de la pieza (foto|video): si se indica, DECIDE las redes destino
    # (`redes.redes_de_formato`: foto=3, video=5) en vez de la lista cruda `redes`. Vacío/
    # desconocido -> "foto" (el flujo automático). Lo normaliza `db.crear_publicacion`.
    formato_in = datos.get("formato")
    formato = redes.normalizar_formato(formato_in) if isinstance(formato_in, str) else ""

    redes_iniciales = datos.get("redes", [])
    if not isinstance(redes_iniciales, list):
        redes_iniciales = []
    redes_iniciales = [r for r in redes_iniciales if isinstance(r, str)]
    if any(not _red_valida(r) for r in redes_iniciales):
        return JSONResponse({"error": "Alguna red no es válida."}, status_code=400)

    etiquetas_iniciales, err = _etiquetas_validas(datos.get("etiquetas"))
    if err:
        return JSONResponse({"error": err}, status_code=400)

    def _texto(clave: str) -> str:
        v = datos.get(clave, "")
        return v.strip()[:_MAX_TEXTO] if isinstance(v, str) else ""

    item = repos.crear_publicacion(
        clase=clase,
        flujo=flujo,
        titulo=titulo.strip(),
        descripcion=_texto("descripcion"),
        marca=marca,
        evento_id=evento_id,
        programa=_texto("programa"),
        prioridad=prioridad,
        fecha_objetivo=_texto("fecha_objetivo"),
        hora_objetivo=_texto("hora_objetivo"),
        fecha_entrega=_texto("fecha_entrega"),
        autor=autor_de_peticion(request),
        responsable=responsable,
        notas=_texto("notas"),
        # Tipo de contenido (ia|galeria|fuente): de dónde sale la imagen. `db` coacciona
        # un valor desconocido o vacío al defecto ('ia').
        tipo_contenido=_texto("tipo_contenido"),
        # FORMATO de la pieza (foto|video): "" -> 'foto' (defecto). Decide las redes destino.
        formato=formato or "foto",
    )
    # Redes destino: si se indicó `formato`, las DECIDE `redes.redes_de_formato` (foto=3,
    # video=5) con el checklist de video activado en piezas video. Si no, se usan las `redes`
    # crudas que pasó el cliente (compat). Quita duplicados conservando el orden de llegada.
    if formato:
        es_video = formato == redes.FORMATO_VIDEO
        for red in redes.redes_de_formato(formato):
            repos.crear_pieza_fila(
                publicacion_id=item["id"], red=red, falta_video=es_video
            )
    else:
        for red in dict.fromkeys(redes_iniciales):
            repos.crear_pieza_fila(publicacion_id=item["id"], red=red)
    for etiqueta_id in dict.fromkeys(etiquetas_iniciales):
        repos.asignar_etiqueta(item["id"], etiqueta_id)
    plataformas = repos.listar_piezas_fila(item["id"])
    return JSONResponse(
        {"contenido": _contenido_a_dict(item, plataformas, list(dict.fromkeys(etiquetas_iniciales)))}
    )


async def actualizar(request: Request) -> Response:
    """PATCH /api/publicaciones/{id}: edita campos del padre (todos opcionales)."""
    publicacion_id = request.path_params["publicacion_id"]
    actual = repos.obtener_publicacion(publicacion_id)
    if actual is None:
        return JSONResponse({"error": "Ese contenido ya no existe."}, status_code=404)
    datos = await leer_json(request)
    campos: dict[str, object] = {}

    if "estado" in datos:
        if datos["estado"] not in ESTADOS_PUBLICACION:
            return JSONResponse({"error": "Estado inválido."}, status_code=400)
        campos["estado"] = datos["estado"]
    if "flujo" in datos:
        flujo = datos.get("flujo") or ""
        if flujo and flujo not in FLUJOS_CONTENIDO:
            return JSONResponse({"error": "Flujo inválido."}, status_code=400)
        campos["flujo"] = flujo
    if "prioridad" in datos:
        if datos["prioridad"] not in PRIORIDADES_CONTENIDO:
            return JSONResponse({"error": "Prioridad inválida."}, status_code=400)
        campos["prioridad"] = datos["prioridad"]
    if "tipo_contenido" in datos:
        if datos["tipo_contenido"] not in TIPOS_CONTENIDO:
            return JSONResponse({"error": "Tipo de contenido inválido."}, status_code=400)
        campos["tipo_contenido"] = datos["tipo_contenido"]
    # FORMATO de la pieza (foto|video): FLIP. Cambiar de formato reajusta las redes destino
    # (`redes.redes_de_formato`: foto=3, video=5) sin perder trabajo (ver
    # `repos.ajustar_plataformas_por_formato`). Se procesa DESPUÉS de persistir el padre.
    formato_nuevo: str | None = None
    if "formato" in datos:
        formato_nuevo = redes.normalizar_formato(datos.get("formato"))
        campos["formato"] = formato_nuevo
    if "marca" in datos:
        marca, err = _validar_marca(datos.get("marca"))
        if err:
            return JSONResponse({"error": err}, status_code=400)
        # Reasignar la pieza a OTRA marca es una accion legitima (el equipo es
        # multidisciplinar y cubre cualquier marca): la marca es un foco, no un bloqueo.
        campos["marca"] = marca
    if "evento_id" in datos:
        evento_id = datos.get("evento_id") or ""
        if not isinstance(evento_id, str):
            evento_id = ""
        evento_id = evento_id.strip()
        if evento_id and repos.obtener_evento_rota(evento_id) is None:
            return JSONResponse({"error": "Ese evento ya no está en la rota"}, status_code=400)
        campos["evento_id"] = evento_id
    if "responsable_id" in datos:
        responsable, valido = _resolver_responsable(datos.get("responsable_id"))
        if not valido:
            return JSONResponse({"error": "El responsable no es un usuario válido."}, status_code=400)
        nuevo_responsable = responsable["id"] if responsable else ""
        responsable_actual = actual.get("responsable_id") or ""
        # POLÍTICA DE CLAIMS (la lista): una pieza COGIDA solo la reasigna/libera su
        # responsable o un admin; pisarla por PATCH burlaría el claim atómico de
        # coger/soltar. Una pieza LIBRE la puede asignar cualquiera (flujo de tareas y
        # mcp-tablero: el token de mantenimiento no es usuario ni admin, así que puede
        # asignar piezas libres pero nunca robar un claim).
        if responsable_actual and nuevo_responsable != responsable_actual and not es_admin(request):
            autor = autor_de_peticion(request)
            if autor is None or autor.get("id") != responsable_actual:
                return JSONResponse(
                    {
                        "error": f"Ya la cogió {actual.get('responsable_nombre') or 'otra persona'}.",
                        "responsable_id": responsable_actual,
                        "responsable_nombre": actual.get("responsable_nombre") or "",
                    },
                    status_code=409,
                )
        campos["responsable_id"] = nuevo_responsable
        campos["responsable_nombre"] = responsable["usuario"] if responsable else ""
    for clave in ("titulo", "descripcion", "programa", "fecha_objetivo", "hora_objetivo", "fecha_entrega", "notas"):
        if clave in datos:
            v = datos.get(clave)
            campos[clave] = v.strip()[:_MAX_TEXTO] if isinstance(v, str) else ""

    if not campos:
        return JSONResponse({"error": "Indica algún campo a actualizar."}, status_code=400)

    # CONCURRENCIA OPTIMISTA (ADR 0012): si el cliente manda la `version` que leyó, el repo
    # rechaza la edición con `ConflictoVersion` si otra escritura adelantó el contador (carrera
    # pipeline↔humano). Sin `version` en el body se conserva el last-write-wins de siempre.
    version_esperada = datos.get("version")
    version_esperada = int(version_esperada) if isinstance(version_esperada, int) else None

    formato_anterior = redes.normalizar_formato(actual.get("formato"))
    try:
        item = repos.actualizar_publicacion(publicacion_id, campos, version_esperada=version_esperada)
    except ConflictoVersion:
        return JSONResponse(
            {"error": "El contenido cambió mientras lo editabas; recárgalo."},
            status_code=409,
        )
    if item is None:
        return JSONResponse({"error": "Ese contenido ya no existe."}, status_code=404)

    # FLIP de formato: reajusta las redes destino + el checklist (falta_video/falta_imagen) sin
    # perder trabajo. Solo si el formato CAMBIÓ realmente. El resumen viaja al cliente para avisar.
    ajuste: dict[str, list[str]] | None = None
    if formato_nuevo is not None and formato_nuevo != formato_anterior:
        ajuste = repos.ajustar_plataformas_por_formato(publicacion_id, formato_nuevo)

    plataformas = repos.listar_piezas_fila(publicacion_id)
    etiquetas = repos.etiquetas_por_contenido().get(publicacion_id, [])
    respuesta: dict[str, object] = {
        "contenido": _contenido_a_dict(item, plataformas, etiquetas)
    }
    if ajuste is not None:
        respuesta["ajuste_formato"] = ajuste
        # Aviso si se conservaron redes con trabajo en un flip video->foto (no se borraron).
        if ajuste.get("conservadas"):
            nombres = ", ".join(_red_nombre(r) for r in ajuste["conservadas"])
            respuesta["aviso"] = (
                f"Se conservaron redes con contenido ({nombres}); revisa si quieres quitarlas."
            )
    return JSONResponse(respuesta)


async def borrar(request: Request) -> Response:
    publicacion_id = request.path_params["publicacion_id"]
    if not repos.borrar_publicacion(publicacion_id):
        return JSONResponse({"error": "Ese contenido ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Contenido borrado."})


# --------------------------------------------------------------------------- #
# "Coger" / "Soltar": reparto de tareas SIN solaparse (la lista de ClaroSports).#
# El claim es ATÓMICO (`reclamar_publicacion`): si dos personas pulsan a la vez,   #
# solo una se la lleva; la otra recibe 409 con quién la tiene. UnoTV no usa esto #
# (su flujo es auto): la UI solo lo expone con Claro Sports activa.              #
# --------------------------------------------------------------------------- #


async def coger(request: Request) -> Response:
    """POST /api/publicaciones/{id}/coger: el usuario autenticado RECLAMA la pieza (claim atómico).

    Solo si está LIBRE (sin responsable). Si otra persona ya la cogió, 409 con quién la tiene
    — no se pisa. Idempotente si ya era mía.
    """
    publicacion_id = request.path_params["publicacion_id"]
    autor = autor_de_peticion(request)
    if not autor or not autor.get("id"):
        return JSONResponse(
            {"error": "Necesitas iniciar sesión para coger una tarea."}, status_code=401
        )
    item = repos.reclamar_publicacion(
        publicacion_id,
        responsable_id=autor["id"],
        responsable_nombre=autor.get("usuario", "") or "",
    )
    if item is None:
        # No se pudo reclamar: distinguir "no existe" de "ya cogida por otra persona".
        actual = repos.obtener_publicacion(publicacion_id)
        if actual is None:
            return JSONResponse({"error": "Ese contenido ya no existe."}, status_code=404)
        if (actual.get("responsable_id") or "") == autor["id"]:
            item = actual  # ya era mía: idempotente
        else:
            return JSONResponse(
                {
                    "error": f"Ya la cogió {actual.get('responsable_nombre') or 'otra persona'}.",
                    "responsable_id": actual.get("responsable_id") or "",
                    "responsable_nombre": actual.get("responsable_nombre") or "",
                },
                status_code=409,
            )
    plataformas = repos.listar_piezas_fila(publicacion_id)
    etiquetas = repos.etiquetas_por_contenido().get(publicacion_id, [])
    return JSONResponse({"contenido": _contenido_a_dict(item, plataformas, etiquetas)})


async def soltar(request: Request) -> Response:
    """POST /api/publicaciones/{id}/soltar: libera la pieza (vuelve al backlog «Por coger»).

    Solo puede soltarla quien la tiene, o un admin (para reasignar/balancear). Idempotente si
    ya estaba libre.
    """
    publicacion_id = request.path_params["publicacion_id"]
    actual = repos.obtener_publicacion(publicacion_id)
    if actual is None:
        return JSONResponse({"error": "Ese contenido ya no existe."}, status_code=404)
    autor = autor_de_peticion(request)
    if not autor or not autor.get("id"):
        return JSONResponse({"error": "Necesitas iniciar sesión."}, status_code=401)
    responsable_actual = actual.get("responsable_id") or ""
    if responsable_actual and responsable_actual != autor["id"] and not es_admin(request):
        return JSONResponse(
            {"error": "Solo quien la cogió (o un admin) puede soltarla."}, status_code=403
        )
    item = repos.actualizar_publicacion(
        publicacion_id, {"responsable_id": "", "responsable_nombre": ""}
    )
    plataformas = repos.listar_piezas_fila(publicacion_id)
    etiquetas = repos.etiquetas_por_contenido().get(publicacion_id, [])
    return JSONResponse({"contenido": _contenido_a_dict(item or actual, plataformas, etiquetas)})


async def asignar(request: Request) -> Response:
    """POST /api/publicaciones/{id}/asignar: el MANAGER (admin) EMPUJA la pieza a una persona.

    Es la SEGUNDA puerta de escritura del mismo campo `responsable_id` —el self-claim del
    empleado es `coger` (CAS contra responsable vacío, no pisa a nadie)—; aquí el coordinador de redes asigna,
    o REASIGNA pisando un responsable ya puesto, a quien elija. Solo admin: un editor reparte
    cogiendo del pool, no empujando a otros. Avisa al asignado (in-app), que es lo que retira
    el «te paso esto» del WhatsApp. Para LIBERAR una pieza se usa `soltar`, no este endpoint.
    """
    publicacion_id = request.path_params["publicacion_id"]
    autor = autor_de_peticion(request)
    if not autor or not autor.get("id"):
        return JSONResponse({"error": "Necesitas iniciar sesión."}, status_code=401)
    if not es_admin(request):
        return JSONResponse(
            {"error": "Solo el responsable de la lista puede asignar a otra persona."},
            status_code=403,
        )
    actual = repos.obtener_publicacion(publicacion_id)
    if actual is None:
        return JSONResponse({"error": "Ese contenido ya no existe."}, status_code=404)
    datos = await leer_json(request)
    responsable, valido = _resolver_responsable(datos.get("responsable_id"))
    if not valido:
        return JSONResponse(
            {"error": "El responsable no es un usuario válido."}, status_code=400
        )
    if responsable is None:
        return JSONResponse(
            {"error": "Indica a quién asignar la pieza (para liberarla, usa «soltar»)."},
            status_code=400,
        )
    item = (
        repos.actualizar_publicacion(
            publicacion_id,
            {
                "responsable_id": responsable["id"],
                "responsable_nombre": responsable["usuario"],
            },
        )
        or actual
    )
    notificaciones.tras_asignacion(item, autor)
    plataformas = repos.listar_piezas_fila(publicacion_id)
    etiquetas = repos.etiquetas_por_contenido().get(publicacion_id, [])
    return JSONResponse({"contenido": _contenido_a_dict(item, plataformas, etiquetas)})


async def aceptar(request: Request) -> Response:
    """POST /api/contenido/{id}/aceptar: PROMUEVE una tarea-propuesta al calendario de Turnos.

    Una tarea SUELTA con FECHA (`clase='tarea'`, `fecha_objetivo` no vacío y SIN `evento_id`) es
    una PROPUESTA de calendario: vive en la bandeja de notificaciones del calendario hasta que
    alguien la acepta. Aceptarla CREA el evento en la rota (con su título/fecha/hora/detalle/marca)
    y CONSUME la tarea (la borra): a partir de ahí se comporta como cualquier evento «Por cubrir».
    Para rechazarla se usa el DELETE normal (`/api/contenido/{id}`), que no crea evento.

    Requiere sesión; CUALQUIERA del equipo puede aceptar (modelo «la lista», pull). El alta del
    evento y el borrado de la tarea son dos pasos: si el borrado fallara, quedaría la propuesta en
    la bandeja (molesto, no pérdida de datos); el orden alta→borrado evita perder el evento.
    """
    publicacion_id = request.path_params["publicacion_id"]
    autor = autor_de_peticion(request)
    if not autor or not autor.get("id"):
        return JSONResponse({"error": "Necesitas iniciar sesión."}, status_code=401)
    actual = repos.obtener_publicacion(publicacion_id)
    if actual is None:
        return JSONResponse({"error": "Esa propuesta ya no existe."}, status_code=404)
    es_propuesta = (
        (actual.get("clase") or "") == CLASE_TAREA
        and bool((actual.get("fecha_objetivo") or "").strip())
        and not (actual.get("evento_id") or "").strip()
    )
    if not es_propuesta:
        return JSONResponse(
            {"error": "Solo una tarea con fecha (aún sin calendario) se puede aceptar al calendario."},
            status_code=409,
        )
    evento = repos.crear_evento_rota(
        actual.get("titulo") or "Evento",
        fecha=(actual.get("fecha_objetivo") or "").strip(),
        hora=(actual.get("hora_objetivo") or "").strip(),
        contenido=actual.get("descripcion") or "",
        prioridad=actual.get("prioridad") or "media",
        marca=actual.get("marca") or "",
    )
    # Consumir la propuesta: ya vive como evento del calendario (no la dejamos duplicada en el tablero).
    repos.borrar_publicacion(publicacion_id)
    return JSONResponse({"aceptada": True, "evento": evento})


def _rol_cobertura(valor: object) -> tuple[str | None, bool]:
    """Valida el ROL de cobertura (campo `formato`) que manda el cliente en cubrir-evento.

    Ausente/"" -> (None, True): sin rol explícito (RETROCOMPATIBLE; comportamiento previo).
    Un rol de `ROLES_COBERTURA` (foto/video/texto/live) -> (rol_normalizado, True). Cualquier
    otra cosa -> (None, False) = 400. No se pasa por `redes.normalizar_formato` a propósito:
    ese normalizador es del pipeline de publicación y coaccionaría 'texto'/'live' a 'foto'.
    """
    if valor in (None, ""):
        return None, True
    if isinstance(valor, str) and valor.strip().lower() in ROLES_COBERTURA:
        return valor.strip().lower(), True
    return None, False


async def cubrir_evento(request: Request) -> Response:
    """POST /api/publicaciones/cubrir-evento {evento_id, responsable_id?, formato?}: registra la
    COBERTURA de un evento de la rota, opcionalmente en un ROL concreto.

    La lista de Tareas muestra TODOS los eventos a cubrir (auto-rellenados desde Fuentes); un
    evento «por cubrir» pasa a tener dueño aquí, mediante una tarea (clase='tarea') enlazada
    por `evento_id`. MULTI-COBERTURA por ROLES: el `formato` opcional es el rol del cubridor
    (foto/video/texto/live; reusa el campo existente, sin migración). La clave find-or-create
    es (evento_id, persona, ROL): con rol, una persona puede llevar VARIOS roles y dos personas
    roles distintos sin solaparse; SIN rol (retrocompat) casa con CUALQUIER cobertura suya del
    evento. Nunca 409. Sin `responsable_id` (o el propio) = me apunto yo; con otro
    `responsable_id` (solo admin) = el manager apunta a esa persona y se le avisa in-app.
    """
    autor = autor_de_peticion(request)
    if not autor or not autor.get("id"):
        return JSONResponse({"error": "Necesitas iniciar sesión."}, status_code=401)
    datos = await leer_json(request)
    evento_id = datos.get("evento_id")
    if not isinstance(evento_id, str) or not evento_id.strip():
        return JSONResponse({"error": "Falta el evento a cubrir."}, status_code=400)
    evento = repos.obtener_evento_rota(evento_id)
    if evento is None:
        return JSONResponse({"error": "Ese evento ya no existe."}, status_code=404)

    rol, rol_ok = _rol_cobertura(datos.get("formato"))
    if not rol_ok:
        return JSONResponse({"error": "Rol de cobertura inválido."}, status_code=400)

    # ¿A quién? Sin responsable_id (o el mío) = me la cojo yo; con OTRO = el manager asigna.
    destino = datos.get("responsable_id")
    asignar_a_otro = isinstance(destino, str) and bool(destino) and destino != autor["id"]
    if asignar_a_otro and not es_admin(request):
        return JSONResponse(
            {"error": "Solo el responsable de la lista puede asignar a otra persona."},
            status_code=403,
        )
    if isinstance(destino, str) and destino:
        responsable, valido = _resolver_responsable(destino)
        if not valido or responsable is None:
            return JSONResponse(
                {"error": "El responsable no es un usuario válido."}, status_code=400
            )
    else:
        responsable = {"id": autor["id"], "usuario": autor.get("usuario", "") or ""}

    # find-or-create de la tarea de cobertura de ESTA persona en ESTE rol (idempotente por
    # (evento_id, responsable, formato/ROL)). Con rol explícito casa solo con la cobertura suya
    # del MISMO rol (así puede sumar otro rol distinto sin pisar el anterior); sin rol casa con
    # CUALQUIER cobertura suya del evento (retrocompat). La tarea nace YA con dueño. Varias
    # tareas del mismo evento = multi-cobertura: cubrir un evento que ya cubre otro AÑADE
    # cubridor, no es 409. No copia datos muertos del evento más allá de lo mínimo.
    mias = repos.listar_publicacion(
        clase=CLASE_TAREA, evento_id=evento_id, responsable_id=responsable["id"]
    )
    coincidentes = (
        [m for m in mias if (m.get("formato") or "") == rol] if rol is not None else mias
    )
    creada = not coincidentes
    if coincidentes:
        item = coincidentes[0]
    else:
        item = repos.crear_publicacion(
            clase=CLASE_TAREA,
            titulo=evento.get("titulo") or "Cobertura",
            marca=evento.get("marca") or "",
            evento_id=evento_id,
            prioridad=evento.get("prioridad") or "media",
            fecha_objetivo=evento.get("fecha") or "",
            hora_objetivo=evento.get("hora") or "",
            autor=autor,
            responsable=responsable,
            formato=rol or redes.FORMATO_FOTO,
        )
        # `db.crear_publicacion` NORMALIZA el formato al catálogo de publicación (foto/video/
        # carrusel), así que 'texto'/'live' caerían a 'foto'. Aquí son ROLES de cobertura
        # (texto libre, columna `TEXT` sin CHECK): si la normalización los cambió, los re-fijamos
        # crudos con `actualizar_publicacion` (que NO normaliza). Solo afecta tareas de cobertura.
        if rol is not None and (item.get("formato") or "") != rol:
            item = repos.actualizar_publicacion(item["id"], {"formato": rol}) or item
    # Avisar SOLO cuando el manager acaba de apuntar a OTRA persona (no en self-claim ni en el
    # no-op idempotente de quien ya cubría).
    if asignar_a_otro and creada:
        notificaciones.tras_asignacion(item, autor)
    plataformas = repos.listar_piezas_fila(item["id"])
    etiquetas = repos.etiquetas_por_contenido().get(item["id"], [])
    return JSONResponse({"contenido": _contenido_a_dict(item, plataformas, etiquetas)})
