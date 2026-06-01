"""Lanzamiento de un PROMPT de la biblioteca como trabajo de `claude -p` (segundo plano).

Es la UNICA primitiva de generacion del producto tras retirar el motor de skills: toma un
prompt (de la biblioteca o ad-hoc), le ADJUNTA la linea editorial elegida (auto por marca +
ajustable) y un BLOQUE DE CONTEXTO del target (contenido pegado / archivo / url / area de la
consola), compone el prompt final y lo ENCOLA reutilizando la infra de generaciones
(`encolar_job_claude` + worker + sondeo). El post-procesado es IDENTIDAD (`jobspec.PROC_PROMPT`):
el resultado es el TEXTO markdown del modelo; no crea piezas ni publicaciones.

La RESOLUCION de los targets (leer la url, guardar el archivo, leer el area) vive en la capa
que llama (API): aqui el contexto llega ya como TEXTO en `bloque_contexto`, de modo que el
dominio es PURO y testeable sin red. La composicion (prompt + editorial + contexto) si vive
aqui, que es la frontera de "como se arma el prompt".
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import biblioteca, generaciones, marcas
from . import jobspec

# Mapa id->nombre de marca (catalogo unico). Para etiquetar la generacion y validar la marca.
_MARCA_NOMBRE: dict[str, str] = dict(marcas.opciones())


def _cwd_ejecucion() -> Path:
    """cwd desde el que corre `claude` (import perezoso: evita acoplar el arranque a skills)."""
    from . import skills as dom_skills

    return dom_skills.cwd_ejecucion_skills()


def componer(cuerpo_prompt: str, adjuntos: list[biblioteca.Documento], bloque_contexto: str) -> str:
    """Arma el prompt final: cuerpo del prompt + linea editorial adjunta + contexto del target.

    Solo incluye las secciones presentes. Las secciones van separadas por reglas `---` para
    que el modelo distinga la instruccion (prompt) del material de apoyo (editorial/contexto).
    """
    partes: list[str] = [cuerpo_prompt.strip()]
    if adjuntos:
        bloques = [f"## {d.titulo}\n\n{d.cuerpo.strip()}" for d in adjuntos]
        partes.append("---\nLÍNEA EDITORIAL (material de referencia, no lo copies literal):\n\n" + "\n\n".join(bloques))
    if bloque_contexto and bloque_contexto.strip():
        partes.append("---\nCONTEXTO:\n\n" + bloque_contexto.strip())
    return "\n\n".join(partes)


def lanzar(
    *,
    prompt_id: str | None = None,
    texto: str | None = None,
    titulo: str = "",
    marca: str,
    adjuntos_ids: list[str] | None = None,
    bloque_contexto: str = "",
    dir_temporal: Path | None = None,
    autor: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Lanza un prompt de la biblioteca. Devuelve el registro de generacion (para sondeo).

    `prompt_id` (de la biblioteca) o `texto` (prompt ad-hoc pegado): uno de los dos. `marca`
    debe ser una marca del catalogo. `adjuntos_ids` son documentos editoriales a adjuntar
    (ya resueltos en la UI a partir de `biblioteca.editoriales_de_marca`, ajustables).
    `bloque_contexto` es el texto del target ya resuelto por el llamante.
    """
    import shutil

    if marca not in _MARCA_NOMBRE:
        raise biblioteca.BibliotecaError("Marca no válida.")

    if prompt_id:
        doc = biblioteca.obtener(prompt_id)
        if doc is None or doc.tipo != "prompt":
            raise biblioteca.BibliotecaError("Ese prompt no existe.")
        cuerpo_prompt = doc.cuerpo
        titulo = titulo.strip() or doc.titulo
    elif isinstance(texto, str) and texto.strip():
        cuerpo_prompt = texto
        titulo = titulo.strip() or "Prompt"
    else:
        raise biblioteca.BibliotecaError("Hace falta un prompt (de la biblioteca o pegado).")

    adjuntos: list[biblioteca.Documento] = []
    for aid in adjuntos_ids or []:
        d = biblioteca.obtener(aid)
        if d is not None and d.tipo == "editorial":
            adjuntos.append(d)
    prompt_final = componer(cuerpo_prompt, adjuntos, bloque_contexto)

    gen = generaciones.crear({
        "tipo": "prompt",
        "marca": marca,
        "etiqueta": f"{titulo} · {_MARCA_NOMBRE.get(marca, marca)}",
        "autor_id": (autor or {}).get("id", "") or "",
        "autor_nombre": (autor or {}).get("usuario", "") or "",
    })
    spec = jobspec.construir(
        prompt=prompt_final,
        procesar=jobspec.construir_prompt_lib(),
        dir_temporal=str(dir_temporal) if dir_temporal is not None else None,
    )
    try:
        generaciones.encolar_job_claude(
            gen["id"], prompt=prompt_final, cwd=_cwd_ejecucion(),
            procesar=jobspec.reconstruir_procesar(spec), dir_temporal=dir_temporal, spec=spec,
        )
    except generaciones.ColaLlenaError:
        if dir_temporal is not None:
            shutil.rmtree(dir_temporal, ignore_errors=True)
        generaciones.actualizar(gen["id"], {
            "estado": generaciones.ESTADO_ERROR, "motivo": generaciones.MOTIVO_COLA_LLENA,
            "error": "Hay demasiadas generaciones en curso; inténtalo en unos segundos.",
            "fecha_fin": generaciones.ahora_iso(),
        })
        raise
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo; reflejamos el error en el registro
        if dir_temporal is not None:
            shutil.rmtree(dir_temporal, ignore_errors=True)
        generaciones.actualizar(gen["id"], {
            "estado": generaciones.ESTADO_ERROR, "error": "No se pudo iniciar la generación.",
            "fecha_fin": generaciones.ahora_iso(),
        })
    return generaciones.obtener(gen["id"]) or gen
