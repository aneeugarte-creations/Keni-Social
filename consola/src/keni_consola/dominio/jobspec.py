"""Spec SERIALIZABLE de un job de generacion (#130 Fase 2 / ADR 0002 Fase B).

Un job se serializa como:
  - `prompt` (str): el prompt de `claude -p` YA renderizado por el back.
  - `cwd_kind` ("generacion"): COMO resolver el cwd en el worker. Hay UN solo cwd: el dir NEUTRO y writable `cwd_generacion` (los prompts son
    autocontenidos; el corpus editorial viaja DENTRO del prompt, no se descubre por cwd).
  - `dir_temporal` (str | None): dir de la subida (foto/clip); el worker lo borra al final
    y lo pasa como `--add-dir`. En hosted los temporales de subida no se
    comparten entre back y worker: ver la nota de `media`/`clip` en el README de deploy.
  - `procesar` (dict): el KIND de post-procesado + sus parametros serializables.

`construir(...)` arma el spec desde los parametros de la generacion.
`reconstruir_procesar(spec)` + `cwd(spec)` lo deshacen en el worker. El spec NO lleva closures ni objetos: solo str/list/dict/bool/None.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import copy as dom_copy
from . import verificar_fuente as dom_verificar

# Versiona el spec por si su forma cambia (un worker viejo no debe malinterpretar uno nuevo).
VERSION = 1

# PRIORIDAD de despacho del job en la cola (entero, mayor = antes). Viaja DENTRO del spec
# (asi los seams inyectables de encolado no cambian de firma); `cola.encolar` la copia a la
# columna `jobs.prioridad` y `reclamar_job` ordena por ella. Un lanzamiento MANUAL del equipo
# (API/MCP) pasa primero; el lote de fondo del pipeline/autogen cede el paso.
#
# TRES niveles (CONTRATO con el pipeline de noticias): `PRIORIDAD_BREAKING` es para el fondo
# URGENTE (una breaking corroborada no debe esperar detras del lote ordinario) — adelanta al
# pipeline normal pero NUNCA a una persona, y a ojos de la economia de tokens SIGUE siendo
# fondo (prioridad < MANUAL): el corte de presupuesto `solo_manual` tambien lo frena. Quien
# decide QUE es breaking es el pipeline (dominio del feed); aqui solo se despacha.
PRIORIDAD_PIPELINE = 0
PRIORIDAD_BREAKING = 5
PRIORIDAD_MANUAL = 10
# "Este primero" del Monitor (decisión humana EXPLÍCITA sobre un job concreto): por encima
# de TODO lo pendiente, también de otros manuales. Sin este nivel, priorizar un job manual
# era un no-op (manual→manual empata y decide el id aleatorio del desempate: a veces
# adelantaba, a veces no — el botón del Monitor mentía la mitad de las veces).
PRIORIDAD_URGENTE = 20

# cwd NEUTRO para prompts AUTOCONTENIDOS (Texto y TODAS las generaciones de texto): un
# dir writable sin skills (el corpus editorial va DENTRO del prompt, no se descubre por cwd).
CWD_GENERACION = "generacion"

# Kinds de post-procesado (`procesar`). Mapean a las fabricas de `dominio.copy`/`verificación`/`hashtags`.
PROC_COPY = "copy"
PROC_DOCUMENTO = "documento"
# verificación de la FUENTE (pre-copy, rediseño QPC): verificación PERMISIVA de la nota de origen por TEMA. Persiste el verificación estructurado (`no_verificado`/`problema`) + hallazgos
# sobre el `contenido` (tema), para que CD genere copy SOLO de los `no_verificado`.
PROC_VERIFICACION_FUENTE = "verificacion-fuente"
# Texto de prompts: post-procesado IDENTIDAD. Un prompt de la texto devuelve el
# texto markdown tal cual (ya queda en `salida` del registro); NO crea piezas/piezas.
PROC_PROMPT = "prompt"
# Importacion de PARRILLA desde documento: parsea el JSON de claude, re-construye el contexto
# de la semana desde la BD, valida con `dominio.parrilla_import` y guarda las operaciones +
# resumen en la fila `parrilla_propuesta` (estado pendiente | error). NO toca el calendario.
PROC_PARRILLA_IMPORT = "parrilla-import"
# Taller EVERGREEN / brainstorming: parsea el JSON `{"ideas":[...]}` de claude y crea filas
# `evergreen_ideas` en estado `propuesta` (origen `ia`) para que el equipo las apruebe/descarte.
# NO genera contenido todavia: solo PROPONE ideas (la generacion ocurre al aprobar+generar).
PROC_EVERGREEN_IDEAS = "evergreen-ideas"
# Insumos del dia (cajones): parsea el JSON `{"items":[...]}` de claude (Haiku), normaliza e
# INSERTA `insumos_item`, y deja el lote en estado `listo`/`error`. El back ya NO ejecuta
# `claude -p` (no tiene binario ni token): el WORKER corre el parseo. Mismo patron que copy.
PROC_INSUMOS = "insumos"
# Importacion de CALENDARIO desde un archivo NO tabular (PDF/Word/imagen/captura): parsea el
# JSON `{"filas":[...]}` de claude (Haiku) e IMPORTA al tablero (`importar_a_tablero`). El camino
# tabular (.xlsx/.csv) sigue siendo SINCRONO en el back (no usa claude); solo el camino IA se
# ENCOLA al worker (el back no tiene claude).
PROC_IMPORT_CALENDARIO = "import-calendario"
# Crítica IA (post-aprobación, con VISIÓN): tras los dos OK humanos, `claude -p` critica la pieza
# (arte sintético, coherencia imagen↔texto, sustancia, rigor, hashtags, voz) y VOTA el nivel
# "Crítica IA" de la cadena. El worker baja el arte de S3 a un dir temporal (`prefetch_s3` +
# `dir_temporal`, igual que la importación de parrilla) para que claude lo LEA. El post-procesado
# parsea el verificación JSON y, vía `repos`, aprueba el nivel IA (→ se programa sola) o lo rechaza
# con un comentario sin resolver (→ frena y queda en el feed). Solo el `pieza_id` viaja.
PROC_CRITICA_IA = "critica-ia"
# Sugerir hashtags (post-Redactar): `claude -p` READ-ONLY elige de la biblioteca de la marca los
# hashtags más relevantes para un borrador SIN hashtags y los guarda en `pieza.hashtags_sugeridos`
# (el feed los ofrece en gris para aceptar/rechazar). No toca el copy. Solo el `pieza_id` viaja.
PROC_SUGERIR_HASHTAGS = "sugerir-hashtags"

# ------------------------------------------------------------------------------------------- #
# Jobs de PROCESO (no-claude): el SEAM del motor de video (Ola VIDEO).                         #
# ------------------------------------------------------------------------------------------- #
# Estos KINDS encolan trabajo GENERICO (render de video con ffmpeg, transcripcion ASR con
# faster-whisper) que NO usa claude, pero SI reutiliza la infra de `generaciones`/`jobs`/worker
# para colgarse de Actividad IA + streaming. El worker DESPACHA un job de proceso a su EJECUTOR
# (ver `EJECUTORES_PROCESO`) en vez de reconstruir un `procesar` de claude. El spec de un job de
# proceso es PLANO: {"kind": <PROC_*>, ...params}  (sin `prompt`/`procesar`/`cwd`; el ejecutor
# lee los params).
PROC_RENDER_VIDEO = "render-video"
PROC_TRANSCRIBIR = "transcribir"
# Generacion de ARTE (imagen) del auto-pipeline: un job de PROCESO. La llamada HTTP al
# proveedor de imagen + la subida a S3 + el adjuntado a la pieza son I/O (y algo de CPU), encajan
# en el carril de proceso (NO bloquea el copy) y heredan idempotencia (clave estable en
# `dominio.generar.lanzar_arte`) + reintentos/sueltos del limpiador. Su ejecutor (`autogen_ilustrar.
# ejecutar_arte_job`) llama a `media.generar_imagen` y reporta estado como ASR/video. NO gasta
# tokens de la suscripcion claude (proveedor de imagen aparte), asi que —como los demas procesos—
# queda EXENTO del corte por presupuesto de tokens; solo el kill switch PAUSADO lo frena.
PROC_IMAGEN = "imagen"

# KINDS de proceso (no-claude). El worker, al reclamar un job, mira si su `spec["kind"]` esta
# aqui; si lo esta, despacha al ejecutor; si no, sigue el camino `claude` de siempre.
KINDS_PROCESO = frozenset({PROC_RENDER_VIDEO, PROC_TRANSCRIBIR, PROC_IMAGEN})

# Registro de EJECUTORES por kind de proceso. Valor = "modulo:funcion" (path importable),
# resuelto por import PEREZOSO en `resolver_ejecutor_proceso` (asi `jobspec` no importa los
# motores al cargar: el back/CI no necesita ffmpeg/whisper para importar este modulo). Cada
# ejecutor tiene firma `ejecutar(gen_id: str, spec: dict) -> None` y reporta progreso/estado/
# errores via `generaciones.actualizar(...)` (igual que el camino claude marca terminal).
EJECUTORES_PROCESO: dict[str, str] = {
    PROC_RENDER_VIDEO: "keni_consola.motores.estudio_video:ejecutar_render",
    PROC_TRANSCRIBIR: "keni_consola.motores.transcripcion:ejecutar_transcripcion",
    # El ejecutor del arte vive junto al resto de la logica de auto-arte (seleccion + dedup +
    # registro), que ya conoce `media`/`repos`/`generaciones`; el worker lo despacha igual que
    # ASR/video, sin que worker.py tenga que conocer la imagen (dispatch GENERICO de proceso).
    PROC_IMAGEN: "keni_consola.autogen_ilustrar:ejecutar_arte_job",
}


def es_kind_proceso(spec: dict[str, Any]) -> bool:
    """True si el spec es un job de PROCESO (no-claude) — su `kind` esta en `KINDS_PROCESO`.

    Un job de proceso lleva el `kind` a NIVEL RAIZ del spec (`spec["kind"]`), no en `procesar`
    (ese es el post-procesado del camino claude). El worker usa esto para elegir el dispatch.
    """
    return isinstance(spec, dict) and spec.get("kind") in KINDS_PROCESO


def resolver_ejecutor_proceso(kind: str):  # noqa: ANN201 -- Callable[[str, dict], None]
    """Importa y devuelve el ejecutor de un kind de proceso (import PEREZOSO).

    Resuelve "modulo:funcion" de `EJECUTORES_PROCESO` SOLO al despachar el job, no al importar
    `jobspec` (asi el back/CI no cargan ffmpeg/whisper de balde). Lanza `ValueError` si el kind
    no esta registrado (defensa: nunca debe pasar si `es_kind_proceso` filtro antes).
    """
    import importlib

    ruta = EJECUTORES_PROCESO.get(kind)
    if not ruta:
        raise ValueError(f"kind de proceso desconocido: {kind!r}")
    modulo_nombre, _, funcion_nombre = ruta.partition(":")
    modulo = importlib.import_module(modulo_nombre)
    return getattr(modulo, funcion_nombre)


def construir_proceso(kind: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Arma el spec PLANO de un job de proceso: `{"kind": kind, **params}`.

    A diferencia de `construir(...)` (camino claude: prompt + procesar + cwd), un job de proceso
    no lleva prompt ni post-procesado: solo su `kind` y los params que su ejecutor leera. Lo usa
    `generaciones.encolar_job_proceso`. Lanza `ValueError` si `kind` no es un kind de proceso.
    """
    if kind not in KINDS_PROCESO:
        raise ValueError(f"'{kind}' no es un kind de proceso valido (KINDS_PROCESO).")
    spec: dict[str, Any] = {"version": VERSION, "kind": kind}
    spec.update(params or {})
    return spec


