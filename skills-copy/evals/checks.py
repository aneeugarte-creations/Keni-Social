#!/usr/bin/env python3
"""Bloques de verificacion compartidos por los dos niveles del eval.

Este modulo NO usa el modelo ni dependencias de terceros: es Python puro y
deterministico. Lo importan tanto las pruebas estaticas (CI) como el corredor
local basado en `claude -p`.

Dos familias de funciones:

1. Estructura del repo (CI-safe): leer frontmatter de los SKILL.md, comprobar
   que existen los ficheros de `contexto-editorial`, y contar code points igual
   que `contar.py`.
2. Propiedades del copy generado (nivel local): limites de caracteres, bloque de
   auto-verificacion, regla de la bandera con escudo, y deteccion de
   numeros/citas que no estan en la fuente.

Las funciones de la familia 2 reciben texto ya capturado (no llaman al modelo),
asi se pueden probar con fixtures y reutilizar desde el corredor local.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

# --- rutas del repo (este fichero vive en skills-copy/evals/) ---
EVALS_DIR = Path(__file__).resolve().parent
SKILLS_COPY_DIR = EVALS_DIR.parent
SKILLS_DIR = SKILLS_COPY_DIR / ".claude" / "skills"
CONTEXTO_DIR = SKILLS_COPY_DIR / "contexto-editorial"
CONTAR_PY = SKILLS_DIR / "copy-desde-nota" / "contar.py"
MARCAS_JSON_BREAKING = SKILLS_DIR / "breaking-express" / "marcas.json"

# Limite DURO del cuerpo de X/tuit. FUENTE UNICA (H3/E1): se deriva de
# `keni_shared.limites_plataforma.LIMITES["x"]`; respaldo a 280 en corrida aislada
# sin keni-shared instalado (mismo patron que el catalogo de marca).
def _limite_x() -> int:
    try:
        from keni_shared.limites_plataforma import LIMITES as _LIM
    except ImportError:
        return 280
    return _LIM.get("x") or 280


LIMITE_X = _limite_x()
LIMITE_TUIT = LIMITE_X
# Tope EDITORIAL del titulo de YouTube para el copy (recomendacion de la skill, NO
# el limite tecnico de la plataforma; ese lo cubre el guard de test_limites.py).
LIMITE_YT_TITULO = 70

# Claves de frontmatter obligatorias en cada SKILL.md.
FRONTMATTER_OBLIGATORIO = ("name", "description", "allowed-tools")

# Catalogo UNICO de marca (id canonico slug-guion -> id_metricas guion_bajo). Cada
# `id` tiene su ficha editorial `marcas/<id>.md`. El golf NO es marca: es un
# sub-vertical editorial de Claro Sports.
#
# FUENTE UNICA (H3/E1): se DERIVA de `keni_shared.marcas`, la capa mas baja del
# monorepo, que keni-metricas y la consola tambien importan. Antes este guard
# mantenia un ESPEJO hardcodeado (#82/#102); ahora se ancla a la fuente real, asi
# que las fichas y `marcas.json` se verifican contra el catalogo canonico de verdad.
#
# El runner de CI de skills instala keni-shared en el mismo venv (es Python puro,
# sin dependencias). Si por alguna razon no estuviera disponible (corrida aislada
# de skills-copy sin instalar nada), se cae a un espejo de respaldo para que el
# guard estatico siga corriendo; el caso normal usa la fuente unica.
def _cargar_marcas_id_metricas() -> dict[str, str]:
    try:
        from keni_shared import marcas as _ks_marcas
    except ImportError:
        # Respaldo: corrida aislada de skills-copy sin keni-shared instalado.
        return {
            "unotv": "unotv",
            "claro-sports": "claro_sports",
            "nacion-gamer": "nacion_gamer",
            "piso-15": "piso_15",
            "fundacion": "fundacion",
        }
    return {m.id: m.id_metricas for m in _ks_marcas.MARCAS}


MARCAS_ID_METRICAS: dict[str, str] = _cargar_marcas_id_metricas()

# Ficheros que deben existir en contexto-editorial (la skill los carga). Son los
# `id` canonicos del catalogo unico, ordenados alfabeticamente.
MARCAS_ESPERADAS = tuple(sorted(MARCAS_ID_METRICAS))
CONTEXTO_RAIZ_ESPERADO = (
    "plataformas.md",
    "tropicalizacion.md",
    "reglas-legales.md",
)


# ---------------------------------------------------------------------------
# 1) Estructura del repo (CI-safe)
# ---------------------------------------------------------------------------

def contar_code_points(texto: str) -> int:
    """Cuenta code points igual que `contar.py` (sin el salto final del heredoc).

    `contar.py` lee de stdin y, si el texto acaba en '\\n', lo quita antes de
    contar `len(...)`. Replicamos esa semantica exacta para que el eval cuente
    como la skill.
    """
    if texto.endswith("\n"):
        texto = texto[:-1]
    return len(texto)


def parsear_frontmatter(md_texto: str) -> dict[str, str] | None:
    """Extrae el frontmatter YAML simple (`clave: valor`) de un SKILL.md.

    Devuelve un dict de claves de primer nivel a su valor (como string), o None
    si no hay bloque `---\\n...\\n---` al principio. Parser minimo a proposito:
    no necesitamos PyYAML para comprobar la PRESENCIA de claves, asi el chequeo
    estatico corre en un runner de CI con solo Python.
    """
    if not md_texto.startswith("---"):
        return None
    # separa: "", frontmatter, resto
    partes = md_texto.split("---", 2)
    if len(partes) < 3:
        return None
    bloque = partes[1]
    claves: dict[str, str] = {}
    for linea in bloque.splitlines():
        if not linea.strip() or linea.lstrip().startswith("#"):
            continue
        # solo claves de primer nivel (sin indentacion) con forma "clave: valor"
        if linea[0] in (" ", "\t"):
            continue
        m = re.match(r"^([A-Za-z0-9_-]+)\s*:\s*(.*)$", linea)
        if m:
            claves[m.group(1)] = m.group(2).strip()
    return claves


def listar_skills() -> list[Path]:
    """Rutas a cada SKILL.md bajo .claude/skills/*/SKILL.md."""
    return sorted(SKILLS_DIR.glob("*/SKILL.md"))


