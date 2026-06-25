"""API Biblioteca de medios UNIFICADA: una galería buscable y navegable sobre `catalogo_media`.

Reúne en un solo índice las tres CARPETAS de origen (`fuente`) de las fotos disponibles para
postear —`portal` · `subidas` · `fotografias`— con un buscador GLOBAL (cruza las tres si no se
filtra) y navegación por carpeta (`fuente`) y carpeta lógica (`grupo`, p. ej. el partido). No
reinventa el almacén: el índice es `catalogo_media` (via `repos.*_media_catalogo`), los binarios
viven en el almacén de media (`almacen_media`/`media`) y se sirven por `/api/media/<key>`.

  - `GET  /api/biblioteca`                 buscador global (FTS+trigram) + filtros `fuente`/`marca`/`grupo`/`q`.
  - `GET  /api/biblioteca/carpetas`        conteos por `fuente` y por `grupo` (para navegar).
  - `GET  /api/biblioteca/sugerir`         top-N fotos para una pieza (FTS del titular+keywords, por marca).
  - `POST /api/biblioteca/guardar-remoto`  baja el original de un dispositivo (túnel keni-fotos),
                                           lo sube a `fotografias` y lo cataloga (conserva etiquetas).
  - `POST /api/biblioteca/adjuntar`        adjunta un item del catálogo a una pieza (foto propia) y
                                           hereda en la foto las keywords de las etiquetas de la pieza.
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

# Carpetas de origen válidas de la biblioteca (la dimensión lógica `fuente`; la categoría FÍSICA
# S3 de las subidas sigue siendo `originales/`, esto es solo la carpeta navegable de la biblioteca).
_FUENTES = ("portal", "subidas", "fotografias")

_MAX_TITULO = 120
_MAX_ETIQUETAS = 12
_MAX_ETIQUETA = 40
# Sugerencias foto→pieza por defecto y tope (cada item es una miniatura en una fila de propuesta).
_SUGERIR_LIMITE = 8
_SUGERIR_MAX = 24


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
    if busqueda:
        # Búsqueda por RELEVANCIA: FTS `spanish` (ts_rank) con fallback trigram para erratas.
        crudos = repos.buscar_media_catalogo(
            q=busqueda, marca=marca, fuente=fuente, grupo=grupo, incluir_globales=True
        )
    else:
        crudos = repos.listar_media_catalogo(
            marca=marca, fuente=fuente, grupo=grupo, incluir_globales=True
        )
    return {"items": [_item_a_dict(c) for c in crudos]}


async def listar(request: Request) -> Response:
    """GET /api/biblioteca?fuente=&marca=&grupo=&q= → buscador GLOBAL de la biblioteca.

    Sin filtros, cruza las tres carpetas (`portal`/`subidas`/`fotografias`). `q` busca por
    RELEVANCIA: FTS en español (título>etiquetas>descripción, ordenado por `ts_rank`) con fallback
    a similitud trigram sobre el título cuando la FTS no devuelve nada (erratas, nombres propios).
    `marca` acota a esa marca MÁS los globales (marca=''); `fuente`/`grupo` acotan a una carpeta y
    subcarpeta. → `{items:[...]}`.
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

    grupo = await run_in_threadpool(fotos_tunel.nombre_galeria, marca, galeria_id) or galeria_id
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


def _keywords_de_publicacion(publicacion_id: str) -> list[str]:
    """Keywords (CSV de las etiquetas asignadas) de una publicación, normalizadas y dedup.

    Cada etiqueta (categoría/origen) lleva un CSV `keywords` que el clasificador casa contra el
    texto; aquí las cosechamos para enriquecer la foto adjunta y para componer la consulta del
    sugeridor. Minúsculas, recortadas, sin vacíos ni duplicados.
    """
    palabras: list[str] = []
    vistas: set[str] = set()
    for etiqueta_id in repos.etiqueta_ids_de_contenido(publicacion_id):
        etiqueta = repos.obtener_etiqueta(etiqueta_id)
        if etiqueta is None:
            continue
        for cruda in (etiqueta.get("keywords") or "").split(","):
            kw = cruda.strip().lower()
            if kw and kw not in vistas:
                palabras.append(kw)
                vistas.add(kw)
    return palabras


def _fusionar_etiquetas(existentes: list[str], nuevas: list[str]) -> list[str]:
    """Une etiquetas conservando las existentes primero; dedup case-insensitive; tope `_MAX_ETIQUETAS`."""
    fusion: list[str] = []
    vistas: set[str] = set()
    for et in (*existentes, *nuevas):
        clave = et.lower()
        if et and clave not in vistas:
            fusion.append(et)
            vistas.add(clave)
        if len(fusion) >= _MAX_ETIQUETAS:
            break
    return fusion


def _heredar_keywords_en_media(media_id: str, item: dict, pieza: dict) -> None:
    """MERGE en `catalogo_media.etiquetas` las keywords de las etiquetas de la pieza (idempotente).

    Al adjuntar una foto a una pieza, la foto hereda el contexto editorial de la pieza (las keywords
    de sus etiquetas) para quedar buscable por él. No pisa lo que ya tenía: une, dedup y tope a 12.
    """
    keywords = _keywords_de_publicacion(pieza.get("publicacion_id") or "")
    if not keywords:
        return
    existentes = _etiquetas_lista(item.get("etiquetas"))
    fusion = _fusionar_etiquetas(existentes, keywords)
    if fusion != existentes:
        repos.actualizar_media_catalogo(
            media_id, {"etiquetas": json.dumps(fusion, ensure_ascii=False)}
        )


