"""Catálogo: a qué PROCESO(S) se inyecta cada prompt de la Biblioteca.

Fuente única para la transparencia "¿a qué proceso se inyecta este prompt?" que muestra el
estudio de texto (pestaña «Prompts»). El mapeo vive en CÓDIGO a propósito: es propiedad de qué
módulo inyecta el prompt en un agente, no del contenido editable; así no se desincroniza cuando
el equipo edita el documento. Cuando se cablea un prompt nuevo (lectura por
`libtexto.cuerpo_efectivo`), se añade aquí su entrada.

Las claves son los IDs de documento (`prompt/...`); los valores, etiquetas legibles del/los
proceso(s) donde el prompt se inyecta a la IA. `procesos_de` devuelve [] para los no catalogados.
"""

from __future__ import annotations

PROCESOS_POR_PROMPT: dict[str, list[str]] = {
    # Imagen
    "prompt/arte": [
        "Generación de imagen · directiva del generador (auto-arte del pipeline y botón «Generar con IA»)",
    ],
    # Insumos del día (buzón de cajones)
    "prompt/insumos/portal": ["Buzón de insumos · cajón Portal/SMS"],
    "prompt/insumos/corresponsales": ["Buzón de insumos · cajón Corresponsales"],
    "prompt/insumos/reporteros": ["Buzón de insumos · cajón Reporteros"],
    "prompt/insumos/eventos-claro": ["Buzón de insumos · cajón Eventos Claro Sports"],
    # Noticias / algoritmo
    "prompt/sugerencias": [
        "Sugerencias editoriales · digest diario de cambios de algoritmo por plataforma",
    ],
    "prompt/traduccion": ["Ingesta de noticias · traducción/localización (MX)"],
    "prompt/fusion": [
        "Ingesta de noticias · fusión de historias del mismo evento",
    ],
    "prompt/fusion-verificacion": [
        "Ingesta de noticias · verificación de cada grupo propuesto antes de fundir",
    ],
    "prompt/editorial": ["Investigación · ranking (perfil de keywords por marca)"],
    "prompt/clasificacion-marca": ["Investigación · clasificación de marca"],
    # Importación de documentos
    "prompt/importar/calendario": ["Importar calendario de contenido (documento → parrilla)"],
    "prompt/importar/parrilla": ["Importar rota/parrilla (documento → operaciones)"],
    # Pipeline de contenido
    "prompt/validacion": ["Investigación · verificación de la fuente (antes del copy)"],
    "prompt/copy": ["Producción · generación de copy desde la nota"],
    "prompt/evergreen": ["Taller evergreen · brainstorming de ideas"],
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
    "prompt/envoltorios/sin-emojis": [
        "Pipeline de copy · sin emojis (aditivo opt-in de flujos cuya salida nunca lleva emojis: evergreen/termómetro)",
    ],
    # De LANZAMIENTO MANUAL (no se inyectan en un proceso de fondo; se ejecutan a demanda).
    "prompt/hashtags": ["Herramienta · sugerencia de hashtags"],
    "prompt/asistente/variantes": ["Asistente del editor · modo variantes"],
    "prompt/asistente/resumir": ["Asistente del editor · modo resumir"],
}


def procesos_de(prompt_id: str) -> list[str]:
    """Procesos a los que se inyecta `prompt_id` (lista vacía si no está catalogado)."""
    return list(PROCESOS_POR_PROMPT.get(prompt_id, ()))
