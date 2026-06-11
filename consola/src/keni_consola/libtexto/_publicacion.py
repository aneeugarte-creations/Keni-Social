"""Modelo de PUBLICACION de la Biblioteca: versiones inmutables + puntero "produccion".

Rediseno de la Biblioteca de Prompts: EDITAR es libre (working copy + commits git, como
siempre), pero los PIPELINES inyectan SIEMPRE la version PUBLICADA de cada documento (un
sha git fijado por un admin). Publicar = mover el puntero (tabla `texto_publicaciones`,
solo admin; los editores proponen via `texto_solicitudes`). Sin puntero para un doc, el
fallback es la working copy: la migracion es suave y nada se rompe.

Este modulo es la CAPA DE LECTURA de ese modelo para libtexto y el ensamblaje:

  - `produccion_de` / `producciones`: puntero(s) vigente(s), BEST-EFFORT (si Postgres no
    esta disponible devuelven None/{}; la composicion de prompts NUNCA se rompe por la BD,
    simplemente cae a la working copy).
  - `sha_actual` / `shas_actuales`: "HEAD" git de cada documento (para `sin_publicar`).
  - `cuerpo_publicado`: cuerpo del documento EN su version publicada (None sin puntero).
  - `aplicar_produccion`: mapea una lista de `Documento` a sus cuerpos publicados (por
    lote); es el gancho que usa `dominio.generar.componer` con los adjuntos editoriales.
  - `estado_publicacion`: los 3 campos nuevos del JSON de documento de la API
    (`produccion`, `sha_actual`, `sin_publicar`).

La ESCRITURA (publicar/solicitar/aprobar/rechazar) vive en `api/texto.py` + `db_texto_pub`
(validaciones de rol y de sha en la API; persistencia pura en db).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from .. import versionado
from ._comun import Documento
from ._io import _parsear

__all__ = [
    "produccion_de",
    "producciones",
    "sha_actual",
    "shas_actuales",
    "cuerpo_publicado",
    "aplicar_produccion",
    "estado_publicacion",
]


def produccion_de(doc_id: str) -> dict[str, Any] | None:
    """Puntero de produccion vigente de `doc_id`, o None (sin puntero O BD no disponible).

    BEST-EFFORT a proposito: la Biblioteca es files-as-truth y debe poder listarse/inyectarse
    aunque Postgres no este (tests aislados, arranque degradado); en ese caso simplemente no
    hay puntero y todo cae a la working copy.
    """
    try:
        from .. import db  # perezoso: no cargar la persistencia para usos puros de ficheros

        return db.texto_produccion_de(doc_id)
    except Exception:  # noqa: BLE001 -- sin BD no hay puntero; nunca rompemos la lectura
        return None


def producciones() -> dict[str, dict[str, Any]]:
    """Mapa doc_id -> puntero de produccion vigente (por lote). {} si BD no disponible."""
    try:
        from .. import db

        return db.texto_producciones()
    except Exception:  # noqa: BLE001 -- best-effort (ver `produccion_de`)
        return {}


def sha_actual(doc_id: str) -> str | None:
    """SHA git del ultimo commit del documento (None sin repo/commits)."""
    return versionado.sha_documento(doc_id)


def shas_actuales() -> dict[str, str]:
    """Mapa doc_id -> sha del ultimo commit, por lote (una sola llamada a git)."""
    return versionado.shas_documentos()


def _cuerpo_en_sha(doc_id: str, sha: str) -> str | None:
    """Cuerpo del documento en la version `sha` (None si esa version no es legible)."""
    texto = versionado.version(doc_id, sha)
    if texto is None:
        return None
    try:
        _meta, cuerpo = _parsear(texto)
    except Exception:  # noqa: BLE001 -- una version corrupta no debe romper la composicion
        return None
    return cuerpo


def cuerpo_publicado(doc_id: str) -> str | None:
    """Cuerpo del documento EN PRODUCCION (su version publicada), o None.

    None significa "sin puntero o version no legible": el llamante debe caer a la working
    copy (fallback de la migracion suave). Lo usan `cuerpo_efectivo` (prompts base) y
    `texto_lanzar` (prompt elegido a mano).
    """
    pub = produccion_de(doc_id)
    if not pub or not pub.get("sha"):
        return None
    return _cuerpo_en_sha(doc_id, str(pub["sha"]))


def aplicar_produccion(docs: list[Documento]) -> list[Documento]:
    """Sustituye el cuerpo de cada doc por su version PUBLICADA (si tiene puntero legible).

    POR LOTE: una sola consulta de punteros (`producciones`) + un `git show` por doc
    publicado. Los docs sin puntero (o cuya version no se pueda leer) quedan INTACTOS
    (working copy). Devuelve copias; no muta los documentos de entrada. Es el gancho del
    ensamblaje de adjuntos editoriales (`dominio.generar.componer`).
    """
    if not docs:
        return list(docs)
    punteros = producciones()
    if not punteros:
        return list(docs)
    resultado: list[Documento] = []
    for d in docs:
        pub = punteros.get(d.id)
        cuerpo = _cuerpo_en_sha(d.id, str(pub["sha"])) if pub and pub.get("sha") else None
        resultado.append(replace(d, cuerpo=cuerpo) if cuerpo is not None else d)
    return resultado


def _puntero_json(pub: dict[str, Any] | None) -> dict[str, Any] | None:
    """Forma publica del puntero (`{sha, autor, nota, creado}`) o None."""
    if not pub:
        return None
    return {
        "sha": pub.get("sha", ""),
        "autor": pub.get("autor", ""),
        "nota": pub.get("nota", ""),
        "creado": pub.get("creado", ""),
    }


def estado_publicacion(
    doc_id: str,
    *,
    punteros: dict[str, dict[str, Any]] | None = None,
    shas: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Los campos de publicacion del JSON de documento de la API.

    Forma (CONTRATO con el frontend; tambien en el listado `GET /api/texto`):
      - `produccion`: `{sha, autor, nota, creado}` del puntero vigente, o `null`.
      - `sha_actual`: sha git del ultimo commit del doc, o `null` (sin repo/commits).
      - `sin_publicar`: True si hay puntero Y HEAD y difieren (hay cambios sin publicar);
        False si no hay puntero (la working copy ES lo que se inyecta) o si coinciden.

    `punteros`/`shas` (opcionales) permiten resolver POR LOTE en los listados (una consulta
    SQL + una llamada git para N documentos) en vez de pagar una por documento.
    """
    pub = punteros.get(doc_id) if punteros is not None else produccion_de(doc_id)
    sha = shas.get(doc_id) if shas is not None else sha_actual(doc_id)
    puntero = _puntero_json(pub)
    return {
        "produccion": puntero,
        "sha_actual": sha,
        "sin_publicar": bool(puntero and sha and sha != puntero["sha"]),
    }
