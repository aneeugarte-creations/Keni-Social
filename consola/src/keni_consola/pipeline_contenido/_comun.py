"""Constantes, seams y helpers COMPARTIDOS del pipeline de contenido (CI→verificación→CD).

Núcleo común a las distintas etapas (ingesta, verificación, copy, barrido): constantes del flujo,
los seams inyectables de `og:image`, el sello de ACTIVIDAD por etapa (`registrar_etapa`), el
autor de los lanzamientos y los lectores de temas/copy que más de una etapa comparte. Vive
aparte para que los módulos de etapa no se importen entre sí (evita ciclos): todos dependen
de `_comun`, no al revés.
"""

from __future__ import annotations

import html as _html
import logging
import re
from typing import Any

from .. import config, generaciones, marcas, redes, repos
from ..dominio import http_feed
from ..dominio import verificar_fuente as dom_verificar

__all__ = [
    # módulos/seams reexportados que algún consumidor referencia vía el paquete
    "Any",
    "logging",
    "re",
    "config",
    "generaciones",
    "marcas",
    "repos",
    "redes",
    "dom_verificar",
    "_log",
    # constantes de flujo
    "ORIGEN_PIPELINE",
    "TIPO_ACTIVIDAD",
    "TIPO_PIPELINE",
    "ETAPA_ADMITIR",
    "ETAPA_REDACTAR",
    "ETAPA_VERIFICAR",
    "ETAPA_SUGERIR_HASHTAGS",
    "_DIAS_DEDUP",
    "_FORMATO_PIPELINE",
    "PROMPT_VERIFICACION_ID",
    "_TITULO_VERIFICACION",
    "VERIFICACION_EN_CURSO",
    "VERIFICACION_SALTADA",
    "VERIFICACION_CADUCADA",
    "VERIFICACION_NO_VERIFICADO",
    "VERIFICACION_PROBLEMA",
    "_DEFAULT_VERIFICACION_CRITERIOS",
    # og:image
    "_RE_OG_IMAGE",
    "_RE_CONTENT",
    "_OG_MAX_BYTES",
    "_OG_TIMEOUT_S",
    "_FETCH_OG_IMAGE",
    "_fetch_og_image_real",
    "_fetch_html_validado",
    "_extraer_og_image",
    # cuerpo del artículo + limpieza del snippet (enriquecer la nota de origen)
    "_FETCH_ARTICULO",
    "_fetch_articulo_real",
    "_extraer_texto_articulo",
    "_limpiar_snippet",
    # actividad / autor / lecturas compartidas
    "registrar_etapa",
    "ADMISION_VERIFICACION_ESTADOS",
    "VERIFICADAS_OK",
    "admision_verificacion",
    "_autor_pipeline",
    "_copy_pendiente_leido",
    "_tiene_copy",
    "_MAX_INTENTOS_ETAPA",
    "_BACKOFF_ETAPA_SEG",
    "intentos_de",
    "anotar_intento",
    "en_backoff",
    "marcar_fallo_etapa",
    "temas_pipeline",
]

_log = logging.getLogger("keni_consola.pipeline_contenido")

# Origen reservado de los BORRADORES producidos por el pipeline (en el `contenido` padre que
# los NIDA). La dedup de la pasada verificación y la UI distinguen lo del pipeline de lo manual/otro auto.
ORIGEN_PIPELINE = "pipeline"

# `tipo` con el que se sellan los MARCADORES de etapa (CI/CD/verificación): registros `generaciones`
# ligeros SIN coste (no llaman a `claude`). Llevan tipo PROPIO `pipeline_etapa` para que la
# vista "Actividad IA" los EXCLUYA (no son trabajo con tokens/coste; serían irrelevantes a 0). El
# trabajo REAL con coste (verificación verificación, copy, arte, fusión/encaje del pool) se sella
# `tipo='pipeline'` (TIPO_PIPELINE) y SÍ aparece en Actividad con sus tokens/coste/tiempo: TODO
# lo que lanza la máquina es UN solo tipo; lo manual (copy a mano, imagen del Estudio) conserva
# su tipo propio. La vista Pipelines lee los marcadores por `publicacion_id`. La ETAPA viaja en la
# `etiqueta` ("ADMITIR · ..."/"REDACTAR · ..."/"VERIFICAR · ...").
TIPO_ACTIVIDAD = "pipeline_etapa"
# `tipo` ÚNICO de toda generación REAL que lanza el pipeline (verificación verificación, copy, arte, Haiku del
# pool): trabajo con tokens/coste/tiempo, identificable y medible en Actividad como `pipeline`.
TIPO_PIPELINE = "pipeline"

ETAPA_ADMITIR = "ADMITIR"
ETAPA_REDACTAR = "REDACTAR"
ETAPA_VERIFICAR = "VERIFICAR"
ETAPA_SUGERIR_HASHTAGS = "SUGERIR_HASHTAGS"
ETAPA_ILUSTRAR = "ILUSTRAR"

