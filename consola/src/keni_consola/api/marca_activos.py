"""API Texto de ACTIVOS DE MARCA: el kit visual reutilizable de cada marca.

Generaliza `marca_assets.py` (que solo conocia logo/marca-agua/pleca como PNGs en disco) a un
catalogo en Postgres (`marca_activos`) + objetos en el almacen (S3/disco). Cada activo tiene un
`tipo` (logo | tipografia | arte | infografia | icono | paleta | fondo), un `objeto` (uuid+ext del
binario, salvo `paleta` que vive solo en `metadatos`), `metadatos` por tipo (p.ej. familia/peso de
una tipografia, lista de hex de una paleta) y `lineas` (ids de `etiquetas` clase=vertical que lo
etiquetan por linea editorial). El editor lo muestra agrupado por tipo y arrastra cada activo al
lienzo como una capa.

  - `GET    /api/marca-activos`        lista (filtros `?marca=&tipo=&linea=&q=`).
  - `POST   /api/marca-activos`        cataloga un objeto de media ya existente como activo.
  - `PATCH  /api/marca-activos/{id}`   edita metadatos del activo (no reasigna el binario).
  - `DELETE /api/marca-activos/{id}`   descataloga (con `?purgar=1` borra tambien el binario).

SEGURIDAD: `objeto` debe EXISTIR en el almacen; `marca` (si llega) del catalogo unico
(`consola.marcas`); `tipo` de la lista blanca. Errores en espanol, sin tracebacks. SQL
parametrizado en `repos`/`db`. Multiusuario por middleware (tablero compartido).
"""

from __future__ import annotations

import json
import logging

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import almacen_media, marcas, media, repos
from .._http_json import leer_json
from ..seguridad import autor_de_peticion

_log = logging.getLogger("keni_consola.marca_activos")

# Tipos de activo del kit de marca. `paleta` es el unico que puede no tener binario (vive en
# `metadatos.colores`); el resto referencia un `objeto` del almacen.
_TIPOS = ("logo", "tipografia", "arte", "infografia", "icono", "paleta", "fondo")
_TIPO_DEFECTO = "arte"
_TIPOS_SIN_OBJETO = ("paleta",)

_MAX_NOMBRE = 120
_MAX_LINEAS = 24
_MAX_METADATOS = 4000  # bytes del JSON serializado (defensa contra payloads gigantes)


def _validar_marca(marca: object) -> tuple[str | None, str | None]:
    """'' (global, compartido entre marcas) es valido; cualquier otra debe ser del catalogo."""
    if marca in (None, ""):
        return "", None
    if not isinstance(marca, str) or not marcas.es_marca(marca):
        return None, "Marca no permitida."
    return marca, None


def _normalizar_lineas(valor: object) -> list[str]:
    """Lista de ids de linea (etiquetas clase=vertical) saneada: strings no vacios, sin duplicados."""
    if not isinstance(valor, list):
        return []
    vistas: list[str] = []
    for item in valor:
        if not isinstance(item, str):
            continue
        et = item.strip()
        if et and et not in vistas:
            vistas.append(et)
        if len(vistas) >= _MAX_LINEAS:
            break
    return vistas


def _metadatos_json(valor: object) -> tuple[str | None, str | None]:
    """Serializa `metadatos` (dict) a JSON; '{}' si falta. Error si no es objeto o es enorme."""
    if valor in (None, ""):
        return "{}", None
    if not isinstance(valor, dict):
        return None, "Los metadatos deben ser un objeto."
    texto = json.dumps(valor, ensure_ascii=False)
    if len(texto.encode("utf-8")) > _MAX_METADATOS:
        return None, "Los metadatos son demasiado grandes."
    return texto, None


def _activo_a_dict(item: dict) -> dict:
    """Serializa un activo: metadatos/lineas como objeto/lista, url y nombre de marca."""
    try:
        meta = json.loads(item.get("metadatos") or "{}")
    except (ValueError, TypeError):
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    try:
        lineas = json.loads(item.get("lineas") or "[]")
    except (ValueError, TypeError):
        lineas = []
    if not isinstance(lineas, list):
        lineas = []
    objeto = item.get("objeto") or ""
    return {
        **item,
        "metadatos": meta,
        "lineas": [x for x in lineas if isinstance(x, str)],
        "url": f"/api/media/{objeto}" if objeto else "",
        "marca_nombre": marcas.etiqueta_de(item["marca"]) if item.get("marca") else "",
    }


def _coincide_busqueda(activo: dict, q: str) -> bool:
    """Coincidencia simple (substring) por nombre."""
    return q.lower() in (activo.get("nombre") or "").lower()


async def listar(request: Request) -> Response:
    """GET /api/marca-activos: activos catalogados (mas recientes primero).

    Filtros opcionales: `marca`, `tipo` (lista blanca), `linea` (id de etiqueta vertical) y `q`
    (substring por nombre, en memoria). Devuelve `{activos: [...]}`.
    """
    q = request.query_params
    activos = [
        _activo_a_dict(item)
        for item in repos.listar_marca_activos(
            marca=q.get("marca") or None,
            tipo=q.get("tipo") or None,
        )
    ]
    linea = (q.get("linea") or "").strip()
    if linea:
        activos = [a for a in activos if linea in a.get("lineas", [])]
    busqueda = (q.get("q") or "").strip()
    if busqueda:
        activos = [a for a in activos if _coincide_busqueda(a, busqueda)]
    return JSONResponse({"activos": activos})


