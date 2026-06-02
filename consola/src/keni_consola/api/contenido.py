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

from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import (
    auth,
    auto_responsable,
    autogen_copy,
    importador_calendario,
    marcas,
    metricas_pieza,
    redes,
    repos,
)
from .._http_json import leer_json
from ..dominio import asistente, estudio_imagen, eventos, placeholders
from ..estados import (
    CLASES_CONTENIDO,
    ESTADOS_CONTENIDO,
    ESTADOS_CONTENIDO_PLATAFORMA,
    FLUJOS_CONTENIDO,
    PRIORIDADES_CONTENIDO,
    TIPOS_CONTENIDO,
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


def _contenido_a_dict(
    item: dict, plataformas: list[dict], etiquetas: list[str] | None = None
) -> dict:
    """Serializa un item del tablero con sus plataformas (ordenadas), etiquetas y `vencido`."""
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
        "etiquetas": list(etiquetas or []),
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


# --------------------------------------------------------------------------- #
# Endpoints                                                                    #
# --------------------------------------------------------------------------- #


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
    # Filtro por etiqueta: acota a los contenidos que la llevan (una sola lectura del N:M).
    etiqueta_id = q.get("etiqueta") or None
    if etiqueta_id:
        con_etiqueta = repos.ids_contenido_con_etiqueta(etiqueta_id)
        items = [it for it in items if it["id"] in con_etiqueta]
    # Una sola lectura de todas las plataformas y etiquetas, agrupadas por contenido.
    por_contenido: dict[str, list[dict]] = {}
    for plat in repos.listar_contenido_plataforma():
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


def _validar_marca(marca: object) -> tuple[str | None, str | None]:
    if marca in (None, ""):
        return "", None
    if not isinstance(marca, str) or not marcas.es_marca(marca):
        return None, "Marca no permitida."
    return marca, None


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
    )
    # Quita duplicados conservando el orden de llegada.
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
    etiquetas = repos.etiquetas_por_contenido().get(contenido_id, [])
    return JSONResponse({"contenido": _contenido_a_dict(item, plataformas, etiquetas)})


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


# Estado de plataforma -> evento interno que se emite al ENTRAR en ese estado.
_EVENTO_POR_ESTADO: dict[str, str] = {
    "aprobado": "pieza.aprobada",
    "publicado": "pieza.publicada",
}


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
    for clave in (
        "copy",
        "imagen",
        "imagen_fuente",
        "enlace",
        "fecha_programada",
        "hora_post",
        "veredicto",
    ):
        if clave in datos:
            v = datos.get(clave)
            campos[clave] = v.strip()[:_MAX_TEXTO] if isinstance(v, str) else ""

    if not campos:
        return JSONResponse({"error": "Indica algún campo a actualizar."}, status_code=400)

    # Estado ANTERIOR (para emitir el evento solo en la TRANSICION, no en cada PATCH).
    previa = repos.obtener_contenido_plataforma(plataforma_id)
    estado_anterior = previa.get("estado") if previa else None

    plat = repos.actualizar_contenido_plataforma(plataforma_id, campos)
    if plat is None:
        return JSONResponse({"error": "Esa plataforma ya no existe."}, status_code=404)

    nuevo_estado = plat.get("estado")
    tipo_evento = _EVENTO_POR_ESTADO.get(nuevo_estado or "")
    if tipo_evento is not None and nuevo_estado != estado_anterior:
        padre = repos.obtener_contenido(plat.get("contenido_id", "")) or {}
        eventos.emitir(
            tipo_evento,
            {
                "contenido_id": plat.get("contenido_id", ""),
                "plataforma_id": plataforma_id,
                "red": plat.get("red", ""),
                "red_nombre": _red_nombre(plat.get("red", "")),
                "titulo": padre.get("titulo", ""),
                "marca": padre.get("marca", ""),
                "marca_nombre": marcas.etiqueta_de(padre["marca"]) if padre.get("marca") else "",
                "estado": nuevo_estado,
            },
            contenido_id=plat.get("contenido_id", ""),
            plataforma_id=plataforma_id,
        )
    return JSONResponse({"plataforma": _plataforma_a_dict(plat)})