# FLUJO CONTINUO: el pipeline NO tiene topes por etapa (verificaciones verificación/copies/autogen/revisados). El
# volumen lo regula la ADMISIÓN (`config.pipeline_max()` + el gate serial WIP
# `config.pipeline_en_proceso_max()`, editables en el Monitor) y el backpressure de la cola.

# DEDUP de contenido: ventana (días) hacia atrás para considerar que una noticia "ya está" en la
# marca. Un tema nuevo cuyo título coincide (normalizado) con otro contenido de la MISMA marca
# creado en esta ventana NO se crea: cubre el duplicado en la cola (misma noticia por dos fuentes)
# y el republicado de lo ya salido hace poco. Fuera de la ventana, una noticia recurrente sí entra.
_DIAS_DEDUP = 60

# El pipeline no sabe de antemano si un ítem será FOTO o VIDEO, así que crea piezas de FOTO
# (regla del dueño: foto -> 3 redes IG/X/FB). El mapeo formato->redes vive en
# `redes.redes_de_formato` (fuente única); video -> las 5 queda definido para flujos futuros.
_FORMATO_PIPELINE = redes.FORMATO_FOTO

# --- Verificar la FUENTE por DOCUMENTO de Texto (no skills) ------------------------------
# El equipo NO usa skills: la verificación pre-copy de la FUENTE se hace adjuntando un DOCUMENTO de la
# Texto con los criterios. Regla del dueño: "si el documento existe, adjúntalo; si no existe,
# créalo y adjúntalo." Apunta al prompt EDITABLE `prompt/verificar` (pestaña «Prompts»), cuyo
# cuerpo base viaja en la inicial. El título DEBE sluggear al id (`crear` deriva el id del
# slug del título): "Verificar" -> "prompt/verificar". DISTINTO de Revisar el COPY (`prompt/revision`).
PROMPT_VERIFICACION_ID = "prompt/verificar"
_TITULO_VERIFICACION = "Verificar"
# Etiqueta HUMANA de la generación de la verificación (Actividad IA). DISTINTA del título del prompt
# (`_TITULO_VERIFICACION`="Verificar", que sluggea al id `prompt/verificar`): en la vista Pipelines
# la etapa se llama "Verificar", y la actividad debe llamarse igual para no desconcertar.
_ETIQUETA_VERIFICACION = "Verificar la fuente"

# Verificacion SENTINEL que se persiste en el TEMA mientras su verificación de la fuente (claude -p) está en
# curso: la fase verificación NO lo re-lanza (deja de estar "sin verificacion") y la vista Pipelines pinta la
# etapa verificación como "en curso". Al completar, el `procesar` lo sustituye por el verificacion real.
VERIFICACION_EN_CURSO = "en_curso"

# Verificacion SENTINEL que se persiste cuando la etapa verificación está DESACTIVADA para la marca (toggle
# `KENI_PIPELINE_VERIFICAR` off): no se lanza la verificación, pero el tema NO queda bloqueado: `temas_para_redactar` lo acepta
# igual que un `no_verificado`, así el copy se genera sin verificación. La vista Pipelines pinta verificación como
# "saltada". Distinto de "sin verificacion" (que significaría "verificación pendiente, aún por verificar").
VERIFICACION_SALTADA = "saltada"

# Verificacion TERMINAL de FRESCURA: el tema superó el TTL en curso (`KENI_PIPELINE_TEMA_TTL_HORAS`)
# sin completar sus fases y CADUCA: sale del gate serial (libera hueco de admisión), no se verificación
# ni genera copy. El pipeline es ventana deslizante sobre el ranking: lo de ayer no entra hoy.
VERIFICACION_CADUCADA = "caducada"

# Verificaciones ESTRUCTURADAS de la verificación de la FUENTE (rediseño QPC), reexportados del dominio para
# que el sweep, la API y los tests compartan los literales sin acoplarse al módulo de dominio.
VERIFICACION_NO_VERIFICADO = dom_verificar.VERIFICACION_NO_VERIFICADO  # ⚠️ OK para seguir (no verificado a fondo)
VERIFICACION_PROBLEMA = dom_verificar.VERIFICACION_PROBLEMA  # ❗ algo de peso en contra: NO se genera copy

