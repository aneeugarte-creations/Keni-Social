"""Buscadores de FOTOS de stock en APIs gratuitas (Pexels, Pixabay, Wikimedia, NASA, Openverse).

Dan al equipo candidatos de imagen reutilizables (con su crédito y licencia) para acompañar
una pieza. Cada proveedor se normaliza a la MISMA forma de candidato, de modo que la UI los
trata por igual venga de donde venga la foto.

PRINCIPIO — DEGRADACION HONESTA (igual que las agencias y el Radar)
--------------------------------------------------------------------------------------
Pexels y Pixabay están GATEADOS por credencial: sin API key NO se inventa nada,
`estado_fuente()` los marca `disponible=False` con su motivo y `buscar()` devuelve `[]`.
Wikimedia, NASA y Openverse no requieren clave: siempre disponibles. La descarga va por el
`_DESCARGADOR` INYECTABLE de `api.rss` (mismos límites de tamaño/timeout; en tests se parchea
sin red) y la URL pasa por el guard SSRF de `api.rss`.

PARSEO TOLERANTE
--------------------------------------------------------------------------------------
Las respuestas de cada API tienen formas propias y versionan; para no acoplarnos a un esquema
frágil, los normalizadores (`normalizar_pexels`/`normalizar_pixabay`/`normalizar_wikimedia`/
`normalizar_nasa`/`normalizar_openverse`) son TOLERANTES: buscan los campos por una lista de
nombres alternativos y omiten lo que no traiga al menos una URL de imagen descargable. Son
funciones PURAS (sin red), cubiertas por tests; el fetch (`buscar`/`buscar_todos`) solo
descarga + delega el parseo aquí.
"""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

from . import config
from .api import rss

# Recortes defensivos (textos cortos: crédito/licencia/título de una foto).
_MAX_TEXTO = 300
_MAX_ITEMS = 30

# Catálogo de proveedores: nombre legible + si requiere credencial para operar.
_PROVEEDORES: dict[str, dict[str, Any]] = {
    "pexels": {"nombre": "Pexels", "requiere_clave": True},
    "pixabay": {"nombre": "Pixabay", "requiere_clave": True},
    "wikimedia": {"nombre": "Wikimedia Commons", "requiere_clave": False},
    "nasa": {"nombre": "NASA Images", "requiere_clave": False},
    "openverse": {"nombre": "Openverse", "requiere_clave": False},
}

# User-Agent descriptivo para las APIs que lo piden (Wikimedia, NASA). El `_DESCARGADOR`
# real ignora cabeceras; se documenta aquí el contrato y los tests pueden inspeccionarlo.
_USER_AGENT = "keni-social/1.0 (https://social.kenitech.io)"


# --------------------------------------------------------------------------- #
# Helpers de parseo (PUROS)                                                    #
# --------------------------------------------------------------------------- #


def _primero(d: dict[str, Any], *claves: str) -> str:
    """Primer valor string no vacío de `d` entre `claves` (tolerante a formas distintas)."""
    for clave in claves:
        valor = d.get(clave)
        if isinstance(valor, str) and valor.strip():
            return valor.strip()
    return ""


def _candidato(
    proveedor: str,
    *,
    url: str,
    thumb: str,
    autor: str,
    licencia: str,
    credito_url: str,
    titulo: str,
) -> dict[str, str]:
    """Construye un candidato normalizado (misma forma para todos los proveedores)."""
    url = url.strip()
    thumb = (thumb.strip() or url)
    return {
        "proveedor": proveedor,
        "url": url,
        "thumb": thumb,
        "autor": autor[:_MAX_TEXTO],
        "licencia": licencia[:_MAX_TEXTO],
        "credito_url": credito_url.strip(),
        "titulo": rss._limpiar_resumen(titulo)[:_MAX_TEXTO],
    }


def _meta_valor(extmetadata: Any, *claves: str) -> str:
    """Saca un valor de `extmetadata` de Wikimedia (cada campo es `{value: ...}`). Tolerante."""
    if not isinstance(extmetadata, dict):
        return ""
    for clave in claves:
        campo = extmetadata.get(clave)
        if isinstance(campo, dict):
            valor = campo.get("value")
            if isinstance(valor, str) and valor.strip():
                return rss._limpiar_resumen(valor)
        elif isinstance(campo, str) and campo.strip():
            return rss._limpiar_resumen(campo)
    return ""


# --------------------------------------------------------------------------- #
# Normalizadores por proveedor (PUROS, tolerantes a la forma)                  #
# --------------------------------------------------------------------------- #


