"""Catálogo: a qué PROCESO(S) se inyecta cada prompt de la Prompts.

Fuente única para la transparencia "¿a qué proceso se inyecta este prompt?" que muestra el
estudio de texto (pestaña «Prompts»). El mapeo vive en CÓDIGO a propósito: es propiedad de qué
módulo inyecta el prompt en un agente, no del contenido editable; así no se desincroniza cuando
el equipo edita el documento. Cuando se cablea un prompt nuevo (lectura por
`libprompts.cuerpo_efectivo`), se añade aquí su entrada.

Las claves son los IDs de documento (`prompt/...`); los valores, etiquetas legibles del/los
proceso(s) donde el prompt se inyecta a la IA. `procesos_de` devuelve [] para los no catalogados.
"""

from __future__ import annotations

PROCESOS_POR_PROMPT: dict[str, list[str]] = {
    # Imagen
    "prompt/ilustrar": [
        "Generación de imagen · directiva del generador (etapa Ilustrar del pipeline y botón «Generar con IA»)",
    ],
    # Recibir (cajones del día)
    "prompt/recibir/portal": ["Recibir · cajón Portal/SMS"],
    "prompt/recibir/corresponsales": ["Recibir · cajón Corresponsales"],
    "prompt/recibir/reporteros": ["Recibir · cajón Reporteros"],
    "prompt/recibir/eventos-claro": ["Recibir · cajón Eventos Claro Sports"],
    "prompt/recibir/notas": ["Recibir · cajón Notas y links (Claro Sports)"],
    "prompt/recibir/contexto": ["Recibir · cajón Indicaciones (Claro Sports)"],
    # Noticias / algoritmo
    "prompt/traducir": ["Recolectar noticias · Traducir (MX)"],
    "prompt/fusionar": [
        "Recolectar noticias · Fusionar historias del mismo evento",
    ],
    "prompt/fusionar-verificar": [
        "Recolectar noticias · Verificar cada grupo propuesto antes de fusionar",
    ],
    "prompt/priorizar": ["Investigación · Priorizar (perfil de keywords por marca)"],
    "prompt/clasificar-marca": ["Investigación · Clasificar marca"],
    # Importación de documentos
    "prompt/importar/calendario": ["Importar calendario de contenido (documento → parrilla)"],
    "prompt/importar/parrilla": ["Importar rota/parrilla (documento → operaciones)"],
    # Pipeline de contenido
    "prompt/verificar": ["Investigación · Verificar la fuente (antes del copy)"],
    "prompt/redactar": ["Producción · Redactar copy desde la nota"],
    "prompt/critica": [
        "Aprobar · crítica IA con visión (vota el nivel «Crítica IA» antes de programar)",
    ],
    "prompt/idear": ["Idear · brainstorming de ideas"],
    # Envoltorios del copy (instrucciones aditivas que `dominio.generar.componer` concatena
    # al prompt base; el código decide CUÁNDO se inyectan y rellena sus {{VARIABLES}}).
    "prompt/envoltorios/redes": [
        "Pipeline de copy · envoltorio de redes (una pieza por red: Texto manual, galería, termómetro)",
    ],
    "prompt/envoltorios/copy-unico": [
        "Pipeline de copy · copy unificado (un texto + un texto-en-imagen para todas las redes)",
    ],
    "prompt/envoltorios/carrusel": [
        "Pipeline de copy · decisión de carrusel (historias que agrupan 2+ notas)",
    ],
    # De LANZAMIENTO MANUAL (no se inyectan en un proceso de fondo; se ejecutan a demanda).
    "prompt/hashtags": ["Herramienta · sugerencia de hashtags"],
    "prompt/asistente/variantes": ["Asistente del editor · modo variantes"],
    "prompt/asistente/resumir": ["Asistente del editor · modo resumir"],
}


def procesos_de(prompt_id: str) -> list[str]:
    """Procesos a los que se inyecta `prompt_id` (lista vacía si no está catalogado)."""
    return list(PROCESOS_POR_PROMPT.get(prompt_id, ()))