def _autor_spec(autor: dict[str, str] | None) -> dict[str, str] | None:
    """Normaliza el autor a un dict simple serializable (o None)."""
    if not autor:
        return None
    return {"id": autor.get("id", "") or "", "usuario": autor.get("usuario", "") or ""}


def construir_copy(
    *,
    prompt_id: str,
    marca: str,
    redes_ids: list[str],
    titulo_dado: str,
    texto_base: str,
    con_imagenes: bool = False,
    autor: dict[str, str] | None = None,
    fuente_id: str | None = None,
    clave: str | None = None,
    publicacion_id: str = "",
    imagen_fuente: str = "",
    fotos_notas: list[dict[str, str]] | None = None,
    tipo_contenido: str = "",
    revision_inicial: str = "",
    url_fuente: str = "",
    limpiar_pendiente: bool = False,
    etiqueta_exito: str = "",
) -> dict[str, Any]:
    """Spec del post-procesado de PIEZAS (copy/RSS): parsea piezas + crea borradores.

    `fuente_id`/`clave` (RSS): si vienen, ademas se MARCA el item del feed como usado al
    completar con exito (el wrap que antes hacia `api/rss.generar`). Sin ellos, es copy puro.
    `publicacion_id` (lista viva): si viene, el borrador se NIDA bajo ese tema del tablero al
    reconstruir el post-procesado en el worker; sin el, borrador suelto (back-compat).
    `imagen_fuente`/`tipo_contenido` (RSS de marca propia): si vienen, cada borrador nace con
    la imagen original del articulo (`tipo_contenido='fuente'`) lista para usarse.
    `fotos_notas` (pipeline, historias): catálogo de fotos de fuente propia por NOTA
    (`[{titulo, imagen}, …]`, mismo orden numerado que vio el modelo en el prompt). Si la
    salida del copy declara `tipo=carrusel` con `slides`, el post-procesado HORNEA una placa
    por slide (titular + su foto por número) y arma la pieza CARRUSEL. None/[] = sin catálogo
    (los slides salen como placa de solo texto si el modelo elige carrusel).
    `revision_inicial` (pipeline QPC): verificación por DEFECTO de cada borrador cuando la salida
    no trae uno propio (p. ej. `no_verificado` para que la pieza herede el aviso de la verificación de
    la fuente). "" = comportamiento de hoy (el verificación sale de la propia salida del copy).
    `url_fuente` (RSS, trazabilidad): URL CANONICA de la nota de origen. Si viene, el post-
    procesado la PERSISTE en `contenido.url_fuente` del tema padre de cada borrador (dedup por
    URL). "" = no se toca (comportamiento de hoy).
    `limpiar_pendiente` (pipeline): si True, el post-procesado LIMPIA `contenido.copy_pendiente`
    del tema AL COMPLETAR CON EXITO (dedup al exito, no al lanzar: un copy fallido se reintenta
    en el siguiente barrido; mientras el job esta EN CURSO, la clave de idempotencia de
    `dominio.generar.lanzar` evita el doble lanzamiento).
    `etiqueta_exito` (autogen): nombre de etiqueta a asignar al tema AL COMPLETAR CON EXITO
    (p. ej. `autogen`): mismo principio de dedup-al-exito que `limpiar_pendiente`.
    """
    return {
        "kind": PROC_COPY,
        "prompt_id": prompt_id,
        "marca": marca,
        "redes_ids": list(redes_ids),
        "titulo_dado": titulo_dado,
        "texto_base": texto_base,
        "con_imagenes": bool(con_imagenes),
        "autor": _autor_spec(autor),
        "fuente_id": fuente_id or "",
        "clave": clave or "",
        "publicacion_id": publicacion_id or "",
        "imagen_fuente": imagen_fuente or "",
        "fotos_notas": [dict(f) for f in (fotos_notas or []) if isinstance(f, dict)],
        "tipo_contenido": tipo_contenido or "",
        "revision_inicial": revision_inicial or "",
        "url_fuente": url_fuente or "",
        "limpiar_pendiente": bool(limpiar_pendiente),
        "etiqueta_exito": etiqueta_exito or "",
    }


