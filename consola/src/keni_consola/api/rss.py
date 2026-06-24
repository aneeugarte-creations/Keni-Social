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
    `redes_def`/`redes` solo redes canonicas; `prompt` solo de la allowlist de la Texto.
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

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import marcas, redes, repos
from .._http_json import leer_json
from ..dominio import fuentes_pesos, http_feed

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
# que piezas.
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
        # Categoría del feed: manda la CADENCIA de sondeo del motor y la cobertura de /salud.
        "categoria": fuente.get("categoria", ""),
        # Línea editorial a la que cuelga el feed (consolidación de líneas); '' = catch-all.
        "linea_id": fuente.get("linea_id", ""),
        # Peso editorial (pondera la corroboración del ranking) + su tier legible.
        "peso": float(fuente.get("peso") or 1.0),
        "tier": fuentes_pesos.tier_de_peso(float(fuente.get("peso") or 1.0)),
    }


# Categorías VÁLIDAS de un feed: el vocabulario editorial canónico + 'breaking' (la cadencia
# más agresiva del motor). DESACOPLADO de lo que traigan los presets iniciales: el equipo puede
# crear una fuente en cualquier categoría editorial aunque esos presets no incluyan ninguna de
# ella. La categoría manda la cadencia de sondeo (`config.ingesta_intervalo_categoria`) y la
# detección de huecos de /salud; '' = sin categoría (cadencia por defecto).
def _categorias_validas() -> frozenset[str]:
    from ..dominio import fuentes_presets

    return frozenset([*fuentes_presets.CATEGORIAS_VALIDAS, "breaking"])


def _validar_categoria(valor: Any) -> tuple[str | None, str | None]:
    """Valida la categoría del cuerpo: '' o una de la allowlist. `(categoria, error)`."""
    if valor is None:
        valor = ""
    if not isinstance(valor, str):
        return None, "La categoría debe ser texto."
    valor = valor.strip().lower()
    if valor and valor not in _categorias_validas():
        return None, "Categoría no permitida."
    return valor, None


def _validar_peso(valor: Any) -> tuple[float | None, str | None]:
    """Valida el peso editorial: numérico y dentro del rango admisible. `(peso, error)`.

    Se exige el rango explícito (no se clampa en silencio): un peso fuera de
    [PESO_MIN, PESO_MAX] casi siempre es un error de dedo y conviene avisar.
    """
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None, "El peso de la fuente debe ser un número."
    peso = float(valor)
    if not (fuentes_pesos.PESO_MIN <= peso <= fuentes_pesos.PESO_MAX):
        return None, (
            f"El peso debe estar entre {fuentes_pesos.PESO_MIN} y {fuentes_pesos.PESO_MAX}."
        )
    return peso, None


async def listar_fuentes(request: Request) -> Response:
    """Listado de fuentes RSS.

    `?marca=` filtra por marca (sus fuentes + las compartidas); vacio = todas.
    """
    marca = (request.query_params.get("marca") or "").strip()
    if marca and not marcas.es_marca(marca):
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)
    cuerpo = await run_in_threadpool(_listar_fuentes, marca)
    return JSONResponse(cuerpo)


def _listar_fuentes(marca: str) -> dict:
    fuentes = repos.listar_fuentes_rss(marca=marca or None)
    return {"fuentes": [_fuente_a_dict(f) for f in fuentes]}


def _validar_linea_id(valor: object, marca: str) -> tuple[str | None, str | None]:
    """'' (catch-all "General") es válido; si llega un id debe ser una LÍNEA (clase `categoria`)
    de la marca de la fuente (o global)."""
    if valor in (None, ""):
        return "", None
    if not isinstance(valor, str):
        return None, "Línea no válida."
    et = repos.obtener_etiqueta(valor.strip())
    if et is None or et.get("clase") != "categoria":
        return None, "Esa línea no existe."
    if (et.get("marca") or "") not in ("", marca):
        return None, "La línea no pertenece a esta marca."
    return valor.strip(), None


def _crear_fuente(datos: dict) -> tuple[int, dict]:
    nombre = datos.get("nombre")
    if not isinstance(nombre, str) or not nombre.strip():
        return 400, {"error": "El nombre de la fuente es obligatorio."}
    url, error = validar_url(datos.get("url"))
    if error is not None:
        return 400, {"error": error}
    marca, error = _validar_marca(datos.get("marca", ""))
    if error is not None:
        return 400, {"error": error}
    incluir, error = _validar_filtro(datos.get("incluir"), "inclusión")
    if error is not None:
        return 400, {"error": error}
    excluir, error = _validar_filtro(datos.get("excluir"), "exclusión")
    if error is not None:
        return 400, {"error": error}
    redes_def, error = _validar_redes_def(datos.get("redes_def"))
    if error is not None:
        return 400, {"error": error}
    categoria, error = _validar_categoria(datos.get("categoria"))
    if error is not None:
        return 400, {"error": error}
    linea_id, error = _validar_linea_id(datos.get("linea_id"), marca or "")
    if error is not None:
        return 400, {"error": error}
    # Peso editorial: explícito en el cuerpo, o el SEED por host de la url (Reuters/BBC/…
    # nacen potentes sin que nadie lo configure; el equipo lo puede corregir después).
    if datos.get("peso") is not None:
        peso, error = _validar_peso(datos.get("peso"))
        if error is not None:
            return 400, {"error": error}
    else:
        peso = fuentes_pesos.peso_de_url(url or "")

    fuente = repos.crear_fuente_rss(
        nombre.strip(),
        url,
        marca=marca,
        incluir=incluir,
        excluir=excluir,
        redes_def=redes_def,
        propia=bool(datos.get("propia")),
        categoria=categoria or "",
        linea_id=linea_id or "",
        peso=peso or 1.0,
    )
    return 200, {"fuente": _fuente_a_dict(fuente)}


