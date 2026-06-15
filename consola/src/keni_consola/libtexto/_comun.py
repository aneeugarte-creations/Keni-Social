"""Constantes, regex, error, dataclass y helpers compartidos de la Texto.

Base sin dependencias internas: el resto de submódulos de `libtexto` se apoyan en
estos símbolos (tipos válidos, `Documento`, `TextoError`, normalizaciones básicas).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..tiempo import ahora_iso

__all__ = [
    "TIPOS",
    "CLASES",
    "SALIDAS",
    "ESTADOS",
    "ESTADO_DEFECTO",
    "ROLES_PROMPT",
    "PIPELINES",
    "_CLASES_GLOBALES",
    "_CARPETAS_GLOBALES",
    "PILARES_EDITORIALES",
    "_PAPELERA",
    "_RE_SLUG",
    "TextoError",
    "Documento",
    "_ahora_iso",
    "_slug",
    "_segmentos_validos",
    "_lista_str",
]

# --------------------------------------------------------------------------- #
# Constantes y errores                                                        #
# --------------------------------------------------------------------------- #

# Tipos de documento. El primer segmento del id (y la carpeta de primer nivel) es el tipo.
TIPOS = ("prompt", "editorial")

# Clase de un documento EDITORIAL (organiza la linea editorial y gobierna el auto-adjunto).
CLASES = ("marca", "voz", "plataforma", "tropicalizacion", "reglas")

# Tipo de SALIDA de un PROMPT: "" / "documento" = texto markdown (no crea artefactos);
# "piezas" = copy por red que se parsea y crea borradores en Parrilla (selector de redes).
SALIDAS = ("", "documento", "piezas")

# Estado del CICLO DE VIDA de un documento (cualquier tipo). Gobierna navegacion y inyeccion:
#   - `activo`    : en uso; se lista por defecto y SE INYECTA en sus pipelines.
#   - `borrador`  : trabajo en curso; se lista (filtrable) pero NO se inyecta en pipelines.
#   - `archivado` : retirado; oculto por defecto y NO se inyecta. No es papelera (sigue vivo).
ESTADOS = ("activo", "borrador", "archivado")
ESTADO_DEFECTO = "activo"

# ROL de un PROMPT base: ata un prompt al rol que un pipeline espera (redactar/verificar/idear/...).
# "" = prompt generico (lanzable a mano, no es base de ningun pipeline). Permite re-bindear
# que prompt alimenta un pipeline SIN tocar codigo (gana el doc con ese rol+pipeline).
ROLES_PROMPT = ("", "redactar", "verificar", "idear", "ilustrar")

# --------------------------------------------------------------------------- #
# Registro de PIPELINES                                                        #
# --------------------------------------------------------------------------- #
# Cada pipeline de generacion declara AQUI (no hardcodeado por todo el codigo) cual es su
# prompt base por defecto y el rol que espera. Esto convierte la "atribucion a pipeline" en
# un dato de primera clase: un editorial puede acotar en QUE pipelines entra (campo
# `pipelines`) y un prompt puede REBINDEAR cual alimenta a un pipeline (campo `rol`+`pipelines`),
# todo SIN tocar codigo. Los modulos de generacion siguen pasando su id por defecto como
# fallback, asi que el comportamiento actual se conserva si nadie configura nada.
#
#   prompt_defecto : id del prompt base que se usa si ningun doc rebindea el pipeline.
#   rol            : rol que el prompt base de este pipeline debe declarar para rebindearlo.
#   titulo/descripcion : etiquetas humanas para la UI.
PIPELINES: dict[str, dict[str, str]] = {
    "redactar": {
        "titulo": "Redactar",
        "descripcion": "Convierte una nota/clip/tendencia en copy publicable por red.",
        "prompt_defecto": "prompt/redactar",
        "rol": "redactar",
    },
    "verificar": {
        "titulo": "Verificar",
        "descripcion": "Verifica la nota de origen antes de generar copy (pipeline de contenido).",
        "prompt_defecto": "prompt/verificar",
        "rol": "verificar",
    },
    "idear": {
        "titulo": "Idear",
        "descripcion": "Propone ideas de contenido evergreen para la marca.",
        "prompt_defecto": "prompt/idear",
        "rol": "idear",
    },
}

# Clases editoriales GLOBALES: aplican a TODAS las marcas (no llevan `marcas` propias).
_CLASES_GLOBALES = frozenset({"plataforma", "tropicalizacion", "reglas"})

# Carpetas (primer segmento) cuyos documentos aplican a TODAS las marcas. La marca, si no, se
# deriva de la carpeta (la marca ES una carpeta): un doc bajo `…/<marca>/…` aplica a esa marca.
_CARPETAS_GLOBALES = frozenset({"global", "comun", "general", "todas"})

# Los 4 PILARES que toda línea editorial COMPLETA debe cubrir para una marca:
#   - `marca`           (específico de la marca): qué es la marca, su posicionamiento.
#   - `voz`             (específico de la marca): tono y estilo de redacción.
#   - `tropicalizacion` (global): adaptación a México (modismos, contexto local).
#   - `plataforma`      (global): convenciones por red (formato, límites, hábitos).
# `reglas` (global) es un pilar AUXILIAR, no obligatorio: refuerza, pero su ausencia no deja
# la línea editorial incompleta. El auto-adjunto sigue incluyendo `reglas` si existe.
PILARES_EDITORIALES = ("marca", "voz", "tropicalizacion", "plataforma")

# Dir de la papelera (oculto; no es un tipo navegable).
_PAPELERA = ".papelera"

# slug: minusculas, digitos y guiones; sin guiones colgando.
_RE_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class TextoError(RuntimeError):
    """Error de la texto con mensaje ya en espanol, apto para mostrar al usuario."""


class ConflictoEdicion(TextoError):
    """El working copy cambio debajo entre que el cliente lo cargo y guardo (concurrencia
    optimista). La API la traduce a 409 para que el frontend avise "recarga, no pises". Es
    subclase de `TextoError` (mensaje listo para el usuario), pero se captura ANTES para no
    confundirla con una validacion (400)."""


# --------------------------------------------------------------------------- #
# Dataclass                                                                    #
# --------------------------------------------------------------------------- #


@dataclass
class Documento:
    """Un documento de la texto (prompt o editorial)."""

    id: str  # ruta relativa posix sin extension, p.ej. "prompts/investigacion/resumen"
    titulo: str
    tipo: str  # prompt | editorial
    carpeta: str  # subruta bajo el tipo ("" = raiz del tipo)
    cuerpo: str
    creado: str
    actualizado: str
    # Explicación HUMANA (UI): qué es el doc y para qué sirve. NO se inyecta en ningún prompt
    # (a diferencia de `cuerpo`): separa la meta del documento del contenido que ve el agente.
    descripcion: str = ""
    clase: str = ""  # solo editorial
    marcas: list[str] = field(default_factory=list)  # solo editorial (clase marca/voz)
    # Solo prompt: "" | "documento" (texto) | "piezas" (copy por red -> borradores en Parrilla).
    salida: str = ""
    # --- Metadatos transversales (cualquier tipo) ---
    estado: str = ESTADO_DEFECTO  # activo | borrador | archivado (ver ESTADOS)
    etiquetas: list[str] = field(default_factory=list)  # tags transversales (navegacion/facetas)
    # Atribucion a PIPELINES: en que procesos participa este doc. Para EDITORIALES filtra el
    # auto-adjunto por pipeline ([] = aplica a TODOS, retrocompat). Para PROMPTS marca de que
    # pipelines es la base (junto con `rol`).
    pipelines: list[str] = field(default_factory=list)
    rol: str = ""  # solo prompt: redactar | verificar | idear | ilustrar | "" (ver ROLES_PROMPT)
    prioridad: int = 0  # orden de ensamblaje del auto-adjunto (menor = antes); empata por pilar/id

    def a_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "titulo": self.titulo,
            "descripcion": self.descripcion,
            "tipo": self.tipo,
            "carpeta": self.carpeta,
            "cuerpo": self.cuerpo,
            "creado": self.creado,
            "actualizado": self.actualizado,
            "clase": self.clase,
            "marcas": list(self.marcas),
            "salida": self.salida,
            "estado": self.estado,
            "etiquetas": list(self.etiquetas),
            "pipelines": list(self.pipelines),
            "rol": self.rol,
            "prioridad": self.prioridad,
        }


# --------------------------------------------------------------------------- #
# Helpers básicos (sin dependencias internas)                                  #
# --------------------------------------------------------------------------- #


def _ahora_iso() -> str:
    """Marca de tiempo ISO (segundos, UTC) para `creado`/`actualizado`."""
    return ahora_iso()


def _slug(texto: str) -> str:
    """Deriva un slug seguro (`[a-z0-9-]`) desde un texto humano. Lanza si queda vacio."""
    base = (texto or "").strip().lower()
    base = base.replace("ñ", "n")
    # Quita acentos comunes sin depender de unicodedata para mantenerlo simple/determinista.
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ü", "u")):
        base = base.replace(a, b)
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    if not base:
        raise TextoError("El título no produce un identificador válido.")
    return base


def _segmentos_validos(partes: list[str]) -> bool:
    """True si cada segmento es un slug valido (sin `.`/`..`/vacios)."""
    return all(p and p not in (".", "..") and bool(_RE_SLUG.match(p)) for p in partes)


def _lista_str(valor: object) -> list[str]:
    """Normaliza un campo de frontmatter a lista de strings no vacios (de-dup, orden estable)."""
    if not isinstance(valor, list):
        return []
    vistas: list[str] = []
    for v in valor:
        if isinstance(v, str) and v.strip() and v.strip() not in vistas:
            vistas.append(v.strip())
    return vistas