# Criterios por defecto del documento verificación que se CREA si aún no existe (idempotente). MISMO
# cuerpo que la inicial `prompt/verificar` del paquete (último recurso si la inicial no se
# pudiera leer; si tocas uno, toca el otro). REDISEÑO: la verificación es PRE-COPY y verifica la NOTA DE
# ORIGEN (no el copy, que aún no existe). Es PERMISIVA: solo levanta `problema` ante algo de
# PESO (dato falso evidente, problema legal/ético claro); ante la duda, `no_verificado`.
# SEÑALA (no publica ni reescribe). El campo JSON `veredicto` va en slug ASCII
# ("apta"|"problema"); el semáforo 🟢/🔴 queda como línea humana.
_DEFAULT_VERIFICACION_CRITERIOS = """\
Eres el revisor editorial de AMX Contenido. Recibes en el bloque CONTEXTO la NOTA DE ORIGEN
(título + resumen + enlace) de la que se generará copy para redes. Haces una VERIFICACIÓN PREVIA,
ANTES de que se redacte el copy: decides si la fuente es apta para producir contenido. NO
redactas copy ni reescribes nada. Aplica la LÍNEA EDITORIAL adjunta (voz de marca, reglas).

Modo dry-run: no publicas ni haces peticiones de red. SEÑALAS; el equipo decide.

SÉ PERMISIVO: esta verificación es un primer filtro barato, NO una verificación a fondo. Solo levanta
un PROBLEMA cuando hay algo de PESO en contra (un dato claramente falso, un asunto legal o ético
serio, una fuente no fiable o sensacionalista que no debería amplificarse). Ante la duda, DEJA
PASAR: el copy generado llevará un aviso de "no verificado" y un humano lo revisará después.

## Verificacion (ANTES del detalle)

Empieza, arriba del todo, por una sola línea de semáforo:

🟢 (apta, seguir) · 🔴 (problema de peso, NO generar copy)

No uses el amarillo: o es apta (🟢) o tiene un problema de peso (🔴).

## Qué miras (a alto nivel, sin verificar a fondo)

1. Veracidad evidente: ¿la nota afirma algo claramente falso o inventado? No verifiques datos uno
   a uno; solo señala lo que salte a la vista como falso.
2. Legal / ético: ¿hay algo serio (difamación, contenido sensible, desinformación) que desaconseje
   amplificar esta fuente?
3. Fuente: ¿es una fuente fiable o un clickbait/sensacionalismo que no deberíamos amplificar?

## Salida

Tras el semáforo, cierra con un bloque ```json con la forma:
{"veredicto": "apta", "resumen": "una frase",
 "hallazgos": [{"tipo": "dato|legal|voz", "gravedad": "error|aviso",
                "fragmento": "...", "explicacion": "...", "sugerencia": "..."}]}
El campo "veredicto" va SIEMPRE en slug ASCII: "apta" (seguir) o "problema" (de peso, NO
generar copy). El semáforo 🟢/🔴 es solo la línea humana de arriba, NO un valor del JSON.
Usa gravedad "error" SOLO para lo de peso (lo que hace "problema"). Sin emojis en el cuerpo
ni en el JSON.
"""


# --------------------------------------------------------------------------- #
# og:image (best-effort, INYECTABLE)                                           #
# --------------------------------------------------------------------------- #

# Regex tolerante para `<meta property="og:image" content="...">` (en cualquier orden de
# atributos). Solo se usa sobre el HTML de marca PROPIA; un fallo devuelve "" (la placa de
# marca con hueco de foto es aceptable). NUNCA lanza fuera del barrido.
_RE_OG_IMAGE = re.compile(
    r"""<meta[^>]+?(?:property|name)\s*=\s*["']og:image["'][^>]*?>""",
    re.IGNORECASE,
)
_RE_CONTENT = re.compile(r"""content\s*=\s*["']([^"']+)["']""", re.IGNORECASE)

# Tope de bytes que leemos del artículo para buscar la og:image (suele estar en el <head>).
_OG_MAX_BYTES = 512 * 1024
_OG_TIMEOUT_S = 8.0

# User-Agent de los fetches del pipeline (og:image y cuerpo del artículo).
_UA_PIPELINE = "keni-social/pipeline (+https://social.kenitech.io)"
# Máximo de saltos de redirección que seguimos REVALIDANDO cada destino. Un enlace de Google News
# redirige al editor (1-2 saltos); este tope corta cadenas abusivas y bucles de redirección.
_MAX_REDIRECTS = 5