def faltan_claves_frontmatter(md_texto: str) -> list[str]:
    """Devuelve las claves obligatorias que faltan (o estan vacias). [] = ok."""
    fm = parsear_frontmatter(md_texto)
    if fm is None:
        return list(FRONTMATTER_OBLIGATORIO)
    return [k for k in FRONTMATTER_OBLIGATORIO if not fm.get(k)]


def ficheros_contexto_faltantes() -> list[str]:
    """Lista de ficheros esperados en contexto-editorial que no existen. [] = ok."""
    faltan: list[str] = []
    for nombre in CONTEXTO_RAIZ_ESPERADO:
        if not (CONTEXTO_DIR / nombre).is_file():
            faltan.append(nombre)
    for marca in MARCAS_ESPERADAS:
        ruta = CONTEXTO_DIR / "marcas" / f"{marca}.md"
        if not ruta.is_file():
            faltan.append(f"marcas/{marca}.md")
    if not (CONTEXTO_DIR / "voces" / "_plantilla.md").is_file():
        faltan.append("voces/_plantilla.md")
    return faltan


def errores_identidad_fichas_marca() -> list[str]:
    """#102: cada ficha `marcas/<id>.md` declara su identidad UNICA y coincide.

    Comprueba que el frontmatter de cada ficha tiene `id` (= nombre del fichero),
    `etiqueta` y un `id_metricas` que cuadra con la tabla canonica. [] = ok.
    """
    errores: list[str] = []
    for marca in MARCAS_ESPERADAS:
        ruta = CONTEXTO_DIR / "marcas" / f"{marca}.md"
        if not ruta.is_file():
            continue  # lo reporta ficheros_contexto_faltantes()
        fm = parsear_frontmatter(ruta.read_text(encoding="utf-8"))
        if fm is None:
            errores.append(f"{marca}.md: sin frontmatter de identidad")
            continue
        if fm.get("id") != marca:
            errores.append(f"{marca}.md: id='{fm.get('id')}' != nombre de fichero")
        if not fm.get("etiqueta"):
            errores.append(f"{marca}.md: falta 'etiqueta'")
        esperado = MARCAS_ID_METRICAS[marca]
        if fm.get("id_metricas") != esperado:
            errores.append(
                f"{marca}.md: id_metricas='{fm.get('id_metricas')}' != '{esperado}' (catalogo canonico)"
            )
    return errores


def errores_identidad_marcas_json() -> list[str]:
    """#102: las claves de breaking-express/marcas.json son ids canonicos y su
    `id_metricas` coincide con la tabla canonica. [] = ok.

    Requiere que `marcas.json` exista (lo crea breaking-express). Solo valida la
    seccion `marcas` (los tokens de diseño). Las claves son un SUBCONJUNTO de las
    marcas canonicas: breaking solo tiene tokens para algunas, no inventa ids.
    """
    import json

    errores: list[str] = []
    if not MARCAS_JSON_BREAKING.is_file():
        return ["breaking-express/marcas.json no existe"]
    try:
        datos = json.loads(MARCAS_JSON_BREAKING.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"marcas.json no parsea: {e}"]
    bloque = datos.get("marcas", {})
    if not isinstance(bloque, dict) or not bloque:
        return ["marcas.json sin seccion 'marcas'"]
    for clave, tokens in bloque.items():
        if clave not in MARCAS_ID_METRICAS:
            errores.append(f"marcas.json: clave '{clave}' no es una marca canonica")
            continue
        esperado = MARCAS_ID_METRICAS[clave]
        if tokens.get("id_metricas") != esperado:
            errores.append(
                f"marcas.json[{clave}]: id_metricas='{tokens.get('id_metricas')}' != '{esperado}'"
            )
    return errores


# ---------------------------------------------------------------------------
# 2) Propiedades del copy generado (nivel local)
# ---------------------------------------------------------------------------

@dataclass
class ResultadoCheck:
    """Resultado de una comprobacion individual sobre el copy generado."""

    nombre: str
    ok: bool
    detalle: str = ""


