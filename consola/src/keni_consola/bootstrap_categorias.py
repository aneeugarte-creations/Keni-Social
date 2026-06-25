"""Inicializacion idempotente de CATEGORÍAS de contenido (etiquetas clase 'categoria') y ORÍGENES
(clase 'origen') por marca.

- Las CATEGORÍAS las dicta el equipo. UnoTV, Claro Sports, Nación Gamer y Fundación están
  definidas (las dio la dirección); el resto de marcas se deja VACÍO a propósito hasta que el
  equipo las cree desde la pestaña de Líneas.
- Los ORÍGENES son GLOBALES (marca=''): "Interno" y "Externo".
- Las `keywords` (auto-etiquetado léxico, `dominio.clasificador_categorias`) se SIEMBRAN para las
  categorías de Claro Sports (catálogo curado en `KEYWORDS_POR_CATEGORIA`, editable por el equipo desde
  la UI); para el resto nacen vacías. Una categoría sin keywords no casa ninguna pieza (queda "sin
  categoría", aviso, nunca se descarta). La siembra es guarded: solo rellena una categoría cuyo campo
  siga vacío (nunca pisa lo que el equipo edite).

Frescura (TTL) por categoría editorial:
- `ttl_dias=0` significa sin caducidad / evergreen.
- `es_evergreen=True` marca categorías evergreen reutilizables en fines de semana.
- Al crear se aplican tal cual. Para una categoría YA existente, `_reconciliar_linea` reconcilia
  guarded (ttl/grupo/cadencia/keywords): lleva la taxonomía nueva a las categorías sembradas sin
  pisar lo que el equipo haya editado a mano.

Idempotente: solo crea lo que no exista ya (por nombre+clase+marca); NUNCA pisa lo que el
equipo edite (nombres, keywords). Pensada para correr en el bootstrap del arranque.
"""

from __future__ import annotations

import logging
import unicodedata
from collections.abc import Mapping
from typing import Any

from . import repos
from .dominio import fuentes_pesos, fuentes_presets

_log = logging.getLogger(__name__)


def slug_hashtag(nombre: str) -> str:
    """Cuerpo (sin '#') del hashtag de una CATEGORÍA, derivado de su nombre: sin acentos, en
    minúscula y solo alfanumérico. "Ciencia/Tech" -> "cienciatech", "Medio ambiente" ->
    "medioambiente", "LaLiga (España)" -> "laligaespana". "" si el nombre no deja nada."""
    base = unicodedata.normalize("NFKD", str(nombre or ""))
    base = "".join(c for c in base if not unicodedata.combining(c))
    return "".join(c for c in base.lower() if c.isalnum())