def normalizar_pexels(datos: Any) -> list[dict[str, str]]:
    """Normaliza la respuesta de Pexels (`photos[]`) a candidatos. PURA, tolerante."""
    fotos = datos.get("photos") if isinstance(datos, dict) else datos
    if not isinstance(fotos, list):
        return []
    salida: list[dict[str, str]] = []
    for foto in fotos[:_MAX_ITEMS]:
        if not isinstance(foto, dict):
            continue
        src = foto.get("src") if isinstance(foto.get("src"), dict) else {}
        url = _primero(src, "original", "large2x", "large", "medium")
        if not url:
            continue
        thumb = _primero(src, "medium", "small", "large")
        salida.append(
            _candidato(
                "pexels",
                url=url,
                thumb=thumb,
                autor=_primero(foto, "photographer"),
                licencia="Pexels License",
                credito_url=_primero(foto, "url"),
                titulo=_primero(foto, "alt"),
            )
        )
    return salida


def normalizar_pixabay(datos: Any) -> list[dict[str, str]]:
    """Normaliza la respuesta de Pixabay (`hits[]`) a candidatos. PURA, tolerante."""
    hits = datos.get("hits") if isinstance(datos, dict) else datos
    if not isinstance(hits, list):
        return []
    salida: list[dict[str, str]] = []
    for hit in hits[:_MAX_ITEMS]:
        if not isinstance(hit, dict):
            continue
        url = _primero(hit, "largeImageURL", "fullHDURL", "webformatURL")
        if not url:
            continue
        thumb = _primero(hit, "webformatURL", "previewURL")
        salida.append(
            _candidato(
                "pixabay",
                url=url,
                thumb=thumb,
                autor=_primero(hit, "user"),
                licencia="Pixabay Content License",
                credito_url=_primero(hit, "pageURL"),
                titulo=_primero(hit, "tags"),
            )
        )
    return salida


def normalizar_wikimedia(datos: Any) -> list[dict[str, str]]:
    """Normaliza la respuesta de Wikimedia Commons (`query.pages`) a candidatos. PURA.

    `query.pages` es un dict pageid->page; cada page trae `imageinfo[0]` con la URL real y la
    `extmetadata` (autor/licencia). Omite las páginas sin URL de imagen.
    """
    query = datos.get("query") if isinstance(datos, dict) else None
    paginas = query.get("pages") if isinstance(query, dict) else None
    if isinstance(paginas, dict):
        items = list(paginas.values())
    elif isinstance(paginas, list):
        items = paginas
    else:
        return []
    salida: list[dict[str, str]] = []
    for pagina in items[:_MAX_ITEMS]:
        if not isinstance(pagina, dict):
            continue
        info = pagina.get("imageinfo")
        info0 = info[0] if isinstance(info, list) and info and isinstance(info[0], dict) else {}
        url = _primero(info0, "url")
        if not url:
            continue
        extmeta = info0.get("extmetadata")
        licencia = _meta_valor(extmeta, "LicenseShortName", "License", "UsageTerms")
        salida.append(
            _candidato(
                "wikimedia",
                url=url,
                thumb=_primero(info0, "thumburl"),
                autor=_meta_valor(extmeta, "Artist", "Credit"),
                licencia=licencia or "Wikimedia Commons",
                credito_url=_primero(info0, "descriptionurl", "descriptionshorturl"),
                titulo=_primero(pagina, "title"),
            )
        )
    return salida


def normalizar_nasa(datos: Any) -> list[dict[str, str]]:
    """Normaliza la respuesta de NASA Images (`collection.items[]`) a candidatos. PURA.

    Cada item trae `links[0].href` (thumb/imagen) y `data[0]` con título/descripción/autor.
    Omite los items sin URL de imagen.
    """
    coleccion = datos.get("collection") if isinstance(datos, dict) else None
    items = coleccion.get("items") if isinstance(coleccion, dict) else None
    if not isinstance(items, list):
        return []
    salida: list[dict[str, str]] = []
    for item in items[:_MAX_ITEMS]:
        if not isinstance(item, dict):
            continue
        links = item.get("links")
        link0 = links[0] if isinstance(links, list) and links and isinstance(links[0], dict) else {}
        url = _primero(link0, "href")
        if not url:
            continue
        data = item.get("data")
        data0 = data[0] if isinstance(data, list) and data and isinstance(data[0], dict) else {}
        salida.append(
            _candidato(
                "nasa",
                url=url,
                thumb=url,
                autor=_primero(data0, "photographer", "secondary_creator"),
                licencia="NASA (dominio público)",
                credito_url=url,
                titulo=_primero(data0, "title", "description"),
            )
        )
    return salida


