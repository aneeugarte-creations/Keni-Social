"""Lanzamiento de un PROMPT de la texto como trabajo de `claude -p` (segundo plano).

Es la UNICA primitiva de generacion del producto tras retirar el motor de skills: toma un
prompt (de la texto o ad-hoc), le ADJUNTA la linea editorial elegida (auto por marca +
ajustable) y un BLOQUE DE CONTEXTO del target (contenido pegado / archivo / url / area de la
consola), compone el prompt final y lo ENCOLA reutilizando la infra de generaciones
(`encolar_job_claude` + worker + sondeo). El post-procesado es IDENTIDAD (`jobspec.PROC_PROMPT`):
el resultado es el TEXTO markdown del modelo; no crea piezas ni piezas.

La RESOLUCION de los targets (leer la url, guardar el archivo, leer el area) vive en la capa
que llama (API): aqui el contexto llega ya como TEXTO en `bloque_contexto`, de modo que el
dominio es PURO y testeable sin red. La composicion (prompt + editorial + contexto) si vive
aqui, que es la frontera de "como se arma el prompt".
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from .. import libprompts
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
    """Una linea legible de una pieza (tolerante a la forma del dict)."""
    red = p.get("red") or "?"
    titulo = p.get("titulo") or (p.get("contenido") or "")[:80]
    cuando = p.get("fecha_programada") or ""
    cola = f" — {cuando}" if cuando else ""
    return f"- [{red}] {titulo}{cola}".rstrip()


def _area_parrilla(marca: str) -> str:
    """Contexto de la PARRILLA: proximas piezas programadas (de la marca)."""
    from . import piezas

    items, total = piezas.proximas_programadas(_MAX_FILAS_AREA)
    if marca:
        items = [p for p in items if p.get("marca") == marca]
    if not items:
        return "No hay piezas programadas próximas para esta marca."
    return f"Próximas piezas programadas (total {total}):\n" + "\n".join(_resumen_pieza(p) for p in items)


def _area_pendientes(marca: str) -> str:
    """Contexto de PENDIENTES: piezas en cola de aprobacion (de la marca)."""
    from . import piezas

    cola = piezas.cola_de_aprobacion()
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


def area_contexto(area: str, marca: str) -> str:
    """Texto de contexto de un area. Lanza `PromptsError` si el area no existe."""
    entrada = AREAS.get(area)
    if entrada is None:
        raise libprompts.PromptsError("Área no válida.")
    try:
        return entrada[1](marca)
    except Exception:  # noqa: BLE001 -- degradacion honesta: el area no debe romper el lanzamiento
        return "(No se pudo leer el contexto de esta área.)"


def lanzar(
    *,
    prompt_id: str | None = None,
    texto: str | None = None,
    titulo: str = "",
    marca: str,
    adjuntos_ids: list[str] | None = None,
    bloque_contexto: str = "",
    titulo_contenido: str = "",
    redes_ids: list[str] | None = None,
    dir_temporal: Path | None = None,
    autor: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Lanza un prompt de la texto. Devuelve el registro de generacion (para sondeo).

    `prompt_id` (de la texto) o `texto` (prompt ad-hoc pegado): uno de los dos. `marca`
    debe ser una marca del catalogo. `adjuntos_ids` son documentos editoriales a adjuntar
    (ya resueltos en la UI a partir de `libprompts.editoriales_de_marca`, ajustables).
    `bloque_contexto` es el texto del target ya resuelto por el llamante. `titulo_contenido`
    es un título del CONTENIDO sugerido por el llamante (p. ej. el titular real de una URL):
    en MODO PIEZAS titula los borradores, evitando que se derive de la 1ª línea del bloque
    (que en una URL es el AVISO de extracción automática). Vacío => se deriva como antes.

    MODO PIEZAS (copy): si el prompt resuelto tiene `salida == "piezas"` y llegan `redes_ids`,
    se compone con la instruccion de redes (la politica de emojis la marcan el prompt y la
    editorial adjunta, no un hardcode) y se lanza con el post-procesado de COPY (parsea piezas
    por red + AUTO-CREA borradores en la Parrilla), igual que la antigua generacion de copy.
    En cualquier otro caso se usa el camino IDENTIDAD (`PROC_PROMPT`): el resultado es el
    texto markdown y no se crean artefactos.
    """
    if not generar.marca_valida(marca):
        raise libprompts.PromptsError("Marca no válida.")

    salida = ""
    if prompt_id:
        doc = libprompts.obtener(prompt_id)
        if doc is None or doc.tipo != "prompt":
            raise libprompts.PromptsError("Ese prompt no existe.")
        # MODELO DE PIEZA: si el prompt tiene puntero de produccion se inyecta ESA
        # version (sha fijado); sin puntero, la working copy como siempre (fallback suave).
        publicado = libprompts.cuerpo_publicado(prompt_id)
        cuerpo_prompt = publicado if publicado is not None else doc.cuerpo
        titulo = titulo.strip() or doc.titulo
        salida = doc.salida
        origen_historial = prompt_id.rsplit("/", 1)[-1] or "prompt"
    elif isinstance(texto, str) and texto.strip():
        cuerpo_prompt = texto
        titulo = titulo.strip() or "Prompt"
        origen_historial = "prompt"
    else:
        raise libprompts.PromptsError("Hace falta un prompt (de la texto o pegado).")

    adjuntos: list[libprompts.Documento] = []
    for aid in adjuntos_ids or []:
        d = libprompts.obtener(aid)
        if d is not None and d.tipo == "editorial":
            adjuntos.append(d)

    # MODO PIEZAS: el prompt declara salida=piezas y el lanzamiento trae redes -> copy.
    if salida == "piezas" and redes_ids:
        # INDICACIONES DEL EQUIPO: MODO PIEZAS crea piezas reales, así que (como el resto del
        # copy, cuyo punto único es `generar.componer_copy`) inyecta las indicaciones VIGENTES
        # del cajón `contexto` de los Insumos. No rutamos por `componer_copy`: MODO PIEZAS usa
        # OTRA composición (adjuntos elegidos en la UI + una pieza POR red, no `adjuntos_copy`
        # + copy unificado), así que replicamos solo su INYECCIÓN. Import perezoso (igual que
        # componer_copy) para no acoplar; best-effort: sin ítems / sin BD el prompt no cambia.
        from . import indicaciones as indicaciones_dom

        prompt_final = generar.componer(
            cuerpo_prompt, adjuntos, bloque_contexto, redes_ids=redes_ids,
            indicaciones=indicaciones_dom.bloque_para_marca(marca),
        )
        # `titulo` es el nombre del PROMPT ("Copy desde nota"), no el título del historial.
        # `titulo_dado` titula los borradores: si el llamante sugiere un título del contenido
        # (titular de la URL) lo usamos; si no, "" para que se DERIVE de la nota (texto_base).
        procesar_spec = jobspec.construir_copy(
            prompt_id=origen_historial, marca=marca, redes_ids=redes_ids,
            titulo_dado=titulo_contenido.strip(),
            texto_base=bloque_contexto, autor=autor,
        )
        return generar.lanzar(
            tipo="copy", titulo=titulo, marca=marca, prompt=prompt_final,
            procesar=jobspec.reconstruir_procesar({"procesar": procesar_spec}),
            procesar_spec=procesar_spec, dir_temporal=dir_temporal, autor=autor,
            # MODO PIEZAS = SALIDA ESTRUCTURADA (se parsea a piezas por red + auto-crea borradores;
            # el usuario no ve la salida cruda): bajo riesgo aunque el material sea no confiable. No
            # se veta la web por-callsite; queda la veta global `Bash Write Edit`. El camino
            # IDENTIDAD de abajo tampoco la veta (igual que hoy).
        )

    prompt_final = generar.componer(cuerpo_prompt, adjuntos, bloque_contexto)

    # Post-procesado IDENTIDAD: el prompt devuelve el texto markdown; no crea artefactos.
    procesar_spec = jobspec.construir_prompt_lib()
    return generar.lanzar(
        tipo="prompt", titulo=titulo, marca=marca, prompt=prompt_final,
        procesar=jobspec.reconstruir_procesar({"procesar": procesar_spec}),
        procesar_spec=procesar_spec, dir_temporal=dir_temporal, autor=autor,
        # Etapa EXPLÍCITA: el tipo='prompt' no la deriva; sellarla agrupa el gasto de los
        # lanzamientos de la biblioteca bajo su fila «Prompts» en la pestaña Herramientas.
        etapa="Prompts",
    )