async def adaptar_imagen(request: Request) -> Response:
    """POST /api/contenido/{contenido_id}/adaptar-imagen {imagen}.

    Genera una imagen ADAPTADA POR RED de forma DETERMINISTA y la asigna a cada plataforma de
    la pieza: para cada red recorta la `imagen` de origen al formato de esa red (16:9, 1:1,
    9:16...) y, si la marca tiene plantilla visual, la compone tras el marco de marca. Las
    plataformas cuya composición falle se omiten (no abortan el resto).
    -> `{plataformas, adaptadas}` | 400 | 404.
    """
    contenido_id = request.path_params["contenido_id"]
    item = repos.obtener_contenido(contenido_id)
    if item is None:
        return JSONResponse({"error": "Esa pieza ya no existe."}, status_code=404)

    datos = await leer_json(request)
    imagen = datos.get("imagen")
    if not isinstance(imagen, str) or not imagen.strip():
        return JSONResponse({"error": "Falta la imagen a adaptar."}, status_code=400)
    imagen = imagen.strip()

    plataformas = repos.listar_contenido_plataforma(contenido_id)
    if not plataformas:
        return JSONResponse(
            {"error": "La pieza no tiene plataformas a las que adaptar."}, status_code=400
        )

    marca = item.get("marca") or ""
    con_plantilla = estudio_imagen.marca_tiene_plantilla(marca)

    actualizadas: list[dict] = []
    for plat in plataformas:
        formato = estudio_imagen.formato_por_red(plat.get("red", ""))
        try:
            if con_plantilla:
                res = estudio_imagen.componer(imagen, marca=marca, formato=formato)
            else:
                res = estudio_imagen.editar(imagen, "recortar", {"formato": formato})
        except estudio_imagen.EstudioError:
            continue
        plat2 = repos.actualizar_contenido_plataforma(plat["id"], {"imagen": res["id"]})
        if plat2 is not None:
            actualizadas.append(_plataforma_a_dict(plat2))

    if not actualizadas:
        return JSONResponse(
            {"error": "No se pudo adaptar la imagen a ninguna red."}, status_code=400
        )

    return JSONResponse({"plataformas": actualizadas, "adaptadas": len(actualizadas)})


async def borrar_plataforma(request: Request) -> Response:
    plataforma_id = request.path_params["plataforma_id"]
    if not repos.borrar_contenido_plataforma(plataforma_id):
        return JSONResponse({"error": "Esa plataforma ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Plataforma borrada."})


async def asignar_etiqueta(request: Request) -> Response:
    """POST /api/contenido/{id}/etiquetas: asigna una etiqueta (`{"etiqueta_id": ...}`)."""
    contenido_id = request.path_params["contenido_id"]
    if repos.obtener_contenido(contenido_id) is None:
        return JSONResponse({"error": "Ese contenido ya no existe."}, status_code=404)
    datos = await leer_json(request)
    etiqueta_id = datos.get("etiqueta_id")
    if not isinstance(etiqueta_id, str) or not etiqueta_id:
        return JSONResponse({"error": "Falta la etiqueta."}, status_code=400)
    if repos.obtener_etiqueta(etiqueta_id) is None:
        return JSONResponse({"error": "Esa etiqueta ya no existe."}, status_code=404)
    repos.asignar_etiqueta(contenido_id, etiqueta_id)
    etiquetas = repos.etiquetas_por_contenido().get(contenido_id, [])
    return JSONResponse({"etiquetas": etiquetas})


async def quitar_etiqueta(request: Request) -> Response:
    """DELETE /api/contenido/{id}/etiquetas/{etiqueta_id}: quita una etiqueta del contenido."""
    contenido_id = request.path_params["contenido_id"]
    etiqueta_id = request.path_params["etiqueta_id"]
    if not repos.quitar_etiqueta(contenido_id, etiqueta_id):
        return JSONResponse({"error": "Esa etiqueta no estaba asignada."}, status_code=404)
    etiquetas = repos.etiquetas_por_contenido().get(contenido_id, [])
    return JSONResponse({"etiquetas": etiquetas})


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
        # El tema viene de una FUENTE (Radar), no de arte propio: tipo "fuente" (item E).
        tipo_contenido="fuente",
    )
    # Checklist "pendientes" (item E): cada plataforma nace con copy e imagen por hacer. Si
    # luego lanzamos generacion de copy en background, su borrador rellenara el copy (y la UI
    # marcara falta_copy=0); la imagen sigue manual (falta_imagen=1).
    for red in dict.fromkeys(redes_iniciales):
        repos.crear_contenido_plataforma(
            contenido_id=item["id"], red=red, falta_copy=True, falta_imagen=True
        )

    # Generacion de copy en SEGUNDO PLANO (item E), reusando el flujo del asistente/RSS
    # (`autogen_copy.lanzar_para_topic`): compone la nota desde el tema, infiere redes y
    # encola un `claude -p` cuyo borrador cuelga del tema. GATEADO por marca (sin marca no
    # hay voz) y por el flag `generar` del cuerpo (def True). Es BEST-EFFORT: si la skill o
    # la cola fallan, NO rompe la promocion (queda el copy manual como fallback).
    generar_copy = datos.get("generar", True)
    genero = False
    if marca and generar_copy:
        try:
            genero = autogen_copy.lanzar_para_topic(item) is not None
        except Exception:  # noqa: BLE001 -- la generacion es opcional; nunca tumba la promocion
            genero = False

    plataformas = repos.listar_contenido_plataforma(item["id"])
    return JSONResponse(
        {"contenido": _contenido_a_dict(item, plataformas), "copy_en_proceso": genero}
    )


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


