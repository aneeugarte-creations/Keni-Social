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

from collections.abc import Callable
from pathlib import Path
from typing import Any

from .. import biblioteca
from . import generar, jobspec

# --------------------------------------------------------------------------- #
# Proveedores de CONTEXTO de AREA (secciones de la Consola; SOLO LECTURA)      #
# --------------------------------------------------------------------------- #
#
# Un prompt puede lanzarse "sobre un area" de la Consola: el proveedor lee datos que el
# usuario YA ve (parrilla, pendientes) en modo SOLO LECTURA y los entrega como TEXTO plano
# que se incrusta como bloque de contexto. Degradan con gracia: ante cualquier fallo (sin
# datos / BD no disponible) devuelven una nota, nunca rompen el lanzamiento.

# Cuantas filas como maximo lista un proveedor de area (no inundar el prompt).
_MAX_FILAS_AREA = 20


def _resumen_pieza(p: dict[str, Any]) -> str:
    """Una linea legible de una publicacion (tolerante a la forma del dict)."""
    red = p.get("red") or "?"
    titulo = p.get("titulo") or (p.get("contenido") or "")[:80]
    cuando = p.get("fecha_programada") or ""
    cola = f" — {cuando}" if cuando else ""
    return f"- [{red}] {titulo}{cola}".rstrip()


def _area_parrilla(marca: str) -> str:
    """Contexto de la PARRILLA: proximas publicaciones programadas (de la marca)."""
    from . import publicaciones

    items, total = publicaciones.proximas_programadas(_MAX_FILAS_AREA)
    if marca:
        items = [p for p in items if p.get("marca") == marca]
    if not items:
        return "No hay publicaciones programadas próximas para esta marca."
    return f"Próximas publicaciones programadas (total {total}):\n" + "\n".join(_resumen_pieza(p) for p in items)


def _area_pendientes(marca: str) -> str:
    """Contexto de PENDIENTES: piezas en cola de aprobacion (de la marca)."""
    from . import publicaciones

    cola = publicaciones.cola_de_aprobacion()
    if marca:
        cola = [p for p in cola if p.get("marca") == marca]
    if not cola:
        return "No hay piezas pendientes de aprobación para esta marca."
    return "Piezas pendientes de aprobación:\n" + "\n".join(_resumen_pieza(p) for p in cola[:_MAX_FILAS_AREA])


# Registro de areas (extensible). id -> (etiqueta humana, proveedor(marca) -> texto).
AREAS: dict[str, tuple[str, Callable[[str], str]]] = {
    "parrilla": ("Parrilla (próximas programadas)", _area_parrilla),
    "pendientes": ("Pendientes de aprobación", _area_pendientes),
}


def areas_disponibles() -> list[dict[str, str]]:
    """Areas que un prompt puede usar como contexto (para el selector del SPA)."""
    return [{"id": k, "nombre": etiqueta} for k, (etiqueta, _) in AREAS.items()]


def area_contexto(area: str, marca: str) -> str:
    """Texto de contexto de un area. Lanza `BibliotecaError` si el area no existe."""
    entrada = AREAS.get(area)
    if entrada is None:
        raise biblioteca.BibliotecaError("Área no válida.")
    try:
        return entrada[1](marca)
    except Exception:  # noqa: BLE001 -- degradacion honesta: el area no debe romper el lanzamiento
        return "(No se pudo leer el contexto de esta área.)"


def componer(cuerpo_prompt: str, adjuntos: list[biblioteca.Documento], bloque_contexto: str) -> str:
    """Arma el prompt final autocontenido (delega en el lanzador neutro `generar`)."""
    return generar.componer(cuerpo_prompt, adjuntos, bloque_contexto)


def lanzar(
    *,
    prompt_id: str | None = None,
    texto: str | None = None,
    titulo: str = "",
    marca: str,
    adjuntos_ids: list[str] | None = None,
    bloque_contexto: str = "",
    redes_ids: list[str] | None = None,
    dir_temporal: Path | None = None,
    autor: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Lanza un prompt de la biblioteca. Devuelve el registro de generacion (para sondeo).

    `prompt_id` (de la biblioteca) o `texto` (prompt ad-hoc pegado): uno de los dos. `marca`
    debe ser una marca del catalogo. `adjuntos_ids` son documentos editoriales a adjuntar
    (ya resueltos en la UI a partir de `biblioteca.editoriales_de_marca`, ajustables).
    `bloque_contexto` es el texto del target ya resuelto por el llamante.

    MODO PIEZAS (copy): si el prompt resuelto tiene `salida == "piezas"` y llegan `redes_ids`,
    se compone con la instruccion de redes (sin emojis) y se lanza con el post-procesado de
    COPY (parsea piezas por red + AUTO-CREA borradores en la Parrilla), igual que la antigua
    generacion de copy. En cualquier otro caso se usa el camino IDENTIDAD (`PROC_PROMPT`): el
    resultado es el texto markdown y no se crean artefactos.
    """
    if not generar.marca_valida(marca):
        raise biblioteca.BibliotecaError("Marca no válida.")

    salida = ""
    if prompt_id:
        doc = biblioteca.obtener(prompt_id)
        if doc is None or doc.tipo != "prompt":
            raise biblioteca.BibliotecaError("Ese prompt no existe.")
        cuerpo_prompt = doc.cuerpo
        titulo = titulo.strip() or doc.titulo
        salida = doc.salida
        origen_historial = prompt_id.rsplit("/", 1)[-1] or "prompt"
    elif isinstance(texto, str) and texto.strip():
        cuerpo_prompt = texto
        titulo = titulo.strip() or "Prompt"
        origen_historial = "prompt"
    else:
        raise biblioteca.BibliotecaError("Hace falta un prompt (de la biblioteca o pegado).")

    adjuntos: list[biblioteca.Documento] = []
    for aid in adjuntos_ids or []:
        d = biblioteca.obtener(aid)
        if d is not None and d.tipo == "editorial":
            adjuntos.append(d)

    # MODO PIEZAS: el prompt declara salida=piezas y el lanzamiento trae redes -> copy.
    if salida == "piezas" and redes_ids:
        prompt_final = generar.componer(
            cuerpo_prompt, adjuntos, bloque_contexto,
            sin_emojis=True, redes_ids=redes_ids,
        )
        # `titulo` es el nombre del PROMPT ("Copy desde nota"), no el título del historial:
        # pasamos `titulo_dado=""` para que se DERIVE de la nota (texto_base/contexto).
        procesar_spec = jobspec.construir_copy(
            skill=origen_historial, marca=marca, redes_ids=redes_ids, titulo_dado="",
            texto_base=bloque_contexto, autor=autor,
        )
        return generar.lanzar(
            tipo="copy", titulo=titulo, marca=marca, prompt=prompt_final,
            procesar=jobspec.reconstruir_procesar({"procesar": procesar_spec}),
            procesar_spec=procesar_spec, dir_temporal=dir_temporal, autor=autor,
        )

    prompt_final = generar.componer(cuerpo_prompt, adjuntos, bloque_contexto)

    # Post-procesado IDENTIDAD: el prompt devuelve el texto markdown; no crea artefactos.
    procesar_spec = jobspec.construir_prompt_lib()
    return generar.lanzar(
        tipo="prompt", titulo=titulo, marca=marca, prompt=prompt_final,
        procesar=jobspec.reconstruir_procesar({"procesar": procesar_spec}),
        procesar_spec=procesar_spec, dir_temporal=dir_temporal, autor=autor,
    )
