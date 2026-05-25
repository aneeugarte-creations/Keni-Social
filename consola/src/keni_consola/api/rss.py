"""API RSS: fuentes RSS/Atom (CRUD) + lectura de items para importar como borradores.

El SPA guarda fuentes (un feed por marca, opcional) y lista sus items recientes para
que la persona elija cuales convertir en publicaciones. Persistencia de las FUENTES en
SQLite (`consola.db`); los ITEMS se leen del feed en vivo (no se persisten aqui).

SEGURIDAD / VALIDACION:
  - `nombre` y `url` obligatorios al crear una fuente.
  - La URL SOLO puede ser `http`/`https` y se valida contra SSRF: se resuelve el host
    y se RECHAZA si apunta a loopback / rangos privados / link-local / etc. El guard
    se aplica TANTO al crear la fuente COMO antes de cada descarga (defensa en
    profundidad: una IP puede cambiar de resolucion entre el alta y la lectura).
  - `marca` (si viene) SOLO de la allowlist de Skills (`consola.marcas` con slug).
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
import re
import socket
from typing import Any
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import db, marcas
from .._http_json import leer_json

# Marcas validas: las de Skills (con slug). Mismo criterio que publicaciones.
_MARCAS: tuple[tuple[str, str], ...] = tuple(marcas.opciones_por_slug())
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


def parsear_feed(xml: str) -> list[dict[str, str]]:
    """Parsea un feed RSS 2.0 o Atom y devuelve hasta `_MAX_ITEMS` items.

    Cada item es `{titulo, resumen, enlace, fecha}`. Tolerante: campos ausentes salen
    como ''. Lanza `RSSError` si el XML no se puede parsear.

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
            items.append(
                {
                    "titulo": titulo,
                    "resumen": _limpiar_resumen(resumen),
                    "enlace": enlace,
                    "fecha": fecha,
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
        items.append(
            {
                "titulo": titulo,
                "resumen": _limpiar_resumen(resumen),
                "enlace": enlace,
                "fecha": fecha,
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


def _fuente_a_dict(fuente: dict[str, Any]) -> dict[str, Any]:
    """Serializa una fuente resolviendo el nombre legible de la marca."""
    return {
        "id": fuente["id"],
        "nombre": fuente["nombre"],
        "url": fuente["url"],
        "marca": fuente["marca"],
        "marca_nombre": marcas.etiqueta_por_slug(fuente["marca"]) if fuente["marca"] else "",
    }


async def listar_fuentes(request: Request) -> Response:
    """Listado de fuentes RSS."""
    fuentes = db.listar_fuentes_rss()
    return JSONResponse({"fuentes": [_fuente_a_dict(f) for f in fuentes]})


async def crear_fuente(request: Request) -> Response:
    """Crea una fuente `{nombre, url, marca?}` -> `{fuente}`. Valida URL + SSRF."""
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

    fuente = db.crear_fuente_rss(nombre.strip(), url, marca=marca)
    return JSONResponse({"fuente": _fuente_a_dict(fuente)})


async def borrar_fuente(request: Request) -> Response:
    fuente_id = request.path_params["fuente_id"]
    if not db.borrar_fuente_rss(fuente_id):
        return JSONResponse({"error": "Esa fuente ya no existe."}, status_code=404)
    return JSONResponse({"mensaje": "Fuente borrada."})


# --------------------------------------------------------------------------- #
# Endpoints: items (lectura en vivo del feed)                                  #
# --------------------------------------------------------------------------- #


async def listar_items(request: Request) -> Response:
    """Items recientes `?fuente={id}` (o de TODAS las fuentes si no se pasa).

    -> `{items:[{titulo, resumen, enlace, fecha, fuente_id, fuente_nombre}], errores:[..]}`.
    Si un feed falla, se OMITE y su error se anota en `errores` sin romper los demas.
    Si se pide una fuente concreta inexistente -> 404.
    """
    fuente_id = request.query_params.get("fuente") or None
    if fuente_id:
        fuente = db.obtener_fuente_rss(fuente_id)
        if fuente is None:
            return JSONResponse({"error": "Esa fuente ya no existe."}, status_code=404)
        fuentes = [fuente]
    else:
        fuentes = db.listar_fuentes_rss()

    items: list[dict[str, Any]] = []
    errores: list[dict[str, str]] = []
    for fuente in fuentes:
        try:
            items.extend(leer_items_fuente(fuente))
        except RSSError as e:
            errores.append({"fuente_id": fuente["id"], "fuente_nombre": fuente["nombre"], "error": str(e)})
        except Exception:  # noqa: BLE001 -- nunca un traceback crudo; se omite la fuente
            errores.append(
                {
                    "fuente_id": fuente["id"],
                    "fuente_nombre": fuente["nombre"],
                    "error": "No se pudo leer el feed.",
                }
            )
    return JSONResponse({"items": items, "errores": errores})


RUTAS = [
    Route("/api/rss/fuentes", listar_fuentes, methods=["GET"]),
    Route("/api/rss/fuentes", crear_fuente, methods=["POST"]),
    Route("/api/rss/fuentes/{fuente_id}", borrar_fuente, methods=["DELETE"]),
    Route("/api/rss/items", listar_items, methods=["GET"]),
]
