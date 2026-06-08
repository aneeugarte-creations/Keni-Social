"""Almacen UNICO de la Texto: PROMPTS + LINEA EDITORIAL (files-as-truth).

Reemplaza la autoria de "skills" (carpetas `SKILL.md` + `keni.yaml` con formularios) por un
almacen plano de DOCUMENTOS markdown editables con el mismo editor a pantalla completa. Cada
documento es un `.md` con frontmatter YAML + cuerpo (el cuerpo ES el contenido: el prompt, o
la pieza editorial). Conviven las DOS piezas clave del proyecto, distinguidas por `tipo`:

  - `prompt`    : una instruccion que se LANZA sobre contenido/areas (motor de generacion).
  - `editorial` : la LINEA EDITORIAL (voz de marca, plataformas, tropicalizacion, reglas).
                  Se ADJUNTA a un prompt al lanzarlo (auto por marca + ajustable).

LAYOUT EN DISCO (la jerarquia de carpetas ES la navegacion):

    <raiz>/
      prompts/<carpeta...>/<slug>.md          # tipo: prompt
      editorial/<carpeta...>/<slug>.md         # tipo: editorial
      .papelera/<id-aplanado>__<ts>.md         # borrados (restaurables)

El `id` de un documento es su ruta relativa POSIX bajo `<raiz>` SIN extension, p.ej.
`prompts/investigacion/resumen` o `editorial/marcas/unotv`. Es estable y legible.

FRONTMATTER (minimo; todo lo demas es el cuerpo):
    titulo, tipo, carpeta, creado, actualizado
    (solo editorial) clase ∈ {marca,voz,plataforma,tropicalizacion,reglas}, marcas: [ids]

SEGURIDAD: el id se sanea contra traversal (segmentos `[a-z0-9-]`, primer segmento = tipo
valido, sin `..`); las rutas se resuelven y se comprueba que caen ESTRICTAMENTE dentro de
`raiz()`; las escrituras son ATOMICAS (`io_atomico`). Todo error sale en espanol.

La raiz se sobreescribe con `KENI_TEXTO_DIR` (los tests lo apuntan a un tmp).
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import yaml

from . import config, rutas, versionado
from .io_atomico import escribir_atomico

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

# ROL de un PROMPT base: ata un prompt al rol que un pipeline espera (copy/qa/evergreen/...).
# "" = prompt generico (lanzable a mano, no es base de ningun pipeline). Permite re-bindear
# que prompt alimenta un pipeline SIN tocar codigo (gana el doc con ese rol+pipeline).
ROLES_PROMPT = ("", "copy", "qa", "evergreen", "arte")

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
    "copy": {
        "titulo": "Copy desde nota",
        "descripcion": "Convierte una nota/clip/tendencia en copy publicable por red.",
        "prompt_defecto": "prompt/copy-desde-nota",
        "rol": "copy",
    },
    "qa": {
        "titulo": "Criba editorial de la fuente",
        "descripcion": "Verifica la nota de origen antes de generar copy (pipeline de contenido).",
        "prompt_defecto": "prompt/qa-editorial",
        "rol": "qa",
    },
    "evergreen": {
        "titulo": "Ideas evergreen (EVERGREEN)",
        "descripcion": "Propone ideas de contenido evergreen para la marca.",
        "prompt_defecto": "prompt/brainstorming-evergreen",
        "rol": "evergreen",
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
    rol: str = ""  # solo prompt: copy | qa | evergreen | arte | "" (ver ROLES_PROMPT)
    prioridad: int = 0  # orden de ensamblaje del auto-adjunto (menor = antes); empata por pilar/id

    def a_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "titulo": self.titulo,
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
# Localizacion de la raiz + saneo de ids                                       #
# --------------------------------------------------------------------------- #


def raiz() -> Path:
    """Dir raiz del almacen de la texto.

    Preferencia: env `KENI_TEXTO_DIR` (lo usan los tests con un tmp) ->
    `rutas.dir_config()/texto` (bajo `KENI_DATA_DIR` en contenedor; `~/.config/
    keni-social/texto` en local).
    """
    override = config.texto_dir()
    if override is not None:
        return override
    return rutas.dir_config() / "texto"


def _ahora_iso() -> str:
    """Marca de tiempo ISO (segundos, UTC) para `creado`/`actualizado`."""
    return datetime.now(UTC).isoformat(timespec="seconds")


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


def _ruta_de_id(doc_id: str) -> Path:
    """Resuelve `<raiz>/<id>.md` garantizando que cae ESTRICTAMENTE dentro de la raiz.

    El id debe ser una ruta POSIX relativa cuyo PRIMER segmento es un `tipo` valido y el
    resto son slugs. Lanza `TextoError` si el id es invalido o se escapa de la raiz.
    """
    if not isinstance(doc_id, str) or not doc_id.strip():
        raise TextoError("Identificador de documento no válido.")
    partes = doc_id.strip().strip("/").split("/")
    if len(partes) < 2 or partes[0] not in TIPOS or not _segmentos_validos(partes):
        raise TextoError("Identificador de documento no válido.")
    base = raiz().resolve()
    destino = base.joinpath(*partes).with_suffix(".md").resolve()
    # Defensa en profundidad: el destino debe colgar de la raiz (nunca de `..`).
    if base not in destino.parents:
        raise TextoError("Ruta de documento fuera del almacén.")
    return destino


def _id_de_ruta(ruta: Path) -> str:
    """Id (ruta relativa posix sin extension) de un `.md` bajo la raiz."""
    rel = ruta.resolve().relative_to(raiz().resolve())
    return rel.with_suffix("").as_posix()


def _carpeta_relativa(tipo: str, carpeta: str) -> list[str]:
    """Valida y trocea `carpeta` (subruta bajo el tipo); [] para la raiz del tipo."""
    carpeta = (carpeta or "").strip().strip("/")
    if not carpeta:
        return []
    partes = carpeta.split("/")
    if not _segmentos_validos(partes):
        raise TextoError("Nombre de carpeta no válido (usa minúsculas, dígitos y guiones).")
    return partes


# --------------------------------------------------------------------------- #
# Lectura / escritura de un documento (.md con frontmatter)                     #
# --------------------------------------------------------------------------- #


def _parsear(texto: str) -> tuple[dict[str, object], str]:
    """Separa frontmatter YAML (entre `---`) y cuerpo. Tolerante: sin frontmatter -> ({}, texto)."""
    if texto.startswith("---"):
        # Busca el cierre del bloque (segunda linea `---`).
        partes = texto.split("\n")
        cierre = None
        for i in range(1, len(partes)):
            if partes[i].strip() == "---":
                cierre = i
                break
        if cierre is not None:
            crudo = "\n".join(partes[1:cierre])
            cuerpo = "\n".join(partes[cierre + 1 :])
            try:
                meta = yaml.safe_load(crudo)
            except yaml.YAMLError:
                meta = None
            if isinstance(meta, dict):
                return meta, cuerpo.lstrip("\n")
    return {}, texto


def _serializar(doc: Documento) -> str:
    """Documento -> texto `.md` (frontmatter estable + cuerpo)."""
    meta: dict[str, object] = {
        "titulo": doc.titulo,
        "tipo": doc.tipo,
        "carpeta": doc.carpeta,
        "creado": doc.creado,
        "actualizado": doc.actualizado,
    }
    if doc.tipo == "editorial":
        meta["clase"] = doc.clase
        meta["marcas"] = list(doc.marcas)
    elif doc.tipo == "prompt":
        if doc.salida:
            meta["salida"] = doc.salida
        if doc.rol:
            meta["rol"] = doc.rol
    # Metadatos transversales: solo se escriben si NO son el defecto, para no ensuciar el
    # frontmatter de los documentos existentes (que siguen leyendose con los defaults).
    if doc.estado and doc.estado != ESTADO_DEFECTO:
        meta["estado"] = doc.estado
    if doc.etiquetas:
        meta["etiquetas"] = list(doc.etiquetas)
    if doc.pipelines:
        meta["pipelines"] = list(doc.pipelines)
    if doc.prioridad:
        meta["prioridad"] = doc.prioridad
    cabecera = yaml.safe_dump(meta, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return f"---\n{cabecera}---\n\n{doc.cuerpo.rstrip()}\n"


def _leer(ruta: Path) -> Documento | None:
    """Lee un `.md` como Documento; None si no existe / corrupto. El id se DERIVA de la ruta."""
    try:
        texto = ruta.read_text(encoding="utf-8")
    except OSError:
        return None
    meta, cuerpo = _parsear(texto)
    try:
        doc_id = _id_de_ruta(ruta)
    except (ValueError, TextoError):
        return None
    partes = doc_id.split("/")
    tipo = partes[0]
    if tipo not in TIPOS:
        return None
    # `carpeta` se reconstruye de la ruta (fuente de verdad), no del frontmatter (que puede
    # quedar viejo tras un mv manual). El frontmatter aporta titulo/fechas/clase/marcas.
    carpeta = "/".join(partes[1:-1])
    titulo = meta.get("titulo")
    titulo = titulo.strip() if isinstance(titulo, str) and titulo.strip() else partes[-1].replace("-", " ")
    clase = meta.get("clase")
    clase = clase if isinstance(clase, str) and clase in CLASES else ""
    marcas_crudas = meta.get("marcas")
    marcas = [m for m in marcas_crudas if isinstance(m, str)] if isinstance(marcas_crudas, list) else []
    creado = meta.get("creado") if isinstance(meta.get("creado"), str) else ""
    actualizado = meta.get("actualizado") if isinstance(meta.get("actualizado"), str) else creado
    salida = meta.get("salida")
    salida = salida if isinstance(salida, str) and salida in SALIDAS else ""
    estado = meta.get("estado")
    estado = estado if isinstance(estado, str) and estado in ESTADOS else ESTADO_DEFECTO
    etiquetas = _lista_str(meta.get("etiquetas"))
    pipelines = _lista_str(meta.get("pipelines"))
    rol = meta.get("rol")
    rol = rol if tipo == "prompt" and isinstance(rol, str) and rol in ROLES_PROMPT else ""
    prioridad = meta.get("prioridad")
    prioridad = prioridad if isinstance(prioridad, int) and not isinstance(prioridad, bool) else 0
    return Documento(
        id=doc_id, titulo=titulo, tipo=tipo, carpeta=carpeta, cuerpo=cuerpo,
        creado=creado, actualizado=actualizado, clase=clase, marcas=marcas, salida=salida,
        estado=estado, etiquetas=etiquetas, pipelines=pipelines, rol=rol, prioridad=prioridad,
    )


def _lista_str(valor: object) -> list[str]:
    """Normaliza un campo de frontmatter a lista de strings no vacios (de-dup, orden estable)."""
    if not isinstance(valor, list):
        return []
    vistas: list[str] = []
    for v in valor:
        if isinstance(v, str) and v.strip() and v.strip() not in vistas:
            vistas.append(v.strip())
    return vistas


# --------------------------------------------------------------------------- #
# Listado / lectura                                                            #
# --------------------------------------------------------------------------- #


def listar(
    tipo: str | None = None,
    carpeta: str | None = None,
    q: str | None = None,
    *,
    estado: str | None = None,
    etiqueta: str | None = None,
    marca: str | None = None,
    clase: str | None = None,
    pipeline: str | None = None,
) -> list[Documento]:
    """Documentos del almacen, filtrables por multiples facetas. Excluye la papelera.

    Facetas (todas AND, todas opcionales):
      - `tipo`     : prompt | editorial.
      - `carpeta`  : prefijo de carpeta (jerarquia clasica de navegacion).
      - `q`        : busqueda por subcadena en titulo + cuerpo.
      - `estado`   : activo | borrador | archivado (sin filtro -> todos).
      - `etiqueta` : tag transversal (debe estar en `etiquetas`).
      - `marca`    : id de marca (editoriales cuyo `marcas` la incluye, o globales).
      - `clase`    : clase editorial.
      - `pipeline` : participa en ese pipeline (`pipelines` lo incluye, o esta vacio).

    Ordena por (tipo, id). Tolerante: un `.md` corrupto se SALTA.
    """
    base = raiz()
    if not base.is_dir():
        return []
    docs: list[Documento] = []
    tipos = (tipo,) if tipo in TIPOS else TIPOS
    for t in tipos:
        sub = base / t
        if not sub.is_dir():
            continue
        for ruta in sub.rglob("*.md"):
            doc = _leer(ruta)
            if doc is None:
                continue
            if carpeta is not None and not _coincide_carpeta(doc.carpeta, carpeta):
                continue
            if q and not _coincide_busqueda(doc, q):
                continue
            if estado and doc.estado != estado:
                continue
            if etiqueta and etiqueta not in doc.etiquetas:
                continue
            if clase and doc.clase != clase:
                continue
            if marca and not (marca in doc.marcas or doc.clase in _CLASES_GLOBALES):
                continue
            if pipeline and doc.pipelines and pipeline not in doc.pipelines:
                continue
            docs.append(doc)
    docs.sort(key=lambda d: (d.tipo, d.id))
    return docs


def _coincide_carpeta(carpeta_doc: str, filtro: str) -> bool:
    """True si `carpeta_doc` es exactamente `filtro` o cuelga de el (prefijo de carpeta)."""
    filtro = (filtro or "").strip().strip("/")
    if not filtro:
        return True
    return carpeta_doc == filtro or carpeta_doc.startswith(filtro + "/")


def _coincide_busqueda(doc: Documento, q: str) -> bool:
    """Busqueda simple por subcadena (case-insensitive) en titulo + cuerpo."""
    aguja = q.strip().lower()
    return aguja in doc.titulo.lower() or aguja in doc.cuerpo.lower()


def obtener(doc_id: str) -> Documento | None:
    """Un documento por id, o None si no existe / id invalido / corrupto."""
    try:
        ruta = _ruta_de_id(doc_id)
    except TextoError:
        return None
    if not ruta.is_file():
        return None
    return _leer(ruta)


def listar_carpetas(tipo: str | None = None) -> list[str]:
    """Subcarpetas existentes (ids de carpeta `tipo/sub...`) que contienen documentos."""
    base = raiz()
    if not base.is_dir():
        return []
    carpetas: set[str] = set()
    tipos = (tipo,) if tipo in TIPOS else TIPOS
    for t in tipos:
        sub = base / t
        if not sub.is_dir():
            continue
        for ruta in sub.rglob("*.md"):
            doc = _leer(ruta)
            if doc is not None and doc.carpeta:
                # Registra la carpeta y todas sus ancestras (para un arbol completo).
                partes = doc.carpeta.split("/")
                for i in range(1, len(partes) + 1):
                    carpetas.add(f"{t}/" + "/".join(partes[:i]))
    return sorted(carpetas)


# --------------------------------------------------------------------------- #
# Creacion / actualizacion / borrado                                           #
# --------------------------------------------------------------------------- #


def _id_unico(tipo: str, partes_carpeta: list[str], slug: str) -> tuple[str, Path]:
    """Devuelve (id, ruta) libres para `tipo/carpeta/slug`, anadiendo `-2`, `-3`… si choca."""
    base = raiz()
    candidato = slug
    n = 2
    while True:
        ruta = base.joinpath(tipo, *partes_carpeta, candidato + ".md")
        if not ruta.exists():
            doc_id = ruta.resolve().relative_to(base.resolve()).with_suffix("").as_posix()
            return doc_id, ruta
        candidato = f"{slug}-{n}"
        n += 1


def crear(
    titulo: str,
    *,
    tipo: str = "prompt",
    carpeta: str = "",
    cuerpo: str = "",
    clase: str = "",
    marcas: list[str] | None = None,
    estado: str | None = None,
    etiquetas: list[str] | None = None,
    pipelines: list[str] | None = None,
    rol: str | None = None,
    prioridad: int | None = None,
) -> Documento:
    """Crea un documento nuevo (prompt o editorial) y lo escribe (atomico). Devuelve el doc."""
    if not isinstance(titulo, str) or not titulo.strip():
        raise TextoError("El título no puede estar vacío.")
    if tipo not in TIPOS:
        raise TextoError("El tipo debe ser 'prompt' o 'editorial'.")
    clase = _validar_clase(tipo, clase)
    partes = _carpeta_relativa(tipo, carpeta)
    slug = _slug(titulo)
    doc_id, ruta = _id_unico(tipo, partes, slug)
    ahora = _ahora_iso()
    doc = Documento(
        id=doc_id, titulo=titulo.strip(), tipo=tipo, carpeta="/".join(partes),
        cuerpo=cuerpo if isinstance(cuerpo, str) else "", creado=ahora, actualizado=ahora,
        clase=clase, marcas=_validar_marcas(marcas),
        estado=_validar_estado(estado), etiquetas=_validar_etiquetas(etiquetas),
        pipelines=_validar_pipelines(pipelines), rol=_validar_rol(tipo, rol),
        prioridad=_validar_prioridad(prioridad),
    )
    ruta.parent.mkdir(parents=True, exist_ok=True)
    escribir_atomico(ruta, _serializar(doc))
    versionado.registrar(ruta, f"crear {doc_id}")
    return doc


def guardar(
    doc_id: str,
    *,
    titulo: str | None = None,
    cuerpo: str | None = None,
    carpeta: str | None = None,
    clase: str | None = None,
    marcas: list[str] | None = None,
    estado: str | None = None,
    etiquetas: list[str] | None = None,
    pipelines: list[str] | None = None,
    rol: str | None = None,
    prioridad: int | None = None,
) -> Documento:
    """Actualiza un documento (atomico). Si cambia titulo/carpeta, MUEVE el fichero (nuevo id).

    Devuelve el documento resultante (con el id posiblemente NUEVO). Conserva `creado`.
    Solo se aplican los campos pasados (no-None).
    """
    actual = obtener(doc_id)
    if actual is None:
        raise TextoError("Ese documento no existe.")

    nuevo_titulo = titulo.strip() if isinstance(titulo, str) and titulo.strip() else actual.titulo
    nuevo_cuerpo = cuerpo if isinstance(cuerpo, str) else actual.cuerpo
    nueva_clase = actual.clase if clase is None else _validar_clase(actual.tipo, clase)
    nuevas_marcas = actual.marcas if marcas is None else _validar_marcas(marcas)
    nuevo_estado = actual.estado if estado is None else _validar_estado(estado)
    nuevas_etiquetas = actual.etiquetas if etiquetas is None else _validar_etiquetas(etiquetas)
    nuevos_pipelines = actual.pipelines if pipelines is None else _validar_pipelines(pipelines)
    nuevo_rol = actual.rol if rol is None else _validar_rol(actual.tipo, rol)
    nueva_prioridad = actual.prioridad if prioridad is None else _validar_prioridad(prioridad)
    partes_carpeta = _carpeta_relativa(actual.tipo, actual.carpeta if carpeta is None else carpeta)

    nuevo = Documento(
        id=actual.id, titulo=nuevo_titulo, tipo=actual.tipo, carpeta="/".join(partes_carpeta),
        cuerpo=nuevo_cuerpo, creado=actual.creado, actualizado=_ahora_iso(),
        clase=nueva_clase, marcas=nuevas_marcas, salida=actual.salida,
        estado=nuevo_estado, etiquetas=nuevas_etiquetas, pipelines=nuevos_pipelines,
        rol=nuevo_rol, prioridad=nueva_prioridad,
    )

    # ¿Cambia la RUTA (titulo o carpeta)? Si si, calculamos id/ruta nuevos y movemos.
    cambia_titulo = titulo is not None and _slug(nuevo_titulo) != actual.id.split("/")[-1]
    cambia_carpeta = carpeta is not None and "/".join(partes_carpeta) != actual.carpeta
    ruta_actual = _ruta_de_id(actual.id)
    if cambia_titulo or cambia_carpeta:
        nuevo.id, ruta_nueva = _id_unico(actual.tipo, partes_carpeta, _slug(nuevo_titulo))
        ruta_nueva.parent.mkdir(parents=True, exist_ok=True)
        escribir_atomico(ruta_nueva, _serializar(nuevo))
        ruta_actual.unlink(missing_ok=True)
        versionado.registrar(ruta_nueva, f"mover {actual.id} -> {nuevo.id}", ruta_previa=ruta_actual)
    else:
        escribir_atomico(ruta_actual, _serializar(nuevo))
        versionado.registrar(ruta_actual, f"editar {nuevo.id}")
    return nuevo


def borrar(doc_id: str) -> None:
    """Mueve un documento a la papelera (NO borra en duro; restaurable)."""
    ruta = _ruta_de_id(doc_id)
    if not ruta.is_file():
        raise TextoError("Ese documento no existe.")
    doc = _leer(ruta)
    if doc is None:
        raise TextoError("Ese documento no se puede leer.")
    papelera = raiz() / _PAPELERA
    papelera.mkdir(parents=True, exist_ok=True)
    aplanado = doc_id.replace("/", "__")
    sello = _ahora_iso().replace(":", "").replace("-", "")
    destino = papelera / f"{aplanado}__{sello}.md"
    # Estampa el id de origen para poder restaurar a su sitio.
    texto = _serializar(doc)
    texto = texto.replace("titulo:", f"papelera_origen: {doc_id}\ntitulo:", 1)
    escribir_atomico(destino, texto)
    ruta.unlink(missing_ok=True)
    versionado.registrar(ruta, f"borrar {doc_id}")


def listar_papelera() -> list[dict[str, object]]:
    """Documentos en la papelera (id de papelera + titulo + origen + tipo)."""
    papelera = raiz() / _PAPELERA
    if not papelera.is_dir():
        return []
    items: list[dict[str, object]] = []
    for ruta in sorted(papelera.glob("*.md")):
        try:
            texto = ruta.read_text(encoding="utf-8")
        except OSError:
            continue
        meta, _ = _parsear(texto)
        items.append({
            "id": ruta.stem,  # id de papelera (nombre del fichero sin .md)
            "titulo": meta.get("titulo") if isinstance(meta.get("titulo"), str) else ruta.stem,
            "tipo": meta.get("tipo") if isinstance(meta.get("tipo"), str) else "",
            "origen": meta.get("papelera_origen") if isinstance(meta.get("papelera_origen"), str) else "",
        })
    return items


def restaurar(papelera_id: str) -> Documento:
    """Restaura un documento de la papelera a su id de origen. Lanza si no existe / choca."""
    nombre = Path(papelera_id).name
    if not nombre or nombre != papelera_id:
        raise TextoError("Identificador de papelera no válido.")
    ruta = raiz() / _PAPELERA / f"{nombre}.md"
    if not ruta.is_file():
        raise TextoError("Ese elemento no está en la papelera.")
    texto = ruta.read_text(encoding="utf-8")
    meta, _ = _parsear(texto)
    origen = meta.get("papelera_origen")
    if not isinstance(origen, str) or not origen:
        raise TextoError("No se conoce el origen de este elemento.")
    destino = _ruta_de_id(origen)
    if destino.exists():
        raise TextoError("Ya existe un documento en la ubicación original.")
    # Quita la marca de papelera al restaurar.
    limpio = re.sub(r"^papelera_origen:.*\n", "", texto, count=1, flags=re.MULTILINE)
    destino.parent.mkdir(parents=True, exist_ok=True)
    escribir_atomico(destino, limpio)
    ruta.unlink(missing_ok=True)
    doc = _leer(destino)
    if doc is None:  # pragma: no cover -- recien escrito, deberia leerse
        raise TextoError("No se pudo restaurar el documento.")
    versionado.registrar(destino, f"restaurar {origen}")
    return doc


# --------------------------------------------------------------------------- #
# Historial de versiones (git)                                                 #
# --------------------------------------------------------------------------- #


def historial(doc_id: str, *, limite: int = 50) -> list[dict[str, str]]:
    """Historial de versiones de un documento (recientes primero). Delega en `versionado`."""
    if obtener(doc_id) is None:
        raise TextoError("Ese documento no existe.")
    return versionado.historial(doc_id, limite=limite)


def version(doc_id: str, sha: str) -> Documento | None:
    """Lee un documento tal y como estaba en la version `sha` (sin tocar el actual)."""
    texto = versionado.version(doc_id, sha)
    if texto is None:
        return None
    meta, cuerpo = _parsear(texto)
    actual = obtener(doc_id)
    tipo = actual.tipo if actual is not None else doc_id.split("/")[0]
    titulo = meta.get("titulo")
    titulo = titulo.strip() if isinstance(titulo, str) and titulo.strip() else doc_id.split("/")[-1]
    clase = meta.get("clase")
    clase = clase if isinstance(clase, str) and clase in CLASES else ""
    return Documento(
        id=doc_id, titulo=titulo, tipo=tipo, carpeta="/".join(doc_id.split("/")[1:-1]),
        cuerpo=cuerpo, creado=meta.get("creado", "") if isinstance(meta.get("creado"), str) else "",
        actualizado=meta.get("actualizado", "") if isinstance(meta.get("actualizado"), str) else "",
        clase=clase, marcas=_lista_str(meta.get("marcas")), salida=meta.get("salida", "") if isinstance(meta.get("salida"), str) else "",
        estado=meta.get("estado", ESTADO_DEFECTO) if isinstance(meta.get("estado"), str) else ESTADO_DEFECTO,
        etiquetas=_lista_str(meta.get("etiquetas")), pipelines=_lista_str(meta.get("pipelines")),
        rol=meta.get("rol", "") if isinstance(meta.get("rol"), str) else "",
        prioridad=meta.get("prioridad", 0) if isinstance(meta.get("prioridad"), int) and not isinstance(meta.get("prioridad"), bool) else 0,
    )


def restaurar_version(doc_id: str, sha: str, *, autor: dict[str, str] | None = None) -> Documento:
    """Devuelve el documento al contenido de la version `sha` (un commit nuevo encima).

    No reescribe la historia: graba el contenido antiguo como un nuevo estado (rollback no
    destructivo). El id/carpeta se conservan (no se mueve el fichero). Lanza si no existe.
    """
    texto = versionado.version(doc_id, sha)
    if texto is None:
        raise TextoError("No se encontró esa versión del documento.")
    ruta = _ruta_de_id(doc_id)
    if not ruta.is_file():
        raise TextoError("Ese documento no existe.")
    # Conserva el `actualizado` fresco (es un cambio nuevo) pero el resto del cuerpo/meta viene
    # de la version antigua. Releemos via _parsear y reserializamos para normalizar.
    meta, cuerpo = _parsear(texto)
    actual = obtener(doc_id)
    assert actual is not None  # is_file arriba lo garantiza
    restaurado = Documento(
        id=actual.id, titulo=(meta.get("titulo") if isinstance(meta.get("titulo"), str) else actual.titulo) or actual.titulo,
        tipo=actual.tipo, carpeta=actual.carpeta, cuerpo=cuerpo, creado=actual.creado,
        actualizado=_ahora_iso(),
        clase=meta.get("clase", actual.clase) if isinstance(meta.get("clase"), str) and meta.get("clase") in CLASES else actual.clase,
        marcas=_lista_str(meta.get("marcas")) or actual.marcas,
        salida=actual.salida,
        estado=meta.get("estado", actual.estado) if isinstance(meta.get("estado"), str) and meta.get("estado") in ESTADOS else actual.estado,
        etiquetas=_lista_str(meta.get("etiquetas")),
        pipelines=_lista_str(meta.get("pipelines")),
        rol=meta.get("rol", actual.rol) if isinstance(meta.get("rol"), str) and meta.get("rol") in ROLES_PROMPT else actual.rol,
        prioridad=meta.get("prioridad", actual.prioridad) if isinstance(meta.get("prioridad"), int) and not isinstance(meta.get("prioridad"), bool) else actual.prioridad,
    )
    escribir_atomico(ruta, _serializar(restaurado))
    versionado.registrar(ruta, f"revertir {doc_id} a {sha[:8]}", autor=autor)
    return restaurado


def vaciar_papelera() -> None:
    """Borra en duro toda la papelera."""
    papelera = raiz() / _PAPELERA
    if papelera.is_dir():
        shutil.rmtree(papelera, ignore_errors=True)


# --------------------------------------------------------------------------- #
# Linea editorial: auto-adjunto por marca                                      #
# --------------------------------------------------------------------------- #


def editoriales_de_marca(marca: str, *, pipeline: str | None = None) -> list[Documento]:
    """Documentos EDITORIALES que aplican por defecto al lanzar un prompt con esa marca.

    Incluye (a) los GLOBALES (clase plataforma/tropicalizacion/reglas, aplican a todas las
    marcas) y (b) los especificos de la marca (clase marca/voz cuyo `marcas` incluye `marca`).
    El usuario puede luego anadir/quitar en la UI; esto es solo el conjunto por defecto.

    Filtros del rediseno (retrocompatibles):
      - ESTADO: solo se adjuntan documentos `activo` (un `borrador`/`archivado` no inyecta).
      - PIPELINE (opcional): si se pasa, un doc se incluye solo si NO acota pipelines
        (`pipelines == []`, aplica a todos -> comportamiento clasico) o si incluye `pipeline`.
        Asi un editorial puede entrar en `copy` pero no en `qa`, sin romper a los docs viejos
        (que no declaran `pipelines` y siguen aplicando a todo).

    Orden: por `prioridad` (menor primero), luego PILAR (orden de `PILARES_EDITORIALES`,
    despues el resto) y, a igualdad, por id; auto-adjunto estable y legible.
    """
    seleccion: list[Documento] = []
    for doc in listar(tipo="editorial"):
        if doc.estado != ESTADO_DEFECTO:
            continue
        if pipeline is not None and doc.pipelines and pipeline not in doc.pipelines:
            continue
        # La pertenencia a marca se deriva de la CARPETA (la marca es una carpeta): un doc bajo
        # `…/<marca>/…` aplica a esa marca; uno bajo `global/` (o comun/general/todas) aplica a
        # TODAS. Se conservan `clase`/`marcas` por retrocompatibilidad con los docs existentes.
        segmentos = doc.carpeta.split("/") if doc.carpeta else []
        es_global = doc.clase in _CLASES_GLOBALES or any(s in _CARPETAS_GLOBALES for s in segmentos)
        es_de_marca = bool(marca) and (marca in doc.marcas or marca in segmentos)
        if es_global or es_de_marca:
            seleccion.append(doc)

    orden = {clase: i for i, clase in enumerate(PILARES_EDITORIALES)}
    seleccion.sort(key=lambda d: (d.prioridad, orden.get(d.clase, len(orden)), d.id))
    return seleccion


# --------------------------------------------------------------------------- #
# Resolucion de PIPELINES (que prompt base + que editoriales alimentan a cada uno)            #
# --------------------------------------------------------------------------- #


def prompt_base_de(pipeline: str) -> str:
    """Id del prompt base EFECTIVO de un pipeline.

    Resolucion: si EXISTE un prompt `activo` que declara `rol == registro.rol` y lista este
    `pipeline` en sus `pipelines`, ese REBINDEA al pipeline (gana el de menor `prioridad`,
    luego id). Si nadie rebindea, cae al `prompt_defecto` del registro (comportamiento actual).
    """
    spec = PIPELINES.get(pipeline)
    if spec is None:
        raise TextoError(f"Pipeline desconocido: {pipeline}.")
    rol = spec.get("rol", "")
    candidatos = [
        d for d in listar(tipo="prompt")
        if d.estado == ESTADO_DEFECTO and rol and d.rol == rol and pipeline in d.pipelines
    ]
    if candidatos:
        candidatos.sort(key=lambda d: (d.prioridad, d.id))
        return candidatos[0].id
    return spec.get("prompt_defecto", "")


def editoriales_de_pipeline(marca: str, pipeline: str) -> list[Documento]:
    """Editoriales auto-adjuntables a `pipeline` para `marca` (atajo con filtro de pipeline)."""
    return editoriales_de_marca(marca, pipeline=pipeline)


def previsualizar_pipeline(pipeline: str, marca: str, contexto: str = "") -> dict[str, object]:
    """Devuelve el prompt ENSAMBLADO que recibiria `claude -p` para `pipeline`+`marca`.

    "Lo que inyectas es lo que ves": usa el MISMO compositor que la generacion real, sin
    lanzar nada. Devuelve `{pipeline, prompt_base_id, prompt_efectivo, adjuntos, falta_base}`.
    `adjuntos` es la lista (id/titulo/clase) de editoriales que se adjuntarian, en orden.
    """
    from .dominio import generar  # perezoso: generar importa texto

    base_id = prompt_base_de(pipeline)
    cuerpo = cuerpo_efectivo(base_id) if base_id else None
    adjuntos = editoriales_de_pipeline(marca, pipeline)
    prompt = generar.componer(cuerpo or "", adjuntos, contexto) if cuerpo is not None else ""
    return {
        "pipeline": pipeline,
        "prompt_base_id": base_id,
        "falta_base": cuerpo is None,
        "prompt_efectivo": prompt,
        "adjuntos": [
            {"id": d.id, "titulo": d.titulo, "clase": d.clase, "prioridad": d.prioridad}
            for d in adjuntos
        ],
    }


def validacion_editorial(marca: str) -> dict[str, object]:
    """Diagnostica si la linea editorial de `marca` cubre los 4 PILARES obligatorios.

    Devuelve `{completa, faltan, recomendacion, pilares}`:
      - `completa`: True si los 4 pilares (`PILARES_EDITORIALES`) tienen al menos un
        documento editorial con cuerpo.
      - `faltan`: lista de pilares sin cubrir (en el orden canonico).
      - `recomendacion`: frase en espanol lista para mostrar (vacia si esta completa).
      - `pilares`: mapa pilar -> bool (cubierto o no), para una UI mas detallada.

    Si `marca` es vacio, los pilares ESPECIFICOS (marca/voz) se consideran no cubiertos
    (no hay marca de la que colgarlos): se exige elegir una marca primero.
    """
    if marca:
        docs = editoriales_de_marca(marca)
    else:
        docs = [d for d in listar(tipo="editorial") if d.clase in _CLASES_GLOBALES]
    # Un pilar solo cuenta como CUBIERTO si su documento tiene cuerpo (un editorial vacio no
    # aporta contexto): el filtro de no-vacio vive aqui, donde se decide la completitud.
    cubiertas = {d.clase for d in docs if d.cuerpo.strip()}
    pilares = {p: (p in cubiertas) for p in PILARES_EDITORIALES}
    faltan = [p for p in PILARES_EDITORIALES if not pilares[p]]

    if not marca:
        recomendacion = "Elige una marca para validar su línea editorial."
    elif not faltan:
        recomendacion = ""
    else:
        nombres = ", ".join(faltan)
        recomendacion = (
            f"La línea editorial de esta marca está incompleta: falta(n) {nombres}. "
            "Crea o completa esos documentos en la Texto (sección Editorial) para "
            "que la generación tenga contexto suficiente."
        )
    return {
        "completa": not faltan,
        "faltan": faltan,
        "recomendacion": recomendacion,
        "pilares": pilares,
    }


# --------------------------------------------------------------------------- #
# Validacion de campos editoriales                                             #
# --------------------------------------------------------------------------- #


def _validar_clase(tipo: str, clase: str) -> str:
    """Valida `clase` para editoriales; para prompts debe quedar vacia."""
    if tipo != "editorial":
        return ""
    clase = (clase or "").strip()
    if not clase:
        return ""
    if clase not in CLASES:
        raise TextoError(f"La clase editorial debe ser una de: {', '.join(CLASES)}.")
    return clase


def _validar_estado(estado: str | None) -> str:
    """Valida el estado del ciclo de vida; vacio/None -> defecto."""
    if estado is None:
        return ESTADO_DEFECTO
    estado = estado.strip()
    if not estado:
        return ESTADO_DEFECTO
    if estado not in ESTADOS:
        raise TextoError(f"El estado debe ser uno de: {', '.join(ESTADOS)}.")
    return estado


def _validar_etiquetas(etiquetas: list[str] | None) -> list[str]:
    """Normaliza etiquetas (tags): minusculas, slug-safe, de-dup, orden estable."""
    if not etiquetas:
        return []
    if not isinstance(etiquetas, list):
        raise TextoError("Las etiquetas deben ser una lista de textos.")
    vistas: list[str] = []
    for e in etiquetas:
        if not isinstance(e, str):
            raise TextoError("Cada etiqueta debe ser un texto.")
        norm = re.sub(r"[^a-z0-9]+", "-", e.strip().lower()).strip("-")
        if norm and norm not in vistas:
            vistas.append(norm)
    return vistas


def _validar_pipelines(pipelines: list[str] | None) -> list[str]:
    """Valida la lista de pipelines a los que se ata el doc (deben existir en el registro)."""
    if not pipelines:
        return []
    if not isinstance(pipelines, list):
        raise TextoError("Los pipelines deben ser una lista de identificadores.")
    vistas: list[str] = []
    for p in pipelines:
        if not isinstance(p, str):
            raise TextoError("Cada pipeline debe ser un identificador.")
        p = p.strip()
        if p and p not in PIPELINES:
            raise TextoError(f"Pipeline desconocido: {p}.")
        if p and p not in vistas:
            vistas.append(p)
    return vistas


def _validar_rol(tipo: str, rol: str | None) -> str:
    """Valida el rol de un prompt; para no-prompt debe quedar vacio."""
    if tipo != "prompt" or rol is None:
        return ""
    rol = rol.strip()
    if not rol:
        return ""
    if rol not in ROLES_PROMPT:
        raise TextoError(f"El rol debe ser uno de: {', '.join(r for r in ROLES_PROMPT if r)}.")
    return rol


def _validar_prioridad(prioridad: int | None) -> int:
    """Valida la prioridad de ensamblaje (entero; None -> 0)."""
    if prioridad is None:
        return 0
    if isinstance(prioridad, bool) or not isinstance(prioridad, int):
        raise TextoError("La prioridad debe ser un número entero.")
    return prioridad


def dir_semilla() -> Path:
    """Dir de la SEMILLA (documentos por defecto que se copian al store en el 1er arranque).

    Vive DENTRO del paquete (`texto_semilla/`) para viajar con el código (a diferencia
    del store, que es estado de usuario). Override por `KENI_TEXTO_SEMILLA` (tests).
    """
    import os

    env = os.environ.get("KENI_TEXTO_SEMILLA")
    if env:
        return Path(env).expanduser()
    return Path(__file__).resolve().parent / "texto_semilla"


def obtener_semilla(doc_id: str) -> Documento | None:
    """Lee un documento de la SEMILLA del paquete (no del store). None si no existe."""
    if not isinstance(doc_id, str) or not doc_id.strip():
        return None
    partes = doc_id.strip().strip("/").split("/")
    if len(partes) < 2 or partes[0] not in TIPOS or not _segmentos_validos(partes):
        return None
    base = dir_semilla()
    ruta = base.joinpath(*partes).with_suffix(".md")
    # Anti-traversal robusto: el destino DEBE caer estrictamente dentro de la semilla
    # (resolver + relative_to lanza si se escapa) y ser un fichero.
    try:
        ruta.resolve().relative_to(base.resolve())
    except (ValueError, OSError):
        return None
    if not ruta.is_file():
        return None
    meta, cuerpo = _parsear(ruta.read_text(encoding="utf-8"))
    tipo = partes[0]
    titulo = meta.get("titulo")
    titulo = titulo.strip() if isinstance(titulo, str) and titulo.strip() else partes[-1].replace("-", " ")
    clase = meta.get("clase") if isinstance(meta.get("clase"), str) and meta.get("clase") in CLASES else ""
    marcas_crudas = meta.get("marcas")
    marcas = [m for m in marcas_crudas if isinstance(m, str)] if isinstance(marcas_crudas, list) else []
    rol = meta.get("rol")
    rol = rol if tipo == "prompt" and isinstance(rol, str) and rol in ROLES_PROMPT else ""
    return Documento(
        id=doc_id, titulo=titulo, tipo=tipo, carpeta="/".join(partes[1:-1]), cuerpo=cuerpo,
        creado="", actualizado="", clase=clase, marcas=marcas,
        etiquetas=_lista_str(meta.get("etiquetas")), pipelines=_lista_str(meta.get("pipelines")),
        rol=rol,
    )


def cuerpo_efectivo(prompt_id: str) -> str | None:
    """Cuerpo de un prompt: la versión del STORE si el equipo la editó, si no la SEMILLA.

    Es la fuente de verdad para las features que se apoyan en un prompt base: el equipo
    puede editarlo en la Texto (gana el store) y, si no, se usa el que viaja en el
    paquete (semilla). None si no existe ni en uno ni en otro.
    """
    doc = obtener(prompt_id)
    if doc is not None:
        return doc.cuerpo
    semilla = obtener_semilla(prompt_id)
    return semilla.cuerpo if semilla is not None else None


def importar_semilla(origen: Path | None = None) -> int:
    """Copia los documentos de la semilla al store que AÚN NO existan. Idempotente.

    Pensado para el PRIMER arranque (poblar la Texto con la línea editorial y los
    prompts base). No pisa nada: un documento ya presente en el store se respeta. Devuelve
    cuántos documentos se importaron. Los ficheros de la semilla ya vienen en formato de
    store (frontmatter + cuerpo, ruta `tipo/.../slug.md`).
    """
    base = origen or dir_semilla()
    if not base.is_dir():
        return 0
    destino_raiz = raiz()
    n = 0
    for ruta in sorted(base.rglob("*.md")):
        rel = ruta.relative_to(base)
        partes = rel.with_suffix("").as_posix().split("/")
        if partes[0] not in TIPOS or not _segmentos_validos(partes):
            continue
        destino = destino_raiz.joinpath(*rel.parts)
        if destino.exists():
            continue
        try:
            texto = ruta.read_text(encoding="utf-8")
        except OSError:
            continue
        destino.parent.mkdir(parents=True, exist_ok=True)
        escribir_atomico(destino, texto)
        n += 1
    return n


def _validar_marcas(marcas: list[str] | None) -> list[str]:
    """Normaliza la lista de marcas (ids canonicos) de un documento editorial."""
    if not marcas:
        return []
    if not isinstance(marcas, list) or not all(isinstance(m, str) for m in marcas):
        raise TextoError("Las marcas deben ser una lista de identificadores.")
    # De-dup preservando orden.
    vistas: list[str] = []
    for m in marcas:
        m = m.strip()
        if m and m not in vistas:
            vistas.append(m)
    return vistas
