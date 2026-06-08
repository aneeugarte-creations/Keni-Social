"""Historial de versiones (git) de un documento. Delega en `versionado`."""

from __future__ import annotations

from .. import versionado
from ..io_atomico import escribir_atomico
from ._comun import (
    CLASES,
    ESTADO_DEFECTO,
    ESTADOS,
    ROLES_PROMPT,
    Documento,
    TextoError,
    _ahora_iso,
    _lista_str,
)
from ._crud import obtener
from ._io import _parsear, _serializar
from ._rutas import _ruta_de_id

__all__ = ["historial", "version", "restaurar_version"]


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
