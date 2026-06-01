"""Almacen UNICO de la Biblioteca: PROMPTS + LINEA EDITORIAL (files-as-truth).

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

La raiz se sobreescribe con `KENI_BIBLIOTECA_DIR` (los tests lo apuntan a un tmp).
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import yaml

from . import config, rutas
from .io_atomico import escribir_atomico

# --------------------------------------------------------------------------- #
# Constantes y errores                                                        #
# --------------------------------------------------------------------------- #

# Tipos de documento. El primer segmento del id (y la carpeta de primer nivel) es el tipo.
TIPOS = ("prompt", "editorial")

# Clase de un documento EDITORIAL (organiza la linea editorial y gobierna el auto-adjunto).
CLASES = ("marca", "voz", "plataforma", "tropicalizacion", "reglas")

# Clases editoriales GLOBALES: aplican a TODAS las marcas (no llevan `marcas` propias).
_CLASES_GLOBALES = frozenset({"plataforma", "tropicalizacion", "reglas"})

# Dir de la papelera (oculto; no es un tipo navegable).
_PAPELERA = ".papelera"

# slug: minusculas, digitos y guiones; sin guiones colgando.
_RE_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class BibliotecaError(RuntimeError):
    """Error de la biblioteca con mensaje ya en espanol, apto para mostrar al usuario."""


# --------------------------------------------------------------------------- #
# Dataclass                                                                    #
# --------------------------------------------------------------------------- #


@dataclass
class Documento:
    """Un documento de la biblioteca (prompt o editorial)."""

    id: str  # ruta relativa posix sin extension, p.ej. "prompts/investigacion/resumen"
    titulo: str
    tipo: str  # prompt | editorial
    carpeta: str  # subruta bajo el tipo ("" = raiz del tipo)
    cuerpo: str
    creado: str
    actualizado: str
    clase: str = ""  # solo editorial
    marcas: list[str] = field(default_factory=list)  # solo editorial (clase marca/voz)

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
        }


# --------------------------------------------------------------------------- #
# Localizacion de la raiz + saneo de ids                                       #
# --------------------------------------------------------------------------- #


def raiz() -> Path:
    """Dir raiz del almacen de la biblioteca.

    Preferencia: env `KENI_BIBLIOTECA_DIR` (lo usan los tests con un tmp) ->
    `rutas.dir_config()/biblioteca` (bajo `KENI_DATA_DIR` en contenedor; `~/.config/
    keni-social/biblioteca` en local).
    """
    override = config.biblioteca_dir()
    if override is not None:
        return override
    return rutas.dir_config() / "biblioteca"


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
        raise BibliotecaError("El título no produce un identificador válido.")
    return base


def _segmentos_validos(partes: list[str]) -> bool:
    """True si cada segmento es un slug valido (sin `.`/`..`/vacios)."""
    return all(p and p not in (".", "..") and bool(_RE_SLUG.match(p)) for p in partes)


def _ruta_de_id(doc_id: str) -> Path:
    """Resuelve `<raiz>/<id>.md` garantizando que cae ESTRICTAMENTE dentro de la raiz.

    El id debe ser una ruta POSIX relativa cuyo PRIMER segmento es un `tipo` valido y el
    resto son slugs. Lanza `BibliotecaError` si el id es invalido o se escapa de la raiz.
    """
    if not isinstance(doc_id, str) or not doc_id.strip():
        raise BibliotecaError("Identificador de documento no válido.")
    partes = doc_id.strip().strip("/").split("/")
    if len(partes) < 2 or partes[0] not in TIPOS or not _segmentos_validos(partes):
        raise BibliotecaError("Identificador de documento no válido.")
    base = raiz().resolve()
    destino = base.joinpath(*partes).with_suffix(".md").resolve()
    # Defensa en profundidad: el destino debe colgar de la raiz (nunca de `..`).
    if base not in destino.parents:
        raise BibliotecaError("Ruta de documento fuera del almacén.")
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
        raise BibliotecaError("Nombre de carpeta no válido (usa minúsculas, dígitos y guiones).")
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
    except (ValueError, BibliotecaError):
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
    return Documento(
        id=doc_id, titulo=titulo, tipo=tipo, carpeta=carpeta, cuerpo=cuerpo,
        creado=creado, actualizado=actualizado, clase=clase, marcas=marcas,
    )


# --------------------------------------------------------------------------- #
# Listado / lectura                                                            #
# --------------------------------------------------------------------------- #


def listar(tipo: str | None = None, carpeta: str | None = None, q: str | None = None) -> list[Documento]:
    """Documentos del almacen, filtrables por `tipo`, `carpeta` (prefijo) y busqueda `q`.

    Ordena por (tipo, id). Tolerante: un `.md` corrupto se SALTA. Excluye la papelera.
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
    except BibliotecaError:
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
) -> Documento:
    """Crea un documento nuevo (prompt o editorial) y lo escribe (atomico). Devuelve el doc."""
    if not isinstance(titulo, str) or not titulo.strip():
        raise BibliotecaError("El título no puede estar vacío.")
    if tipo not in TIPOS:
        raise BibliotecaError("El tipo debe ser 'prompt' o 'editorial'.")
    clase = _validar_clase(tipo, clase)
    partes = _carpeta_relativa(tipo, carpeta)
    slug = _slug(titulo)
    doc_id, ruta = _id_unico(tipo, partes, slug)
    ahora = _ahora_iso()
    doc = Documento(
        id=doc_id, titulo=titulo.strip(), tipo=tipo, carpeta="/".join(partes),
        cuerpo=cuerpo if isinstance(cuerpo, str) else "", creado=ahora, actualizado=ahora,
        clase=clase, marcas=_validar_marcas(marcas),
    )
    ruta.parent.mkdir(parents=True, exist_ok=True)
    escribir_atomico(ruta, _serializar(doc))
    return doc