def _fetch_html_validado(enlace: str, *, timeout: float, max_bytes: int) -> str:
    """Descarga el HTML de `enlace` con GUARD SSRF en CADA salto. "" si falla / no permitido. NUNCA lanza.

    ANTI-SSRF: la ingesta resuelve URLs de ARTÍCULOS de TERCEROS (las trae el feed RSS, no
    confiable). Antes de pedir cada URL la validamos con `http_feed.validar_url` (esquema
    http/https + rechazo de IPs privadas/loopback/link-local/multicast/reservadas, incl. la
    metadata 169.254.169.254). Como un editor legítimo puede REDIRIGIR (Google News → medio),
    seguimos los redirects MANUALMENTE revalidando cada destino —en vez de delegar en el
    `follow_redirects` de httpx, que NO revalida y abriría SSRF por redirección a una IP interna—.
    Lee sólo el principio del documento (`max_bytes`). Es la base común de la og:image y del cuerpo.
    """
    if not isinstance(enlace, str) or not enlace.strip():
        return ""
    try:
        import httpx
    except ImportError:  # pragma: no cover -- httpx es dependencia
        return ""
    cabeceras = {"User-Agent": _UA_PIPELINE}
    url = enlace.strip()
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False, headers=cabeceras) as cliente:
            for _ in range(_MAX_REDIRECTS + 1):
                limpia, error = http_feed.validar_url(url)
                if error is not None:
                    _log.debug("pipeline: fetch bloqueado por guard SSRF (%s): %s", url[:120], error)
                    return ""
                with cliente.stream("GET", limpia) as respuesta:
                    if respuesta.is_redirect:
                        destino = respuesta.headers.get("location") or ""
                        if not destino:
                            return ""
                        # Resuelve un Location relativo contra la URL actual y revalida en la
                        # siguiente iteración (el guard SSRF se aplica también al destino del redirect).
                        url = str(respuesta.url.join(destino))
                        continue
                    respuesta.raise_for_status()
                    trozos: list[bytes] = []
                    total = 0
                    for trozo in respuesta.iter_bytes():
                        trozos.append(trozo)
                        total += len(trozo)
                        if total >= max_bytes:
                            break
                    return b"".join(trozos).decode("utf-8", errors="replace")
            _log.debug("pipeline: demasiadas redirecciones al traer %s", enlace[:120])
            return ""
    except Exception:  # noqa: BLE001 -- el fetch es un extra; nunca rompe el barrido
        return ""


def _fetch_og_image_real(enlace: str) -> str:
    """Resuelve la `og:image` de un artículo. "" si falla / no hay. NUNCA lanza.

    Best-effort: GET con redirects VALIDADOS contra SSRF (`_fetch_html_validado`), timeout corto,
    lee solo el principio del HTML y parsea la meta og:image con regex. Es el punto INYECTABLE:
    los tests lo parchean para no tocar la red (`monkeypatch.setattr`).
    """
    html = _fetch_html_validado(enlace, timeout=_OG_TIMEOUT_S, max_bytes=_OG_MAX_BYTES)
    return _extraer_og_image(html)


def _extraer_og_image(html: str) -> str:
    """Extrae la URL `og:image` del HTML (PURA, testeable). "" si no la encuentra."""
    if not html:
        return ""
    for meta in _RE_OG_IMAGE.finditer(html):
        m = _RE_CONTENT.search(meta.group(0))
        if m:
            url = (m.group(1) or "").strip()
            if url.startswith(("http://", "https://")):
                return url
    return ""


# Seam inyectable (los tests lo parchean): NO se llama a la red en tests.
_FETCH_OG_IMAGE = _fetch_og_image_real


# --------------------------------------------------------------------------- #
# Cuerpo del ARTÍCULO + limpieza del snippet RSS (enriquecer la nota de origen) #
# --------------------------------------------------------------------------- #
# Gateado por `config.pipeline_fetch_fuente()`: cuando está ON, la ingesta baja el CUERPO del
# artículo (no solo el snippet RSS) para que `claude -p` sintetice sobre material real. El snippet
# RSS además llega sucio (entidades HTML sin decodificar, boilerplate "The post … appeared first on
# …"): `_limpiar_snippet` lo normaliza SIEMPRE (no depende del flag; es barato y puro).

# Tope de bytes que leemos del artículo para extraer el cuerpo. Mayor que el de og:image: el
# cuerpo suele estar más abajo en el documento, no solo en el <head>.
_ART_MAX_BYTES = 1024 * 1024
_ART_TIMEOUT_S = 8.0
# Tope de caracteres del cuerpo extraído que anexamos a la nota (acota el tamaño del prompt; el
# modelo no necesita el artículo entero para sintetizar, basta el grueso de la nota).
_ART_MAX_CHARS = 5000
# Un <p> con menos de esto suele ser cruft (navegación, pies, créditos): se descarta.
_ART_MIN_P_CHARS = 40
# Si el texto extraído no llega a esto, lo tratamos como fallo (página sin cuerpo legible) -> "".
_ART_MIN_TEXTO = 200

