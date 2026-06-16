"""INICIAL: documentos por defecto que viajan en el paquete y se copian al store.

La inicial vive DENTRO del paquete (`prompts_inicial/`) para viajar con el código (a
diferencia del store, que es estado de usuario).
"""

from __future__ import annotations

import hashlib
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
    "migrar_nombres_prompts", "limpiar_prompts_obsoletos", "limpiar_prompts_obsoletos_v2",
    "migrar_descripciones_editorial",
    "reformatear_prompts", "publicar_linea_base", "migrar_contrato_salida", "migrar_redactar_v1",
    "migrar_parrilla_v1", "migrar_titulos_prompts", "migrar_alcance_editorial",
    "migrar_descripciones_prompt",
]

_PROMPTS_OBSOLETOS: tuple[str, ...] = (
    "prompt/arte-sistema",
    "prompt/arte-ilustracion",
    "prompt/sugerencias",
    "prompt/editorial/sugerencias-plataforma",
)
_SENTINELA_OBSOLETOS = ".prompts-obsoletos-v1"

# OLA v2 de obsoletos: prompts retirados al eliminar features. El envoltorio «sin emojis» se
# INLINEÓ en el prompt de `idear` (su único usuario), así que su prompt editable ya no hace falta.
# El store en vivo ya pasó la v1 (sentinela `.prompts-obsoletos-v1`), por eso esta ola lleva su
# PROPIO sentinela y lista. Idempotente.
_PROMPTS_OBSOLETOS_V2: tuple[str, ...] = (
    "prompt/envoltorios/sin-emojis",
)
_SENTINELA_OBSOLETOS_V2 = ".prompts-obsoletos-v2"

