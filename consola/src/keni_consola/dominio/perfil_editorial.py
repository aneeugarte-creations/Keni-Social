"""Perfil editorial por marca: keywords/temas DERIVADOS de la línea editorial (libprompts) con Haiku.

Un agente Haiku lee los docs editoriales de la marca (`libprompts.editoriales_de_marca`)
y devuelve sus temas/keywords; se cachea en disco (dir de texto) y se refresca cuando
cambia la editorial (hash) o caduca (TTL). La priorización usa `palabras(marca)` (match léxico, SIN
coste por-cluster: el Haiku solo corre en el refresco, acotado por marca y TTL).

GATEADO por `KENI_PRIORIZAR_PERFIL_IA` (def OFF): la decisión de usarlo/refrescarlo la toma el daemon
de Recolección; este módulo es neutro (lee/escribe el cache y, si se le pide, llama a Haiku).

El refresco corre como JOB del worker (no inline en el barrido): el paso de Recolección decide si
HACE FALTA (`necesita_refresco`), evita re-encolar uno EN VUELO (`refresco_en_curso` +
`marcar_refresco_encolado`/`limpiar_refresco_encolado`, marcador con TTL en el propio cache) y ENCOLA
un job `claude` por marca; el worker corre el Haiku y su post-procesado (`construir_procesar_perfil`)
ESCRIBE el cache. El cache vive bajo `/data` (volumen compartido), así que el worker puede escribirlo.

Patrón de Haiku SÍNCRONO POR LOTES idéntico a `dominio.traducir` (ejecutor inyectable en tests).
BEST-EFFORT: ante cualquier fallo (sin claude, JSON inválido, sin editorial) NO toca el cache y
devuelve lo que hubiera (o vacío); el daemon cae entonces al vocabulario inicial.
"""

from __future__ import annotations

import hashlib
import json
import logging
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import json_llm

_log = logging.getLogger("keni_consola.dominio.perfil_editorial")

# Ejecutor inyectable (misma firma que `traducir.Ejecutor`): `(prompt, dir_permitido) -> str`.
Ejecutor = Callable[[str, str], str]

# Nº de keywords/temas que se piden a Haiku (cota del perfil).
_MAX_KEYWORDS = 30
# Recorte del cuerpo editorial que se pasa al prompt (protección de tamaño).
_MAX_CHARS_EDITORIAL = 6000


def _ruta_cache() -> Path | None:
    """Ruta del JSON de perfiles (bajo el dir de texto). None si no se puede resolver."""
    try:
        from .. import libprompts

        return libprompts.raiz() / "perfiles_editoriales.json"
    except Exception:  # noqa: BLE001 -- sin dir de texto no hay cache (se cae a inicial)
        return None


def _cargar() -> dict[str, Any]:
    ruta = _ruta_cache()
    if ruta is None or not ruta.exists():
        return {}
    try:
        return json.loads(ruta.read_text(encoding="utf-8")) or {}
    except (OSError, json.JSONDecodeError, ValueError):
        return {}


def _guardar(data: dict[str, Any]) -> None:
    ruta = _ruta_cache()
    if ruta is None:
        return
    try:
        from ..io_atomico import escribir_atomico

        ruta.parent.mkdir(parents=True, exist_ok=True)
        escribir_atomico(ruta, json.dumps(data, ensure_ascii=False, indent=2))
    except Exception:  # noqa: BLE001 -- el cache es best-effort; un fallo no rompe la Recolección
        _log.warning("perfil_editorial: no se pudo persistir el cache.", exc_info=True)


def _docs_de_marca(marca: str) -> list[Any]:
    """Docs editoriales ESPECÍFICOS de la marca (excluye globales: definen el perfil propio)."""
    try:
        from .. import libprompts

        docs = libprompts.editoriales_de_marca(marca, pipeline="priorizar")
    except Exception:  # noqa: BLE001 -- sin libprompts, no hay perfil
        return []
    propios = [d for d in docs if marca in getattr(d, "marcas", []) or marca in (getattr(d, "carpeta", "") or "").split("/")]
    return propios or docs


