"""Inicializacion idempotente de LÍNEAS de contenido (etiquetas clase 'vertical') y ORÍGENES
(clase 'origen') por marca.

- Las LÍNEAS las dicta el equipo. Solo UnoTV está definida (la dio la dirección): virales,
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
from typing import Any

from . import repos
from .dominio import fuentes_pesos, fuentes_presets

_log = logging.getLogger(__name__)

# Líneas (clase 'vertical') por marca. SOLO las reales dadas por el equipo. El resto vacío.
# Formato: (nombre, ttl_dias, es_evergreen, grupo, cadencia)
#   ttl_dias=0 -> sin caducidad
#   es_evergreen=True -> evergreen, reutilizable en fines de semana
#   grupo -> agrupación de líneas ('' = línea plana, sin grupo). Solo Claro la usa.
#   cadencia -> ritmo de sondeo de sus fuentes: 'rapida' (~3 min) | 'normal' (~10 min) |
#               'evergreen' (~30 min, temas de cambio lento).
LINEAS_POR_MARCA: dict[str, list[tuple[str, int, bool, str, str]]] = {
    "unotv": [
        ("Virales",                   2,  False, "", "normal"),
        ("Internacional",             1,  False, "", "normal"),
        ("Nacional",                  1,  False, "", "normal"),
        ("Presidencia",               1,  False, "", "normal"),
        ("Comercial",                 1,  False, "", "normal"),
        ("Reportero/Corresponsales",  1,  False, "", "normal"),
        ("Ciencia/Tech",              0,  True,  "", "evergreen"),
        ("Geek/Pop",                  0,  True,  "", "evergreen"),
        ("Eventos",                   1,  False, "", "normal"),
    ],
    # Claro Sports (dadas por el equipo). Fútbol = una línea por competición; las
    # competiciones extra "relevantes en México" se añaden cuando el equipo las confirme.
    # El feed se cuelga del GRUPO (Fútbol/Otros deportes/…) y la pieza recibe la línea fina.
    "claro-sports": [
        # Fútbol — una línea por competición (sondeo rápido: deporte en vivo)
        ("Liga MX",              0, False, "Fútbol", "rapida"),
        ("Premier League",       0, False, "Fútbol", "rapida"),
        ("LaLiga (España)",      0, False, "Fútbol", "rapida"),
        ("Mundial",              0, False, "Fútbol", "rapida"),
        ("Eurocopa",             0, False, "Fútbol", "rapida"),
        ("Concacaf",             0, False, "Fútbol", "rapida"),
        ("Copa América",         0, False, "Fútbol", "rapida"),
        ("Champions League",     0, False, "Fútbol", "rapida"),
        ("Europa League",        0, False, "Fútbol", "rapida"),
        ("Leagues Cup",          0, False, "Fútbol", "rapida"),
        ("MLS",                  0, False, "Fútbol", "rapida"),
        ("Bundesliga",           0, False, "Fútbol", "rapida"),
        ("Serie A",              0, False, "Fútbol", "rapida"),
        ("Copa Libertadores",    0, False, "Fútbol", "rapida"),
        ("Mundial de Clubes",    0, False, "Fútbol", "rapida"),
        ("Liga MX Femenil",      0, False, "Fútbol", "rapida"),
        ("Selección de México",  0, False, "Fútbol", "rapida"),
        # Olímpicos (separados): de cambio lento salvo durante los juegos
        ("Olímpicos Verano",     0, False, "Olímpicos", "evergreen"),
        ("Olímpicos Invierno",   0, False, "Olímpicos", "evergreen"),
        # Otros deportes (rápido; Golf es de ritmo lento)
        ("NFL",           0, False, "Otros deportes", "rapida"),
        ("NBA",           0, False, "Otros deportes", "rapida"),
        ("MLB",           0, False, "Otros deportes", "rapida"),
        ("LMB",           0, False, "Otros deportes", "rapida"),
        ("F1 Checo",      0, False, "Otros deportes", "rapida"),
        ("F1 (no Checo)", 0, False, "Otros deportes", "rapida"),
        ("NASCAR",        0, False, "Otros deportes", "rapida"),
        ("Fórmula E",     0, False, "Otros deportes", "rapida"),
        ("Ciclismo",      0, False, "Otros deportes", "rapida"),
        ("TNA",           0, False, "Otros deportes", "rapida"),
        ("Golf",          0, False, "Otros deportes", "evergreen"),
        # Transversales (no deportivas: ritmo normal)
        ("Televisión",   0, False, "Transversal", "normal"),
        ("Portal web",   0, False, "Transversal", "normal"),
        ("Comercial",    0, False, "Transversal", "normal"),
        ("Virales",      0, False, "Transversal", "normal"),
    ],
    # Nación Gamer (noticias de videojuegos). El equipo sumará el resto de líneas.
    "nacion-gamer": [
        ("Gaming",       0, False, "", "normal"),
    ],
    # Fundación: el contenido se clasifica por el PILAR de misión del que habla (no por
    # geografía). Cadencia evergreen: temas de cambio lento, no breaking.
    "fundacion": [
        ("Ciencia/Tech",     0, True, "", "evergreen"),
        ("Salud",            0, True, "", "evergreen"),
        ("Medio ambiente",   0, True, "", "evergreen"),
        ("Cultura",          0, True, "", "evergreen"),
        ("Educación",        0, True, "", "evergreen"),
        ("Impacto social",   0, True, "", "evergreen"),
    ],
}

# Orígenes GLOBALES (marca=''): solo dos, interno y externo.
ORIGENES_GLOBALES: list[str] = ["Interno", "Externo"]


def _crear_si_falta(
    *, nombre: str, clase: str, marca: str, ttl_dias: int = 0, es_evergreen: bool = False,
    grupo: str = "", cadencia: str = "normal",
) -> bool:
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
        grupo=grupo,
        cadencia=cadencia,
    )
    return True


def _backfill_ttl_si_defaults(
    *, nombre: str, clase: str, marca: str, ttl_dias: int, es_evergreen: bool,
    grupo: str = "", cadencia: str = "normal",
) -> bool:
    """Backfilla ttl_dias/es_evergreen/grupo/cadencia en una línea existente SOLO si aún está en
    sus defaults (ttl 0 / es_evergreen False / grupo '' / cadencia 'normal').

    Guarded: nunca sobreescribe si el equipo ya editó los valores. True si actualizó.
    """
    et = repos.obtener_etiqueta_por_nombre(nombre, clase, marca)
    if et is None:
        return False
    cambios: dict[str, Any] = {}
    if et.get("ttl_dias", 0) == 0 and not et.get("es_evergreen", False) and (ttl_dias != 0 or es_evergreen):
        cambios["ttl_dias"] = ttl_dias
        cambios["es_evergreen"] = es_evergreen
    if not (et.get("grupo") or "") and grupo:
        cambios["grupo"] = grupo
    if (et.get("cadencia") or "normal") == "normal" and cadencia != "normal":
        cambios["cadencia"] = cadencia
    if cambios:
        repos.actualizar_etiqueta(et["id"], cambios)
        return True
    return False


def inicializar_lineas() -> int:
    """Inicializa líneas (vertical) por marca y orígenes (global). Devuelve cuántas creó.

    Idempotente y tolerante a fallos por etiqueta (no aborta el resto). Pensada para el
    bootstrap del arranque.
    """
    creadas = 0
    actualizadas = 0
    for marca, lineas in LINEAS_POR_MARCA.items():
        for nombre, ttl_dias, es_evergreen, grupo, cadencia in lineas:
            try:
                if _crear_si_falta(
                    nombre=nombre, clase="vertical", marca=marca, ttl_dias=ttl_dias,
                    es_evergreen=es_evergreen, grupo=grupo, cadencia=cadencia,
                ):
                    creadas += 1
                else:
                    # Línea ya existe: backfill guarded (solo si aún en defaults)
                    if _backfill_ttl_si_defaults(
                        nombre=nombre, clase="vertical", marca=marca,
                        ttl_dias=ttl_dias, es_evergreen=es_evergreen,
                        grupo=grupo, cadencia=cadencia,
                    ):
                        actualizadas += 1
            except Exception:  # noqa: BLE001 -- una etiqueta no debe romper el resto
                _log.warning("inicializacion líneas: no se pudo crear/actualizar %s/%s", marca, nombre, exc_info=True)
    for nombre in ORIGENES_GLOBALES:
        try:
            if _crear_si_falta(nombre=nombre, clase="origen", marca=""):
                creadas += 1
        except Exception:  # noqa: BLE001
            _log.warning("inicializacion orígenes: no se pudo crear %s", nombre, exc_info=True)
    if creadas or actualizadas:
        _log.info("inicializacion líneas/orígenes: %d creadas, %d actualizadas (TTL backfill)", creadas, actualizadas)
    return creadas


# Mapeo categoria(slug de feed) -> nombre de LÍNEA por marca, para el backfill de `linea_id`.
# Solo los casos 1:1 con confianza; lo no mapeado queda en catch-all "General" (linea_id='').
# Claro Sports NO está: sus feeds son GRUESOS (futbol/motor/otros-deportes) y sus líneas FINAS
# (Liga MX…); sin 1:1, se quedan en catch-all y el clasificador por pieza asigna la línea fina.
# Fundación: sus pilares de misión usan los mismos slugs que las categorías de fuente.
_CATEGORIA_A_LINEA: dict[str, dict[str, str]] = {
    "unotv": {
        "mx": "Nacional",
        "internacional": "Internacional",
        "entretenimiento": "Entretenimiento",
        "ciencia-tech": "Ciencia/Tech",
    },
    "nacion-gamer": {
        "gaming": "Gaming",
    },
    "fundacion": {
        "ciencia-tech": "Ciencia/Tech",
        "salud": "Salud",
        "medio-ambiente": "Medio ambiente",
        "cultura": "Cultura",
        "educacion": "Educación",
        "impacto-social": "Impacto social",
    },
}


def vincular_fuentes_a_lineas() -> int:
    """Backfilla `fuentes_rss.linea_id` desde el slug `categoria` por marca. Devuelve cuántas tocó.

    Idempotente: solo toca fuentes cuyo `linea_id` aún esté vacío (nunca pisa una asociación del
    equipo). Las fuentes cuya categoría no mapea a una línea de su marca quedan en catch-all
    (linea_id=''). Requiere las líneas ya sembradas (`inicializar_lineas`).
    """
    vinculadas = 0
    try:
        fuentes = repos.listar_fuentes_rss(marca=None)
    except Exception:  # noqa: BLE001 -- el arranque no debe romper por el backfill
        _log.warning("vincular fuentes->líneas: no se pudo listar fuentes", exc_info=True)
        return 0
    for fuente in fuentes:
        if fuente.get("linea_id") or "":
            continue
        marca = fuente.get("marca") or ""
        cat = (fuente.get("categoria") or "").strip().lower()
        nombre = _CATEGORIA_A_LINEA.get(marca, {}).get(cat)
        if not nombre:
            continue
        try:
            et = repos.obtener_etiqueta_por_nombre(nombre, "vertical", marca)
            if et is None:
                continue
            repos.actualizar_fuente_rss(fuente["id"], {"linea_id": et["id"]})
            vinculadas += 1
        except Exception:  # noqa: BLE001 -- una fuente no debe romper el resto
            _log.warning("vincular fuentes->líneas: fallo en %s", fuente.get("id"), exc_info=True)
    if vinculadas:
        _log.info("vincular fuentes->líneas: %d fuentes asociadas a su línea", vinculadas)
    return vinculadas


# --------------------------------------------------------------------------- #
# Auto-seed del catálogo de feeds para el motor de ingesta (Ola A)             #
# --------------------------------------------------------------------------- #

# Prioridad de sondeo por categoría (mayor = más frecuente al planificar). Espeja la cadencia:
# las categorías de deporte (futbol/motor/otros-deportes) son prioritarias; mx/internacional
# medias; gaming de cambio lento. El motor usa además la cadencia por categoría; la prioridad
# ordena los vencidos dentro de un barrido.
_PRIORIDAD_CATEGORIA: dict[str, int] = {
    "futbol": 3,
    "motor": 3,
    "otros-deportes": 3,
    "mx": 2,
    "internacional": 2,
    "gaming": 1,
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
    de consentimiento: aporta contenido irrelevante sin cuerpo para el copy. La señal de tendencia ya la cubre
    Google Trends, así que NO se auto-inicializan. Siguen en el catálogo (activables a mano).
    """
    return "news.google.com" in (preset.get("url") or "")


