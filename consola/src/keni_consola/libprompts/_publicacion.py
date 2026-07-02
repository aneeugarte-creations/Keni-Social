"""Modelo de PIEZA de la Prompts: versiones inmutables + puntero "produccion".

EDITAR es libre (working copy + commits git), pero los PIPELINES inyectan SIEMPRE un cuerpo
ESTABLE de cada documento, NUNCA el working copy mutable que el autosave reescribe en vivo:

  - Con puntero de produccion: la version PUBLICADA (sha git fijado por un admin).
  - Sin puntero, pero con historial git: el cuerpo del ULTIMO commit (HEAD). El autosave NO
    commitea (versionado intencional), asi que ese cuerpo no refleja un borrador a medias.
  - Sin puntero NI commit legible (versionado apagado / sin repo / doc aun sin commits): el
    llamante cae al working copy. Es la migracion suave y nada se rompe.

MODO ESTRICTO (`KENI_PROMPTS_ESTRICTO`, default OFF): con el flag ON, un documento CON
puntero de produccion cuyo sha no es legible en git NO cae a la working copy: `cuerpo_publicado`
y `aplicar_produccion` lanzan `ProduccionIlegibleError` y el job de generacion falla con ese
mensaje (el worker lo registra en `generaciones.error`; no hay reintento). El editor y su
preview (`estado_publicacion`, `_crud.obtener`) siguen sobre la working copy en ambos modos.

Publicar = mover el puntero (tabla `texto_publicaciones`, solo admin; los editores proponen
via `texto_solicitudes`).

Este modulo es la CAPA DE LECTURA de ese modelo para libprompts y el ensamblaje:

  - `produccion_de` / `producciones`: puntero(s) vigente(s), BEST-EFFORT (si Postgres no
    esta disponible devuelven None/{}; la composicion de prompts NUNCA se rompe por la BD,
    simplemente cae al snapshot estable o al working copy).
  - `sha_actual` / `shas_actuales`: "HEAD" git de cada documento (referencia; con el
    versionado intencional NO se mueve en autosave, solo al publicar/renombrar).
  - `cuerpo_publicado`: cuerpo ESTABLE del documento (version publicada o, sin puntero, el
    HEAD git; None si no hay ni puntero ni commit legible -> el llamante usa el working copy).
  - `aplicar_produccion`: mapea una lista de `Documento` a su cuerpo estable (por lote); es
    el gancho que usa `dominio.generar.componer` con los adjuntos editoriales.
  - `estado_publicacion`: los 3 campos nuevos del JSON de documento de la API
    (`produccion`, `sha_actual`, `sin_publicar`).

NOTA (alcance del snapshot estable): cubre los docs con AL MENOS un commit git. Los creados
via API/movidos/publicados ya tienen HEAD; los de la INICIAL, que el import escribe sin
commitear, reciben una linea base versionada al final de la siembra
(`_inicial.asegurar_linea_base`), asi que tambien sirven snapshot estable. Solo cae al working
copy si el versionado esta apagado o no hay repo (migracion suave).

La ESCRITURA (publicar/solicitar/aprobar/rechazar) vive en `api/prompts.py` + `db_prompts_pub`
(validaciones de rol y de sha en la API; persistencia pura en db).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from .. import versionado
from ._comun import Documento
from ._io import _parsear

__all__ = [
    "ProduccionIlegibleError",
    "produccion_de",
    "producciones",
    "sha_actual",
    "shas_actuales",
    "cuerpo_publicado",
    "aplicar_produccion",
    "estado_publicacion",
]


class ProduccionIlegibleError(RuntimeError):
    """El puntero de produccion de un documento apunta a un sha NO legible en git.

    Solo se lanza en modo ESTRICTO (`KENI_PROMPTS_ESTRICTO`, ver `config.prompts_estricto`):
    con el flag OFF (defecto), un puntero ilegible cae en silencio a la working copy
    (migracion suave). El mensaje es autoexplicativo: es el error con el que FALLA el job
    de generacion (el worker lo registra tal cual en `generaciones.error`)."""


def _estricto() -> bool:
    """True si el modo estricto esta activo (import perezoso: config carga ajustes/rutas)."""
    from .. import config

    return config.prompts_estricto()


def _fallo_produccion(doc_id: str, sha: str) -> ProduccionIlegibleError:
    return ProduccionIlegibleError(
        f"La version PUBLICADA del documento '{doc_id}' (sha {sha}) no es legible en el "
        "repo git de la biblioteca y el modo estricto esta activo (KENI_PROMPTS_ESTRICTO): "
        "republica el documento desde la Biblioteca o desactiva el modo estricto."
    )


def produccion_de(doc_id: str) -> dict[str, Any] | None:
    """Puntero de produccion vigente de `doc_id`, o None (sin puntero O BD no disponible).

    BEST-EFFORT a proposito: la Prompts es files-as-truth y debe poder listarse/inyectarse
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
    """Cuerpo ESTABLE del documento para los pipelines (NUNCA el working copy mutable), o None.

    Resuelve, en orden:
      1. Con puntero de produccion: el cuerpo en ese sha (version PUBLICADA).
      2. Sin puntero pero con historial git: el cuerpo en su HEAD (ultimo commit:
         crear/mover/una pieza previa). El autosave NO commitea, asi que es un snapshot
         estable que no refleja un borrador a medio escribir.
      3. None: ni puntero ni commit legibles (versionado apagado / sin repo / doc sin commits,
         p. ej. los de la inicial nunca commiteados). El llamante cae entonces al working copy.

    En modo ESTRICTO (`KENI_PROMPTS_ESTRICTO`), un puntero de produccion cuyo sha no es
    legible LANZA `ProduccionIlegibleError` en vez de devolver None: la generacion falla
    con un mensaje claro en lugar de sustituir en silencio la version publicada.

    Lo usan `cuerpo_efectivo` (prompts base) y `prompts_lanzar` (prompt elegido a mano).
    """
    pub = produccion_de(doc_id)
    if pub and pub.get("sha"):
        cuerpo = _cuerpo_en_sha(doc_id, str(pub["sha"]))
        if cuerpo is None and _estricto():
            raise _fallo_produccion(doc_id, str(pub["sha"]))
        return cuerpo
    sha = sha_actual(doc_id)
    if sha:
        return _cuerpo_en_sha(doc_id, sha)
    return None


