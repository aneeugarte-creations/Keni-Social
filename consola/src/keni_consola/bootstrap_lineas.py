"""Semilla idempotente de LÍNEAS de contenido (etiquetas clase 'vertical') y ORÍGENES
(clase 'origen') por marca.

- Las LÍNEAS las dicta el equipo. Solo UnoTV está definida (la dio Bernardo): virales,
  internacional, nacional, presidencia, comercial, reportero/corresponsales, ciencia/tech,
  geek/pop, eventos. El RESTO de marcas se deja VACÍO a propósito: el equipo las creará
  desde la pestaña de Líneas cuando toque (no se inventan aquí).
- Los ORÍGENES son GLOBALES (marca=''): "Interno" y "Externo".
- Las `keywords` (para el auto-etiquetado) se dejan VACÍAS: las rellena el equipo desde la
  UI por línea. Sin keywords, una pieza queda "sin línea" (aviso), nunca se descarta.

Idempotente: solo crea lo que no exista ya (por nombre+clase+marca); NUNCA pisa lo que el
equipo edite (nombres, keywords). Pensada para correr en el bootstrap del arranque.
"""

from __future__ import annotations

import logging

from . import repos

_log = logging.getLogger(__name__)

# Líneas (clase 'vertical') por marca. SOLO las reales dadas por el equipo. El resto vacío.
LINEAS_POR_MARCA: dict[str, list[str]] = {
    "unotv": [
        "Virales",
        "Internacional",
        "Nacional",
        "Presidencia",
        "Comercial",
        "Reportero/Corresponsales",
        "Ciencia/Tech",
        "Geek/Pop",
        "Eventos",
    ],
    # Claro Sports (dadas por el equipo). Fútbol = una línea por competición; las
    # competiciones extra "relevantes en México" se añaden cuando el equipo las confirme.
    "claro-sports": [
        # Fútbol — una línea por competición
        "Liga MX",
        "Premier League",
        "LaLiga (España)",
        "Mundial",
        "Eurocopa",
        "Concacaf",
        "Copa América",
        "Champions League",
        "Europa League",
        "Leagues Cup",
        "MLS",
        "Bundesliga",
        "Serie A",
        "Copa Libertadores",
        "Mundial de Clubes",
        "Liga MX Femenil",
        "Selección de México",
        # Olímpicos (separados)
        "Olímpicos Verano",
        "Olímpicos Invierno",
        # Otros deportes
        "NFL",
        "NBA",
        "MLB",
        "LMB",
        "F1 Checo",
        "F1 (no Checo)",
        "NASCAR",
        "Fórmula E",
        "Ciclismo",
        "TNA",
        "Golf",
        # Transversales
        "Televisión",
        "Portal web",
        "Comercial",
        "Virales",
    ],
}

# Orígenes GLOBALES (marca=''): solo dos, interno y externo.
ORIGENES_GLOBALES: list[str] = ["Interno", "Externo"]


def _crear_si_falta(*, nombre: str, clase: str, marca: str) -> bool:
    """Crea la etiqueta (sin keywords) si no existe (nombre+clase+marca). True si la creó."""
    if repos.existe_etiqueta_nombre(nombre, clase, marca):
        return False
    repos.crear_etiqueta(nombre=nombre, clase=clase, marca=marca, keywords="")
    return True


def sembrar_lineas() -> int:
    """Siembra líneas (vertical) por marca y orígenes (global). Devuelve cuántas creó.

    Idempotente y tolerante a fallos por etiqueta (no aborta el resto). Pensada para el
    bootstrap del arranque.
    """
    creadas = 0
    for marca, lineas in LINEAS_POR_MARCA.items():
        for nombre in lineas:
            try:
                if _crear_si_falta(nombre=nombre, clase="vertical", marca=marca):
                    creadas += 1
            except Exception:  # noqa: BLE001 -- una etiqueta no debe romper el resto
                _log.warning("semilla líneas: no se pudo crear %s/%s", marca, nombre, exc_info=True)
    for nombre in ORIGENES_GLOBALES:
        try:
            if _crear_si_falta(nombre=nombre, clase="origen", marca=""):
                creadas += 1
        except Exception:  # noqa: BLE001
            _log.warning("semilla orígenes: no se pudo crear %s", nombre, exc_info=True)
    if creadas:
        _log.info("semilla líneas/orígenes: %d etiquetas creadas", creadas)
    return creadas
