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
- `es_evergreen=True` marca líneas evergreen reutilizables en fines de semana.
- Los valores por defecto se aplican SOLO al crear la etiqueta (nunca sobreescriben
  ediciones del equipo). Para UnoTV se aplica además una actualización guarded de
  backfill que solo toca filas que aún estén en los defaults (0/0).

Idempotente: solo crea lo que no exista ya (por nombre+clase+marca); NUNCA pisa lo que el
equipo edite (nombres, keywords). Pensada para correr en el bootstrap del arranque.
"""

from __future__ import annotations

import logging

from . import repos
from .dominio import fuentes_pesos, fuentes_presets

_log = logging.getLogger(__name__)

# Líneas (clase 'vertical') por marca. SOLO las reales dadas por el equipo. El resto vacío.
# Formato: (nombre, ttl_dias, es_evergreen)
#   ttl_dias=0 -> sin caducidad
#   es_evergreen=True -> evergreen, reutilizable en fines de semana
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


def _crear_si_falta(*, nombre: str, clase: str, marca: str, ttl_dias: int = 0, es_evergreen: bool = False) -> bool:
    """Crea la etiqueta (sin keywords) si no existe (nombre+clase+marca). True si la creó."""
    if repos.existe_etiqueta_nombre(nombre, clase, marca):
        return False
    repos.crear_etiqueta(
        nombre=nombre,
        clase=clase,
        marca=marca,
        keywords="",
        ttl_dias=ttl_dias,
        es_evergreen=es_evergreen,
    )
    return True


def _backfill_ttl_si_defaults(*, nombre: str, clase: str, marca: str, ttl_dias: int, es_evergreen: bool) -> bool:
    """Actualiza ttl_dias/es_evergreen en una línea existente SOLO si aún está en defaults (0/False).

    Guarded: nunca sobreescribe si el equipo ya editó los valores. True si actualizó.
    """
    et = repos.obtener_etiqueta_por_nombre(nombre, clase, marca)
    if et is None:
        return False
    if et.get("ttl_dias", 0) == 0 and not et.get("es_evergreen", False):
        # Solo backfill si los valores objetivo son no-default (evita writes inútiles)
        if ttl_dias != 0 or es_evergreen:
            repos.actualizar_etiqueta(et["id"], {"ttl_dias": ttl_dias, "es_evergreen": es_evergreen})
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
        for nombre, ttl_dias, es_evergreen in lineas:
            try:
                if _crear_si_falta(nombre=nombre, clase="vertical", marca=marca, ttl_dias=ttl_dias, es_evergreen=es_evergreen):
                    creadas += 1
                else:
                    # Línea ya existe: backfill guarded (solo si aún en defaults)
                    if _backfill_ttl_si_defaults(
                        nombre=nombre, clase="vertical", marca=marca,
                        ttl_dias=ttl_dias, es_evergreen=es_evergreen,
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


# --------------------------------------------------------------------------- #
# Auto-seed del catálogo de feeds para el motor de ingesta (Ola A)             #
# --------------------------------------------------------------------------- #

# Prioridad de sondeo por categoría (mayor = más frecuente al planificar). Espeja la cadencia:
# breaking/deportes son prioritarias; mx/internacional/tendencias medias; ciencia-tech/gaming
# de cambio lento. El motor usa además la cadencia por categoría; la prioridad ordena los
# vencidos dentro de un barrido.
_PRIORIDAD_CATEGORIA: dict[str, int] = {
    "deportes": 3,
    "mx": 2,
    "regional": 2,
    "internacional": 2,
    "negocios": 1,
    "tendencias": 2,
    "ciencia-tech": 1,
    "gaming": 1,
}

# Subset por DEFECTO que se activa en una instalación nueva (auto-seed). El catálogo completo
# (cientos de presets) se activa a mano desde la UI; aquí solo sembramos un subconjunto sensato
# por marca para que el motor de ingesta arranque con cobertura útil SIN ruido:
#   - UnoTV (noticias): MX + regional + internacional + ciencia-tech + tendencias.
#   - Claro Sports (deporte): deportes (todas las competiciones) + algo de internacional.
#   - Nación Gamer (gaming/tech): gaming + ciencia-tech.
# El ruteo es por `marca_sugerida` del preset y su `categoria`. Un preset sin marca_sugerida
# (p.ej. plantillas) no entra. Cada marca declara las categorías que le interesan.
_CATEGORIAS_SEED_POR_MARCA: dict[str, set[str]] = {
    "unotv": {"mx", "regional", "internacional", "negocios", "ciencia-tech", "tendencias"},
    "claro-sports": {"deportes", "internacional"},
    "nacion-gamer": {"gaming", "ciencia-tech"},
}


# Las PLANTILLAS (con `{variable}` sin sustituir, p.ej. Google News búsqueda, GDELT, YouTube,
# Reddit personalizado) NO se activan en el auto-seed: su URL no es un feed real hasta que el
# equipo la ajusta. Se reconocen por el sufijo "[PLANTILLA]" en el nombre del preset.
def _es_plantilla(preset: dict) -> bool:
    """True si el preset es una PLANTILLA (URL con variable sin sustituir)."""
    return "[PLANTILLA]" in (preset.get("nombre") or "")


def _es_google_news(preset: dict) -> bool:
    """True si el preset es un feed de Google News (`news.google.com`).

    Google News solo entrega titular + snippet corto (sin `content:encoded`) tras un redirect
    de consentimiento: aporta ruido sin cuerpo para el copy. La señal de tendencia ya la cubre
    Google Trends, así que NO se auto-siembran. Siguen en el catálogo (activables a mano).
    """
    return "news.google.com" in (preset.get("url") or "")


def _preset_va_en_seed(preset: dict) -> bool:
    """True si el preset debe activarse en el auto-seed por defecto.

    Función PURA (sin red ni BD), reutilizable en tests. Un preset entra si:
      - NO es plantilla (su URL es un feed real, sondeable directamente), y
      - NO es Google News (snippet sin cuerpo; la tendencia la cubre Google Trends), y
      - su `marca_sugerida` tiene categorías de interés declaradas, y
      - su `categoria` está entre las de interés de esa marca.
    """
    if _es_plantilla(preset) or _es_google_news(preset):
        return False
    marca = (preset.get("marca_sugerida") or "").strip()
    categoria = (preset.get("categoria") or "").strip()
    cats_marca = _CATEGORIAS_SEED_POR_MARCA.get(marca)
    if not cats_marca:
        return False
    return categoria in cats_marca


def sembrar_fuentes_ingesta() -> int:
    """Activa los presets de feeds como `fuentes_rss` SI el catálogo está vacío (idempotente).

    Garantiza cobertura inicial real para que el motor de ingesta no arranque vacío. Solo
    siembra cuando NO hay ninguna `fuentes_rss` (no pisa un catálogo que el equipo ya curó).
    Idempotente por URL: omite cualquier preset cuya URL ya exista. Salta las PLANTILLAS (URL
    con variable) y los presets fuera del subset por defecto (`_preset_va_en_seed`): el catálogo
    completo (cientos de presets verificados) se activa a mano desde la UI; aquí sembramos un
    subconjunto sensato por marca para arrancar con cobertura útil sin ruido. Fija
    `categoria`/`marca_sugerida`/`prioridad` para la planificación. Best-effort por preset.
    """
    try:
        if repos.contar_fuentes_rss() > 0:
            return 0
    except Exception:  # noqa: BLE001 -- si no se puede leer, no sembramos (no rompe el arranque)
        _log.warning("semilla feeds ingesta: no se pudo consultar fuentes_rss", exc_info=True)
        return 0

    existentes: set[str] = set()
    try:
        existentes = {
            str(f.get("url", "")).strip() for f in repos.listar_fuentes_rss() if f.get("url")
        }
    except Exception:  # noqa: BLE001
        existentes = set()

    creadas = 0
    for preset in fuentes_presets.listar_presets():
        url = (preset.get("url") or "").strip()
        if not url or url in existentes or not _preset_va_en_seed(preset):
            continue
        categoria = preset.get("categoria") or ""
        try:
            repos.crear_fuente_rss(
                preset.get("nombre") or url,
                url,
                marca=preset.get("marca_sugerida") or "",
                categoria=categoria,
                prioridad=_PRIORIDAD_CATEGORIA.get(categoria, 0),
                # Peso editorial: el del preset o el seed por host (Reuters/BBC nacen potentes).
                peso=float(preset.get("peso") or 0) or fuentes_pesos.peso_de_url(url),
            )
            existentes.add(url)
            creadas += 1
        except Exception:  # noqa: BLE001 -- un preset no debe romper el resto
            _log.warning("semilla feeds ingesta: no se pudo crear %s", url, exc_info=True)

    if creadas:
        _log.info("semilla feeds ingesta: %d fuente(s) activadas desde presets.", creadas)
    return creadas
