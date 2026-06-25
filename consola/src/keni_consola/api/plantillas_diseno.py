"""API Texto de PLANTILLAS DE DISEÑO: N plantillas reutilizables por marca (editor).

Cada plantilla es un DOCUMENTO de capas completo (logo + textos + marcos + …) que el equipo
guarda para reutilizar; se etiqueta por `categoria` (texto LIBRE normalizado a slug: ultima-hora |
marcador | efemerides | … con "general" como fallback; sin enum en BD) y por `categorias` (ids de
`etiquetas` clase=categoria) para filtrar por categoria editorial. A diferencia de `plantillas_marca`
(1 plantilla POR DEFECTO por marca), aquí hay muchas. El catálogo legible de categorías vive en
el frontend (`lib/categoriasPlantilla.ts`); el legado "post" se trata como "general".

  - `GET    /api/plantillas-diseno`        lista (filtros `?marca=&categoria=&tipo=&categorias=&q=`).
  - `POST   /api/plantillas-diseno`        crea una plantilla a partir de un documento (validado).
  - `GET    /api/plantillas-diseno/{id}`   una plantilla (con su documento listo para cargar).
  - `PATCH  /api/plantillas-diseno/{id}`   edita nombre/categoria/tipo/documento/categorias/miniatura/foto_muestra/activo/rotar.
  - `DELETE /api/plantillas-diseno/{id}`   borra.

SEGURIDAD: `marca` (si llega) del catálogo único; el `documento` se valida en el dominio
(`estudio_imagen.validar_documento`) antes de persistir; errores en español, sin tracebacks.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import unicodedata

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import almacen_media, marcas, repos
from .._http_json import leer_json
from ..dominio import estudio_imagen
from ..seguridad import autor_de_peticion

_MAX_NOMBRE = 120
_MAX_CATEGORIAS = 24
_MAX_MUESTRA_TEXTO = 200  # tope del titular/pleca de muestra (solo overview de la galería)
_TIPOS_VALIDOS = frozenset({"foto", "miniatura"})

# El preview renderiza con un proceso Node (CPU + ~50 MiB/proc). Sin tope, una galería con N
# plantillas SIN miniatura dispararía N renders a la vez (HTTP/2 multiplexa las peticiones del
# navegador) y saturaría CPU/RAM del `back`. Semáforo de HILOS (por worker uvicorn) que se toma
# DENTRO del threadpool: acota cuántos Node corren en paralelo sin ligarse a ningún event loop
# (un `asyncio.Semaphore` a nivel de módulo se ligaría al primer loop y rompería en los tests).
_MAX_PREVIEW_CONCURRENTE = 4
_sem_preview = threading.BoundedSemaphore(_MAX_PREVIEW_CONCURRENTE)

# Carpeta de la CACHÉ del preview: 1 png por combinación documento+muestra. Reciclable (el
# contenido se puede regenerar). La clave la fija la huella del contenido -> self-invalidante.
_CARPETA_CACHE_PREVIEW = "previews"


def _preview_bytes(
    huella: str,
    documento: str,
    foto_muestra: str,
    titular_muestra: str,
    etiqueta_muestra: str,
) -> bytes:
    """Bytes del preview, de la CACHÉ o recién renderizados. Corre en threadpool (lee/escribe el
    almacén S3-o-disco + subprocess Node), NUNCA en el event loop.

    Si ya se renderizó esa combinación documento+muestra (`previews/<huella>.png`), la sirve sin
    tocar Node —esto es lo que hace rápida la galería de marcas cuyas plantillas no tienen
    `miniatura` guardada—. En cache-miss renderiza (acotado por `_sem_preview`) y persiste. La huella
    la fija el contenido, así que cambiar el documento/muestra escribe una clave NUEVA (self-invalida).
    """
    clave = f"{_CARPETA_CACHE_PREVIEW}/{huella}.png"
    cacheado = almacen_media.leer_objeto(clave)
    if cacheado is not None:
        return cacheado
    doc = json.loads(documento) if isinstance(documento, str) else documento
    doc = _hornear_muestra(doc, foto_muestra)
    # Subtítulo/pleca: con texto de muestra propio se INYECTA (binding); sin él, se revela el
    # literal de la capa (quitando el binding) para que igualmente se vea en la galería.
    if not etiqueta_muestra:
        doc = _revelar_pleca(doc)
    with _sem_preview:
        datos = estudio_imagen.renderizar_documento_bytes(
            doc,
            bindings={"copy_in": titular_muestra or "TITULAR", "etiqueta_default": etiqueta_muestra},
        )
    try:
        almacen_media.guardar_objeto(clave, datos, content_type="image/png")
    except Exception:  # noqa: BLE001 -- la caché es best-effort: un fallo al escribir no rompe el preview
        pass
    return datos


def _normalizar_categoria(valor: object) -> str:
    """Slug normalizado de la categoría (texto libre, SIN enum en BD): minúsculas, sin acentos,
    separadores a guiones, máx 40. Vacío y el legado "post" caen a "general" (el fallback)."""
    texto = valor if isinstance(valor, str) else ""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c)).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", texto).strip("-")[:40].strip("-")
    return slug if slug and slug != "post" else "general"


def _validar_marca(marca: object) -> tuple[str | None, str | None]:
    if marca in (None, ""):
        return "", None
    if not isinstance(marca, str) or not marcas.es_marca(marca):
        return None, "Marca no permitida."
    return marca, None


def _normalizar_categorias(valor: object) -> list[str]:
    if not isinstance(valor, list):
        return []
    vistas: list[str] = []
    for item in valor:
        if isinstance(item, str) and item.strip() and item.strip() not in vistas:
            vistas.append(item.strip())
        if len(vistas) >= _MAX_CATEGORIAS:
            break
    return vistas


def _promover_foto_muestra(valor: object) -> str:
    """Normaliza el objeto de `foto_muestra` (foto representativa de la plantilla, horneada en la
    galería): vacío => "" (sin muestra), si hay objeto lo promueve a `plantillas/` (asset REUSABLE,
    no efímero en `fotos/`). Idempotente vía `promover_objeto`."""
    objeto = valor.strip() if isinstance(valor, str) else ""
    return almacen_media.promover_objeto(objeto, "plantillas") if objeto else ""


def _texto_muestra(valor: object) -> str:
    """Normaliza un texto de muestra (titular/pleca del overview): str recortado a `_MAX_MUESTRA_TEXTO`,
    o "" (que en el render cae al fallback: "TITULAR" para el titular, el literal para la pleca)."""
    return valor.strip()[:_MAX_MUESTRA_TEXTO] if isinstance(valor, str) else ""


def _plantilla_a_dict(item: dict) -> dict:
    """Serializa una plantilla: documento/categorias como objeto/lista, url de miniatura y marca_nombre."""
    try:
        doc = json.loads(item.get("documento") or "{}")
    except (ValueError, TypeError):
        doc = {}
    try:
        categorias = json.loads(item.get("categorias") or "[]")
    except (ValueError, TypeError):
        categorias = []
    if not isinstance(categorias, list):
        categorias = []
    miniatura = item.get("miniatura") or ""
    foto_muestra = item.get("foto_muestra") or ""
    return {
        **item,
        "documento": doc,
        "categorias": [x for x in categorias if isinstance(x, str)],
        "miniatura_url": f"/api/media/{miniatura}" if miniatura else "",
        "foto_muestra_url": f"/api/media/{foto_muestra}" if foto_muestra else "",
        "marca_nombre": marcas.etiqueta_de(item["marca"]) if item.get("marca") else "",
    }


def _coincide(p: dict, q: str) -> bool:
    """Búsqueda `q`: por nombre (substring, case-insensitive) y por categoría (slug normalizado,
    así «Última hora» encuentra plantillas con categoria `ultima-hora`)."""
    if q.lower() in (p.get("nombre") or "").lower():
        return True
    if not any(ch.isalnum() for ch in q):
        return False
    return _normalizar_categoria(q) in _normalizar_categoria(p.get("categoria"))


def _listar(marca: str | None, tipo: str | None, cat_q: str, categorias_filtro: str, busqueda: str) -> list[dict]:
    plantillas = [
        _plantilla_a_dict(item)
        for item in repos.listar_plantillas_diseno(marca=marca, tipo=tipo)
    ]
    # DOS ejes "categoría" distintos: `cat_q` (`?categoria=`) filtra por el SLUG de la plantilla
    # (ultima-hora | marcador | …); `categorias_filtro` (`?categorias=`) filtra por MEMBRESÍA en la
    # lista `categorias` (ids de etiquetas a las que aplica la plantilla). El slug acepta el valor
    # crudo (igualdad exacta, p. ej. el legado "post") o cualquier forma que normalice al mismo slug
    # («Última hora» == `ultima-hora`). Se filtra en memoria, como `q`, para no acoplar al SQL.
    if cat_q:
        cat_norm = _normalizar_categoria(cat_q)
        plantillas = [
            p
            for p in plantillas
            if p.get("categoria") == cat_q or _normalizar_categoria(p.get("categoria")) == cat_norm
        ]
    if categorias_filtro:
        plantillas = [p for p in plantillas if categorias_filtro in p.get("categorias", [])]
    if busqueda:
        plantillas = [p for p in plantillas if _coincide(p, busqueda)]
    return plantillas


async def listar(request: Request) -> Response:
    """GET /api/plantillas-diseno: plantillas (mas recientes primero) con filtros opcionales."""
    q = request.query_params
    tipo_q = (q.get("tipo") or "").strip() or None
    if tipo_q and tipo_q not in _TIPOS_VALIDOS:
        return JSONResponse({"error": "tipo debe ser 'foto' o 'miniatura'."}, status_code=400)
    plantillas = await run_in_threadpool(
        _listar,
        q.get("marca") or None,
        tipo_q,
        (q.get("categoria") or "").strip(),
        (q.get("categorias") or "").strip(),
        (q.get("q") or "").strip(),
    )
    return JSONResponse({"plantillas": plantillas})


async def crear(request: Request) -> Response:
    """POST /api/plantillas-diseno: crea una plantilla desde un documento (validado). -> `{plantilla}` | 400."""
    datos = await leer_json(request)
    if not isinstance(datos, dict):
        return JSONResponse({"error": "Cuerpo JSON inválido."}, status_code=400)

    doc = datos.get("documento")
    if not isinstance(doc, dict):
        return JSONResponse({"error": "Falta el documento de la plantilla."}, status_code=400)
    try:
        doc_ok = estudio_imagen.validar_documento(doc)
    except estudio_imagen.EstudioError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    if not estudio_imagen.documento_tiene_hueco(doc_ok):
        return JSONResponse(
            {"error": "La plantilla necesita un hueco de foto: marca una imagen como «hueco de foto»."},
            status_code=400,
        )

    marca, err = _validar_marca(datos.get("marca"))
    if err:
        return JSONResponse({"error": err}, status_code=400)

    nombre = (datos.get("nombre") or "").strip()[:_MAX_NOMBRE]
    categoria = _normalizar_categoria(datos.get("categoria"))
    tipo_raw = (datos.get("tipo") or "").strip()
    tipo = tipo_raw if tipo_raw in _TIPOS_VALIDOS else "foto"
    miniatura = (datos.get("miniatura") or "").strip() if isinstance(datos.get("miniatura"), str) else ""
    if miniatura:
        # La miniatura es un asset REUSABLE de la plantilla: a la carpeta `plantillas/`.
        miniatura = almacen_media.promover_objeto(miniatura, "plantillas")
    foto_muestra = _promover_foto_muestra(datos.get("foto_muestra"))
    titular_muestra = _texto_muestra(datos.get("titular_muestra"))
    etiqueta_muestra = _texto_muestra(datos.get("etiqueta_muestra"))
    categorias = _normalizar_categorias(datos.get("categorias"))

    plantilla = await run_in_threadpool(
        repos.crear_plantilla_diseno,
        marca=marca or "",
        nombre=nombre,
        categoria=categoria,
        tipo=tipo,
        documento=json.dumps(doc_ok, ensure_ascii=False),
        miniatura=miniatura,
        foto_muestra=foto_muestra,
        titular_muestra=titular_muestra,
        etiqueta_muestra=etiqueta_muestra,
        categorias=json.dumps(categorias, ensure_ascii=False),
        rotar=bool(datos.get("rotar")),
        autor=autor_de_peticion(request),
    )
    return JSONResponse({"plantilla": _plantilla_a_dict(plantilla)})


async def reordenar(request: Request) -> Response:
    """POST /api/plantillas-diseno/reordenar: fija el orden MANUAL de la galería (drag-and-drop).

    Cuerpo `{"ids": ["id1", "id2", …]}` con la secuencia EXACTA deseada; asigna `orden`=1..N a esos
    ids (el resto queda igual). -> `{actualizadas: n}` | 400. El llamante envía la lista completa de
    la marca en su nuevo orden.
    """
    datos = await leer_json(request)
    if not isinstance(datos, dict):
        return JSONResponse({"error": "Cuerpo JSON inválido."}, status_code=400)
    ids = datos.get("ids")
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        return JSONResponse({"error": "«ids» debe ser una lista de identificadores."}, status_code=400)
    n = await run_in_threadpool(repos.reordenar_plantillas_diseno, [i for i in ids if i])
    return JSONResponse({"actualizadas": n})


async def obtener(request: Request) -> Response:
    """GET /api/plantillas-diseno/{id}: una plantilla con su documento listo para cargar. -> 404 si no existe."""
    item = await run_in_threadpool(repos.obtener_plantilla_diseno, request.path_params["plantilla_id"])
    if item is None:
        return JSONResponse({"error": "Esa plantilla no existe."}, status_code=404)
    return JSONResponse({"plantilla": _plantilla_a_dict(item)})


async def actualizar(request: Request) -> Response:
    """PATCH /api/plantillas-diseno/{id}: edita campos. Si llega `documento`, se valida. -> `{plantilla}` | 400/404."""
    plantilla_id = request.path_params["plantilla_id"]
    datos = await leer_json(request)
    if not isinstance(datos, dict):
        return JSONResponse({"error": "Cuerpo JSON inválido."}, status_code=400)

    campos: dict[str, object] = {}
    if "nombre" in datos:
        campos["nombre"] = (datos.get("nombre") or "").strip()[:_MAX_NOMBRE]
    if "categoria" in datos:
        campos["categoria"] = _normalizar_categoria(datos.get("categoria"))
    if "tipo" in datos:
        tipo_raw = (datos.get("tipo") or "").strip()
        if tipo_raw and tipo_raw not in _TIPOS_VALIDOS:
            return JSONResponse({"error": "tipo debe ser 'foto' o 'miniatura'."}, status_code=400)
        campos["tipo"] = tipo_raw if tipo_raw in _TIPOS_VALIDOS else "foto"
    if "miniatura" in datos:
        campos["miniatura"] = (datos.get("miniatura") or "").strip()
    if "foto_muestra" in datos:
        # "" limpia la muestra (huecos grises de nuevo); cualquier objeto se promueve a `plantillas/`.
        campos["foto_muestra"] = _promover_foto_muestra(datos.get("foto_muestra"))
    if "titular_muestra" in datos:
        campos["titular_muestra"] = _texto_muestra(datos.get("titular_muestra"))
    if "etiqueta_muestra" in datos:
        campos["etiqueta_muestra"] = _texto_muestra(datos.get("etiqueta_muestra"))
    if "categorias" in datos:
        campos["categorias"] = json.dumps(_normalizar_categorias(datos.get("categorias")), ensure_ascii=False)
    if "activo" in datos:
        campos["activo"] = bool(datos["activo"])
    if "rotar" in datos:
        campos["rotar"] = bool(datos["rotar"])
    if "documento" in datos:
        if not isinstance(datos["documento"], dict):
            return JSONResponse({"error": "El documento debe ser un objeto."}, status_code=400)
        try:
            doc_ok = estudio_imagen.validar_documento(datos["documento"])
        except estudio_imagen.EstudioError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        if not estudio_imagen.documento_tiene_hueco(doc_ok):
            return JSONResponse(
                {"error": "La plantilla necesita un hueco de foto: marca una imagen como «hueco de foto»."},
                status_code=400,
            )
        campos["documento"] = json.dumps(doc_ok, ensure_ascii=False)

    plantilla = await run_in_threadpool(repos.actualizar_plantilla_diseno, plantilla_id, campos)
    if plantilla is None:
        return JSONResponse({"error": "Esa plantilla no existe."}, status_code=404)
    return JSONResponse({"plantilla": _plantilla_a_dict(plantilla)})


async def borrar(request: Request) -> Response:
    """DELETE /api/plantillas-diseno/{id}: borra la plantilla. -> `{mensaje}` | 404."""
    item = await run_in_threadpool(repos.borrar_plantilla_diseno, request.path_params["plantilla_id"])
    if item is None:
        return JSONResponse({"error": "Esa plantilla ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Plantilla borrada."})


def _hornear_muestra(doc: dict, objeto: str) -> dict:
    """Copia del documento con el `objeto` de la foto de muestra puesto en cada HUECO de foto
    (`es_foto`) VACÍO de nivel superior, para que la miniatura/preview de la galería se vea «tal cual
    quedaría». Espejo server-side del horneado client-side `conFotoEnHuecosVacios`. No persiste."""
    if not objeto:
        return doc
    capas = doc.get("capas")
    if not isinstance(capas, list):
        return doc
    return {
        **doc,
        "capas": [
            {**c, "objeto": objeto}
            if (
                isinstance(c, dict)
                and c.get("tipo") == "imagen"
                and c.get("es_foto")
                and not str(c.get("objeto") or "").strip()
            )
            else c
            for c in capas
        ],
    }


def _revelar_pleca(doc: dict) -> dict:
    """Copia del documento con las capas de texto atadas a `etiqueta_default` (pleca/SUBTÍTULO)
    DESvinculadas (binding -> None), para que el render las pinte con su `texto` literal en el
    overview de la galería (un binding sin valor se omite). Así el subtítulo se ve «tal cual
    quedaría». El titular (`copy_in`) NO se toca: sigue con el placeholder de ejemplo ("TITULAR")."""
    capas = doc.get("capas")
    if not isinstance(capas, list):
        return doc
    return {
        **doc,
        "capas": [
            {**c, "binding": None}
            if (isinstance(c, dict) and c.get("tipo") == "texto" and c.get("binding") == "etiqueta_default")
            else c
            for c in capas
        ],
    }


async def preview(request: Request) -> Response:
    """GET /api/plantillas-diseno/{id}/preview: MINIATURA on-demand del diseño (cacheada).

    Renderiza el DOCUMENTO de la plantilla (con su foto de muestra horneada en los huecos vacíos y el
    titular/subtítulo de muestra) a PNG. Es el RESPALDO de la galería cuando la plantilla no tiene
    `miniatura` guardada —p. ej. las creadas por API/agente, que no pasan por el guardado del estudio
    (es ahí donde se genera la miniatura)—. Así se ven todas sin tener que abrir+editar cada una.

    DOS niveles de caché por la misma huella (hash del documento + la muestra): el ETag para el 304
    del navegador, y una caché PERSISTENTE en el almacén (`previews/<huella>.png`) para que cada
    combinación se renderice con Node UNA sola vez (las siguientes peticiones —incl. tras expirar el
    `max-age`— se sirven del almacén, sin Node). Cambiar el documento/muestra cambia la huella -> clave
    nueva (self-invalida). 404 si no existe; 422 si el render falla.
    """
    item = await run_in_threadpool(repos.obtener_plantilla_diseno, request.path_params["plantilla_id"])
    if item is None:
        return JSONResponse({"error": "Esa plantilla no existe."}, status_code=404)
    documento = item.get("documento") or "{}"
    foto_muestra = item.get("foto_muestra") or ""
    titular_muestra = item.get("titular_muestra") or ""
    etiqueta_muestra = item.get("etiqueta_muestra") or ""
    clave_etag = f"{documento}|{foto_muestra}|{titular_muestra}|{etiqueta_muestra}"
    huella = hashlib.sha256(clave_etag.encode()).hexdigest()[:32]
    etag = f'"{huella}"'
    cache = "private, max-age=300"
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": cache})
    try:
        datos = await run_in_threadpool(
            _preview_bytes, huella, documento, foto_muestra, titular_muestra, etiqueta_muestra
        )
    except (ValueError, TypeError) as e:
        return JSONResponse({"error": f"Documento inválido: {e}"}, status_code=422)
    except estudio_imagen.EstudioError as e:
        return JSONResponse({"error": str(e)}, status_code=422)
    return Response(
        content=datos,
        media_type="image/png",
        headers={"ETag": etag, "Cache-Control": cache},
    )


RUTAS = [
    Route("/api/plantillas-diseno", listar, methods=["GET"]),
    Route("/api/plantillas-diseno", crear, methods=["POST"]),
    # Antes que `/{plantilla_id}` para que «reordenar» no se interprete como un id.
    Route("/api/plantillas-diseno/reordenar", reordenar, methods=["POST"]),
    Route("/api/plantillas-diseno/{plantilla_id}", obtener, methods=["GET"]),
    Route("/api/plantillas-diseno/{plantilla_id}/preview", preview, methods=["GET"]),
    Route("/api/plantillas-diseno/{plantilla_id}", actualizar, methods=["PATCH"]),
    Route("/api/plantillas-diseno/{plantilla_id}", borrar, methods=["DELETE"]),
]
