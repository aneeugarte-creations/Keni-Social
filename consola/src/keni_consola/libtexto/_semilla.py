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
from ._publicacion import cuerpo_publicado
from ._rutas import raiz

__all__ = [
    "dir_semilla", "obtener_semilla", "cuerpo_efectivo", "cuerpo_semilla", "importar_semilla",
    "migrar_nombres_biblioteca", "limpiar_prompts_obsoletos",
]

# Prompts del sistema RETIRADOS de la semilla (fusionados/borrados): sus ficheros quedarían
# huérfanos en el store de la Biblioteca. `limpiar_prompts_obsoletos` los borra al desplegar.
_PROMPTS_OBSOLETOS_BIBLIOTECA: tuple[str, ...] = (
    "prompt/arte-sistema",       # fusionado en prompt/arte (directiva única del generador)
    "prompt/arte-ilustracion",   # Estudio de generación retirado (código muerto)
)
_SENTINELA_OBSOLETOS = ".prompts-obsoletos-v1"

# Migración ONE-SHOT del rediseño de nombres/ids de la Biblioteca: el store en vivo ya tiene los
# docs del sistema con ids/títulos VIEJOS, y `importar_semilla` no pisa lo existente, así que los
# nombres nuevos + descripción + cuerpos limpios no llegarían. Esta migración (a) borra del store
# las copias con el id viejo de los prompts renombrados y (b) RE-SIEMBRA todos los docs del sistema
# desde la semilla nueva, EXCEPTO los `patrones.md` (los gestiona `patrones_derivar --store`). One-
# shot por SENTINELA: tras correr no vuelve a tocar el store, así que las ediciones futuras del
# equipo se respetan. El contenido viejo es recuperable (historial git de la semilla).
_RENOMBRES_PROMPT_BIBLIOTECA: tuple[tuple[str, str], ...] = (
    ("prompt/copy-desde-nota", "prompt/copy"),
    ("prompt/qa-fuente", "prompt/validacion"),
    ("prompt/brainstorming-evergreen", "prompt/evergreen"),
    ("prompt/editorial/sugerencias-plataforma", "prompt/sugerencias"),
    ("prompt/imagen/arte-noticia", "prompt/arte"),
    ("prompt/imagen/ilustracion-fondo", "prompt/arte-ilustracion"),
    ("prompt/imagen/sistema-generador", "prompt/arte-sistema"),
    ("prompt/noticias/fusion-historias", "prompt/fusion"),
    ("prompt/noticias/fusion-verificacion", "prompt/fusion-verificacion"),
    ("prompt/noticias/perfil-editorial", "prompt/editorial"),
    ("prompt/noticias/traduccion", "prompt/traduccion"),
    ("prompt/importacion/calendario", "prompt/importar/calendario"),
    ("prompt/importacion/parrilla", "prompt/importar/parrilla"),
)
_SENTINELA_NOMBRES = ".migracion-nombres-v1"
# Carpetas de prompt que quedan vacías en el store tras aplanar los ids (se limpian al final).
_CARPETAS_VIEJAS_BIBLIOTECA = ("prompt/imagen", "prompt/noticias", "prompt/importacion", "prompt/editorial")


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
    """Cuerpo de un prompt: version PUBLICADA > working copy del store > SEMILLA.

    Es la fuente de verdad para las features que se apoyan en un prompt base. Con el
    modelo de PUBLICACION (rediseno de la Biblioteca), si el documento tiene puntero de
    produccion los pipelines inyectan ESA version (sha git inmutable), no la working
    copy: editar es libre, pero lo que corre es lo publicado. Sin puntero (o si la BD/
    git no estan disponibles) gana la working copy del store, como siempre; y si el doc
    no existe en el store, la semilla del paquete. None si no existe en ninguno.
    """
    doc = obtener(prompt_id)
    if doc is not None:
        publicado = cuerpo_publicado(prompt_id)
        return publicado if publicado is not None else doc.cuerpo
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


def migrar_nombres_biblioteca(origen: Path | None = None) -> int:
    """Aplica el rediseño de nombres/ids de la Biblioteca al store (ONE-SHOT por sentinela).

    Pensado para el arranque del servidor, ANTES de `importar_semilla`. Devuelve cuántos
    documentos tocó (0 si ya se aplicó o no hay semilla). Idempotente: tras la primera pasada
    deja un sentinela y no vuelve a pisar el store (respeta ediciones futuras del equipo).
    """
    base = origen or dir_semilla()
    if not base.is_dir():
        return 0
    destino_raiz = raiz()
    sentinela = destino_raiz / _SENTINELA_NOMBRES
    if sentinela.exists():
        return 0
    n = 0
    # (1) Borra del store las copias con el ID VIEJO de los prompts renombrados (el id nuevo se
    #     siembra en el paso 2). Sin esto quedarían huérfanas en la Biblioteca con el nombre viejo.
    for viejo, _nuevo in _RENOMBRES_PROMPT_BIBLIOTECA:
        ruta_vieja = destino_raiz.joinpath(*f"{viejo}.md".split("/"))
        if ruta_vieja.is_file():
            ruta_vieja.unlink()
            n += 1
    # (2) Re-siembra desde la semilla NUEVA todos los docs del sistema (ids nuevos + editoriales con
    #     título/descr/cuerpo limpios), EXCEPTO patrones.md (lo gestiona `patrones_derivar --store`).
    for ruta in sorted(base.rglob("*.md")):
        rel = ruta.relative_to(base)
        partes = rel.with_suffix("").as_posix().split("/")
        if partes[0] not in TIPOS or not _segmentos_validos(partes):
            continue
        if rel.name == "patrones.md":
            continue
        try:
            texto = ruta.read_text(encoding="utf-8")
        except OSError:
            continue
        destino = destino_raiz.joinpath(*rel.parts)
        destino.parent.mkdir(parents=True, exist_ok=True)
        escribir_atomico(destino, texto)
        n += 1
    # (3) Limpia las carpetas viejas de prompt que quedaron vacías tras aplanar los ids.
    for sub in _CARPETAS_VIEJAS_BIBLIOTECA:
        carpeta = destino_raiz.joinpath(*sub.split("/"))
        try:
            if carpeta.is_dir() and not any(carpeta.iterdir()):
                carpeta.rmdir()
        except OSError:
            pass
    sentinela.parent.mkdir(parents=True, exist_ok=True)
    escribir_atomico(sentinela, "ok\n")
    return n


def limpiar_prompts_obsoletos() -> int:
    """Borra del store los prompts del sistema RETIRADOS (`_PROMPTS_OBSOLETOS_BIBLIOTECA`).

    ONE-SHOT por sentinela: tras fusionar/borrar prompts (p. ej. `arte-sistema`→`arte`, o el
    Estudio de generación retirado), sus ficheros quedarían huérfanos en la Biblioteca. Esto los
    elimina al desplegar (vía `sembrar`). Idempotente; no toca nada más del store. Devuelve cuántos
    borró. Recuperable: el contenido vive en el historial git de la semilla.
    """
    destino_raiz = raiz()
    sentinela = destino_raiz / _SENTINELA_OBSOLETOS
    if sentinela.exists():
        return 0
    n = 0
    for pid in _PROMPTS_OBSOLETOS_BIBLIOTECA:
        ruta = destino_raiz.joinpath(*f"{pid}.md".split("/"))
        if ruta.is_file():
            ruta.unlink()
            n += 1
    sentinela.parent.mkdir(parents=True, exist_ok=True)
    escribir_atomico(sentinela, "ok\n")
    return n
