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
  - La descarga (`httpx`) vive detras de `_DESCARGADOR`, un punto INYECTABLE/mockeable:
    en tests se parchea para NUNCA tocar la red. Limites: timeout, tamano maximo
    (leyendo en trozos) y maximo de items por feed.
  - El parseo usa la stdlib `xml.etree.ElementTree` (tolerante, sin deps nuevas):
    soporta RSS 2.0 (`<item>`) y Atom (`<entry>`). El resumen se recorta y se le
    quita el HTML. Si un feed falla, se OMITE con su error sin romper los demas.
"""

from __future__ import annotations

import ipaddress
import json
import re
import socket
from typing import Any
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import biblioteca, marcas, redes, repos
from .._http_json import leer_json
from ..dominio import generar as gen_dom
from ..dominio import stream
from ..seguridad import autor_de_peticion

# Marcas validas: TODAS las del catalogo unico (por su id canonico). Mismo criterio
# que publicaciones.
_MARCAS: tuple[tuple[str, str], ...] = tuple(marcas.opciones())
_MARCAS_IDS = {m[0] for m in _MARCAS}

# Limites de descarga (defensa frente a feeds maliciosos o gigantes).
_TIMEOUT = 10.0  # segundos
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_MAX_ITEMS = 30  # items por feed
_RESUMEN_MAX = 500  # caracteres del resumen (tras limpiar HTML)

# Etiquetas HTML a texto plano (tolerante; los feeds suelen traer HTML en el resumen).
_RE_TAGS = re.compile(r"<[^>]+>")
_RE_ESPACIOS = re.compile(r"\s+")


# --------------------------------------------------------------------------- #
# Validacion de URL + guard SSRF                                               #
# --------------------------------------------------------------------------- #


def _ip_es_privada(ip: ipaddress._BaseAddress) -> bool:
    """True si la IP NO debe ser alcanzable desde un fetch de servidor (SSRF)."""
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validar_url(url: Any) -> tuple[str | None, str | None]:
    """Valida una URL de feed: `(url_limpia, None)` o `(None, mensaje_en_espanol)`.

    Reglas:
      - debe ser un string no vacio,
      - esquema SOLO `http`/`https`,
      - con host,
      - guard SSRF: resuelve el host y rechaza si CUALQUIER IP resuelta cae en un
        rango privado / loopback / link-local / multicast / reservado.
    """
    if not isinstance(url, str) or not url.strip():
        return None, "La URL del feed es obligatoria."
    url = url.strip()
    try:
        partes = urlsplit(url)
    except ValueError:
        return None, "La URL del feed no es válida."
    if partes.scheme not in ("http", "https"):
        return None, "La URL del feed debe empezar por http:// o https://."
    host = partes.hostname
    if not host:
        return None, "La URL del feed no tiene un host válido."

    error = _guard_ssrf(host)
    if error is not None:
        return None, error
    return url, None


def _guard_ssrf(host: str) -> str | None:
    """Resuelve `host` y devuelve un mensaje de error si apunta a una IP no permitida.

    Si el host ya es una IP literal, se comprueba directamente. Si es un nombre, se
    resuelve (A/AAAA) y se comprueban TODAS las direcciones: con que UNA sea privada
    se rechaza (defensa frente a DNS rebinding / nombres que resuelven a interno).
    """
    # Host que es una IP literal (incluye [::1] -> '::1' ya sin corchetes por hostname).
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        if _ip_es_privada(ip):
            return "La URL del feed apunta a una dirección no permitida."
        return None

    # Nombre de host: resolver y comprobar todas las IPs.
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return "No se pudo resolver el host del feed."
    except OSError:
        return "No se pudo resolver el host del feed."
    for info in infos:
        direccion = info[4][0]
        try:
            ip = ipaddress.ip_address(direccion)
        except ValueError:
            continue
        if _ip_es_privada(ip):
            return "La URL del feed apunta a una dirección no permitida."
    return None


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
# Descarga (INYECTABLE) + parseo tolerante (RSS 2.0 y Atom)                    #
# --------------------------------------------------------------------------- #


class RSSError(Exception):
    """Fallo controlado al descargar o parsear un feed (mensaje en espanol)."""


def _descargar_real(url: str) -> str:
    """Descarga el feed con `httpx` respetando timeout y tamano maximo.

    Lee en trozos y corta si supera `_MAX_BYTES`. Importacion diferida de httpx
    (dependencia transitiva via keni-metricas), igual que en `media`/`conexiones`.
    Lanza `RSSError` con mensaje en espanol ante cualquier fallo.
    """
    try:
        import httpx
    except ImportError as e:  # pragma: no cover -- httpx es dependencia transitiva
        raise RSSError("Falta la librería para leer feeds en este equipo.") from e

    try:
        with httpx.Client(timeout=_TIMEOUT, follow_redirects=False) as cliente:
            with cliente.stream("GET", url) as respuesta:
                if respuesta.status_code != 200:
                    raise RSSError(f"El feed respondió con un error (HTTP {respuesta.status_code}).")
                trozos: list[bytes] = []
                total = 0
                for trozo in respuesta.iter_bytes():
                    total += len(trozo)
                    if total > _MAX_BYTES:
                        raise RSSError("El feed es demasiado grande y se canceló la descarga.")
                    trozos.append(trozo)
    except httpx.TimeoutException as e:
        raise RSSError("El feed tardó demasiado y se canceló.") from e
    except httpx.HTTPError as e:
        raise RSSError("No se pudo contactar con el feed.") from e
    return b"".join(trozos).decode("utf-8", errors="replace")


# Punto INYECTABLE: lo unico que toca la red. Los tests lo parchean (sin red real).
_DESCARGADOR = _descargar_real


def _limpiar_resumen(crudo: str | None) -> str:
    """Quita el HTML de un resumen, colapsa espacios y lo recorta a `_RESUMEN_MAX`."""
    if not crudo:
        return ""
    texto = _RE_TAGS.sub(" ", crudo)
    texto = _RE_ESPACIOS.sub(" ", texto).strip()
    if len(texto) > _RESUMEN_MAX:
        texto = texto[:_RESUMEN_MAX].rstrip() + "…"
    return texto


def _texto_local(elemento: ET.Element | None) -> str:
    """Texto plano de un elemento (o ''). Sin recortar; el recorte lo hace el resumen."""
    if elemento is None or elemento.text is None:
        return ""
    return elemento.text.strip()


def _quitar_ns(tag: str) -> str:
    """Devuelve el nombre local de una etiqueta, sin el namespace `{...}`."""
    return tag.rsplit("}", 1)[-1]


def _buscar_hijo(elemento: ET.Element, *nombres: str) -> ET.Element | None:
    """Primer hijo cuyo nombre local este en `nombres` (ignora namespaces)."""
    objetivo = set(nombres)
    for hijo in elemento:
        if _quitar_ns(hijo.tag) in objetivo:
            return hijo
    return None


def _enlace_atom(entrada: ET.Element) -> str:
    """Extrae el href de un `<link>` de Atom (prefiere rel='alternate' o sin rel)."""
    candidato = ""
    for hijo in entrada:
        if _quitar_ns(hijo.tag) != "link":
            continue
        rel = hijo.get("rel", "")
        href = hijo.get("href", "")
        if not href:
            continue
        if rel in ("", "alternate"):
            return href
        if not candidato:
            candidato = href
    return candidato


def _clave_item(clave_feed: str, enlace: str) -> str:
    """Clave estable de un item: el `<guid>`/`<id>` del feed, o el enlace como fallback.

    Es la identidad que usamos para dedup / marcar usado. Si el feed no trae ni guid
    ni enlace, la clave queda vacia (el item no se puede marcar de forma estable).
    """
    return (clave_feed or "").strip() or (enlace or "").strip()


def _terminos_csv(crudo: str | None) -> list[str]:
    """Parte un CSV de terminos en una lista limpia (sin vacios, en minusculas)."""
    if not crudo:
        return []
    return [parte.strip().lower() for parte in crudo.split(",") if parte.strip()]


def item_pasa_filtros(item: dict[str, Any], incluir: str, excluir: str) -> bool:
    """Aplica los filtros incluir/excluir de un feed sobre titulo+resumen (insensible).

    Pasa si: (no hay terminos `incluir` O el texto contiene ALGUNO de `incluir`) Y
    (el texto NO contiene NINGUNO de `excluir`). CSV vacios => no filtran.
    """
    texto = f"{item.get('titulo', '')} {item.get('resumen', '')}".lower()
    incluir_terms = _terminos_csv(incluir)
    excluir_terms = _terminos_csv(excluir)
    if incluir_terms and not any(t in texto for t in incluir_terms):
        return False
    if any(t in texto for t in excluir_terms):
        return False
    return True


def parsear_feed(xml: str) -> list[dict[str, str]]:
    """Parsea un feed RSS 2.0 o Atom y devuelve hasta `_MAX_ITEMS` items.

    Cada item es `{titulo, resumen, enlace, fecha, clave}`. La `clave` es estable
    (`<guid>`/`<id>` del feed, con fallback al enlace) y sirve para dedup / marcar
    usado. Tolerante: campos ausentes salen como ''. Lanza `RSSError` si el XML no
    se puede parsear.

    No depende de feedparser: la stdlib `xml.etree.ElementTree` basta para RSS 2.0
    (`<channel><item>`) y Atom (`<feed><entry>`), que cubren el caso de uso.
    """
    try:
        raiz = ET.fromstring(xml)
    except ET.ParseError as e:
        raise RSSError("El feed no es un XML válido.") from e

    nombre_raiz = _quitar_ns(raiz.tag)
    items: list[dict[str, str]] = []

    if nombre_raiz == "feed":
        # Atom: <feed><entry>...
        entradas = [h for h in raiz if _quitar_ns(h.tag) == "entry"]
        for entrada in entradas[:_MAX_ITEMS]:
            titulo = _texto_local(_buscar_hijo(entrada, "title"))
            resumen = _texto_local(_buscar_hijo(entrada, "summary", "content"))
            enlace = _enlace_atom(entrada)
            fecha = _texto_local(_buscar_hijo(entrada, "updated", "published"))
            clave_feed = _texto_local(_buscar_hijo(entrada, "id"))
            items.append(
                {
                    "titulo": titulo,
                    "resumen": _limpiar_resumen(resumen),
                    "enlace": enlace,
                    "fecha": fecha,
                    "clave": _clave_item(clave_feed, enlace),
                }
            )
        return items

    # RSS 2.0 (y RDF/RSS 1.0 tolerado): buscar <item> en cualquier nivel.
    canal = _buscar_hijo(raiz, "channel")
    contenedor = canal if canal is not None else raiz
    entradas = [h for h in contenedor if _quitar_ns(h.tag) == "item"]
    if not entradas:
        # RSS 1.0 (RDF): los <item> cuelgan de la raiz, no del channel.
        entradas = [h for h in raiz if _quitar_ns(h.tag) == "item"]
    for entrada in entradas[:_MAX_ITEMS]:
        titulo = _texto_local(_buscar_hijo(entrada, "title"))
        resumen = _texto_local(_buscar_hijo(entrada, "description", "summary"))
        enlace = _texto_local(_buscar_hijo(entrada, "link"))
        fecha = _texto_local(_buscar_hijo(entrada, "pubDate", "date"))
        clave_feed = _texto_local(_buscar_hijo(entrada, "guid", "id"))
        items.append(
            {
                "titulo": titulo,
                "resumen": _limpiar_resumen(resumen),
                "enlace": enlace,
                "fecha": fecha,
                "clave": _clave_item(clave_feed, enlace),
            }
        )
    return items


def leer_items_fuente(fuente: dict[str, Any]) -> list[dict[str, Any]]:
    """Descarga y parsea el feed de una fuente, etiquetando cada item con la fuente.

    Aplica el guard SSRF ANTES de descargar (la IP puede haber cambiado desde el alta).
    Lanza `RSSError` si la URL ya no es válida, si la descarga falla o si el XML no
    parsea. El llamante decide si omitir la fuente con su error.
    """
    url, error = validar_url(fuente["url"])
    if error is not None:
        raise RSSError(error)
    xml = _DESCARGADOR(url)
    items = parsear_feed(xml)
    return [
        {**item, "fuente_id": fuente["id"], "fuente_nombre": fuente["nombre"]}
        for item in items
    ]


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
        nombre.strip(), url, marca=marca, incluir=incluir, excluir=excluir, redes_def=redes_def
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


def _items_de_fuente(fuente: dict[str, Any], *, ocultar_usados: bool) -> list[dict[str, Any]]:
    """Lee, filtra (incluir/excluir) y marca `usado` los items de UNA fuente.

    Aplica los filtros del feed sobre titulo+resumen, marca cada item segun
    `rss_items_vistos`, y con `ocultar_usados` omite los ya usados. Cada item sale
    como `{titulo, resumen, enlace, fecha, fuente_id, fuente_nombre, clave, usado}`.
    Propaga `RSSError` (la maneja el llamante para anotar el error y la salud).
    """
    crudos = leer_items_fuente(fuente)
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

    items: list[dict[str, Any]] = []
    errores: list[dict[str, str]] = []
    for fuente in fuentes:
        try:
            propios = _items_de_fuente(fuente, ocultar_usados=ocultar_usados)
            items.extend(propios)
            repos.registrar_salud_fuente_rss(fuente["id"], conteo=len(propios), error="")
        except RSSError as e:
            repos.registrar_salud_fuente_rss(fuente["id"], conteo=0, error=str(e))
            errores.append({"fuente_id": fuente["id"], "fuente_nombre": fuente["nombre"], "error": str(e)})
        except Exception:  # noqa: BLE001 -- nunca un traceback crudo; se omite la fuente
            mensaje = "No se pudo leer el feed."
            repos.registrar_salud_fuente_rss(fuente["id"], conteo=0, error=mensaje)
            errores.append(
                {
                    "fuente_id": fuente["id"],
                    "fuente_nombre": fuente["nombre"],
                    "error": mensaje,
                }
            )
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
    nota = _nota_desde_item(titulo, resumen, enlace)
    fuente_id = datos.get("fuente_id")
    clave = datos.get("clave")

    # Atribucion por usuario (#130 Fase 1): el item lo genera el usuario de la peticion.
    # ENCOLA y devuelve de inmediato (#130 Fase 2); el worker corre `claude -p`. El post-
    # procesado de copy (parsear + historial + N borradores) se reutiliza; `fuente_id`/`clave`
    # marcan el item del feed como usado SOLO si completa con exito.
    autor = autor_de_peticion(request)
    fuente = fuente_id.strip() if isinstance(fuente_id, str) and fuente_id.strip() else None
    clave_item = clave.strip() if isinstance(clave, str) and clave.strip() else None
    gen = gen_dom.lanzar_copy(
        tipo="rss", prompt_id=prompt_id, origen_historial=skill.strip(), marca=marca,
        contexto=nota, redes_ids=redes_ids, titulo=titulo.strip(), titulo_dado=titulo.strip(),
        texto_base=nota, autor=autor,
        fuente_id=fuente if clave_item else None, clave=clave_item if fuente else None,
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
