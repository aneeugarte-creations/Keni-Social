"""API Biblioteca de medios UNIFICADA: una galería buscable y navegable sobre `catalogo_media`.

Reúne en un solo índice las tres CARPETAS de origen (`fuente`) de las fotos disponibles para
postear —`portal` · `originales` · `fotografias`— con un buscador GLOBAL (cruza las tres si no se
filtra) y navegación por carpeta (`fuente`) y carpeta lógica (`grupo`, p. ej. el partido). No
reinventa el almacén: el índice es `catalogo_media` (via `repos.*_media_catalogo`), los binarios
viven en el almacén de media (`almacen_media`/`media`) y se sirven por `/api/media/<key>`.

  - `GET  /api/biblioteca`                 buscador global + filtros `fuente`/`marca`/`grupo`/`q`.
  - `GET  /api/biblioteca/carpetas`        conteos por `fuente` y por `grupo` (para navegar).
  - `POST /api/biblioteca/guardar-remoto`  baja el original de un dispositivo (túnel keni-fotos),
                                           lo sube a `fotografias` y lo cataloga (conserva etiquetas).
  - `POST /api/biblioteca/adjuntar`        adjunta un item del catálogo a una pieza (foto propia).
  - `GET  /api/biblioteca/descargar/{id}`  descarga (attachment) el binario del item.

Auth: sesión normal del SPA (el middleware exige sesión completa; no es público). Errores en
español, sin tracebacks. SQL parametrizado en `repos`/`db`.
"""

from __future__ import annotations

import json
import logging

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import almacen_media, autogen_stock, fotos_tunel, marcas, media, repos
from .._http_json import leer_json
from ..dominio import extraccion_url, licencia_imagen
from ..seguridad import autor_de_peticion

_log = logging.getLogger("keni_consola.biblioteca")

# Carpetas de origen válidas de la biblioteca (espejo de las categorías S3 + `fuente`).
_FUENTES = ("portal", "originales", "fotografias")

_MAX_TITULO = 120
_MAX_ETIQUETAS = 12
_MAX_ETIQUETA = 40


def _normalizar_etiquetas(valor: object) -> list[str]:
    """Lista de etiquetas normalizada (cadenas no vacías, recortadas, sin duplicados)."""
    if not isinstance(valor, list):
        return []
    vistas: list[str] = []
    for item in valor:
        if not isinstance(item, str):
            continue
        et = item.strip()[:_MAX_ETIQUETA]
        if et and et not in vistas:
            vistas.append(et)
        if len(vistas) >= _MAX_ETIQUETAS:
            break
    return vistas


def _etiquetas_lista(crudas: object) -> list[str]:
    """Etiquetas de un item del catálogo como lista de cadenas (el almacén las guarda como JSON)."""
    try:
        tags = json.loads(crudas) if isinstance(crudas, str) else crudas
    except (ValueError, TypeError):
        tags = []
    if not isinstance(tags, list):
        return []
    return [t for t in tags if isinstance(t, str)]


def _item_a_dict(item: dict) -> dict:
    """Serializa un item del catálogo a la forma de la biblioteca (url/thumb por `/api/media`)."""
    key = item.get("objeto") or ""
    return {
        "id": item.get("id", ""),
        "key": key,
        "url": f"/api/media/{key}",
        # Derivada redimensionada (resize on-the-fly cacheado): la rejilla pide thumbs, no el original.
        "thumb": f"/api/media/{key}?w=480",
        "titulo": item.get("titulo", ""),
        "etiquetas": _etiquetas_lista(item.get("etiquetas")),
        "fuente": item.get("fuente", ""),
        "grupo": item.get("grupo", ""),
        "marca": item.get("marca", ""),
        "marca_nombre": marcas.etiqueta_de(item["marca"]) if item.get("marca") else "",
        "credito": item.get("credito", ""),
        "creado": item.get("creado", ""),
    }


