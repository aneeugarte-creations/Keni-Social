"""Spec SERIALIZABLE de un job de generacion (#130 Fase 2 / ADR 0002 Fase B).

El back ya NO ejecuta `claude -p` en proceso: ENCOLA un job (este spec, como JSON) y un
WORKER lo clava y lo ejecuta —in-proceso en local, en un servicio aparte en hosted—. El
reto del desacoplo es que el POST-PROCESADO de una generacion (`procesar`) era un CLOSURE
de Python que el back construia (parsear piezas, registrar historial, crear borradores,
marcar un item de RSS, parsear hashtags). Un worker en OTRO proceso no puede recibir un
closure; SI puede recibir sus PARAMETROS y reconstruirlo, porque toda esa logica es codigo
de DOMINIO PURO (`dominio.copy`, `dominio.qa_editorial`, `dominio.hashtags`, `repos`) que el
worker comparte.

Por eso un job se serializa como:
  - `prompt` (str): el prompt de `claude -p` YA renderizado por el back.
  - `cwd_kind` ("generacion"): COMO resolver el cwd en el worker. Tras retirar el sistema de
    skills hay UN solo cwd: el dir NEUTRO y writable `cwd_generacion` (los prompts son
    autocontenidos; el corpus editorial viaja DENTRO del prompt, no se descubre por cwd).
  - `dir_temporal` (str | None): dir de la subida (foto/clip); el worker lo borra al final
    y lo pasa como `--add-dir` (igual que antes). En hosted los temporales de subida no se
    comparten entre back y worker: ver la nota de `media`/`clip` en el README de deploy.
  - `procesar` (dict): el KIND de post-procesado + sus parametros serializables.

`construir(...)` arma el spec desde los mismos parametros que antes recibian
`lanzar_generacion_copy`/`_skill`/RSS/hashtags. `reconstruir_procesar(spec)` + `cwd(spec)`
lo deshacen en el worker. El spec NO lleva closures ni objetos: solo str/list/dict/bool/None.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import copy as dom_copy
from . import hashtags as dom_hashtags
from . import qa_editorial as dom_qa

# Versiona el spec por si su forma cambia (un worker viejo no debe malinterpretar uno nuevo).
VERSION = 1

# cwd NEUTRO para prompts AUTOCONTENIDOS (Biblioteca y TODAS las generaciones de texto): un
# dir writable sin skills (el corpus editorial va DENTRO del prompt, no se descubre por cwd).
# Tras retirar el sistema de skills es el ÚNICO cwd de `claude`; ya no hay cwd "de skills".
CWD_GENERACION = "generacion"

# Kinds de post-procesado (`procesar`). Mapean a las fabricas de `dominio.copy`/`qa`/`hashtags`.
PROC_COPY = "copy"
PROC_GALERIA = "galeria"
PROC_DOCUMENTO = "documento"
PROC_HASHTAGS = "hashtags"
PROC_QA = "qa"
# QA de la FUENTE (pre-copy, rediseño QPC): criba PERMISIVA de la nota de origen por TEMA antes
# de generar copy. Persiste el veredicto estructurado (`no_verificado`/`problema`) + hallazgos
# sobre el `contenido` (tema), para que CD genere copy SOLO de los `no_verificado`.
PROC_QA_FUENTE = "qa-fuente"
# Biblioteca de prompts: post-procesado IDENTIDAD. Un prompt de la biblioteca devuelve el
# texto markdown tal cual (ya queda en `salida` del registro); NO crea piezas/publicaciones.
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
# tabular (.xlsx/.csv) sigue siendo SINCRONO en el back (no usa claude); solo el camino IA, que
# antes ejecutaba `claude -p` en la peticion, se ENCOLA al worker (el back no tiene claude).
PROC_IMPORT_CALENDARIO = "import-calendario"

# ------------------------------------------------------------------------------------------- #
# Jobs de PROCESO (no-claude): el SEAM del motor de video (Ola VIDEO).                         #
# ------------------------------------------------------------------------------------------- #
# La cola/worker existentes solo corrian `claude -p`. Estos KINDS encolan trabajo GENERICO
# (render de video con ffmpeg, transcripcion ASR con faster-whisper) que NO usa claude, pero
# SI reutiliza la infra de `generaciones`/`jobs`/worker para colgarse de Actividad IA +
# streaming. El worker DESPACHA un job de proceso a su EJECUTOR (ver `EJECUTORES_PROCESO`) en
# vez de reconstruir un `procesar` de claude. El spec de un job de proceso es PLANO:
#   {"kind": <PROC_*>, ...params}  (sin `prompt`/`procesar`/`cwd`; el ejecutor lee los params).
PROC_RENDER_VIDEO = "render-video"
PROC_TRANSCRIBIR = "transcribir"

# KINDS de proceso (no-claude). El worker, al reclamar un job, mira si su `spec["kind"]` esta
# aqui; si lo esta, despacha al ejecutor; si no, sigue el camino `claude` de siempre.
KINDS_PROCESO = frozenset({PROC_RENDER_VIDEO, PROC_TRANSCRIBIR})

# Registro de EJECUTORES por kind de proceso. Valor = "modulo:funcion" (path importable),
# resuelto por import PEREZOSO en `resolver_ejecutor_proceso` (asi `jobspec` no importa los
# motores al cargar: el back/CI no necesita ffmpeg/whisper para importar este modulo). Cada
# ejecutor tiene firma `ejecutar(gen_id: str, spec: dict) -> None` y reporta progreso/estado/
# errores via `generaciones.actualizar(...)` (igual que el camino claude marca terminal).
EJECUTORES_PROCESO: dict[str, str] = {
    PROC_RENDER_VIDEO: "keni_consola.motores.estudio_video:ejecutar_render",
    PROC_TRANSCRIBIR: "keni_consola.motores.transcripcion:ejecutar_transcripcion",
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
    contenido_id: str = "",
    imagen_fuente: str = "",
    tipo_contenido: str = "",
    veredicto_inicial: str = "",
    url_fuente: str = "",
) -> dict[str, Any]:
    """Spec del post-procesado de PIEZAS (copy/RSS): parsea piezas + crea borradores.

    `fuente_id`/`clave` (RSS): si vienen, ademas se MARCA el item del feed como usado al
    completar con exito (el wrap que antes hacia `api/rss.generar`). Sin ellos, es copy puro.
    `contenido_id` (lista viva): si viene, el borrador se NIDA bajo ese tema del tablero al
    reconstruir el post-procesado en el worker; sin el, borrador suelto (back-compat).
    `imagen_fuente`/`tipo_contenido` (RSS de marca propia): si vienen, cada borrador nace con
    la imagen original del articulo (`tipo_contenido='fuente'`) lista para usarse.
    `veredicto_inicial` (pipeline QPC): veredicto por DEFECTO de cada borrador cuando la salida
    no trae uno propio (p. ej. `no_verificado` para que la pieza herede el aviso de la criba de
    la fuente). "" = comportamiento de hoy (el veredicto sale de la propia salida del copy).
    `url_fuente` (RSS, trazabilidad): URL CANONICA de la nota de origen. Si viene, el post-
    procesado la PERSISTE en `contenido.url_fuente` del tema padre de cada borrador (dedup por
    URL). "" = no se toca (comportamiento de hoy).
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
        "contenido_id": contenido_id or "",
        "imagen_fuente": imagen_fuente or "",
        "tipo_contenido": tipo_contenido or "",
        "veredicto_inicial": veredicto_inicial or "",
        "url_fuente": url_fuente or "",
    }


