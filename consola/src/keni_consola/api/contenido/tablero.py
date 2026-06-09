"""Handlers del padre del tablero: listar, crear, actualizar y borrar un contenido.

El item de `contenido` es el padre del tablero; aquí viven el listado (con foco por
marca, filtros y catálogos) y el CRUD del item. Las filas por plataforma, etiquetas,
métricas, importación y puerta creativa viven en sus propios submódulos.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ...tiempo import hoy_utc
from ._comun import (
    _MAX_TEXTO,
    _MAX_TITULO,
    _RED_WEB,
    CLASES_CONTENIDO,
    ESTADOS_CONTENIDO,
    ESTADOS_CONTENIDO_PLATAFORMA,
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


def _catalogos() -> dict:
    """Catalogos para los selects del tablero."""
    return {
        "usuarios": _usuarios_asignables(),
        "marcas": [{"id": mid, "nombre": nombre} for mid, nombre in marcas.opciones()],
        "redes": [*redes.opciones(), {"id": _RED_WEB, "nombre": "Web", "limite": None}],
        "flujos": list(FLUJOS_CONTENIDO),
        "prioridades": list(PRIORIDADES_CONTENIDO),
        "estados_contenido": list(ESTADOS_CONTENIDO),
        "estados_plataforma": list(ESTADOS_CONTENIDO_PLATAFORMA),
        "eventos": _eventos_proximos(),
        # Solo etiquetas ACTIVAS para el selector; el catálogo completo vive en /api/etiquetas.
        "etiquetas": [_etiqueta_catalogo(e) for e in repos.listar_etiquetas(solo_activas=True)],
        # Variables `{...}` que el copy puede llevar y se autocompletan (placeholders).
        "variables": placeholders.catalogo(),
    }


async def listar(request: Request) -> Response:
    """GET /api/contenido: tablero completo (items + plataformas) y catalogos.

    Filtros opcionales por query: `clase`, `flujo`, `marca` (workspace), `evento_id`
    (cobertura de un evento de la rota), `responsable_id`, `estado`, `desde`, `hasta`
    (por `fecha_objetivo`), `etiqueta` (id de una etiqueta).
    """
    q = request.query_params
    items = repos.listar_contenido(
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
    # Es siempre sobreescribible: con `?marca=` (cualquiera) se ve esa marca. `listar_contenido`
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
    # de `contenido_plataforma` (antes se traia la tabla ENTERA en cada GET del tablero).
    por_contenido: dict[str, list[dict]] = {}
    for plat in repos.listar_contenido_plataforma(marca=q.get("marca") or None):
        por_contenido.setdefault(plat["contenido_id"], []).append(plat)
    etiquetas_de = repos.etiquetas_por_contenido()
    return JSONResponse(
        {
            "contenidos": [
                _contenido_a_dict(
                    it, por_contenido.get(it["id"], []), etiquetas_de.get(it["id"], [])
                )
                for it in items
            ],
            "catalogos": _catalogos(),
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
    """POST /api/contenido: crea un item (padre) y, opcionalmente, sus filas por plataforma.

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
    if clase not in CLASES_CONTENIDO:
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

    # --- FASE 3 auto-operativa: auto-asignacion de responsable desde la rota -------------
    # Si no se fijo responsable, lo deriva la rota del dia para que la pieza no quede
    # huerfana (el equipo solo crea; el reparto es automatico). Override manual: si el
    # cliente mando `responsable_id`, se respeta y NO se toca. Degrada a None sin romper.
    # [MERGE] bloque propio y autocontenido; no toca la validacion de arriba.
    if responsable is None and marca:
        responsable = auto_responsable.responsable_automatico(marca)
    # --- fin bloque auto-operativa -------------------------------------------------------

    # FORMATO de la pieza (foto|video): si se indica, DECIDE las redes destino
    # (`redes.redes_de_formato`: foto=3, video=5) en vez de la lista cruda `redes`. Vacío/
    # desconocido -> "foto" (el flujo automático). Lo normaliza `db.crear_contenido`.
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

    item = repos.crear_contenido(
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
            repos.crear_contenido_plataforma(
                contenido_id=item["id"], red=red, falta_video=es_video
            )
    else:
        for red in dict.fromkeys(redes_iniciales):
            repos.crear_contenido_plataforma(contenido_id=item["id"], red=red)
    for etiqueta_id in dict.fromkeys(etiquetas_iniciales):
        repos.asignar_etiqueta(item["id"], etiqueta_id)
    plataformas = repos.listar_contenido_plataforma(item["id"])
    return JSONResponse(
        {"contenido": _contenido_a_dict(item, plataformas, list(dict.fromkeys(etiquetas_iniciales)))}
    )


async def actualizar(request: Request) -> Response:
    """PATCH /api/contenido/{id}: edita campos del padre (todos opcionales)."""
    contenido_id = request.path_params["contenido_id"]
    actual = repos.obtener_contenido(contenido_id)
    if actual is None:
        return JSONResponse({"error": "Ese contenido ya no existe."}, status_code=404)
    datos = await leer_json(request)
    campos: dict[str, object] = {}

    if "estado" in datos:
        if datos["estado"] not in ESTADOS_CONTENIDO:
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
        # multidisciplinar y cubre cualquier marca): la marca es un foco, no un cerrojo.
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
        campos["responsable_id"] = responsable["id"] if responsable else ""
        campos["responsable_nombre"] = responsable["usuario"] if responsable else ""
    for clave in ("titulo", "descripcion", "programa", "fecha_objetivo", "hora_objetivo", "fecha_entrega", "notas"):
        if clave in datos:
            v = datos.get(clave)
            campos[clave] = v.strip()[:_MAX_TEXTO] if isinstance(v, str) else ""

    if not campos:
        return JSONResponse({"error": "Indica algún campo a actualizar."}, status_code=400)

    formato_anterior = redes.normalizar_formato(actual.get("formato"))
    item = repos.actualizar_contenido(contenido_id, campos)
    if item is None:
        return JSONResponse({"error": "Ese contenido ya no existe."}, status_code=404)

    # FLIP de formato: reajusta las redes destino + el checklist (falta_video/falta_imagen) sin
    # perder trabajo. Solo si el formato CAMBIÓ realmente. El resumen viaja al cliente para avisar.
    ajuste: dict[str, list[str]] | None = None
    if formato_nuevo is not None and formato_nuevo != formato_anterior:
        ajuste = repos.ajustar_plataformas_por_formato(contenido_id, formato_nuevo)

    plataformas = repos.listar_contenido_plataforma(contenido_id)
    etiquetas = repos.etiquetas_por_contenido().get(contenido_id, [])
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
    contenido_id = request.path_params["contenido_id"]
    if not repos.borrar_contenido(contenido_id):
        return JSONResponse({"error": "Ese contenido ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Contenido borrado."})
