"""Algoritmos: inteligencia de PLATAFORMA (cambios de algoritmo + tendencias por red).

Aqui seguimos los BLOGS OFICIALES de las plataformas (Meta, YouTube, ...) y agregadores
de industria (Social Media Today, ...) para saber QUE cambia en los algoritmos y que
tendencias funcionan, con dos usos: (1) ir actualizando la ficha editorial de cada
plataforma en la Texto y (2) destacar en el panel las noticias mas importantes
sobre algoritmos para decisiones de marca.

PRINCIPIO CRITICO — HONESTIDAD / SIN INVENTAR
--------------------------------------------------------------------------------------
Misma regla que el Radar: NO se fabrican noticias, importancia ni causas. Las noticias
salen de feeds RSS REALES; la `importancia` es un score HEURISTICO y TRANSPARENTE (suma
de palabras clave que SI aparecen en el texto), y `senales` lista esas palabras para que
la UI muestre el "por que" sin reinterpretar. Una fuente que falla se marca con su error
y NO aporta noticias. Las plataformas que no publican un feed RSS oficial (TikTok,
Instagram, X) se declaran en `fuentes_pendientes()` para mostrar el hueco sin rellenarlo:
su cobertura llega via los agregadores, no inventada.

REUTILIZACION
--------------------------------------------------------------------------------------
La descarga/parseo/guard-SSRF viven en la infra `dominio.http_feed` (capa sin Starlette).
La descarga es el punto INYECTABLE `_DESCARGADOR`; los tests lo parchean sobre `api.rss`
(`monkeypatch.setattr(rss, "_DESCARGADOR", ...)`), que es el seam estable del proyecto,
asi que la ingesta llama a `rss.leer_items_fuente` (re-export de `http_feed` que respeta
ese parche). El TIPO de error controlado es `http_feed.RSSError` (re-exportado tambien
como `rss.RSSError`: misma clase). La clasificacion vive aqui; la persistencia, en
`repos`/`db` (tablas `fuentes_algoritmo` + `noticias_algoritmo`).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from .. import repos
from ..api import rss  # seam de descarga inyectable (`rss._DESCARGADOR`); ver REUTILIZACION
from ..dominio import http_feed

# --------------------------------------------------------------------------- #
# Vocabulario controlado: plataformas, tipos de fuente, niveles                 #
# --------------------------------------------------------------------------- #

# Plataforma de una fuente/noticia (id -> etiqueta humana). `general` = agregador que
# cubre varias redes; la noticia se reubica a una red concreta si el texto la nombra.
PLATAFORMAS: dict[str, str] = {
    "meta": "Meta",
    "instagram": "Instagram",
    "facebook": "Facebook",
    "tiktok": "TikTok",
    "youtube": "YouTube",
    "x": "X (Twitter)",
    "linkedin": "LinkedIn",
    "threads": "Threads",
    "general": "Multiplataforma",
}

# Tipo de fuente: oficial (la propia plataforma) pesa mas que un agregador de industria.
TIPOS: dict[str, str] = {
    "oficial": "Blog oficial",
    "agregador": "Agregador de industria",
}

NIVELES = ("alta", "media", "baja")


def es_plataforma(valor: Any) -> bool:
    return isinstance(valor, str) and valor in PLATAFORMAS


def es_tipo(valor: Any) -> bool:
    return isinstance(valor, str) and valor in TIPOS


# --------------------------------------------------------------------------- #
# Deteccion de plataforma a partir del texto (para agregadores)                 #
# --------------------------------------------------------------------------- #
#
# Cada red declara las palabras que la nombran sin ambiguedad. Conservador: si el texto no
# nombra ninguna red, NO se inventa (se deja la plataforma de la fuente). El orden importa:
# se devuelve la PRIMERA red con mas coincidencias (mas especifica gana sobre `meta`).

_PISTAS_PLATAFORMA: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("instagram", ("instagram", "reels", "ig ")),
    ("tiktok", ("tiktok", "tik tok")),
    ("youtube", ("youtube", "shorts", "youtuber")),
    ("linkedin", ("linkedin",)),
    ("x", ("twitter", "x.com", "tweet")),
    ("threads", ("threads",)),
    ("facebook", ("facebook",)),
    ("meta", ("meta ", "whatsapp", "messenger")),
)


def _detectar_plataforma(texto: str) -> str | None:
    """Red mencionada en el texto (la de mas coincidencias), o None si ninguna."""
    mejor: str | None = None
    mejor_n = 0
    for red, pistas in _PISTAS_PLATAFORMA:
        n = sum(texto.count(p) for p in pistas)
        if n > mejor_n:
            mejor_n = n
            mejor = red
    return mejor


# --------------------------------------------------------------------------- #
# Heuristica de importancia: palabras clave que SI aparecen en el texto         #
# --------------------------------------------------------------------------- #
#
# Dos pesos. SEÑALES FUERTES (peso 3) = cambio de algoritmo / distribucion (lo que de
# verdad mueve a una marca). SEÑALES MEDIAS (peso 1) = actualizacion de producto/politica.
# Cada palabra suma su peso x2 si aparece en el TITULO (mas señal que en el cuerpo). Una
# fuente OFICIAL suma un bonus fijo (la plataforma confirmando pesa mas que un tercero).
# `senales` devuelve las palabras canonicas que dispararon el score (el "por que" honesto).

_SEÑALES_FUERTES: dict[str, tuple[str, ...]] = {
    "algoritmo": ("algorithm", "algoritmo"),
    "ranking": ("ranking", "rank ", "ranks "),
    "feed": ("feed", "for you", "para ti", "recommend", "recomend"),
    "alcance": ("reach", "alcance", "distribution", "distribución", "visibility", "visibilidad"),
    "señal de ranking": ("watch time", "completion", "retención", "retention", "engagement signal", "dwell time"),
    "penalización": ("shadowban", "suppress", "downrank", "penaliz", "deprecat", "demote"),
    "monetización": ("monetiz", "monetización", "revenue", "payout"),
}

_SEÑALES_MEDIAS: dict[str, tuple[str, ...]] = {
    "actualización": ("update", "actualiz", "rolls out", "rolling out", "introduc", "lanza", "launch"),
    "cambio": ("change", "cambio", "revamp", "overhaul", "new "),
    "función": ("feature", "función", "herramienta", "tool"),
    "anuncio": ("announce", "anuncia", "unveil", "presenta"),
    "política": ("policy", "política", "guideline", "rules", "norma"),
    "creadores": ("creator", "creador", "creators", "community"),
}

# Una noticia es "cambio de algoritmo" (candidata a la ficha) si dispara ALGUNA señal fuerte.
_UMBRAL_ALTA = 9
_UMBRAL_MEDIA = 4


def _normalizar(texto: str) -> str:
    """Minusculas + sin acentos + espacios colapsados, para casar palabras de forma estable."""
    texto = (texto or "").lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto)


def _coincide(texto: str, variantes: tuple[str, ...]) -> bool:
    """True si alguna variante aparece en el texto normalizado, por LÍMITE DE PALABRA.

    Toda variante exige límite de palabra al inicio; las que traían espacio final ("new ",
    "rank ") lo exigen también al final (palabra completa). Las variantes-prefijo
    ("penaliz", "monetiz") siguen casando sus derivados ("penalización") porque no llevan
    espacio final.
    """
    for v in variantes:
        vn = _normalizar(v).strip()
        if not vn:
            continue
        palabra_completa = v != v.rstrip()
        patron = r"\b" + re.escape(vn) + (r"\b" if palabra_completa else "")
        if re.search(patron, texto):
            return True
    return False


def clasificar(item: dict[str, Any], fuente: dict[str, Any]) -> dict[str, Any]:
    """Clasifica un item de feed: plataforma + importancia + nivel + señales + es_cambio.

    Heuristica transparente (no LLM, deterministica y sin red): pondera palabras clave
    presentes en titulo/resumen. Devuelve los campos de clasificacion para fusionar con
    el item antes de persistirlo.
    """
    titulo_n = _normalizar(item.get("titulo", ""))
    resumen_n = _normalizar(item.get("resumen", ""))
    texto = f"{titulo_n} {resumen_n}"

    # Plataforma: la de la fuente, salvo que sea agregador/meta y el texto nombre otra red.
    base = fuente.get("plataforma") or "general"
    detectada = _detectar_plataforma(texto)
    if detectada and (base in ("general", "meta")):
        plataforma = detectada
    else:
        plataforma = base

    oficial = (fuente.get("tipo") or "agregador") == "oficial"

    senales: list[str] = []
    puntos = 0
    es_cambio = False
    for etiqueta, variantes in _SEÑALES_FUERTES.items():
        en_titulo = _coincide(titulo_n, variantes)
        en_texto = en_titulo or _coincide(resumen_n, variantes)
        if not en_texto:
            continue
        senales.append(etiqueta)
        puntos += 3 * (2 if en_titulo else 1)
        es_cambio = True
    for etiqueta, variantes in _SEÑALES_MEDIAS.items():
        en_titulo = _coincide(titulo_n, variantes)
        en_texto = en_titulo or _coincide(resumen_n, variantes)
        if not en_texto:
            continue
        senales.append(etiqueta)
        puntos += 1 * (2 if en_titulo else 1)
    if oficial:
        puntos += 2

    if puntos >= _UMBRAL_ALTA:
        nivel = "alta"
    elif puntos >= _UMBRAL_MEDIA:
        nivel = "media"
    else:
        nivel = "baja"

    return {
        "plataforma": plataforma,
        "tipo": fuente.get("tipo") or "agregador",
        "importancia": puntos,
        "nivel": nivel,
        "senales": senales,
        "es_cambio": es_cambio,
    }


# --------------------------------------------------------------------------- #
# Ingesta: descarga + parseo (reusa api.rss) + clasifica + persiste            #
# --------------------------------------------------------------------------- #


def ingerir_fuente(fuente: dict[str, Any]) -> dict[str, int]:
    """Descarga, parsea, clasifica y PERSISTE las noticias de UNA fuente.

    Reusa `rss.leer_items_fuente` (seam de descarga inyectable `rss._DESCARGADOR` + guard
    SSRF de `http_feed`). Propaga `http_feed.RSSError` si la URL ya no es valida, la
    descarga falla o el XML no parsea (el llamante anota el error y la salud). Items sin
    `clave` estable se OMITEN (no se pueden deduplicar). Devuelve `{insertadas,
    actualizadas, omitidas}`.
    """
    items = rss.leer_items_fuente(fuente)
    contador = {"insertadas": 0, "actualizadas": 0, "omitidas": 0}
    for item in items:
        if not (item.get("clave") or "").strip():
            contador["omitidas"] += 1
            continue
        clasif = clasificar(item, fuente)
        noticia = {
            "fuente_id": fuente["id"],
            "fuente_nombre": fuente.get("nombre", ""),
            "titulo": item.get("titulo", ""),
            "resumen": item.get("resumen", ""),
            "enlace": item.get("enlace", ""),
            "fecha": item.get("fecha", ""),
            "clave": item.get("clave", ""),
            **clasif,
        }
        estado = repos.guardar_noticia_algoritmo(noticia)
        if estado == "insertada":
            contador["insertadas"] += 1
        elif estado == "actualizada":
            contador["actualizadas"] += 1
        else:
            contador["omitidas"] += 1
    return contador


def refrescar(solo_fuente: str | None = None) -> dict[str, Any]:
    """Refresca TODAS las fuentes activas (o solo `solo_fuente`). Degradacion honesta.

    Cada fuente que falla se anota con su error y NO rompe las demas. Devuelve un resumen
    `{fuentes, insertadas, actualizadas, errores:[{fuente_id, fuente_nombre, error}]}`.
    """
    if solo_fuente:
        una = repos.obtener_fuente_algoritmo(solo_fuente)
        fuentes = [una] if una is not None else []
    else:
        fuentes = repos.listar_fuentes_algoritmo()
    activas = [f for f in fuentes if f.get("activo", True)]

    resumen: dict[str, Any] = {
        "fuentes": len(activas),
        "insertadas": 0,
        "actualizadas": 0,
        "errores": [],
    }
    for fuente in activas:
        try:
            cont = ingerir_fuente(fuente)
            resumen["insertadas"] += cont["insertadas"]
            resumen["actualizadas"] += cont["actualizadas"]
            repos.registrar_salud_fuente_algoritmo(
                fuente["id"], conteo=cont["insertadas"] + cont["actualizadas"], error=""
            )
        except http_feed.RSSError as e:
            repos.registrar_salud_fuente_algoritmo(fuente["id"], conteo=0, error=str(e))
            resumen["errores"].append(
                {"fuente_id": fuente["id"], "fuente_nombre": fuente.get("nombre", ""), "error": str(e)}
            )
        except Exception:  # noqa: BLE001 -- nunca un traceback crudo; se omite la fuente
            mensaje = "No se pudo leer el feed."
            repos.registrar_salud_fuente_algoritmo(fuente["id"], conteo=0, error=mensaje)
            resumen["errores"].append(
                {"fuente_id": fuente["id"], "fuente_nombre": fuente.get("nombre", ""), "error": mensaje}
            )
    return resumen


# --------------------------------------------------------------------------- #
# Fuentes INICIAL (verificadas con feed RSS real) + huecos honestos             #
# --------------------------------------------------------------------------- #
#
# Solo feeds RSS COMPROBADOS (se valido que devuelven XML de feed). El equipo puede
# añadir/editar mas desde la UI. TikTok, Instagram y X NO publican un feed oficial: su
# cobertura llega via los agregadores; el hueco se declara en `fuentes_pendientes()`.

FUENTES_INICIAL: tuple[dict[str, str], ...] = (
    {
        "nombre": "Meta Newsroom",
        "url": "https://about.fb.com/news/feed/",
        "plataforma": "meta",
        "tipo": "oficial",
    },
    {
        "nombre": "YouTube · Blog oficial",
        "url": "https://blog.youtube/rss/",
        "plataforma": "youtube",
        "tipo": "oficial",
    },
    {
        "nombre": "Social Media Today",
        "url": "https://www.socialmediatoday.com/feeds/news/",
        "plataforma": "general",
        "tipo": "agregador",
    },
    {
        "nombre": "TechCrunch · Social",
        "url": "https://techcrunch.com/tag/social/feed/",
        "plataforma": "general",
        "tipo": "agregador",
    },
)


def fuentes_pendientes() -> list[dict[str, str]]:
    """Plataformas SIN feed RSS oficial: se declara el hueco, no se inventa.

    Su cobertura llega via los agregadores (Social Media Today / TechCrunch). La UI las
    muestra como "sin feed oficial" para ser honesta sobre que NO hay una fuente primaria.
    """
    return [
        {
            "plataforma": "tiktok",
            "nombre": "TikTok Newsroom",
            "motivo": "TikTok no publica un feed RSS oficial; se cubre via agregadores.",
        },
        {
            "plataforma": "instagram",
            "nombre": "Instagram / @Creators",
            "motivo": "Instagram no expone un feed RSS; se cubre via Meta Newsroom y agregadores.",
        },
        {
            "plataforma": "x",
            "nombre": "X · @XEng",
            "motivo": "X no publica un feed RSS oficial; se cubre via agregadores.",
        },
    ]


def inicializar() -> list[dict[str, Any]]:
    """Crea las fuentes INICIAL que aun no existan (idempotente por URL). Devuelve las nuevas.

    No borra ni toca las que el equipo haya añadido. Pensado para el primer arranque y para
    un boton "restaurar fuentes recomendadas" desde la UI.
    """
    existentes = {f.get("url", "").strip() for f in repos.listar_fuentes_algoritmo()}
    creadas: list[dict[str, Any]] = []
    for inicial in FUENTES_INICIAL:
        if inicial["url"] in existentes:
            continue
        creadas.append(
            repos.crear_fuente_algoritmo(
                inicial["nombre"],
                inicial["url"],
                plataforma=inicial["plataforma"],
                tipo=inicial["tipo"],
            )
        )
    return creadas


# --------------------------------------------------------------------------- #
# Propuesta para la Texto (la decide el equipo: NO escribe la ficha sola)  #
# --------------------------------------------------------------------------- #


def texto_propuesta_ficha(noticia: dict[str, Any]) -> str:
    """Borrador markdown para añadir a la ficha editorial de una plataforma.

    Devuelve un bloque listo para pegar/confirmar en la Texto. NO escribe la ficha:
    la linea editorial es verdad CURADA por humanos (mismo principio que el Radar: el
    sistema PROPONE, el equipo decide).
    """
    plataforma = PLATAFORMAS.get(noticia.get("plataforma", "general"), "Multiplataforma")
    fecha = noticia.get("fecha", "") or "s/f"
    titulo = noticia.get("titulo", "").strip() or "(sin título)"
    resumen = noticia.get("resumen", "").strip()
    enlace = noticia.get("enlace", "").strip()
    senales = ", ".join(noticia.get("senales", []) or [])
    lineas = [f"- **{titulo}** ({plataforma} · {fecha})"]
    if resumen:
        lineas.append(f"  - {resumen}")
    if senales:
        lineas.append(f"  - Señales: {senales}")
    if enlace:
        lineas.append(f"  - Fuente: {enlace}")
    return "\n".join(lineas)
