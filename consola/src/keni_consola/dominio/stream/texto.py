"""Utilidades de TEXTO del dominio STREAM: emojis, titulo, normalizacion de redes.

Helpers de texto PUROS extraidos del parseo del stream: la limpieza determinista de emojis
del copy, la derivacion del titulo legible y la normalizacion/orden de las redes pedidas.
Sin I/O y sin dependencias de las otras areas del paquete.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from ...tiempo import hoy_utc

# --------------------------------------------------------------------------- #
# Limpieza de emojis del copy generado por IA (determinista)                   #
# --------------------------------------------------------------------------- #

# Rangos unicode de emojis/simbolos pictograficos que quitamos del copy. Cubre:
#   - Emoticonos (U+1F600-U+1F64F)
#   - Misc Symbols and Pictographs (U+1F300-U+1F5FF)
#   - Transporte y mapas (U+1F680-U+1F6FF)
#   - Symbols and Pictographs Extended-A (U+1FA70-U+1FAFF)
#   - Supplemental Symbols and Pictographs (U+1F900-U+1F9FF)
#   - Banderas / Regional Indicators (U+1F1E6-U+1F1FF)
#   - Misc Symbols (U+2600-U+26FF) y Dingbats (U+2700-U+27BF) -> incluye ✅⚠❌
#   - Variation Selector U+FE0F y ZWJ U+200D (unen secuencias tipo familia/banderas)
# NOTA: NO toca acentos (latin) ni los caracteres de las URLs (ASCII), porque esos
# puntos de codigo caen fuera de estos rangos.
_RE_EMOJI = re.compile(
    "["
    "\U0001f600-\U0001f64f"  # emoticonos
    "\U0001f300-\U0001f5ff"  # misc symbols and pictographs
    "\U0001f680-\U0001f6ff"  # transporte y mapas
    "\U0001fa70-\U0001faff"  # symbols and pictographs extended-a
    "\U0001f900-\U0001f9ff"  # supplemental symbols and pictographs
    "\U0001f1e6-\U0001f1ff"  # regional indicators (banderas)
    "\U00002600-\U000026ff"  # misc symbols (incluye ⚠)
    "\U00002700-\U000027bf"  # dingbats (incluye ✅❌)
    "\U0000fe0f"  # variation selector-16
    "\U0000200d"  # zero width joiner (ZWJ)
    "]+",
    flags=re.UNICODE,
)

# Colapsa dobles espacios (no saltos de linea) que deja el borrado de emojis.
_RE_ESPACIOS = re.compile(r"[ \t]{2,}")
# Espacios/tabs colgando al FINAL de una linea (antes de un salto o del fin).
_RE_COLA_LINEA = re.compile(r"[ \t]+(?=\n|$)")


def quitar_emojis(texto: str) -> str:
    """Quita emojis/simbolos pictograficos del texto de forma determinista.

    Borra los puntos de codigo en `_RE_EMOJI` (emojis, dingbats, banderas,
    variation selectors y ZWJ), colapsa los dobles espacios que pueda dejar el
    borrado y recorta los extremos. NO toca acentos ni URLs (caen fuera de los
    rangos). Sobre un texto sin emojis es practicamente la identidad (salvo el
    recorte de extremos y el colapso de espacios dobles).
    """
    if not texto:
        return texto
    limpio = _RE_EMOJI.sub("", texto)
    # Colapsa los dobles espacios/tabs horizontales (no los saltos de linea) que
    # deja el borrado de un emoji rodeado de espacios.
    limpio = _RE_ESPACIOS.sub(" ", limpio)
    # Quita el espacio que pueda quedar colgando al final de cada linea (p.ej. un
    # emoji al final de la linea); conserva los saltos y la sangria a la izquierda.
    limpio = _RE_COLA_LINEA.sub("", limpio)
    return limpio.strip()


# --------------------------------------------------------------------------- #
# Titulo derivado de la nota                                                   #
# --------------------------------------------------------------------------- #

# Largo maximo del titulo derivado de la nota (chars).
_MAX_TITULO = 80


def derivar_titulo(texto: str) -> str:
    """Deriva un titulo legible desde el texto: 1a linea no vacia recortada a ~80 chars.

    Si no hay ninguna linea con contenido, cae a `"Borrador {YYYY-MM-DD}"`.
    """
    for linea in (texto or "").splitlines():
        limpia = linea.strip()
        if limpia:
            if len(limpia) > _MAX_TITULO:
                # Cortamos en el ULTIMO espacio antes del tope para no partir una palabra.
                # Si no hay ningun espacio (una sola palabra larga), cortamos en seco.
                recorte = limpia[:_MAX_TITULO]
                corte = recorte.rsplit(" ", 1)[0].rstrip() if " " in recorte else recorte.rstrip()
                return corte + "…"
            return limpia
    return f"Borrador {hoy_utc().isoformat()}"


# --------------------------------------------------------------------------- #
# Normalizacion de redes pedidas                                              #
# --------------------------------------------------------------------------- #


def normalizar_redes(crudas: Iterable[str] | None, *, canonicas: list[str]) -> list[str]:
    """Filtra/ordena ids de red contra las `canonicas`; sin entradas validas => todas.

    Ignora ids desconocidos o repetidos. El resultado respeta SIEMPRE el orden de
    `canonicas`, sea cual sea el orden en que llegaron. Si no llega ninguna red valida
    (lista vacia, None o solo basura), se devuelven todas las `canonicas`.
    """
    if crudas is None:
        return list(canonicas)
    validas = set(canonicas)
    pedidas = {r for r in crudas if isinstance(r, str) and r in validas}
    if not pedidas:
        return list(canonicas)
    return [r for r in canonicas if r in pedidas]
