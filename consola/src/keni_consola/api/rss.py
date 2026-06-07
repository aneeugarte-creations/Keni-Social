"""API RSS: gestión de FUENTES RSS/Atom (CRUD + salud + filtros).

El SPA da de alta los feeds (un feed por marca, opcional) en la pestaña RSS de Fuentes.
Los ITEMS que esos feeds producen NO se sirven aquí: viven en el pool persistente de
Noticias (`/api/noticias`, motor de ingesta), donde se revisan y se usan. Este router
solo configura los CANALES; además re-exporta los helpers de parseo/lectura de
`dominio.http_feed` que reutilizan el Radar, las agencias y el Termómetro.

CAPACIDADES:
  - Fuentes: CRUD completo (incl. PUT parcial) + activar/desactivar (`activo`) +
    filtros por palabra clave (`incluir`/`excluir`, CSV) + redes por defecto
    (`redes_def`) + salud (ultima_actualizacion / ultimo_error / ultimo_conteo).

SEGURIDAD / VALIDACION:
  - `nombre` y `url` obligatorios al crear una fuente.
  - La URL SOLO puede ser `http`/`https` y se valida contra SSRF: se resuelve el host
    y se RECHAZA si apunta a loopback / rangos privados / link-local / etc. El guard
    se aplica al crear la fuente, al cambiar la url en el PUT, Y antes de cada descarga
    (defensa en profundidad: una IP puede cambiar de resolucion entre el alta y la
    lectura).
  - `marca` (si viene) SOLO del catalogo unico (`consola.marcas`, por su id canonico);
    `redes_def`/`redes` solo redes canonicas; `prompt` solo de la allowlist de la Biblioteca.
  - SQL parametrizado en `consola.db`; errores en espanol, sin tracebacks crudos.

DESCARGA Y PARSEO:
  - La descarga/parseo/guard-SSRF viven en la INFRA `dominio.http_feed` (capa sin
    Starlette, reutilizable por el dominio). `_DESCARGADOR` es el punto INYECTABLE/
    mockeable: en tests se parchea para NUNCA tocar la red. Limites: timeout, tamano
    maximo (leyendo en trozos) y maximo de items por feed.
  - El parseo usa la stdlib `xml.etree.ElementTree` (tolerante, sin deps nuevas):
    soporta RSS 2.0 (`<item>`) y Atom (`<entry>`). El resumen se recorta y se le
    quita el HTML. Si un feed falla, se OMITE con su error sin romper los demas.
  - Este router RE-EXPORTA los simbolos de `http_feed` (`validar_url`, `RSSError`,
    `parsear_feed`, `leer_items_fuente`, `_DESCARGADOR`, los helpers `_buscar_hijo`/
    `_texto_local`/`_quitar_ns`, etc.) para no romper a quien importe `rss.X`.
"""

from __future__ import annotations

import json
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import marcas, redes, repos
from .._http_json import leer_json
from ..dominio import http_feed

# Re-exportes de la infra de feeds (`dominio.http_feed`): la logica vive alli (sin
# Starlette), y aqui se re-expone para compatibilidad con quien importe `rss.X`. El
# `_DESCARGADOR` es una copia local que los tests parchean (`monkeypatch.setattr(rss,
# "_DESCARGADOR", ...)`); `_items_de_fuente`/`leer_items_fuente` de este modulo lo
# pasan explicitamente a la infra para que el parche siga siendo el punto inyectable.
RSSError = http_feed.RSSError
validar_url = http_feed.validar_url
parsear_feed = http_feed.parsear_feed
ordenar_items_por_fecha = http_feed.ordenar_items_por_fecha
fecha_a_orden = http_feed.fecha_a_orden
_FECHA_MINIMA = http_feed._FECHA_MINIMA
item_pasa_filtros = http_feed.item_pasa_filtros
_buscar_hijo = http_feed._buscar_hijo
_texto_local = http_feed._texto_local
_quitar_ns = http_feed._quitar_ns
_limpiar_resumen = http_feed._limpiar_resumen  # usado por `agencias._item`
_DESCARGADOR = http_feed._descargar_real


def leer_items_fuente(fuente: dict[str, Any]) -> list[dict[str, Any]]:
    """Descarga y parsea el feed de una fuente (via `http_feed`, con `_DESCARGADOR` local).

    Pasa el `_DESCARGADOR` de ESTE modulo a la infra para que el parche de tests
    (`monkeypatch.setattr(rss, "_DESCARGADOR", ...)`) siga siendo el punto inyectable.
    Propaga `RSSError`. Ver `dominio.http_feed.leer_items_fuente`.
    """
    return http_feed.leer_items_fuente(fuente, descargador=_DESCARGADOR)


