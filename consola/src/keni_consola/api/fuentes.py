"""API del HUB de fuentes (item G): TODAS las fuentes de insumo, no solo RSS.

Convierte "Fuentes" en el lugar donde se dan de alta fuentes de cualquier `tipo`
(rss/idea/interna), cada una con su `config` (JSON especifico del tipo),
`prioridad` y `etiquetas`. Es ADITIVO: `fuentes_rss` sigue siendo la fuente de verdad del
Radar v1; este hub se siembra de ella (migracion idempotente en `db._sembrar_fuentes_hub_
desde_rss`) y NO la sustituye.

  - GET  /api/fuentes?tipo=         -> {fuentes:[...], agencias:[...], pendientes:[...]}
  - POST /api/fuentes               -> crea una fuente {tipo, nombre, config?, marca?,
                                       prioridad?, etiquetas?}
  - PUT  /api/fuentes/{id}          -> edita parcialmente
  - DELETE /api/fuentes/{id}        -> borra

Las fuentes "standing" (rss/interna configurada) son CONFIGURABLES y se guardan en el hub.
(Las aportaciones manuales "Idea" e "Interno AMX" se mudaron a Contenidos, al banco de ideas
evergreen; ya no viven aqui.)

Las AGENCIAS (Reuters/AFP, item F) se exponen como su estado HONESTO (`agencias`): cada una
disponible o "pendiente/no configurada" segun haya credencial, sin inventar nada. Validacion:
`tipo` de una allowlist, `marca` del catalogo unico, `config` un objeto JSON. Errores en
espanol; SQL parametrizado en `db`.
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import agencias, marcas, repos
from .._http_json import leer_json
from ..db_noticias import _TIPOS_FUENTE
from ..dominio import fuentes_presets, http_feed

_MARCAS_IDS = {m[0] for m in marcas.opciones()}


def _validar_marca(marca: Any) -> tuple[str | None, str | None]:
    if marca is None:
        marca = ""
    if not isinstance(marca, str):
        return None, "La marca debe ser texto."
    if marca and marca not in _MARCAS_IDS:
        return None, "Marca no permitida."
    return marca, None


def _fuente_rss_a_hub(fuente: dict[str, Any]) -> dict[str, Any]:
    """Presenta un feed `fuentes_rss` (la fuente de verdad del motor de ingesta) con la forma
    del catálogo de fuentes (tipo='rss'): la vista "Todas" lo consume sin cambios."""
    marca = fuente.get("marca", "")
    categoria = (fuente.get("categoria") or "").strip()
    return {
        "id": fuente["id"],
        "tipo": "rss",
        "nombre": fuente.get("nombre", ""),
        "config": {"url": fuente.get("url", "")},
        "marca": marca,
        "marca_nombre": marcas.etiqueta_de(marca) if marca else "",
        "prioridad": int(fuente.get("prioridad", 0) or 0),
        "etiquetas": [categoria] if categoria else [],
        "activo": bool(fuente.get("activo", True)),
        "creado": fuente.get("creado", ""),
    }


async def listar(request: Request) -> Response:
    """`GET /api/fuentes?tipo=` -> fuentes configuradas + estado de agencias + pendientes.

    Lee `fuentes_rss` (la fuente de verdad del motor de ingesta) y la presenta como el
    catálogo de fuentes (tipo='rss'); ya no hay una tabla-hub espejo aparte. Agencias
    (Reuters/AFP) y pendientes informan su estado honesto.
    """
    tipo = request.query_params.get("tipo") or None
    if tipo is not None and tipo not in _TIPOS_FUENTE:
        return JSONResponse({"error": "Tipo de fuente no permitido."}, status_code=400)
    marca, error = _validar_marca(request.query_params.get("marca"))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)
    fuentes_rss = (
        repos.listar_fuentes_rss(marca=marca or None) if tipo in (None, "rss") else []
    )
    return JSONResponse(
        {
            "fuentes": [_fuente_rss_a_hub(f) for f in fuentes_rss],
            "tipos": list(_TIPOS_FUENTE),
            "agencias": [agencias.estado_fuente(a) for a in ("reuters", "afp")],
            "pendientes": agencias.fuentes_pendientes(),
        }
    )


async def reactivar(request: Request) -> Response:
    """`POST /api/fuentes/{id}/reactivar` -> reactiva un feed RSS auto-desactivado (Ola D).

    Opera sobre `fuentes_rss` (la fuente de verdad del motor de ingesta): `activo=1`,
    `desactivado_auto=0`, `errores_seguidos=0`, `proximo_sondeo=''` (reintentar YA). Idempotente.
    404 si el feed no existe.
    """
    fuente_id = request.path_params["fuente_id"]
    if repos.obtener_fuente_rss(fuente_id) is None:
        return JSONResponse({"error": "Esa fuente ya no existe."}, status_code=404)
    fuente = repos.actualizar_fuente_rss(
        fuente_id,
        {
            "activo": True,
            "desactivado_auto": False,
            "errores_seguidos": 0,
            "proximo_sondeo": "",
        },
    )
    if fuente is None:
        return JSONResponse({"error": "Esa fuente ya no existe."}, status_code=404)
    return JSONResponse({"fuente": fuente})


# --------------------------------------------------------------------------- #
# Catálogo de presets (Ola 4 — fuentes externas)                               #
# --------------------------------------------------------------------------- #


def _urls_activas() -> set[str]:
    """Conjunto de URLs que ya tienen una fuente RSS dada de alta (para marcar `activa`)."""
    fuentes = repos.listar_fuentes_rss()
    return {str(f.get("url", "")).strip() for f in fuentes if f.get("url")}


async def listar_presets_handler(request: Request) -> Response:
    """`GET /api/fuentes/presets?categoria=` -> presets del catálogo con `activa: bool`.

    `activa` es True si ya existe una `fuentes_rss` con esa URL exacta.
    """
    categoria = (request.query_params.get("categoria") or "").strip() or None
    marca, error = _validar_marca(request.query_params.get("marca"))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)
    todos = fuentes_presets.listar_presets(categoria=categoria, marca=marca or None)
    urls = _urls_activas()
    for p in todos:
        p["activa"] = p.get("url", "") in urls
    return JSONResponse(
        {
            "presets": todos,
            "categorias": fuentes_presets.categorias(),
        }
    )


async def activar_presets_handler(request: Request) -> Response:
    """`POST /api/fuentes/presets/activar` -> crea fuentes RSS para los presets elegidos.

    Cuerpo: `{ids: ["preset-id", ...], marca?: ""}`.
    - Para cada preset, valida la URL con el guard SSRF y crea una `fuentes_rss`.
    - Idempotente por URL: si ya existe una fuente con esa URL, se omite (no duplica).
    - Si no se pasa `marca`, usa `marca_sugerida` del preset. Igual con `linea_sugerida`.
    - Devuelve `{creadas: n, fuentes: [...], omitidas: n}`.
    """
    datos = await leer_json(request)

    ids_raw = datos.get("ids")
    if not isinstance(ids_raw, list) or not ids_raw:
        return JSONResponse({"error": "El campo 'ids' es obligatorio y debe ser una lista."}, status_code=400)
    if not all(isinstance(i, str) for i in ids_raw):
        return JSONResponse({"error": "Los ids de preset deben ser texto."}, status_code=400)

    # Marca opcional: si se pasa, sobrescribe la marca_sugerida del preset.
    marca_override = datos.get("marca")
    if marca_override is not None:
        if not isinstance(marca_override, str):
            return JSONResponse({"error": "La marca debe ser texto."}, status_code=400)
        marca_override = marca_override.strip()
        if marca_override and marca_override not in _MARCAS_IDS:
            return JSONResponse({"error": "Marca no permitida."}, status_code=400)
    else:
        marca_override = None  # usar marca_sugerida del preset

    # URLs ya activas -> idempotencia.
    urls_activas = _urls_activas()

    creadas: list[dict[str, Any]] = []
    omitidas = 0
    errores: list[str] = []

    for preset_id in ids_raw:
        preset = fuentes_presets.obtener_preset(preset_id.strip())
        if preset is None:
            errores.append(f"Preset '{preset_id}' no existe en el catálogo.")
            continue

        url_preset = preset.get("url", "")

        # Idempotente: ya existe una fuente con esta URL -> omitir.
        if url_preset in urls_activas:
            omitidas += 1
            continue

        # Guard SSRF antes de persistir.
        url_limpia, err_url = http_feed.validar_url(url_preset)
        if err_url is not None:
            errores.append(f"Preset '{preset_id}': {err_url}")
            continue

        # Marca: override del body > marca_sugerida del preset > "" (compartida).
        if marca_override is not None:
            marca = marca_override
        else:
            m_sug = (preset.get("marca_sugerida") or "").strip()
            marca = m_sug if m_sug in _MARCAS_IDS else ""

        nombre = preset.get("nombre", preset_id)

        fuente = repos.crear_fuente_rss(
            nombre,
            url_limpia,
            marca=marca,
            incluir="",
            excluir="",
            redes_def="",
        )
        # Añade a las ya activas para que iteraciones posteriores en este mismo request
        # sean idempotentes (misma URL pedida dos veces -> solo se crea una).
        urls_activas.add(url_limpia)
        # Enriquece la respuesta con el idioma/región del preset.
        fuente_resp = {
            **fuente,
            "idioma": preset.get("idioma", ""),
            "region": preset.get("region", ""),
            "categoria": preset.get("categoria", ""),
        }
        creadas.append(fuente_resp)

    respuesta: dict[str, Any] = {
        "creadas": len(creadas),
        "fuentes": creadas,
        "omitidas": omitidas,
    }
    if errores:
        respuesta["errores"] = errores
    return JSONResponse(respuesta)


RUTAS = [
    Route("/api/fuentes", listar, methods=["GET"]),
    Route("/api/fuentes/presets", listar_presets_handler, methods=["GET"]),
    Route("/api/fuentes/presets/activar", activar_presets_handler, methods=["POST"]),
    Route("/api/fuentes/{fuente_id}/reactivar", reactivar, methods=["POST"]),
]
