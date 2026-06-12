"""API del cajón CLIPS (Investigación → Fuentes → Internas, Claro Sports).

CONCEPTO: la mayor parte del material de Claro Sports llega como VÍDEO o FOTO por WhatsApp
(Envíos Mundial, Ramón Mundial, Videos AS Claro, ClaroSports PS…). El equipo lo vuelca aquí
TAL CUAL —pega un pie/contexto y sube el media— y el sistema crea AUTOMÁTICAMENTE la pieza:

  - un clip de VÍDEO -> pieza `formato='video'` (el vídeo ES la pieza, en las 5 redes);
  - FOTOS            -> pieza `formato='carrusel'` (portada=1ª foto con la placa de marca +
                       el resto del media en crudo como slides, igual que Presidencia).

El COPY se lanza al crear (mismo lanzador neutro que presidencia/evergreen) con el texto como
material; el depósito RELLENA las filas pre-creadas (no las duplica), conservando el media. La
pieza fluye por el gate humano normal (revisión → aprobación → programación): nada se publica
solo.

RECURSOS:
  - `GET  /api/clips?marca=`  clips volcados (`origen='clips'`), recientes primero, con el
                             estado de su pieza.
  - `POST /api/clips`        `{marca, texto, titulo?, media:[{tipo,objeto}]}` -> crea el tema
                             + la pieza (video|carrusel) + lanza el copy.

El media se sube ANTES por los endpoints existentes (`POST /api/media` imágenes,
`POST /api/media/video` vídeos); aquí solo viajan sus ids. `tipo` ∈ {imagen, video}. Un clip de
vídeo es UN solo vídeo (las fotos van en un envío aparte).

SEGURIDAD / VALIDACIÓN: multiusuario via middleware; `marca` del catálogo único; el texto es
obligatorio (es el material del copy). Errores en español, sin tracebacks.
"""

from __future__ import annotations

import json
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import generaciones, marcas, redes, repos
from .._http_json import leer_json
from ..dominio import generar as gen_dom
from ..estados import FLUJO_IMPORTANTE, ORIGEN_CLIPS
from ..seguridad import autor_de_peticion
from ..tiempo import hoy_utc

_MAX_TITULO = 200
_MAX_TEXTO = 8000
# Tope de elementos de media por clip de fotos (los carruseles nativos de IG/FB rondan 10).
_MAX_MEDIA = 10

_TIPOS_MEDIA = ("imagen", "video")


def _resolver_media(crudo: object) -> tuple[str, list[dict[str, str]], str | None]:
    """Valida la lista `media` y DECIDE el formato de la pieza.

    -> `(formato, slides, None)` o `("", [], error)`. El orden de llegada ES el de publicación.
       - si hay un VÍDEO -> formato `video` y debe ser el ÚNICO archivo (un clip = un vídeo);
       - si son IMÁGENES -> formato `carrusel` (portada=1ª imagen + slides extra).
    """
    if not isinstance(crudo, list) or not crudo:
        return "", [], "El clip necesita al menos un archivo (un vídeo o una foto)."
    if len(crudo) > _MAX_MEDIA:
        return "", [], f"Demasiados archivos: hasta {_MAX_MEDIA}."
    slides: list[dict[str, str]] = []
    for i, el in enumerate(crudo, start=1):
        if not isinstance(el, dict):
            return "", [], f"El archivo {i} del clip no es válido."
        tipo = str(el.get("tipo") or "").strip().lower()
        objeto = str(el.get("objeto") or "").strip()
        if tipo not in _TIPOS_MEDIA:
            return "", [], f"El archivo {i} tiene un tipo desconocido (imagen o video)."
        if not objeto or len(objeto) > 300:
            return "", [], f"El archivo {i} no referencia un media válido."
        slides.append({"tipo": tipo, "objeto": objeto})
    if any(s["tipo"] == "video" for s in slides):
        if len(slides) != 1:
            return "", [], (
                "Un clip de vídeo es una sola pieza de vídeo; sube las fotos en un envío aparte."
            )
        return redes.FORMATO_VIDEO, slides, None
    return redes.FORMATO_CARRUSEL, slides, None


def _derivar_titulo(titulo: object, texto: str) -> str:
    """Título dado por el equipo o, en su defecto, la primera línea del texto."""
    if isinstance(titulo, str) and titulo.strip():
        return titulo.strip()[:_MAX_TITULO]
    primera = next((ln.strip() for ln in texto.splitlines() if ln.strip()), "")
    return primera[:_MAX_TITULO]


def _clip_a_dict(item: dict[str, Any], estado_pieza: str) -> dict[str, Any]:
    """Forma pública de un clip del cajón: el tema + el estado resumido de su pieza."""
    return {
        "id": item["id"],
        "titulo": item.get("titulo") or "",
        "texto": item.get("descripcion") or "",
        "marca": item.get("marca") or "",
        "marca_nombre": marcas.etiqueta_de(item["marca"]) if item.get("marca") else "",
        "formato": item.get("formato") or "",
        "autor_nombre": item.get("autor_nombre") or "",
        "creado": item.get("creado") or "",
        # 'generando' (copy en curso) | 'lista' (ya tiene copy) | 'sin_pieza' (no produjo).
        "estado_pieza": estado_pieza,
    }


