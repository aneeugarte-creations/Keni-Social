"""API del TABLERO de contenido unificado (herramienta de community manager).

Un item de `contenido` es el padre del tablero: lo IMPORTANTE del dia, contenido EVERGREEN,
cobertura de un EVENTO previsto, o una TAREA libre del equipo (relevo/recado). Cada contenido
publicable lleva N filas `contenido_plataforma` (una por red) con su propio estado y checklist
"falta copy / imagen / revision / publicar".

El tablero es UNICO y compartido (como Tareas): todo usuario autenticado lo ve y lo edita.

SEGURIDAD:
  - Multiusuario via middleware (sesion o token); `autor`/`responsable` se atribuyen al usuario.
  - `marca` debe ser del catalogo (`consola.marcas`); `red` una red canonica (`consola.redes`)
    o el canal extra "web". `evento_id`, si llega, debe existir en la rota. El RESPONSABLE
    solo puede ser un usuario REAL. Nada se confia del cliente.
  - SQL parametrizado en `repos`/`db` (nunca f-strings con datos).
"""

from __future__ import annotations

from datetime import date

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import auth, marcas, metricas_pieza, redes, repos
from .._http_json import leer_json
from ..estados import (
    CLASES_CONTENIDO,
    ESTADOS_CONTENIDO,
    ESTADOS_CONTENIDO_PLATAFORMA,
    FLUJOS_CONTENIDO,
    PRIORIDADES_CONTENIDO,
)
from ..seguridad import autor_de_peticion

# Canal extra del tablero que NO es una red social del catalogo (no entra en Metricool):
# "web" cubre la nota en el sitio. Se admite como `red` de una fila por plataforma.
_RED_WEB = "web"

# Estados terminales para los que un deadline vencido ya no es relevante.
_ESTADOS_CERRADOS = ("publicado", "hecha")

_MAX_TITULO = 300
_MAX_TEXTO = 8000


def _orden_red(red: str) -> int:
    """Indice de orden canonico de una red (las del catalogo primero, "web"/otros al final)."""
    ids = redes.ids()
    return ids.index(red) if red in ids else len(ids)


def _red_valida(red: str) -> bool:
    return redes.es_red(red) or red == _RED_WEB


def _red_nombre(red: str) -> str:
    return "Web" if red == _RED_WEB else redes.nombre_por_id(red)


def _usuarios_asignables() -> list[dict[str, str]]:
    """Usuarios candidatos a RESPONSABLE: solo los que entran en la rota (`cobertura`).

    Misma regla que el tablero de tareas: un contenido lo asume quien hace coberturas.
    """
    return [
        {"id": u["id"], "usuario": u["usuario"]}
        for u in auth.listar_usuarios()
        if u.get("cobertura")
    ]


def _resolver_responsable(
    responsable_id: object,
) -> tuple[dict[str, str] | None, bool]:
    """Resuelve un `responsable_id` del cliente a `{"id","usuario"}`. Ver api/tareas."""
    if responsable_id in (None, ""):
        return None, True
    if not isinstance(responsable_id, str):
        return None, False
    usuario = auth.obtener_usuario_por_id(responsable_id)
    if usuario is None:
        return None, False
    return {"id": usuario["id"], "usuario": usuario["usuario"]}, True


def _plataforma_a_dict(plat: dict) -> dict:
    """Serializa una fila por plataforma anadiendo el nombre legible de la red."""
    return {**plat, "red_nombre": _red_nombre(plat.get("red", ""))}


def _contenido_a_dict(item: dict, plataformas: list[dict]) -> dict:
    """Serializa un item del tablero con sus plataformas (ordenadas) y `vencido` derivado."""
    hoy = date.today().isoformat()
    entrega = item.get("fecha_entrega") or ""
    vencido = bool(
        entrega and entrega < hoy and item.get("estado") not in _ESTADOS_CERRADOS
    )
    plats = sorted(plataformas, key=lambda p: (_orden_red(p.get("red", "")), p.get("creado", "")))
    return {
        **item,
        "marca_nombre": marcas.etiqueta_de(item["marca"]) if item.get("marca") else "",
        "vencido": vencido,
        "plataformas": [_plataforma_a_dict(p) for p in plats],
    }


def _eventos_proximos() -> list[dict]:
    """Eventos de la rota desde hoy en adelante (para atar un contenido a un evento)."""
    eventos = repos.listar_eventos_rota(desde=date.today().isoformat())
    return [
        {
            "id": e["id"],
            "titulo": e.get("titulo", ""),
            "fecha": e.get("fecha", ""),
            "hora": e.get("hora", ""),
        }
        for e in eventos
    ]


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
    }


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #


