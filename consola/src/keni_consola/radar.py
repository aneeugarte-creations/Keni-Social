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
El parseo del feed de Trends reutiliza los helpers PUROS de la infra `dominio.http_feed`
(`_buscar_hijo`/`_texto_local`/`_quitar_ns` y `RSSError`), no el router `api.rss`: el
dominio no debe importar la capa de transporte. La DESCARGA del feed de Trends (con sus
limites de tamaño/timeout y el guard SSRF) la hace el router `api/radar.py` via el punto
INYECTABLE `rss._DESCARGADOR` (re-exportado desde `http_feed`); en tests se parchea para
NO tocar la red.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any
from xml.etree import ElementTree as ET

from .dominio import http_feed

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
    # `True` si el tema viene de una fuente que el equipo etiquetó con la marca activa
    # (curado): entra al foco de la marca SIEMPRE, sin pasar por el filtro de keywords.
    curado: bool = False
    _claves_enlace: set[str] = field(default_factory=set, repr=False)

    def fusionar(self, otro: Tema) -> None:
        """Funde `otro` en este tema (mismo asunto detectado por clave normalizada)."""
        self.redes |= otro.redes
        self.fuentes |= otro.fuentes
        self.curado = self.curado or otro.curado
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
            "curado": self.curado,
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
# El RSS generico de `http_feed.parsear_feed` descarta el namespace `ht:` (trafico y
# notas), que es justo la señal que necesita el radar. Por eso el radar parsea el feed
# de Trends con su propio lector (misma stdlib `xml.etree`, tolerante), reutilizando los
# helpers PUROS de `dominio.http_feed` (el guard SSRF y el DESCARGADOR inyectable los
# aplica el router `api/radar.py`).


def _texto_hijo(elemento: ET.Element, *nombres: str) -> str:
    """Texto del primer hijo cuyo nombre local este en `nombres` (ignora namespace)."""
    hijo = http_feed._buscar_hijo(elemento, *nombres)
    return http_feed._texto_local(hijo)


def _enlaces_de_item(item: ET.Element) -> list[Enlace]:
    """Extrae los `ht:news_item` de un item de Trends como enlaces (titulo+url+medio)."""
    enlaces: list[Enlace] = []
    for hijo in item:
        if http_feed._quitar_ns(hijo.tag) != "news_item":
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
        raise http_feed.RSSError("El feed de tendencias no es un XML válido.") from e

    canal = http_feed._buscar_hijo(raiz, "channel")
    contenedor = canal if canal is not None else raiz
    items = [h for h in contenedor if http_feed._quitar_ns(h.tag) == "item"]

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


