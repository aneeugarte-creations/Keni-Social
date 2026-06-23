"""Adaptadores de AGENCIAS de noticias (Reuters Connect / AFP) como fuentes (item F).

Convierten la respuesta de cada agencia en items con la MISMA forma que los del RSS del
equipo (`{titulo, resumen, enlace, fecha, fuente, clave}`), para que entren al pipeline de
fuentes/radar sin tratamiento especial. Asi un tema de Reuters/AFP se consolida, deduplica
y prioriza igual que cualquier otro item.

PRINCIPIO — DEGRADACION HONESTA (igual que el Radar)
--------------------------------------------------------------------------------------
Cada agencia esta GATEADA por credencial (`config.reuters_configurado()` /
`config.afp_configurado()`). Sin credencial NO se inventa nada: `estado_fuente()` la marca
`disponible=False` con el motivo ("falta la API key", etc.) y `traer_items()` devuelve `[]`.
Con credencial, se descarga via el `_DESCARGADOR` INYECTABLE de `api.rss` (mismos limites de
tamaño/timeout; en tests se parchea sin red) y la URL pasa por el guard SSRF de `api.rss`.

PARSEO TOLERANTE
--------------------------------------------------------------------------------------
Las APIs reales de Reuters Connect (GraphQL) y AFP (REST) tienen formas propias y versionan;
para no acoplarnos a un esquema fragil, los normalizadores (`normalizar_reuters`/
`normalizar_afp`) son TOLERANTES: buscan los campos por una lista de nombres alternativos y
omiten lo que no traiga al menos titulo o enlace. Son funciones PURAS (sin red), cubiertas
por tests; el `traer_items_*` solo hace el fetch + delega el parseo aqui.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

from . import config
from .api import rss

# Recortes defensivos (paridad con el RSS del equipo).
_MAX_TITULO = 300
_MAX_RESUMEN = 500
_MAX_ITEMS = 30

# Timeout (s) de las llamadas POST a AFP (login OAuth2 + búsqueda): cortas, solo intercambian
# credencial por token o piden una página de resultados.
_AFP_POST_TIMEOUT = 20


def _primero(d: dict[str, Any], *claves: str) -> str:
    """Primer valor string no vacio de `d` entre `claves` (tolerante a formas distintas)."""
    for clave in claves:
        valor = d.get(clave)
        if isinstance(valor, str) and valor.strip():
            return valor.strip()
    return ""


def _item(titulo: str, resumen: str, enlace: str, fecha: str, fuente: str) -> dict[str, str]:
    """Construye un item normalizado (misma forma que los items del RSS del equipo)."""
    titulo = titulo[:_MAX_TITULO]
    resumen = rss._limpiar_resumen(resumen)[:_MAX_RESUMEN]
    return {
        "titulo": titulo,
        "resumen": resumen,
        "enlace": enlace,
        "fecha": fecha,
        "fuente": fuente,
        # Clave estable para dedup/marcado (guid de la agencia si lo hay, fallback al enlace).
        "clave": (enlace or titulo).strip(),
    }


def normalizar_reuters(datos: Any, *, fuente: str = "Reuters") -> list[dict[str, str]]:
    """Normaliza la respuesta de Reuters Connect a items. PURA, tolerante a la forma.

    Acepta tanto una lista de notas como un dict que las envuelve (en `items`/`results`/
    `data`/`edges` o, para GraphQL, `data.search.items`). Cada nota se mapea por nombres
    alternativos de campo. Omite las que no traen al menos titulo o enlace.
    """
    notas = _extraer_lista(datos, ("items", "results", "data", "edges"))
    salida: list[dict[str, str]] = []
    for nota in notas[:_MAX_ITEMS]:
        if not isinstance(nota, dict):
            continue
        # GraphQL suele envolver el objeto real en `node`.
        nodo = nota.get("node") if isinstance(nota.get("node"), dict) else nota
        titulo = _primero(nodo, "headline", "title", "titulo", "name")
        enlace = _primero(nodo, "uri", "url", "link", "enlace", "webUrl")
        if not titulo and not enlace:
            continue
        resumen = _primero(nodo, "caption", "description", "summary", "body", "resumen")
        fecha = _primero(nodo, "versionCreated", "firstCreated", "dateCreated", "published", "fecha")
        salida.append(_item(titulo, resumen, enlace, fecha, fuente))
    return salida


def normalizar_afp(datos: Any, *, fuente: str = "AFP") -> list[dict[str, str]]:
    """Normaliza la respuesta de AFP (REST) a items. PURA, tolerante a la forma.

    AFP devuelve documentos bajo `response.docs` (estilo Solr) o en `documents`/`items`.
    Cada documento se mapea por nombres alternativos; se omite lo que no trae titulo/enlace.
    """
    if isinstance(datos, dict) and isinstance(datos.get("response"), dict):
        notas = _extraer_lista(datos["response"], ("docs", "documents", "items"))
    else:
        notas = _extraer_lista(datos, ("documents", "docs", "items", "results"))
    salida: list[dict[str, str]] = []
    for nota in notas[:_MAX_ITEMS]:
        if not isinstance(nota, dict):
            continue
        titulo = _primero(nota, "title", "headline", "titulo", "name")
        enlace = _primero(nota, "href", "url", "uno", "link", "enlace")
        if not titulo and not enlace:
            continue
        resumen = _primero(nota, "summary", "description", "abstract", "lead", "resumen")
        fecha = _primero(nota, "published", "created", "issued", "date", "fecha")
        salida.append(_item(titulo, resumen, enlace, fecha, fuente))
    return salida


def _extraer_lista(datos: Any, claves: tuple[str, ...], _profundidad: int = 0) -> list[Any]:
    """Saca una lista de notas de `datos`: si ya es lista la devuelve; si es dict, la busca.

    Primero mira las `claves` conocidas (items/results/...). Si ninguna da una lista, baja
    UN nivel por CUALQUIER valor dict (GraphQL envuelve en `data -> search -> edges`, con
    nombres intermedios que no estan en `claves`). Acotado en profundidad para no recorrer
    estructuras patologicas.
    """
    if isinstance(datos, list):
        return datos
    if not isinstance(datos, dict) or _profundidad > 4:
        return []
    for clave in claves:
        valor = datos.get(clave)
        if isinstance(valor, list):
            return valor
    # Ninguna clave conocida dio lista: baja un nivel por cualquier sub-dict (GraphQL).
    for valor in datos.values():
        if isinstance(valor, dict):
            anidado = _extraer_lista(valor, claves, _profundidad + 1)
            if anidado:
                return anidado
    return []


# --------------------------------------------------------------------------- #
# Estado / fetch por agencia (gateado por credencial)                          #
# --------------------------------------------------------------------------- #


def estado_fuente(agencia: str) -> dict[str, Any]:
    """Estado HONESTO de una agencia: `{red, nombre, disponible, motivo}` (sin tocar red).

    `disponible=False` con motivo cuando falta credencial (la UI la pinta como "pendiente/
    no configurada" sin inventar datos). `agencia` ∈ {"reuters", "afp"}.
    """
    if agencia == "reuters":
        if config.reuters_configurado():
            return {"red": "reuters", "nombre": "Reuters Connect", "disponible": True, "motivo": ""}
        return {
            "red": "reuters",
            "nombre": "Reuters Connect",
            "disponible": False,
            "motivo": "Falta la API key de Reuters (configura KENI_REUTERS_API_KEY).",
        }
    if agencia == "afp":
        if config.afp_configurado():
            return {"red": "afp", "nombre": "AFP", "disponible": True, "motivo": ""}
        return {
            "red": "afp",
            "nombre": "AFP",
            "disponible": False,
            "motivo": "Faltan las credenciales OAuth2 de AFP (KENI_AFP_CLIENT_ID / KENI_AFP_CLIENT_SECRET).",
        }
    return {"red": agencia, "nombre": agencia, "disponible": False, "motivo": "Agencia desconocida."}


def fuentes_pendientes() -> list[dict[str, str]]:
    """Agencias NO configuradas (para la UI: 'fuente pendiente' sin inventar nada)."""
    pendientes: list[dict[str, str]] = []
    for agencia in ("reuters", "afp"):
        estado = estado_fuente(agencia)
        if not estado["disponible"]:
            pendientes.append(
                {"red": estado["red"], "nombre": estado["nombre"], "motivo": estado["motivo"]}
            )
    return pendientes


def _postear_real(url: str, cuerpo: bytes, headers: dict[str, str]) -> str:
    """POST real a `url` (guard SSRF + timeout) que devuelve el texto de la respuesta.

    Transporte INYECTABLE para AFP (login OAuth2 + búsqueda): a diferencia del `_DESCARGADOR`
    de feeds (solo GET), AFP necesita POST con cuerpo. En tests se parchea (`_POSTEAR`) para no
    tocar la red. Lanza `rss.RSSError` ante SSRF o fallo de red.
    """
    url_ok, error = rss.validar_url(url)
    if error is not None:
        raise rss.RSSError(error)
    peticion = urllib.request.Request(url_ok, data=cuerpo, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(peticion, timeout=_AFP_POST_TIMEOUT) as resp:
            return resp.read().decode("utf-8", "replace")
    except rss.RSSError:
        raise
    except Exception as e:  # noqa: BLE001 -- red/HTTP: se uniforma a RSSError (no se filtra el detalle)
        raise rss.RSSError("No se pudo contactar con AFP.") from e


# Punto INYECTABLE del POST a AFP (token + búsqueda): los tests lo parchean para correr OFFLINE.
_POSTEAR = _postear_real


def obtener_token_afp() -> str:
    """Pide un token OAuth2 a AFP (`client_credentials`) y devuelve el `access_token`.

    REUTILIZABLE por las dos fuentes AFP (noticias y fotos licenciadas): centraliza el login para
    no reimplementar OAuth en cada sitio. Lanza `rss.RSSError` si AFP no está configurada, si la
    red falla o si la respuesta no trae token. NUNCA loguea las credenciales.

    A VERIFICAR con credenciales reales: la forma EXACTA del intercambio (campos del cuerpo vs.
    `Authorization: Basic`) puede variar; aquí se usa el grant `client_credentials` estándar por
    cuerpo `application/x-www-form-urlencoded`.
    """
    client_id = config.afp_client_id()
    client_secret = config.afp_client_secret()
    if not client_id or not client_secret:
        raise rss.RSSError("AFP no está configurada (faltan client_id/client_secret).")
    url = f"{config.afp_base_url()}/oauth/token"
    cuerpo = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }
    ).encode("utf-8")
    crudo = _POSTEAR(url, cuerpo, {"Content-Type": "application/x-www-form-urlencoded"})
    try:
        datos = json.loads(crudo)
    except (json.JSONDecodeError, ValueError) as e:
        raise rss.RSSError("AFP respondió al login algo que no es JSON válido.") from e
    token = datos.get("access_token") if isinstance(datos, dict) else None
    if not isinstance(token, str) or not token:
        raise rss.RSSError("AFP no devolvió un token de acceso.")
    return token


def _descargar_json(url: str, headers: dict[str, str]) -> Any:
    """Descarga JSON de `url` (guard SSRF + descargador inyectable). Lanza `rss.RSSError`.

    Reutiliza el guard SSRF y el `_DESCARGADOR` de `api.rss` (en tests se parchea sin red).
    El descargador devuelve texto; aqui se parsea a JSON. NOTA: `_DESCARGADOR` real ignora
    cabeceras; `headers` se acepta para que los tests/mocks puedan inspeccionarlas y para
    documentar el contrato. La autenticacion real se cablea cuando haya credenciales vivas.
    """
    url_ok, error = rss.validar_url(url)
    if error is not None:
        raise rss.RSSError(error)
    crudo = rss._DESCARGADOR(url_ok)
    try:
        return json.loads(crudo)
    except (json.JSONDecodeError, ValueError) as e:
        raise rss.RSSError("La agencia respondió algo que no es JSON válido.") from e


def traer_items(agencia: str) -> list[dict[str, str]]:
    """Trae items de una agencia configurada (o `[]` si no lo esta). Propaga `rss.RSSError`.

    Sin credencial devuelve `[]` (degradacion honesta, no lanza). Con credencial descarga y
    normaliza. El endpoint concreto se construye desde la base URL de `config`; al no haber
    credenciales vivas en el entorno, el cableado de auth/endpoint final se completa cuando
    se conecte la cuenta (los normalizadores ya estan listos y testeados).
    """
    if agencia == "reuters":
        if not config.reuters_configurado():
            return []
        url = f"{config.reuters_base_url()}/v1/items"
        headers = {"Authorization": f"Bearer {config.reuters_api_key()}"}
        return normalizar_reuters(_descargar_json(url, headers))
    if agencia == "afp":
        if not config.afp_configurado():
            return []
        url = f"{config.afp_base_url()}/v1/api/search"
        headers = {"Authorization": "Bearer <afp-oauth-token>"}
        return normalizar_afp(_descargar_json(url, headers))
    return []
