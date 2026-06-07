"""Helpers PUROS de similitud de títulos (normalización + fuzzy con sinónimos).

Antes vivían en `keni_consola.radar` (Radar v1, retirado). Se extrajeron aquí porque
los reutiliza el clustering del pool (`dominio.clustering`): cruzar títulos para fundir
"la misma noticia" contada por varias fuentes. Sin red, sin estado, deterministas.
"""

from __future__ import annotations

import re
import unicodedata

_RE_NO_ALNUM = re.compile(r"[^a-z0-9áéíóúñü ]+", re.IGNORECASE)
_RE_ESPACIOS = re.compile(r"\s+")


def normalizar_clave(titulo: str) -> str:
    """Clave de dedup de un título: minúsculas, sin signos, espacios colapsados.

    Conservadora a propósito: solo funde títulos con la MISMA forma normalizada (no hace
    clustering semántico). Así nunca inventa una agrupación que no está en los datos.
    """
    texto = (titulo or "").strip().lower()
    texto = _RE_NO_ALNUM.sub(" ", texto)
    texto = _RE_ESPACIOS.sub(" ", texto).strip()
    return texto


# Diccionario de SINÓNIMOS / variantes de escritura para el fuzzy. Cada grupo se colapsa a
# su forma CANÓNICA (la clave) ANTES de comparar, así "cdmx"/"ciudad de mexico"/"df" o
# "vs"/"versus" no cuentan como diferencia. Conservador: solo entradas inequívocas del
# dominio (deportes/MX); ampliar con cuidado para no fusionar temas que no son el mismo.
_SINONIMOS: dict[str, tuple[str, ...]] = {
    "cdmx": ("ciudad de mexico", "df", "distrito federal"),
    "vs": ("versus", "contra"),
    "futbol": ("football", "soccer"),
    "estados unidos": ("eeuu", "ee uu", "usa", "us"),
    "seleccion mexicana": ("el tri", "tricolor"),
}
# Mapa inverso (variante -> canónica), pre-calculado una vez. Las variantes más LARGAS
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


def sin_acentos(texto: str) -> str:
    """Quita acentos (NFD + descarta diacríticos) para comparar sin depender de tildes."""
    return "".join(c for c in unicodedata.normalize("NFD", texto) if not unicodedata.combining(c))


def clave_fuzzy(titulo: str) -> str:
    """Clave NORMALIZADA para el fuzzy: minúscula, sin acentos, sin signos y con sinónimos.

    Sobre la clave exacta (`normalizar_clave`) aplica: quitar acentos y colapsar los grupos
    de `_SINONIMOS` a su forma canónica. Así "Selección Mexicana" y "el Tri" comparten base.
    Determinista y pura.
    """
    base = sin_acentos(normalizar_clave(titulo))
    for variante, canonica in _VARIANTE_A_CANONICA:
        base = re.sub(rf"\b{re.escape(variante)}\b", canonica, base)
    return _RE_ESPACIOS.sub(" ", base).strip()