def _texto_editorial(marca: str) -> str:
    """Concatena título+cuerpo de los docs editoriales de la marca (recortado)."""
    partes: list[str] = []
    for d in _docs_de_marca(marca):
        titulo = (getattr(d, "titulo", "") or "").strip()
        cuerpo = (getattr(d, "cuerpo", "") or "").strip()
        if cuerpo:
            partes.append(f"## {titulo}\n{cuerpo}")
    return "\n\n".join(partes)[:_MAX_CHARS_EDITORIAL]


def _hash(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16]


_PROMPT_ID = "prompt/priorizar"


def _plantilla() -> str:
    """Cuerpo EFECTIVO de la plantilla (store del equipo > inicial del paquete)."""
    from .. import libprompts

    try:
        cuerpo = (libprompts.cuerpo_efectivo(_PROMPT_ID) or "").strip()
    except Exception:  # noqa: BLE001 -- nunca dejar el perfil sin prompt por un fallo de lectura
        cuerpo = ""
    return cuerpo or libprompts.cuerpo_inicial(_PROMPT_ID).strip()


def _construir_prompt(marca: str, texto_editorial: str) -> str:
    """Prompt para que Haiku extraiga el perfil de temas/keywords de la marca (plantilla editable).

    Inserta MARCA (puede aparecer varias veces), el tope de keywords y la línea editorial; si el
    equipo quitó el marcador de la línea editorial, la adjunta al final para no perderla.
    """
    plantilla = (
        _plantilla()
        .replace("{{MARCA}}", marca)
        .replace("{{MAX_KEYWORDS}}", str(_MAX_KEYWORDS))
    )
    if "{{EDITORIAL}}" in plantilla:
        return plantilla.replace("{{EDITORIAL}}", texto_editorial)
    return f"{plantilla}\n\nLínea editorial de «{marca}»:\n{texto_editorial}"


def _extraer_keywords(texto: str) -> list[str]:
    """Extrae la lista de keywords del texto de Haiku (extractor compartido). [] si falla."""
    bruto = json_llm.extraer_lista(texto, claves=("keywords",))
    if bruto is None:
        return []
    from . import similitud  # sin acentos: la Agrupación compara contra texto de-acentuado

    fuera: list[str] = []
    for k in bruto:
        norm = " ".join(similitud.sin_acentos(str(k or "").strip().lower()).split())
        if norm and norm not in fuera:
            fuera.append(norm)
    return fuera[:_MAX_KEYWORDS]


def palabras(marca: str | None) -> frozenset[str]:
    """Keywords cacheadas del perfil editorial de `marca` (vacío si no hay cache para ella)."""
    if not marca:
        return frozenset()
    entrada = _cargar().get(marca)
    if not isinstance(entrada, dict):
        return frozenset()
    kws = entrada.get("keywords")
    return frozenset(kws) if isinstance(kws, list) else frozenset()


# --------------------------------------------------------------------------- #
# Camino ENCOLADO (job del worker)                                              #
# --------------------------------------------------------------------------- #

# Clave del marcador "refresco en curso" DENTRO de la entrada de la marca en el cache. Mismo papel
# que la columna `traduccion_encolada` de los clusters: idempotencia entre encolar y completar (no
# re-encolar una marca con job en vuelo), con reapertura por TTL si el job se interrumpe.
_CLAVE_ENCOLADO = "refresco_encolado_en"


def necesita_refresco(
    marca: str, *, ttl_horas: int, ahora: datetime | None = None
) -> bool:
    """True si el perfil de `marca` HACE FALTA refrescarlo (cache ausente/caducado/editorial cambiada).

    Predicado PURO (lee cache + editorial, NO llama a Haiku): el mismo gate hash+TTL que aplicaba
    `refrescar_si_corresponde` antes de llamar al modelo, extraído para que el barrido decida si
    ENCOLAR el job. False si la marca no tiene editorial (no hay nada que refrescar).
    """
    texto = _texto_editorial(marca)
    if not texto:
        return False
    h = _hash(texto)
    ref = ahora or datetime.now(UTC)
    entrada = _cargar().get(marca)
    if not isinstance(entrada, dict) or entrada.get("hash") != h:
        return True  # sin cache o editorial cambiada (hash distinto)
    gen = entrada.get("generado_en") or ""
    try:
        edad_h = (ref - datetime.fromisoformat(gen)).total_seconds() / 3600.0
    except (ValueError, TypeError):
        edad_h = float("inf")
    return edad_h >= max(1, ttl_horas)  # caducó por TTL


