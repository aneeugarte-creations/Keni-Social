"""Listado, lectura, creación, actualización y borrado (papelera) de documentos."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from .. import versionado
from ..io_atomico import escribir_atomico
from ._comun import (
    _CLASES_GLOBALES,
    _PAPELERA,
    TIPOS,
    Documento,
    TextoError,
    _ahora_iso,
    _slug,
)
from ._io import _leer, _parsear, _serializar
from ._rutas import _carpeta_relativa, _id_unico, _ruta_de_id, raiz
from ._validacion import (
    _validar_clase,
    _validar_estado,
    _validar_etiquetas,
    _validar_marcas,
    _validar_pipelines,
    _validar_prioridad,
    _validar_rol,
)

__all__ = [
    "listar",
    "_coincide_carpeta",
    "_coincide_busqueda",
    "obtener",
    "listar_carpetas",
    "crear",
    "guardar",
    "borrar",
    "listar_papelera",
    "restaurar",
    "vaciar_papelera",
]


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


def vaciar_papelera() -> None:
    """Borra en duro toda la papelera."""
    papelera = raiz() / _PAPELERA
    if papelera.is_dir():
        shutil.rmtree(papelera, ignore_errors=True)
