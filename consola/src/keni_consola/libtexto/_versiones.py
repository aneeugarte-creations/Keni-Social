"""Versionado INTENCIONADO de un documento (rediseño "commit como GitHub").

Una VERSIÓN nace solo al PUBLICAR/SOLICITAR (`fijar_version`), no en cada autosave. Por eso:

  - `historial` devuelve el HISTORIAL DE PUBLICACIONES (tabla `texto_publicaciones`), no el
    `git log` crudo (que ahora solo tiene "crear"/"mover" + los commits de publicación). Es
    lo que ve el usuario como "versiones".
  - `version` lee el `.md` completo de un sha git (sigue siendo git por debajo).
  - `restaurar_version` ("Traer al borrador") CARGA el contenido de una versión en el working
    copy SIN commitear ni publicar (antes creaba un commit "revertir X").
  - `descartar_borrador` resetea el working copy al contenido PUBLICADO (puntero de
    producción) SIN commitear.
  - `fijar_version` comitea el working copy como versión inmutable y devuelve su sha (es el
    commit intencional que dispara publicar/solicitar).
"""

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
from ._publicacion import produccion_de
from ._rutas import _ruta_de_id

__all__ = [
    "historial",
    "version",
    "restaurar_version",
    "descartar_borrador",
    "fijar_version",
]


def historial(doc_id: str, *, limite: int = 50) -> list[dict[str, str]]:
    """Historial de PUBLICACIONES de un documento (recientes primero).

    Cada entrada conserva la forma `RespuestaHistorialTexto` del contrato con el frontend
    (`{sha, sha_corto, fecha, autor, mensaje}`), mapeada desde una publicación:
    `mensaje`=nota de publicación, `fecha`=`creado`, `autor`=autor, `sha_corto`=`sha[:8]`.

    Una VERSIÓN = una publicación: el "borrador" (working copy) NO es una versión y el
    frontend lo sintetiza aparte. Si el doc no tiene publicaciones -> lista vacía.

    BEST-EFFORT (como el resto del modelo de publicación): si Postgres no está disponible,
    cae a lista vacía (NO al `git log`, que tras el rediseño es ruido de "crear"/"mover").
    """
    if obtener(doc_id) is None:
        raise TextoError("Ese documento no existe.")
    try:
        from .. import db  # perezoso: no cargar la persistencia para usos puros de ficheros

        filas = db.historial_texto_publicaciones(doc_id, limite=limite)
    except Exception:  # noqa: BLE001 -- sin BD no hay publicaciones; nunca rompemos la lectura
        return []
    return [
        {
            "sha": str(f.get("sha", "")),
            "sha_corto": str(f.get("sha", ""))[:8],
            "fecha": str(f.get("creado", "")),
            "autor": str(f.get("autor", "")),
            "mensaje": str(f.get("nota", "")),
        }
        for f in filas
    ]


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
        id=doc_id, titulo=titulo,
        descripcion=meta.get("descripcion", "") if isinstance(meta.get("descripcion"), str) else "",
        tipo=tipo, carpeta="/".join(doc_id.split("/")[1:-1]),
        cuerpo=cuerpo, creado=meta.get("creado", "") if isinstance(meta.get("creado"), str) else "",
        actualizado=meta.get("actualizado", "") if isinstance(meta.get("actualizado"), str) else "",
        clase=clase, marcas=_lista_str(meta.get("marcas")), salida=meta.get("salida", "") if isinstance(meta.get("salida"), str) else "",
        estado=meta.get("estado", ESTADO_DEFECTO) if isinstance(meta.get("estado"), str) else ESTADO_DEFECTO,
        etiquetas=_lista_str(meta.get("etiquetas")), pipelines=_lista_str(meta.get("pipelines")),
        rol=meta.get("rol", "") if isinstance(meta.get("rol"), str) else "",
        prioridad=meta.get("prioridad", 0) if isinstance(meta.get("prioridad"), int) and not isinstance(meta.get("prioridad"), bool) else 0,
    )


def _escribir_desde_texto(doc_id: str, texto: str) -> Documento:
    """Reescribe el working copy de `doc_id` con `texto` (un `.md` completo), SIN commitear.

    Normaliza vía `_parsear`/`_serializar` y refresca `actualizado` (es un cambio nuevo del
    borrador). Conserva id/carpeta/creado del documento ACTUAL. Lanza si el doc no existe.
    Núcleo común de `restaurar_version` ("Traer al borrador") y `descartar_borrador`.
    """
    ruta = _ruta_de_id(doc_id)
    if not ruta.is_file():
        raise TextoError("Ese documento no existe.")
    meta, cuerpo = _parsear(texto)
    actual = obtener(doc_id)
    assert actual is not None  # is_file arriba lo garantiza
    resultante = Documento(
        id=actual.id, titulo=(meta.get("titulo") if isinstance(meta.get("titulo"), str) else actual.titulo) or actual.titulo,
        descripcion=meta.get("descripcion", actual.descripcion) if isinstance(meta.get("descripcion"), str) else actual.descripcion,
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
    escribir_atomico(ruta, _serializar(resultante))
    return resultante


def restaurar_version(doc_id: str, sha: str, *, autor: dict[str, str] | None = None) -> Documento:
    """"Traer al borrador": CARGA el contenido de la versión `sha` en el working copy.

    NO commitea ni publica (antes creaba un commit "revertir X"): el contenido entra al
    BORRADOR; el usuario decide después si lo publica. El id/carpeta se conservan. Lanza si
    la versión o el documento no existen. `autor` se acepta por compatibilidad de firma con la
    API (ya no se usa: no hay commit que atribuir).
    """
    texto = versionado.version(doc_id, sha)
    if texto is None:
        raise TextoError("No se encontró esa versión del documento.")
    return _escribir_desde_texto(doc_id, texto)


def descartar_borrador(doc_id: str) -> Documento:
    """Resetea el working copy al contenido PUBLICADO (puntero de producción), SIN commitear.

    Devuelve el documento resultante. Lanza si no hay puntero de producción (nada a lo que
    volver) o si esa versión ya no es legible del historial.
    """
    pub = produccion_de(doc_id)
    if not pub or not pub.get("sha"):
        raise TextoError("No hay versión publicada a la que volver.")
    texto = versionado.version(doc_id, str(pub["sha"]))
    if texto is None:
        raise TextoError("La versión publicada ya no se puede leer del historial.")
    return _escribir_desde_texto(doc_id, texto)


def fijar_version(doc_id: str, *, nota: str = "", autor: dict[str, str] | None = None) -> str | None:
    """Comitea el working copy como una VERSIÓN inmutable y devuelve su sha (o None).

    Es el COMMIT INTENCIONAL del rediseño: lo disparan PUBLICAR y SOLICITAR. La `nota` del
    usuario es el MENSAJE del commit (deja de ser solo metadato de Postgres). Si el working
    copy no cambió respecto al último commit (p. ej. publicar justo tras crear), git no crea
    commit nuevo y se devuelve el sha vigente: igualmente válido para fijar el puntero.

    Best-effort git (como todo `versionado`): devuelve None si el versionado está apagado o
    no hay repo/commits, y el llamante traduce eso a un 400 accionable. Lanza si el documento
    no existe.
    """
    ruta = _ruta_de_id(doc_id)
    if not ruta.is_file():
        raise TextoError("Ese documento no existe.")
    mensaje = nota.strip() if isinstance(nota, str) and nota.strip() else f"publicar {doc_id}"
    versionado.registrar(ruta, mensaje, autor=autor)
    return versionado.sha_documento(doc_id)
