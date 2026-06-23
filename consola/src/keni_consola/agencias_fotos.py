"""Buscador de FOTOS LICENCIADAS de AFP (imagen PUBLICABLE, a diferencia del stock gratuito).

AFP da una licencia editorial: sus fotos SÍ se pueden publicar (no requieren la autorización
manual de derechos del stock gratuito), pero el CRÉDITO/BYLINE es OBLIGATORIO. Por eso una foto
de AFP se adjunta como `imagen_origen='licenciada'` (publicable) conservando autor/crédito, no
como `'stock'` (ayuda visual bloqueada). Espejo de `stock_fotos.py` pero contra una sola fuente.

PRINCIPIO — DEGRADACIÓN HONESTA (igual que las agencias de noticias y el stock)
--------------------------------------------------------------------------------------
AFP está GATEADA por credencial OAuth2 (`config.afp_configurado()`): sin client_id/secret NO se
inventa nada, `estado_fuente()` la marca `disponible=False` con su motivo y `buscar()` devuelve
`[]`. El TOKEN y el TRANSPORTE HTTP se REUTILIZAN de `agencias.py` (misma fuente AFP que las
noticias): `agencias.obtener_token_afp()` + `agencias._POSTEAR`. La búsqueda real va por el punto
INYECTABLE `_BUSCADOR` (en tests se parchea para correr OFFLINE, sin red).

PARSEO TOLERANTE
--------------------------------------------------------------------------------------
La forma EXACTA del array de medios (`medias`/`bagItem`/`renditions`/`sizes`) y de cada tamaño
(`href`/`role`/`sizeName`) solo se ve con credenciales vivas, así que `normalizar_afp_fotos` es
PURO y TOLERANTE: busca los href por una lista de nombres alternativos, navega el array de medios
de forma defensiva y OMITE los documentos sin ninguna URL de imagen. Cubierto por tests OFFLINE.
"""

from __future__ import annotations

import json
from typing import Any

from . import agencias, config
from .api import rss

# Recortes defensivos (textos cortos: crédito/licencia/título de una foto).
_MAX_TEXTO = 300
_MAX_ITEMS = 30

# Claves bajo las que AFP puede colgar el array de medios de un documento (formas alternativas).
_CLAVES_MEDIOS = ("medias", "media", "bagItem", "renditions", "sizes", "images", "thumbnails")

# Pistas de tamaño en el nombre/role de un medio, EN ORDEN DE PREFERENCIA, para elegir la imagen
# GRANDE (publicable) y la MINIATURA. Se comparan en minúsculas como substrings (tolerante a la
# nomenclatura). `_elige` recorre estas pistas en orden, así la prioridad no depende del orden del
# array de medios que devuelva AFP.
_HINTS_GRANDES = ("highdef", "high", "original", "publishable", "full", "xl", "large")
_HINTS_THUMB = ("thumbnail", "thumb", "small", "icon", "preview", "low")

# Claves bajo las que un medio puede traer su URL y su pista de tamaño/rol.
_CLAVES_HREF = ("href", "url", "uri", "src", "link")
_CLAVES_HINT = ("role", "sizeName", "name", "type", "size", "rendition", "label")


def _primero(d: dict[str, Any], *claves: str) -> str:
    """Primer valor string no vacío de `d` entre `claves` (tolerante a formas distintas)."""
    for clave in claves:
        valor = d.get(clave)
        if isinstance(valor, str) and valor.strip():
            return valor.strip()
    return ""


def _candidato(
    *,
    url: str,
    thumb: str,
    autor: str,
    licencia: str,
    credito_url: str,
    titulo: str,
) -> dict[str, str]:
    """Construye un candidato AFP con la MISMA forma que los de stock (la UI los trata igual)."""
    url = url.strip()
    thumb = thumb.strip() or url
    return {
        "proveedor": "afp",
        "url": url,
        "thumb": thumb,
        "autor": autor[:_MAX_TEXTO],
        "licencia": licencia[:_MAX_TEXTO],
        "credito_url": credito_url.strip(),
        "titulo": rss._limpiar_resumen(titulo)[:_MAX_TEXTO],
    }


def _medio_a_hrefs(medio: Any) -> list[tuple[str, str]]:
    """Saca pares `(pista_tamaño, href)` de un medio. Tolerante: str, dict o listas anidadas."""
    if isinstance(medio, str) and medio.strip():
        return [("", medio.strip())]
    if not isinstance(medio, dict):
        return []
    href = _primero(medio, *_CLAVES_HREF)
    if not href:
        # Algunos formatos anidan otra lista de tamaños dentro del medio (renditions/sizes).
        salida: list[tuple[str, str]] = []
        for valor in medio.values():
            if isinstance(valor, list):
                for sub in valor:
                    salida.extend(_medio_a_hrefs(sub))
        return salida
    hint = " ".join(_primero(medio, k) for k in _CLAVES_HINT if _primero(medio, k)).lower()
    return [(hint, href)]