def normalizar_openverse(datos: Any) -> list[dict[str, str]]:
    """Normaliza la respuesta de Openverse (`results[]`) a candidatos. PURA, tolerante."""
    resultados = datos.get("results") if isinstance(datos, dict) else datos
    if not isinstance(resultados, list):
        return []
    salida: list[dict[str, str]] = []
    for res in resultados[:_MAX_ITEMS]:
        if not isinstance(res, dict):
            continue
        url = _primero(res, "url")
        if not url:
            continue
        salida.append(
            _candidato(
                "openverse",
                url=url,
                thumb=_primero(res, "thumbnail"),
                autor=_primero(res, "creator", "attribution"),
                licencia=_primero(res, "license", "license_version") or "Openverse",
                credito_url=_primero(res, "foreign_landing_url"),
                titulo=_primero(res, "title"),
            )
        )
    return salida


_NORMALIZADORES = {
    "pexels": normalizar_pexels,
    "pixabay": normalizar_pixabay,
    "wikimedia": normalizar_wikimedia,
    "nasa": normalizar_nasa,
    "openverse": normalizar_openverse,
}


# --------------------------------------------------------------------------- #
# Credenciales (config accessor si existe, fallback a env var)                 #
# --------------------------------------------------------------------------- #


def _clave_proveedor(proveedor: str, marca: str = "") -> str | None:
    """Devuelve la API key de un proveedor gateado para una marca, o None si no hay.

    Delega en `config.pexels_api_key(marca)` / `config.pixabay_api_key(marca)`, que
    resuelven la precedencia secreto-por-marca > clave global por entorno.
    """
    accessor = {"pexels": "pexels_api_key", "pixabay": "pixabay_api_key"}.get(proveedor)
    if accessor:
        fn = getattr(config, accessor, None)
        if callable(fn):
            return fn(marca) or None
    return None


def _fuente_activa(proveedor: str, marca: str) -> bool:
    """True si `proveedor` está HABILITADO para `marca` (toggle de la subpágina de Stock).

    `config.fuentes_stock_activas(marca)` devuelve el conjunto habilitado o None (sin
    filtro = todas activas).
    """
    activas = config.fuentes_stock_activas(marca)
    return activas is None or proveedor in activas


# --------------------------------------------------------------------------- #
# Estado / disponibilidad (gateado por credencial)                            #
# --------------------------------------------------------------------------- #


def ids_proveedores() -> list[str]:
    """Ids de TODOS los proveedores del catálogo, en su orden (disponibles o no)."""
    return list(_PROVEEDORES)


def estado_fuente(proveedor: str, marca: str = "") -> dict[str, Any]:
    """Estado HONESTO de un proveedor PARA UNA MARCA (sin tocar red).

    `{proveedor, nombre, requiere_clave, disponible, activa, motivo}`:
      - `disponible`: el proveedor PUEDE operar (gratuito, o con API key para la marca).
      - `activa`: el usuario lo ha HABILITADO para la marca (toggle de la subpágina Stock).
    Pexels/Pixabay sólo `disponible=True` con API key; Wikimedia/NASA/Openverse siempre.
    Una fuente se usa en la búsqueda sólo si está `disponible` Y `activa`.
    """
    info = _PROVEEDORES.get(proveedor)
    if info is None:
        return {
            "proveedor": proveedor,
            "nombre": proveedor,
            "requiere_clave": False,
            "disponible": False,
            "activa": False,
            "motivo": "Proveedor de fotos desconocido.",
        }
    activa = _fuente_activa(proveedor, marca)
    requiere_clave = info["requiere_clave"]
    if not requiere_clave or _clave_proveedor(proveedor, marca):
        motivo = ""
        disponible = True
    else:
        disponible = False
        motivo = (
            f"Falta la API key de {info['nombre']} "
            "(configúrala en Sistema → Proveedores)."
        )
    return {
        "proveedor": proveedor,
        "nombre": info["nombre"],
        "requiere_clave": requiere_clave,
        "disponible": disponible,
        "activa": activa,
        "motivo": motivo,
    }


def proveedores_disponibles(marca: str = "") -> list[str]:
    """Ids de los proveedores USABLES para una marca: disponibles Y habilitados."""
    return [
        p
        for p in _PROVEEDORES
        if (e := estado_fuente(p, marca))["disponible"] and e["activa"]
    ]


# --------------------------------------------------------------------------- #
# Fetch (vía el descargador inyectable de api.rss)                             #
# --------------------------------------------------------------------------- #