def construir_documento(
    *,
    prompt_id: str,
    marca: str,
    titulo_base: str,
    titulo_dado: str = "",
    con_imagenes: bool = False,
    autor: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Spec del post-procesado de un DOCUMENTO (prompt de salida documento, sin piezas)."""
    return {
        "kind": PROC_DOCUMENTO,
        "prompt_id": prompt_id,
        "marca": marca,
        "titulo_base": titulo_base,
        "titulo_dado": titulo_dado,
        "con_imagenes": bool(con_imagenes),
        "autor": _autor_spec(autor),
    }


def construir_verificacion_fuente(
    *,
    marca: str,
    titulo: str,
    autor: dict[str, str] | None = None,
    cluster_id: str = "",
) -> dict[str, Any]:
    """Spec del post-procesado de la verificación de la FUENTE (pre-copy).

    El verificación se sella en la HISTORIA (`cluster_id`, ADR 0011 F3): verificación sobre la fuente antes de
    materializar contenido (el worker sella `noticias_clusters.verificacion_fuente`).
    """
    return {
        "kind": PROC_VERIFICACION_FUENTE,
        "marca": marca,
        "titulo": titulo,
        "autor": _autor_spec(autor),
        "cluster_id": cluster_id or "",
    }


def construir_prompt_lib() -> dict[str, Any]:
    """Spec del post-procesado de un PROMPT de la texto (identidad: solo el texto)."""
    return {"kind": PROC_PROMPT}


def construir_parrilla_import(*, propuesta_id: str) -> dict[str, Any]:
    """Spec del post-procesado de la IMPORTACION de parrilla (#parrilla-import).

    `propuesta_id` es la fila `parrilla_propuesta` a actualizar. NO lleva semana: el contexto
    de validacion se re-construye en el worker a partir de las FECHAS de las operaciones que
    devuelva claude (un documento puede cubrir varias semanas / un año entero).
    """
    return {
        "kind": PROC_PARRILLA_IMPORT,
        "propuesta_id": propuesta_id,
    }


def construir_evergreen_ideas(
    *, marca: str, generacion_id: str = "", autor: dict[str, str] | None = None
) -> dict[str, Any]:
    """Spec del post-procesado del taller EVERGREEN: crea filas `evergreen_ideas` en estado propuesta.

    `marca` es la marca de las ideas; `generacion_id` (opcional) traza el lote a su generacion
    IA. El worker parsea `{"ideas":[...]}` y llama a `repos.crear_evergreen_idea` por cada idea.
    """
    return {
        "kind": PROC_EVERGREEN_IDEAS,
        "marca": marca,
        "generacion_id": generacion_id or "",
        "autor": _autor_spec(autor),
    }


def construir_insumos(
    *, lote_id: str, cajon: str, fecha: str, marca_defecto: str = ""
) -> dict[str, Any]:
    """Spec del post-procesado de un lote de INSUMOS (cajones): parsea + inserta items.

    `lote_id` es el lote (estado `parseando`) al que pertenecen los items; `cajon`/`fecha`
    los necesita el normalizador (`recibir_parse._items_desde_registros`). `marca_defecto`
    (id canónico de la marca que el equipo eligió al aportar el lote) es el fallback de marca
    para los ítems que la IA no clasifique: así el filtro por marca del cajón los encuentra en
    vez de dejarlos sin marca. El worker parsea `{"items":[...]}`, normaliza, INSERTA los items
    y deja el lote `listo` (o `error`).
    """
    return {
        "kind": PROC_INSUMOS,
        "lote_id": lote_id,
        "cajon": cajon,
        "fecha": fecha,
        "marca_defecto": marca_defecto or "",
    }


def construir_import_calendario(
    *, marca_defecto: str = "", autor: dict[str, str] | None = None
) -> dict[str, Any]:
    """Spec del post-procesado de la IMPORTACION de calendario por IA (#import-calendario).

    `marca_defecto` (id canonico) se aplica a las filas sin marca reconocida; `autor` atribuye
    los contenidos creados. El worker parsea `{"filas":[...]}` de Haiku con
    `importador_calendario.parsear_respuesta_claude` e IMPORTA al tablero (`importar_a_tablero`).
    """
    return {
        "kind": PROC_IMPORT_CALENDARIO,
        "marca_defecto": marca_defecto or "",
        "autor": _autor_spec(autor),
    }


def construir_critica_ia(*, pieza_id: str) -> dict[str, Any]:
    """Spec del post-procesado de la CRÍTICA IA: parsea el verificación y vota el nivel IA.

    `pieza_id` es la pieza (`pieza_id`) cuyo nivel "Crítica IA" se decide. El worker
    reconstruye el callback (que toca `repos`) vía `dominio.critica_ia`; no lleva más estado: la
    pieza, su cadena y su contenido se releen frescos en el worker al aplicar el verificación.
    """
    return {"kind": PROC_CRITICA_IA, "pieza_id": pieza_id}


def construir_sugerir_hashtags(*, pieza_id: str) -> dict[str, Any]:
    """Spec del post-procesado de SUGERIR HASHTAGS: filtra la salida y la guarda en la pieza.

    `pieza_id` es la pieza cuyos `hashtags_sugeridos` se proponen. El worker reconstruye el
    callback (que toca `repos`) vía `dominio.sugerir_hashtags`; la pieza se relee fresca al aplicar.
    """
    return {"kind": PROC_SUGERIR_HASHTAGS, "pieza_id": pieza_id}


def construir(
    *,
    prompt: str,
    procesar: dict[str, Any],
    cwd_kind: str = CWD_GENERACION,
    dir_temporal: str | None = None,
    prefetch_s3: dict[str, str] | None = None,
    endurecer: dict[str, Any] | None = None,
    prioridad: int = PRIORIDAD_MANUAL,
) -> dict[str, Any]:
    """Arma el spec completo de un job (prompt + cwd + post-procesado + temporal).

    `endurecer` (opcional): overrides de seguridad para ESE run (herramientas vetadas extra,
    max-turns/max-budget mas bajos). Solo ENDURECEN; ausente = comportamiento global. Lo usa
    un job READ-ONLY como la importacion de parrilla (vetar Write/Edit/Bash/MCP de escritura).
    `prefetch_s3` (opcional): `{clave, destino}` para que el WORKER baje un objeto de S3 a la
    ruta `destino` ANTES de correr claude (solo lo pone la importacion de parrilla: el doc viaja
    por S3, no por un disco compartido entre back y worker).
    """
    return {
        "version": VERSION,
        "prompt": prompt,
        "cwd_kind": cwd_kind,
        "dir_temporal": dir_temporal,
        "prefetch_s3": prefetch_s3 or None,
        "procesar": procesar,
        "endurecer": endurecer or None,
        "prioridad": int(prioridad),
    }


def prioridad(spec: dict[str, Any]) -> int:
    """Prioridad de despacho del spec (def `PRIORIDAD_MANUAL` si falta/ilegible).

    El default conserva la semantica para specs VIEJOS aun en cola (sin el campo) y para los
    jobs de PROCESO (render/ASR, iniciados por una persona): se despachan como manuales.
    """
    try:
        return int(spec.get("prioridad", PRIORIDAD_MANUAL))
    except (TypeError, ValueError):
        return PRIORIDAD_MANUAL


def endurecer(spec: dict[str, Any]) -> dict[str, Any] | None:
    """Overrides de endurecimiento del run (o None). El worker los pasa a `lanzar_job_claude`."""
    e = spec.get("endurecer")
    return e if isinstance(e, dict) and e else None


def prefetch_s3(spec: dict[str, Any]) -> dict[str, str] | None:
    """Instruccion de PREFETCH de S3 del worker (o None).

    Devuelve `{clave, destino}` SOLO si el spec lo trae (lo pone la importacion de parrilla):
    `clave` es la key del objeto en el almacen de media y `destino` la ruta local absoluta a la
    que el worker debe escribir los bytes ANTES de lanzar claude. None (o forma invalida) =>
    sin prefetch.
    """
    p = spec.get("prefetch_s3")
    if isinstance(p, dict) and p.get("clave") and p.get("destino"):
        return {"clave": str(p["clave"]), "destino": str(p["destino"])}
    return None


def serializar(spec: dict[str, Any]) -> str:
    """Spec -> JSON (texto) para guardar en la fila de la cola."""
    return json.dumps(spec, ensure_ascii=False)


def deserializar(texto: str | dict[str, Any]) -> dict[str, Any]:
    """JSON (texto) -> spec. Lanza `ValueError` si no es un objeto JSON valido.

    Acepta tambien un dict YA deserializado: tras migrar `jobs.spec` a `jsonb` (ADR 0012),
    `dict_row` devuelve la columna como dict, no como str. Asi el call-site (`cola._reclamar`)
    no cambia y la migracion es transparente.
    """
    datos = texto if isinstance(texto, dict) else json.loads(texto)
    if not isinstance(datos, dict):
        raise ValueError("spec de job no es un objeto")
    return datos


# --------------------------------------------------------------------------- #
# Reconstruccion en el worker                                                  #
# --------------------------------------------------------------------------- #


def cwd(spec: dict[str, Any]) -> Path:
    """Resuelve el cwd de `claude` en el worker. Siempre el dir NEUTRO de generacion.

    Tras retirar el sistema de skills, todas las generaciones de texto son prompts
    AUTOCONTENIDOS y corren desde un cwd writable sin skills (`cwd_generacion`). Las rutas
    absolutas no viajan en el spec: el worker las resuelve aqui. Cualquier `cwd_kind` legado
    en un spec viejo de la cola degrada a este mismo dir (ya no existe cwd "de skills").
    """
    return cwd_generacion()


def cwd_generacion() -> Path:
    """Dir writable desde el que corre `claude` para prompts AUTOCONTENIDOS (sin skills).

    El corpus editorial viaja DENTRO del prompt. Es un dir estable y escribible bajo la
    config (se crea si falta).
    """
    from .. import rutas

    d = rutas.dir_config() / "generacion-cwd"
    d.mkdir(parents=True, exist_ok=True)
    return d


def dir_temporal(spec: dict[str, Any]) -> Path | None:
    """Dir temporal de la subida (o None). El worker lo pasa como `--add-dir` y lo borra."""
    dt = spec.get("dir_temporal")
    return Path(dt) if isinstance(dt, str) and dt else None


def reconstruir_procesar(spec: dict[str, Any]):  # noqa: ANN201 -- generaciones.Procesar (evita ciclo de tipos)
    """Reconstruye el callback `procesar(salida, metricas) -> dict` desde el spec.

    Reusa las MISMAS fabricas de dominio que usaba el back en proceso, asi el resultado de
    un job es identico antes/despues del desacoplo. Para RSS, envuelve el `procesar` de copy
    para marcar el item del feed como usado al completar con exito (igual que antes).
    """
    p = spec.get("procesar") or {}
    kind = p.get("kind")
    autor = p.get("autor")

    if kind == PROC_PROMPT:
        # Identidad: el texto markdown ya queda en `salida` del registro; no hay artefactos.
        def procesar(_salida: str, _metricas: object) -> dict[str, object]:
            return {}
        return procesar

    if kind == PROC_PARRILLA_IMPORT:
        # Import perezoso: el factory toca BD (`repos`), no cabe en este modulo de dominio puro.
        from . import parrilla_import_job

        return parrilla_import_job.construir_procesar_parrilla_import(
            propuesta_id=p["propuesta_id"]
        )

    if kind == PROC_EVERGREEN_IDEAS:
        # Import perezoso: el factory toca BD (`repos`), no cabe en este modulo de dominio puro.
        from . import idear as dom_idear

        return dom_idear.construir_procesar_evergreen_ideas(
            marca=p.get("marca", "") or "",
            generacion_id=p.get("generacion_id", "") or "",
        )

    if kind == PROC_INSUMOS:
        # Import perezoso: el factory toca BD (`repos`), no cabe en este modulo de dominio puro.
        from . import recibir_parse

        return recibir_parse.construir_procesar_insumos(
            lote_id=p["lote_id"], cajon=p.get("cajon", ""), fecha=p.get("fecha", ""),
            marca_defecto=p.get("marca_defecto", "") or "",
        )

    if kind == PROC_IMPORT_CALENDARIO:
        # Import perezoso: el factory toca BD (`repos`); `importador_calendario` vive en el
        # paquete raiz (no en `dominio`), por eso el import sube un nivel.
        from .. import importador_calendario

        return importador_calendario.construir_procesar_import(
            marca_defecto=p.get("marca_defecto", "") or "", autor=autor,
        )

    if kind == PROC_CRITICA_IA:
        # Import perezoso: el factory toca BD (`repos`, `auto_programar`), no cabe en este modulo
        # de dominio puro. Vota el nivel "Crítica IA" de la cadena segun el verificación de claude.
        from . import critica_ia as dom_critica

        return dom_critica.construir_procesar_critica_ia(
            pieza_id=p["pieza_id"]
        )

    if kind == PROC_SUGERIR_HASHTAGS:
        # Import perezoso: el factory toca BD (`repos`) y la biblioteca de hashtags.
        from . import sugerir_hashtags as dom_sugerir

        return dom_sugerir.construir_procesar_sugerir_hashtags(
            pieza_id=p["pieza_id"]
        )

    if kind == PROC_VERIFICACION_FUENTE:
        return dom_verificar.construir_procesar_verificacion_fuente(
            p["marca"], p.get("titulo", ""), autor=autor,
            cluster_id=p.get("cluster_id", "") or "",
        )

    if kind == PROC_DOCUMENTO:
        return dom_copy.construir_procesar_documento(
            p["prompt_id"], p["marca"], titulo_base=p.get("titulo_base", ""),
            titulo_dado=p.get("titulo_dado", ""), con_imagenes=bool(p.get("con_imagenes")),
            autor=autor,
        )

    if kind == PROC_COPY:
        procesar_copy = dom_copy.construir_procesar_copy(
            p["prompt_id"], p["marca"], redes_ids=list(p.get("redes_ids") or []),
            titulo_dado=p.get("titulo_dado", ""), texto_base=p.get("texto_base", ""),
            con_imagenes=bool(p.get("con_imagenes")), autor=autor,
            publicacion_id=p.get("publicacion_id", "") or "",
            imagen_fuente=p.get("imagen_fuente", "") or "",
            fotos_notas=[f for f in (p.get("fotos_notas") or []) if isinstance(f, dict)],
            tipo_contenido=p.get("tipo_contenido", "") or "",
            revision_inicial=p.get("revision_inicial", "") or "",
            url_fuente=p.get("url_fuente", "") or "",
        )
        fuente_id = p.get("fuente_id") or ""
        clave = p.get("clave") or ""
        base = procesar_copy
        if fuente_id and clave:
            # RSS: tras el copy, marca el item del feed como usado (solo si la fuente existe).
            from .. import repos

            def procesar_rss(salida: str, metricas: object) -> dict[str, object]:
                resultado = procesar_copy(salida, metricas)
                if repos.obtener_fuente_rss(fuente_id) is not None:
                    repos.marcar_item(fuente_id, clave, True)
                return resultado

            base = procesar_rss

        publicacion_id = p.get("publicacion_id", "") or ""
        if not publicacion_id:
            return base
        # COPY NIDADO BAJO UN TEMA (pipeline/autogen): acciones POST-EXITO sobre el tema.
        #   - dedup AL EXITO (no al lanzar): limpiar `copy_pendiente` / etiquetar `autogen`
        #     SOLO cuando los borradores ya existen. Un copy fallido conserva sus marcas de
        #     "pendiente" y el barrido lo REINTENTA; el doble lanzamiento en curso lo evita
        #     la clave de idempotencia de `dominio.generar.lanzar`.
        #   - ENCADENADO copy->arte: dispara la etapa de Ilustración de ESE tema al instante (si su
        #     gate esta activo), sin esperar al siguiente barrido (que queda de red de
        #     seguridad). Todo best-effort: el copy YA esta hecho; nada de esto lo rompe.
        limpiar_pendiente = bool(p.get("limpiar_pendiente"))
        etiqueta_exito = str(p.get("etiqueta_exito") or "").strip()

        def procesar_pipeline(salida: str, metricas: object) -> dict[str, object]:
            resultado = base(salida, metricas)
            from .. import repos

            if limpiar_pendiente:
                try:
                    repos.actualizar_publicacion(publicacion_id, {"copy_pendiente": ""})
                except Exception:  # noqa: BLE001 -- dedup best-effort; el copy ya esta hecho
                    pass
            if etiqueta_exito:
                try:
                    _asignar_etiqueta_por_nombre(publicacion_id, etiqueta_exito)
                except Exception:  # noqa: BLE001 -- dedup best-effort; el copy ya esta hecho
                    pass
            try:
                from ..pipeline_contenido import encadenar_ilustrar_tras_redactar

                encadenar_ilustrar_tras_redactar(publicacion_id)
            except Exception:  # noqa: BLE001 -- el encadenado nunca rompe el post-procesado
                pass
            return resultado

        return procesar_pipeline

    raise ValueError(f"kind de post-procesado desconocido: {kind!r}")


def _asignar_etiqueta_por_nombre(publicacion_id: str, nombre: str) -> None:
    """Asigna al contenido la etiqueta llamada `nombre` (creandola si falta). Best-effort.

    Pequeno helper del dedup-al-exito del copy autogen (etiqueta `autogen`): mismo criterio
    de normalizacion que `autogen_redactar._id_etiqueta_autogen`, sin acoplar este modulo de
    dominio a aquel (import de `repos` perezoso, igual que el resto de posts-procesados).
    """
    from .. import repos

    objetivo = " ".join(nombre.strip().lower().split())
    et_id = ""
    for et in repos.listar_etiquetas():
        if " ".join(str(et.get("nombre", "")).strip().lower().split()) == objetivo:
            et_id = et.get("id", "")
            break
    if not et_id:
        et_id = repos.crear_etiqueta(nombre=nombre).get("id", "")
    if et_id:
        repos.asignar_etiqueta(publicacion_id, et_id)
