"""Semilla idempotente de LÍNEAS de contenido (etiquetas clase 'vertical') y ORÍGENES
(clase 'origen') por marca.

- Las LÍNEAS las dicta el equipo. Solo UnoTV está definida (la dio Bernardo): virales,
  internacional, nacional, presidencia, comercial, reportero/corresponsales, ciencia/tech,
  geek/pop, eventos. El RESTO de marcas se deja VACÍO a propósito: el equipo las creará
  desde la pestaña de Líneas cuando toque (no se inventan aquí).
- Los ORÍGENES son GLOBALES (marca=''): "Interno" y "Externo".
- Las `keywords` (para el auto-etiquetado) se dejan VACÍAS: las rellena el equipo desde la
  UI por línea. Sin keywords, una pieza queda "sin línea" (aviso), nunca se descarta.

Frescura (TTL) por línea editorial:
- `ttl_dias=0` significa sin caducidad / evergreen.
- `es_green=True` marca líneas evergreen reutilizables en fines de semana.
- Los valores por defecto se aplican SOLO al crear la etiqueta (nunca sobreescriben
  ediciones del equipo). Para UnoTV se aplica además una actualización guarded de
  backfill que solo toca filas que aún estén en los defaults (0/0).

Idempotente: solo crea lo que no exista ya (por nombre+clase+marca); NUNCA pisa lo que el
equipo edite (nombres, keywords). Pensada para correr en el bootstrap del arranque.
"""

from __future__ import annotations

import logging

from . import repos

_log = logging.getLogger(__name__)

# Líneas (clase 'vertical') por marca. SOLO las reales dadas por el equipo. El resto vacío.
# Formato: (nombre, ttl_dias, es_green)
#   ttl_dias=0 -> sin caducidad
#   es_green=True -> evergreen, reutilizable en fines de semana
LINEAS_POR_MARCA: dict[str, list[tuple[str, int, bool]]] = {
    "unotv": [
        ("Virales",                   2,  False),
        ("Internacional",             1,  False),
        ("Nacional",                  1,  False),
        ("Presidencia",               1,  False),
        ("Comercial",                 1,  False),
        ("Reportero/Corresponsales",  1,  False),
        ("Ciencia/Tech",              0,  True),
        ("Geek/Pop",                  0,  True),
        ("Eventos",                   1,  False),
    ],
    # Claro Sports (dadas por el equipo). Fútbol = una línea por competición; las
    # competiciones extra "relevantes en México" se añaden cuando el equipo las confirme.
    "claro-sports": [
        # Fútbol — una línea por competición
        ("Liga MX",              0, False),
        ("Premier League",       0, False),
        ("LaLiga (España)",      0, False),
        ("Mundial",              0, False),
        ("Eurocopa",             0, False),
        ("Concacaf",             0, False),
        ("Copa América",         0, False),
        ("Champions League",     0, False),
        ("Europa League",        0, False),
        ("Leagues Cup",          0, False),
        ("MLS",                  0, False),
        ("Bundesliga",           0, False),
        ("Serie A",              0, False),
        ("Copa Libertadores",    0, False),
        ("Mundial de Clubes",    0, False),
        ("Liga MX Femenil",      0, False),
        ("Selección de México",  0, False),
        # Olímpicos (separados)
        ("Olímpicos Verano",     0, False),
        ("Olímpicos Invierno",   0, False),
        # Otros deportes
        ("NFL",           0, False),
        ("NBA",           0, False),
        ("MLB",           0, False),
        ("LMB",           0, False),
        ("F1 Checo",      0, False),
        ("F1 (no Checo)", 0, False),
        ("NASCAR",        0, False),
        ("Fórmula E",     0, False),
        ("Ciclismo",      0, False),
        ("TNA",           0, False),
        ("Golf",          0, False),
        # Transversales
        ("Televisión",   0, False),
        ("Portal web",   0, False),
        ("Comercial",    0, False),
        ("Virales",      0, False),
    ],
}

# Orígenes GLOBALES (marca=''): solo dos, interno y externo.
ORIGENES_GLOBALES: list[str] = ["Interno", "Externo"]


def _crear_si_falta(*, nombre: str, clase: str, marca: str, ttl_dias: int = 0, es_green: bool = False) -> bool:
    """Crea la etiqueta (sin keywords) si no existe (nombre+clase+marca). True si la creó."""
    if repos.existe_etiqueta_nombre(nombre, clase, marca):
        return False
    repos.crear_etiqueta(
        nombre=nombre,
        clase=clase,
        marca=marca,
        keywords="",
        ttl_dias=ttl_dias,
        es_green=es_green,
    )
    return True


def _backfill_ttl_si_defaults(*, nombre: str, clase: str, marca: str, ttl_dias: int, es_green: bool) -> bool:
    """Actualiza ttl_dias/es_green en una línea existente SOLO si aún está en defaults (0/False).

    Guarded: nunca sobreescribe si el equipo ya editó los valores. True si actualizó.
    """
    et = repos.obtener_etiqueta_por_nombre(nombre, clase, marca)
    if et is None:
        return False
    if et.get("ttl_dias", 0) == 0 and not et.get("es_green", False):
        # Solo backfill si los valores objetivo son no-default (evita writes inútiles)
        if ttl_dias != 0 or es_green:
            repos.actualizar_etiqueta(et["id"], {"ttl_dias": ttl_dias, "es_green": es_green})
            return True
    return False


def sembrar_lineas() -> int:
    """Siembra líneas (vertical) por marca y orígenes (global). Devuelve cuántas creó.

    Idempotente y tolerante a fallos por etiqueta (no aborta el resto). Pensada para el
    bootstrap del arranque.
    """
    creadas = 0
    actualizadas = 0
    for marca, lineas in LINEAS_POR_MARCA.items():
        for nombre, ttl_dias, es_green in lineas:
            try:
                if _crear_si_falta(nombre=nombre, clase="vertical", marca=marca, ttl_dias=ttl_dias, es_green=es_green):
                    creadas += 1
                else:
                    # Línea ya existe: backfill guarded (solo si aún en defaults)
                    if _backfill_ttl_si_defaults(
                        nombre=nombre, clase="vertical", marca=marca,
                        ttl_dias=ttl_dias, es_green=es_green,
                    ):
                        actualizadas += 1
            except Exception:  # noqa: BLE001 -- una etiqueta no debe romper el resto
                _log.warning("semilla líneas: no se pudo crear/actualizar %s/%s", marca, nombre, exc_info=True)
    for nombre in ORIGENES_GLOBALES:
        try:
            if _crear_si_falta(nombre=nombre, clase="origen", marca=""):
                creadas += 1
        except Exception:  # noqa: BLE001
            _log.warning("semilla orígenes: no se pudo crear %s", nombre, exc_info=True)
    if creadas or actualizadas:
        _log.info("semilla líneas/orígenes: %d creadas, %d actualizadas (TTL backfill)", creadas, actualizadas)
    return creadas
