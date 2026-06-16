"""API del cajón PRESIDENCIA (Investigación → Fuentes → Internas).

CONCEPTO: de vez en cuando presidencia manda por WhatsApp una nota (texto + 4-5 imágenes
y algún video) que la marca DEBE publicar. El equipo la vuelca aquí TAL CUAL (pega el
texto y sube todo el media) y el sistema genera AUTOMÁTICAMENTE la pieza en el feed:

  - una pieza `formato='carrusel'` (`origen='presidencia'`, `flujo='importante'`): la
    PORTADA es la primera imagen con la placa de marca (foto cruda + plantilla, la
    maquinaria de imagen de siempre) y el RESTO del media va EN CRUDO, en orden, como
    slides extra (campo `carrusel` de cada fila por plataforma);
  - el COPY se lanza al crear la nota (mismo lanzador neutro que evergreen/noticias) con
    la nota íntegra como material a redactar; el depósito RELLENA las filas pre-creadas
    (no las duplica), conservando el media adjunto;
  - la pieza fluye por el gate humano normal (revisión → aprobación → programación):
    nada se publica solo.

RECURSOS:
  - `GET  /api/presidencia/notas?marca=`  notas volcadas (temas `origen='presidencia'`),
                                          recientes primero, con el estado de su pieza.
  - `POST /api/presidencia/notas`         `{marca, texto, titulo?, media:[{tipo,objeto}]}`
                                          crea el tema + pieza carrusel + lanza el copy.

El media se sube ANTES por los endpoints existentes (`POST /api/media` imágenes,
`POST /api/media/video` videos); aquí solo viajan sus ids. `tipo` ∈ {imagen, video}.

SEGURIDAD / VALIDACIÓN: multiusuario via middleware; `marca` del catálogo único; el texto
es obligatorio (es el material del copy); se exige AL MENOS UNA imagen (la portada del
carrusel se compone sobre una foto). Errores en español, sin tracebacks.
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
from ..estados import FLUJO_IMPORTANTE, ORIGEN_PRESIDENCIA
from ..seguridad import autor_de_peticion
from ..tiempo import hoy_utc

_MAX_TITULO = 200
_MAX_TEXTO = 8000
# Tope de elementos de media por nota (portada incluida): los carruseles nativos de
# IG/FB rondan 10 slides; más media de la publicable solo confunde al equipo.
_MAX_MEDIA = 10

_TIPOS_MEDIA = ("imagen", "video")


def _validar_media(crudo: object) -> tuple[list[dict[str, str]], str | None]:
    """Valida la lista `media` del cliente -> `(slides, None)` o `([], error)`.

    Cada elemento debe ser `{tipo: "imagen"|"video", objeto: <id de media subido>}`. El
    orden de llegada ES el orden de publicación. Se exige al menos UNA imagen (portada).
    """
    if not isinstance(crudo, list) or not crudo:
        return [], "La nota necesita el media de presidencia (al menos una imagen)."
    if len(crudo) > _MAX_MEDIA:
        return [], f"Demasiados archivos: el carrusel admite hasta {_MAX_MEDIA}."
    slides: list[dict[str, str]] = []
    for i, el in enumerate(crudo, start=1):
        if not isinstance(el, dict):
            return [], f"El archivo {i} de la nota no es válido."
        tipo = str(el.get("tipo") or "").strip().lower()
        objeto = str(el.get("objeto") or "").strip()
        if tipo not in _TIPOS_MEDIA:
            return [], f"El archivo {i} tiene un tipo desconocido (imagen o video)."
        if not objeto or len(objeto) > 300:
            return [], f"El archivo {i} no referencia un media válido."
        slides.append({"tipo": tipo, "objeto": objeto})
    if not any(s["tipo"] == "imagen" for s in slides):
        return [], "La nota necesita al menos una imagen (la portada del carrusel)."
    return slides, None


def _derivar_titulo(titulo: object, texto: str) -> str:
    """Título dado por el equipo o, en su defecto, la primera línea de la nota."""
    if isinstance(titulo, str) and titulo.strip():
        return titulo.strip()[:_MAX_TITULO]
    primera = next((ln.strip() for ln in texto.splitlines() if ln.strip()), "")
    return primera[:_MAX_TITULO]


def _nota_a_dict(item: dict[str, Any], estado_pieza: str) -> dict[str, Any]:
    """Forma pública de una nota del cajón: el tema + el estado resumido de su pieza."""
    return {
        "id": item["id"],
        "titulo": item.get("titulo") or "",
        "texto": item.get("descripcion") or "",
        "marca": item.get("marca") or "",
        "marca_nombre": marcas.etiqueta_de(item["marca"]) if item.get("marca") else "",
        "autor_nombre": item.get("autor_nombre") or "",
        "creado": item.get("creado") or "",
        # 'generando' (copy en curso) | 'lista' (ya tiene copy) | 'sin_pieza' (no produjo).
        "estado_pieza": estado_pieza,
    }


async def listar(request: Request) -> Response:
    """GET /api/presidencia/notas: notas volcadas, recientes primero. Filtro: `marca`."""
    marca = request.query_params.get("marca") or None
    items = repos.listar_publicaciones_origenes([ORIGEN_PRESIDENCIA])
    if marca:
        items = [it for it in items if (it.get("marca") or "") == marca]
    items.sort(key=lambda it: it.get("creado") or "", reverse=True)
    estados = repos.estado_pieza_por_publicacion([it["id"] for it in items])
    return JSONResponse(
        {
            "notas": [
                _nota_a_dict(it, estados.get(it["id"], "sin_pieza")) for it in items
            ],
            "marcas": [{"id": mid, "nombre": nombre} for mid, nombre in marcas.opciones()],
        }
    )


async def crear(request: Request) -> Response:
    """POST /api/presidencia/notas: vuelca la nota y genera la pieza carrusel del feed.

    Cuerpo `{marca, texto, titulo?, media:[{tipo,objeto}]}` -> `{nota, publicacion_id,
    generacion}`. Crea el tema (`origen='presidencia'`, `formato='carrusel'`), una fila
    por red del carrusel con la PORTADA (primera imagen, como foto cruda para la placa)
    y los slides extra en crudo, y lanza el copy EN SEGUNDO PLANO con la nota íntegra.
    """
    datos = await leer_json(request)
    marca = datos.get("marca")
    if not isinstance(marca, str) or not marcas.es_marca(marca.strip()):
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)
    marca = marca.strip()
    texto = datos.get("texto")
    if not isinstance(texto, str) or not texto.strip():
        return JSONResponse(
            {"error": "Pega el texto de la nota de presidencia."}, status_code=400
        )
    texto = texto.strip()[:_MAX_TEXTO]
    slides, error = _validar_media(datos.get("media"))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)

    titulo = _derivar_titulo(datos.get("titulo"), texto)
    if not titulo:
        return JSONResponse({"error": "La nota necesita un título."}, status_code=400)

    # PORTADA = primera imagen (se compone con la placa de marca); el RESTO del media va
    # en crudo, en su orden de llegada, como slides extra del carrusel.
    portada = next(s for s in slides if s["tipo"] == "imagen")
    extras = [s for s in slides if s is not portada]

    autor = autor_de_peticion(request)
    item = repos.crear_publicacion(
        clase="contenido",
        flujo=FLUJO_IMPORTANTE,
        titulo=titulo,
        descripcion=texto,
        marca=marca,
        prioridad="alta",
        fecha_objetivo=hoy_utc().isoformat(),
        autor=autor,
        origen=ORIGEN_PRESIDENCIA,
        tipo_contenido="galeria",
        formato=redes.FORMATO_CARRUSEL,
    )
    carrusel_json = json.dumps(extras, ensure_ascii=False) if extras else ""
    for red in redes.redes_de_formato(redes.FORMATO_CARRUSEL):
        repos.crear_pieza_fila(
            publicacion_id=item["id"],
            red=red,
            falta_copy=True,
            # La portada YA está (foto cruda + placa on-demand): la pieza no espera imagen.
            falta_imagen=False,
            foto=portada["objeto"],
            carrusel=carrusel_json,
            es_publicacion=True,
        )

    # Copy en segundo plano con la nota ÍNTEGRA como material (mismo lanzador neutro que
    # evergreen/noticias). El depósito rellena las filas vacías recién creadas.
    try:
        gen = gen_dom.lanzar_copy(
            tipo="copy",
            origen_historial="presidencia",
            marca=marca,
            contexto=texto[: gen_dom.MAX_TEXTO],
            redes_ids=list(redes.redes_de_formato(redes.FORMATO_CARRUSEL)),
            titulo=titulo,
            titulo_dado=titulo,
            texto_base=texto[: gen_dom.MAX_TEXTO],
            autor=autor,
            publicacion_id=item["id"],
            # Lo de presidencia corre prisa: adelanta al lote de fondo de la cola.
            urgente=True,
        )
    except generaciones.ColaLlenaError:
        # El tema y su pieza YA existen (con su media); solo faltó encolar el copy. Se
        # informa con claridad: el equipo puede relanzar el copy desde la pieza.
        return JSONResponse(
            {
                "error": (
                    "La nota se guardó pero hay demasiadas generaciones en curso; "
                    "lanza el copy desde la pieza del feed en unos segundos."
                ),
                "publicacion_id": item["id"],
            },
            status_code=429,
        )

    return JSONResponse(
        {
            "nota": _nota_a_dict(item, "generando"),
            "publicacion_id": item["id"],
            "generacion": gen,
        }
    )


RUTAS = [
    Route("/api/presidencia/notas", listar, methods=["GET"]),
    Route("/api/presidencia/notas", crear, methods=["POST"]),
]