def _descargar_json(url: str, headers: dict[str, str]) -> Any:
    """Descarga JSON de `url` (guard SSRF + descargador inyectable). Lanza `rss.RSSError`.

    Reutiliza el guard SSRF y el `_DESCARGADOR` de `api.rss` (en tests se parchea sin red).
    `_DESCARGADOR` real ignora cabeceras; `headers` se acepta para documentar el contrato
    (Authorization de Pexels, User-Agent de Wikimedia/NASA) y para que los mocks las inspeccionen.
    """
    url_ok, error = rss.validar_url(url)
    if error is not None:
        raise rss.RSSError(error)
    crudo = rss._DESCARGADOR(url_ok)
    try:
        return json.loads(crudo)
    except (json.JSONDecodeError, ValueError) as e:
        raise rss.RSSError("El proveedor de fotos respondió algo que no es JSON válido.") from e


def _url_y_headers(
    proveedor: str, query: str, limite: int, marca: str = ""
) -> tuple[str, dict[str, str]]:
    """Construye la URL de búsqueda y las cabeceras de un proveedor. `query` ya saneado."""
    q = urllib.parse.quote(query)
    if proveedor == "pexels":
        url = f"https://api.pexels.com/v1/search?query={q}&per_page={limite}"
        return url, {"Authorization": _clave_proveedor("pexels", marca) or ""}
    if proveedor == "pixabay":
        clave = urllib.parse.quote(_clave_proveedor("pixabay", marca) or "")
        url = (
            f"https://pixabay.com/api/?key={clave}&q={q}&per_page={limite}"
            "&image_type=photo&safesearch=true"
        )
        return url, {}
    if proveedor == "wikimedia":
        url = (
            "https://commons.wikimedia.org/w/api.php?action=query&generator=search"
            f"&gsrsearch={q}&gsrnamespace=6&gsrlimit={limite}"
            # `iiurlwidth` hace que la API devuelva `thumburl` (miniatura a ese ancho); sin él la
            # respuesta no trae miniatura y el buscador caía a la imagen original (pesada/rota).
            "&prop=imageinfo&iiprop=url%7Cextmetadata&iiurlwidth=320&format=json"
        )
        return url, {"User-Agent": _USER_AGENT}
    if proveedor == "nasa":
        url = f"https://images-api.nasa.gov/search?q={q}&media_type=image"
        return url, {"User-Agent": _USER_AGENT}
    if proveedor == "openverse":
        url = f"https://api.openverse.org/v1/images/?q={q}&page_size={limite}"
        return url, {"User-Agent": _USER_AGENT}
    return "", {}


def buscar(
    query: str, proveedor: str, limite: int = 6, marca: str = ""
) -> list[dict[str, str]]:
    """Busca fotos en un proveedor. Degradación honesta: `[]` si query vacío o no disponible.

    Usa la API key de `marca` (si el proveedor la requiere). Propaga `rss.RSSError` si
    falla la descarga (igual que las agencias). El query se URL-encodea y `limite` se
    acota a [1, _MAX_ITEMS]. Comprueba `disponible` (puede operar), no el toggle `activa`:
    elegir un proveedor explícito lo fuerza aunque no esté en el conjunto por defecto.
    """
    query = (query or "").strip()
    if not query or proveedor not in _NORMALIZADORES:
        return []
    if not estado_fuente(proveedor, marca)["disponible"]:
        return []
    limite = max(1, min(int(limite), _MAX_ITEMS))
    url, headers = _url_y_headers(proveedor, query, limite, marca)
    if not url:
        return []
    datos = _descargar_json(url, headers)
    return _NORMALIZADORES[proveedor](datos)


def buscar_todos(
    query: str,
    limite_por: int = 4,
    proveedores: list[str] | None = None,
    marca: str = "",
) -> list[dict[str, str]]:
    """Busca en los proveedores usables de una marca y concatena los candidatos.

    Tolera fallos por proveedor (un `rss.RSSError` no corta a los demás). `proveedores`
    None = los USABLES de la marca (disponibles Y habilitados); si se pasa una lista,
    sólo los que estén `disponible` para la marca (un proveedor pedido a mano no se
    descarta por el toggle, pero sí si le falta la clave).
    """
    query = (query or "").strip()
    if not query:
        return []
    if proveedores is None:
        elegidos = proveedores_disponibles(marca)
    else:
        disponibles = {p for p in _PROVEEDORES if estado_fuente(p, marca)["disponible"]}
        elegidos = [p for p in proveedores if p in disponibles]
    salida: list[dict[str, str]] = []
    for proveedor in elegidos:
        try:
            salida.extend(buscar(query, proveedor, limite_por, marca))
        except rss.RSSError:
            continue
    return salida
