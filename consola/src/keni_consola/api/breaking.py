"""API del Carril Rápido de Breaking — Claro Sports.

Superficie para que el equipo de Claro Sports atienda breaking news al instante:
lista los temas del Radar marcados como `breaking` (señal acelerando AHORA) y
permite preparar un borrador de copy con un tap. SÓLO PROPONE; nunca publica.

ENDPOINTS
---------
  GET  /api/breaking?marca=claro-sports
    → `{ "items": [ <BreakingItem>, … ] }`
    Temas breaking del snapshot del Investigador para la marca, con su estado de
    borrador: "ninguno" / "generando" / "listo". Se cruza con el tablero para saber
    si ya hay un draft creado.

  POST /api/breaking/preparar
    Body: `{ "titulo": str, "marca": str, "redes": [str]? }`
    Crea un DRAFT `contenido` (flujo='importante', prioridad='alta', origen='breaking')
    y encola la generación de copy reusando `autogen_redactar.lanzar_para_topic` (el mismo
    camino que el botón manual del asistente y que el radar). NUNCA publica.
    → `{ "publicacion_id": str, "generacion_id": str }`

SEGURIDAD
---------
  - Requiere sesión válida (middleware global).
  - `marca` se valida contra el catálogo.
  - `titulo` se recorta (never fstring de entrada).
  - El borrador nace `pendiente`/`en_revision`; la publicación real sigue gated
    por `KENI_PUBLICAR_REAL` (OFF por defecto).
"""

from __future__ import annotations

import logging

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import autogen_redactar, marcas, redes, repos
from ._guardas import redactar_apagado
from .._http_json import leer_json
from ..dominio import breaking as dom_breaking
from ..estados import FLUJO_IMPORTANTE
from ..seguridad import autor_de_peticion
from ..tiempo import hoy_utc

_log = logging.getLogger("keni_consola.api.breaking")

_MAX_TITULO = 300

# Geo por defecto para consultar el snapshot del Investigador (mismo que el daemon).
_GEO_DEFECTO = "MX"

# Origen con el que se crean los borradores de breaking.
ORIGEN_BREAKING = "breaking"


async def listar(request: Request) -> Response:
    """GET /api/breaking?marca=<id>[&geo=MX]

    Devuelve los temas del snapshot del Investigador marcados como `breaking=True`
    para la marca indicada, ordenados por señal descendente. Cada item incluye su
    `estado_borrador` ("ninguno" | "generando" | "listo"), `publicacion_id` y
    `generacion_id` (si hay borrador/generación activa).

    Si el Investigador no está activo (KENI_INVESTIGADOR off) o la marca no tiene
    snapshot, devuelve `items=[]` sin error (safe-by-default).
    """
    marca_crudo = (request.query_params.get("marca") or "").strip()
    if not marca_crudo:
        return JSONResponse({"error": "El parámetro 'marca' es obligatorio."}, status_code=400)
    if not marcas.es_marca(marca_crudo):
        return JSONResponse({"error": "Marca no válida."}, status_code=400)

    geo = (request.query_params.get("geo") or _GEO_DEFECTO).strip().upper()
    if not geo:
        geo = _GEO_DEFECTO

    cuerpo = await run_in_threadpool(_listar, marca_crudo, geo)
    return JSONResponse(cuerpo)


def _listar(marca_crudo: str, geo: str) -> dict:
    items = dom_breaking.items_breaking(marca_crudo, geo)

    # Anota IN-PLACE: estado_borrador / publicacion_id / generacion_id.
    dom_breaking.anotar_estado_borrador(items, marca_crudo)

    # Serializar: extraer sólo los campos públicos del contrato.
    publicos = [_serializar_item(it, marca_crudo) for it in items]

    return {"items": publicos}


def _serializar_item(item: dict, marca: str) -> dict:
    """Extrae los campos públicos de un item breaking."""
    fuentes = item.get("fuentes")
    if isinstance(fuentes, str):
        import json as _json
        try:
            fuentes = _json.loads(fuentes)
        except Exception:  # noqa: BLE001
            fuentes = [fuentes] if fuentes else []
    elif not isinstance(fuentes, list):
        fuentes = []

    enlaces = item.get("enlaces")
    if isinstance(enlaces, str):
        import json as _json
        try:
            enlaces = _json.loads(enlaces)
        except Exception:  # noqa: BLE001
            enlaces = []
    elif not isinstance(enlaces, list):
        enlaces = []

    return {
        "titulo": (item.get("titulo") or "").strip(),
        "marca": marca,
        "marca_nombre": marcas.etiqueta_de(marca) if marca else "",
        "senal": int(item.get("senal") or 0),
        "senal_texto": (item.get("senal_texto") or "").strip(),
        "breaking": True,
        "idioma": (item.get("idioma") or "es"),
        "fuentes": fuentes,
        "enlaces": enlaces,
        "fecha": (item.get("actualizado") or item.get("creado") or "").strip(),
        # Estado del borrador: "ninguno" | "generando" | "listo"
        "estado_borrador": item.get("estado_borrador", "ninguno"),
        "publicacion_id": item.get("publicacion_id", ""),
        "generacion_id": item.get("generacion_id", ""),
    }