async def listar(request: Request) -> Response:
    """GET /api/contenido: tablero completo (items + plataformas) y catalogos.

    Filtros opcionales por query: `clase`, `flujo`, `marca`, `responsable_id`, `estado`,
    `desde`, `hasta` (por `fecha_objetivo`).
    """
    q = request.query_params
    items = repos.listar_contenido(
        clase=q.get("clase") or None,
        flujo=q.get("flujo") or None,
        marca=q.get("marca") or None,
        responsable_id=q.get("responsable_id") if "responsable_id" in q else None,
        estado=q.get("estado") or None,
        desde=q.get("desde") or None,
        hasta=q.get("hasta") or None,
    )
    # Una sola lectura de todas las plataformas, agrupadas por contenido (evita N consultas).
    por_contenido: dict[str, list[dict]] = {}
    for plat in repos.listar_contenido_plataforma():
        por_contenido.setdefault(plat["contenido_id"], []).append(plat)
    return JSONResponse(
        {
            "contenidos": [
                _contenido_a_dict(it, por_contenido.get(it["id"], [])) for it in items
            ],
            "catalogos": _catalogos(),
        }
    )


def _validar_marca(marca: object) -> tuple[str | None, str | None]:
    if marca in (None, ""):
        return "", None
    if not isinstance(marca, str) or not marcas.es_marca(marca):
        return None, "Marca no permitida."
    return marca, None


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

    redes_iniciales = datos.get("redes", [])
    if not isinstance(redes_iniciales, list):
        redes_iniciales = []
    redes_iniciales = [r for r in redes_iniciales if isinstance(r, str)]
    if any(not _red_valida(r) for r in redes_iniciales):
        return JSONResponse({"error": "Alguna red no es válida."}, status_code=400)

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
    )
    # Quita duplicados conservando el orden de llegada.
    for red in dict.fromkeys(redes_iniciales):
        repos.crear_contenido_plataforma(contenido_id=item["id"], red=red)
    plataformas = repos.listar_contenido_plataforma(item["id"])
    return JSONResponse({"contenido": _contenido_a_dict(item, plataformas)})


async def actualizar(request: Request) -> Response:
    """PATCH /api/contenido/{id}: edita campos del padre (todos opcionales)."""
    contenido_id = request.path_params["contenido_id"]
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
    if "marca" in datos:
        marca, err = _validar_marca(datos.get("marca"))
        if err:
            return JSONResponse({"error": err}, status_code=400)
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

    item = repos.actualizar_contenido(contenido_id, campos)
    if item is None:
        return JSONResponse({"error": "Ese contenido ya no existe."}, status_code=404)
    plataformas = repos.listar_contenido_plataforma(contenido_id)
    return JSONResponse({"contenido": _contenido_a_dict(item, plataformas)})


async def borrar(request: Request) -> Response:
    contenido_id = request.path_params["contenido_id"]
    if not repos.borrar_contenido(contenido_id):
        return JSONResponse({"error": "Ese contenido ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Contenido borrado."})


async def agregar_plataforma(request: Request) -> Response:
    """POST /api/contenido/{id}/plataformas: anade una fila por red al contenido."""
    contenido_id = request.path_params["contenido_id"]
    if repos.obtener_contenido(contenido_id) is None:
        return JSONResponse({"error": "Ese contenido ya no existe."}, status_code=404)
    datos = await leer_json(request)
    red = datos.get("red")
    if not isinstance(red, str) or not _red_valida(red):
        return JSONResponse({"error": "Red no válida."}, status_code=400)
    plat = repos.crear_contenido_plataforma(contenido_id=contenido_id, red=red)
    return JSONResponse({"plataforma": _plataforma_a_dict(plat)})


async def actualizar_plataforma(request: Request) -> Response:
    """PATCH /api/contenido/{id}/plataformas/{plataforma_id}: estado/checklist/copy/...."""
    plataforma_id = request.path_params["plataforma_id"]
    datos = await leer_json(request)
    campos: dict[str, object] = {}

    if "estado" in datos:
        if datos["estado"] not in ESTADOS_CONTENIDO_PLATAFORMA:
            return JSONResponse({"error": "Estado de plataforma inválido."}, status_code=400)
        campos["estado"] = datos["estado"]
    for flag in ("falta_copy", "falta_imagen", "falta_revision", "falta_publicar", "evergreen"):
        if flag in datos:
            campos[flag] = bool(datos[flag])
    for clave in ("copy", "imagen", "enlace", "fecha_programada", "hora_post", "veredicto"):
        if clave in datos:
            v = datos.get(clave)
            campos[clave] = v.strip()[:_MAX_TEXTO] if isinstance(v, str) else ""

    if not campos:
        return JSONResponse({"error": "Indica algún campo a actualizar."}, status_code=400)

    plat = repos.actualizar_contenido_plataforma(plataforma_id, campos)
    if plat is None:
        return JSONResponse({"error": "Esa plataforma ya no existe."}, status_code=404)
    return JSONResponse({"plataforma": _plataforma_a_dict(plat)})


