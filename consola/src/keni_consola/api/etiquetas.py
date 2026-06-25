"""API de ETIQUETAS editoriales del tablero (ola "organizacion").

Una etiqueta clasifica transversalmente las piezas del tablero de contenido por un EJE
(`clase`): una CAMPAÑA ("Mundial 2026"), una CATEGORÍA/sección editorial ("futbol") o un
TIPO de formato ("reel", "nota"). Es N:M con `contenido` (una pieza puede llevar varias).

WORKSPACES / MULTIMARCA: cada etiqueta puede ACOTARSE a una marca (`marca`) — así UnoTV
y Claro Sports tienen sus propias campañas/categorías sin pisarse — o ser GLOBAL
(`marca = ''`, visible en todas). El equipo es compartido; lo que aísla cada workspace es
la marca de las piezas y de sus etiquetas. El selector de etiquetas del tablero pide las
de la marca activa + las globales.

La asignación de etiquetas a un contenido vive en `api/publicaciones.py` (mismo recurso padre);
aquí se gestiona el CATÁLOGO de etiquetas (crear/editar/borrar).

SEGURIDAD:
  - Multiusuario via middleware (sesión o token). Tablero compartido (como Tareas).
  - `clase` debe ser del catálogo (`estados.CLASES_ETIQUETA`); `marca`, si llega, del
    catálogo de marcas (`consola.marcas`) o vacía (global). `color` se repara a un token
    hex corto. Unicidad por (nombre, clase, marca). Nada se confía del cliente.
  - SQL parametrizado en `repos`/`db`.

CONCURRENCIA: los handlers son `async` pero el acceso a Postgres (`repos`) es síncrono;
toda lectura/escritura de BD va en `run_in_threadpool` para no bloquear el event loop.
La validación pura (sin BD) se queda en el handler; el helper síncrono concentra el
trabajo de BD en una sola unidad por petición (conexión adquirida y soltada en el hilo).
"""

from __future__ import annotations

import re

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import marcas, repos
from ..bootstrap_categorias import slug_hashtag
from .._http_json import leer_json
from ..estados import (
    CADENCIA_LINEA_DEFECTO,
    CADENCIAS_LINEA,
    CLASE_ETIQUETA_DEFECTO,
    CLASES_ETIQUETA,
)

_MAX_NOMBRE = 60
# Color como token hex (#rgb o #rrggbb). Vacío = sin color (la UI elige uno por clase).
_RE_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _etiqueta_a_dict(et: dict) -> dict:
    """Serializa una etiqueta añadiendo el nombre legible de su marca (o '' si global)."""
    return {
        **et,
        "marca_nombre": marcas.etiqueta_de(et["marca"]) if et.get("marca") else "",
    }


def _validar_marca(marca: object) -> tuple[str | None, str | None]:
    """'' (global) es válido; cualquier otra debe ser una marca del catálogo."""
    if marca in (None, ""):
        return "", None
    if not isinstance(marca, str) or not marcas.es_marca(marca):
        return None, "Marca no permitida."
    return marca, None


def _validar_color(color: object) -> str:
    if isinstance(color, str) and _RE_COLOR.match(color.strip()):
        return color.strip().lower()
    return ""


_MAX_GRUPO = 40


def _normalizar_grupo(valor: object) -> str:
    """Grupo de líneas (clase `categoria`): texto libre recortado. '' = línea plana (sin grupo)."""
    return valor.strip()[:_MAX_GRUPO] if isinstance(valor, str) else ""


def _validar_cadencia(valor: object) -> str:
    """Cadencia de la línea: una de `CADENCIAS_LINEA`; cualquier otra cae al defecto ('normal')."""
    c = valor.strip().lower() if isinstance(valor, str) else ""
    return c if c in CADENCIAS_LINEA else CADENCIA_LINEA_DEFECTO


_MAX_KEYWORDS = 400


def _normalizar_keywords(valor: object) -> str:
    """CSV de palabras clave para auto-etiquetar (líneas/orígenes): minúsculas, sin
    duplicados, recortado. Solo aplica de verdad a clases `categoria` y `origen`, pero se
    acepta en cualquiera sin romper nada."""
    if not isinstance(valor, str):
        return ""
    vistas: list[str] = []
    for kw in valor.split(","):
        k = kw.strip().lower()
        if k and k not in vistas:
            vistas.append(k)
    return ", ".join(vistas)[:_MAX_KEYWORDS]


_MAX_HASHTAGS = 400
# Lo que NO es carácter de palabra (acentos/dígitos incluidos bajo UNICODE) se quita del tag.
_RE_TAG_NO_PALABRA = re.compile(r"[^\w]", re.UNICODE)