# Líneas (clase 'categoria') por marca. SOLO las reales dadas por el equipo. El resto vacío.
# Formato: (nombre, ttl_dias, es_evergreen, grupo, cadencia)
#   ttl_dias=0 -> sin caducidad
#   es_evergreen=True -> evergreen, reutilizable en fines de semana
#   grupo -> agrupación de categorías ('' = categoría plana, sin grupo). Solo Claro la usa: es el
#            nivel de la BARRA de navegación de Noticias (un chip por grupo distinto).
#   cadencia -> ritmo de sondeo de sus fuentes: 'rapida' (~3 min) | 'normal' (~10 min) |
#               'evergreen' (~30 min, temas de cambio lento).
CATEGORIAS_POR_MARCA: dict[str, list[tuple[str, int, bool, str, str]]] = {
    # UnoTV publica por estas CATEGORÍAS reales (las dio la dirección). «Última hora» (breaking) y
    # «Evergreen» son señales del motor, no categorías. Las etiquetas viejas que sobraban se retiran
    # (ver `_CATEGORIAS_RETIRADAS`).
    "unotv": [
        ("Nacional",        1, False, "", "normal"),
        ("Internacional",   1, False, "", "normal"),
        ("Entretenimiento", 1, False, "", "normal"),
    ],
    # Claro Sports: una CATEGORÍA fina por competición/disciplina, agrupadas por GRUPO. El grupo es
    # el nivel de la barra de navegación de Noticias (Fútbol · Motor · Olímpicos · NFL · Boxeo ·
    # NBA · Béisbol · Otros Deportes · Actualidad). El feed se cuelga del grupo y el clasificador
    # léxico (keywords en `KEYWORDS_POR_CATEGORIA`) asigna la categoría fina a cada pieza.
    "claro-sports": [
        # Fútbol — una categoría por competición (sondeo rápido: deporte en vivo)
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
        # Olímpicos: de cambio lento salvo durante los juegos.
        ("Olímpicos Verano",     0, False, "Olímpicos", "evergreen"),
        ("Olímpicos Invierno",   0, False, "Olímpicos", "evergreen"),
        # Motor: F1 (Checo) es el buque insignia; NASCAR/Fórmula E cuelgan del mismo grupo.
        ("F1 Checo",      0, False, "Motor", "rapida"),
        ("F1 (no Checo)", 0, False, "Motor", "rapida"),
        ("NASCAR",        0, False, "Motor", "rapida"),
        ("Fórmula E",     0, False, "Motor", "rapida"),
        # Deportes de EE. UU.: cada uno con su propio chip en la barra.
        ("NFL",           0, False, "NFL", "rapida"),
        ("NBA",           0, False, "NBA", "rapida"),
        ("MLB",           0, False, "Béisbol", "rapida"),
        ("LMB",           0, False, "Béisbol", "rapida"),
        # Boxeo: categoría propia (motor de volumen mexicano: Canelo).
        ("Boxeo",         0, False, "Boxeo", "rapida"),
        # Otros deportes: cola larga bajo un solo chip (Golf es de ritmo lento).
        ("Tenis",         0, False, "Otros deportes", "rapida"),
        ("Ciclismo",      0, False, "Otros deportes", "rapida"),
        ("UFC",           0, False, "Otros deportes", "rapida"),
        ("TNA",           0, False, "Otros deportes", "rapida"),
        ("Golf",          0, False, "Otros deportes", "evergreen"),
        # Actualidad: no deportivas (entretenimiento, virales, parrilla de TV, comercial).
        ("Televisión",   0, False, "Actualidad", "normal"),
        ("Portal web",   0, False, "Actualidad", "normal"),
        ("Comercial",    0, False, "Actualidad", "normal"),
        ("Virales",      0, False, "Actualidad", "normal"),
    ],
    # Nación Gamer (noticias de videojuegos). El equipo sumará el resto de categorías.
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

# Palabras clave (CSV) por CATEGORÍA para el clasificador léxico (`dominio.clasificador_categorias`):
# casan como palabra contra título+resumen normalizado (sin acentos, minúsculas). Catálogo de
# arranque para Claro Sports; el equipo lo refina desde la UI de Líneas. Tokens distintivos para
# minimizar el cruce entre categorías (gana la categoría con más coincidencias). SOLO Claro trae
# catálogo; «Portal web»/«Comercial» se dejan sin keywords (operativas, no son destino de
# clasificación de noticias). La siembra es guarded: solo rellena una categoría con keywords vacías.
KEYWORDS_POR_CATEGORIA: dict[str, dict[str, str]] = {
    "claro-sports": {
        # — Fútbol —
        "Liga MX": "liga mx, club america, chivas, guadalajara, cruz azul, pumas, tigres, rayados, monterrey, toluca, santos laguna, pachuca, atlas, leon, necaxa, queretaro, mazatlan, fc juarez, xolos, tijuana, puebla, atletico de san luis, apertura, clausura, liguilla",
        "Premier League": "premier league, manchester city, manchester united, liverpool, chelsea, arsenal, tottenham, newcastle",
        "LaLiga (España)": "laliga, la liga, real madrid, barcelona, barca, atletico de madrid, sevilla, villarreal, real betis",
        "Mundial": "mundial 2026, copa del mundo, world cup, repechaje mundial, sede mundialista",
        "Eurocopa": "eurocopa, euro 2028, campeonato europeo de naciones",
        "Concacaf": "concacaf, liga de naciones concacaf, copa oro, concachampions, gold cup",
        "Copa América": "copa america, conmebol copa america",
        "Champions League": "champions league, uefa champions, liga de campeones",
        "Europa League": "europa league, uefa europa, conference league",
        "Leagues Cup": "leagues cup",
        "MLS": "mls, major league soccer, inter miami",
        "Bundesliga": "bundesliga, bayern munich, borussia dortmund, bayer leverkusen, rb leipzig",
        "Serie A": "serie a, juventus, inter de milan, ac milan, napoli, as roma, lazio",
        "Copa Libertadores": "copa libertadores, conmebol libertadores, copa sudamericana",
        "Mundial de Clubes": "mundial de clubes, club world cup",
        "Liga MX Femenil": "liga mx femenil, futbol femenil",
        "Selección de México": "seleccion mexicana, seleccion de mexico, el tri, tricolor",
        # — Olímpicos —
        "Olímpicos Verano": "juegos olimpicos, olimpiadas, paris 2024, los angeles 2028, medalla olimpica, clavados, tiro con arco, halterofilia, marcha atletica",
        "Olímpicos Invierno": "juegos olimpicos de invierno, milano cortina, milan cortina 2026, esqui, patinaje artistico, snowboard, biatlon",
        # — Motor —
        "F1 Checo": "checo perez, sergio perez, cadillac f1",
        "F1 (no Checo)": "formula 1, formula uno, gran premio, verstappen, lewis hamilton, escuderia ferrari, mclaren, red bull racing, pole position",
        "NASCAR": "nascar, nascar mexico",
        "Fórmula E": "formula e, formula electrica",
        # — Deportes de EE. UU. —
        "NFL": "nfl, super bowl, super tazon, touchdown, quarterback, dallas cowboys, kansas city chiefs, futbol americano",
        "NBA": "nba, lakers, celtics, golden state warriors, lebron james, stephen curry, baloncesto, basquetbol, playoffs nba",
        "MLB": "mlb, grandes ligas, new york yankees, dodgers, world series, serie mundial",
        "LMB": "lmb, liga mexicana de beisbol, diablos rojos, sultanes de monterrey, pericos de puebla",
        # — Boxeo —
        "Boxeo": "boxeo, canelo, canelo alvarez, saul alvarez, box, pelea de box, nocaut, knockout, cmb, campeon mundial de boxeo, marco verde, pugilismo",
        # — Otros deportes —
        "Tenis": "tenis, atp, wta, grand slam, roland garros, wimbledon, us open, australian open, carlos alcaraz, jannik sinner, novak djokovic, sabalenka",
        "Ciclismo": "ciclismo, tour de francia, giro de italia, vuelta a espana, isaac del toro, uci, peloton, contrarreloj",
        "UFC": "ufc, mma, artes marciales mixtas, octagono, pelea ufc",
        "TNA": "tna, lucha libre, wrestling, wwe, aaa lucha",
        "Golf": "golf, pga, masters de augusta, lpga, ryder cup",
        # — Actualidad —
        "Televisión": "estreno, serie de netflix, hbo max, disney plus, masterchef, exatlon, telenovela",
        "Virales": "viral, se viraliza, redes sociales, polemica en redes",
    },
    # Fundación: sus feeds son MIXTOS (divulgación, buenas noticias) y vienen con slugs gruesos
    # (entretenimiento/internacional/mx) que no mapean a estas categorías; el clasificador léxico
    # asigna la categoría fina por CONTENIDO de cada nota. Catálogo de arranque; el equipo lo refina
    # desde la UI de Líneas. Tokens distintivos para minimizar el cruce (gana la categoría con más
    # coincidencias; empate -> la primera del orden, Ciencia/Tech).
    "fundacion": {
        "Ciencia/Tech": "ciencia, cientifico, cientificos, cientifica, investigacion, estudio, "
        "descubrimiento, hallazgo, fisica, quimica, biologia, astronomia, espacio, nasa, universo, "
        "galaxia, telescopio, tecnologia, inteligencia artificial, robot, algoritmo, software, "
        "innovacion, ingenieria, fosil, dinosaurio, arqueologia, arqueologico, adn, genetica, "
        "particula, cuantica",
        "Salud": "salud, medico, medicos, medicina, enfermedad, enfermedades, virus, vacuna, "
        "vacunas, cancer, diabetes, obesidad, salud mental, depresion, ansiedad, nutricion, dieta, "
        "alimentacion, ejercicio, bienestar, hospital, paciente, pacientes, sintoma, sintomas, "
        "tratamiento, terapia, farmaco, cerebro, corazon, sueno, longevidad",
        "Medio ambiente": "medio ambiente, ambiental, clima, climatico, cambio climatico, "
        "calentamiento, sostenible, sostenibilidad, sustentable, ecologia, ecosistema, "
        "biodiversidad, especie, especies, contaminacion, emisiones, carbono, reciclaje, "
        "energia renovable, renovable, solar, eolica, bosque, bosques, deforestacion, oceano, "
        "oceanos, arrecife, fauna, naturaleza, residuos, plastico",
        "Cultura": "cultura, cultural, arte, artista, museo, exposicion, pintura, escultura, "
        "musica, concierto, festival, cine, pelicula, libro, literatura, novela, escritor, poesia, "
        "teatro, danza, patrimonio, historia, historico, civilizacion, tradicion, gastronomia",
        "Educación": "educacion, educativo, escuela, escuelas, maestro, maestros, docente, alumno, "
        "alumnos, estudiante, estudiantes, universidad, aprendizaje, ensenanza, beca, becas, aula, "
        "pedagogia, alfabetizacion, capacitacion",
        "Impacto social": "impacto social, comunidad, comunidades, solidaridad, voluntario, "
        "voluntariado, donacion, donaciones, ong, beneficencia, pobreza, desigualdad, inclusion, "
        "derechos humanos, vulnerable, vulnerables, refugiados, migrantes, discapacidad, equidad",
    },
}

# Orígenes GLOBALES (marca=''): solo dos, interno y externo.
ORIGENES_GLOBALES: list[str] = ["Interno", "Externo"]

# CATEGORÍAS (clase 'categoria') que se RETIRAN por marca: etiquetas viejas que no son categorías reales
# del plan. Se desactivan (activo=0), no se borran: salen del editor «Plan y horarios», del
# selector de feeds y del catálogo, pero su historial de métricas se conserva. UnoTV publica solo
# por Nacional/Internacional/Entretenimiento (+ Última hora/Evergreen, que son señales del motor).
_CATEGORIAS_RETIRADAS: dict[str, list[str]] = {
    "unotv": [
        "Virales", "Presidencia", "Comercial", "Reportero/Corresponsales",
        "Ciencia/Tech", "Geek/Pop", "Eventos", "Green",
    ],
}


def _crear_si_falta(
    *, nombre: str, clase: str, marca: str, ttl_dias: int = 0, es_evergreen: bool = False,
    grupo: str = "", cadencia: str = "normal", keywords: str = "", hashtags: str = "",
) -> bool:
    """Crea la etiqueta si no existe (nombre+clase+marca). True si la creó.

    `keywords` (CSV) siembra el clasificador léxico; '' deja la categoría sin auto-etiquetado.
    `hashtags` (CSV, sin '#') es el hashtag de la categoría que la etapa Keywords inyecta en sus
    piezas (para que el desglose de métricas por categoría exista también en el caption).
    """
    if repos.existe_etiqueta_nombre(nombre, clase, marca):
        return False
    repos.crear_etiqueta(
        nombre=nombre,
        clase=clase,
        marca=marca,
        keywords=keywords,
        hashtags=hashtags,
        ttl_dias=ttl_dias,
        es_evergreen=es_evergreen,
        grupo=grupo,
        cadencia=cadencia,
    )
    return True


def _grupos_gestionados(marca: str) -> set[str]:
    """Grupos que el bootstrap administra para `marca` (los del seed + el legacy 'Transversal').

    La reconciliación de `grupo` solo re-mapea una categoría cuyo grupo ACTUAL esté en este conjunto:
    así la taxonomía nueva llega a las categorías ya sembradas, pero NUNCA pisa un grupo que el equipo
    haya puesto a mano.
    """
    seed = {g for (_n, _t, _e, g, _c) in CATEGORIAS_POR_MARCA.get(marca, [])}
    return seed | {"", "Transversal"}


def _reconciliar_linea(
    *, nombre: str, marca: str, ttl_dias: int, es_evergreen: bool,
    grupo: str = "", cadencia: str = "normal", keywords: str = "", hashtags: str = "",
) -> bool:
    """Reconcilia una categoría YA existente con su definición del seed. True si tocó algo.

    La mayoría de ejes son guarded (nunca pisan una edición del equipo); el hashtag NO:
      - ttl/es_evergreen: solo si la categoría sigue en defaults (ttl 0 / es_evergreen False).
      - grupo: re-mapea a la taxonomía canónica del seed SOLO si el grupo actual lo administra el
        bootstrap (`_grupos_gestionados`); un grupo puesto a mano se respeta. Lleva el re-grupado
        (p. ej. Transversal->Actualidad, Otros deportes->Motor/NFL/…) a categorías ya sembradas.
      - cadencia: solo si sigue en 'normal'.
      - keywords: siembra el catálogo SOLO si la categoría aún no tiene keywords.
      - hashtags: se FUERZA al slug del nombre (categoría = hueco de programación = hashtag, 1:1; no es
        un campo libre). Mantiene en sincronía todas las categorías existentes.
    """
    et = repos.obtener_etiqueta_por_nombre(nombre, "categoria", marca)
    if et is None:
        return False
    cambios: dict[str, Any] = {}
    if et.get("ttl_dias", 0) == 0 and not et.get("es_evergreen", False) and (ttl_dias != 0 or es_evergreen):
        cambios["ttl_dias"] = ttl_dias
        cambios["es_evergreen"] = es_evergreen
    actual_grupo = et.get("grupo") or ""
    if actual_grupo != grupo and actual_grupo in _grupos_gestionados(marca):
        cambios["grupo"] = grupo
    if (et.get("cadencia") or "normal") == "normal" and cadencia != "normal":
        cambios["cadencia"] = cadencia
    if keywords and not (et.get("keywords") or "").strip():
        cambios["keywords"] = keywords
    if hashtags and (et.get("hashtags") or "") != hashtags:
        cambios["hashtags"] = hashtags
    if cambios:
        repos.actualizar_etiqueta(et["id"], cambios)
        return True
    return False


def inicializar_categorias() -> int:
    """Inicializa categorías (categoria) por marca y orígenes (global). Devuelve cuántas creó.

    Idempotente y tolerante a fallos por etiqueta (no aborta el resto). Pensada para el
    bootstrap del arranque.
    """
    creadas = 0
    actualizadas = 0
    for marca, lineas in CATEGORIAS_POR_MARCA.items():
        for nombre, ttl_dias, es_evergreen, grupo, cadencia in lineas:
            kw = KEYWORDS_POR_CATEGORIA.get(marca, {}).get(nombre, "")
            ht = slug_hashtag(nombre)
            try:
                if _crear_si_falta(
                    nombre=nombre, clase="categoria", marca=marca, ttl_dias=ttl_dias,
                    es_evergreen=es_evergreen, grupo=grupo, cadencia=cadencia, keywords=kw,
                    hashtags=ht,
                ):
                    creadas += 1
                else:
                    # Línea ya existe: reconcilia guarded (taxonomía + keywords/hashtags si faltan).
                    if _reconciliar_linea(
                        nombre=nombre, marca=marca,
                        ttl_dias=ttl_dias, es_evergreen=es_evergreen,
                        grupo=grupo, cadencia=cadencia, keywords=kw, hashtags=ht,
                    ):
                        actualizadas += 1
            except Exception:  # noqa: BLE001 -- una etiqueta no debe romper el resto
                _log.warning("inicializacion categorías: no se pudo crear/actualizar %s/%s", marca, nombre, exc_info=True)
    for nombre in ORIGENES_GLOBALES:
        try:
            if _crear_si_falta(nombre=nombre, clase="origen", marca=""):
                creadas += 1
        except Exception:  # noqa: BLE001
            _log.warning("inicializacion orígenes: no se pudo crear %s", nombre, exc_info=True)
    if creadas or actualizadas:
        _log.info("inicializacion categorías/orígenes: %d creadas, %d actualizadas (TTL backfill)", creadas, actualizadas)
    return creadas


def retirar_categorias_obsoletas() -> int:
    """Desactiva (activo=0) las categorías viejas que no son del plan (`_CATEGORIAS_RETIRADAS`). Devuelve
    cuántas tocó.

    Reversible y no destructivo: la etiqueta y su historial de métricas se conservan; solo deja de
    aparecer en «Plan y horarios», el selector de feeds y el catálogo (todos filtran `activas`).
    Idempotente (una etiqueta ya inactiva se salta). Best-effort.
    """
    retiradas = 0
    for marca, nombres in _CATEGORIAS_RETIRADAS.items():
        for nombre in nombres:
            try:
                et = repos.obtener_etiqueta_por_nombre(nombre, "categoria", marca)
                if et is None or not et.get("activo", True):
                    continue
                repos.actualizar_etiqueta(et["id"], {"activo": False})
                retiradas += 1
            except Exception:  # noqa: BLE001 -- una etiqueta no debe romper el resto
                _log.warning("retirar categorías: fallo en %s/%s", marca, nombre, exc_info=True)
    if retiradas:
        _log.info("retirar categorías obsoletas: %d desactivadas", retiradas)
    return retiradas


# Mapeo categoria(slug de feed) -> nombre de CATEGORÍA por marca, para el backfill de `linea_id`.
# Solo los casos 1:1 con confianza; lo no mapeado queda en catch-all "General" (linea_id='').
# Claro Sports NO está: sus feeds son GRUESOS (futbol/motor/otros-deportes) y sus categorías FINAS
# (Liga MX…); sin 1:1, se quedan en catch-all y el clasificador por pieza asigna la categoría fina.
# Fundación: sus pilares de misión usan los mismos slugs que las categorías de fuente.
_CATEGORIA_A_LINEA: dict[str, dict[str, str]] = {
    "unotv": {
        "mx": "Nacional",
        "internacional": "Internacional",
        "entretenimiento": "Entretenimiento",
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


# Claves de PLAN/FRANJA que NO son categorías sino señales del motor: se dejan TAL CUAL.
#   - 'breaking' = última hora (prioridad), '' = genérico (cualquier pieza).
#   - 'evergreen' = flujo de reciclaje (lo llena su automatismo diario).
_CLAVES_NO_LINEA: frozenset[str] = frozenset({"", "breaking", "evergreen"})

# ÚNICA fuente de verdad del nombre legible de las señales del motor (las claves de plan que
# NO son una categoría editorial). El nombre del resto de categorías —ids de categoría— lo da la BD
# (la etiqueta categoria). La consume cualquier superficie que muestre una categoría de plan
# (franjas, producción, mesa de noticias, dropdown de «Crear post»): así no se duplica el rótulo.
ETIQUETAS_CLAVE_NO_LINEA: dict[str, str] = {
    "breaking": "Última hora",
    "evergreen": "Evergreen",
}


def etiqueta_categoria(categoria: str, lineas: Mapping[str, str]) -> str:
    """Nombre legible de una categoría de plan/franja.

    - señal del motor ('breaking'/'evergreen') -> su rótulo fijo;
    - id de categoría -> su nombre (vía el mapa `lineas` id->nombre);
    - '' -> genérico (cadena vacía);
    - desconocida -> la propia clave (último recurso, nunca un id crudo si está en `lineas`).
    """
    if not categoria:
        return ""
    rotulo = ETIQUETAS_CLAVE_NO_LINEA.get(categoria)
    if rotulo is not None:
        return rotulo
    return lineas.get(categoria, categoria)


def linea_id_de_slug(marca: str, clave: str) -> str:
    """Traduce una clave de plan/franja (slug de categoría) al id de su CATEGORÍA por marca.

    Idempotente: las señales del motor ('', 'breaking', 'evergreen') y una clave que YA es un
    id de categoría (etiqueta categoria existente) se devuelven sin tocar. Un slug temático conocido
    (`_CATEGORIA_A_LINEA`) se resuelve al id de su categoría; lo no mapeable cae a '' (genérico).
    """
    clave = (clave or "").strip()
    if clave.lower() in _CLAVES_NO_LINEA:
        return clave.lower()
    try:
        ya = repos.obtener_etiqueta(clave)
        if ya is not None and ya.get("clase") == "categoria":
            return clave  # ya es un id de categoría -> idempotente
    except Exception:  # noqa: BLE001 -- resolver es best-effort
        pass
    nombre = _CATEGORIA_A_LINEA.get(marca, {}).get(clave.lower())
    if not nombre:
        return ""
    et = repos.obtener_etiqueta_por_nombre(nombre, "categoria", marca)
    return et["id"] if et else ""


def vincular_fuentes_a_lineas() -> int:
    """Backfilla `fuentes_rss.linea_id` desde el slug `categoria` por marca. Devuelve cuántas tocó.

    Idempotente: solo toca fuentes cuyo `linea_id` aún esté vacío (nunca pisa una asociación del
    equipo). Las fuentes cuya categoría no mapea a una categoría de su marca quedan en catch-all
    (linea_id=''). Requiere las categorías ya sembradas (`inicializar_categorias`).
    """
    vinculadas = 0
    try:
        fuentes = repos.listar_fuentes_rss(marca=None)
    except Exception:  # noqa: BLE001 -- el arranque no debe romper por el backfill
        _log.warning("vincular fuentes->categorías: no se pudo listar fuentes", exc_info=True)
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
            et = repos.obtener_etiqueta_por_nombre(nombre, "categoria", marca)
            if et is None:
                continue
            repos.actualizar_fuente_rss(fuente["id"], {"linea_id": et["id"]})
            vinculadas += 1
        except Exception:  # noqa: BLE001 -- una fuente no debe romper el resto
            _log.warning("vincular fuentes->categorías: fallo en %s", fuente.get("id"), exc_info=True)
    if vinculadas:
        _log.info("vincular fuentes->categorías: %d fuentes asociadas a su categoría", vinculadas)
    return vinculadas


def migrar_plan_y_franjas_a_lineas() -> int:
    """Re-clava el PLAN DIARIO y las FRANJAS del slug de categoría al id de CATEGORÍA, por marca.

    El scheduler pasa a programar por CATEGORÍA (etiqueta categoria), no por slug de feed. Esto
    reescribe las dos claves persistentes del motor a ids de categoría:
      - `KENI_PLAN_DIA::marca` (cupos "clave:n,…"): cada slug temático -> id de su categoría; las
        señales 'breaking'/'evergreen' se conservan; un cupo no mapeable se descarta.
      - `franjas_editoriales.categoria`: idem (sin update en la capa db, se borra+recrea).
    Idempotente (las claves ya en forma de id/sentinela no se tocan) y best-effort. Devuelve
    cuántas filas/claves tocó. Requiere las categorías ya sembradas. Lo no mapeable (p. ej. el cajón
    'mx' de Claro, sin categoría fina) cae a '' = genérico, sin romper la programación.
    """
    from . import ajustes

    tocadas = 0
    marcas = set(CATEGORIAS_POR_MARCA)
    try:
        franjas = repos.listar_franjas()
    except Exception:  # noqa: BLE001
        _log.warning("migrar plan/franjas: no se pudieron listar franjas", exc_info=True)
        franjas = []
    marcas |= {str(f.get("marca") or "") for f in franjas if f.get("marca")}
    # 1) Plan diario por marca.
    for marca in marcas:
        clave = f"KENI_PLAN_DIA::{marca}"
        crudo = ajustes.obtener(clave)
        if not crudo:
            continue
        partes: list[str] = []
        cambiado = False
        for seg in crudo.split(","):
            if ":" not in seg:
                continue
            k, _, n = seg.partition(":")
            nueva = linea_id_de_slug(marca, k.strip())
            if nueva != k.strip():
                cambiado = True
            if nueva:  # descarta cupos no mapeables (sin categoría)
                partes.append(f"{nueva}:{n.strip()}")
        if cambiado:
            try:
                ajustes.guardar(clave, ",".join(partes))
                tocadas += 1
            except Exception:  # noqa: BLE001
                _log.warning("migrar plan: fallo en %s", clave, exc_info=True)
    # 2) Franjas (sin update en db: borrar + recrear con la nueva categoría).
    for f in franjas:
        marca = str(f.get("marca") or "")
        nueva = linea_id_de_slug(marca, str(f.get("categoria") or ""))
        if nueva == (f.get("categoria") or ""):
            continue
        try:
            repos.borrar_franja(f["id"])
            repos.crear_franja(
                int(f.get("dia_semana") or 0), str(f.get("hora") or ""),
                marca=marca, red=str(f.get("red") or ""), categoria=nueva,
            )
            tocadas += 1
        except Exception:  # noqa: BLE001 -- una franja no debe romper el resto
            _log.warning("migrar franjas: fallo en %s", f.get("id"), exc_info=True)
    if tocadas:
        _log.info("migrar plan/franjas a categorías: %d claves/filas re-clavadas", tocadas)
    return tocadas


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
