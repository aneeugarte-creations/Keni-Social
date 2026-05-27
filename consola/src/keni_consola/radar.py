"""Radar de tendencias: consolida lo MAS VIRAL del momento, multi-red (F7 · #147).

Superficie de DESCUBRIMIENTO, distinta de:
  - Termometro (noticias internacionales CURADAS a mano para el posteo de galeria),
  - `resumen-tendencia` (resume UNA tendencia ya dada),
  - Verificacion (¿el video es nuevo o reciclado?).

El radar TRAE y CONSOLIDA lo que esta reventando ahora, agrupado por tema, deduplicado
y priorizado por SEÑAL, con un "por que sube" y enlaces. SOLO PROPONE: no publica nada;
el equipo decide la relevancia editorial.

PRINCIPIO CRITICO — HONESTIDAD / SIN INVENTAR
--------------------------------------------------------------------------------------
Esta es LA regla de esta feature. El radar NUNCA fabrica tendencias, conteos ni "por que
sube": solo muestra lo que devuelven fuentes REALES. Una fuente que no esta disponible
(falta API/credencial, o falla la descarga) se marca explicitamente como NO DISPONIBLE
con su motivo, y NO aporta items. Sin datos de muestra, sin relleno.

FUENTES (Fase 1)
--------------------------------------------------------------------------------------
EN VIVO, sin credenciales:
  - Google Trends (busquedas en tendencia por pais, feed RSS publico con namespace `ht:`):
    da el termino en tendencia, su trafico aproximado (`ht:approx_traffic` = la SEÑAL
    honesta) y las notas que lo explican (`ht:news_item`). Cobertura: red "Búsquedas"
    (Google) por geo (def. MX).
  - Feeds RSS del equipo (los que ya gestiona la pagina Fuentes): se reusan tal cual como
    señal editorial; no traen un conteo de viralidad, asi que su señal es CUALITATIVA.

PENDIENTES (requieren API/credencial externa que aun no esta en el entorno) — ver
`fuentes_pendientes()`: TikTok, Instagram/Meta, X, YouTube trending. Se listan con su
motivo para que la UI las muestre como "fuente no disponible" sin inventar nada.

REUTILIZACION
--------------------------------------------------------------------------------------
La descarga pasa por `api.rss._DESCARGADOR` (mismo punto INYECTABLE que el RSS del
equipo): aplica los limites de tamaño/timeout y, en tests, se parchea para NO tocar la
red. La URL del feed de Trends pasa por el guard SSRF de `api.rss.validar_url`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from xml.etree import ElementTree as ET

from .api import rss

# --------------------------------------------------------------------------- #
# Geos soportados por el feed de Google Trends (pais -> etiqueta humana)        #
# --------------------------------------------------------------------------- #
#
# El feed publico de Google Trends acepta `?geo=XX` (ISO 3166-1 alpha-2). Acotamos a
# una allowlist relevante para el piloto (MX el principal) para no construir URLs con
# entrada libre. MX es el geo por defecto del radar.

GEO_DEFECTO = "MX"

GEOS: dict[str, str] = {
    "MX": "México",
    "US": "Estados Unidos",
    "ES": "España",
    "AR": "Argentina",
    "CO": "Colombia",
    "CL": "Chile",
}


def es_geo(geo: Any) -> bool:
    """True si `geo` es un pais soportado por el radar."""
    return isinstance(geo, str) and geo in GEOS


def _url_trends(geo: str) -> str:
    """URL del feed RSS publico de Google Trends para un geo de la allowlist."""
    return f"https://trends.google.com/trending/rss?geo={geo}"


# Maximo de temas a devolver tras consolidar (la UI muestra un radar escaneable, no todo).
MAX_TEMAS = 40
# Maximo de enlaces "por que" por tema (las notas que explican la subida).
MAX_ENLACES = 5
# Recorte defensivo de textos.
_MAX_TITULO = 300
_MAX_TEXTO = 500


# --------------------------------------------------------------------------- #
# Modelo de salida                                                              #
# --------------------------------------------------------------------------- #


@dataclass
class Enlace:
    """Una nota/enlace que explica por que sube un tema (titulo + url + medio)."""

    titulo: str
    url: str
    fuente: str = ""

    def a_dict(self) -> dict[str, str]:
        return {"titulo": self.titulo, "url": self.url, "fuente": self.fuente}


@dataclass
class Tema:
    """Un tema en tendencia, consolidado de una o varias fuentes.

    `senal` es un entero comparable para PRIORIZAR (mayor = mas viral). Sale de datos
    REALES: para Trends, el trafico aproximado parseado (`ht:approx_traffic`); para los
    feeds del equipo, una señal baja fija (presencia, sin conteo). `senal_texto` es la
    señal tal cual la da la fuente, para mostrarla sin reinterpretar ("50 mil+").
    """

    titulo: str
    redes: set[str] = field(default_factory=set)
    fuentes: set[str] = field(default_factory=set)
    por_que: str = ""
    senal: int = 0
    senal_texto: str = ""
    enlaces: list[Enlace] = field(default_factory=list)
    _claves_enlace: set[str] = field(default_factory=set, repr=False)

    def fusionar(self, otro: Tema) -> None:
        """Funde `otro` en este tema (mismo asunto detectado por clave normalizada)."""
        self.redes |= otro.redes
        self.fuentes |= otro.fuentes
        # Conserva la señal mas alta y su texto (la fuente con mas viralidad manda).
        if otro.senal > self.senal:
            self.senal = otro.senal
            self.senal_texto = otro.senal_texto
        elif not self.senal_texto:
            self.senal_texto = otro.senal_texto
        if otro.por_que and not self.por_que:
            self.por_que = otro.por_que
        for enlace in otro.enlaces:
            self._anadir_enlace(enlace)

    def _anadir_enlace(self, enlace: Enlace) -> None:
        """Añade un enlace deduplicado por URL (hasta MAX_ENLACES)."""
        clave = (enlace.url or enlace.titulo).strip().lower()
        if not clave or clave in self._claves_enlace:
            return
        if len(self.enlaces) >= MAX_ENLACES:
            return
        self._claves_enlace.add(clave)
        self.enlaces.append(enlace)

    def a_dict(self) -> dict[str, Any]:
        return {
            "titulo": self.titulo,
            "redes": sorted(self.redes),
            "fuentes": sorted(self.fuentes),
            "por_que": self.por_que,
            "senal": self.senal,
            "senal_texto": self.senal_texto,
            "enlaces": [e.a_dict() for e in self.enlaces],
        }


# --------------------------------------------------------------------------- #
# Normalizacion / dedup                                                         #
# --------------------------------------------------------------------------- #

_RE_NO_ALNUM = re.compile(r"[^a-z0-9áéíóúñü ]+", re.IGNORECASE)
_RE_ESPACIOS = re.compile(r"\s+")


def _normalizar_clave(titulo: str) -> str:
    """Clave de dedup de un tema: minusculas, sin signos, espacios colapsados.

    Conservadora a proposito: solo funde temas con el MISMO titulo normalizado (no hace
    clustering semantico). Asi nunca inventa una agrupacion que no esta en los datos.
    """
    texto = (titulo or "").strip().lower()
    texto = _RE_NO_ALNUM.sub(" ", texto)
    texto = _RE_ESPACIOS.sub(" ", texto).strip()
    return texto


def _recortar(texto: str, maximo: int) -> str:
    texto = (texto or "").strip()
    return texto[:maximo].rstrip() if len(texto) > maximo else texto


# --------------------------------------------------------------------------- #
# Señal de Google Trends: parseo HONESTO de `ht:approx_traffic`                 #
# --------------------------------------------------------------------------- #

# "100+", "2K+", "50 mil+", "1M+", "1,000+". Devolvemos un entero comparable y el
# texto original para mostrarlo sin reinterpretar. Las palabras (mil/millones) van ANTES
# de las letras sueltas (k/m) en la alternancia para que "mil" no case como "m".
_RE_TRAFICO = re.compile(
    r"([\d.,]+)\s*(millones|millón|million|mil|[kmKM])?", re.IGNORECASE
)
_MULTIPLICADOR = {
    "k": 1_000,
    "m": 1_000_000,
    "mil": 1_000,
    "millones": 1_000_000,
    "millón": 1_000_000,
    "million": 1_000_000,
}


def traduce_trafico(crudo: str) -> int:
    """Convierte un `approx_traffic` ("2K+", "50 mil+") a un entero comparable, o 0.

    No fabrica nada: si no hay numero parseable, devuelve 0 (señal desconocida). Solo
    se usa para ORDENAR; el texto original se muestra tal cual en `senal_texto`.
    """
    if not isinstance(crudo, str) or not crudo.strip():
        return 0
    m = _RE_TRAFICO.search(crudo)
    if not m:
        return 0
    numero_txt = m.group(1).replace(",", "").replace(".", "")
    if not numero_txt.isdigit():
        return 0
    base = int(numero_txt)
    sufijo = (m.group(2) or "").lower()
    return base * _MULTIPLICADOR.get(sufijo, 1)


# --------------------------------------------------------------------------- #
# Parser del feed de Google Trends (namespace `ht:`)                            #
# --------------------------------------------------------------------------- #
#
# El RSS generico de `api.rss.parsear_feed` descarta el namespace `ht:` (trafico y
# notas), que es justo la señal que necesita el radar. Por eso el radar parsea el feed
# de Trends con su propio lector (misma stdlib `xml.etree`, tolerante), reutilizando el
# DESCARGADOR inyectable y el guard SSRF de `api.rss`.


def _texto_hijo(elemento: ET.Element, *nombres: str) -> str:
    """Texto del primer hijo cuyo nombre local este en `nombres` (ignora namespace)."""
    hijo = rss._buscar_hijo(elemento, *nombres)
    return rss._texto_local(hijo)


def _enlaces_de_item(item: ET.Element) -> list[Enlace]:
    """Extrae los `ht:news_item` de un item de Trends como enlaces (titulo+url+medio)."""
    enlaces: list[Enlace] = []
    for hijo in item:
        if rss._quitar_ns(hijo.tag) != "news_item":
            continue
        titulo = _texto_hijo(hijo, "news_item_title")
        url = _texto_hijo(hijo, "news_item_url")
        fuente = _texto_hijo(hijo, "news_item_source")
        if titulo or url:
            enlaces.append(
                Enlace(titulo=_recortar(titulo, _MAX_TITULO), url=url.strip(), fuente=fuente.strip())
            )
    return enlaces


def parsear_trends(xml: str, *, geo: str) -> list[Tema]:
    """Parsea el feed RSS de Google Trends a una lista de `Tema`. Lanza `RSSError`.

    Cada `<item>` es un termino en tendencia: titulo + `ht:approx_traffic` (la señal) +
    sus `ht:news_item` (el "por que sube" + enlaces). Tolerante: campos ausentes salen
    vacios. No inventa: si no hay trafico, la señal queda en 0.
    """
    try:
        raiz = ET.fromstring(xml)
    except ET.ParseError as e:
        raise rss.RSSError("El feed de tendencias no es un XML válido.") from e

    canal = rss._buscar_hijo(raiz, "channel")
    contenedor = canal if canal is not None else raiz
    items = [h for h in contenedor if rss._quitar_ns(h.tag) == "item"]

    temas: list[Tema] = []
    red = f"busquedas-{geo.lower()}"
    for item in items[:MAX_TEMAS]:
        titulo = _recortar(_texto_hijo(item, "title"), _MAX_TITULO)
        if not titulo:
            continue
        trafico = _texto_hijo(item, "approx_traffic")
        enlaces = _enlaces_de_item(item)
        # "Por que sube": señal real + la nota mas relevante (sin inventar la causa).
        partes: list[str] = []
        if trafico:
            partes.append(f"~{trafico} búsquedas en {GEOS.get(geo, geo)}")
        if enlaces and enlaces[0].titulo:
            partes.append(enlaces[0].titulo)
        por_que = _recortar(" · ".join(partes), _MAX_TEXTO)
        temas.append(
            Tema(
                titulo=titulo,
                redes={red},
                fuentes={"Google Trends"},
                por_que=por_que,
                senal=traduce_trafico(trafico),
                senal_texto=trafico.strip(),
                enlaces=enlaces,
                _claves_enlace={(e.url or e.titulo).strip().lower() for e in enlaces},
            )
        )
    return temas


# --------------------------------------------------------------------------- #
# Feeds del equipo (Fuentes RSS) como señal editorial                           #
# --------------------------------------------------------------------------- #

# Señal cualitativa fija para items de feeds RSS (no traen un conteo de viralidad): se
# ordenan DEBAJO de cualquier tema de Trends con conteo real, pero por encima de los
# Trends sin trafico. No es un numero inventado de viralidad: es un peso de presencia.
_SENAL_FEED = 1


def temas_de_feeds(items: list[dict[str, Any]]) -> list[Tema]:
    """Convierte items de feeds RSS del equipo en `Tema` (señal cualitativa).

    `items` son los que devuelve `api.rss._items_de_fuente` ({titulo, resumen, enlace,
    fuente_nombre, ...}). El "por que sube" es el resumen del feed (no un conteo), y se
    deja claro que la señal es editorial, no de viralidad.
    """
    temas: list[Tema] = []
    for item in items:
        titulo = _recortar(str(item.get("titulo", "")), _MAX_TITULO)
        if not titulo:
            continue
        fuente = str(item.get("fuente_nombre", "")).strip() or "RSS"
        enlace = str(item.get("enlace", "")).strip()
        resumen = _recortar(str(item.get("resumen", "")), _MAX_TEXTO)
        temas.append(
            Tema(
                titulo=titulo,
                redes={"rss"},
                fuentes={fuente},
                por_que=resumen,
                senal=_SENAL_FEED,
                senal_texto="",
                enlaces=[Enlace(titulo=titulo, url=enlace, fuente=fuente)] if enlace else [],
                _claves_enlace={enlace.lower()} if enlace else set(),
            )
        )
    return temas


# --------------------------------------------------------------------------- #
# Consolidacion: dedup + prioridad por señal                                    #
# --------------------------------------------------------------------------- #


def consolidar(*grupos: list[Tema]) -> list[Tema]:
    """Funde temas de varias fuentes por clave normalizada y ordena por señal desc.

    Dedup: temas con el mismo titulo normalizado se funden (uniendo redes/fuentes/
    enlaces y quedandose la señal mas alta). Orden: señal desc, y a igualdad, mas
    fuentes (un tema que aparece en varias redes pesa mas) y luego alfabetico estable.
    """
    por_clave: dict[str, Tema] = {}
    for grupo in grupos:
        for tema in grupo:
            clave = _normalizar_clave(tema.titulo)
            if not clave:
                continue
            existente = por_clave.get(clave)
            if existente is None:
                por_clave[clave] = tema
            else:
                existente.fusionar(tema)
    temas = list(por_clave.values())
    temas.sort(key=lambda t: (-t.senal, -len(t.fuentes), t.titulo.lower()))
    return temas[:MAX_TEMAS]


# --------------------------------------------------------------------------- #
# Fuentes PENDIENTES (degradacion honesta, documentadas)                        #
# --------------------------------------------------------------------------- #
#
# Redes cuyo "lo mas viral del momento" NO se puede traer hoy sin una API/credencial
# que no esta en el entorno. Se devuelven a la UI como fuentes NO DISPONIBLES, con el
# motivo, para que se vea el hueco sin inventar datos. La recomendacion build/no-build
# vive en el reporte del issue, no en runtime.


def fuentes_pendientes() -> list[dict[str, str]]:
    """Lista de redes que el radar AUN no cubre, con el motivo (sin inventar datos)."""
    return [
        {
            "red": "tiktok",
            "nombre": "TikTok",
            "motivo": (
                "No hay feed público de tendencias. Requiere la Research/Display API de "
                "TikTok (acceso aprobado y credenciales), que no están en este entorno."
            ),
        },
        {
            "red": "instagram",
            "nombre": "Instagram",
            "motivo": (
                "Meta no expone un feed público de “reels/temas en tendencia”. Requeriría "
                "la Graph API con permisos avanzados, que no están en este entorno."
            ),
        },
        {
            "red": "x",
            "nombre": "X",
            "motivo": (
                "Los trending topics de X ya no tienen API pública gratuita. Requeriría un "
                "plan de la API de X (de pago), que no está en este entorno."
            ),
        },
        {
            "red": "youtube",
            "nombre": "YouTube",
            "motivo": (
                "El “en tendencia” de YouTube necesita la YouTube Data API v3 (clave). "
                "Pendiente de habilitar; aún no está conectada en este entorno."
            ),
        },
    ]