@dataclass
class InformeCopy:
    """Agrega los resultados de todas las comprobaciones de un output."""

    resultados: list[ResultadoCheck] = field(default_factory=list)

    def add(self, nombre: str, ok: bool, detalle: str = "") -> None:
        self.resultados.append(ResultadoCheck(nombre, ok, detalle))

    @property
    def ok(self) -> bool:
        return all(r.ok for r in self.resultados)

    def fallos(self) -> list[ResultadoCheck]:
        return [r for r in self.resultados if not r.ok]

    def texto(self) -> str:
        lineas = []
        for r in self.resultados:
            marca = "OK  " if r.ok else "FALLA"
            sufijo = f" — {r.detalle}" if r.detalle else ""
            lineas.append(f"[{marca}] {r.nombre}{sufijo}")
        return "\n".join(lineas)


# --- deteccion del bloque de auto-verificacion ---

_SIMBOLOS_VERIF = ("✅", "⚠️", "❌")


def tiene_bloque_verificacion(salida: str) -> bool:
    """True si la salida trae el bloque de auto-verificacion obligatorio.

    Requiere: al menos un simbolo (✅/⚠️/❌) Y un veredicto explicito. Las skills
    cierran con "Veredicto:" / "LISTO PARA APROBAR" / "LISTO TRAS VERIFICAR".
    """
    tiene_simbolo = any(s in salida for s in _SIMBOLOS_VERIF)
    bajo = salida.lower()
    tiene_veredicto = (
        "veredicto" in bajo
        or "listo para aprobar" in bajo
        or "listo tras verificar" in bajo
    )
    return tiene_simbolo and tiene_veredicto


# --- regla legal: bandera de Mexico con escudo ---

def viola_bandera_con_escudo(salida: str) -> bool:
    """True si la salida PROPONE bandera de Mexico con escudo (prohibido).

    reglas-legales.md: la bandera con escudo nacional esta prohibida en contenido
    comercial/editorial; la bandera SIN escudo si se puede. Heuristica: marcamos
    violacion si aparecen juntas, en una ventana corta, "bandera" y
    "escudo" SIN una negacion cercana ("sin escudo", "no ... escudo", "prohib").

    Es deteccion conservadora para un gate; un humano confirma. No pretende
    entender semantica, solo cazar la combinacion peligrosa.
    """
    bajo = _normaliza(salida)
    for m in re.finditer(r"bandera", bajo):
        ventana = bajo[m.start(): m.start() + 60]
        if "escudo" not in ventana:
            continue
        # negaciones/avisos que indican que NO se esta proponiendo el recurso
        if "sin escudo" in ventana:
            continue
        if re.search(r"no\s+\w*\s*escudo", ventana):
            continue
        # contexto de la propia regla / verificacion (se esta advirtiendo, no proponiendo)
        contexto = bajo[max(0, m.start() - 40): m.start() + 80]
        if any(t in contexto for t in ("prohib", "no usar", "no propong", "evitar", "regla", "verific", "❌", "⚠️")):
            continue
        return True
    return False


def _normaliza(texto: str) -> str:
    """Minusculas y sin acentos, para comparaciones robustas."""
    nfkd = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


# --- tropicalizacion: deteccion de espanolismos (es-ES) ---

# Lista CERRADA de terminos inequivocamente peninsulares. La forma guardada es la
# ya normalizada (minusculas, sin acentos) para casar contra `_normaliza`.
#
# Decision (conservadora, pocos falsos positivos):
#   - Solo entran terminos que en es-MX NO se usan (o suenan a "de fuera"):
#     vale, vosotros, os, coche, ordenador, movil, zumo, gilipollas, flipar,
#     chaval, molar, currar, guay.
#   - Se EXCLUYEN a proposito los ambiguos, porque en MX tambien existen con otro
#     sentido y dispararian falsos positivos:
#       * "piso"  -> en MX = suelo (no solo vivienda).
#       * "tio"   -> en MX = pariente (uso literal muy comun).
#       * "coger" -> en MX es de uso (aunque con carga vulgar); reescribir es
#                    criterio editorial, no un error inequivoco de origen.
#     Estos se documentan aqui y se tratan en tropicalizacion.md, no en el gate.
ESPANOLISMOS = (
    "vale",
    "vosotros",
    "os",
    "coche",
    "ordenador",
    "movil",
    "zumo",
    "gilipollas",
    "flipar",
    "chaval",
    "molar",
    "currar",
    "guay",
)

# Terminos ambiguos: existen en es-MX con otro sentido, por eso NO disparan el
# gate (se documentan en tropicalizacion.md para revision humana).
ESPANOLISMOS_AMBIGUOS = ("piso", "tio", "coger")

_RE_PALABRA = re.compile(r"[a-z]+")