def aplicar_produccion(docs: list[Documento]) -> list[Documento]:
    """Sustituye el cuerpo de cada doc por su cuerpo ESTABLE (version publicada o HEAD git).

    POR LOTE: una sola consulta de punteros (`producciones`) + una llamada git de HEADs
    (`shas_actuales`) + un `git show` por doc resuelto. Para cada doc: el cuerpo del puntero
    de produccion si lo hay, si no el del HEAD git (snapshot estable que el autosave no toca).
    Los docs sin puntero NI commit legible quedan INTACTOS (working copy: migracion suave).
    En modo ESTRICTO (`KENI_PROMPTS_ESTRICTO`), un doc CON puntero cuyo sha no es legible
    LANZA `ProduccionIlegibleError` (misma politica que `cuerpo_publicado`).
    Devuelve copias; no muta los documentos de entrada. Es el gancho del ensamblaje de adjuntos
    editoriales (`dominio.generar.componer`).
    """
    if not docs:
        return list(docs)
    estricto = _estricto()
    punteros = producciones()
    shas = shas_actuales()
    resultado: list[Documento] = []
    for d in docs:
        pub = punteros.get(d.id)
        if pub and pub.get("sha"):
            cuerpo = _cuerpo_en_sha(d.id, str(pub["sha"]))
            if cuerpo is None and estricto:
                raise _fallo_produccion(d.id, str(pub["sha"]))
        else:
            sha = shas.get(d.id)
            cuerpo = _cuerpo_en_sha(d.id, sha) if sha else None
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
    cuerpo_actual: str | None = None,
) -> dict[str, Any]:
    """Los campos de pieza del JSON de documento de la API.

    Forma (CONTRATO con el frontend; tambien en el listado `GET /api/prompts`):
      - `produccion`: `{sha, autor, nota, creado}` del puntero vigente, o `null`.
      - `sha_actual`: sha del ULTIMO commit del doc (crear/mover/publicar), o `null`. Con el
        versionado INTENCIONADO ya NO se mueve al teclear (el autosave no commitea): solo
        cambia al publicar/solicitar o renombrar. El frontend lo conserva como referencia.
      - `sin_publicar`: hay cambios de BORRADOR sin publicar. Se calcula por CONTENIDO (no por
        divergencia de HEAD, que ya no se mueve en autosave):
          * CON puntero: True si el cuerpo del working copy != cuerpo publicado (o la versión
            publicada ya no es legible).
          * SIN puntero: True si el doc tiene contenido (nunca se publicó -> mostrar
            "Publicar"); False si el cuerpo está en blanco.

    `punteros`/`shas` (opcionales) resuelven POR LOTE en los listados (una consulta SQL +
    una llamada git de HEADs para N documentos). El cálculo de `sin_publicar` es EXACTO tanto
    en el detalle como en el lote: lee el cuerpo del working copy (de `cuerpo_actual` si se
    pasa, o releyendo el `.md`) y, solo para los docs PUBLICADOS, su cuerpo publicado con un
    `git show` (los docs sin puntero no pagan git). El repo de la Prompts es pequeño, así
    que ese `git show` por doc publicado es asumible; si hiciera falta, el lote podría caer a
    una aproximación más barata sin tocar el detalle.
    """
    pub = punteros.get(doc_id) if punteros is not None else produccion_de(doc_id)
    sha = shas.get(doc_id) if shas is not None else sha_actual(doc_id)
    puntero = _puntero_json(pub)

    if cuerpo_actual is None:
        from ._crud import obtener  # perezoso: evita ciclo de import en la carga del barrel

        doc = obtener(doc_id)
        cuerpo_wc = doc.cuerpo if doc is not None else ""
    else:
        cuerpo_wc = cuerpo_actual

    if pub and pub.get("sha"):
        cuerpo_pub = _cuerpo_en_sha(doc_id, str(pub["sha"]))
        sin_publicar = cuerpo_pub is None or cuerpo_wc != cuerpo_pub
    else:
        sin_publicar = bool(cuerpo_wc.strip())

    return {
        "produccion": puntero,
        "sha_actual": sha,
        "sin_publicar": sin_publicar,
    }