_RE_JSONLD = re.compile(
    r"""<script[^>]+type\s*=\s*["']application/ld\+json["'][^>]*>(.*?)</script>""",
    re.IGNORECASE | re.DOTALL,
)
_RE_ARTICLE = re.compile(r"<article\b[^>]*>(.*?)</article>", re.IGNORECASE | re.DOTALL)
_RE_P = re.compile(r"<p\b[^>]*>(.*?)</p>", re.IGNORECASE | re.DOTALL)
# <script>/<style> con su contenido: hay que borrarlos ENTEROS antes de quitar tags sueltos.
_RE_SCRIPT_STYLE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_RE_TAG = re.compile(r"<[^>]+>")
_RE_WS_HORIZ = re.compile(r"[ \t ]+")
_RE_WS_NL = re.compile(r"\n{3,}")
# Boilerplate de WordPress al final del snippet RSS ("The post <título> appeared first on <medio>.").
_RE_WP_BOILER = re.compile(r"\s*The post\b.*?appeared first on\b.*$", re.IGNORECASE | re.DOTALL)
# Marca de truncado del feed: "[…]" (tras decodificar `[&#8230;]`) o "[...]".
_RE_ELIPSIS_CORCHETE = re.compile(r"\s*\[\s*(?:…|\.\.\.)\s*\]\s*")


def _texto_de_html(fragmento: str) -> str:
    """HTML -> texto plano: quita tags, decodifica entidades y normaliza espacios. PURO."""
    sin_tags = _RE_TAG.sub(" ", fragmento)
    return _RE_WS_HORIZ.sub(" ", _html.unescape(sin_tags)).strip()


def _articlebody_de_jsonld(crudo: str) -> str:
    """Busca recursivamente la clave `articleBody` en un bloque JSON-LD. "" si no la halla."""
    import json

    try:
        datos = json.loads(crudo.strip())
    except (json.JSONDecodeError, ValueError):
        return ""

    def _buscar(nodo: Any) -> str:
        if isinstance(nodo, dict):
            cuerpo = nodo.get("articleBody")
            if isinstance(cuerpo, str) and cuerpo.strip():
                return cuerpo.strip()
            for valor in nodo.values():
                hallado = _buscar(valor)
                if hallado:
                    return hallado
        elif isinstance(nodo, list):
            for item in nodo:
                hallado = _buscar(item)
                if hallado:
                    return hallado
        return ""

    return _buscar(datos)


def _extraer_texto_articulo(html_doc: str) -> str:
    """Extrae el CUERPO de un artículo de su HTML. PURA y testeable. "" si no hay cuerpo legible.

    Estrategia, de más fiable a menos: (1) `articleBody` del JSON-LD `NewsArticle`/`Article` (lo
    publican Infobae, UnoTV y la mayoría de medios); (2) los `<p>` dentro de `<article>` si lo
    hay, o del documento entero; tags fuera, entidades decodificadas, espacios normalizados.
    Trunca a `_ART_MAX_CHARS`. Por debajo de `_ART_MIN_TEXTO` se considera que no hubo cuerpo.
    """
    if not html_doc:
        return ""
    # (1) JSON-LD articleBody.
    for bloque in _RE_JSONLD.finditer(html_doc):
        cuerpo = _articlebody_de_jsonld(bloque.group(1))
        if cuerpo:
            texto = _RE_WS_HORIZ.sub(" ", _html.unescape(cuerpo)).strip()
            if len(texto) >= _ART_MIN_TEXTO:
                return texto[:_ART_MAX_CHARS]
    # (2) Párrafos: preferimos los de dentro de <article>; si no hay, los del documento.
    m = _RE_ARTICLE.search(html_doc)
    ambito = m.group(1) if m else html_doc
    ambito = _RE_SCRIPT_STYLE.sub(" ", ambito)
    parrafos: list[str] = []
    for p in _RE_P.finditer(ambito):
        texto_p = _texto_de_html(p.group(1))
        if len(texto_p) >= _ART_MIN_P_CHARS:
            parrafos.append(texto_p)
    cuerpo = _RE_WS_NL.sub("\n\n", "\n\n".join(parrafos)).strip()
    if len(cuerpo) < _ART_MIN_TEXTO:
        return ""
    return cuerpo[:_ART_MAX_CHARS]


def _limpiar_snippet(texto: str) -> str:
    """Normaliza el snippet RSS: decodifica entidades, quita tags y el boilerplate de WordPress.

    PURA. Aplica SIEMPRE (no depende del flag de fetch): el resumen del feed llega con entidades
    sin decodificar (`[&#8230;]`), a veces HTML, y cola de WordPress ("The post … appeared first
    on UnoTV."). Devuelve el resumen limpio listo para la nota. "" -> "".
    """
    if not texto:
        return ""
    limpio = _html.unescape(texto)
    limpio = _RE_TAG.sub(" ", limpio)
    limpio = _RE_WP_BOILER.sub("", limpio)
    limpio = _RE_ELIPSIS_CORCHETE.sub(" ", limpio)
    return _RE_WS_HORIZ.sub(" ", limpio).strip()