def detecta_espanolismos(texto: str) -> list[str]:
    """Devuelve los espanolismos (es-ES) crudos hallados en el texto. [] = ok.

    Conservador a proposito: solo busca palabras de la lista CERRADA
    `ESPANOLISMOS` (terminos inequivocamente peninsulares). No incluye los
    ambiguos (piso/tio/coger), que en MX existen con otro sentido y darian falsos
    positivos; esos se tratan como criterio editorial en tropicalizacion.md.

    - Insensible a acentos y mayusculas (usa `_normaliza`, igual que el resto de
      checks).
    - Casa por PALABRA COMPLETA (tokeniza), asi "valeroso" no marca "vale" ni
      "sosa"/"sosos" marcan "os".
    - Preserva el orden de aparicion y no repite el mismo termino.
    """
    norm = _normaliza(texto)
    objetivo = set(ESPANOLISMOS)
    encontrados: list[str] = []
    vistos: set[str] = set()
    for palabra in _RE_PALABRA.findall(norm):
        if palabra in objetivo and palabra not in vistos:
            vistos.add(palabra)
            encontrados.append(palabra)
    return encontrados


# --- limites de caracteres por plataforma ---

# Secciones de plataforma en la salida. La skill produce "una variante por
# plataforma"; aqui localizamos el texto de X, los tuits del hilo y el titulo de
# YouTube para contarlos. Los encabezados son flexibles (## X, **X/Twitter**...).

_RE_TUIT = re.compile(r"^\s*(\d+)\s*/\s*\d+\b", re.MULTILINE)


def extraer_secciones(salida: str) -> dict[str, str]:
    """Trocea la salida por encabezados de plataforma.

    Devuelve un dict {clave_normalizada: texto_de_la_seccion}. Las claves usan la
    primera palabra reconocida del encabezado (x, instagram, facebook, tiktok,
    youtube, hilo, carrusel). Robusto a `## `, `### `, `**...**`, `# `.
    """
    # corta el bloque de auto-verificacion: las secciones de plataforma no deben
    # absorberlo (si no, el ultimo post/tuit/titulo mediria texto de la verif.).
    cuerpo = _quita_bloque_verificacion(salida)
    encabezado = re.compile(
        r"^\s{0,3}(?:#{1,4}\s+|\*\*\s*)?"  # marcador opcional de heading
        r"(X(?:\s*/\s*Twitter)?|Twitter|Instagram|Facebook|TikTok|YouTube|Hilo|Carrusel|Carousel)"
        r"\b",
        re.IGNORECASE | re.MULTILINE,
    )
    matches = list(encabezado.finditer(cuerpo))
    secciones: dict[str, str] = {}
    for i, m in enumerate(matches):
        inicio = m.end()
        fin = matches[i + 1].start() if i + 1 < len(matches) else len(cuerpo)
        crudo = m.group(1).lower()
        if crudo.startswith("x") or crudo == "twitter":
            clave = "x"
        elif crudo.startswith("carrou") or crudo.startswith("carrus") or crudo.startswith("carou"):
            # "carrusel" (es), "carrousel" (fr) y "carousel" (en) -> "carrusel"
            clave = "carrusel"
        else:
            clave = crudo
        # no machaques una seccion ya capturada (quedate con la primera)
        secciones.setdefault(clave, cuerpo[inicio:fin].strip())
    return secciones


def _limpia_linea_copy(linea: str) -> str:
    """Quita bullets/markdown de bloque al principio de una linea de copy."""
    return re.sub(r"^\s*(?:[-*>]\s+|\d+[.)]\s+)", "", linea).strip()


def excede_limite_x(salida: str) -> list[str]:
    """Devuelve mensajes por cada variante de X que exceda 280. [] = ok.

    Cuenta la primera linea no vacia de la seccion X (el post). Si no hay seccion
    X identificable, devuelve [] (no se puede afirmar violacion).
    """
    secciones = extraer_secciones(salida)
    problemas: list[str] = []
    if "x" in secciones:
        post = _primera_linea_copy(secciones["x"])
        if post is not None:
            n = contar_code_points(post)
            if n > LIMITE_X:
                problemas.append(f"post X = {n} cp (> {LIMITE_X})")
    return problemas


def excede_limite_tuits(salida: str) -> list[str]:
    """Devuelve mensajes por cada tuit de hilo `n/n` que exceda 280. [] = ok.

    El hilo vive en su propia seccion ("Hilo") o, si no hay, inline en la de X.
    Cada tuit va de su marcador `n/n` hasta el siguiente marcador o una linea en
    blanco (asi un tuit no absorbe texto que no le pertenece).
    """
    secciones = extraer_secciones(salida)
    base = secciones.get("hilo") or secciones.get("x") or ""
    problemas: list[str] = []
    marcadores = list(_RE_TUIT.finditer(base))
    for i, m in enumerate(marcadores):
        inicio = m.start()
        sig = marcadores[i + 1].start() if i + 1 < len(marcadores) else len(base)
        # corta tambien en la primera linea en blanco dentro del tramo del tuit
        corte_blanco = base.find("\n\n", inicio)
        if corte_blanco != -1 and corte_blanco < sig:
            sig = corte_blanco
        tuit = base[inicio:sig].strip()
        n = contar_code_points(tuit)
        if n > LIMITE_TUIT:
            problemas.append(f"tuit {m.group(0).strip()} = {n} cp (> {LIMITE_TUIT})")
    return problemas