def _preset_va_en_seed(preset: dict) -> bool:
    """True si el preset debe activarse en el auto-seed por defecto.

    Función PURA (sin red ni BD), reutilizable en tests. El catálogo base (`fuentes_presets.json`) YA
    es el conjunto curado que el equipo dejó valioso en producción, así que se carga ENTERO,
    salvo los dos guardas defensivos: NO plantillas (URL con variable sin sustituir) y NO Google
    News (snippet sin cuerpo; la tendencia la cubre Google Trends). El catálogo de hoy no trae
    ninguno de los dos, pero los guardas se mantienen por si se reintroducen.
    """
    return not _es_plantilla(preset) and not _es_google_news(preset)


def inicializar_fuentes_ingesta() -> int:
    """Activa los presets de feeds como `fuentes_rss` SI el catálogo está vacío (idempotente).

    Garantiza cobertura inicial real para que el motor de ingesta no arranque vacío. Solo
    inicializa cuando NO hay ninguna `fuentes_rss` (no pisa un catálogo que el equipo ya curó).
    Idempotente por URL: omite cualquier preset cuya URL ya exista. Salta las PLANTILLAS (URL
    con variable) y los presets fuera del subset por defecto (`_preset_va_en_seed`): el catálogo
    completo (cientos de presets verificados) se activa a mano desde la UI; aquí activamos un
    subconjunto sensato por marca para arrancar con cobertura útil sin contenido irrelevante. Fija
    `categoria`/`marca_sugerida`/`prioridad` para la planificación. Best-effort por preset.
    """
    try:
        if repos.contar_fuentes_rss() > 0:
            return 0
    except Exception:  # noqa: BLE001 -- si no se puede leer, no inicializamos (no rompe el arranque)
        _log.warning("inicializacion feeds ingesta: no se pudo consultar fuentes_rss", exc_info=True)
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
            _log.warning("inicializacion feeds ingesta: no se pudo crear %s", url, exc_info=True)

    if creadas:
        _log.info("inicializacion feeds ingesta: %d fuente(s) activadas desde presets.", creadas)
    return creadas