def _normalizar_hashtags(valor: object) -> str:
    """CSV de hashtags propios de la línea/estrategia, SIN el '#' (se añade al inyectar).

    Cada tag se repara a un token de palabra (sin espacios ni símbolos: «Mundial 2026» →
    «Mundial2026»), se admite un '#' inicial opcional, se deduplica case-insensitive y se
    PRESERVA el casing (los hashtags se estilizan: #Nacional, #Finanzas). Acepta separadores
    por coma o espacio. Se inyectan al final del copy de las piezas de esta línea."""
    if not isinstance(valor, str):
        return ""
    vistas: list[str] = []
    claves: set[str] = set()
    for crudo in re.split(r"[,\s]+", valor):
        tag = _RE_TAG_NO_PALABRA.sub("", crudo.lstrip("#"))
        if tag and tag.lower() not in claves:
            claves.add(tag.lower())
            vistas.append(tag)
    return ", ".join(vistas)[:_MAX_HASHTAGS]


def _validar_ttl_dias(valor: object) -> int:
    """ttl_dias: entero >= 0. 0 = sin caducidad / evergreen. Default 0."""
    try:
        v = int(valor)  # type: ignore[arg-type]
        return max(0, v)
    except (TypeError, ValueError):
        return 0


def _listar(marca: str | None, clase: str | None, solo_activas: bool) -> dict:
    etiquetas = repos.listar_etiquetas(marca=marca, clase=clase, solo_activas=solo_activas)
    return {
        "etiquetas": [_etiqueta_a_dict(e) for e in etiquetas],
        "clases": list(CLASES_ETIQUETA),
        "marcas": [{"id": mid, "nombre": nombre} for mid, nombre in marcas.opciones()],
    }


async def listar(request: Request) -> Response:
    """GET /api/etiquetas: catálogo de etiquetas.

    Filtros opcionales: `marca` (incluye las de esa marca Y las globales), `clase`,
    `activas` ("1" para excluir las ocultas).
    """
    q = request.query_params
    cuerpo = await run_in_threadpool(
        _listar,
        q.get("marca") if "marca" in q else None,
        q.get("clase") or None,
        q.get("activas") == "1",
    )
    return JSONResponse(cuerpo)


def _crear(
    *,
    nombre: str,
    clase: str,
    marca: str,
    color: str,
    keywords: str,
    hashtags: str,
    ttl_dias: int,
    es_evergreen: bool,
    grupo: str,
    cadencia: str,
) -> tuple[int, dict]:
    existente = repos.obtener_etiqueta_por_nombre(nombre, clase, marca)
    if existente is not None:
        if existente["activo"]:
            return 409, {"error": "Ya existe una etiqueta con ese nombre."}
        # Quitar una etiqueta (la ×) la OCULTA (activo=False), no la borra, para conservar el
        # histórico de las piezas que ya clasificó. Re-añadir el mismo nombre la resucita en su
        # sitio (con sus keywords/hashtag previos) en vez de chocar con la copia oculta.
        etiqueta = repos.actualizar_etiqueta(existente["id"], {"activo": True})
        return 200, {"etiqueta": _etiqueta_a_dict(etiqueta)}
    # LÍNEA = hashtag (1:1, línea = hueco de programación = hashtag): el hashtag de una línea se
    # DERIVA del nombre, no es un campo libre. Para campañas/otras clases lo edita el equipo.
    if clase == "categoria":
        hashtags = slug_hashtag(nombre)
    etiqueta = repos.crear_etiqueta(
        nombre=nombre,
        clase=clase,
        marca=marca,
        color=color,
        keywords=keywords,
        hashtags=hashtags,
        ttl_dias=ttl_dias,
        es_evergreen=es_evergreen,
        grupo=grupo,
        cadencia=cadencia,
    )
    return 200, {"etiqueta": _etiqueta_a_dict(etiqueta)}


async def crear(request: Request) -> Response:
    """POST /api/etiquetas: crea una etiqueta. Cuerpo: `nombre` (obligatorio), `clase`,
    `marca` ('' = global), `color`, `keywords`, `hashtags` (CSV sin '#'), `ttl_dias` (int,
    def 0), `es_evergreen` (bool, def false)."""
    datos = await leer_json(request)
    nombre = datos.get("nombre")
    if not isinstance(nombre, str) or not nombre.strip():
        return JSONResponse({"error": "La etiqueta necesita un nombre."}, status_code=400)
    nombre = nombre.strip()[:_MAX_NOMBRE]

    clase = datos.get("clase", CLASE_ETIQUETA_DEFECTO) or CLASE_ETIQUETA_DEFECTO
    if clase not in CLASES_ETIQUETA:
        return JSONResponse({"error": "Tipo de etiqueta inválido."}, status_code=400)

    marca, err = _validar_marca(datos.get("marca"))
    if err:
        return JSONResponse({"error": err}, status_code=400)

    status, cuerpo = await run_in_threadpool(
        _crear,
        nombre=nombre,
        clase=clase,
        marca=marca,
        color=_validar_color(datos.get("color")),
        keywords=_normalizar_keywords(datos.get("keywords")),
        hashtags=_normalizar_hashtags(datos.get("hashtags")),
        ttl_dias=_validar_ttl_dias(datos.get("ttl_dias", 0)),
        es_evergreen=bool(datos.get("es_evergreen", False)),
        grupo=_normalizar_grupo(datos.get("grupo")),
        cadencia=_validar_cadencia(datos.get("cadencia", CADENCIA_LINEA_DEFECTO)),
    )
    return JSONResponse(cuerpo, status_code=status)