def excede_limite_youtube(salida: str) -> list[str]:
    """Devuelve mensaje si el titulo de YouTube excede 70. [] = ok.

    Busca una linea "Titulo: ..." dentro de la seccion de YouTube; si no, usa la
    primera linea de copy de esa seccion.
    """
    secciones = extraer_secciones(salida)
    problemas: list[str] = []
    if "youtube" not in secciones:
        return problemas
    seccion = secciones["youtube"]
    titulo = None
    m = re.search(r"^\s*(?:[-*]\s*)?(?:\*\*)?\s*t[ií]tulo\s*(?:\*\*)?\s*[:\-]\s*(.+)$",
                  seccion, re.IGNORECASE | re.MULTILINE)
    if m:
        titulo = _limpia_linea_copy(m.group(1)).strip(" *")
    else:
        titulo = _primera_linea_copy(seccion)
    if titulo is not None:
        n = contar_code_points(titulo)
        if n > LIMITE_YT_TITULO:
            problemas.append(f"titulo YouTube = {n} cp (> {LIMITE_YT_TITULO})")
    return problemas


def _primera_linea_copy(seccion: str) -> str | None:
    """Primera linea con contenido de copy de una seccion (saltando metadatos)."""
    for linea in seccion.splitlines():
        limpia = _limpia_linea_copy(linea)
        if not limpia:
            continue
        # salta lineas de metadatos tipo "Caracteres: 123" / "Conteo: ..."
        if re.match(r"^\s*(?:\*\*)?\s*(caracteres|conteo|chars|cp)\b", limpia, re.IGNORECASE):
            continue
        return limpia
    return None


# --- fidelidad: numeros y citas que no esten en la fuente ---

_RE_NUMERO = re.compile(r"\d[\d.,]*")

# Numeros que aparecen por formato/estructura, no como dato del copy:
#   - numeracion de tuits/slides: "1/5", "2/5"
#   - contadores: "Caracteres: 230"
# Los excluimos para no marcar falsos positivos.

# --- normalizacion de MAGNITUDES (anti-invencion robusto) ---------------------
#
# El check ya no compara solo cadenas de digitos: compara el VALOR NUMERICO
# canonico de cada cifra. Asi:
#   - "40 millones" (fuente) == "40,000,000" / "40.000.000" (copy)  -> NO falso positivo
#   - "cuarenta millones" inventado (no esta en la fuente)           -> SI se caza
# Para eso normalizamos separadores de miles y aplicamos el multiplicador de la
# palabra de magnitud que sigue al numero ("mil", "millon/millones", etc.), y
# parseamos numeros escritos EN PALABRAS (cardinales en es-MX hasta millones).

# Multiplicadores de magnitud (forma ya normalizada: minusculas, sin acentos).
_MAGNITUDES: dict[str, int] = {
    "mil": 1_000,
    "millon": 1_000_000,
    "millones": 1_000_000,
    "millardo": 1_000_000_000,
    "millardos": 1_000_000_000,
}

# Cardinales en palabra (es-MX). Mapa CERRADO y conservador: cubre lo habitual
# en una nota de noticias (unidades, decenas, centenas y sus combinaciones con
# "y"). La forma guardada es la normalizada (sin acentos).
_UNIDADES: dict[str, int] = {
    "cero": 0, "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4,
    "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
    "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15,
    "dieciseis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19,
    "veinte": 20, "veintiun": 21, "veintiuno": 21, "veintiuna": 21,
    "veintidos": 22, "veintitres": 23, "veinticuatro": 24, "veinticinco": 25,
    "veintiseis": 26, "veintisiete": 27, "veintiocho": 28, "veintinueve": 29,
}
_DECENAS: dict[str, int] = {
    "treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60,
    "setenta": 70, "ochenta": 80, "noventa": 90,
}
_CENTENAS: dict[str, int] = {
    "cien": 100, "ciento": 100, "doscientos": 200, "doscientas": 200,
    "trescientos": 300, "trescientas": 300, "cuatrocientos": 400,
    "cuatrocientas": 400, "quinientos": 500, "quinientas": 500,
    "seiscientos": 600, "seiscientas": 600, "setecientos": 700,
    "setecientas": 700, "ochocientos": 800, "ochocientas": 800,
    "novecientos": 900, "novecientas": 900,
}
# Palabras que pueden formar parte de un numero en palabras (incluye conector "y").
_PALABRAS_NUMERO = set(_UNIDADES) | set(_DECENAS) | set(_CENTENAS) | set(_MAGNITUDES) | {"y"}

_RE_PALABRA_NUM = re.compile(r"[a-z]+")


def _valor_grupo_palabras(tokens: list[str]) -> int | None:
    """Suma un grupo de palabras-numero (sin magnitudes) a su valor. None si vacio.

    Soporta combinaciones es-MX: "cuarenta", "cuarenta y cinco", "ciento veinte",
    "doscientos treinta y cuatro". Ignora el conector "y".
    """
    total = 0
    visto = False
    for t in tokens:
        if t == "y":
            continue
        if t in _CENTENAS:
            total += _CENTENAS[t]
            visto = True
        elif t in _DECENAS:
            total += _DECENAS[t]
            visto = True
        elif t in _UNIDADES:
            total += _UNIDADES[t]
            visto = True
        else:
            return None
    return total if visto else None