async def borrar_plataforma(request: Request) -> Response:
    plataforma_id = request.path_params["plataforma_id"]
    if not repos.borrar_contenido_plataforma(plataforma_id):
        return JSONResponse({"error": "Esa plataforma ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Plataforma borrada."})


async def desde_radar(request: Request) -> Response:
    """POST /api/contenido/desde-radar: promueve un tema del Radar/Parrilla al tablero.

    El Radar es efimero (no persiste): el cliente manda el tema elegido. Se crea un
    contenido `flujo='importante'` con `origen='radar'`, prioridad opcional y, si se indican,
    sus filas por plataforma.
    """
    datos = await leer_json(request)
    titulo = datos.get("titulo")
    if not isinstance(titulo, str) or not titulo.strip():
        return JSONResponse({"error": "El tema necesita un título."}, status_code=400)

    prioridad = datos.get("prioridad", "media") or "media"
    if prioridad not in PRIORIDADES_CONTENIDO:
        prioridad = "media"

    marca, err = _validar_marca(datos.get("marca"))
    if err:
        return JSONResponse({"error": err}, status_code=400)

    redes_iniciales = datos.get("redes", [])
    if not isinstance(redes_iniciales, list):
        redes_iniciales = []
    redes_iniciales = [r for r in redes_iniciales if isinstance(r, str) and _red_valida(r)]

    descripcion = datos.get("descripcion", "")
    if not isinstance(descripcion, str):
        descripcion = ""

    item = repos.crear_contenido(
        clase="contenido",
        flujo="importante",
        titulo=titulo.strip()[:_MAX_TITULO],
        descripcion=descripcion.strip()[:_MAX_TEXTO],
        marca=marca,
        prioridad=prioridad,
        fecha_objetivo=date.today().isoformat(),
        autor=autor_de_peticion(request),
        origen="radar",
    )
    for red in dict.fromkeys(redes_iniciales):
        repos.crear_contenido_plataforma(contenido_id=item["id"], red=red)
    plataformas = repos.listar_contenido_plataforma(item["id"])
    return JSONResponse({"contenido": _contenido_a_dict(item, plataformas)})


async def metricas(request: Request) -> Response:
    """GET /api/contenido/metricas: rendimiento REAL por pieza publicada (Metricool).

    Para cada fila por plataforma del tablero que tiene `id_post_metricool`, devuelve su
    rendimiento (visualizaciones/interacciones/engagement) leido de la fuente activa
    (Metricool de pago en prod; muestra en demo) y cacheado por pieza. La UI lo pinta en
    cada tarjeta. Las filas sin `id_post_metricool` se omiten (la UI no muestra nada).

    Forma: `{"metricas": {"<contenido_plataforma.id>": {<MetricaPieza>, generado_en}}}`.
    Acepta los mismos filtros que `GET /api/contenido` para acotar el universo.
    """
    q = request.query_params
    items = repos.listar_contenido(
        clase=q.get("clase") or None,
        flujo=q.get("flujo") or None,
        marca=q.get("marca") or None,
        responsable_id=q.get("responsable_id") if "responsable_id" in q else None,
        estado=q.get("estado") or None,
        desde=q.get("desde") or None,
        hasta=q.get("hasta") or None,
    )
    por_contenido: dict[str, list[dict]] = {}
    for plat in repos.listar_contenido_plataforma():
        por_contenido.setdefault(plat["contenido_id"], []).append(plat)
    contenidos = [
        {"marca": it.get("marca", ""), "plataformas": por_contenido.get(it["id"], [])}
        for it in items
    ]
    return JSONResponse({"metricas": metricas_pieza.rendimiento_de_tablero(contenidos)})


RUTAS = [
    Route("/api/contenido", listar, methods=["GET"]),
    Route("/api/contenido", crear, methods=["POST"]),
    Route("/api/contenido/metricas", metricas, methods=["GET"]),
    Route("/api/contenido/desde-radar", desde_radar, methods=["POST"]),
    Route("/api/contenido/{contenido_id}", actualizar, methods=["PATCH"]),
    Route("/api/contenido/{contenido_id}", borrar, methods=["DELETE"]),
    Route("/api/contenido/{contenido_id}/plataformas", agregar_plataforma, methods=["POST"]),
    Route(
        "/api/contenido/{contenido_id}/plataformas/{plataforma_id}",
        actualizar_plataforma,
        methods=["PATCH"],
    ),
    Route(
        "/api/contenido/{contenido_id}/plataformas/{plataforma_id}",
        borrar_plataforma,
        methods=["DELETE"],
    ),
]
