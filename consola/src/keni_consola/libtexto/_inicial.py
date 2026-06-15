"""INICIAL: documentos por defecto que viajan en el paquete y se copian al store.

La inicial vive DENTRO del paquete (`texto_inicial/`) para viajar con el código (a
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
    _ahora_iso,
    _lista_str,
    _segmentos_validos,
)
from ._crud import obtener
from ._io import _leer, _parsear, _serializar
from ._publicacion import cuerpo_publicado
from ._rutas import raiz

__all__ = [
    "dir_inicial", "obtener_inicial", "cuerpo_efectivo", "cuerpo_inicial", "importar_inicial",
    "asegurar_linea_base",
    "migrar_nombres_biblioteca", "limpiar_prompts_obsoletos", "migrar_descripciones_editorial",
]

_PROMPTS_OBSOLETOS_BIBLIOTECA: tuple[str, ...] = (
    "prompt/arte-sistema",
    "prompt/arte-ilustracion",
    "prompt/sugerencias",
    "prompt/editorial/sugerencias-plataforma",
)
_SENTINELA_OBSOLETOS = ".prompts-obsoletos-v1"

# Migración ONE-SHOT del rediseño de nombres/ids de la Biblioteca: el store en vivo ya tiene los
# docs del sistema con ids/títulos VIEJOS, y `importar_inicial` no pisa lo existente, así que los
# nombres nuevos + descripción + cuerpos limpios no llegarían. Esta migración (a) borra del store
# las copias con el id viejo de los prompts renombrados y (b) RE-SIEMBRA todos los docs del sistema
# desde la inicial nueva, EXCEPTO los `patrones.md` (los gestiona `patrones_derivar --store`). One-
# shot por SENTINELA: tras correr no vuelve a tocar el store, así que las ediciones futuras del
# equipo se respetan. El contenido viejo es recuperable (historial git de la inicial).
#
# OLA v2 (rediseño de ETAPAS a verbos C): los ids que ARRIBA quedaron en su forma «v1» (prompt/copy,
# prompt/validacion, prompt/editorial, prompt/fusion, prompt/insumos/*, …) NOMBRABAN una etapa de la
# máquina por su nombre viejo y ahora pasan al verbo C (Redactar, Verificar, Priorizar, Fusionar,
# Recibir, …). El store en vivo ya pasó la v1, así que su sentinela es `.migracion-nombres-v1`; por
# eso el SENTINELA sube a `.migracion-nombres-v2`: la MISMA función vuelve a correr (el call site no
# cambia), borra los ids «v1» con `_IDS_VIEJOS_BIBLIOTECA_V2` y re-siembra los ids con verbo C. En un
# store fresco las dos olas se aplican de una sola pasada. Idempotente por el sentinela v2.
_RENOMBRES_PROMPT_BIBLIOTECA: tuple[tuple[str, str], ...] = (
    ("prompt/copy-desde-nota", "prompt/copy"),
    ("prompt/qa-fuente", "prompt/validacion"),
    ("prompt/brainstorming-evergreen", "prompt/evergreen"),
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
# OLA v2: ids del sistema cuyo nombre nombraba una ETAPA por su nombre viejo y que ahora pasa al
# verbo C. Se BORRAN del store (su id con verbo C se re-siembra en el mismo paso). El cuerpo viejo es
# recuperable (historial git de la inicial). El destino renombrado: prompt/fusion→fusionar,
# prompt/fusion-verificacion→fusionar-verificar, prompt/traduccion→traducir,
# prompt/clasificacion-marca→clasificar-marca, prompt/editorial→priorizar, prompt/validacion→verificar,
# prompt/copy→redactar, prompt/arte→ilustrar, prompt/evergreen→idear, prompt/insumos/*→recibir/*.
_IDS_VIEJOS_BIBLIOTECA_V2: tuple[str, ...] = (
    "prompt/fusion",
    "prompt/fusion-verificacion",
    "prompt/traduccion",
    "prompt/clasificacion-marca",
    "prompt/editorial",
    "prompt/validacion",
    "prompt/copy",
    "prompt/arte",
    "prompt/evergreen",
    "prompt/insumos/contexto",
    "prompt/insumos/corresponsales",
    "prompt/insumos/eventos-claro",
    "prompt/insumos/notas",
    "prompt/insumos/portal",
    "prompt/insumos/reporteros",
)
_SENTINELA_NOMBRES = ".migracion-nombres-v2"
# Carpetas de prompt que quedan vacías en el store tras aplanar/renombrar los ids (se limpian al
# final). `prompt/insumos` la vacía la ola v2 al mover sus prompts a `prompt/recibir`.
_CARPETAS_VIEJAS_BIBLIOTECA = (
    "prompt/imagen", "prompt/noticias", "prompt/importacion", "prompt/editorial", "prompt/insumos",
)

_DESCRIPCIONES_VIEJAS_EDITORIAL: tuple[tuple[str, str], ...] = (
    (r"Ajustes de formato por red propios de .+, sobre el formato común\.",
     "Excepciones de la marca sobre el formato común."),
    (r"Reglas y límites editoriales de .+ al generar copy\.",
     "Límites editoriales al generar copy."),
    (r"Cómo escribe .+: registro, tono y estilo\. Se inyecta al generar copy\.",
     "Registro, tono y estilo; se inyecta al generar copy."),
    (r"Qué es .+, qué cubre y su posicionamiento\. Referencia para redactar el copy\.",
     "Qué cubre y su posicionamiento; referencia del copy."),
    (r"Bandas de rendimiento medidas en Metricool \(longitud, emojis, hashtags\) de .+; "
     r"se regenera periódicamente\.",
     "Bandas medidas en Metricool (longitud, emojis, hashtags); se regeneran periódicamente."),
    (r"Convenciones de formato por red comunes a todas las marcas\.",
     "Base común de formato; cada marca añade sus excepciones."),
    (r"Adaptación al español de México \(léxico y giros\)\. Común a todas las marcas\.",
     "Léxico, giros y registro del español de México."),
    (r"Reglas legales y éticas comunes a todas las marcas\.",
     "Líneas rojas comunes a todas las marcas."),
)
_TITULOS_VIEJOS_EDITORIAL: tuple[tuple[str, str], ...] = (
    ("Formato por red (común)", "Formato por red · común"),
    ("Tropicalización (México)", "Tropicalización MX"),
)
_SENTINELA_DESCRIPCIONES = ".descripciones-v1"


def dir_inicial() -> Path:
    """Dir de la INICIAL (documentos por defecto que se copian al store en el 1er arranque).

    Vive DENTRO del paquete (`texto_inicial/`) para viajar con el código (a diferencia
    del store, que es estado de usuario). Override por `KENI_TEXTO_INICIAL` (tests).
    """
    import os

    env = os.environ.get("KENI_TEXTO_INICIAL")
    if env:
        return Path(env).expanduser()
    # La inicial viaja junto al paquete `keni_consola`; este módulo vive un nivel más
    # abajo (paquete `libtexto`), así que se sube al directorio del paquete padre.
    return Path(__file__).resolve().parent.parent / "texto_inicial"


def obtener_inicial(doc_id: str) -> Documento | None:
    """Lee un documento de la INICIAL del paquete (no del store). None si no existe."""
    if not isinstance(doc_id, str) or not doc_id.strip():
        return None
    partes = doc_id.strip().strip("/").split("/")
    if len(partes) < 2 or partes[0] not in TIPOS or not _segmentos_validos(partes):
        return None
    base = dir_inicial()
    ruta = base.joinpath(*partes).with_suffix(".md")
    # Anti-traversal robusto: el destino DEBE caer estrictamente dentro de la inicial
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
    """Cuerpo de un prompt: version PUBLICADA > working copy del store > INICIAL.

    Es la fuente de verdad para las features que se apoyan en un prompt base. Con el
    modelo de PUBLICACION (rediseno de la Biblioteca), si el documento tiene puntero de
    produccion los pipelines inyectan ESA version (sha git inmutable), no la working
    copy: editar es libre, pero lo que corre es lo publicado. Sin puntero (o si la BD/
    git no estan disponibles) gana la working copy del store, como siempre; y si el doc
    no existe en el store, la inicial del paquete. None si no existe en ninguno.
    """
    doc = obtener(prompt_id)
    if doc is not None:
        publicado = cuerpo_publicado(prompt_id)
        return publicado if publicado is not None else doc.cuerpo
    inicial = obtener_inicial(prompt_id)
    return inicial.cuerpo if inicial is not None else None


def cuerpo_inicial(prompt_id: str) -> str:
    """Cuerpo del documento en la INICIAL del paquete ("" si no existe). NUNCA lanza.

    Red de los módulos que componen prompts: si la lectura del store fallara
    (`cuerpo_efectivo` lanza), el fallback es el seed que viaja en el paquete, no un
    string duplicado en el código.
    """
    try:
        doc = obtener_inicial(prompt_id)
    except Exception:  # noqa: BLE001 -- el fallback nunca debe propagar un fallo de lectura
        return ""
    return doc.cuerpo if doc is not None else ""


def importar_inicial(origen: Path | None = None) -> int:
    """Copia los documentos de la inicial al store que AÚN NO existan. Idempotente.

    Pensado para el PRIMER arranque (poblar la Texto con la línea editorial y los
    prompts base). No pisa nada: un documento ya presente en el store se respeta. Devuelve
    cuántos documentos se importaron. Los ficheros de la inicial ya vienen en formato de
    store (frontmatter + cuerpo, ruta `tipo/.../slug.md`).
    """
    base = origen or dir_inicial()
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


def asegurar_linea_base() -> int:
    """Fija en git una linea base de los documentos del store que aun no tengan commit.

    La siembra/migracion escribe los `.md` directo a disco (atomico) sin commitear, asi que
    un documento recien inicializado no tiene HEAD git y el modelo de publicacion caeria a su
    working copy. Esto registra esos documentos como una linea base versionada, de modo que
    los pipelines sirvan su snapshot estable. Best-effort e idempotente. Se llama al final de
    la siembra. Devuelve cuantos documentos quedaron versionados por primera vez.
    """
    from .. import versionado

    return versionado.linea_base()


def migrar_nombres_biblioteca(origen: Path | None = None) -> int:
    """Aplica el rediseño de nombres/ids de la Biblioteca al store (ONE-SHOT por sentinela).

    Pensado para el arranque del servidor, ANTES de `importar_inicial`. Devuelve cuántos
    documentos tocó (0 si ya se aplicó o no hay inicial). Idempotente: tras la primera pasada
    deja un sentinela y no vuelve a pisar el store (respeta ediciones futuras del equipo).

    Corre DOS olas en la misma pasada: la v1 (renombres de ids ya planos) y la v2 (rediseño de
    ETAPAS a verbos C, `_IDS_VIEJOS_BIBLIOTECA_V2`). El sentinela es `.migracion-nombres-v2`, así
    que un store que solo pasó la v1 (sentinela `.migracion-nombres-v1`) vuelve a entrar aquí y
    recibe la v2 sin tocar el call site.
    """
    base = origen or dir_inicial()
    if not base.is_dir():
        return 0
    destino_raiz = raiz()
    sentinela = destino_raiz / _SENTINELA_NOMBRES
    if sentinela.exists():
        return 0
    n = 0
    for viejo, _nuevo in _RENOMBRES_PROMPT_BIBLIOTECA:
        ruta_vieja = destino_raiz.joinpath(*f"{viejo}.md".split("/"))
        if ruta_vieja.is_file():
            ruta_vieja.unlink()
            n += 1
    # (1b) OLA v2: borra los ids del sistema que nombraban una ETAPA por su nombre viejo (prompt/copy,
    #      prompt/validacion, prompt/insumos/*, …); su id con verbo C se re-siembra en el paso 2.
    #      Imprescindible en un store que ya pasó la v1 y todavía conserva esos ids.
    for viejo in _IDS_VIEJOS_BIBLIOTECA_V2:
        ruta_vieja = destino_raiz.joinpath(*f"{viejo}.md".split("/"))
        if ruta_vieja.is_file():
            ruta_vieja.unlink()
            n += 1
    # (2) Re-siembra desde la inicial NUEVA todos los docs del sistema (ids nuevos + editoriales con
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


def migrar_descripciones_editorial() -> int:
    """Sustituye descripciones y títulos de editoriales (ONE-SHOT por sentinela).

    Se reemplaza cada descripción (y dos títulos específicos) SOLO si su valor actual casa
    EXACTO con un patrón conocido — una edición del equipo deja de casar y se respeta.
    Se escribe IN PLACE (sin `guardar`). Idempotente. Devuelve cuántos documentos tocó.
    """
    import dataclasses
    import re

    destino_raiz = raiz()
    sentinela = destino_raiz / _SENTINELA_DESCRIPCIONES
    if sentinela.exists():
        return 0
    n = 0
    base_editorial = destino_raiz / "editorial"
    if base_editorial.is_dir():
        for ruta in sorted(base_editorial.rglob("*.md")):
            doc = _leer(ruta)
            if doc is None:
                continue
            cambios: dict[str, str] = {}
            for patron, nuevo in _DESCRIPCIONES_VIEJAS_EDITORIAL:
                if re.fullmatch(patron, doc.descripcion.strip()):
                    cambios["descripcion"] = nuevo
                    break
            for viejo, nuevo in _TITULOS_VIEJOS_EDITORIAL:
                if doc.titulo.strip() == viejo:
                    cambios["titulo"] = nuevo
                    break
            if not cambios:
                continue
            nuevo_doc = dataclasses.replace(doc, actualizado=_ahora_iso(), **cambios)
            escribir_atomico(ruta, _serializar(nuevo_doc))
            n += 1
    sentinela.parent.mkdir(parents=True, exist_ok=True)
    escribir_atomico(sentinela, "ok\n")
    return n


def limpiar_prompts_obsoletos() -> int:
    """Borra del store los prompts obsoletos (`_PROMPTS_OBSOLETOS_BIBLIOTECA`).

    ONE-SHOT por sentinela. Idempotente; no toca nada más del store. Devuelve cuántos borró.
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