def _coincide(item: dict, q: str) -> bool:
    """Coincidencia substring (case-insensitive) por título, descripción o etiquetas."""
    aguja = q.lower()
    if aguja in (item.get("titulo") or "").lower():
        return True
    if aguja in (item.get("descripcion") or "").lower():
        return True
    return any(aguja in t.lower() for t in _etiquetas_lista(item.get("etiquetas")))


def _validar_marca(marca: object) -> tuple[str | None, str | None]:
    """'' (global) es válido; cualquier otra debe ser una marca del catálogo único."""
    if marca in (None, ""):
        return "", None
    if not isinstance(marca, str) or not marcas.es_marca(marca):
        return None, "Marca no permitida."
    return marca, None


# --------------------------------------------------------------------------- #
# Buscador global + navegación por carpeta                                      #
# --------------------------------------------------------------------------- #


def _listar(marca: str | None, fuente: str | None, grupo: str | None, busqueda: str) -> dict:
    crudos = repos.listar_media_catalogo(
        marca=marca, fuente=fuente, grupo=grupo, incluir_globales=True
    )
    if busqueda:
        crudos = [c for c in crudos if _coincide(c, busqueda)]
    return {"items": [_item_a_dict(c) for c in crudos]}


async def listar(request: Request) -> Response:
    """GET /api/biblioteca?fuente=&marca=&grupo=&q= → buscador GLOBAL de la biblioteca.

    Sin filtros, cruza las tres carpetas (`portal`/`originales`/`fotografias`). `q` busca substring
    (case-insensitive) en título+descripción+etiquetas. `marca` acota a esa marca MÁS los globales
    (marca=''); `fuente`/`grupo` acotan a una carpeta y subcarpeta. → `{items:[...]}`.
    """
    q = request.query_params
    marca, err = _validar_marca(q.get("marca"))
    if err is not None:
        return JSONResponse({"error": err}, status_code=400)
    fuente = (q.get("fuente") or "").strip() or None
    if fuente is not None and fuente not in _FUENTES:
        return JSONResponse({"error": "Carpeta de origen no válida."}, status_code=400)
    grupo = (q.get("grupo") or "").strip() or None
    cuerpo = await run_in_threadpool(
        _listar, marca or None, fuente, grupo, (q.get("q") or "").strip()
    )
    return JSONResponse(cuerpo)


def _carpetas(marca: str | None) -> dict:
    """Conteos por `fuente` y por `grupo` (dentro de cada fuente) para navegar la biblioteca."""
    items = repos.listar_media_catalogo(marca=marca, incluir_globales=True)
    por_fuente: dict[str, int] = {f: 0 for f in _FUENTES}
    por_grupo: dict[str, dict[str, int]] = {f: {} for f in _FUENTES}
    for it in items:
        fuente = it.get("fuente") or ""
        if fuente not in por_fuente:
            continue
        por_fuente[fuente] += 1
        grupo = it.get("grupo") or ""
        if grupo:
            por_grupo[fuente][grupo] = por_grupo[fuente].get(grupo, 0) + 1
    return {
        "carpetas": [
            {
                "fuente": f,
                "total": por_fuente[f],
                "grupos": [
                    {"grupo": g, "total": n}
                    for g, n in sorted(por_grupo[f].items())
                ],
            }
            for f in _FUENTES
        ]
    }


async def carpetas(request: Request) -> Response:
    """GET /api/biblioteca/carpetas?marca= → `{carpetas:[{fuente,total,grupos:[{grupo,total}]}]}`.

    Conteos para pintar el árbol de navegación (carpetas por origen y, dentro, por partido/grupo).
    `marca` acota a esa marca más los globales; sin marca, toda la biblioteca.
    """
    marca, err = _validar_marca(request.query_params.get("marca"))
    if err is not None:
        return JSONResponse({"error": err}, status_code=400)
    cuerpo = await run_in_threadpool(_carpetas, marca or None)
    return JSONResponse(cuerpo)