def marcar_refresco_encolado(marca: str, *, ahora: datetime | None = None) -> None:
    """Marca el refresco del perfil de `marca` como EN CURSO (timestamp) AL ENCOLAR su job.

    Sella `refresco_encolado_en = ahora` en la entrada de la marca (la crea si no existe). Idempotencia
    entre barridos: mientras el marcador siga fresco (`refresco_en_curso`), el barrido NO re-encola.
    No toca `keywords`/`hash`/`generado_en` (las lecturas `palabras` siguen viendo el perfil previo).
    """
    if not marca:
        return
    ref = ahora or datetime.now(UTC)
    cache = _cargar()
    entrada = cache.get(marca)
    if not isinstance(entrada, dict):
        entrada = {}
    entrada[_CLAVE_ENCOLADO] = ref.isoformat()
    cache[marca] = entrada
    _guardar(cache)


def refresco_en_curso(
    marca: str, *, ahora: datetime | None = None, ttl_min: int
) -> bool:
    """True si hay un refresco EN VUELO para `marca` (marcador dentro del TTL).

    Un marcador más viejo que `ttl_min` se considera ATASCADO (job interrumpido por deploy/OOM/error)
    y NO bloquea: el barrido re-encola (reapertura por TTL, igual que `reparar_traduccion_encolada_
    atascada`). Un marcador corrupto/ilegible tampoco bloquea (se re-encola).
    """
    if not marca:
        return False
    entrada = _cargar().get(marca)
    if not isinstance(entrada, dict):
        return False
    sello = entrada.get(_CLAVE_ENCOLADO) or ""
    if not sello:
        return False
    ref = ahora or datetime.now(UTC)
    try:
        edad_min = (ref - datetime.fromisoformat(sello)).total_seconds() / 60.0
    except (ValueError, TypeError):
        return False
    return edad_min < max(1, ttl_min)


def limpiar_refresco_encolado(marca: str) -> None:
    """Quita el marcador de refresco en curso de `marca` (encolado rechazado por admisión/abortado).

    La usa el barrido cuando el encolado NO llegó a ocurrir (presupuesto/pausa), para que la marca
    vuelva a ser candidata en el próximo barrido sin esperar al TTL. No toca el perfil cacheado.
    """
    if not marca:
        return
    cache = _cargar()
    entrada = cache.get(marca)
    if isinstance(entrada, dict) and _CLAVE_ENCOLADO in entrada:
        del entrada[_CLAVE_ENCOLADO]
        cache[marca] = entrada
        _guardar(cache)


def construir_prompt_perfil(marca: str) -> str:
    """Prompt de extracción de perfil para Haiku, o "" si la marca no tiene editorial. PURO.

    Lo usa el paso de Recolección para componer el prompt del JOB que ENCOLA por marca (el worker lo
    corre con `claude -p`); mismo cuerpo (plantilla + línea editorial) que el camino inline.
    """
    texto = _texto_editorial(marca)
    if not texto:
        return ""
    return _construir_prompt(marca, texto)


