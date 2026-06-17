"""Línea editorial: auto-adjunto por marca + resolución de PIPELINES.

Qué prompt base y qué editoriales alimentan a cada pipeline, y diagnóstico de
completitud editorial de una marca.
"""

from __future__ import annotations

from ._comun import (
    _CARPETAS_GLOBALES,
    _CLASES_GLOBALES,
    PILARES_EDITORIALES,
    PIPELINES,
    Documento,
    PromptsError,
)
from ._crud import listar
from ._inicial import cuerpo_efectivo

__all__ = [
    "editoriales_de_marca",
    "es_editorial_global",
    "prompt_base_de",
    "editoriales_de_pipeline",
    "previsualizar_pipeline",
    "validacion_editorial",
]


def es_editorial_global(doc: Documento) -> bool:
    """True si el documento editorial aplica a TODAS las marcas.

    Un doc es GLOBAL si cuelga de una carpeta global (`global`, `comun`, ...) o si su clase es
    global (`plataforma`/`tropicalizacion`/`reglas`) Y NO está atado a una marca concreta. Una
    versión POR-MARCA de esas clases (p. ej. `editorial/rrss/claro-sports/plataformas` con
    `marcas=[claro-sports]`, o cualquier doc bajo `rrss/<marca>/`) es ESPECÍFICA de su marca, no
    global. Mismo criterio que el auto-adjunto (`editoriales_de_marca`).
    """
    segmentos = doc.carpeta.split("/") if doc.carpeta else []
    if any(s in _CARPETAS_GLOBALES for s in segmentos):
        return True  # global explícito (carpeta `global`/`comun`/...)
    if doc.marcas or "rrss" in segmentos:
        return False  # atado a una marca (por `marcas` o por colgar de `rrss/<marca>/`)
    return doc.clase in _CLASES_GLOBALES


def editoriales_de_marca(marca: str, *, pipeline: str | None = None) -> list[Documento]:
    """Documentos EDITORIALES que aplican por defecto al lanzar un prompt con esa marca.

    Incluye (a) los GLOBALES (clase plataforma/tropicalizacion/reglas, aplican a todas las
    marcas) y (b) los especificos de la marca (clase marca/voz cuyo `marcas` incluye `marca`).
    El usuario puede luego anadir/quitar en la UI; esto es solo el conjunto por defecto.

    Filtro del rediseno (retrocompatible):
      - PIPELINE (opcional): si se pasa, un doc se incluye solo si NO acota pipelines
        (`pipelines == []`, aplica a todos -> comportamiento clasico) o si incluye `pipeline`.
        Asi un editorial puede entrar en `copy` pero no en `verificación`, sin romper a los docs viejos
        (que no declaran `pipelines` y siguen aplicando a todo).

    Orden: por `prioridad` (menor primero), luego PILAR (orden de `PILARES_EDITORIALES`,
    despues el resto) y, a igualdad, por id; auto-adjunto estable y legible.
    """
    seleccion: list[Documento] = []
    for doc in listar(tipo="editorial"):
        if pipeline is not None and doc.pipelines and pipeline not in doc.pipelines:
            continue
        # La pertenencia a marca se deriva de la CARPETA (la marca es una carpeta): un doc bajo
        # `…/<marca>/…` aplica a esa marca; uno bajo `global/` (o comun/general/todas) aplica a
        # TODAS. Se conservan `clase`/`marcas` por retrocompatibilidad con los docs existentes.
        segmentos = doc.carpeta.split("/") if doc.carpeta else []
        es_de_marca = bool(marca) and (marca in doc.marcas or marca in segmentos)
        if es_editorial_global(doc) or es_de_marca:
            seleccion.append(doc)

    orden = {clase: i for i, clase in enumerate(PILARES_EDITORIALES)}
    seleccion.sort(key=lambda d: (d.prioridad, orden.get(d.clase, len(orden)), d.id))
    return seleccion


def prompt_base_de(pipeline: str) -> str:
    """Id del prompt base EFECTIVO de un pipeline.

    Resolucion: si EXISTE un prompt que declara `rol == registro.rol` y lista este `pipeline`
    en sus `pipelines`, ese REBINDEA al pipeline (gana el de menor `prioridad`, luego id). Si
    nadie rebindea, cae al `prompt_defecto` del registro (comportamiento actual).
    """
    spec = PIPELINES.get(pipeline)
    if spec is None:
        raise PromptsError(f"Pipeline desconocido: {pipeline}.")
    rol = spec.get("rol", "")
    candidatos = [
        d for d in listar(tipo="prompt")
        if rol and d.rol == rol and pipeline in d.pipelines
    ]
    if candidatos:
        candidatos.sort(key=lambda d: (d.prioridad, d.id))
        return candidatos[0].id
    return spec.get("prompt_defecto", "")