def _fetch_articulo_real(enlace: str) -> str:
    """Descarga y extrae el CUERPO del artículo de `enlace`. "" si falla / no hay. NUNCA lanza.

    Best-effort, mismo patrón que `_fetch_og_image_real` (GET con redirects VALIDADOS contra SSRF,
    timeout corto, tope de bytes), pero leyendo más cuerpo y extrayendo texto con
    `_extraer_texto_articulo`. Es el punto INYECTABLE: los tests lo parchean (`_FETCH_ARTICULO`).
    """
    html_doc = _fetch_html_validado(enlace, timeout=_ART_TIMEOUT_S, max_bytes=_ART_MAX_BYTES)
    return _extraer_texto_articulo(html_doc)


# Seam inyectable (los tests lo parchean): NO se llama a la red en tests.
_FETCH_ARTICULO = _fetch_articulo_real


# --------------------------------------------------------------------------- #
# Actividad (etapas CI/CD/verificación como generaciones-marcador)                       #
# --------------------------------------------------------------------------- #


def registrar_etapa(
    etapa: str, marca: str, detalle: str, publicacion_id: str = "", gen_id: str = ""
) -> dict[str, Any] | None:
    """Sella una entrada de ACTIVIDAD de una etapa del pipeline (CI/CD/verificación). Best-effort.

    Crea una generación-marcador `completado` (sin `claude`): `tipo='pipeline'` y la etapa +
    detalle en la `etiqueta` ("ADMITIR · Recolectar...", etc.). La vista "Actividad IA" la muestra
    junto al resto de la actividad de IA. Un fallo al sellar NUNCA aborta el barrido (devuelve
    None y se loguea): la actividad es trazabilidad, no parte crítica del flujo.

    `publicacion_id` (opcional, def "") CORRELACIONA la etapa con la RUN (el `contenido` padre
    del pipeline) para la vista Pipelines (`/api/pipelines/{id}`). CD/verificación lo pasan (la etapa va
    sobre un tema concreto); CI es brand-level y lo deja vacío. Es ADITIVO: vacío no engorda el
    registro (lo filtra `generaciones._cuerpo`) y los registros previos lo traen como "".

    `gen_id` (opcional, def "") apunta a la GENERACIÓN REAL de `claude -p` que ejecutó esa
    etapa (CD = copy, verificación = revisión editorial). La vista Pipelines lo resuelve para mostrar el
    STREAM del agente (su proceso de pensamiento). CI no lanza `claude`, así que lo deja vacío.
    """
    etiqueta = f"{etapa} · {detalle}".strip()
    # Frontera ADR 0011: Admitir (CI) y Verificar (verificación) son INVESTIGACION; Redactar (CD) e Ilustrar son
    # PRODUCCION. Se sella en el marcador para clasificarlo sin reparsear la etiqueta.
    proceso = (
        generaciones.PROCESO_INVESTIGACION
        if etapa in (ETAPA_ADMITIR, ETAPA_VERIFICAR)
        else generaciones.PROCESO_PRODUCCION
    )
    try:
        gen = generaciones.crear({
            "tipo": TIPO_ACTIVIDAD,
            "marca": marca or "",
            "proceso": proceso,
            "publicacion_id": publicacion_id or "",
            "gen_id": gen_id or "",
            "etiqueta": etiqueta[:200],
            "estado": generaciones.ESTADO_COMPLETADO,
            "fecha_fin": generaciones.ahora_iso(),
        })
        return gen
    except Exception:  # noqa: BLE001 -- la traza de actividad no debe romper el pipeline
        _log.warning("pipeline: no se pudo registrar la etapa %s (%s)", etapa, marca, exc_info=True)
        return None


# Estados del ADMISION de verificacion (clusters `nuevo` ya en el circuito de Verificar y aun sin
# admitir): en proceso + verificados-pendientes + saltados. Acotan cuanta verificación se lanza por tick (el mismo
# `_ADMISION_VERIFICACION` que usa `_barrido`); aqui se exponen para que el Monitor lea el admision sin
# importar el barrido (el orquestador) desde la capa API.
ADMISION_VERIFICACION_ESTADOS = (VERIFICACION_EN_CURSO, VERIFICACION_NO_VERIFICADO, VERIFICACION_SALTADA)

# Verificaciones que ADMITEN a producción (ADR 0011 F3): la historia pasó la verificación (`no_verificado`)
# o la verificación estaba saltada para la marca. FUENTE ÚNICA del filtro OBLIGATORIO de la admisión: la
# usa `promover_clusters_marca`/`clusters_para_promover` por defecto (no existe ya un camino que
# promueva SIN verificar) y el barrido de investigación.
VERIFICADAS_OK = (VERIFICACION_NO_VERIFICADO, VERIFICACION_SALTADA)


