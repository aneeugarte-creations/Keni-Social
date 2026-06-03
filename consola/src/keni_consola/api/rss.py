"""API RSS: fuentes RSS/Atom (CRUD + salud + filtros) + items (dedup) + generar copy.

El SPA guarda fuentes (un feed por marca, opcional) y lista sus items recientes para
que la persona elija cuales convertir en publicaciones. Persistencia de las FUENTES y
de los ITEMS YA USADOS en SQLite (`consola.db`); los ITEMS en si se leen del feed en
vivo (no se persisten, solo su `clave` cuando se marcan usados).

CAPACIDADES (RSS v2):
  - Fuentes: CRUD completo (incl. PUT parcial) + activar/desactivar (`activo`) +
    filtros por palabra clave (`incluir`/`excluir`, CSV) + redes por defecto
    (`redes_def`) + salud (ultima_actualizacion / ultimo_error / ultimo_conteo).
  - Items: `clave` estable por item (guid/id del feed, fallback al enlace), marcado
    de usado / dedup (`rss_items_vistos`) y filtros del feed aplicados al listar.
  - Generar: copy DIRECTO desde un item, reutilizando el AUTO-GUARDADO de Skills
    (`api.skills._responder_generacion`): crea historial + N publicaciones borrador.

SEGURIDAD / VALIDACION:
  - `nombre` y `url` obligatorios al crear una fuente.
  - La URL SOLO puede ser `http`/`https` y se valida contra SSRF: se resuelve el host
    y se RECHAZA si apunta a loopback / rangos privados / link-local / etc. El guard
    se aplica al crear la fuente, al cambiar la url en el PUT, Y antes de cada descarga
    (defensa en profundidad: una IP puede cambiar de resolucion entre el alta y la
    lectura).
  - `marca` (si viene) SOLO del catalogo unico (`consola.marcas`, por su id canonico);
    `redes_def`/`redes` solo redes canonicas; `skill` solo de la allowlist de Skills.
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

from .. import biblioteca, marcas, redes, repos
from .._http_json import leer_json
from ..dominio import dedup
from ..dominio import generar as gen_dom
from ..dominio import http_feed
from ..dominio import stream
from ..seguridad import autor_de_peticion

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
    resultado respeta el orden fijo de `redes.REDES` (igual criterio que Skills).
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


def _flag(request: Request, nombre: str) -> bool:
    """Lee un query param booleano (`1`/`true`/`si`/`yes` => True; ausente/otro => False)."""
    return (request.query_params.get(nombre) or "").strip().lower() in ("1", "true", "si", "yes")


def _items_de_fuente(
    fuente: dict[str, Any],
    *,
    ocultar_usados: bool,
    vistas: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Lee, filtra (incluir/excluir) y marca `usado` los items de UNA fuente.

    Aplica los filtros del feed sobre titulo+resumen, marca cada item segun
    `rss_items_vistos`, y con `ocultar_usados` omite los ya usados. Cada item sale
    como `{titulo, resumen, enlace, fecha, fuente_id, fuente_nombre, clave, usado}`.
    Propaga `RSSError` (la maneja el llamante para anotar el error y la salud).

    `vistas` (opcional): conjunto de claves ya usadas de ESTA fuente, ya resuelto por el
    llamante. Permite evitar el N+1 a Postgres (`repos.claves_vistas` por fuente DENTRO de
    un bucle): el descubrimiento (Radar) pasa `set()` porque NO necesita la marca `usado`
    (sus consumidores no la leen). Si es `None`, se consulta aqui (compat: feed unico).
    """
    crudos = leer_items_fuente(fuente)
    if vistas is None:
        vistas = repos.claves_vistas(fuente["id"])
    incluir = fuente.get("incluir", "")
    excluir = fuente.get("excluir", "")
    resultado: list[dict[str, Any]] = []
    for item in crudos:
        if not item_pasa_filtros(item, incluir, excluir):
            continue
        usado = item["clave"] in vistas if item["clave"] else False
        if ocultar_usados and usado:
            continue
        resultado.append({**item, "usado": usado})
    return resultado