def editoriales_de_pipeline(marca: str, pipeline: str) -> list[Documento]:
    """Editoriales auto-adjuntables a `pipeline` para `marca` (atajo con filtro de pipeline)."""
    return editoriales_de_marca(marca, pipeline=pipeline)


def previsualizar_pipeline(
    pipeline: str, marca: str, contexto: str = "", redes_ids: list[str] | None = None
) -> dict[str, object]:
    """Devuelve el prompt ENSAMBLADO que recibiria `claude -p` para `pipeline`+`marca`.

    "Lo que inyectas es lo que ves": usa el MISMO compositor que la generacion real, sin
    lanzar nada. Para el pipeline `redactar` pasa por la MISMA composicion que `lanzar_copy`
    (adjuntos de copy con reglas de imagen + instruccion de redes con limites): `redes_ids`
    son las redes a previsualizar; sin ellas se previsualiza con TODAS (un lanzamiento
    real siempre las trae). Devuelve `{pipeline, prompt_base_id, prompt_efectivo, adjuntos,
    falta_base}`. `adjuntos` es la lista (id/titulo/clase) de adjuntos, en orden.
    """
    from ..dominio import generar  # perezoso: generar importa texto

    base_id = prompt_base_de(pipeline)
    cuerpo = cuerpo_efectivo(base_id) if base_id else None
    if pipeline == "redactar":
        from .. import redes as catalogo_redes

        ids = list(redes_ids) if redes_ids else catalogo_redes.ids()
        adjuntos = generar.adjuntos_copy(marca)
        prompt = (
            generar.componer_copy(cuerpo, marca=marca, contexto=contexto, redes_ids=ids)
            if cuerpo is not None
            else ""
        )
    else:
        adjuntos = editoriales_de_pipeline(marca, pipeline)
        prompt = generar.componer(cuerpo or "", adjuntos, contexto) if cuerpo is not None else ""
    return {
        "pipeline": pipeline,
        "prompt_base_id": base_id,
        "falta_base": cuerpo is None,
        "prompt_efectivo": prompt,
        "adjuntos": [
            {"id": d.id, "titulo": d.titulo, "clase": d.clase, "prioridad": d.prioridad}
            for d in adjuntos
        ],
    }


def validacion_editorial(marca: str) -> dict[str, object]:
    """Diagnostica si la linea editorial de `marca` cubre los 4 PILARES obligatorios.

    Devuelve `{completa, faltan, recomendacion, pilares}`:
      - `completa`: True si los 4 pilares (`PILARES_EDITORIALES`) tienen al menos un
        documento editorial con cuerpo.
      - `faltan`: lista de pilares sin cubrir (en el orden canonico).
      - `recomendacion`: frase en espanol lista para mostrar (vacia si esta completa).
      - `pilares`: mapa pilar -> bool (cubierto o no), para una UI mas detallada.

    Si `marca` es vacio, los pilares ESPECIFICOS (marca/voz) se consideran no cubiertos
    (no hay marca de la que colgarlos): se exige elegir una marca primero.
    """
    if marca:
        docs = editoriales_de_marca(marca)
    else:
        docs = [d for d in listar(tipo="editorial") if d.clase in _CLASES_GLOBALES]
    # Un pilar solo cuenta como CUBIERTO si su documento tiene cuerpo (un editorial vacio no
    # aporta contexto): el filtro de no-vacio vive aqui, donde se decide la completitud.
    cubiertas = {d.clase for d in docs if d.cuerpo.strip()}
    pilares = {p: (p in cubiertas) for p in PILARES_EDITORIALES}
    faltan = [p for p in PILARES_EDITORIALES if not pilares[p]]

    if not marca:
        recomendacion = "Elige una marca para validar su línea editorial."
    elif not faltan:
        recomendacion = ""
    else:
        nombres = ", ".join(faltan)
        recomendacion = (
            f"La línea editorial de esta marca está incompleta: falta(n) {nombres}. "
            "Crea o completa esos documentos en la Texto (sección Editorial) para "
            "que la generación tenga contexto suficiente."
        )
    return {
        "completa": not faltan,
        "faltan": faltan,
        "recomendacion": recomendacion,
        "pilares": pilares,
    }
