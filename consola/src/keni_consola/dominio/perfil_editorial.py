"""Perfil editorial por marca: keywords/temas DERIVADOS de la línea editorial (libtexto) con Haiku.

Reemplaza el vocabulario hardcodeado de `relevancia_marca` por un perfil extraído de la ESTRATEGIA
de la página *texto*: un agente Haiku lee los docs editoriales de la marca (`libtexto.editoriales_
de_marca`) y devuelve sus temas/keywords; se cachea en disco (dir de texto) y se refresca cuando
cambia la editorial (hash) o caduca (TTL). El ranking usa `palabras(marca)` (match léxico, SIN
coste por-cluster: el Haiku solo corre en el refresco, acotado por marca y TTL).

GATEADO por `KENI_RANKING_PERFIL_IA` (def OFF): la decisión de usarlo/refrescarlo la toma el daemon
de ingesta; este módulo es neutro (lee/escribe el cache y, si se le pide, llama a Haiku).

Patrón de Haiku SÍNCRONO POR LOTES idéntico a `dominio.traduccion` (ejecutor inyectable en tests).
BEST-EFFORT: ante cualquier fallo (sin claude, JSON inválido, sin editorial) NO toca el cache y
devuelve lo que hubiera (o vacío); el daemon cae entonces al vocabulario semilla.
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

# Ejecutor inyectable (misma firma que `traduccion.Ejecutor`): `(prompt, dir_permitido) -> str`.
Ejecutor = Callable[[str, str], str]

# Nº de keywords/temas que se piden a Haiku (cota del perfil).
_MAX_KEYWORDS = 30
# Recorte del cuerpo editorial que se pasa al prompt (protección de tamaño).
_MAX_CHARS_EDITORIAL = 6000


def _ruta_cache() -> Path | None:
    """Ruta del JSON de perfiles (bajo el dir de texto). None si no se puede resolver."""
    try:
        from .. import libtexto

        return libtexto.raiz() / "perfiles_editoriales.json"
    except Exception:  # noqa: BLE001 -- sin dir de texto no hay cache (se cae a semilla)
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
    except Exception:  # noqa: BLE001 -- el cache es best-effort; un fallo no rompe la ingesta
        _log.warning("perfil_editorial: no se pudo persistir el cache.", exc_info=True)


def _docs_de_marca(marca: str) -> list[Any]:
    """Docs editoriales ESPECÍFICOS de la marca (excluye globales: definen el perfil propio)."""
    try:
        from .. import libtexto

        docs = libtexto.editoriales_de_marca(marca)
    except Exception:  # noqa: BLE001 -- sin libtexto, no hay perfil
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


# La plantilla vive en la Biblioteca de Texto como prompt EDITABLE (pestaña «Prompts»). Se
# insertan la MARCA, el tope de keywords y la línea editorial en sus marcadores. Si el store
# fallara, la red es la SEMILLA del paquete (fuente única, sin texto duplicado aquí).
_PROMPT_ID = "prompt/editorial"


def _plantilla() -> str:
    """Cuerpo EFECTIVO de la plantilla (store del equipo > semilla del paquete)."""
    from .. import libtexto

    try:
        cuerpo = (libtexto.cuerpo_efectivo(_PROMPT_ID) or "").strip()
    except Exception:  # noqa: BLE001 -- nunca dejar el perfil sin prompt por un fallo de lectura
        cuerpo = ""
    return cuerpo or libtexto.cuerpo_semilla(_PROMPT_ID).strip()


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
    from . import similitud  # sin acentos: el clustering compara contra texto de-acentuado

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
    de la llamada. El daemon lo usa para registrar la actividad IA del encaje editorial con el
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
    from .traduccion import _ejecutar_claude_json

    return _ejecutar_claude_json(prompt, dir_permitido)