def _numeros_en_palabras(texto: str) -> list[int]:
    """Valores de los numeros escritos EN PALABRAS dentro del texto (es-MX).

    Recorre las palabras y agrupa secuencias de cardinales (+ conector "y" +
    palabra de magnitud final tipo "millones"/"mil"). "cuarenta millones" -> 40000000;
    "cinco" -> 5; "ciento veinte mil" -> 120000. Conservador: solo reconoce el
    vocabulario del mapa cerrado.
    """
    palabras = _RE_PALABRA_NUM.findall(_normaliza(texto))
    valores: list[int] = []
    i = 0
    n = len(palabras)
    while i < n:
        if palabras[i] not in _PALABRAS_NUMERO or palabras[i] in ("y", *_MAGNITUDES):
            i += 1
            continue
        # acumula el grupo de cardinales
        grupo: list[str] = []
        while i < n and palabras[i] in _PALABRAS_NUMERO and palabras[i] not in _MAGNITUDES:
            grupo.append(palabras[i])
            i += 1
        # quita un conector "y" colgando al final del grupo
        while grupo and grupo[-1] == "y":
            grupo.pop()
        base = _valor_grupo_palabras(grupo)
        if base is None:
            continue
        # magnitud que sigue al grupo ("millones", "mil"...)
        magnitud = 1
        if i < n and palabras[i] in _MAGNITUDES:
            magnitud = _MAGNITUDES[palabras[i]]
            i += 1
        # "un"/"uno"/"una" sueltos son ARTICULO, no dato ("una negociacion"): solo
        # cuentan como numero si llevan magnitud ("un millon") o forman compuesto.
        if magnitud == 1 and grupo in (["un"], ["uno"], ["una"]):
            continue
        valores.append(base * magnitud)
    return valores


def _magnitud_tras(texto: str, fin: int) -> int:
    """Multiplicador de la palabra de magnitud que sigue a una cifra (1 si no hay).

    `fin` es el indice donde termina el numero en `texto`. Salta espacios y, si la
    primera palabra siguiente es una magnitud ("millones", "mil"...), devuelve su
    multiplicador. Asi "40 millones" -> 1_000_000.
    """
    resto = texto[fin:]
    m = re.match(r"\s+([a-zA-ZáéíóúñÁÉÍÓÚÑ]+)", resto)
    if not m:
        return 1
    return _MAGNITUDES.get(_normaliza(m.group(1)), 1)


def _valor_cifra(tok: str, magnitud: int) -> int | None:
    """Valor canonico de una cifra en digitos aplicando su magnitud. None si vacia.

    Normaliza separadores de miles (`.` `,` y espacios) antes de multiplicar, de
    modo que "40,000,000" y "40.000.000" valen lo mismo que "40 millones".
    """
    d = _digitos(tok)
    if not d:
        return None
    return int(d) * magnitud


def _valores_fuente(fuente: str) -> set[int]:
    """Conjunto de valores numericos canonicos presentes en la fuente.

    Incluye cifras en digitos (con su magnitud, p.ej. "40 millones"=40000000) y
    numeros escritos en palabras. Tambien guarda el valor "crudo" sin magnitud
    (int(digitos)) para no marcar falsos positivos cuando el copy repite la cifra
    base sin la palabra de magnitud.
    """
    valores: set[int] = set()
    for m in _RE_NUMERO.finditer(fuente):
        crudo = int(_digitos(m.group())) if _digitos(m.group()) else None
        if crudo is None:
            continue
        valores.add(crudo)
        valores.add(crudo * _magnitud_tras(fuente, m.end()))
    valores.update(_numeros_en_palabras(fuente))
    return valores


def numeros_inventados(salida: str, fuente: str, *, ignorar: set[str] | None = None) -> list[str]:
    """Numeros en el copy que NO aparecen en la fuente. [] = ok.

    Recorre la salida (excluyendo el bloque de auto-verificacion y las lineas de
    conteo/numeracion) y comprueba que el VALOR de cada numero "de contenido"
    exista en la fuente. La comparacion es por valor canonico, no por cadena de
    digitos: normaliza separadores de miles (`.` `,`), aplica la palabra de
    magnitud que sigue ("mil", "millon/millones") y parsea numeros escritos EN
    PALABRAS ("cuarenta millones", "cinco"). Asi:
      - fuente "40 millones" vs copy "40,000,000"  -> NO es invencion (mismo valor);
      - copy "cuarenta millones" sin estar en la fuente -> SI se caza.
    `ignorar` recibe cadenas de digitos (compatibilidad): se ignora el numero cuyo
    `_digitos` coincide. Conservador: pensado para cazar cifras claramente ausentes.
    """
    ignorar = ignorar or set()
    fuente_valores = _valores_fuente(fuente)
    cuerpo = _quita_bloque_verificacion(salida)
    problemas: list[str] = []
    vistos: set[int] = set()
    for linea in cuerpo.splitlines():
        if _es_linea_meta(linea):
            continue
        # quita numeracion de hilo/slide al principio ("1/5", "2/7")
        sin_num = re.sub(r"^\s*\d+\s*/\s*\d+", "", linea)
        # 1) cifras en digitos (con su magnitud)
        for m in _RE_NUMERO.finditer(sin_num):
            tok = m.group()
            d = _digitos(tok)
            if not d or d in ignorar:
                continue
            valor = int(d) * _magnitud_tras(sin_num, m.end())
            if valor in vistos:
                continue
            if valor not in fuente_valores:
                vistos.add(valor)
                problemas.append(f'numero "{tok}" no esta en la fuente')
        # 2) numeros escritos en palabras
        for valor in _numeros_en_palabras(sin_num):
            if valor in vistos:
                continue
            if valor not in fuente_valores:
                vistos.add(valor)
                problemas.append(f'numero "{_etiqueta_valor(valor)}" no esta en la fuente')
    return problemas