def temas_de_feeds(items: list[dict[str, Any]], *, curado: bool = False) -> list[Tema]:
    """Convierte items de feeds RSS del equipo en `Tema` (señal cualitativa).

    `items` son los que devuelve `api.rss._items_de_fuente` (router; {titulo, resumen, enlace,
    fuente_nombre, ...}). El "por que sube" es el resumen del feed (no un conteo), y se
    deja claro que la señal es editorial, no de viralidad. `curado=True` marca los temas
    como propios de la marca activa (entran a su foco sin filtro de keywords).
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
                curado=curado,
                enlaces=[Enlace(titulo=titulo, url=enlace, fuente=fuente)] if enlace else [],
                _claves_enlace={enlace.lower()} if enlace else set(),
            )
        )
    return temas


# --------------------------------------------------------------------------- #
# Consolidacion: dedup + prioridad por señal                                    #
# --------------------------------------------------------------------------- #


# Umbral de similitud para el SEGUNDO pase (fuzzy): dos titulos cuyo ratio de
# `SequenceMatcher` supera esto se consideran el MISMO tema. Alto a proposito (0.85): el
# objetivo es cazar variantes triviales ("Liga MX" vs "Liga mx jornada"), NO agrupar
# semanticamente temas distintos. Subirlo reduce falsos positivos; bajarlo, falsos negativos.
_UMBRAL_FUZZY = 0.85
# Longitud minima de un titulo normalizado para entrar al fuzzy. Titulos muy cortos
# ("ee", "tv") disparan ratios altos espurios entre si; se quedan SOLO en el dedup exacto.
_MIN_LONGITUD_FUZZY = 6

# Diccionario de SINONIMOS / variantes de escritura para el fuzzy. Cada grupo se colapsa a
# su forma CANONICA (la clave) ANTES de comparar, asi "cdmx"/"ciudad de mexico"/"df" o
# "vs"/"versus" no cuentan como diferencia. Conservador: solo entradas inequivocas del
# dominio (deportes/MX); ampliar con cuidado para no fusionar temas que no son el mismo.
_SINONIMOS: dict[str, tuple[str, ...]] = {
    "cdmx": ("ciudad de mexico", "df", "distrito federal"),
    "vs": ("versus", "contra"),
    "futbol": ("football", "soccer"),
    "estados unidos": ("eeuu", "ee uu", "usa", "us"),
    "seleccion mexicana": ("el tri", "tricolor"),
}
# Mapa inverso (variante -> canonica), pre-calculado una vez. Las variantes mas LARGAS
# primero para que el reemplazo por substring no parta una variante dentro de otra.
_VARIANTE_A_CANONICA: tuple[tuple[str, str], ...] = tuple(
    sorted(
        (
            (variante, canonica)
            for canonica, variantes in _SINONIMOS.items()
            for variante in variantes
        ),
        key=lambda par: -len(par[0]),
    )
)


def _sin_acentos(texto: str) -> str:
    """Quita acentos (NFD + descarta diacriticos) para comparar sin depender de tildes."""
    return "".join(c for c in unicodedata.normalize("NFD", texto) if not unicodedata.combining(c))


def _clave_fuzzy(titulo: str) -> str:
    """Clave NORMALIZADA para el fuzzy: minuscula, sin acentos, sin signos y con sinonimos.

    Sobre la clave exacta (`_normalizar_clave`) aplica: quitar acentos y colapsar los grupos
    de `_SINONIMOS` a su forma canonica. Asi "Selección Mexicana" y "el Tri" comparten base
    y el `SequenceMatcher` los ve casi identicos. Determinista y pura.
    """
    base = _sin_acentos(_normalizar_clave(titulo))
    for variante, canonica in _VARIANTE_A_CANONICA:
        base = re.sub(rf"\b{re.escape(variante)}\b", canonica, base)
    return _RE_ESPACIOS.sub(" ", base).strip()


def _fundir_similares(temas: list[Tema]) -> list[Tema]:
    """SEGUNDO pase de dedup: funde temas con titulos MUY similares (fuzzy + sinonimos).

    Entra ya sin duplicados EXACTOS (los resolvio `_normalizar_clave`). Aqui se comparan las
    claves fuzzy con `SequenceMatcher`: si el ratio supera `_UMBRAL_FUZZY`, se funde el tema
    en el representante YA aceptado (orden de entrada = prioridad, asi gana el de mayor señal,
    que `consolidar` ya ordeno antes de llamar aqui). Conservador para no agrupar temas
    distintos: claves cortas no entran al fuzzy y el umbral es alto. Funcion PURA.
    """
    representantes: list[tuple[str, Tema]] = []  # (clave_fuzzy, tema)
    for tema in temas:
        clave = _clave_fuzzy(tema.titulo)
        if not clave:
            continue
        fusionado = False
        if len(clave) >= _MIN_LONGITUD_FUZZY:
            for clave_rep, rep in representantes:
                if len(clave_rep) < _MIN_LONGITUD_FUZZY:
                    continue
                if SequenceMatcher(None, clave_rep, clave).ratio() >= _UMBRAL_FUZZY:
                    rep.fusionar(tema)
                    fusionado = True
                    break
        if not fusionado:
            representantes.append((clave, tema))
    return [rep for _, rep in representantes]


def consolidar(*grupos: list[Tema]) -> list[Tema]:
    """Funde temas de varias fuentes y ordena por señal desc. Dedup en DOS pases.

    Pase 1 (exacto): temas con el mismo titulo normalizado (`_normalizar_clave`) se funden
    (uniendo redes/fuentes/enlaces y quedandose la señal mas alta). Pase 2 (fuzzy): sobre el
    resultado YA ordenado por señal, se funden titulos MUY similares (`_fundir_similares`:
    `SequenceMatcher` > umbral + diccionario de sinonimos), conservando el representante de
    mayor señal. Orden final: señal desc, y a igualdad, mas fuentes y alfabetico estable.
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
    # Ordena ANTES del fuzzy para que el representante de cada cluster sea el de mayor señal
    # (el primero que ve `_fundir_similares` en su orden de entrada).
    temas.sort(key=lambda t: (-t.senal, -len(t.fuentes), t.titulo.lower()))
    temas = _fundir_similares(temas)
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
