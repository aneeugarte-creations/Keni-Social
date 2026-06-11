"""Handler del ALTA DIRECTA de un post (`/api/contenido/post-directo`).

El equipo crea un post DESDE CERO tecleando el COPY FINAL. Es el mismo motor por el que
nacen las piezas al usar una noticia/investigación (un tema del tablero + un borrador por
red depositado por el contrato del copy, `dominio.publicaciones.crear_borrador_en`), solo
que sin generación: el copy ya lo trae el humano. Ver el docstring de `crear_post_directo`.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ...dominio import publicaciones as dom_publicaciones
from ...estados import ORIGEN_POST_DIRECTO
from ...tiempo import hoy_utc
from ._comun import (
    _MAX_TEXTO,
    _MAX_TITULO,
    _contenido_a_dict,
    _validar_marca,
    auto_responsable,
    autor_de_peticion,
    leer_json,
    redes,
    repos,
)

# Rótulo de la idea en el feed cuando el equipo no da título: la primera línea del copy,
# acotada (un copy entero como título gritaría en la cabecera de grupo del feed).
_MAX_TITULO_DERIVADO = 120


def _titulo_desde_copy(copy: str) -> str:
    """Primera línea no vacía del copy, acotada, como título derivado."""
    primera = next((ln.strip() for ln in copy.splitlines() if ln.strip()), "")
    return primera[:_MAX_TITULO_DERIVADO]


async def crear_post_directo(request: Request) -> Response:
    """POST /api/contenido/post-directo: un post desde cero con el copy FINAL del equipo.

    Cuerpo (JSON):
      - `copy` (OBLIGATORIO): el texto final de la publicación, tal cual lo teclea el humano.
      - `marca` (OBLIGATORIA): sin marca la pieza no entra al flujo (igual que en `aportar`).
      - `titulo` (opcional): rótulo de la idea en el feed; si falta se deriva del copy.
      - `redes` (opcional): ids canónicos destino; por defecto las del formato foto (las
        mismas a las que el flujo automático manda una pieza).

    Crea el tema padre (`origen='post-directo'`, EXCLUIDO de la auto-generación de copy:
    aquí no hay nada que redactar) y deposita UNA pieza-borrador por red con el copy dado,
    por el MISMO contrato que usa el post-procesado del copy IA
    (`dominio.publicaciones.crear_borrador_en`): la pieza nace `borrador` con
    `falta_copy=False` y `falta_imagen=True`, aparece en el feed y sigue el flujo normal
    (arte por red, revisión, programación). -> `{contenido}` | 400.
    """
    datos = await leer_json(request)

    copy = datos.get("copy")
    if not isinstance(copy, str) or not copy.strip():
        return JSONResponse({"error": "El post necesita un copy."}, status_code=400)
    copy = copy.strip()[:_MAX_TEXTO]

    marca, err = _validar_marca(datos.get("marca"))
    if err:
        return JSONResponse({"error": err}, status_code=400)
    if not marca:
        return JSONResponse(
            {"error": "Elige una marca: el post necesita una marca para entrar al flujo."},
            status_code=400,
        )

    titulo = datos.get("titulo")
    titulo = titulo.strip() if isinstance(titulo, str) else ""
    if len(titulo) > _MAX_TITULO:
        return JSONResponse({"error": "El título es demasiado largo."}, status_code=400)
    if not titulo:
        titulo = _titulo_desde_copy(copy)

    crudas = datos.get("redes", [])
    if not isinstance(crudas, list):
        crudas = []
    redes_objetivo = [r for r in dict.fromkeys(crudas) if isinstance(r, str) and r]
    # Solo redes sociales canónicas (sin el canal "web" del tablero): cada red recibe una
    # PUBLICACIÓN de verdad, no una fila de checklist.
    if any(not redes.es_red(r) for r in redes_objetivo):
        return JSONResponse({"error": "Alguna red no es válida."}, status_code=400)
    if not redes_objetivo:
        redes_objetivo = list(redes.redes_de_formato("foto"))

    item = repos.crear_contenido(
        clase="contenido",
        titulo=titulo,
        marca=marca,
        prioridad="media",
        fecha_objetivo=hoy_utc().isoformat(),
        autor=autor_de_peticion(request),
        # Reparto automático desde la rota del día (mismo patrón que `aportar`): el equipo
        # solo crea; el reparto es automático. Degrada a None sin romper.
        responsable=auto_responsable.responsable_automatico(marca),
        origen=ORIGEN_POST_DIRECTO,
        formato="foto",
    )
    for red in redes_objetivo:
        dom_publicaciones.crear_borrador_en(item["id"], marca, red, titulo=titulo, contenido=copy)

    plataformas = repos.listar_contenido_plataforma(item["id"])
    return JSONResponse({"contenido": _contenido_a_dict(item, plataformas)})