# --------------------------------------------------------------------------- #
# Guardar una foto remota (túnel keni-fotos) en la carpeta `fotografias`         #
# --------------------------------------------------------------------------- #


def _guardar_catalogo(
    *, datos: bytes, marca: str, grupo: str, titulo: str, etiquetas: list[str],
    credito: str, autor: dict | None,
) -> dict:
    """Sube los bytes a la carpeta `fotografias` y cataloga el objeto (`fuente='fotografias'`)."""
    ext = extraccion_url._ext_imagen(datos) or "jpg"
    key = media.guardar_bytes(datos, ext=ext, categoria="fotografias")
    item = repos.crear_media_catalogo(
        objeto=key,
        tipo="imagen",
        titulo=titulo,
        marca=marca,
        etiquetas=json.dumps(etiquetas, ensure_ascii=False),
        credito=credito,
        fuente="fotografias",
        grupo=grupo,
        autor=autor,
    )
    return _item_a_dict(item)


async def guardar_remoto(request: Request) -> Response:
    """POST /api/biblioteca/guardar-remoto {galeria_id, archivo, dispositivo, marca, titulo?, etiquetas?}.

    Pide el ORIGINAL a un dispositivo que comparte `marca` (túnel keni-fotos), lo sube a la carpeta
    `fotografias` del almacén y lo cataloga con `fuente='fotografias'`, `grupo=<nombre de la galería>`
    y las `etiquetas` que pasa el front (labels del candidato: fase/cámara/en_foco/nombre). → `{item}`.
    """
    datos_req = await leer_json(request)
    marca, err = _validar_marca(datos_req.get("marca"))
    if err is not None or not marca:
        return JSONResponse({"error": err or "Falta la marca."}, status_code=400)
    galeria_id = (datos_req.get("galeria_id") or "").strip()
    archivo = (datos_req.get("archivo") or "").strip()
    dispositivo = (datos_req.get("dispositivo") or "").strip()
    if not galeria_id or not archivo:
        return JSONResponse({"error": "Falta la foto a guardar."}, status_code=400)

    try:
        binario, _mime = await fotos_tunel.pedir_original(marca, galeria_id, archivo, dispositivo)
    except fotos_tunel.TunelError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    grupo = fotos_tunel.nombre_galeria(marca, galeria_id) or galeria_id
    titulo = (datos_req.get("titulo") or "").strip()[:_MAX_TITULO]
    etiquetas = _normalizar_etiquetas(datos_req.get("etiquetas"))
    autor = autor_de_peticion(request)
    credito = (autor or {}).get("usuario", "") or dispositivo

    try:
        item = await run_in_threadpool(
            _guardar_catalogo,
            datos=binario, marca=marca, grupo=grupo, titulo=titulo,
            etiquetas=etiquetas, credito=credito, autor=autor,
        )
    except media.MediaError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    # Las coordenadas del túnel no se persisten en el catálogo, pero se devuelven en el item recién
    # guardado para que la UI pueda navegar la RÁFAGA del burst (`GET /api/artes/propio/rafaga`).
    item.update({"galeria_id": galeria_id, "archivo": archivo, "dispositivo": dispositivo})
    return JSONResponse({"item": item})


# --------------------------------------------------------------------------- #
# Adjuntar un item de la biblioteca a una pieza (foto propia, publicable)        #
# --------------------------------------------------------------------------- #


def _adjuntar(pieza_id: str, media_id: str) -> tuple[int, dict]:
    """Lee el binario del item del catálogo y lo fija en la pieza como foto de galería (publicable)."""
    item = repos.obtener_media_catalogo(media_id)
    if item is None:
        return 404, {"error": "Esa imagen ya no está en la biblioteca."}
    if repos.obtener_pieza_fila(pieza_id) is None:
        return 404, {"error": "Esa pieza ya no existe."}
    datos = almacen_media.leer_objeto(item.get("objeto") or "")
    if datos is None:
        return 404, {"error": "No se encontró el archivo de esa imagen."}
    try:
        actualizada = autogen_stock.adjuntar_bytes(
            pieza_id,
            datos,
            proveedor="biblioteca",
            credito_url=item.get("credito", ""),
            origen=licencia_imagen.ORIGEN_GALERIA,
            autorizada=True,
            falta_imagen=False,
        )
    except extraccion_url.ExtraccionError as e:
        return 400, {"error": str(e)}
    if actualizada is None:
        return 404, {"error": "Esa pieza ya no existe."}
    return 200, {"plataforma": _plataforma_a_dict(actualizada)}