# Marcas validas: TODAS las del catalogo unico (por su id canonico). Mismo criterio
# que publicaciones.
_MARCAS: tuple[tuple[str, str], ...] = tuple(marcas.opciones())
_MARCAS_IDS = {m[0] for m in _MARCAS}


def _validar_marca(marca: Any) -> tuple[str | None, str | None]:
    """Normaliza/valida una marca opcional. `(marca, None)` o `(None, mensaje)`."""
    if marca is None:
        marca = ""
    if not isinstance(marca, str):
        return None, "La marca debe ser texto."
    if marca and marca not in _MARCAS_IDS:
        return None, "Marca no permitida."
    return marca, None


def _validar_filtro(valor: Any, nombre: str) -> tuple[str | None, str | None]:
    """Normaliza un CSV de filtro (`incluir`/`excluir`). `(csv, None)` o `(None, msg)`.

    Acepta un string (se guarda tal cual) o una lista de strings (se une por comas).
    None/ausente => CSV vacio. Cualquier otro tipo => error en espanol.
    """
    if valor is None:
        return "", None
    if isinstance(valor, str):
        return valor.strip(), None
    if isinstance(valor, list) and all(isinstance(v, str) for v in valor):
        return ", ".join(v.strip() for v in valor if v.strip()), None
    return None, f"El filtro de {nombre} debe ser texto o una lista de términos."


def _validar_redes_def(valor: Any) -> tuple[str | None, str | None]:
    """Valida `redes_def` (lista de ids de red) y la serializa a JSON. `(json, None)`.

    None/ausente => '' (sin redes por defecto). Lista => se filtran ids contra las
    redes canonicas, en orden fijo, y se serializa a JSON. Cualquier id desconocido
    => error en espanol. Otro tipo => error.
    """
    if valor is None or valor == "":
        return "", None
    if not isinstance(valor, list) or not all(isinstance(v, str) for v in valor):
        return None, "Las redes por defecto deben ser una lista de identificadores."
    for r in valor:
        if not redes.es_red(r):
            return None, "Red no permitida."
    ordenadas = [r for r in redes.ids() if r in set(valor)]
    return json.dumps(ordenadas), None


# --------------------------------------------------------------------------- #
# Endpoints: fuentes (CRUD)                                                    #
# --------------------------------------------------------------------------- #


def _parsear_redes_def(crudo: Any) -> list[str]:
    """Parsea `redes_def` (JSON de ids) a una lista de ids de red canonicos y en orden.

    Tolerante: JSON invalido / no-lista / ids desconocidos => se descartan. El
    resultado respeta el orden fijo de `redes.REDES` (igual criterio que el copy).
    """
    if not crudo:
        return []
    if isinstance(crudo, list):
        datos = crudo
    elif isinstance(crudo, str):
        try:
            datos = json.loads(crudo)
        except (json.JSONDecodeError, ValueError):
            return []
    else:
        return []
    if not isinstance(datos, list):
        return []
    pedidas = {r for r in datos if isinstance(r, str) and redes.es_red(r)}
    return [r for r in redes.ids() if r in pedidas]


def _fuente_a_dict(fuente: dict[str, Any]) -> dict[str, Any]:
    """Serializa una fuente resolviendo el nombre de la marca y `redes_def` como lista."""
    return {
        "id": fuente["id"],
        "nombre": fuente["nombre"],
        "url": fuente["url"],
        "marca": fuente["marca"],
        "marca_nombre": marcas.etiqueta_de(fuente["marca"]) if fuente["marca"] else "",
        "activo": bool(fuente.get("activo", True)),
        "incluir": fuente.get("incluir", ""),
        "excluir": fuente.get("excluir", ""),
        "redes_def": _parsear_redes_def(fuente.get("redes_def", "")),
        "ultima_actualizacion": fuente.get("ultima_actualizacion", ""),
        "ultimo_error": fuente.get("ultimo_error", ""),
        "ultimo_conteo": fuente.get("ultimo_conteo", 0),
        # Sitio de marca propia: su imagen original es reutilizable al generar.
        "propia": bool(fuente.get("propia", False)),
    }


async def listar_fuentes(request: Request) -> Response:
    """Listado de fuentes RSS."""
    fuentes = repos.listar_fuentes_rss()
    return JSONResponse({"fuentes": [_fuente_a_dict(f) for f in fuentes]})


