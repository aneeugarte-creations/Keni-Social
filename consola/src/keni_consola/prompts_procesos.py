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
    "prompt/fusionar-macroevento": [
        "Recolectar noticias · Etiquetar familias de macro-evento (historias distintas, mismo gran evento)",
    ],
    "prompt/fusionar-subtema": [
        "Recolectar noticias · Partir un macro-evento en subtemas coherentes (un carrusel por faceta)",
    ],
    "prompt/priorizar": ["Investigación · Priorizar (perfil de keywords por marca)"],
    "prompt/clasificar-marca": ["Investigación · Clasificar marca"],
    # Importación de documentos
    "prompt/importar/calendario": ["Importar calendario de contenido (documento → parrilla)"],
    "prompt/importar/parrilla": ["Importar rota/parrilla (documento → operaciones)"],
    # Pipeline de contenido
    "prompt/verificar": ["Investigación · Verificar la fuente (antes del copy)"],
    "prompt/decisor": ["Producción · Decisor de formato (foto vs carrusel, antes de Redactar)"],
    "prompt/redactar": ["Producción · Redactar copy desde la nota (camino foto)"],
    "prompt/redactar-carrusel": ["Producción · Redactar carrusel (camino carrusel: panel de tarjetas)"],
    "prompt/sugerir-hashtags": [
        "Producción · Keywords: hashtags de la marca + keyword de imagen (etapa tras Redactar)",
    ],
    "prompt/critica": [
        "Aprobar · crítica IA con visión (vota el nivel «Crítica IA» antes de programar)",
    ],
    "prompt/idear": ["Idear · brainstorming de ideas"],
    # Gestor de audio (audio→texto): agentes de Claude sobre la transcripción.
    "prompt/audio/limpiar": ["Audio · Limpiar la transcripción (silencios/loops/repeticiones)"],
    "prompt/audio/resumir": ["Audio · Resumir la transcripción"],
    "prompt/audio/aclarar": ["Audio · Aclarar (preguntas sobre los fragmentos dudosos)"],
    "prompt/audio/corregir": ["Audio · Corregir la transcripción con las respuestas del equipo"],
    "prompt/audio/ideas": ["Audio · Extraer ideas de todo tipo (software/contenido/negocio) de la transcripción"],
    "prompt/audio/clips": ["Audio · Extraer clips y hooks (momentos clipeables con su minuto)"],
    "prompt/audio/capitulado": ["Audio · Capítulos de YouTube (SEO) a partir de la transcripción"],
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
    "prompt/carrusel-desde-post": [
        "Carrusel desde post · parte un post ya redactado en titulares de tarjetas (acción «Carrusel» del feed)",
    ],
}


def procesos_de(prompt_id: str) -> list[str]:
    """Procesos a los que se inyecta `prompt_id` (lista vacía si no está catalogado)."""
    return list(PROCESOS_POR_PROMPT.get(prompt_id, ()))