async def preparar(request: Request) -> Response:
    """POST /api/breaking/preparar

    Body: `{ "titulo": str, "marca": str, "redes"?: [str] }`

    Crea un DRAFT `contenido` con `origen='breaking'`, `flujo='importante'`,
    `prioridad='alta'` y lanza la generación de copy en segundo plano reusando
    `autogen_redactar.lanzar_para_topic` (el mismo camino que el botón manual del
    asistente). NUNCA publica: el borrador
    nace sin aprobación y pasa por el flujo de revisión humana normal.

    Devuelve `{ "publicacion_id": str, "generacion_id": str }`.
    Si ya existe un borrador para ese título + marca (mismo `origen='breaking'`),
    lo devuelve sin crear uno duplicado (dedup por clave).
    """
    datos = await leer_json(request)

    titulo = datos.get("titulo")
    if not isinstance(titulo, str) or not titulo.strip():
        return JSONResponse({"error": "El título es obligatorio."}, status_code=400)
    titulo = titulo.strip()[:_MAX_TITULO]

    marca_crudo = datos.get("marca")
    if not isinstance(marca_crudo, str) or not marca_crudo.strip():
        return JSONResponse({"error": "La marca es obligatoria."}, status_code=400)
    marca_crudo = marca_crudo.strip()
    if not marcas.es_marca(marca_crudo):
        return JSONResponse({"error": "Marca no válida."}, status_code=400)
    # Preparar SIEMPRE encola copy: si «Redactar» está apagada para la marca, no creamos nada.
    err = redactar_apagado(marca_crudo)
    if err:
        return JSONResponse(err, status_code=409)

    redes_crudo = datos.get("redes", [])
    if not isinstance(redes_crudo, list):
        redes_crudo = []
    redes_ids = [r for r in redes_crudo if isinstance(r, str) and redes.es_red(r)]

    autor = autor_de_peticion(request)
    cuerpo = await run_in_threadpool(_preparar, titulo, marca_crudo, redes_ids, autor)
    return JSONResponse(cuerpo)


def _preparar(titulo: str, marca_crudo: str, redes_ids: list[str], autor: object) -> dict:
    # --- Dedup: si ya existe un borrador breaking para este título+marca, no duplicar ---
    clave = dom_breaking.clave_de_titulo(titulo)
    existente_id = ""
    if clave:
        try:
            todos = repos.listar_publicacion(marca=marca_crudo, clase="contenido")
            for it in todos:
                if (it.get("origen") or "") != ORIGEN_BREAKING:
                    continue
                clave_it = dom_breaking.clave_de_titulo((it.get("titulo") or "").strip())
                if clave_it == clave:
                    existente_id = it.get("id") or ""
                    break
        except Exception:  # noqa: BLE001
            _log.exception("breaking/preparar: fallo al comprobar dedup (marca=%s)", marca_crudo)

    if existente_id:
        # Devuelve el existente con su generación activa.
        gen_id, _ = dom_breaking._generacion_reciente_de(existente_id)
        return {"publicacion_id": existente_id, "generacion_id": gen_id}

    # --- Crear el borrador ---
    item = repos.crear_publicacion(
        clase="contenido",
        flujo=FLUJO_IMPORTANTE,
        titulo=titulo,
        descripcion="",
        marca=marca_crudo,
        prioridad="alta",
        fecha_objetivo=hoy_utc().isoformat(),
        autor=autor,
        origen=ORIGEN_BREAKING,
        tipo_contenido="fuente",
    )

    # Crear plataformas (si se indicaron redes; si no, sin plataformas hasta que el copia llega).
    for red in dict.fromkeys(redes_ids):
        repos.crear_pieza_fila(
            publicacion_id=item["id"], red=red, falta_copy=True, falta_imagen=True
        )

    # --- Encolar generación de copy (reusa autogen_redactar.lanzar_para_topic) ---
    gen_id = ""
    try:
        gen = autogen_redactar.lanzar_para_topic(item, manual=True)
        if gen:
            gen_id = gen.get("id") or ""
    except Exception:  # noqa: BLE001 -- la generación es opcional; nunca tumba la preparación
        _log.exception(
            "breaking/preparar: fallo al encolar la generación (publicacion_id=%s)", item["id"]
        )

    return {"publicacion_id": item["id"], "generacion_id": gen_id}


RUTAS = [
    Route("/api/breaking", listar, methods=["GET"]),
    Route("/api/breaking/preparar", preparar, methods=["POST"]),
]