def guardar(
    doc_id: str,
    *,
    titulo: str | None = None,
    cuerpo: str | None = None,
    carpeta: str | None = None,
    clase: str | None = None,
    marcas: list[str] | None = None,
) -> Documento:
    """Actualiza un documento (atomico). Si cambia titulo/carpeta, MUEVE el fichero (nuevo id).

    Devuelve el documento resultante (con el id posiblemente NUEVO). Conserva `creado`.
    Solo se aplican los campos pasados (no-None).
    """
    actual = obtener(doc_id)
    if actual is None:
        raise BibliotecaError("Ese documento no existe.")

    nuevo_titulo = titulo.strip() if isinstance(titulo, str) and titulo.strip() else actual.titulo
    nuevo_cuerpo = cuerpo if isinstance(cuerpo, str) else actual.cuerpo
    nueva_clase = actual.clase if clase is None else _validar_clase(actual.tipo, clase)
    nuevas_marcas = actual.marcas if marcas is None else _validar_marcas(marcas)
    partes_carpeta = _carpeta_relativa(actual.tipo, actual.carpeta if carpeta is None else carpeta)

    nuevo = Documento(
        id=actual.id, titulo=nuevo_titulo, tipo=actual.tipo, carpeta="/".join(partes_carpeta),
        cuerpo=nuevo_cuerpo, creado=actual.creado, actualizado=_ahora_iso(),
        clase=nueva_clase, marcas=nuevas_marcas,
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
    else:
        escribir_atomico(ruta_actual, _serializar(nuevo))
    return nuevo


def borrar(doc_id: str) -> None:
    """Mueve un documento a la papelera (NO borra en duro; restaurable)."""
    ruta = _ruta_de_id(doc_id)
    if not ruta.is_file():
        raise BibliotecaError("Ese documento no existe.")
    doc = _leer(ruta)
    if doc is None:
        raise BibliotecaError("Ese documento no se puede leer.")
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
        raise BibliotecaError("Identificador de papelera no válido.")
    ruta = raiz() / _PAPELERA / f"{nombre}.md"
    if not ruta.is_file():
        raise BibliotecaError("Ese elemento no está en la papelera.")
    texto = ruta.read_text(encoding="utf-8")
    meta, _ = _parsear(texto)
    origen = meta.get("papelera_origen")
    if not isinstance(origen, str) or not origen:
        raise BibliotecaError("No se conoce el origen de este elemento.")
    destino = _ruta_de_id(origen)
    if destino.exists():
        raise BibliotecaError("Ya existe un documento en la ubicación original.")
    # Quita la marca de papelera al restaurar.
    limpio = re.sub(r"^papelera_origen:.*\n", "", texto, count=1, flags=re.MULTILINE)
    destino.parent.mkdir(parents=True, exist_ok=True)
    escribir_atomico(destino, limpio)
    ruta.unlink(missing_ok=True)
    doc = _leer(destino)
    if doc is None:  # pragma: no cover -- recien escrito, deberia leerse
        raise BibliotecaError("No se pudo restaurar el documento.")
    return doc


def vaciar_papelera() -> None:
    """Borra en duro toda la papelera."""
    papelera = raiz() / _PAPELERA
    if papelera.is_dir():
        shutil.rmtree(papelera, ignore_errors=True)


# --------------------------------------------------------------------------- #
# Linea editorial: auto-adjunto por marca                                      #
# --------------------------------------------------------------------------- #


def editoriales_de_marca(marca: str) -> list[Documento]:
    """Documentos EDITORIALES que aplican por defecto al lanzar un prompt con esa marca.

    Incluye (a) los GLOBALES (clase plataforma/tropicalizacion/reglas, aplican a todas las
    marcas) y (b) los especificos de la marca (clase marca/voz cuyo `marcas` incluye `marca`).
    El usuario puede luego anadir/quitar en la UI; esto es solo el conjunto por defecto.
    """
    seleccion: list[Documento] = []
    for doc in listar(tipo="editorial"):
        if doc.clase in _CLASES_GLOBALES:
            seleccion.append(doc)
        elif marca and marca in doc.marcas:
            seleccion.append(doc)
    return seleccion


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
        raise BibliotecaError(f"La clase editorial debe ser una de: {', '.join(CLASES)}.")
    return clase


def dir_semilla() -> Path:
    """Dir de la SEMILLA (documentos por defecto que se copian al store en el 1er arranque).

    Vive DENTRO del paquete (`biblioteca_semilla/`) para viajar con el código (a diferencia
    del store, que es estado de usuario). Override por `KENI_BIBLIOTECA_SEMILLA` (tests).
    """
    import os

    env = os.environ.get("KENI_BIBLIOTECA_SEMILLA")
    if env:
        return Path(env).expanduser()
    return Path(__file__).resolve().parent / "biblioteca_semilla"


def obtener_semilla(doc_id: str) -> Documento | None:
    """Lee un documento de la SEMILLA del paquete (no del store). None si no existe."""
    if not isinstance(doc_id, str) or not doc_id.strip():
        return None
    partes = doc_id.strip().strip("/").split("/")
    if len(partes) < 2 or partes[0] not in TIPOS or not _segmentos_validos(partes):
        return None
    base = dir_semilla()
    ruta = base.joinpath(*partes).with_suffix(".md")
    try:
        if base.resolve() not in ruta.resolve().parents or not ruta.is_file():
            return None
    except OSError:
        return None
    meta, cuerpo = _parsear(ruta.read_text(encoding="utf-8"))
    tipo = partes[0]
    titulo = meta.get("titulo")
    titulo = titulo.strip() if isinstance(titulo, str) and titulo.strip() else partes[-1].replace("-", " ")
    clase = meta.get("clase") if isinstance(meta.get("clase"), str) and meta.get("clase") in CLASES else ""
    marcas_crudas = meta.get("marcas")
    marcas = [m for m in marcas_crudas if isinstance(m, str)] if isinstance(marcas_crudas, list) else []
    return Documento(
        id=doc_id, titulo=titulo, tipo=tipo, carpeta="/".join(partes[1:-1]), cuerpo=cuerpo,
        creado="", actualizado="", clase=clase, marcas=marcas,
    )


def cuerpo_efectivo(prompt_id: str) -> str | None:
    """Cuerpo de un prompt: la versión del STORE si el equipo la editó, si no la SEMILLA.

    Es la fuente de verdad para las features que se apoyan en un prompt base: el equipo
    puede editarlo en la Biblioteca (gana el store) y, si no, se usa el que viaja en el
    paquete (semilla). None si no existe ni en uno ni en otro.
    """
    doc = obtener(prompt_id)
    if doc is not None:
        return doc.cuerpo
    semilla = obtener_semilla(prompt_id)
    return semilla.cuerpo if semilla is not None else None


def importar_semilla(origen: Path | None = None) -> int:
    """Copia los documentos de la semilla al store que AÚN NO existan. Idempotente.

    Pensado para el PRIMER arranque (poblar la Biblioteca con la línea editorial y los
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
        raise BibliotecaError("Las marcas deben ser una lista de identificadores.")
    # De-dup preservando orden.
    vistas: list[str] = []
    for m in marcas:
        m = m.strip()
        if m and m not in vistas:
            vistas.append(m)
    return vistas
