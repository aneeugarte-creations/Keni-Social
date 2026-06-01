"""Spec SERIALIZABLE de un job de generacion (#130 Fase 2 / ADR 0002 Fase B).

El back ya NO ejecuta `claude -p` en proceso: ENCOLA un job (este spec, como JSON) y un
WORKER lo clava y lo ejecuta —in-proceso en local, en un servicio aparte en hosted—. El
reto del desacoplo es que el POST-PROCESADO de una generacion (`procesar`) era un CLOSURE
de Python que el back construia (parsear piezas, registrar historial, crear borradores,
marcar un item de RSS, parsear hashtags). Un worker en OTRO proceso no puede recibir un
closure; SI puede recibir sus PARAMETROS y reconstruirlo, porque toda esa logica es codigo
de DOMINIO PURO (`dominio.skills`, `dominio.hashtags`, `repos`) que el worker comparte.

Por eso un job se serializa como:
  - `prompt` (str): el prompt de `claude -p` YA renderizado por el back.
  - `cwd_kind` ("ejecucion_skills" | "skills"): COMO resolver el cwd en el worker (las
    rutas absolutas pueden diferir entre back y worker; el worker resuelve via
    `dominio.skills`, que lee las MISMAS env vars `KENI_SKILLS_*`).
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
from . import skills as dom_skills

# Versiona el spec por si su forma cambia (un worker viejo no debe malinterpretar uno nuevo).
VERSION = 1

# Como resolver el cwd de `claude` en el worker (las rutas absolutas no viajan; el worker
# las resuelve via `dominio.skills`, que lee KENI_SKILLS_*). "ejecucion_skills" es el dir
# que contiene `.claude/skills` (skills de copy/RSS/hashtags); "skills" es la raiz.
CWD_EJECUCION = "ejecucion_skills"
CWD_SKILLS = "skills"
# cwd NEUTRO para prompts AUTOCONTENIDOS (Biblioteca y features migradas): un dir writable
# sin skills (el corpus editorial va dentro del prompt, no se descubre por cwd).
CWD_GENERACION = "generacion"

# Kinds de post-procesado (`procesar`). Mapean a las fabricas de `dominio.skills`/`qa`.
PROC_COPY = "copy"
PROC_DOCUMENTO = "documento"
PROC_HASHTAGS = "hashtags"
PROC_QA = "qa"
# Biblioteca de prompts: post-procesado IDENTIDAD. Un prompt de la biblioteca devuelve el
# texto markdown tal cual (ya queda en `salida` del registro); NO crea piezas/publicaciones.
PROC_PROMPT = "prompt"


def _autor_spec(autor: dict[str, str] | None) -> dict[str, str] | None:
    """Normaliza el autor a un dict simple serializable (o None)."""
    if not autor:
        return None
    return {"id": autor.get("id", "") or "", "usuario": autor.get("usuario", "") or ""}


def construir_copy(
    *,
    skill: str,
    marca: str,
    redes_ids: list[str],
    titulo_dado: str,
    texto_base: str,
    con_imagenes: bool = False,
    autor: dict[str, str] | None = None,
    fuente_id: str | None = None,
    clave: str | None = None,
) -> dict[str, Any]:
    """Spec del post-procesado de PIEZAS (copy/RSS): parsea piezas + crea borradores.

    `fuente_id`/`clave` (RSS): si vienen, ademas se MARCA el item del feed como usado al
    completar con exito (el wrap que antes hacia `api/rss.generar`). Sin ellos, es copy puro.
    """
    return {
        "kind": PROC_COPY,
        "skill": skill,
        "marca": marca,
        "redes_ids": list(redes_ids),
        "titulo_dado": titulo_dado,
        "texto_base": texto_base,
        "con_imagenes": bool(con_imagenes),
        "autor": _autor_spec(autor),
        "fuente_id": fuente_id or "",
        "clave": clave or "",
    }


def construir_documento(
    *,
    skill: str,
    marca: str,
    titulo_base: str,
    titulo_dado: str = "",
    con_imagenes: bool = False,
    autor: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Spec del post-procesado de un DOCUMENTO (skill de salida documento, sin piezas)."""
    return {
        "kind": PROC_DOCUMENTO,
        "skill": skill,
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
    *, marca: str, titulo: str, autor: dict[str, str] | None = None
) -> dict[str, Any]:
    """Spec del post-procesado de QA EDITORIAL (parsea el informe; no crea borradores)."""
    return {"kind": PROC_QA, "marca": marca, "titulo": titulo, "autor": _autor_spec(autor)}


def construir_prompt_lib() -> dict[str, Any]:
    """Spec del post-procesado de un PROMPT de la biblioteca (identidad: solo el texto)."""
    return {"kind": PROC_PROMPT}


def construir(
    *,
    prompt: str,
    procesar: dict[str, Any],
    cwd_kind: str = CWD_EJECUCION,
    dir_temporal: str | None = None,
) -> dict[str, Any]:
    """Arma el spec completo de un job (prompt + cwd + post-procesado + temporal)."""
    return {
        "version": VERSION,
        "prompt": prompt,
        "cwd_kind": cwd_kind,
        "dir_temporal": dir_temporal,
        "procesar": procesar,
    }


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
    """Resuelve el cwd de `claude` en el worker segun `cwd_kind` (via `dominio.skills`).

    Las rutas absolutas no viajan en el spec: el worker las resuelve aqui, leyendo las
    MISMAS env vars `KENI_SKILLS_*` que el back. Por defecto el dir de ejecucion de skills.
    """
    if spec.get("cwd_kind") == CWD_GENERACION:
        return cwd_generacion()
    if spec.get("cwd_kind") == CWD_SKILLS:
        return dom_skills.cwd_skills()
    return dom_skills.cwd_ejecucion_skills()


def cwd_generacion() -> Path:
    """Dir writable desde el que corre `claude` para prompts AUTOCONTENIDOS (sin skills).

    No depende de `skills-copy/`: el corpus editorial viaja DENTRO del prompt. Es un dir
    estable y escribible bajo la config (se crea si falta).
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

    if kind == PROC_QA:
        return dom_qa.construir_procesar_qa(p["marca"], p.get("titulo", ""), autor=autor)

    if kind == PROC_DOCUMENTO:
        return dom_copy.construir_procesar_documento(
            p["skill"], p["marca"], titulo_base=p.get("titulo_base", ""),
            titulo_dado=p.get("titulo_dado", ""), con_imagenes=bool(p.get("con_imagenes")),
            autor=autor,
        )

    if kind == PROC_COPY:
        procesar_copy = dom_copy.construir_procesar_copy(
            p["skill"], p["marca"], redes_ids=list(p.get("redes_ids") or []),
            titulo_dado=p.get("titulo_dado", ""), texto_base=p.get("texto_base", ""),
            con_imagenes=bool(p.get("con_imagenes")), autor=autor,
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