def _catalogo_por_objeto(objeto: str) -> dict | None:
    """Item del catálogo que cataloga `objeto` (o None). El `objeto` es UNIQUE en el catálogo."""
    if not objeto:
        return None
    for item in repos.listar_media_catalogo():
        if (item.get("objeto") or "").strip() == objeto:
            return item
    return None


def _limpiar_etiquetas_huerfanas(foto_vieja: str) -> None:
    """Al reemplazar la foto de una pieza, vacía las etiquetas heredadas de la foto VIEJA si ya
    no la usa NINGUNA pieza.

    Las etiquetas de una foto del catálogo se enriquecen con las keywords de las piezas que la
    usan (`_heredar_keywords_en_media`). Cuando una pieza cambia de foto, las que heredó de esa
    pieza dejan de tener dueño; si NINGUNA otra pieza referencia la foto vieja, se vacían (la fila
    del catálogo permanece: la foto sigue en la biblioteca, solo pierde el contexto heredado).
    """
    if not foto_vieja:
        return
    if any((p.get("foto") or "").strip() == foto_vieja for p in repos.listar_piezas()):
        return
    item = _catalogo_por_objeto(foto_vieja)
    if item is None or not _etiquetas_lista(item.get("etiquetas")):
        return
    repos.actualizar_media_catalogo(item.get("id") or "", {"etiquetas": "[]"})


def _adjuntar(pieza_id: str, media_id: str) -> tuple[int, dict]:
    """Lee el binario del item del catálogo y lo fija en la pieza como foto de galería (publicable)."""
    item = repos.obtener_media_catalogo(media_id)
    if item is None:
        return 404, {"error": "Esa imagen ya no está en la biblioteca."}
    pieza = repos.obtener_pieza_fila(pieza_id)
    if pieza is None:
        return 404, {"error": "Esa pieza ya no existe."}
    datos = almacen_media.leer_objeto(item.get("objeto") or "")
    if datos is None:
        return 404, {"error": "No se encontró el archivo de esa imagen."}
    # Foto que la pieza tenía ANTES de sobrescribirla (para liberar sus etiquetas heredadas si
    # tras el cambio queda sin dueño).
    foto_vieja = (pieza.get("foto") or "").strip()
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
    _heredar_keywords_en_media(media_id, item, pieza)
    _limpiar_etiquetas_huerfanas(foto_vieja)
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
# Sugeridor foto→pieza (v1, por keywords/titular sobre la FTS)                   #
# --------------------------------------------------------------------------- #


def _sugerir(pieza_id: str, limite: int) -> tuple[int, dict]:
    """Top-N fotos de la biblioteca para una pieza: FTS del titular+keywords, filtrada por marca.

    Compone la consulta con el TITULAR de la pieza más las KEYWORDS de sus etiquetas y la corre por
    la FTS acotada a la marca de la pieza (+ globales) y a fotos APROBADAS. Si la pieza no tiene
    marca o no hay texto del que tirar (sin titular ni keywords), degrada a las fotos RECIENTES de la
    marca. Misma forma que `/api/biblioteca`: `{items:[...]}`.
    """
    pieza = repos.obtener_pieza_fila(pieza_id)
    if pieza is None:
        return 404, {"error": "Esa pieza ya no existe."}
    marca = pieza.get("marca") or ""
    publicacion_id = pieza.get("publicacion_id") or ""
    publicacion = repos.obtener_publicacion(publicacion_id) if publicacion_id else None
    titular = (publicacion or {}).get("titulo", "") or ""
    keywords = _keywords_de_publicacion(publicacion_id) if publicacion_id else []
    consulta = " ".join(p for p in (titular, *keywords) if p).strip()

    if marca and consulta:
        crudos = repos.buscar_media_catalogo(
            q=consulta, marca=marca, incluir_globales=True,
            solo_aprobados=True, limite=limite,
        )
    else:
        # Degradación: sin marca o sin texto que buscar, las más recientes de la marca (aprobadas).
        crudos = repos.listar_media_catalogo(
            marca=marca or None, incluir_globales=True, solo_aprobados=True
        )[:limite]
    return 200, {"items": [_item_a_dict(c) for c in crudos]}


async def sugerir(request: Request) -> Response:
    """GET /api/biblioteca/sugerir?pieza_id=&limite= → fotos sugeridas para la pieza (`{items:[...]}`).

    Sugerencia, no auto-adjuntado: el criterio humano decide. Rankea por relevancia (FTS del titular
    + keywords de la pieza) dentro de la marca; degrada a recientes de la marca si no hay texto.
    """
    q = request.query_params
    pieza_id = (q.get("pieza_id") or "").strip()
    if not pieza_id:
        return JSONResponse({"error": "Falta la pieza."}, status_code=400)
    try:
        limite = int(q.get("limite") or _SUGERIR_LIMITE)
    except (TypeError, ValueError):
        limite = _SUGERIR_LIMITE
    limite = max(1, min(limite, _SUGERIR_MAX))
    status, cuerpo = await run_in_threadpool(_sugerir, pieza_id, limite)
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
    Route("/api/biblioteca/sugerir", sugerir, methods=["GET"]),
    Route("/api/biblioteca/guardar-remoto", guardar_remoto, methods=["POST"]),
    Route("/api/biblioteca/adjuntar", adjuntar, methods=["POST"]),
    Route("/api/biblioteca/descargar/{media_id}", descargar, methods=["GET"]),
]