def _recolectar_medios(doc: dict[str, Any]) -> list[tuple[str, str]]:
    """Junta todos los `(pista, href)` de imagen de un documento (array de medios + href suelto)."""
    medios: list[tuple[str, str]] = []
    for clave in _CLAVES_MEDIOS:
        valor = doc.get(clave)
        if isinstance(valor, list):
            for medio in valor:
                medios.extend(_medio_a_hrefs(medio))
        elif isinstance(valor, dict):
            medios.extend(_medio_a_hrefs(valor))
    # Href de nivel documento como último recurso (algunos docs traen una sola imagen suelta).
    top = _primero(doc, "href", "url", "uri")
    if top:
        medios.append(("", top))
    return medios


def _elige(medios: list[tuple[str, str]], pistas: tuple[str, ...]) -> str:
    """Href del medio que mejor casa `pistas`, recorridas EN ORDEN DE PREFERENCIA; "" si ninguno."""
    for pista in pistas:
        for hint, href in medios:
            if hint and pista in hint:
                return href
    return ""


def normalizar_afp_fotos(datos: Any) -> list[dict[str, str]]:
    """Normaliza la respuesta de fotos de AFP a candidatos. PURA, tolerante a la forma.

    Recorre `response.docs` (estilo Solr) o `docs`/`documents`/`items`; por cada documento elige
    una URL GRANDE (publicable) y una MINIATURA del array de medios, y compone autor + crédito
    ("AFP" + creditline). OMITE los documentos sin ninguna URL de imagen. Reutiliza el extractor
    de listas tolerante de `agencias` (mismo esqueleto que las noticias AFP).
    """
    if isinstance(datos, dict) and isinstance(datos.get("response"), dict):
        docs = agencias._extraer_lista(datos["response"], ("docs", "documents", "items"))
    else:
        docs = agencias._extraer_lista(datos, ("docs", "documents", "items", "results"))
    salida: list[dict[str, str]] = []
    for doc in docs[:_MAX_ITEMS]:
        if not isinstance(doc, dict):
            continue
        medios = _recolectar_medios(doc)
        if not medios:
            continue
        url = _elige(medios, _HINTS_GRANDES) or medios[0][1]
        if not url:
            continue
        thumb = _elige(medios, _HINTS_THUMB) or url
        creditline = _primero(doc, "creditline", "credit", "source", "provider")
        licencia = f"AFP — {creditline}" if creditline and "afp" not in creditline.lower() else (creditline or "AFP")
        salida.append(
            _candidato(
                url=url,
                thumb=thumb,
                autor=_primero(doc, "creator", "photographer", "byline", "author"),
                licencia=licencia,
                credito_url=_primero(doc, "creditUrl", "credito_url", "permalink", "url"),
                titulo=_primero(doc, "title", "headline", "titulo", "name"),
            )
        )
    return salida


def estado_fuente() -> dict[str, Any]:
    """Estado HONESTO de AFP como fuente de FOTOS (sin tocar red): `{proveedor, nombre, disponible, motivo}`.

    `disponible=True` solo si AFP tiene sus credenciales OAuth2 (mismo gate que las noticias AFP).
    """
    if config.afp_configurado():
        return {"proveedor": "afp", "nombre": "AFP", "disponible": True, "motivo": ""}
    return {
        "proveedor": "afp",
        "nombre": "AFP",
        "disponible": False,
        "motivo": "Faltan las credenciales de AFP (configúralas en Sistema → Proveedores).",
    }


def _cuerpo_busqueda(query: str, limite: int) -> dict[str, Any]:
    """Cuerpo JSON de la búsqueda de FOTOS en AFP. A VERIFICAR con credenciales reales.

    Filtra el producto FOTO (`photo`) para traer SOLO fotos publicables (no texto/vídeo). La forma
    EXACTA del filtro de producto puede variar; aquí se envía como filtro `in` sobre `product`.
    """
    return {
        "query": query,
        "langs": ["es", "en"],
        "size": limite,
        "product": {"in": ["photo"]},
    }


def _buscar_red(query: str, limite: int) -> Any:
    """Login OAuth2 (reutilizado) + POST `/v1/api/search` filtrando fotos. Lanza `rss.RSSError`.

    NO loguea credenciales. Reutiliza `agencias.obtener_token_afp()` y el transporte POST inyectable
    `agencias._POSTEAR` (la MISMA fuente AFP que las noticias).
    """
    token = agencias.obtener_token_afp()
    url = f"{config.afp_base_url()}/v1/api/search"
    cuerpo = json.dumps(_cuerpo_busqueda(query, limite)).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    crudo = agencias._POSTEAR(url, cuerpo, headers)
    try:
        return json.loads(crudo)
    except (json.JSONDecodeError, ValueError) as e:
        raise rss.RSSError("AFP respondió a la búsqueda algo que no es JSON válido.") from e


# Punto INYECTABLE de la búsqueda (token + search): los tests lo parchean para correr OFFLINE.
_BUSCADOR = _buscar_red


def buscar(query: str, limite: int = 6) -> list[dict[str, str]]:
    """Busca fotos licenciadas en AFP. Degradación honesta: `[]` si query vacío o AFP no disponible.

    Propaga `rss.RSSError` si falla la descarga (igual que el stock/las agencias); `limite` se
    acota a [1, _MAX_ITEMS].
    """
    query = (query or "").strip()
    if not query or not estado_fuente()["disponible"]:
        return []
    limite = max(1, min(int(limite), _MAX_ITEMS))
    datos = _BUSCADOR(query, limite)
    return normalizar_afp_fotos(datos)