def _actualizar(etiqueta_id: str, datos: dict) -> tuple[int, dict]:
    actual = repos.obtener_etiqueta(etiqueta_id)
    if actual is None:
        return 404, {"error": "Esa etiqueta ya no existe."}
    campos: dict[str, object] = {}

    if "nombre" in datos:
        nombre = datos.get("nombre")
        if not isinstance(nombre, str) or not nombre.strip():
            return 400, {"error": "El nombre no puede quedar vacío."}
        campos["nombre"] = nombre.strip()[:_MAX_NOMBRE]
    if "clase" in datos:
        if datos["clase"] not in CLASES_ETIQUETA:
            return 400, {"error": "Tipo de etiqueta inválido."}
        campos["clase"] = datos["clase"]
    if "marca" in datos:
        marca, err = _validar_marca(datos.get("marca"))
        if err:
            return 400, {"error": err}
        campos["marca"] = marca
    if "color" in datos:
        campos["color"] = _validar_color(datos.get("color"))
    if "keywords" in datos:
        campos["keywords"] = _normalizar_keywords(datos.get("keywords"))
    if "hashtags" in datos:
        campos["hashtags"] = _normalizar_hashtags(datos.get("hashtags"))
    if "activo" in datos:
        campos["activo"] = bool(datos["activo"])
    if "ttl_dias" in datos:
        campos["ttl_dias"] = _validar_ttl_dias(datos.get("ttl_dias"))
    if "es_evergreen" in datos:
        campos["es_evergreen"] = bool(datos["es_evergreen"])
    if "grupo" in datos:
        campos["grupo"] = _normalizar_grupo(datos.get("grupo"))
    if "cadencia" in datos:
        campos["cadencia"] = _validar_cadencia(datos.get("cadencia"))

    if not campos:
        return 400, {"error": "Indica algún campo a actualizar."}

    # Revalida la unicidad si cambió algún campo del triplete (nombre, clase, marca).
    nombre_f = str(campos.get("nombre", actual["nombre"]))
    clase_f = str(campos.get("clase", actual["clase"]))
    marca_f = str(campos.get("marca", actual["marca"]))
    # LÍNEA = hashtag (1:1): el hashtag de una línea se DERIVA del nombre, no se edita a mano.
    # Lo refuerza en cada update (y lo re-sincroniza al renombrar), pisando lo que llegue en `datos`.
    if clase_f == "categoria":
        campos["hashtags"] = slug_hashtag(nombre_f)
    if repos.existe_etiqueta_nombre(nombre_f, clase_f, marca_f, excluir_id=etiqueta_id):
        return 409, {"error": "Ya existe una etiqueta con ese nombre."}

    etiqueta = repos.actualizar_etiqueta(etiqueta_id, campos)
    if etiqueta is None:
        return 404, {"error": "Esa etiqueta ya no existe."}
    return 200, {"etiqueta": _etiqueta_a_dict(etiqueta)}


async def actualizar(request: Request) -> Response:
    """PATCH /api/etiquetas/{id}: edita nombre/clase/marca/color/keywords/hashtags/activo/
    ttl_dias/es_evergreen (todos opcionales)."""
    etiqueta_id = request.path_params["etiqueta_id"]
    datos = await leer_json(request)
    status, cuerpo = await run_in_threadpool(_actualizar, etiqueta_id, datos)
    return JSONResponse(cuerpo, status_code=status)


def _borrar(etiqueta_id: str) -> tuple[int, dict]:
    if not repos.borrar_etiqueta(etiqueta_id):
        return 404, {"error": "Esa etiqueta ya no existe."}
    return 200, {"mensaje": "Etiqueta borrada."}


async def borrar(request: Request) -> Response:
    """DELETE /api/etiquetas/{id}: borra la etiqueta y sus asignaciones (cascada)."""
    etiqueta_id = request.path_params["etiqueta_id"]
    status, cuerpo = await run_in_threadpool(_borrar, etiqueta_id)
    return JSONResponse(cuerpo, status_code=status)


RUTAS = [
    Route("/api/etiquetas", listar, methods=["GET"]),
    Route("/api/etiquetas", crear, methods=["POST"]),
    Route("/api/etiquetas/{etiqueta_id}", actualizar, methods=["PATCH"]),
    Route("/api/etiquetas/{etiqueta_id}", borrar, methods=["DELETE"]),
]