def _etiqueta_valor(valor: int) -> str:
    """Texto legible para reportar un numero en palabras inventado."""
    return f"{valor:,}".replace(",", ".") + " (en palabras)"


def citas_inventadas(salida: str, fuente: str) -> list[str]:
    """Citas entrecomilladas en el copy cuyo texto no este en la fuente. [] = ok.

    Extrae fragmentos entre comillas tipograficas (« » “ ” ‟) o rectas y verifica
    que un nucleo significativo de la cita aparezca en la fuente (normalizado).
    Conservador: solo marca citas de >=3 palabras (las cortas suelen ser enfasis,
    no atribucion textual).
    """
    fuente_norm = _normaliza(fuente)
    cuerpo = _quita_bloque_verificacion(salida)
    problemas: list[str] = []
    for cita in _extrae_citas(cuerpo):
        palabras = [p for p in re.findall(r"\w+", cita) if p]
        if len(palabras) < 3:
            continue
        nucleo = _normaliza(" ".join(palabras))
        if nucleo and nucleo not in fuente_norm:
            recorte = cita if len(cita) <= 50 else cita[:47] + "..."
            problemas.append(f'cita "{recorte}" no esta en la fuente')
    return problemas


_RE_CITAS = re.compile(r"[«“‟\"]([^«»“”‟\"]{3,})[»”\"]")


def _extrae_citas(texto: str) -> list[str]:
    return [c.strip() for c in _RE_CITAS.findall(texto)]


def _digitos(tok: str) -> str:
    return re.sub(r"\D", "", tok)


def _es_linea_meta(linea: str) -> bool:
    """True si la linea es metadato (conteo, numeracion, encabezado de seccion)."""
    norm = linea.strip().lower()
    if not norm:
        return True
    if re.match(r"^\s*(?:\*\*)?\s*(caracteres|conteo|chars|cp|count)\b", norm):
        return True
    return False


def _quita_bloque_verificacion(salida: str) -> str:
    """Devuelve la salida sin el bloque de auto-verificacion final.

    El bloque empieza en el primer encabezado/linea que contiene
    "auto-verificacion" o "verificacion" (con simbolos ✅/⚠️/❌ o "veredicto").
    Asi no marcamos como "inventados" los numeros/citas que la propia
    verificacion enumera al revisarse.
    """
    bajo = _normaliza(salida)
    m = re.search(r"(auto-?verificacion|verificaci|veredicto)", bajo)
    if m:
        # retrocede al inicio de la linea (asi no dejamos colgando el "## " del
        # encabezado de la verificacion en la seccion anterior)
        inicio_linea = salida.rfind("\n", 0, m.start()) + 1
        return salida[:inicio_linea].rstrip()
    return salida


# ---------------------------------------------------------------------------
# 3) Consistencia del propio SKILL.md (CI-safe, sobre el texto del .md)
# ---------------------------------------------------------------------------
#
# Estos checks NO miran el copy generado, sino el CONTRATO escrito en cada
# SKILL.md: que una skill que produce copy DOCUMENTE su bloque de
# veredicto+leyenda (los 3 símbolos ✅/⚠️/❌) y que CARGUE el contexto editorial.
# Reciben el texto del SKILL.md (no llaman al modelo): son testeables con
# fixtures y se corren en CI igual que el resto de la familia estática.
#
# Criterio de aplicabilidad (¿esta skill "produce copy"?):
#   Las 7 skills de copy (copy-desde-nota, clip-a-copy, nota-a-formato,
#   resumen-tendencia, publica-preview, responde-comentarios,
#   calendario-editorial) abren con el bloque veredicto+leyenda de 3 símbolos y
#   cargan contexto-editorial. `revisa-imagen` es un CASO APARTE: no produce
#   copy, REVISA imágenes y su dictamen es **APTA / NO APTA** (no el de copy).
#   La señal que lo distingue es ese vocabulario APTA/NO APTA, ausente en las 7
#   skills de copy. Por eso `produce_copy()` excluye explícitamente la skill cuyo
#   veredicto es APTA/NO APTA: el check de consistencia de copy NO le aplica.