# Migración ONE-SHOT del rediseño de nombres/ids de la Prompts: el store en vivo ya tiene los
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
# cambia), borra los ids «v1» con `_IDS_VIEJOS_PROMPTS_V2` y re-siembra los ids con verbo C. En un
# store fresco las dos olas se aplican de una sola pasada. Idempotente por el sentinela v2.
_RENOMBRES_PROMPT: tuple[tuple[str, str], ...] = (
    ("prompt/copy-desde-nota", "prompt/copy"),
    ("prompt/verificacion-fuente", "prompt/validacion"),
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
_IDS_VIEJOS_PROMPTS_V2: tuple[str, ...] = (
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
_CARPETAS_VIEJAS = (
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

# REFORMATO v1: los prompts del sistema se reescribieron a un formato más legible (párrafos, listas,
# líneas en blanco alrededor de los `{{PLACEHOLDERS}}`). El store en vivo ya tiene esos prompts
# (re-sembrados por la migración de nombres v2) byte-idénticos a la inicial VIEJA, así que la edición
# del cuerpo NO les llega por `importar_inicial` (no pisa lo existente). Esta migración propaga el
# cuerpo NUEVO al store RESPETANDO ediciones del equipo: reescribe un prompt solo si su cuerpo ACTUAL
# casa EXACTO con el cuerpo VIEJO conocido (sha256 de abajo); si alguien lo editó, su hash no casa y se
# deja intacto. One-shot por SENTINELA. El contenido viejo es recuperable (git del store). El sha256 es
# del CUERPO (sin frontmatter), tal como lo devuelve `_leer(...).cuerpo` (con `strip("\n")`).
_REFORMATO_PROMPTS_V1: tuple[tuple[str, str], ...] = (
    ("prompt/clasificar-marca", "4cfd577a327cecb8425167d9c0fce9b036768851f8f5b81afeec60316b31202b"),
    ("prompt/fusionar-verificar", "363f9f50a4d3290e0d934b2523ffafbfa0f4113eb7306e5a83e072f3cb687686"),
    ("prompt/fusionar", "b62024530cc5b7fe5028f39523e19e063f2b5bab688acdf397495fcc980b670d"),
    ("prompt/hashtags", "e7753ea75a397d2ce171e1cbb953ea14155f78a2897ee4746d515fcc02496474"),
    ("prompt/importar/calendario", "4754721ac3c55d0e776fc50fdf96fb49c596e6add74972c138aab895cb041fd6"),
    ("prompt/importar/parrilla", "62cb69f7c486ccb423675a6731da9d31a1437267c26d45af0548b1617731b9f8"),
    ("prompt/priorizar", "ce8e944d3db9ac6bebe899fe8db44e162f300dd7d547229e3f9dc9b12eb60e1d"),
    ("prompt/recibir/contexto", "715f4c8198a75a4c56f6335534c170400fa546781ea61e53a18f7360920ac968"),
    ("prompt/recibir/corresponsales", "8ef5ac1f125634b84a4bf1ed27b67cfe589cc27459737d50881fd031ef122c7c"),
    ("prompt/recibir/eventos-claro", "8f789eb9342a7a3c4582cd906744210c87fe6be98fe53cf9dac1d9c09eefb26e"),
    ("prompt/recibir/notas", "615bd88267d639d10a2047164fd0acfbea674cc25eb344fe36e765b92f7420dc"),
    ("prompt/recibir/portal", "ede0388ee3150481f9d9949fe00ac381215ea89147f5eed7178a1693f3363d6f"),
    ("prompt/recibir/reporteros", "69f5e1271809e789e07c2183d336c594f5494389b1df2c1e840875fe8f5fb202"),
    ("prompt/traducir", "7f1a14bef37042b33b90500c40d943113f3c173e0ef860710dd4587f3a3965f2"),
)
_SENTINELA_REFORMATO = ".reformato-prompts-v1"
_SENTINELA_CONTRATO = ".contrato-salida-v1"
_SENTINELA_REDACTAR = ".redactar-contrato-v1"
_SENTINELA_PARRILLA = ".parrilla-contrato-v1"

# TÍTULOS de una palabra agrupados por etapa: los prompts del sistema pasan a un título de UNA
# palabra (la carpeta da el contexto de etapa: `recibir/Notas`, `importar/Parrilla`, …). El store en
# vivo ya tiene los títulos VIEJOS; esta migración los renombra IN PLACE solo si el título actual casa
# EXACTO con el viejo conocido (una edición del equipo deja de casar y se respeta) y RE-PUBLICA el doc
# para no dejarlo "sin publicar". `(id, titulo_viejo, titulo_nuevo)`. One-shot por sentinela.
_TITULOS_UNA_PALABRA: tuple[tuple[str, str, str], ...] = (
    ("prompt/clasificar-marca", "Clasificar marca", "Clasificar"),
    ("prompt/critica", "Crítica IA (pre-publicación)", "Crítica"),
    ("prompt/envoltorios/carrusel", "Envoltorio: decisión de carrusel", "Carrusel"),
    ("prompt/envoltorios/copy-unico", "Envoltorio: copy unificado", "Unificado"),
    ("prompt/envoltorios/redes", "Envoltorio: piezas por red", "Redes"),
    ("prompt/envoltorios/sin-emojis", "Envoltorio: sin emojis", "Limpio"),
    ("prompt/fusionar-verificar", "Fusionar · verificar", "Cotejar"),
    ("prompt/importar/calendario", "Importar calendario", "Calendario"),
    ("prompt/importar/parrilla", "Importar parrilla", "Parrilla"),
    ("prompt/recibir/contexto", "Recibir: indicaciones y correcciones (Claro Sports)", "Contexto"),
    ("prompt/recibir/corresponsales", "Recibir: corresponsales", "Corresponsales"),
    ("prompt/recibir/eventos-claro", "Recibir: eventos Claro Sports", "Eventos"),
    ("prompt/recibir/notas", "Recibir: notas y links (Claro Sports)", "Notas"),
    ("prompt/recibir/portal", "Recibir: portal/SMS", "Portal"),
    ("prompt/recibir/reporteros", "Recibir: reporteros", "Reporteros"),
    ("prompt/asistente/resumir", "Asistente · resumir", "Resumir"),
    ("prompt/asistente/variantes", "Asistente · variantes", "Variantes"),
)
_SENTINELA_TITULOS = ".titulos-prompts-v1"
_SENTINELA_ALCANCE = ".alcance-editorial-v1"

# DESCRIPCIONES de prompt acortadas: varios prompts del sistema (envoltorios, asistente) traían una
# `descripcion` más LARGA que su propio cuerpo, así que el panel "Acerca de" mostraba más descripción
# que prompt. La inicial ya las acortó a un one-liner; el store en vivo conserva la descripción VIEJA.
# Esta migración la reescribe IN PLACE solo si la descripción actual casa EXACTO con la vieja conocida
# (una edición del equipo deja de casar y se respeta) y RE-PUBLICA el doc para no dejarlo "sin publicar".
# `(id, descripcion_vieja, descripcion_nueva)`. One-shot por sentinela; espejo de `migrar_titulos_prompts`.
_DESCRIPCIONES_PROMPT: tuple[tuple[str, str, str], ...] = (
    ("prompt/asistente/resumir",
     "Instrucción aditiva del modo «resumir» del asistente del tablero: condensa la nota en un copy "
     "breve y directo por red. Se anexa al prompt de copy.",
     "Modo «resumir» del asistente: condensa la nota en un copy breve."),
    ("prompt/asistente/variantes",
     "Instrucción aditiva del modo «variantes» del asistente del tablero: pide tres alternativas de "
     "copy para que el community manager elija. Se anexa al prompt de copy.",
     "Modo «variantes» del asistente: propone tres alternativas de copy."),
    ("prompt/envoltorios/carrusel",
     "Bloque que se añade al copy unificado cuando la historia agrupa 2+ notas: el modelo decide entre "
     "post y carrusel editorial. El código rellena {{N_NOTAS}}, {{MAX_SLIDES}} y {{CATALOGO_FOTOS}} "
     "(catálogo numerado de fotos propias).",
     "Envoltorio que deja al modelo elegir entre post y carrusel."),
    ("prompt/envoltorios/copy-unico",
     "Esqueleto de la instrucción del copy UNIFICADO del pipeline (un texto + un texto-en-imagen para "
     "todas las redes). El código rellena {{MODO_PUBLICACION}}, {{ETIQUETAS}}, {{VERSIONES}} (dos "
     "versiones si se mezclan redes amplias y estrechas; una si no) y {{CIERRE_JSON}} (forma exacta del "
     "bloque json, con la decisión de carrusel si procede).",
     "Envoltorio del copy unificado: un texto para todas las redes."),
    ("prompt/envoltorios/redes",
     "Instrucción aditiva del copy POR RED (Texto manual y flujos que piden una pieza por red): limita "
     "las redes pedidas, ancla sus límites técnicos y fija el bloque json de piezas. El código rellena "
     "{{ETIQUETAS}}, {{LIMITES}} e {{IDS_JSON}} desde el catálogo de redes y sus límites.",
     "Envoltorio del copy por red: una pieza por cada red pedida."),
    ("prompt/envoltorios/sin-emojis",
     "Instrucción aditiva opt-in que se inyecta tras el prompt base en flujos cuya salida nunca lleva "
     "emojis (evergreen/termómetro). El copy NO la usa: su política de emojis vive en el prompt de copy "
     "y la editorial de la marca.",
     "Envoltorio opt-in para flujos sin emojis (evergreen/termómetro)."),
)
_SENTINELA_DESCRIPCIONES_PROMPT = ".descripciones-prompt-v1"


def dir_inicial() -> Path:
    """Dir de la INICIAL (documentos por defecto que se copian al store en el 1er arranque).

    Vive DENTRO del paquete (`prompts_inicial/`) para viajar con el código (a diferencia
    del store, que es estado de usuario). Override por `KENI_PROMPTS_INICIAL` (tests);
    back-compat con el nombre legacy `KENI_TEXTO_INICIAL`.
    """
    import os

    env = os.environ.get("KENI_PROMPTS_INICIAL") or os.environ.get("KENI_TEXTO_INICIAL")
    if env:
        return Path(env).expanduser()
    # La inicial viaja junto al paquete `keni_consola`; este módulo vive un nivel más
    # abajo (paquete `libprompts`), así que se sube al directorio del paquete padre.
    return Path(__file__).resolve().parent.parent / "prompts_inicial"


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
    modelo de PIEZA (rediseno de la Prompts), si el documento tiene puntero de
    produccion los pipelines inyectan ESA version (sha git inmutable), no la working
    copy: editar es libre, pero lo que corre es lo publicado. Sin puntero (o si la BD/
    git no estan disponibles) gana la working copy del store, como siempre; y si el doc
    no existe en el store, la inicial del paquete. None si no existe en ninguno.
    """
    doc = obtener(prompt_id)
    if doc is not None:
        publicado = cuerpo_publicado(prompt_id)
        return _con_contrato(prompt_id, publicado if publicado is not None else doc.cuerpo)
    inicial = obtener_inicial(prompt_id)
    return _con_contrato(prompt_id, inicial.cuerpo) if inicial is not None else None


def _con_contrato(prompt_id: str, cuerpo: str | None) -> str | None:
    """Rellena el placeholder `{{CONTRATO_SALIDA}}` del cuerpo con el contrato de salida del prompt.

    El cuerpo EDITABLE (lo que ve la Prompts vía `obtener`) lleva el placeholder al final; el
    cuerpo EFECTIVO que ven los pipelines / el "Compilado" lleva el contrato ya resuelto al final
    del prompt. No-op para prompts sin placeholder o no estructurados.
    """
    if cuerpo is None:
        return None
    from ..prompts_contratos import resolver_contrato

    return resolver_contrato(prompt_id, cuerpo)


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
    return _con_contrato(prompt_id, doc.cuerpo) or "" if doc is not None else ""


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
    un documento recien inicializado no tiene HEAD git y el modelo de pieza caeria a su
    working copy. Esto registra esos documentos como una linea base versionada, de modo que
    los pipelines sirvan su snapshot estable. Best-effort e idempotente. Se llama al final de
    la siembra. Devuelve cuantos documentos quedaron versionados por primera vez.
    """
    from .. import versionado

    return versionado.linea_base()


def migrar_nombres_prompts(origen: Path | None = None) -> int:
    """Aplica el rediseño de nombres/ids de la Prompts al store (ONE-SHOT por sentinela).

    Pensado para el arranque del servidor, ANTES de `importar_inicial`. Devuelve cuántos
    documentos tocó (0 si ya se aplicó o no hay inicial). Idempotente: tras la primera pasada
    deja un sentinela y no vuelve a pisar el store (respeta ediciones futuras del equipo).

    Corre DOS olas en la misma pasada: la v1 (renombres de ids ya planos) y la v2 (rediseño de
    ETAPAS a verbos C, `_IDS_VIEJOS_PROMPTS_V2`). El sentinela es `.migracion-nombres-v2`, así
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
    for viejo, _nuevo in _RENOMBRES_PROMPT:
        ruta_vieja = destino_raiz.joinpath(*f"{viejo}.md".split("/"))
        if ruta_vieja.is_file():
            ruta_vieja.unlink()
            n += 1
    # (1b) OLA v2: borra los ids del sistema que nombraban una ETAPA por su nombre viejo (prompt/copy,
    #      prompt/validacion, prompt/insumos/*, …); su id con verbo C se re-siembra en el paso 2.
    #      Imprescindible en un store que ya pasó la v1 y todavía conserva esos ids.
    for viejo in _IDS_VIEJOS_PROMPTS_V2:
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
    for sub in _CARPETAS_VIEJAS:
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
    """Borra del store los prompts obsoletos (`_PROMPTS_OBSOLETOS`).

    ONE-SHOT por sentinela. Idempotente; no toca nada más del store. Devuelve cuántos borró.
    """
    destino_raiz = raiz()
    sentinela = destino_raiz / _SENTINELA_OBSOLETOS
    if sentinela.exists():
        return 0
    n = 0
    for pid in _PROMPTS_OBSOLETOS:
        ruta = destino_raiz.joinpath(*f"{pid}.md".split("/"))
        if ruta.is_file():
            ruta.unlink()
            n += 1
    sentinela.parent.mkdir(parents=True, exist_ok=True)
    escribir_atomico(sentinela, "ok\n")
    return n


def limpiar_prompts_obsoletos_v2() -> int:
    """Borra del store la OLA v2 de prompts obsoletos (`_PROMPTS_OBSOLETOS_V2`).

    El store en vivo ya pasó la v1 (sentinela aparte), así que esta ola usa su PROPIO sentinela.
    ONE-SHOT por sentinela. Idempotente; no toca nada más del store. Devuelve cuántos borró.
    """
    destino_raiz = raiz()
    sentinela = destino_raiz / _SENTINELA_OBSOLETOS_V2
    if sentinela.exists():
        return 0
    n = 0
    for pid in _PROMPTS_OBSOLETOS_V2:
        ruta = destino_raiz.joinpath(*f"{pid}.md".split("/"))
        if ruta.is_file():
            ruta.unlink()
            n += 1
    sentinela.parent.mkdir(parents=True, exist_ok=True)
    escribir_atomico(sentinela, "ok\n")
    return n


def reformatear_prompts(origen: Path | None = None) -> int:
    """Propaga al store el REFORMATO de los prompts del sistema (ONE-SHOT por sentinela).

    Reescribe cada prompt de `_REFORMATO_PROMPTS_V1` con su versión de la INICIAL nueva (frontmatter
    + cuerpo reformateado) SOLO si el cuerpo ACTUAL del store casa EXACTO con el cuerpo VIEJO conocido
    (sha256): así un prompt que el equipo haya editado NO se pisa (su hash no casa y se deja intacto).
    Idempotente por sentinela: tras correr no vuelve a tocar el store. Devuelve cuántos reescribió.

    Pensado para el DEPLOY (junto a las demás migraciones de `inicializar`), ANTES de `publicar_linea_base`,
    para que la versión que se publica como "first commit" sea ya la reformateada.
    """
    base = origen or dir_inicial()
    if not base.is_dir():
        return 0
    destino_raiz = raiz()
    sentinela = destino_raiz / _SENTINELA_REFORMATO
    if sentinela.exists():
        return 0
    n = 0
    for doc_id, sha_viejo in _REFORMATO_PROMPTS_V1:
        destino = destino_raiz.joinpath(*f"{doc_id}.md".split("/"))
        if not destino.is_file():
            continue
        actual = _leer(destino)
        if actual is None:
            continue
        if hashlib.sha256(actual.cuerpo.encode("utf-8")).hexdigest() != sha_viejo:
            continue  # editado por el equipo: respetar
        ruta_inicial = base.joinpath(*f"{doc_id}.md".split("/"))
        try:
            texto = ruta_inicial.read_text(encoding="utf-8")
        except OSError:
            continue
        escribir_atomico(destino, texto)
        n += 1
    sentinela.parent.mkdir(parents=True, exist_ok=True)
    escribir_atomico(sentinela, "ok\n")
    return n


def publicar_linea_base(*, nota: str = "first commit") -> int:
    """Publica una VERSIÓN inicial ("first commit") de cada doc activo que aún no tenga puntero.

    El rediseño de la Prompts introdujo el modelo de PUBLICACIÓN (puntero de producción en
    `texto_publicaciones`). Un store poblado ANTES de ese modelo tiene todos sus documentos SIN
    puntero, así que la UI los muestra "sin publicar". Esto fija, para cada documento del store con
    cuerpo no vacío y sin puntero, una versión inmutable (comiteando el working copy con `fijar_version`)
    y crea su puntero de producción con `nota`. La papelera queda fuera (la excluye `listar`).

    Idempotente: salta los documentos que YA tienen puntero (no re-publica). Best-effort: necesita BD
    (`db.crear_texto_publicacion`) y versionado git; si cualquiera falla para un doc, se salta ese doc
    sin abortar el resto (p. ej. arranque sin Postgres -> devuelve 0 sin romper). Devuelve cuántos
    documentos publicó por primera vez.
    """
    from .. import db
    from ._crud import listar
    from ._publicacion import produccion_de
    from ._versiones import fijar_version

    n = 0
    for doc in listar():
        if not doc.cuerpo.strip():
            continue
        try:
            if produccion_de(doc.id) is not None:
                continue  # ya publicado: no re-publicar
            sha = fijar_version(doc.id, nota=nota)
            if not sha:
                continue  # versionado apagado / sin repo
            db.crear_texto_publicacion(doc_id=doc.id, sha=sha, autor="", nota=nota)
            n += 1
        except Exception:  # noqa: BLE001 -- best-effort: un doc no publicable no aborta el resto
            continue
    return n


def migrar_contrato_salida() -> int:
    """Sustituye el contrato de salida INLINE por el placeholder `{{CONTRATO_SALIDA}}` en el store.

    ONE-SHOT por sentinela. Para cada prompt ESTRUCTURADO del registro (`prompts_contratos`), si su
    cuerpo en el store contiene el substring EXACTO del contrato, lo reemplaza por el placeholder
    (la composición lo rellena de vuelta: el prompt que ve el modelo queda BYTE-IDÉNTICO). Respeta
    ediciones del equipo: si el contrato no casa exacto, no toca ese doc. Tras reescribir, RE-PUBLICA
    el doc (mueve el puntero a la versión con placeholder) para que no aparezca "sin publicar"
    espuriamente. Idempotente; best-effort (la re-publicación necesita BD). Devuelve cuántos migró.
    """
    from .. import db
    from ..prompts_contratos import CONTRATO_POR_PROMPT, PLACEHOLDER
    from ._versiones import fijar_version

    destino_raiz = raiz()
    sentinela = destino_raiz / _SENTINELA_CONTRATO
    if sentinela.exists():
        return 0
    n = 0
    for doc_id, contrato in CONTRATO_POR_PROMPT.items():
        ruta = destino_raiz.joinpath(*f"{doc_id}.md".split("/"))
        if not ruta.is_file():
            continue
        try:
            texto = ruta.read_text(encoding="utf-8")
        except OSError:
            continue
        if PLACEHOLDER in texto or contrato not in texto:
            continue  # ya migrado, o editado por el equipo (no casa exacto): respetar
        # Quita el contrato de su sitio y deja el placeholder al FINAL del cuerpo (espejo de la
        # semilla): la composición lo rellena allí, el editor lo oculta y lo pinta read-only.
        nuevo = texto.replace("\n\n" + contrato, "").replace(contrato, "")
        while "\n\n\n" in nuevo:
            nuevo = nuevo.replace("\n\n\n", "\n\n")
        nuevo = nuevo.rstrip("\n") + "\n\n" + PLACEHOLDER + "\n"
        escribir_atomico(ruta, nuevo)
        n += 1
        try:  # re-publica la nueva versión (con placeholder) para no dejarlo "sin publicar"
            sha = fijar_version(doc_id, nota="contrato de salida")
            if sha:
                db.crear_texto_publicacion(doc_id=doc_id, sha=sha, autor="", nota="contrato de salida")
        except Exception:  # noqa: BLE001 -- best-effort: sin BD se queda "sin publicar", no rompe
            pass
    sentinela.parent.mkdir(parents=True, exist_ok=True)
    escribir_atomico(sentinela, "ok\n")
    return n


def migrar_redactar_v1() -> int:
    """Re-siembra `redactar` (simplificado + contrato al placeholder) en el store y lo publica.

    `redactar` quedó FUERA de `migrar_contrato_salida` (su contrato no era un substring limpio) y su
    working copy en el store es la versión vieja (con el ejemplo largo y el contrato inline). Esto lo
    pone al día desde la inicial NUEVA (cuerpo simplificado + `{{CONTRATO_SALIDA}}`) y lo publica, para
    que el editor lo muestre con su bloque read-only y el modelo use la versión nueva. ONE-SHOT por
    sentinela. Best-effort (la publicación necesita BD). Devuelve 1 si lo migró, 0 si no.
    """
    from .. import db
    from ._versiones import fijar_version

    destino_raiz = raiz()
    sentinela = destino_raiz / _SENTINELA_REDACTAR
    if sentinela.exists():
        return 0
    n = 0
    ruta = destino_raiz / "prompt" / "redactar.md"
    ruta_inicial = dir_inicial() / "prompt" / "redactar.md"
    if ruta.is_file() and ruta_inicial.is_file():
        try:
            escribir_atomico(ruta, ruta_inicial.read_text(encoding="utf-8"))
            n = 1
            sha = fijar_version("prompt/redactar", nota="redactar simplificado + contrato")
            if sha:
                db.crear_texto_publicacion(
                    doc_id="prompt/redactar", sha=sha, autor="", nota="redactar simplificado + contrato"
                )
        except Exception:  # noqa: BLE001 -- best-effort: no debe abortar la inicialización
            pass
    sentinela.parent.mkdir(parents=True, exist_ok=True)
    escribir_atomico(sentinela, "ok\n")
    return n


def migrar_parrilla_v1() -> int:
    """Re-siembra `importar/parrilla` (sin la sección «## Salida» editable) en el store y la publica.

    El contrato de salida de parrilla (el esquema de operaciones) pasa a INYECTARSE desde código
    (`dominio.parrilla_import_job`) justo antes del documento, para que el equipo no pueda romperlo
    desde la Prompts; el editor lo muestra read-only. Esto pone el cuerpo del store al día desde la
    inicial nueva y lo publica. ONE-SHOT por sentinela. Best-effort. Devuelve 1 si lo migró, 0 si no.
    """
    from .. import db
    from ._versiones import fijar_version

    destino_raiz = raiz()
    sentinela = destino_raiz / _SENTINELA_PARRILLA
    if sentinela.exists():
        return 0
    n = 0
    ruta = destino_raiz / "prompt" / "importar" / "parrilla.md"
    ruta_inicial = dir_inicial() / "prompt" / "importar" / "parrilla.md"
    if ruta.is_file() and ruta_inicial.is_file():
        try:
            escribir_atomico(ruta, ruta_inicial.read_text(encoding="utf-8"))
            n = 1
            sha = fijar_version("prompt/importar/parrilla", nota="parrilla: contrato de salida a código")
            if sha:
                db.crear_texto_publicacion(
                    doc_id="prompt/importar/parrilla", sha=sha, autor="",
                    nota="parrilla: contrato de salida a código",
                )
        except Exception:  # noqa: BLE001 -- best-effort: no debe abortar la inicialización
            pass
    sentinela.parent.mkdir(parents=True, exist_ok=True)
    escribir_atomico(sentinela, "ok\n")
    return n


def migrar_titulos_prompts() -> int:
    """Renombra los prompts del sistema a un título de UNA palabra (ONE-SHOT por sentinela).

    Por cada `(id, viejo, nuevo)` de `_TITULOS_UNA_PALABRA`, si el doc del store conserva el título
    VIEJO conocido, lo reescribe IN PLACE (solo el `titulo`; el cuerpo intacto) y RE-PUBLICA esa
    versión para no dejarlo "sin publicar". Si el equipo ya cambió el título, no casa y se respeta.
    Idempotente; best-effort (la re-publicación necesita BD). Devuelve cuántos renombró.
    """
    import dataclasses

    from .. import db
    from ._versiones import fijar_version

    destino_raiz = raiz()
    sentinela = destino_raiz / _SENTINELA_TITULOS
    if sentinela.exists():
        return 0
    n = 0
    for doc_id, viejo, nuevo in _TITULOS_UNA_PALABRA:
        ruta = destino_raiz.joinpath(*f"{doc_id}.md".split("/"))
        if not ruta.is_file():
            continue
        doc = _leer(ruta)
        if doc is None or doc.titulo.strip() != viejo:
            continue  # ausente o editado por el equipo: respetar
        nuevo_doc = dataclasses.replace(doc, titulo=nuevo, actualizado=_ahora_iso())
        escribir_atomico(ruta, _serializar(nuevo_doc))
        n += 1
        try:  # re-publica el doc con el título nuevo para no dejarlo "sin publicar"
            sha = fijar_version(doc_id, nota="título de una palabra")
            if sha:
                db.crear_texto_publicacion(doc_id=doc_id, sha=sha, autor="", nota="título de una palabra")
        except Exception:  # noqa: BLE001 -- best-effort: sin BD se queda "sin publicar", no rompe
            pass
    sentinela.parent.mkdir(parents=True, exist_ok=True)
    escribir_atomico(sentinela, "ok\n")
    return n


def migrar_descripciones_prompt() -> int:
    """Acorta las descripciones infladas de prompts del sistema (ONE-SHOT por sentinela).

    Por cada `(id, vieja, nueva)` de `_DESCRIPCIONES_PROMPT`, si el doc del store conserva la
    descripción VIEJA conocida, la reescribe IN PLACE (solo la `descripcion`; el cuerpo intacto) y
    RE-PUBLICA esa versión para no dejarlo "sin publicar". Si el equipo ya cambió la descripción, no
    casa y se respeta. Idempotente; best-effort (la re-publicación necesita BD). Devuelve cuántos tocó.
    """
    import dataclasses

    from .. import db
    from ._versiones import fijar_version

    destino_raiz = raiz()
    sentinela = destino_raiz / _SENTINELA_DESCRIPCIONES_PROMPT
    if sentinela.exists():
        return 0
    n = 0
    for doc_id, viejo, nuevo in _DESCRIPCIONES_PROMPT:
        ruta = destino_raiz.joinpath(*f"{doc_id}.md".split("/"))
        if not ruta.is_file():
            continue
        doc = _leer(ruta)
        if doc is None or doc.descripcion.strip() != viejo:
            continue  # ausente o editado por el equipo: respetar
        nuevo_doc = dataclasses.replace(doc, descripcion=nuevo, actualizado=_ahora_iso())
        escribir_atomico(ruta, _serializar(nuevo_doc))
        n += 1
        try:  # re-publica el doc con la descripción nueva para no dejarlo "sin publicar"
            sha = fijar_version(doc_id, nota="descripción acortada")
            if sha:
                db.crear_texto_publicacion(doc_id=doc_id, sha=sha, autor="", nota="descripción acortada")
        except Exception:  # noqa: BLE001 -- best-effort: sin BD se queda "sin publicar", no rompe
            pass
    sentinela.parent.mkdir(parents=True, exist_ok=True)
    escribir_atomico(sentinela, "ok\n")
    return n


def migrar_alcance_editorial() -> int:
    """Acota el auto-adjunto editorial: propaga al store el campo `pipelines` de cada seed editorial.

    Fin del "sobre-prompteo": un editorial sin `pipelines` se inyectaba en TODAS las etapas. La inicial
    nueva declara, por pilar, en qué pipelines aplica (marca→todas; voz→redactar/idear/priorizar;
    plataforma/tropicalización→redactar; reglas→redactar/verificar; imagen→redactar). Esta migración
    copia ese alcance al store SOLO si el doc del store aún no acota (su `pipelines` está vacío): así se
    respeta cualquier acotación que el equipo ya hubiera puesto, y `patrones` (ya en `[redactar]`) se
    deja intacto. RE-PUBLICA los que toca. ONE-SHOT por sentinela; best-effort. Devuelve cuántos tocó.
    """
    import dataclasses

    from .. import db
    from ._versiones import fijar_version

    base = dir_inicial()
    base_editorial = base / "editorial"
    destino_raiz = raiz()
    sentinela = destino_raiz / _SENTINELA_ALCANCE
    if sentinela.exists() or not base_editorial.is_dir():
        return 0
    n = 0
    for ruta_inicial in sorted(base_editorial.rglob("*.md")):
        rel = ruta_inicial.relative_to(base)
        seed = obtener_inicial(rel.with_suffix("").as_posix())
        if seed is None or not seed.pipelines:
            continue  # la inicial no acota este doc: nada que propagar
        ruta = destino_raiz.joinpath(*rel.parts)
        if not ruta.is_file():
            continue
        doc = _leer(ruta)
        if doc is None or doc.pipelines:
            continue  # ausente o ya acotado por el equipo: respetar
        nuevo_doc = dataclasses.replace(doc, pipelines=list(seed.pipelines), actualizado=_ahora_iso())
        escribir_atomico(ruta, _serializar(nuevo_doc))
        n += 1
        try:  # re-publica con el alcance nuevo para no dejarlo "sin publicar"
            sha = fijar_version(doc.id, nota="alcance editorial por pipeline")
            if sha:
                db.crear_texto_publicacion(doc_id=doc.id, sha=sha, autor="", nota="alcance editorial por pipeline")
        except Exception:  # noqa: BLE001 -- best-effort: sin BD se queda "sin publicar", no rompe
            pass
    sentinela.parent.mkdir(parents=True, exist_ok=True)
    escribir_atomico(sentinela, "ok\n")
    return n