def admision_verificacion() -> dict[str, Any]:
    """Estado del ADMISION de Verificar (lo unico que Investigacion acota aparte de la cola compartida).

    Por cada marca con Recolectar activa, cuenta sus clusters en el admision y lo compara
    con el tope EN PROCESO por marca (`pipeline_en_proceso_max`). Devuelve el total y el desglose por
    marca, para que el Monitor muestre "cuanto se esta verificando" sin tocar la cola de jobs.
    Best-effort: una marca cuyo conteo falle se omite (no tumba el snapshot).
    """
    tope = config.pipeline_en_proceso_max()
    por_marca: list[dict[str, Any]] = []
    total = 0
    for marca in marcas.ids():
        if not config.etapa_activa(config.ENV_PIPELINE_RECOLECTAR, marca):
            continue
        try:
            n = repos.contar_clusters_admision_verificacion(marca, ADMISION_VERIFICACION_ESTADOS)
        except Exception:  # noqa: BLE001 -- un conteo que falle no debe tumbar el Monitor
            continue
        total += n
        por_marca.append({"marca": marca, "en_proceso": n, "tope": tope})
    return {"en_proceso": total, "tope_por_marca": tope, "marcas": por_marca}


def _autor_pipeline() -> dict[str, str] | None:
    """Autor (brand-agnóstico) al que se atribuyen los lanzamientos del pipeline.

    Usa el usuario configurado del MCP (`config.mcp_usuario()`) si existe y resuelve a un
    usuario real; si no, el primer admin. None si no hay usuarios (best-effort: la generación
    seguirá funcionando con autor anónimo).
    """
    try:
        from .. import auth

        usuarios = auth.listar_usuarios()
    except Exception:  # noqa: BLE001 -- sin usuarios legibles, autor anónimo (no rompe)
        return None
    if not usuarios:
        return None
    preferido = (config.mcp_usuario() or "").strip().lower()

    def _u(u: dict[str, Any]) -> dict[str, str]:
        return {"id": str(u.get("id", "") or ""), "usuario": str(u.get("usuario", "") or "")}

    if preferido:
        for u in usuarios:
            if str(u.get("usuario", "") or "").strip().lower() == preferido:
                return _u(u)
    for u in usuarios:
        if (u.get("rol") or "") == "admin":
            return _u(u)
    return _u(usuarios[0])


# --------------------------------------------------------------------------- #
# Lecturas de temas compartidas entre etapas (verificación y CD)                         #
# --------------------------------------------------------------------------- #


def _copy_pendiente_leido(tema: dict[str, Any]) -> dict[str, Any]:
    """Lee y parsea `copy_pendiente` (JSON) de un tema. {} si vacío o ilegible (best-effort)."""
    import json

    crudo = (tema.get("copy_pendiente") or "").strip()
    if not crudo:
        return {}
    try:
        datos = json.loads(crudo)
    except (json.JSONDecodeError, ValueError):
        return {}
    return datos if isinstance(datos, dict) else {}


# REINTENTOS ACOTADOS por etapa (flujo continuo): con el tick corto, una etapa que falla se
# relanzaría cada pocos segundos para siempre (bucle de tokens). Cada lanzamiento de verificación/Copy
# anota su intento en `copy_pendiente` (JSON, sin migración de esquema); al agotarlos, el tema
# se marca `problema` con un hallazgo de sistema: SALE del cupo en curso (in=out se sostiene)
# y queda visible en Pipelines/tablero como fallo, para que un humano decida.
_MAX_INTENTOS_ETAPA = 3

# BACKOFF creciente entre reintentos (espera tras el intento 1/2/3): con el tick de ~15 s, un
# fallo transitorio (proveedor caído, timeout) consumía los 3 intentos en <1 min; esperar 1/4/16
# min da tiempo a que pase, SIN dormir el barrido (el tema solo se SALTA en el tick).
_BACKOFF_ETAPA_SEG = (60.0, 240.0, 960.0)


def intentos_de(tema: dict[str, Any], campo: str) -> int:
    """Intentos ya consumidos de una etapa (`campo` = 'verificar_intentos'/'redactar_intentos'). 0 si no hay."""
    try:
        return int(_copy_pendiente_leido(tema).get(campo) or 0)
    except (TypeError, ValueError):
        return 0