# --------------------------------------------------------------------------- #
# Variables/placeholders en el copy ({marca}, {fecha}, {hashtags}, ...)         #
# --------------------------------------------------------------------------- #


async def previsualizar(request: Request) -> Response:
    """POST /api/contenido/{id}/preview: expande las variables `{...}` de un texto.

    Cuerpo JSON `{texto}`: devuelve `{preview}` con `{marca}`/`{fecha}`/`{hashtags}`/...
    ya sustituidas usando el contexto del contenido (marca, titulo, programa). Es la
    previsualizacion por plataforma del copy (no persiste nada). `{...}` desconocidas se
    dejan literales. 404 si el contenido no existe.
    """
    contenido_id = request.path_params["contenido_id"]
    item = repos.obtener_contenido(contenido_id)
    if item is None:
        return JSONResponse({"error": "Ese contenido ya no existe."}, status_code=404)
    datos = await leer_json(request)
    texto = datos.get("texto")
    if not isinstance(texto, str):
        texto = ""
    preview = placeholders.expandir_para_contenido(texto[:_MAX_TEXTO], item)
    return JSONResponse({"preview": preview})


# --------------------------------------------------------------------------- #
# Asistente IA del tablero (genera/resume/3 variantes reutilizando las skills)  #
# --------------------------------------------------------------------------- #


async def asistente_ia(request: Request) -> Response:
    """POST /api/contenido/{id}/asistente: lanza el asistente IA sobre un contenido.

    Cuerpo JSON `{modo, redes?}` (`modo` ∈ generar|variantes|resumir). Reutiliza la skill
    de copy y la pipeline de generacion: arma el brief del contenido (titulo+descripcion+
    notas), lanza un trabajo en segundo plano y responde `{generacion}` (estado
    "ejecutando"). El frontend sondea `GET /api/generaciones/{id}` y, al completarse, lee
    `resultado.piezas` para rellenar el `copy` de cada fila `contenido_plataforma`.

    Requiere que el contenido tenga MARCA (la voz de marca es el insumo de la skill) y al
    menos una red CANONICA en sus plataformas (el canal "web" no entra en las skills de
    copy). Si faltan, responde 400 con un mensaje en espanol.
    """
    contenido_id = request.path_params["contenido_id"]
    item = repos.obtener_contenido(contenido_id)
    if item is None:
        return JSONResponse({"error": "Ese contenido ya no existe."}, status_code=404)

    marca = item.get("marca", "") or ""
    if not marca or not marcas.es_marca(marca):
        return JSONResponse(
            {"error": "Asigna una marca al contenido para usar el asistente."},
            status_code=400,
        )
    datos = await leer_json(request)
    modo = datos.get("modo", "generar")
    if modo not in asistente.MODOS:
        return JSONResponse({"error": "Modo de asistente no válido."}, status_code=400)

    # Redes del cuerpo (si llegan) o, por defecto, las redes CANONICAS del contenido. El
    # canal "web" se descarta (las skills de copy trabajan sobre redes sociales).
    crudas = datos.get("redes")
    if isinstance(crudas, list):
        pedidas = [r for r in crudas if isinstance(r, str) and redes.es_red(r)]
    else:
        pedidas = [p["red"] for p in repos.listar_contenido_plataforma(contenido_id) if redes.es_red(p["red"])]
    redes_ids = [r for r in redes.ids() if r in set(pedidas)]
    if not redes_ids:
        return JSONResponse(
            {"error": "Añade al menos una red social al contenido para generar copy."},
            status_code=400,
        )

    gen = asistente.lanzar(
        modo=modo,
        marca=marca,
        titulo=item.get("titulo", "") or "",
        descripcion=item.get("descripcion", "") or "",
        notas=item.get("notas", "") or "",
        redes_ids=redes_ids,
        autor=autor_de_peticion(request),
    )
    return JSONResponse({"generacion": gen})