async def crear(request: Request) -> Response:
    """POST /api/marca-activos: cataloga un activo de marca.

    Cuerpo: `tipo` (lista blanca), `marca` ('' = global), `nombre`, `objeto` (id de media;
    obligatorio salvo `tipo=paleta`), `metadatos` (objeto), `lineas` (ids de etiqueta vertical).
    -> `{activo}` | 400.
    """
    datos = await leer_json(request)
    if not isinstance(datos, dict):
        return JSONResponse({"error": "Cuerpo JSON inválido."}, status_code=400)

    tipo = datos.get("tipo") or _TIPO_DEFECTO
    if tipo not in _TIPOS:
        return JSONResponse({"error": "Tipo de activo no válido."}, status_code=400)

    objeto = (datos.get("objeto") or "").strip() if isinstance(datos.get("objeto"), str) else ""
    if tipo not in _TIPOS_SIN_OBJETO:
        if not objeto:
            return JSONResponse({"error": "Falta el archivo del activo."}, status_code=400)
        if media.leer_media(objeto) is None:
            return JSONResponse({"error": "Ese archivo no existe en el almacén."}, status_code=400)
        # Un activo de marca (logo/tipografía/pleca) es REUSABLE: lo promovemos a la carpeta
        # `logos/`. Así, al limpiar `fotos/` a mano, el logo (en otra carpeta) no se toca.
        objeto = almacen_media.promover_objeto(objeto, "logos")

    marca, err = _validar_marca(datos.get("marca"))
    if err:
        return JSONResponse({"error": err}, status_code=400)

    metadatos, err = _metadatos_json(datos.get("metadatos"))
    if err:
        return JSONResponse({"error": err}, status_code=400)

    nombre = (datos.get("nombre") or "").strip()[:_MAX_NOMBRE]
    lineas = _normalizar_lineas(datos.get("lineas"))

    activo = repos.crear_marca_activo(
        marca=marca or "",
        tipo=tipo,
        nombre=nombre,
        objeto=objeto,
        metadatos=metadatos,
        lineas=json.dumps(lineas, ensure_ascii=False),
        autor=autor_de_peticion(request),
    )
    return JSONResponse({"activo": _activo_a_dict(activo)})


async def actualizar(request: Request) -> Response:
    """PATCH /api/marca-activos/{id}: edita nombre/tipo/metadatos/lineas/aprobado. -> `{activo}` | 404."""
    activo_id = request.path_params["activo_id"]
    datos = await leer_json(request)
    if not isinstance(datos, dict):
        return JSONResponse({"error": "Cuerpo JSON inválido."}, status_code=400)

    campos: dict[str, object] = {}
    if "tipo" in datos:
        if datos["tipo"] not in _TIPOS:
            return JSONResponse({"error": "Tipo de activo no válido."}, status_code=400)
        campos["tipo"] = datos["tipo"]
    if "nombre" in datos:
        campos["nombre"] = (datos.get("nombre") or "").strip()[:_MAX_NOMBRE]
    if "metadatos" in datos:
        meta, err = _metadatos_json(datos.get("metadatos"))
        if err:
            return JSONResponse({"error": err}, status_code=400)
        campos["metadatos"] = meta
    if "lineas" in datos:
        campos["lineas"] = json.dumps(_normalizar_lineas(datos.get("lineas")), ensure_ascii=False)
    if "aprobado" in datos:
        campos["aprobado"] = bool(datos["aprobado"])

    activo = repos.actualizar_marca_activo(activo_id, campos)
    if activo is None:
        return JSONResponse({"error": "Ese activo no existe."}, status_code=404)
    return JSONResponse({"activo": _activo_a_dict(activo)})


async def borrar(request: Request) -> Response:
    """DELETE /api/marca-activos/{id}: descataloga. Con `?purgar=1` borra el binario. -> `{mensaje}` | 404."""
    activo_id = request.path_params["activo_id"]
    item = repos.borrar_marca_activo(activo_id)
    if item is None:
        return JSONResponse({"error": "Ese activo ya no está catalogado."}, status_code=404)

    if request.query_params.get("purgar") == "1" and item.get("objeto"):
        try:
            almacen_media.borrar_objeto(item["objeto"])
        except Exception:  # noqa: BLE001 -- el descatalogado ya esta hecho; purgar es best-effort
            _log.exception("No se pudo purgar el binario del activo %r.", item.get("objeto"))

    return JSONResponse({"mensaje": "Activo quitado."})


RUTAS = [
    Route("/api/marca-activos", listar, methods=["GET"]),
    Route("/api/marca-activos", crear, methods=["POST"]),
    Route("/api/marca-activos/{activo_id}", actualizar, methods=["PATCH"]),
    Route("/api/marca-activos/{activo_id}", borrar, methods=["DELETE"]),
]
