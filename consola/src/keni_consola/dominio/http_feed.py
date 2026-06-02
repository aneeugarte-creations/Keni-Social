"""Infra de feeds HTTP: descarga (inyectable) + parseo tolerante (RSS 2.0 / Atom).

Capa de INFRAESTRUCTURA reutilizable por el dominio (radar, algoritmos) y por el
router `api/rss.py`. Aqui vive la logica que NO depende de Starlette ni de un router:

  - Validacion de URL + guard SSRF (`validar_url`): esquema http/https, host valido y
    rechazo de IPs privadas / loopback / link-local / multicast / reservadas (resuelve
    el host y comprueba TODAS las IPs; defensa frente a DNS rebinding).
  - Descarga (`_DESCARGADOR`, punto INYECTABLE/mockeable): lo unico que toca la red. En
    tests se parchea para NUNCA tocar la red. Limites: timeout, tamano maximo (leyendo
    en trozos) y maximo de items por feed.
  - Parseo con la stdlib `xml.etree.ElementTree` (tolerante, sin deps nuevas): RSS 2.0
    (`<item>`) y Atom (`<entry>`). El resumen se recorta y se le quita el HTML. Si un
    feed falla, lanza `RSSError` (mensaje en espanol) y el llamante decide si omitirlo.

`api/rss.py` re-exporta estos simbolos para no romper a nadie que importe `rss.X`; el
dominio (radar/algoritmos) importa de AQUI, no del router (frontera limpia).
"""

from __future__ import annotations

import ipaddress
import re
import socket
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

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


def _imagen_item(entrada: ET.Element) -> str:
    """URL de la imagen de un item, si la trae; "" si no.

    Busca (ignorando namespaces, en cualquier nivel del item, p.ej. dentro de
    `<media:group>`): `<media:content url type=image/*|medium=image>`,
    `<media:thumbnail url>`, `<enclosure url type=image/*>` (RSS) y el enclosure de Atom
    `<link rel=enclosure type=image/* href=...>`. NO usa el `<image>` del canal (ese es el
    logo del sitio, no la imagen del artículo).
    """
    for el in entrada.iter():
        local = _quitar_ns(el.tag)
        tipo = (el.get("type") or "").lower()
        medium = (el.get("medium") or "").lower()
        # En Atom la URL del enclosure va en `href`; en RSS/mrss va en `url`.
        url = (el.get("url") or el.get("href") or "").strip()
        if not url:
            continue
        if local == "thumbnail":
            return url
        if local == "content" and (medium == "image" or tipo.startswith("image/")):
            return url
        if local == "enclosure" and tipo.startswith("image/"):
            return url
        if local == "link" and el.get("rel") == "enclosure" and tipo.startswith("image/"):
            return url
    return ""


def _clave_item(clave_feed: str, enlace: str) -> str:
    """Clave estable de un item: el `<guid>`/`<id>` del feed, o el enlace como fallback.

    Es la identidad que usamos para dedup / marcar usado. Si el feed no trae ni guid
    ni enlace, la clave queda vacia (el item no se puede marcar de forma estable).
    """
    return (clave_feed or "").strip() or (enlace or "").strip()


# Epoch minima (UTC) para items sin fecha parseable: van AL FINAL del orden por fecha.
_FECHA_MINIMA = datetime(1970, 1, 1, tzinfo=timezone.utc)


def fecha_a_orden(crudo: str | None) -> datetime:
    """Parsea la fecha de un item de feed a un `datetime` aware (UTC) para ORDENAR.

    Tolerante con los dos formatos comunes en feeds: RFC 822 (RSS 2.0 `pubDate`, p.ej.
    "Mon, 02 Jun 2025 10:00:00 GMT") e ISO 8601 (Atom `updated`/`published`, p.ej.
    "2025-06-02T10:00:00Z"). Una fecha ausente o no parseable cae a `_FECHA_MINIMA`, de
    forma que esos items quedan AL FINAL al ordenar por fecha desc (nunca arriba "por
    suerte"). Las fechas naive se asumen UTC para que sean comparables entre formatos.
    """
    if not isinstance(crudo, str) or not crudo.strip():
        return _FECHA_MINIMA
    texto = crudo.strip()
    # RFC 822 (pubDate de RSS 2.0). `parsedate_to_datetime` tolera zonas con nombre.
    try:
        fecha = parsedate_to_datetime(texto)
        if fecha is not None:
            return fecha if fecha.tzinfo else fecha.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        pass
    # ISO 8601 (Atom). `fromisoformat` no acepta el sufijo "Z" hasta 3.11; lo normalizamos.
    try:
        fecha = datetime.fromisoformat(texto.replace("Z", "+00:00"))
        return fecha if fecha.tzinfo else fecha.replace(tzinfo=timezone.utc)
    except ValueError:
        return _FECHA_MINIMA


def ordenar_items_por_fecha(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ordena items de feed por fecha DESC (lo MAS NUEVO arriba), no por feed/marca.

    Funcion PURA (no toca red ni BD). El orden es estable: items con la misma fecha (o sin
    fecha parseable) conservan su orden relativo de llegada. Asi un radar/listado multi-feed
    se ve cronologico en vez de agrupado por la fuente que se descargo primero.
    """
    return sorted(items, key=lambda it: fecha_a_orden(it.get("fecha")), reverse=True)


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

    Cada item es `{titulo, resumen, enlace, fecha, clave, imagen}`. La `clave` es
    estable (`<guid>`/`<id>` del feed, con fallback al enlace) y sirve para dedup /
    marcar usado. `imagen` es la URL de la imagen del artículo (media:content/
    thumbnail/enclosure), "" si no la trae. Tolerante: campos ausentes salen como ''.
    Lanza `RSSError` si el XML no se puede parsear.

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
                    "imagen": _imagen_item(entrada),
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
                "imagen": _imagen_item(entrada),
            }
        )
    return items


def leer_items_fuente(
    fuente: dict[str, Any], descargador: Any | None = None
) -> list[dict[str, Any]]:
    """Descarga y parsea el feed de una fuente, etiquetando cada item con la fuente.

    Aplica el guard SSRF ANTES de descargar (la IP puede haber cambiado desde el alta).
    `descargador` es el punto INYECTABLE (def. `_DESCARGADOR`); el router `api/rss.py`
    pasa el suyo para que los tests que parchean `rss._DESCARGADOR` sigan controlandolo.
    Lanza `RSSError` si la URL ya no es válida, si la descarga falla o si el XML no
    parsea. El llamante decide si omitir la fuente con su error.
    """
    descargar = descargador if descargador is not None else _DESCARGADOR
    url, error = validar_url(fuente["url"])
    if error is not None:
        raise RSSError(error)
    xml = descargar(url)
    items = parsear_feed(xml)
    return [
        {**item, "fuente_id": fuente["id"], "fuente_nombre": fuente["nombre"]}
        for item in items
    ]