# Tope defensivo del archivo de calendario (un calendario real pesa KB, no MB).
_LIMITE_IMPORT = 5 * 1024 * 1024


def _fila_a_dict(fila: importador_calendario.FilaCalendario) -> dict:
    """Serializa una fila parseada para la previsualizacion del cliente."""
    return {
        "titulo": fila.titulo,
        "fecha": fila.fecha,
        "marca": fila.marca_id,
        "redes": fila.redes,
        "prioridad": fila.prioridad,
        "compromiso": fila.compromiso,
        "notas": fila.notas,
    }


async def importar(request: Request) -> Response:
    """POST /api/contenido/importar: sube un calendario (.xlsx/.csv) al tablero (multipart).

    Campos: `archivo` (obligatorio), `marca` (id canonico opcional, para filas sin marca),
    `previsualizar` ('1' => parsea y devuelve lo que entraria SIN escribir). Crea contenido
    `origen='import-calendario'`; las filas obligatorias se etiquetan `compromiso`.
    """
    try:
        form = await request.form()
    except Exception:  # noqa: BLE001 -- multipart malformado => mensaje claro, sin traza
        return JSONResponse({"error": "Formulario inválido."}, status_code=400)

    archivo = form.get("archivo")
    if not isinstance(archivo, UploadFile):
        return JSONResponse({"error": "Falta el archivo del calendario."}, status_code=400)
    data = await archivo.read()
    if not data:
        return JSONResponse({"error": "El archivo está vacío."}, status_code=400)
    if len(data) > _LIMITE_IMPORT:
        return JSONResponse({"error": "El archivo es demasiado grande."}, status_code=413)

    marca_defecto, err = _validar_marca(form.get("marca"))
    if err:
        return JSONResponse({"error": err}, status_code=400)

    # Camino RÁPIDO y determinista: el parser tabular para .xlsx/.csv bien formados.
    nombre = archivo.filename or ""
    try:
        filas, errores = importador_calendario.parsear(data, nombre=nombre)
    except Exception:  # noqa: BLE001 -- formato no tabular/ilegible: lo intentará Claude abajo
        filas, errores = [], []
    # Si el parser rígido no sacó nada (PDF, imagen, captura, Word, Excel con otra
    # estructura, cabeceras irreconocibles…), deja que Claude LEA el archivo y lo
    # interprete, sea cual sea el formato. Es síncrono (el usuario espera la importación).
    if not filas:
        filas, errores = importador_calendario.extraer_con_claude(data, nombre=nombre)

    if str(form.get("previsualizar") or "") in ("1", "true", "si", "sí"):
        return JSONResponse({
            "previsualizacion": True,
            "filas": [_fila_a_dict(f) for f in filas],
            "errores": errores,
        })

    resumen = importador_calendario.importar_a_tablero(
        filas, autor=autor_de_peticion(request), marca_defecto=marca_defecto or ""
    )
    return JSONResponse({
        "creados": len(resumen["creados"]),
        "omitidos": resumen["omitidos"],
        "errores": errores,
    })


RUTAS = [
    Route("/api/contenido", listar, methods=["GET"]),
    Route("/api/contenido", crear, methods=["POST"]),
    Route("/api/contenido/metricas", metricas, methods=["GET"]),
    Route("/api/contenido/desde-radar", desde_radar, methods=["POST"]),
    Route("/api/contenido/importar", importar, methods=["POST"]),
    Route("/api/contenido/{contenido_id}/preview", previsualizar, methods=["POST"]),
    Route("/api/contenido/{contenido_id}/asistente", asistente_ia, methods=["POST"]),
    Route("/api/contenido/{contenido_id}/adaptar-imagen", adaptar_imagen, methods=["POST"]),
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
    Route("/api/contenido/{contenido_id}/etiquetas", asignar_etiqueta, methods=["POST"]),
    Route(
        "/api/contenido/{contenido_id}/etiquetas/{etiqueta_id}",
        quitar_etiqueta,
        methods=["DELETE"],
    ),
]