async def listar_items(request: Request) -> Response:
    """Items recientes `?fuente=&ocultar_usados=0|1&incluir_inactivas=0|1`.

    -> `{items:[{titulo, resumen, enlace, fecha, fuente_id, fuente_nombre, clave,
    usado}], errores:[..]}`. Aplica los filtros incluir/excluir del feed, marca
    `usado` segun `rss_items_vistos` (y con `ocultar_usados=1` los omite). Solo lee
    feeds `activo` salvo `incluir_inactivas=1`. Tras descargar, ACTUALIZA la salud de
    la fuente (ultima_actualizacion/ultimo_conteo/ultimo_error). Un feed que falla se
    OMITE con su error sin romper los demas. Fuente concreta inexistente -> 404.
    """
    ocultar_usados = _flag(request, "ocultar_usados")
    incluir_inactivas = _flag(request, "incluir_inactivas")

    fuente_id = request.query_params.get("fuente") or None
    if fuente_id:
        fuente = repos.obtener_fuente_rss(fuente_id)
        if fuente is None:
            return JSONResponse({"error": "Esa fuente ya no existe."}, status_code=404)
        fuentes = [fuente]
    else:
        fuentes = repos.listar_fuentes_rss()

    if not incluir_inactivas:
        fuentes = [f for f in fuentes if f.get("activo", True)]

    # Descarga EN PARALELO (F0 rendimiento): cada fuente (descarga httpx sincrona + filtros)
    # corre en su hilo; un feed lento ya no bloquea a los demas. La marca `usado` se resuelve
    # por fuente DENTRO de cada hilo (`vistas=None`): aqui SI se usa (a diferencia del Radar),
    # asi que mantenemos la consulta por fuente, pero ahora en paralelo con la descarga (no
    # un N+1 serial). `mapear_en_paralelo` RECOMPONE el orden de `fuentes`; el resultado de
    # cada fuente es `(propios, error)` para omitir las caidas sin romper a las demas.
    def _trabajo(fuente: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
        try:
            return _items_de_fuente(fuente, ocultar_usados=ocultar_usados), None
        except RSSError as e:
            return [], str(e)
        except Exception:  # noqa: BLE001 -- nunca un traceback crudo; se omite la fuente
            return [], "No se pudo leer el feed."

    resultados = http_feed.mapear_en_paralelo(_trabajo, fuentes)

    items: list[dict[str, Any]] = []
    errores: list[dict[str, str]] = []
    # Las escrituras de salud a Postgres se hacen SECUENCIALES tras el abanico (evita abrir
    # muchas conexiones concurrentes); el orden sigue el de `fuentes` (determinista).
    for fuente, (propios, error) in zip(fuentes, resultados):
        if error is None:
            items.extend(propios)
            repos.registrar_salud_fuente_rss(fuente["id"], conteo=len(propios), error="")
        else:
            repos.registrar_salud_fuente_rss(fuente["id"], conteo=0, error=error)
            errores.append(
                {"fuente_id": fuente["id"], "fuente_nombre": fuente["nombre"], "error": error}
            )
    # Orden cronologico GLOBAL (mas nuevo arriba), no por feed/marca: tras acumular los
    # items de todas las fuentes se ordenan por su fecha. Los que no traen fecha parseable
    # caen al final (ver `fecha_a_orden`), nunca arriba por azar del orden de descarga.
    items = ordenar_items_por_fecha(items)
    return JSONResponse({"items": items, "errores": errores})


async def marcar_item_usado(request: Request) -> Response:
    """Marca/desmarca un item como usado `{fuente_id, clave, usado?: true}` -> `{mensaje}`.

    Requiere `fuente_id` (existente) y `clave` no vacia. `usado` por defecto True.
    """
    datos = await leer_json(request)
    fuente_id = datos.get("fuente_id")
    clave = datos.get("clave")
    if not isinstance(fuente_id, str) or not fuente_id:
        return JSONResponse({"error": "Falta la fuente del item."}, status_code=400)
    if not isinstance(clave, str) or not clave.strip():
        return JSONResponse({"error": "Falta la clave del item."}, status_code=400)
    if repos.obtener_fuente_rss(fuente_id) is None:
        return JSONResponse({"error": "Esa fuente ya no existe."}, status_code=404)
    usado = datos.get("usado", True)
    repos.marcar_item(fuente_id, clave.strip(), bool(usado))
    return JSONResponse({"mensaje": "Item marcado como usado." if usado else "Item desmarcado."})


# Skill por defecto para generar copy desde un item del feed.
_SKILL_DEFECTO = "copy-desde-nota"


def _nota_desde_item(titulo: str, resumen: str, enlace: str) -> str:
    """Construye la nota para la skill: titulo + resumen + enlace (los vacios se omiten)."""
    partes = [p for p in (titulo.strip(), resumen.strip(), enlace.strip()) if p]
    return "\n\n".join(partes)


async def generar(request: Request) -> Response:
    """Genera copy DIRECTO desde un item, EN SEGUNDO PLANO -> `{generacion}` (tipo "rss").

    `{titulo, resumen?, enlace?, marca, redes:[..], skill?, fuente_id?, clave?}`:
      - Construye la nota (`titulo + "\\n\\n" + resumen + "\\n\\n" + enlace`) y lanza un
        trabajo de claude en background (no bloquea). El frontend sondea
        `GET /api/generaciones/{id}` y, al completarse, recoge `resultado` (misma forma
        que copy: `{resultado, historial_id, verdicto, piezas, publicaciones}`).
      - El item se marca como USADO solo si la generacion completa con exito (en el
        post-procesado), no al lanzar.
      - Skill por defecto `copy-desde-nota`. Valida marca/redes/skill contra allowlists.
    """
    datos = await leer_json(request)
    titulo = datos.get("titulo")
    if not isinstance(titulo, str) or not titulo.strip():
        return JSONResponse({"error": "El título del item es obligatorio."}, status_code=400)
    resumen = datos.get("resumen") if isinstance(datos.get("resumen"), str) else ""
    enlace = datos.get("enlace") if isinstance(datos.get("enlace"), str) else ""

    marca = datos.get("marca")
    if not gen_dom.marca_valida(marca):
        return JSONResponse({"error": "Marca no permitida."}, status_code=400)

    skill = datos.get("skill")
    if not isinstance(skill, str) or not skill.strip():
        skill = _SKILL_DEFECTO
    # El "tipo de contenido" es ahora un PROMPT de la Biblioteca (store-or-semilla).
    prompt_id = f"prompt/{skill.strip()}"
    cuerpo = biblioteca.cuerpo_efectivo(prompt_id)
    if cuerpo is None:
        return JSONResponse({"error": "Tipo de contenido no permitido."}, status_code=400)

    crudas = datos.get("redes")
    redes_ids = stream.normalizar_redes(crudas if isinstance(crudas, list) else None, canonicas=redes.ids())
    # Defensa en profundidad contra token-flooding del prompt: trunca la nota (titulo +
    # resumen + enlace) al mismo limite que aplica el dominio de generacion.
    nota = _nota_desde_item(titulo, resumen, enlace)[: gen_dom.MAX_TEXTO]
    fuente_id = datos.get("fuente_id")
    clave = datos.get("clave")

    # Atribucion por usuario (#130 Fase 1): el item lo genera el usuario de la peticion.
    # ENCOLA y devuelve de inmediato (#130 Fase 2); el worker corre `claude -p`. El post-
    # procesado de copy (parsear + historial + N borradores) se reutiliza; `fuente_id`/`clave`
    # marcan el item del feed como usado SOLO si completa con exito.
    autor = autor_de_peticion(request)
    fuente = fuente_id.strip() if isinstance(fuente_id, str) and fuente_id.strip() else None
    clave_item = clave.strip() if isinstance(clave, str) and clave.strip() else None

    # Imagen ORIGINAL del artículo: solo se reutiliza si la fuente es de MARCA PROPIA
    # (gate server-side; el cliente no puede forzarlo). La pieza nace `tipo_contenido='fuente'`
    # con esa URL en `imagen_fuente`, lista para usarse en el editor.
    imagen_item = datos.get("imagen")
    imagen_item = imagen_item.strip() if isinstance(imagen_item, str) else ""
    imagen_fuente = ""
    tipo_contenido = ""
    if fuente and imagen_item.startswith(("http://", "https://")):
        f = repos.obtener_fuente_rss(fuente)
        if f and f.get("propia"):
            imagen_fuente = imagen_item
            tipo_contenido = "fuente"

    # URL CANONICA de la nota de origen: el enlace ya viaja como texto en la nota; aquí se
    # PERSISTE estructurado en `contenido.url_fuente` (trazabilidad + dedup por URL). "" si el
    # enlace no es http(s) válido (la canonización lo descarta).
    url_fuente = dedup.url_canonica(enlace) if enlace.strip().startswith(("http://", "https://")) else ""

    gen = gen_dom.lanzar_copy(
        tipo="rss", prompt_id=prompt_id, origen_historial=skill.strip(), marca=marca,
        contexto=nota, redes_ids=redes_ids, titulo=titulo.strip(), titulo_dado=titulo.strip(),
        texto_base=nota, autor=autor,
        fuente_id=fuente if clave_item else None, clave=clave_item if fuente else None,
        imagen_fuente=imagen_fuente, tipo_contenido=tipo_contenido,
        url_fuente=url_fuente,
    )
    return JSONResponse({"generacion": gen})


RUTAS = [
    Route("/api/rss/fuentes", listar_fuentes, methods=["GET"]),
    Route("/api/rss/fuentes", crear_fuente, methods=["POST"]),
    Route("/api/rss/fuentes/{fuente_id}", actualizar_fuente, methods=["PUT"]),
    Route("/api/rss/fuentes/{fuente_id}", borrar_fuente, methods=["DELETE"]),
    Route("/api/rss/items", listar_items, methods=["GET"]),
    Route("/api/rss/items/usado", marcar_item_usado, methods=["POST"]),
    Route("/api/rss/generar", generar, methods=["POST"]),
]