def _plataforma_a_dict(plat: dict) -> dict:
    """Subconjunto de campos de imagen de una fila por plataforma (lo que refresca la UI de stock)."""
    return {
        "id": plat.get("id", ""),
        "imagen_url": plat.get("imagen_url", ""),
        "foto": plat.get("foto", ""),
        "falta_imagen": bool(plat.get("falta_imagen")),
        "imagen_origen": plat.get("imagen_origen", ""),
        "imagen_proveedor": plat.get("imagen_proveedor", ""),
        "imagen_autor": plat.get("imagen_autor", ""),
        "imagen_licencia": plat.get("imagen_licencia", ""),
        "imagen_credito_url": plat.get("imagen_credito_url", ""),
        "imagen_autorizada": bool(plat.get("imagen_autorizada")),
    }


async def adjuntar(request: Request) -> Response:
    """POST /api/biblioteca/adjuntar {pieza_id, id} → adjunta el item del catálogo a la pieza.

    Reusa `autogen_stock.adjuntar_bytes` (misma puerta que «Propio»): la pieza queda con foto PROPIA
    publicable y se reparte a las redes hermanas. Las etiquetas siguen en el item del catálogo.
    """
    datos = await leer_json(request)
    pieza_id = (datos.get("pieza_id") or "").strip()
    media_id = (datos.get("id") or "").strip()
    if not pieza_id:
        return JSONResponse({"error": "Falta la pieza."}, status_code=400)
    if not media_id:
        return JSONResponse({"error": "Falta la imagen a adjuntar."}, status_code=400)
    status, cuerpo = await run_in_threadpool(_adjuntar, pieza_id, media_id)
    return JSONResponse(cuerpo, status_code=status)


# --------------------------------------------------------------------------- #
# Descargar el binario de un item (attachment)                                  #
# --------------------------------------------------------------------------- #


def _descargar(media_id: str) -> tuple[int, dict | tuple[bytes, str, str]]:
    """Carga el binario del item del catálogo. (status, {error}) o (status, (datos, mime, nombre))."""
    item = repos.obtener_media_catalogo(media_id)
    if item is None:
        return 404, {"error": "Esa imagen ya no está en la biblioteca."}
    key = item.get("objeto") or ""
    datos = almacen_media.leer_objeto(key)
    if datos is None:
        return 404, {"error": "No se encontró el archivo de esa imagen."}
    nombre = key.rpartition("/")[2] or key or f"{media_id}.jpg"
    return 200, (datos, media.mime_de(key), nombre)


async def descargar(request: Request) -> Response:
    """GET /api/biblioteca/descargar/{id} → descarga (attachment) el binario del item del catálogo."""
    media_id = request.path_params["media_id"]
    status, payload = await run_in_threadpool(_descargar, media_id)
    if status != 200:
        return JSONResponse(payload, status_code=status)
    datos, mime, nombre = payload
    return Response(
        datos,
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


RUTAS = [
    Route("/api/biblioteca", listar, methods=["GET"]),
    Route("/api/biblioteca/carpetas", carpetas, methods=["GET"]),
    Route("/api/biblioteca/guardar-remoto", guardar_remoto, methods=["POST"]),
    Route("/api/biblioteca/adjuntar", adjuntar, methods=["POST"]),
    Route("/api/biblioteca/descargar/{media_id}", descargar, methods=["GET"]),
]