_RE_VERDICTO_3_SIMBOLOS = re.compile(r"✅.*⚠️.*❌")
_RE_APTA = re.compile(r"\bNO\s+APTA\b|\bAPTA\b", re.IGNORECASE)


def tiene_bloque_veredicto_leyenda(texto_skill_md: str) -> bool:
    """True si el SKILL.md documenta el bloque veredicto+leyenda de copy.

    Exige las DOS piezas que abren la salida de las skills de copy:
      (a) una línea de veredicto con los 3 símbolos juntos (✅ … ⚠️ … ❌), y
      (b) una línea de **leyenda** que explique esos símbolos ("Leyenda:").
    """
    tiene_simbolos = bool(_RE_VERDICTO_3_SIMBOLOS.search(texto_skill_md))
    tiene_leyenda = "leyenda:" in texto_skill_md.lower()
    return tiene_simbolos and tiene_leyenda


def carga_contexto_editorial(texto_skill_md: str) -> bool:
    """True si el SKILL.md carga el contexto editorial (lo lee con Read).

    Heurística simple sobre el contrato escrito: una skill que produce copy
    referencia archivos bajo `contexto-editorial/` (reglas-legales, plataformas,
    marcas, etc.). No comprueba que los ficheros existan (eso es
    `ficheros_contexto_faltantes`), solo que la skill DIGA que los carga.
    """
    return "contexto-editorial/" in texto_skill_md


def usa_veredicto_apta(texto_skill_md: str) -> bool:
    """True si el dictamen del SKILL.md es APTA / NO APTA (caso revisa-imagen).

    Es la señal que separa la skill de REVISIÓN DE IMAGEN (cuyo veredicto es
    APTA/NO APTA) de las skills que producen copy (cuyo veredicto es
    LISTO PARA APROBAR / REVISAR / NO PUBLICAR). Solo `revisa-imagen` usa este
    vocabulario; por eso sirve de discriminante.
    """
    return bool(_RE_APTA.search(texto_skill_md))


def produce_copy(texto_skill_md: str) -> bool:
    """True si el SKILL.md es de una skill que PRODUCE/PREVISUALIZA copy.

    Criterio: documenta el bloque veredicto+leyenda de copy Y NO usa el dictamen
    APTA/NO APTA. Así quedan dentro las 7 skills de copy y FUERA `revisa-imagen`
    (que sí trae veredicto+leyenda pero su dictamen es APTA/NO APTA: es revisión
    de imagen, no producción de copy). El check de consistencia de copy solo
    aplica a las skills para las que `produce_copy` es True.
    """
    return tiene_bloque_veredicto_leyenda(texto_skill_md) and not usa_veredicto_apta(texto_skill_md)


def produce_copy_con_veredicto(texto_skill_md: str) -> bool:
    """True si una skill de COPY cumple el contrato de consistencia.

    Para una skill que produce copy (`produce_copy` True), exige las dos
    propiedades del contrato:
      (a) bloque veredicto+leyenda con los 3 símbolos ✅/⚠️/❌, y
      (b) carga del contexto editorial (`contexto-editorial/...`).

    Devuelve **False** tanto si una skill de copy INCUMPLE el contrato como si la
    skill NO produce copy (p. ej. `revisa-imagen`, cuyo veredicto es APTA/NO APTA
    y a la que este check NO aplica). Para distinguir "no aplica" de "incumple",
    filtra antes con `produce_copy(...)`.
    """
    if not produce_copy(texto_skill_md):
        return False
    return tiene_bloque_veredicto_leyenda(texto_skill_md) and carga_contexto_editorial(texto_skill_md)


def evaluar_copy(salida: str, fuente: str, *, ignorar_numeros: set[str] | None = None) -> InformeCopy:
    """Corre TODAS las propiedades deterministicas sobre un copy generado.

    `salida`  = texto que produjo la skill (capturado del corredor local).
    `fuente`  = texto de la(s) nota(s)/transcripcion de entrada (de ejemplos/).
    """
    inf = InformeCopy()

    p_x = excede_limite_x(salida)
    inf.add("X <= 280", not p_x, "; ".join(p_x))

    p_t = excede_limite_tuits(salida)
    inf.add("cada tuit del hilo <= 280", not p_t, "; ".join(p_t))

    p_y = excede_limite_youtube(salida)
    inf.add("titulo YouTube <= 70", not p_y, "; ".join(p_y))

    inf.add(
        "bloque de auto-verificacion presente (simbolo + veredicto)",
        tiene_bloque_verificacion(salida),
        "" if tiene_bloque_verificacion(salida) else "falta ✅/⚠️/❌ o veredicto",
    )

    viola = viola_bandera_con_escudo(salida)
    inf.add("sin bandera con escudo", not viola,
            "propone bandera con escudo (prohibido)" if viola else "")

    p_n = numeros_inventados(salida, fuente, ignorar=ignorar_numeros)
    inf.add("sin numeros ausentes de la fuente", not p_n, "; ".join(p_n))

    p_c = citas_inventadas(salida, fuente)
    inf.add("sin citas ausentes de la fuente", not p_c, "; ".join(p_c))

    return inf