async def crear_fuente(request: Request) -> Response:
    """Crea una fuente `{nombre, url, marca?, incluir?, excluir?, redes_def?}` -> `{fuente}`.

    Valida URL + SSRF; la fuente nace activa. `incluir`/`excluir` son CSV de
    terminos; `redes_def` una lista de ids de red por defecto.
    """
    datos = await leer_json(request)
    status, cuerpo = await run_in_threadpool(_crear_fuente, datos)
    return JSONResponse(cuerpo, status_code=status)


def _actualizar_fuente(fuente_id: str, datos: dict) -> tuple[int, dict]:
    actual = repos.obtener_fuente_rss(fuente_id)
    if actual is None:
        return 404, {"error": "Esa fuente ya no existe."}
    campos: dict[str, Any] = {}

    if "nombre" in datos:
        nombre = datos.get("nombre")
        if not isinstance(nombre, str) or not nombre.strip():
            return 400, {"error": "El nombre de la fuente es obligatorio."}
        campos["nombre"] = nombre.strip()
    if "url" in datos:
        url, error = validar_url(datos.get("url"))  # re-valida URL + SSRF
        if error is not None:
            return 400, {"error": error}
        campos["url"] = url
    if "marca" in datos:
        marca, error = _validar_marca(datos.get("marca"))
        if error is not None:
            return 400, {"error": error}
        campos["marca"] = marca
    if "activo" in datos:
        campos["activo"] = bool(datos.get("activo"))
    if "incluir" in datos:
        incluir, error = _validar_filtro(datos.get("incluir"), "inclusión")
        if error is not None:
            return 400, {"error": error}
        campos["incluir"] = incluir
    if "excluir" in datos:
        excluir, error = _validar_filtro(datos.get("excluir"), "exclusión")
        if error is not None:
            return 400, {"error": error}
        campos["excluir"] = excluir
    if "redes_def" in datos:
        redes_def, error = _validar_redes_def(datos.get("redes_def"))
        if error is not None:
            return 400, {"error": error}
        campos["redes_def"] = redes_def
    if "propia" in datos:
        campos["propia"] = bool(datos.get("propia"))
    if "categoria" in datos:
        categoria, error = _validar_categoria(datos.get("categoria"))
        if error is not None:
            return 400, {"error": error}
        campos["categoria"] = categoria
    if "linea_id" in datos:
        # La línea se valida contra la marca resultante (la nueva si se cambia, o la actual).
        marca_ref = str(campos.get("marca", actual.get("marca") or ""))
        linea_id, error = _validar_linea_id(datos.get("linea_id"), marca_ref)
        if error is not None:
            return 400, {"error": error}
        campos["linea_id"] = linea_id
    if "peso" in datos:
        peso, error = _validar_peso(datos.get("peso"))
        if error is not None:
            return 400, {"error": error}
        campos["peso"] = peso

    fuente = repos.actualizar_fuente_rss(fuente_id, campos)
    if fuente is None:
        return 404, {"error": "Esa fuente ya no existe."}
    return 200, {"fuente": _fuente_a_dict(fuente)}


async def actualizar_fuente(request: Request) -> Response:
    """Edita parcialmente una fuente `{nombre?,url?,marca?,activo?,incluir?,excluir?,redes_def?}`.

    -> `{fuente}` | 404. Si cambia la `url`, se RE-VALIDA URL + guard SSRF (defensa
    en profundidad). Solo se tocan los campos presentes en el cuerpo.
    """
    fuente_id = request.path_params["fuente_id"]
    datos = await leer_json(request)
    status, cuerpo = await run_in_threadpool(_actualizar_fuente, fuente_id, datos)
    return JSONResponse(cuerpo, status_code=status)


def _borrar_fuente(fuente_id: str) -> tuple[int, dict]:
    if not repos.borrar_fuente_rss(fuente_id):
        return 404, {"error": "Esa fuente ya no existe."}
    return 200, {"mensaje": "Fuente borrada."}


async def borrar_fuente(request: Request) -> Response:
    fuente_id = request.path_params["fuente_id"]
    status, cuerpo = await run_in_threadpool(_borrar_fuente, fuente_id)
    return JSONResponse(cuerpo, status_code=status)


# --------------------------------------------------------------------------- #
# Endpoints: items (lectura en vivo del feed)                                  #
# --------------------------------------------------------------------------- #




RUTAS = [
    Route("/api/rss/fuentes", listar_fuentes, methods=["GET"]),
    Route("/api/rss/fuentes", crear_fuente, methods=["POST"]),
    Route("/api/rss/fuentes/{fuente_id}", actualizar_fuente, methods=["PUT"]),
    Route("/api/rss/fuentes/{fuente_id}", borrar_fuente, methods=["DELETE"]),
]
