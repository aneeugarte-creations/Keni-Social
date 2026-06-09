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
    "prompt/imagen/sistema-generador": [
        "Generación de imagen · directiva de sistema (Estudio, auto-arte y botón «Generar con IA»)",
    ],
    "prompt/imagen/arte-noticia": [
        "Auto-arte del pipeline · ilustra temas con copy pero sin imagen",
    ],
    "prompt/imagen/ilustracion-fondo": [
        "Estudio de imagen · prompt base de la variante generada",
    ],
    # Insumos del día (buzón de cajones)
    "prompt/insumos/portal": ["Buzón de insumos · cajón Portal/SMS"],
    "prompt/insumos/corresponsales": ["Buzón de insumos · cajón Corresponsales"],
    "prompt/insumos/reporteros": ["Buzón de insumos · cajón Reporteros"],
    "prompt/insumos/eventos-claro": ["Buzón de insumos · cajón Eventos Claro Sports"],
    # Noticias / algoritmo
    "prompt/editorial/sugerencias-plataforma": [
        "Sugerencias editoriales · digest diario de cambios de algoritmo por plataforma",
    ],
    "prompt/noticias/traduccion": ["Ingesta de noticias · traducción/localización (MX)"],
    "prompt/noticias/fusion-historias": [
        "Ingesta de noticias · fusión de historias del mismo evento",
    ],
    "prompt/noticias/perfil-editorial": ["Priorización · perfil de keywords por marca"],
    # Importación de documentos
    "prompt/importacion/calendario": ["Importar calendario de contenido (documento → parrilla)"],
    "prompt/importacion/parrilla": ["Importar rota/parrilla (documento → operaciones)"],
    # Pipeline de contenido
    "prompt/qa-fuente": ["Pipeline · criba QA de la fuente (pre-copy)"],
    "prompt/copy-desde-nota": ["Pipeline · generación de copy desde la nota"],
    "prompt/qa-editorial": ["QA editorial del copy (revisión manual y aprobador automático)"],
    "prompt/brainstorming-evergreen": ["Taller evergreen · brainstorming de ideas"],
    # De LANZAMIENTO MANUAL (no se inyectan en un proceso de fondo; se ejecutan a demanda).
    "prompt/termometro-mundial": ["Se lanza a mano · sección Termómetro (descubrimiento de tendencias)"],
    "prompt/brief-tendencias": [
        "Se lanza a mano · brief de tendencias desde el estudio (no cableado a ningún proceso)",
    ],
}


def procesos_de(prompt_id: str) -> list[str]:
    """Procesos a los que se inyecta `prompt_id` (lista vacía si no está catalogado)."""
    return list(PROCESOS_POR_PROMPT.get(prompt_id, ()))