def anotar_intento(tema: dict[str, Any], campo: str) -> None:
    """Suma 1 al contador de intentos de la etapa en `copy_pendiente` (best-effort, persiste).

    Anota además el INSTANTE del intento (`campo + "_ts"`, ISO UTC): es la base del backoff
    creciente entre reintentos (`en_backoff`). RE-LEE el tema de BD antes de escribir: con el
    lanzador SÍNCRONO de los tests, el `procesar` del copy puede haber LIMPIADO `copy_pendiente`
    (éxito) durante el propio lanzamiento; anotar sobre el dict viejo lo resucitaría. Si ya no
    hay pendiente, no hay nada que contar.
    """
    import json

    from ..tiempo import ahora_iso

    tema_id = (tema.get("id") or "").strip()
    if not tema_id:
        return
    try:
        fresco = repos.obtener_publicacion(tema_id)
    except Exception:  # noqa: BLE001 -- sin lectura no anotamos (el tope simplemente no avanza)
        return
    if fresco is None or not (fresco.get("copy_pendiente") or "").strip():
        return  # éxito ya limpió el pendiente (o el tema desapareció): nada que anotar
    pend = _copy_pendiente_leido(fresco)
    pend[campo] = int(pend.get(campo) or 0) + 1
    pend[f"{campo}_ts"] = ahora_iso()
    try:
        repos.actualizar_publicacion(tema_id, {"copy_pendiente": json.dumps(pend, ensure_ascii=False)})
    except Exception:  # noqa: BLE001 -- sin contador, el tope no aplica; el reintento sigue
        _log.warning("pipeline: no se pudo anotar el intento %s del tema %s", campo, tema_id, exc_info=True)


def en_backoff(tema: dict[str, Any], campo: str) -> bool:
    """True si el tema debe ESPERAR antes de reintentar la etapa (backoff creciente).

    Lee intentos + timestamp del último intento de `copy_pendiente` (`campo` y `campo + "_ts"`,
    los anota `anotar_intento`) y aplica `_BACKOFF_ETAPA_SEG`. Sin intentos o sin timestamp
    (temas previos al backoff) no hay espera. El barrido SALTA el tema (no duerme): un tick
    posterior lo reevalúa. Comparación lexicográfica: ambos son ISO UTC canónicos.
    """
    from datetime import UTC, datetime, timedelta

    from ..tiempo import iso_utc

    intentos = intentos_de(tema, campo)
    if intentos <= 0:
        return False
    ts = str(_copy_pendiente_leido(tema).get(f"{campo}_ts") or "").strip()
    if not ts:
        return False
    espera = _BACKOFF_ETAPA_SEG[min(intentos, len(_BACKOFF_ETAPA_SEG)) - 1]
    umbral = iso_utc(datetime.now(UTC) - timedelta(seconds=espera))
    return ts > umbral  # último intento más reciente que el umbral: aún en espera


def marcar_fallo_etapa(tema_id: str, etapa: str, motivo: str) -> None:
    """Marca el tema con verificacion `problema` por fallo REPETIDO de una etapa (salida terminal).

    El tema sale del cupo en curso (deja de reintentarse y de bloquear la admisión de su marca)
    y el fallo queda visible (❗) con un hallazgo de sistema. Mismo formato que la verificación verificación.
    """
    import json

    hallazgos = [{
        "tipo": "sistema", "gravedad": "error", "fragmento": etapa,
        "explicacion": motivo, "sugerencia": "Revisa la generación o relanza a mano.",
    }]
    try:
        repos.actualizar_publicacion(tema_id, {
            "verificacion_fuente": VERIFICACION_PROBLEMA,
            "verificar_hallazgos": json.dumps(hallazgos, ensure_ascii=False),
        })
        _log.warning("pipeline: tema %s marcado problema por fallo repetido de %s", tema_id, etapa)
    except Exception:  # noqa: BLE001 -- best-effort; el tema seguirá reintentando si no persiste
        _log.warning("pipeline: no se pudo marcar el fallo terminal del tema %s", tema_id, exc_info=True)


def _tiene_copy(tema_id: str) -> bool:
    """True si el tema ya tiene copy REDACTADO en al menos una pieza. Best-effort.

    Mira el copy real (`falta_copy=0`, mismo canon que `estado_pieza_por_publicacion`), NO la
    mera existencia de filas: las altas que pre-crean piezas vacías (botón Crear post / `aportar`,
    Radar) nacen con piezas SIN copy y deben seguir siendo redactables hasta que el copy aterrice.
    """
    if not tema_id:
        return False
    try:
        piezas = repos.listar_piezas_fila(tema_id)
    except Exception:  # noqa: BLE001 -- sin lectura, conservador: asumimos que NO para reintentar
        return False
    return any(not p.get("falta_copy") or (p.get("copy") or "").strip() for p in piezas)


def temas_pipeline(marca: str | None = None) -> list[dict[str, Any]]:
    """TODOS los temas del pipeline (origen `pipeline`), en orden FIFO. [] si la lectura falla.

    NO recorta: el volumen lo acota la ADMISIÓN (gate serial en curso por marca), así que aquí
    solo puede haber, como mucho, lo admitido. `listar_publicacion` ya ordena por prioridad y
    `fecha_objetivo/creado ASC`, así que el más antiguo PENDIENTE se atiende primero (justo).
    """
    try:
        items = repos.listar_publicacion(marca=marca)
    except Exception:  # noqa: BLE001 -- sin temas legibles, el barrido no hace nada
        return []
    return [it for it in items if (it.get("origen") or "") == ORIGEN_PIPELINE]