async def crear_fuente(request: Request) -> Response:
    """Crea una fuente `{nombre, url, marca?, incluir?, excluir?, redes_def?}` -> `{fuente}`.

    Valida URL + SSRF; la fuente nace activa. `incluir`/`excluir` son CSV de
    terminos; `redes_def` una lista de ids de red por defecto.
    """
    datos = await leer_json(request)
    nombre = datos.get("nombre")
    if not isinstance(nombre, str) or not nombre.strip():
        return JSONResponse({"error": "El nombre de la fuente es obligatorio."}, status_code=400)
    url, error = validar_url(datos.get("url"))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)
    marca, error = _validar_marca(datos.get("marca", ""))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)
    incluir, error = _validar_filtro(datos.get("incluir"), "inclusión")
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)
    excluir, error = _validar_filtro(datos.get("excluir"), "exclusión")
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)
    redes_def, error = _validar_redes_def(datos.get("redes_def"))
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)

    fuente = repos.crear_fuente_rss(
        nombre.strip(),
        url,
        marca=marca,
        incluir=incluir,
        excluir=excluir,
        redes_def=redes_def,
        propia=bool(datos.get("propia")),
    )
    return JSONResponse({"fuente": _fuente_a_dict(fuente)})


async def actualizar_fuente(request: Request) -> Response:
    """Edita parcialmente una fuente `{nombre?,url?,marca?,activo?,incluir?,excluir?,redes_def?}`.

    -> `{fuente}` | 404. Si cambia la `url`, se RE-VALIDA URL + guard SSRF (defensa
    en profundidad). Solo se tocan los campos presentes en el cuerpo.
    """
    fuente_id = request.path_params["fuente_id"]
    if repos.obtener_fuente_rss(fuente_id) is None:
        return JSONResponse({"error": "Esa fuente ya no existe."}, status_code=404)
    datos = await leer_json(request)
    campos: dict[str, Any] = {}

    if "nombre" in datos:
        nombre = datos.get("nombre")
        if not isinstance(nombre, str) or not nombre.strip():
            return JSONResponse(
                {"error": "El nombre de la fuente es obligatorio."}, status_code=400
            )
        campos["nombre"] = nombre.strip()
    if "url" in datos:
        url, error = validar_url(datos.get("url"))  # re-valida URL + SSRF
        if error is not None:
            return JSONResponse({"error": error}, status_code=400)
        campos["url"] = url
    if "marca" in datos:
        marca, error = _validar_marca(datos.get("marca"))
        if error is not None:
            return JSONResponse({"error": error}, status_code=400)
        campos["marca"] = marca
    if "activo" in datos:
        campos["activo"] = bool(datos.get("activo"))
    if "incluir" in datos:
        incluir, error = _validar_filtro(datos.get("incluir"), "inclusión")
        if error is not None:
            return JSONResponse({"error": error}, status_code=400)
        campos["incluir"] = incluir
    if "excluir" in datos:
        excluir, error = _validar_filtro(datos.get("excluir"), "exclusión")
        if error is not None:
            return JSONResponse({"error": error}, status_code=400)
        campos["excluir"] = excluir
    if "redes_def" in datos:
        redes_def, error = _validar_redes_def(datos.get("redes_def"))
        if error is not None:
            return JSONResponse({"error": error}, status_code=400)
        campos["redes_def"] = redes_def
    if "propia" in datos:
        campos["propia"] = bool(datos.get("propia"))

    fuente = repos.actualizar_fuente_rss(fuente_id, campos)
    if fuente is None:
        return JSONResponse({"error": "Esa fuente ya no existe."}, status_code=404)
    return JSONResponse({"fuente": _fuente_a_dict(fuente)})


async def borrar_fuente(request: Request) -> Response:
    fuente_id = request.path_params["fuente_id"]
    if not repos.borrar_fuente_rss(fuente_id):
        return JSONResponse({"error": "Esa fuente ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Fuente borrada."})


# --------------------------------------------------------------------------- #
# Endpoints: items (lectura en vivo del feed)                                  #
# --------------------------------------------------------------------------- #




RUTAS = [
    Route("/api/rss/fuentes", listar_fuentes, methods=["GET"]),
    Route("/api/rss/fuentes", crear_fuente, methods=["POST"]),
    Route("/api/rss/fuentes/{fuente_id}", actualizar_fuente, methods=["PUT"]),
    Route("/api/rss/fuentes/{fuente_id}", borrar_fuente, methods=["DELETE"]),
]