def construir_procesar_perfil(marca: str):  # noqa: ANN201 -- generaciones.Procesar (evita ciclo de tipos)
    """Callback de post-procesado del JOB de perfil editorial: parsea la salida y ESCRIBE el cache.

    El worker corre `claude -p` (Haiku) con el prompt de `construir_prompt_perfil`; aquí parseamos las
    keywords con el extractor tolerante (`_extraer_keywords`), recomputamos el hash de la editorial
    VIGENTE de la marca y, si hay keywords usables, ESCRIBIMOS la entrada del cache
    (`keywords`/`hash`/`generado_en`) — lo que además limpia el marcador de refresco en curso (la
    entrada se reemplaza entera). Si la salida no trae keywords usables, NO toca el cache: el marcador
    queda hasta que caduca por TTL y un barrido posterior re-encola (reintento). Devuelve `{keywords}`.
    """
    def procesar(salida: str, _metricas: object) -> dict[str, object]:
        kws = _extraer_keywords(salida or "")
        if not kws:
            _log.warning("perfil_editorial(%s): el job no devolvió keywords usables.", marca)
            return {"keywords": 0, "marca": marca}
        texto = _texto_editorial(marca)
        cache = _cargar()
        cache[marca] = {
            "keywords": kws,
            "hash": _hash(texto) if texto else "",
            "generado_en": datetime.now(UTC).isoformat(),
        }
        _guardar(cache)
        _log.info("perfil_editorial(%s): perfil refrescado vía job (%d keywords).", marca, len(kws))
        return {"keywords": len(kws), "marca": marca}

    return procesar


def refrescar_si_corresponde(
    marca: str,
    *,
    ttl_horas: int,
    ahora: datetime | None = None,
    ejecutor: Ejecutor | None = None,
    al_refrescar: Callable[[str, list[str], str, str], None] | None = None,
) -> frozenset[str]:
    """Refresca el perfil de `marca` si el cache falta, caducó (TTL) o cambió la editorial (hash).

    Si el cache está fresco (mismo hash y dentro del TTL) NO llama a Haiku. Si la marca no tiene
    editorial, no hace nada. Best-effort: ante fallo conserva el cache previo. Devuelve las
    keywords vigentes tras el (posible) refresco.

    `al_refrescar(marca, keywords, prompt, salida)`: callback OPCIONAL que se invoca SOLO cuando
    Haiku refrescó de verdad el perfil (no en aciertos de cache), con el PROMPT y la SALIDA reales
    de la llamada. El daemon lo usa para registrar la actividad IA de Priorizar con el
    Haiku real; un fallo del callback no rompe el refresco (es observabilidad).
    """
    texto = _texto_editorial(marca)
    if not texto:
        return palabras(marca)
    h = _hash(texto)
    ref = ahora or datetime.now(UTC)
    cache = _cargar()
    entrada = cache.get(marca) if isinstance(cache.get(marca), dict) else None
    if entrada and entrada.get("hash") == h:
        gen = entrada.get("generado_en") or ""
        try:
            edad_h = (ref - datetime.fromisoformat(gen)).total_seconds() / 3600.0
        except (ValueError, TypeError):
            edad_h = float("inf")
        if edad_h < max(1, ttl_horas):
            return frozenset(entrada.get("keywords") or [])  # fresco: sin Haiku

    correr = ejecutor or _ejecutar_haiku
    prompt = _construir_prompt(marca, texto)
    try:
        with tempfile.TemporaryDirectory(prefix="keni-perfil-") as carpeta:
            salida = correr(prompt, carpeta)
    except Exception as e:  # noqa: BLE001 -- best-effort: conserva el cache previo
        _log.warning("perfil_editorial(%s): falló la llamada a Haiku: %s", marca, e)
        return palabras(marca)

    kws = _extraer_keywords(salida)
    if not kws:
        _log.warning("perfil_editorial(%s): Haiku no devolvió keywords usables.", marca)
        return palabras(marca)

    cache[marca] = {"keywords": kws, "hash": h, "generado_en": ref.isoformat()}
    _guardar(cache)
    _log.info("perfil_editorial(%s): perfil refrescado (%d keywords).", marca, len(kws))
    if al_refrescar is not None:
        try:
            al_refrescar(marca, kws, prompt, salida)
        except Exception:  # noqa: BLE001 -- el callback (registrar actividad) es best-effort
            _log.warning("perfil_editorial(%s): fallo en al_refrescar.", marca, exc_info=True)
    return frozenset(kws)


def _ejecutar_haiku(prompt: str, dir_permitido: str) -> str:
    """Ejecutor real: reutiliza el runner síncrono de `traduccion` (claude -p --output-format json)."""
    from .traducir import _ejecutar_claude_json

    return _ejecutar_claude_json(prompt, dir_permitido)
