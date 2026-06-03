"""Parrilla del dia: clasificador 13+6 y jerarquizador de temas del Radar.

Logica PURA y determinista para la herramienta de produccion diaria de UnoTV / AMX:
dado un conjunto de temas (como los que produce el Radar), divide en:
  - `posteos`    (objetivo 13): contenido visual/inmediato → clip, galeria, infografia, normal.
  - `editorial`  (objetivo 6):  contenido con "carnita" (contexto, morbo, seguimiento) →
                                 video editorial de fondo, mas elaborado.

Y jerarquiza los 19 por importancia/orden de publicacion con `puntuar_tema`.

CRITERIO EDITORIAL (Angel, UnoTV):
  - Editorial: tiene contexto, morbo, historia que contar, actualizacion de seguimiento,
    analisis. Necesita tiempo de produccion.
  - Posteo: lo visual, lo inmediato, lo que se puede publicar rapido sin mucho contexto.
    Se subclasifica segun el potencial del material:
      - clip:       hay video / hay que recortar (accion, declaraciones, imagenes en movimiento).
      - galeria:    hay fotografias de un evento / coleccion visual.
      - infografia: datos, estadisticas, lista, ranking → se explica mejor en grafico.
      - normal:     texto + 1 imagen, lo que no encaja en los anteriores.

PUREZA / INYECCION:
  - `puntuar_tema` recibe `ahora` (datetime) como parametro en vez de leer el reloj
    directamente, para que sea completamente testeable.
  - Las funciones de clasificacion son deterministicas: dada la misma entrada, misma salida.
  - No hacen llamadas de red, no leen disco.

SEÑALES USADAS EN EL SCORING:
  1. Viralidad (senal):    trafico de Google Trends / conteo de búsquedas.
  2. Relevancia Mexico:    palabras clave del titulo / fuentes mexicanas.
  3. Novedad / frescura:   si el tema tiene senales de haber surgido en las ultimas horas.
  4. Impacto editorial:    longitud de la señal de impacto (cuantas notas explican el tema).
  5. Multi-red:            aparece en mas de una fuente/red (mayor cobertura = mas peso).
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from .radar import Tema

# --------------------------------------------------------------------------- #
# Configuracion: cuotas objetivo                                               #
# --------------------------------------------------------------------------- #

CUOTA_POSTEOS = 13      # objetivo de piezas de posteo por dia
CUOTA_EDITORIAL = 6     # objetivo de videos editoriales por dia
CUOTA_TOTAL = CUOTA_POSTEOS + CUOTA_EDITORIAL  # 19

# Subtipos de posteo
SUBTIPO_CLIP = "clip"
SUBTIPO_GALERIA = "galeria"
SUBTIPO_INFOGRAFIA = "infografia"
SUBTIPO_NORMAL = "normal"

SUBTIPOS_POSTEO = (SUBTIPO_CLIP, SUBTIPO_GALERIA, SUBTIPO_INFOGRAFIA, SUBTIPO_NORMAL)

# --------------------------------------------------------------------------- #
# Vocabulario para la clasificacion por palabras clave                         #
# --------------------------------------------------------------------------- #

# Palabras que sugieren material en VIDEO (clip).
_PALABRAS_CLIP = frozenset({
    "video", "clip", "declaracion", "declaraciones", "discurso", "conferencia",
    "rueda de prensa", "entrevista", "transmision", "en vivo", "live", "accidente",
    "explosion", "incendio", "pelea", "balacera", "tiroteo", "detención", "arresto",
    "captura", "operativo", "gol", "anotacion", "partido", "carrera", "regresa",
    "cantante", "concierto", "musico", "actuacion",
})

# Palabras que sugieren material FOTOGRAFICO / galeria.
_PALABRAS_GALERIA = frozenset({
    "fotos", "galeria", "imagenes", "fotografias", "boda", "evento", "red carpet",
    "alfombra roja", "desfile", "fashion", "moda", "coleccion", "exposicion",
    "inauguracion", "tour", "visita", "gira", "premiere",
})

# Palabras que sugieren datos / estadisticas / infografia.
_PALABRAS_INFOGRAFIA = frozenset({
    "datos", "estadisticas", "cifras", "ranking", "lista", "top 10", "porcentaje",
    "encuesta", "resultados", "estudio", "reporte", "informe", "comparacion",
    "evolucion", "historico", "record", "maximo", "minimo", "tendencia",
    "proyeccion", "pronostico", "presupuesto", "pib", "inflacion", "crecimiento",
})

# Palabras que apuntan a un tema con contexto editorial (editorial, no posteo).
_PALABRAS_EDITORIAL = frozenset({
    "analisis", "opinion", "columna", "editorial", "investigacion", "contextualiza",
    "explicamos", "explica", "claves", "por que", "como funciona", "historia de",
    "antecedentes", "seguimiento", "lo que debes saber", "balance", "impacto",
    "consecuencias", "reflexion", "debate", "critica", "reportaje",
    "corruption", "corrupcion", "escandalo", "fraude", "desfalco",
    "crisis", "conflicto", "guerra", "disputa", "tension",
    "desaparicion", "feminicidio", "violencia", "violaciones",
    "acusacion", "denuncia", "juicio", "sentencia", "veredicto",
    "acuerdo", "tratado", "negociacion", "cumbre", "diplomacia",
})

# Palabras / fuentes que suman relevancia MEXICO.
_PALABRAS_MX = frozenset({
    "mexico", "méxico", "cdmx", "ciudad de mexico", "edomex", "jalisco", "monterrey",
    "guadalajara", "puebla", "tijuana", "oaxaca", "chiapas", "veracruz", "yucatan",
    "guerrero", "sinaloa", "michoacan", "tamaulipas", "coahuila", "chihuahua",
    "amlo", "sheinbaum", "morena", "pan", "pri", "pvem", "mc", "pt",
    "senado", "camara de diputados", "diputados", "senadores",
    "liga mx", "america", "chivas", "cruz azul", "pumas", "tigres", "rayados",
    "pemex", "imss", "issste", "sep", "semar", "sedena", "sspc",
    "narco", "cartel", "plaza", "fentanilo",
    "banco de mexico", "banxico", "inegi", "sat", "hacienda",
    "mx", "mexicano", "mexicana", "mexicanos", "mexicanas",
})

# Fuentes editoriales conocidas con alta relevancia MX
_FUENTES_MX = frozenset({
    "el universal", "reforma", "excelsior", "milenio", "proceso",
    "animal politico", "sin embargo", "el financiero", "expansion",
    "cnn en espanol", "televisa", "tv azteca", "unoticias", "unomexico",
    "notimex", "ntv", "informador", "el heraldo", "la jornada",
})


# --------------------------------------------------------------------------- #
# Modelo de salida                                                              #
# --------------------------------------------------------------------------- #

@dataclass
class TemaClasificado:
    """Tema con clasificacion (posteo/editorial), subtipo, score y razon del orden."""

    tema: Tema
    tipo: str          # "posteo" | "editorial"
    subtipo: str       # clip/galeria/infografia/normal (solo para posteo; "" para editorial)
    score: float       # puntuacion de jerarquia (mayor = mas importante)
    orden: int         # posicion 1-based en la parrilla del dia (1 = mas importante)
    razon: str         # texto en español explicando el score

    def a_dict(self) -> dict[str, Any]:
        return {
            "titulo": self.tema.titulo,
            "tipo": self.tipo,
            "subtipo": self.subtipo,
            "score": round(self.score, 2),
            "orden": self.orden,
            "razon": self.razon,
            "senal": self.tema.senal,
            "senal_texto": self.tema.senal_texto,
            "por_que": self.tema.por_que,
            "redes": sorted(self.tema.redes),
            "fuentes": sorted(self.tema.fuentes),
            "enlaces": [e.a_dict() for e in self.tema.enlaces],
        }


@dataclass
class ParrillaDia:
    """Resultado de la clasificacion y jerarquizacion de temas para un dia."""

    posteos: list[TemaClasificado]      # hasta CUOTA_POSTEOS (13 objetivo)
    editorial: list[TemaClasificado]    # hasta CUOTA_EDITORIAL (6 objetivo)
    sobrantes: list[TemaClasificado]    # temas que superan la cuota (igualmente jerarquizados)
    total_entrada: int                  # cuantos temas entraron (ya filtrados por marca)
    contexto: str                       # geo / contexto del scoring
    fuera_foco: int = 0                 # temas descartados por NO ser de la marca (0 sin marca)

    def a_dict(self) -> dict[str, Any]:
        return {
            "posteos": [t.a_dict() for t in self.posteos],
            "editorial": [t.a_dict() for t in self.editorial],
            "sobrantes": [t.a_dict() for t in self.sobrantes],
            "total_entrada": self.total_entrada,
            "total_posteos": len(self.posteos),
            "total_editorial": len(self.editorial),
            "total_sobrantes": len(self.sobrantes),
            "total_fuera_foco": self.fuera_foco,
            "contexto": self.contexto,
            "cuota_posteos": CUOTA_POSTEOS,
            "cuota_editorial": CUOTA_EDITORIAL,
        }


# --------------------------------------------------------------------------- #
# Helpers internos                                                              #
# --------------------------------------------------------------------------- #

_RE_TOKENS = re.compile(r"[a-záéíóúñü0-9]+", re.IGNORECASE)


def _tokens(texto: str) -> set[str]:
    """Tokens en minusculas de un texto (palabras y numeros)."""
    return {m.group().lower() for m in _RE_TOKENS.finditer(texto or "")}


def _contiene_alguna(tokens: set[str], vocabulario: frozenset[str]) -> bool:
    """True si alguna palabra del vocabulario esta en los tokens."""
    for termino in vocabulario:
        # Soporte para frases (mas de un token): busca por inclusion de subcadena
        if " " in termino:
            # termino multi-palabra: chequeo de subcadena en el texto completo
            pass
        elif termino in tokens:
            return True
    return False


def _contiene_frase(texto_lower: str, vocabulario: frozenset[str]) -> bool:
    """True si alguna entrada del vocabulario (token o frase) esta en el texto."""
    toks = _tokens(texto_lower)
    for termino in vocabulario:
        if " " in termino:
            if termino in texto_lower:
                return True
        elif termino in toks:
            return True
    return False


# --------------------------------------------------------------------------- #
# Clasificacion editorial: posteo vs editorial                                  #
# --------------------------------------------------------------------------- #

def _clasificar_tipo(tema: Tema) -> tuple[str, str]:
    """Devuelve (tipo, subtipo) para un tema.

    Tipo: "editorial" si el tema tiene palabras de analisis/profundidad/seguimiento;
          "posteo" en el resto de casos.
    Subtipo (solo para posteo): clip / galeria / infografia / normal.
    """
    texto = (tema.titulo + " " + tema.por_que).lower()

    # ---- Clasificacion editorial -----------------------------------------
    # Umbral bajo: si hay señal editorial en el titulo o en el por_que, es editorial.
    if _contiene_frase(texto, _PALABRAS_EDITORIAL):
        return "editorial", ""

    # Ademas, temas con muchos enlaces (4+) sugieren mayor profundidad informativa.
    if len(tema.enlaces) >= 4:
        return "editorial", ""

    # ---- Subtipo de posteo -----------------------------------------------
    if _contiene_frase(texto, _PALABRAS_CLIP):
        return "posteo", SUBTIPO_CLIP
    if _contiene_frase(texto, _PALABRAS_GALERIA):
        return "posteo", SUBTIPO_GALERIA
    if _contiene_frase(texto, _PALABRAS_INFOGRAFIA):
        return "posteo", SUBTIPO_INFOGRAFIA
    return "posteo", SUBTIPO_NORMAL


# --------------------------------------------------------------------------- #
# Scoring: puntuar_tema (PURA, inyecta ahora)                                  #
# --------------------------------------------------------------------------- #

# Pesos de las senales en el score final (todos sumados = base maxima 1.0 aprox).
_PESO_VIRALIDAD = 0.40
_PESO_MX = 0.25
_PESO_NOVEDAD = 0.15
_PESO_IMPACTO = 0.10
_PESO_MULTI_RED = 0.10

# Umbral de trafico para considerar un tema "viral alto" (1K búsquedas).
_TRAFICO_ALTO = 1_000
# Maximo de trafico para normalizar (1M: por encima satura en 1.0).
_TRAFICO_MAX = 1_000_000


def _score_viralidad(tema: Tema) -> float:
    """Componente de viralidad normalizada [0, 1]."""
    if tema.senal <= 0:
        return 0.0
    # Escala logaritmica: 1K -> ~0.5, 1M -> 1.0
    return min(1.0, math.log10(max(1, tema.senal)) / math.log10(_TRAFICO_MAX))


def _score_mx(tema: Tema) -> float:
    """Componente de relevancia Mexico [0, 1]."""
    texto = (tema.titulo + " " + tema.por_que).lower()
    if _contiene_frase(texto, _PALABRAS_MX):
        return 1.0
    # Revisar fuentes tambien
    fuentes_lower = " ".join(f.lower() for f in tema.fuentes)
    if _contiene_frase(fuentes_lower, _FUENTES_MX):
        return 0.8
    return 0.0


def _score_novedad(tema: Tema) -> float:
    """Componente de novedad: señal de trafico reciente [0, 1].

    Como el radar no expone timestamps de items, usamos la señal de trafico como
    proxy: temas con trafico ALTO son tendencias del momento (recientes). Temas sin
    trafico (RSS editoriales) se consideran presentes pero sin penalizacion.
    """
    if tema.senal > _TRAFICO_ALTO:
        return 1.0
    if tema.senal > 0:
        return 0.5
    return 0.3   # RSS editorial: reciente pero sin conteo (señal cualitativa)


def _score_impacto(tema: Tema) -> float:
    """Componente de impacto editorial: cuantos medios/notas cubren el tema [0, 1]."""
    n_enlaces = len(tema.enlaces)
    if n_enlaces == 0:
        return 0.0
    # Logistica suave: 1 enlace -> ~0.5, 3+ -> se acerca a 1.0
    return min(1.0, n_enlaces / (n_enlaces + 2))


def _score_multi_red(tema: Tema) -> float:
    """Componente de cobertura multi-red [0, 1]: aparece en mas de una red/fuente."""
    n = len(tema.fuentes) + len(tema.redes)
    if n <= 1:
        return 0.0
    if n == 2:
        return 0.5
    return min(1.0, (n - 1) / 4)


def _sin_acentos(texto: str) -> str:
    """Minusculas sin acentos (NFD + descarta diacriticos): 'Fútbol' → 'futbol'.

    Las palabras clave de marca se escriben sin acentos; los titulos reales del Radar
    SI los llevan ('fútbol', 'elección'), asi que normalizamos el texto antes de matchear.
    """
    desc = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in desc if unicodedata.category(c) != "Mn")


def _score_marca(tema: Tema, palabras_marca: frozenset[str]) -> float:
    """Relevancia para la MARCA activa [0, 1] segun sus palabras clave.

    1.0 si el tema es CURADO (de una fuente de la marca) o una palabra de la marca esta
    en el TITULO; 0.6 si esta en el cuerpo (por_que / titulos de enlaces); 0.0 si no.
    Sin palabras → 0.0 (no aplica). El texto se normaliza sin acentos para que 'fútbol'
    matchee la keyword 'futbol'.
    """
    if not palabras_marca:
        return 0.0
    # Tema de una fuente propia de la marca: en el foco por definicion (no se keyword-filtra).
    if tema.curado:
        return 1.0
    if _contiene_frase(_sin_acentos(tema.titulo), palabras_marca):
        return 1.0
    cuerpo = _sin_acentos(tema.por_que + " " + " ".join(e.titulo for e in tema.enlaces))
    if _contiene_frase(cuerpo, palabras_marca):
        return 0.6
    return 0.0


def tema_en_foco(tema: Tema, palabras_marca: frozenset[str]) -> bool:
    """True si el tema entra en el FOCO de la marca (alguna palabra clave aparece).

    Con `palabras_marca` vacio devuelve False (no hay foco que aplicar): por eso el
    filtrado en `armar_parrilla`/Radar solo se hace cuando hay marca activa.
    """
    return _score_marca(tema, palabras_marca) > 0.0


def puntuar_tema(
    tema: Tema,
    contexto: str = "MX",
    palabras_marca: frozenset[str] = frozenset(),
) -> tuple[float, str]:
    """Funcion PURA: devuelve (score, razon) para un tema dado su contexto.

    `score` en [0, 1]: combina viralidad, relevancia MX, novedad, impacto y multi-red.
    Si se pasan `palabras_marca` (la investigacion es POR MARCA), el score se inclina
    hacia la relevancia de la marca: `0.6·relevancia_marca + 0.4·newsworthiness`, de
    modo que el Plan del dia de una marca priorice SUS temas, no lo viral en general.
    `razon` es una frase en español que explica el score (transparencia editorial).

    La funcion es deterministica: misma entrada → mismo output.
    No lee el reloj ni hace llamadas de red.
    """
    s_viral = _score_viralidad(tema)
    s_mx = _score_mx(tema)
    s_novedad = _score_novedad(tema)
    s_impacto = _score_impacto(tema)
    s_multi = _score_multi_red(tema)

    base = (
        _PESO_VIRALIDAD * s_viral
        + _PESO_MX * s_mx
        + _PESO_NOVEDAD * s_novedad
        + _PESO_IMPACTO * s_impacto
        + _PESO_MULTI_RED * s_multi
    )

    # Relevancia de marca: con marca activa con vocabulario, domina el score (el Plan
    # del dia es de la marca). Sin marca, el score es el general (base).
    s_marca = _score_marca(tema, palabras_marca)
    score = (0.6 * s_marca + 0.4 * base) if palabras_marca else base

    # Construir la razon en español
    partes: list[str] = []
    if palabras_marca:
        if s_marca >= 1.0:
            partes.append("en el foco de la marca")
        elif s_marca > 0:
            partes.append("relacionado con la marca")
        else:
            partes.append("fuera del foco de la marca")
    if s_viral > 0:
        nivel = "alta" if s_viral >= 0.6 else "media"
        partes.append(f"viralidad {nivel} ({tema.senal_texto or str(tema.senal)} búsquedas)")
    if s_mx > 0:
        partes.append("relevante para México")
    if s_novedad >= 0.8:
        partes.append("tendencia del momento")
    if s_impacto >= 0.5:
        partes.append(f"{len(tema.enlaces)} fuente(s) cubriéndolo")
    if s_multi > 0:
        partes.append(f"presente en {len(tema.redes)} red(es)")

    if partes:
        razon = "; ".join(partes) + f". Score: {round(score, 2)}"
    else:
        razon = f"señal cualitativa (presencia editorial). Score: {round(score, 2)}"

    return score, razon


# --------------------------------------------------------------------------- #
# Clasificacion + jerarquizacion: armar_parrilla                               #
# --------------------------------------------------------------------------- #

def armar_parrilla(
    temas: list[Tema],
    contexto: str = "MX",
    palabras_marca: frozenset[str] = frozenset(),
) -> ParrillaDia:
    """Clasifica y jerarquiza una lista de temas del Radar en la Parrilla del dia.

    1. Puntua todos los temas con `puntuar_tema`.
    2. Clasifica cada uno como posteo (+ subtipo) o editorial.
    3. Ordena ambas listas por score descendente.
    4. Asigna orden global 1-based: primero editorial (por importancia), luego posteos.
    5. Limita a las cuotas (13 posteos / 6 editorial); el resto va a `sobrantes`.

    Si hay `palabras_marca` (marca activa), la parrilla se FILTRA a los temas en el
    foco de la marca: los que no contienen ninguna palabra clave NO entran al plan
    (se reportan como `fuera_foco`). El Plan del dia de una marca muestra LO SUYO.

    Devuelve una `ParrillaDia` con los tres grupos ya ordenados y con metadata.
    """
    # Filtro por marca: solo los temas en el foco de la marca entran al plan.
    fuera_foco = 0
    if palabras_marca:
        en_foco = [t for t in temas if tema_en_foco(t, palabras_marca)]
        fuera_foco = len(temas) - len(en_foco)
        temas = en_foco

    if not temas:
        return ParrillaDia(
            posteos=[],
            editorial=[],
            sobrantes=[],
            total_entrada=0,
            contexto=contexto,
            fuera_foco=fuera_foco,
        )

    # --- 1. Puntuar y clasificar todos los temas ---
    clasificados: list[TemaClasificado] = []
    for tema in temas:
        score, razon = puntuar_tema(tema, contexto, palabras_marca)
        tipo, subtipo = _clasificar_tipo(tema)
        clasificados.append(
            TemaClasificado(
                tema=tema,
                tipo=tipo,
                subtipo=subtipo,
                score=score,
                orden=0,       # se rellena abajo
                razon=razon,
            )
        )

    # --- 2. Separar y ordenar por score desc ---
    edits = sorted([t for t in clasificados if t.tipo == "editorial"], key=lambda t: -t.score)
    posts = sorted([t for t in clasificados if t.tipo == "posteo"], key=lambda t: -t.score)

    # --- 3. Aplicar cuotas ---
    edits_parrilla = edits[:CUOTA_EDITORIAL]
    posts_parrilla = posts[:CUOTA_POSTEOS]
    sobrantes = edits[CUOTA_EDITORIAL:] + posts[CUOTA_POSTEOS:]

    # --- 4. Asignar orden global: editorial primero (son los mas elaborados), luego posteos ---
    # Ordenamos el global por score descendente entre los 19 para asignar el orden de publicacion.
    parrilla_completa = sorted(edits_parrilla + posts_parrilla, key=lambda t: -t.score)
    for i, t in enumerate(parrilla_completa, start=1):
        t.orden = i
    for i, t in enumerate(sobrantes, start=CUOTA_TOTAL + 1):
        t.orden = i

    # Re-separar con ordenes asignados
    edits_final = sorted([t for t in parrilla_completa if t.tipo == "editorial"], key=lambda t: t.orden)
    posts_final = sorted([t for t in parrilla_completa if t.tipo == "posteo"], key=lambda t: t.orden)

    return ParrillaDia(
        posteos=posts_final,
        editorial=edits_final,
        sobrantes=sorted(sobrantes, key=lambda t: t.orden),
        total_entrada=len(temas),
        contexto=contexto,
        fuera_foco=fuera_foco,
    )
