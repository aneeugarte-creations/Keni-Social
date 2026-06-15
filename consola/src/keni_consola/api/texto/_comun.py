"""Helpers compartidos por los submódulos de `api/texto`.

Sin rutas: solo utilidades que cruzan áreas (serialización de documentos y el tope de
contexto). Cada área (`docs`, `publicacion`, `pipelines`, `lanzar`) los importa de aquí.
"""

from __future__ import annotations

from ... import libtexto, prompts_procesos

# Tope de tamano del bloque de contexto (texto pegado / leido de archivo / url) en chars.
_MAX_TEXTO = 200_000


def _doc_json(
    doc: libtexto.Documento, *, estado_pub: dict[str, object] | None = None
) -> dict[str, object]:
    """Serializa un documento + `procesos` (transparencia) + el estado de PUBLICACIÓN.

    `procesos` es de SOLO LECTURA y sale del catálogo en código (`prompts_procesos`), no del
    contenido editable: refleja qué módulo inyecta el prompt en un agente. [] si no está catalogado
    (p. ej. documentos editoriales o prompts aún sin cablear).

    Estado de PUBLICACIÓN (CONTRATO con el frontend, también en
    el listado): `produccion` (`{sha, autor, nota, creado}` | null), `sha_actual` (HEAD git
    del doc | null) y `sin_publicar` (hay cambios sin publicar; false sin puntero).
    `estado_pub` (opcional) lo precalculan los listados POR LOTE para no pagar una consulta
    SQL + un subproceso git por documento.
    """
    if estado_pub is None:
        estado_pub = libtexto.estado_publicacion(doc.id)
    return {
        **doc.a_dict(),
        "procesos": prompts_procesos.procesos_de(doc.id),
        # `rev` (concurrencia optimista, estilo ETag): el cliente lo echa al guardar para que
        # el servidor rechace (409) si otro editor guardo debajo. Ver `libtexto.rev_documento`.
        "rev": libtexto.rev_documento(doc),
        **estado_pub,
    }
