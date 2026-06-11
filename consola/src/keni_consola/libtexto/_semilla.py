"""SEMILLA: documentos por defecto que viajan en el paquete y se copian al store.

La semilla vive DENTRO del paquete (`texto_semilla/`) para viajar con el código (a
diferencia del store, que es estado de usuario).
"""

from __future__ import annotations

from pathlib import Path

from ..io_atomico import escribir_atomico
from ._comun import (
    CLASES,
    ROLES_PROMPT,
    TIPOS,
    Documento,
    _lista_str,
    _segmentos_validos,
)
from ._crud import obtener
from ._io import _parsear
from ._rutas import raiz

__all__ = ["dir_semilla", "obtener_semilla", "cuerpo_efectivo", "cuerpo_semilla", "importar_semilla"]


def dir_semilla() -> Path:
    """Dir de la SEMILLA (documentos por defecto que se copian al store en el 1er arranque).

    Vive DENTRO del paquete (`texto_semilla/`) para viajar con el código (a diferencia
    del store, que es estado de usuario). Override por `KENI_TEXTO_SEMILLA` (tests).
    """
    import os

    env = os.environ.get("KENI_TEXTO_SEMILLA")
    if env:
        return Path(env).expanduser()
    # La semilla viaja junto al paquete `keni_consola`; este módulo vive un nivel más
    # abajo (paquete `libtexto`), así que se sube al directorio del paquete padre.
    return Path(__file__).resolve().parent.parent / "texto_semilla"


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
    descripcion = meta.get("descripcion")
    descripcion = descripcion.strip() if isinstance(descripcion, str) else ""
    clase = meta.get("clase") if isinstance(meta.get("clase"), str) and meta.get("clase") in CLASES else ""
    marcas_crudas = meta.get("marcas")
    marcas = [m for m in marcas_crudas if isinstance(m, str)] if isinstance(marcas_crudas, list) else []
    rol = meta.get("rol")
    rol = rol if tipo == "prompt" and isinstance(rol, str) and rol in ROLES_PROMPT else ""
    return Documento(
        id=doc_id, titulo=titulo, descripcion=descripcion, tipo=tipo,
        carpeta="/".join(partes[1:-1]), cuerpo=cuerpo,
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


def cuerpo_semilla(prompt_id: str) -> str:
    """Cuerpo del documento en la SEMILLA del paquete ("" si no existe). NUNCA lanza.

    Red de los módulos que componen prompts: si la lectura del store fallara
    (`cuerpo_efectivo` lanza), el fallback es el seed que viaja en el paquete, no un
    string duplicado en el código.
    """
    try:
        doc = obtener_semilla(prompt_id)
    except Exception:  # noqa: BLE001 -- el fallback nunca debe propagar un fallo de lectura
        return ""
    return doc.cuerpo if doc is not None else ""


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
