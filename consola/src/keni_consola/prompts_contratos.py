"""Catálogo: el CONTRATO DE SALIDA (forma del JSON) de cada prompt ESTRUCTURADO.

Un prompt es ESTRUCTURADO cuando su salida la PARSEA el código (un objeto JSON con una forma
fija). Esa forma —"responde EXCLUSIVAMENTE con `{...}`"— no es editorial: depende 100% del
parser, así que su FUENTE ÚNICA es CÓDIGO, no el cuerpo editable. Co-ubicar el contrato aquí
evita que se desincronice cuando el equipo edita el prompt, igual que `prompts_procesos`.

Modelo: el cuerpo editable del prompt TERMINA en el placeholder `{{CONTRATO_SALIDA}}`; la
composición lo rellena con el contrato real (`resolver_contrato`) justo antes de enviar al modelo,
así el contrato va SIEMPRE al FINAL del prompt (tras la prosa y los datos). En la Biblioteca el
contrato NO se puede editar (el editor oculta el placeholder del final y pinta el contrato
read-only en un bloque aparte). `contrato_de` devuelve `None` para los
prompts NO estructurados (su salida es prosa para una persona: `prompt/ilustrar`,
`prompt/redactar`, `prompt/asistente/*`, envoltorios…) o los que ya inyectan su contrato por
otro placeholder (`prompt/importar/parrilla` con `{{ESQUEMA_JSON}}`, `prompt/hashtags` no-JSON).
"""

from __future__ import annotations

PLACEHOLDER = "{{CONTRATO_SALIDA}}"

# El contrato es el bloque que declara la FORMA del JSON que exige el parser ("responde
# EXCLUSIVAMENTE con…"). Texto levantado TAL CUAL del cuerpo (debe casar byte a byte para que
# la migración del store lo localice y lo sustituya por el placeholder).
CONTRATO_POR_PROMPT: dict[str, str] = {
    'prompt/traducir': 'Devuelve EXCLUSIVAMENTE un objeto JSON con la forma `{"traducciones": [{"id": "...", "titulo_es": "...", "resumen_es": "..."}, ...]}`, sin ningún texto adicional ni ```json. Incluye TODOS los ítems de la lista en `traducciones` (uno por cada id, sin omitir ninguno), aunque el resumen vaya vacío; si un resumen está vacío, devuelve `resumen_es` vacío también.',
    'prompt/fusionar': 'Devuelve EXCLUSIVAMENTE un objeto JSON con la forma `{"grupos": [["id1","id2"], ["id3","id4","id5"]]}` (solo grupos de 2 o más ids), sin ningún texto adicional ni ```json.',
    'prompt/fusionar-verificar': 'Devuelve EXCLUSIVAMENTE un objeto JSON `{"grupos": [["id1","id2"]]}` con los subgrupos que SÍ son el mismo acontecimiento (solo grupos de 2 o más ids; si ninguno lo es, `{"grupos": []}`), sin ningún texto adicional ni ```json.',
    'prompt/priorizar': 'Responde EXCLUSIVAMENTE con un objeto JSON con la forma `{"keywords": ["...", "..."]}`, sin ningún texto adicional ni ```json.',
    'prompt/clasificar-marca': 'Responde SOLO con un JSON: `{"marca": "<id>", "confianza": <0..1>}`. El id debe ser uno de los listados.',
    'prompt/idear': 'Responde con **UN ÚNICO bloque de código cercado ```json** con esta forma EXACTA, y **NADA de\ntexto antes ni después**:\n\n```json\n{"ideas": [\n  {"titulo": "...", "descripcion": "..."},\n  {"titulo": "...", "descripcion": "..."}\n]}\n```\n\nIncluye entre 5 y 10 ideas. Si por alguna razón no puedes proponer ninguna, devuelve\n`{"ideas": []}`.',
    'prompt/verificar': 'Tras el semáforo, cierra con un bloque ```json con la forma:\n{"veredicto": "apta", "resumen": "una frase",\n "hallazgos": [{"tipo": "dato|legal|voz", "gravedad": "error|aviso",\n                "fragmento": "...", "explicacion": "...", "sugerencia": "..."}]}\nEl campo "veredicto" va SIEMPRE en slug ASCII: "apta" (seguir) o "problema" (de peso, NO\ngenerar copy). El semáforo 🟢/🔴 es solo la línea humana de arriba, NO un valor del JSON.\nUsa gravedad "error" SOLO para lo de peso (lo que hace "problema"). Sin emojis en el cuerpo\nni en el JSON.',
    'prompt/critica': 'Responde EXCLUSIVAMENTE con un objeto JSON válido, sin texto antes ni después, con esta forma:\n\n```json\n{\n  "veredicto": "aprueba" | "rechaza",\n  "problemas": [\n    {"tipo": "arte_sintetico|coherencia|sustancia|rigor|hashtags|voz|otro", "severidad": "alta|media|baja", "detalle": "frase concreta"}\n  ],\n  "comentario": "mensaje breve y accionable para el equipo (vacío si apruebas sin objeciones)",\n  "recomendacion_formato": "carrusel" | "foto" | "video" | ""\n}\n```',
    'prompt/recibir/contexto': 'Devuelve EXCLUSIVAMENTE un objeto JSON con la forma `{"items": [ ... ]}`, sin ningún texto adicional.',
    'prompt/recibir/notas': 'Devuelve EXCLUSIVAMENTE un objeto JSON con la forma `{"items": [ ... ]}`, sin ningún texto adicional.',
    'prompt/recibir/portal': 'Devuelve EXCLUSIVAMENTE un objeto JSON con la forma `{"items": [ ... ]}`, sin ningún texto adicional.',
    'prompt/recibir/corresponsales': 'Devuelve EXCLUSIVAMENTE un objeto JSON `{"items": [ ... ]}`.',
    'prompt/recibir/eventos-claro': 'Devuelve EXCLUSIVAMENTE un objeto JSON `{"items": [ ... ]}`.',
    'prompt/recibir/reporteros': 'Devuelve EXCLUSIVAMENTE un objeto JSON `{"items": [ ... ]}`.',
    'prompt/importar/calendario': 'Devuelve EXCLUSIVAMENTE un objeto JSON con la forma `{"filas": [ ... ]}`, sin ningún texto adicional ni explicación.',
}


def contrato_de(prompt_id: str) -> str | None:
    """Contrato de salida de `prompt_id`, o `None` si el prompt no es estructurado."""
    return CONTRATO_POR_PROMPT.get(prompt_id)


def resolver_contrato(prompt_id: str, cuerpo: str) -> str:
    """Sustituye el placeholder `{{CONTRATO_SALIDA}}` del cuerpo por el contrato real del prompt.

    - Sin placeholder en el cuerpo (bodies aún sin migrar): lo devuelve INTACTO (migración suave;
      el contrato sigue inline como hasta ahora).
    - Con placeholder y contrato conocido: lo sustituye (el contrato queda al FINAL del prompt).
    - Con placeholder pero sin contrato (no estructurado): elimina el placeholder y el hueco que
      lo precede, para no dejar un token crudo en el prompt.
    """
    if PLACEHOLDER not in cuerpo:
        return cuerpo
    contrato = contrato_de(prompt_id)
    if contrato:
        return cuerpo.replace(PLACEHOLDER, contrato)
    return cuerpo.replace("\n\n" + PLACEHOLDER, "").replace(PLACEHOLDER, "")