async def listar(request: Request) -> Response:
    """GET /api/clips: clips volcados, recientes primero. Filtro: `marca`."""
    marca = request.query_params.get("marca") or None
    items = repos.listar_contenido_origenes([ORIGEN_CLIPS])
    if marca:
        items = [it for it in items if (it.get("marca") or "") == marca]
    items.sort(key=lambda it: it.get("creado") or "", reverse=True)
    estados = repos.estado_pieza_por_contenido([it["id"] for it in items])
    return JSONResponse(
        {
            "clips": [_clip_a_dict(it, estados.get(it["id"], "sin_pieza")) for it in items],
            "marcas": [{"id": mid, "nombre": nombre} for mid, nombre in marcas.opciones()],
        }
    )


async def crear(request: Request) -> Response:
    """POST /api/clips: vuelca el clip y genera su pieza (video o carrusel) en el feed.

    Cuerpo `{marca, texto, titulo?, media:[{tipo,objeto}]}` -> `{clip, contenido_id,
    generacion}`. Crea el tema (`origen='clips'`), las filas por red de su formato (vídeo en
    crudo, o portada con placa + slides) y lanza el copy EN SEGUNDO PLANO con el texto.
    """
    datos = await leer_json(request)
    marca = datos.get("marca")
    if not isinstance(marca, str) or not marcas.es_marca(marca.strip()):
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)
    marca = marca.strip()
    texto = datos.get("texto")
    if not isinstance(texto, str) or not texto.strip():
        return JSONResponse(
            {"error": "Pega el pie o el contexto del clip (es el material del copy)."},
            status_code=400,
        )
    texto = texto.strip()[:_MAX_TEXTO]
    formato, slides, error = _resolver_media(datos.get("media"))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)

    titulo = _derivar_titulo(datos.get("titulo"), texto)
    if not titulo:
        return JSONResponse({"error": "El clip necesita un título."}, status_code=400)

    autor = autor_de_peticion(request)
    item = repos.crear_contenido(
        clase="contenido",
        flujo=FLUJO_IMPORTANTE,
        titulo=titulo,
        descripcion=texto,
        marca=marca,
        prioridad="alta",
        fecha_objetivo=hoy_utc().isoformat(),
        autor=autor,
        origen=ORIGEN_CLIPS,
        tipo_contenido="galeria",  # media propia del equipo (no IA, no fuente)
        formato=formato,
    )

    if formato == redes.FORMATO_VIDEO:
        # El vídeo ES la pieza: una fila por red de vídeo con el media en crudo.
        video_obj = slides[0]["objeto"]
        for red in redes.redes_de_formato(redes.FORMATO_VIDEO):
            repos.crear_contenido_plataforma(
                contenido_id=item["id"],
                red=red,
                falta_copy=True,
                falta_imagen=False,  # la pieza de vídeo no espera imagen
                falta_video=False,  # el vídeo ya está
                video=video_obj,
                es_publicacion=True,
            )
    else:
        # FOTOS -> carrusel: PORTADA = primera imagen (se compone con la placa de marca); el
        # RESTO del media va en crudo, en su orden de llegada, como slides extra.
        portada = next(s for s in slides if s["tipo"] == "imagen")
        extras = [s for s in slides if s is not portada]
        carrusel_json = json.dumps(extras, ensure_ascii=False) if extras else ""
        for red in redes.redes_de_formato(redes.FORMATO_CARRUSEL):
            repos.crear_contenido_plataforma(
                contenido_id=item["id"],
                red=red,
                falta_copy=True,
                falta_imagen=False,  # la portada ya está (foto cruda + placa on-demand)
                foto=portada["objeto"],
                carrusel=carrusel_json,
                es_publicacion=True,
            )

    # Copy en segundo plano con el texto como material (mismo lanzador neutro que presidencia).
    try:
        gen = gen_dom.lanzar_copy(
            tipo="copy",
            origen_historial="clips",
            marca=marca,
            contexto=texto[: gen_dom.MAX_TEXTO],
            redes_ids=list(redes.redes_de_formato(formato)),
            titulo=titulo,
            titulo_dado=titulo,
            texto_base=texto[: gen_dom.MAX_TEXTO],
            autor=autor,
            contenido_id=item["id"],
            urgente=True,
        )
    except generaciones.ColaLlenaError:
        # El tema y su pieza YA existen (con su media); solo faltó encolar el copy.
        return JSONResponse(
            {
                "error": (
                    "El clip se guardó pero hay demasiadas generaciones en curso; "
                    "lanza el copy desde la pieza del feed en unos segundos."
                ),
                "contenido_id": item["id"],
            },
            status_code=429,
        )

    return JSONResponse(
        {
            "clip": _clip_a_dict(item, "generando"),
            "contenido_id": item["id"],
            "generacion": gen,
        }
    )


RUTAS = [
    Route("/api/clips", listar, methods=["GET"]),
    Route("/api/clips", crear, methods=["POST"]),
]