def construir_galeria(
    *,
    prompt_id: str,
    marca: str,
    redes_ids: list[str],
    titulo_base: str,
    titulo_dado: str = "",
    autor: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Spec del post-procesado de una GALERÍA (termómetro): piezas sin auto-borradores."""
    return {
        "kind": PROC_GALERIA,
        "prompt_id": prompt_id,
        "marca": marca,
        "redes_ids": list(redes_ids),
        "titulo_base": titulo_base,
        "titulo_dado": titulo_dado,
        "autor": _autor_spec(autor),
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


def construir_hashtags() -> dict[str, Any]:
    """Spec del post-procesado de HASHTAGS (parsea los hashtags de la salida)."""
    return {"kind": PROC_HASHTAGS}


def construir_qa(
    *,
    marca: str,
    titulo: str,
    autor: dict[str, str] | None = None,
    plataforma_id: str = "",
    contenido_id: str = "",
    copy_hash: str = "",
) -> dict[str, Any]:
    """Spec del post-procesado de QA EDITORIAL (parsea el informe; no crea borradores).

    `plataforma_id`/`contenido_id`/`copy_hash` (item A): si la revision se lanzo SOBRE una pieza
    concreta, viajan en el spec para que el WORKER persista el veredicto atado a ella.
    """
    return {
        "kind": PROC_QA,
        "marca": marca,
        "titulo": titulo,
        "autor": _autor_spec(autor),
        "plataforma_id": plataforma_id or "",
        "contenido_id": contenido_id or "",
        "copy_hash": copy_hash or "",
    }


def construir_qa_fuente(
    *,
    marca: str,
    titulo: str,
    autor: dict[str, str] | None = None,
    contenido_id: str = "",
) -> dict[str, Any]:
    """Spec del post-procesado de la QA de la FUENTE (pre-copy).

    `contenido_id` es el TEMA cribado: el worker persiste sobre él el veredicto estructurado
    (`no_verificado`/`problema`) + hallazgos, para que la fase CD genere copy solo de los OK.
    """
    return {
        "kind": PROC_QA_FUENTE,
        "marca": marca,
        "titulo": titulo,
        "autor": _autor_spec(autor),
        "contenido_id": contenido_id or "",
    }


def construir_prompt_lib() -> dict[str, Any]:
    """Spec del post-procesado de un PROMPT de la biblioteca (identidad: solo el texto)."""
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
    los necesita el normalizador (`insumos_parse._items_desde_registros`). `marca_defecto`
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


def construir(
    *,
    prompt: str,
    procesar: dict[str, Any],
    cwd_kind: str = CWD_GENERACION,
    dir_temporal: str | None = None,
    prefetch_s3: dict[str, str] | None = None,
    endurecer: dict[str, Any] | None = None,
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
    }


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


def deserializar(texto: str) -> dict[str, Any]:
    """JSON (texto) -> spec. Lanza `ValueError` si no es un objeto JSON valido."""
    datos = json.loads(texto)
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

    if kind == PROC_HASHTAGS:
        def procesar(salida: str, _metricas: object) -> dict[str, object]:
            return {"hashtags": dom_hashtags.parsear_hashtags(salida)}
        return procesar

    if kind == PROC_PARRILLA_IMPORT:
        # Import perezoso: el factory toca BD (`repos`), no cabe en este modulo de dominio puro.
        from . import parrilla_import_job

        return parrilla_import_job.construir_procesar_parrilla_import(
            propuesta_id=p["propuesta_id"]
        )

    if kind == PROC_EVERGREEN_IDEAS:
        # Import perezoso: el factory toca BD (`repos`), no cabe en este modulo de dominio puro.
        from . import evergreen as dom_evergreen

        return dom_evergreen.construir_procesar_evergreen_ideas(
            marca=p.get("marca", "") or "",
            generacion_id=p.get("generacion_id", "") or "",
        )

    if kind == PROC_INSUMOS:
        # Import perezoso: el factory toca BD (`repos`), no cabe en este modulo de dominio puro.
        from . import insumos_parse

        return insumos_parse.construir_procesar_insumos(
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

    if kind == PROC_QA:
        return dom_qa.construir_procesar_qa(
            p["marca"], p.get("titulo", ""), autor=autor,
            plataforma_id=p.get("plataforma_id", "") or "",
            contenido_id=p.get("contenido_id", "") or "",
            copy_hash=p.get("copy_hash", "") or "",
        )

    if kind == PROC_QA_FUENTE:
        return dom_qa.construir_procesar_qa_fuente(
            p["marca"], p.get("titulo", ""), autor=autor,
            contenido_id=p.get("contenido_id", "") or "",
        )

    if kind == PROC_GALERIA:
        return dom_copy.construir_procesar_galeria(
            p["prompt_id"], p["marca"], redes_ids=list(p.get("redes_ids") or []),
            titulo_base=p.get("titulo_base", ""), titulo_dado=p.get("titulo_dado", ""),
            autor=autor,
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
            contenido_id=p.get("contenido_id", "") or "",
            imagen_fuente=p.get("imagen_fuente", "") or "",
            tipo_contenido=p.get("tipo_contenido", "") or "",
            veredicto_inicial=p.get("veredicto_inicial", "") or "",
            url_fuente=p.get("url_fuente", "") or "",
        )
        fuente_id = p.get("fuente_id") or ""
        clave = p.get("clave") or ""
        if not (fuente_id and clave):
            return procesar_copy

        # RSS: tras el copy, marca el item del feed como usado (solo si la fuente existe).
        from .. import repos

        def procesar_rss(salida: str, metricas: object) -> dict[str, object]:
            resultado = procesar_copy(salida, metricas)
            if repos.obtener_fuente_rss(fuente_id) is not None:
                repos.marcar_item(fuente_id, clave, True)
            return resultado

        return procesar_rss

    raise ValueError(f"kind de post-procesado desconocido: {kind!r}")
