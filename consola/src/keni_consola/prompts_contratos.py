"""Catálogo: el CONTRATO DE SALIDA (forma del JSON) de cada prompt ESTRUCTURADO.

Un prompt es ESTRUCTURADO cuando su salida la PARSEA el código (un objeto JSON con una forma
fija). Esa forma —"responde EXCLUSIVAMENTE con `{...}`"— no es editorial: depende 100% del
parser, así que su FUENTE ÚNICA es CÓDIGO, no el cuerpo editable. Co-ubicar el contrato aquí
evita que se desincronice cuando el equipo edita el prompt, igual que `prompts_procesos`.

Modelo: el cuerpo editable del prompt TERMINA en el placeholder `{{CONTRATO_SALIDA}}`; la
composición lo rellena con el contrato real (`resolver_contrato`) justo antes de enviar al modelo,
así el contrato va SIEMPRE al FINAL del prompt (tras la prosa y los datos). En la Prompts el
contrato NO se puede editar (el editor oculta el placeholder del final y pinta el contrato
read-only en un bloque aparte). `contrato_de` devuelve `None` para los
prompts NO estructurados (su salida es prosa para una persona: `prompt/ilustrar`,
envoltorios…) o los que ya inyectan su contrato por otro placeholder
(`prompt/importar/parrilla` con `{{ESQUEMA_JSON}}`). `prompt/redactar`
SÍ tiene contrato (las formas `{texto, copy_in}` / `{piezas}` que lee el parser).
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
    'prompt/fusionar-macroevento': 'Devuelve EXCLUSIVAMENTE un objeto JSON con la forma `{"familias": [{"tema": "<etiqueta corta>", "ids": ["id1","id2"]}, ...]}` (solo familias de 2 o más ids; si no hay ninguna, `{"familias": []}`), sin ningún texto adicional ni ```json.',
    'prompt/fusionar-subtema': 'Devuelve EXCLUSIVAMENTE un objeto JSON con la forma `{"subtemas": [{"subtema": "<etiqueta corta>", "ids": ["id1","id2"]}, ...]}` (cada id en UN solo subtema; un subtema puede tener un solo id), sin ningún texto adicional ni ```json.',
    'prompt/priorizar': 'Responde EXCLUSIVAMENTE con un objeto JSON con la forma `{"keywords": ["...", "..."]}`, sin ningún texto adicional ni ```json.',
    'prompt/clasificar-marca': 'Responde SOLO con un JSON: `{"marca": "<id>", "confianza": <0..1>}`. El id debe ser uno de los listados.',
    'prompt/idear': 'Responde con **UN ÚNICO bloque de código cercado ```json** con esta forma EXACTA, y **NADA de\ntexto antes ni después**:\n\n```json\n{"ideas": [\n  {"titulo": "...", "descripcion": "..."},\n  {"titulo": "...", "descripcion": "..."}\n]}\n```\n\nIncluye entre 5 y 10 ideas. Si por alguna razón no puedes proponer ninguna, devuelve\n`{"ideas": []}`.',
    'prompt/verificar': 'Tras el semáforo, cierra con un bloque ```json con la forma:\n{"veredicto": "verificado", "resumen": "una frase",\n "hallazgos": [{"tipo": "dato|legal|voz", "gravedad": "error|aviso",\n                "fragmento": "...", "explicacion": "...", "sugerencia": "..."}]}\nEl campo "veredicto" va SIEMPRE en slug ASCII: "verificado" (confirmada), "requiere_humano" (no\nconfirmada, a la mesa) o "rechazado" (de peso, NO generar copy). El semáforo 🟢/🟡/🔴 es solo la\nlínea humana de arriba, NO un valor del JSON. Usa gravedad "error" SOLO para lo de peso (lo que hace\n"rechazado"). Sin emojis en el cuerpo ni en el JSON.',
    'prompt/critica': 'Responde EXCLUSIVAMENTE con un objeto JSON válido, sin texto antes ni después, con esta forma:\n\n```json\n{\n  "veredicto": "aprueba" | "rechaza",\n  "problemas": [\n    {"tipo": "arte_sintetico|coherencia|sustancia|rigor|hashtags|voz|otro", "severidad": "alta|media|baja", "detalle": "frase concreta"}\n  ],\n  "comentario": "mensaje breve y accionable para el equipo (vacío si apruebas sin objeciones)",\n  "recomendacion_formato": "carrusel" | "foto" | "video" | ""\n}\n```',
    'prompt/recibir/contexto': 'Devuelve EXCLUSIVAMENTE un objeto JSON con la forma `{"items": [ ... ]}`, sin ningún texto adicional.',
    'prompt/recibir/notas': 'Devuelve EXCLUSIVAMENTE un objeto JSON con la forma `{"items": [ ... ]}`, sin ningún texto adicional.',
    'prompt/recibir/portal': 'Devuelve EXCLUSIVAMENTE un objeto JSON con la forma `{"items": [ ... ]}`, sin ningún texto adicional.',
    'prompt/recibir/corresponsales': 'Devuelve EXCLUSIVAMENTE un objeto JSON `{"items": [ ... ]}`.',
    'prompt/recibir/eventos-claro': 'Devuelve EXCLUSIVAMENTE un objeto JSON `{"items": [ ... ]}`.',
    'prompt/recibir/reporteros': 'Devuelve EXCLUSIVAMENTE un objeto JSON `{"items": [ ... ]}`.',
    'prompt/importar/calendario': 'Devuelve EXCLUSIVAMENTE un objeto JSON con la forma `{"filas": [ ... ]}`, sin ningún texto adicional ni explicación.',
    'prompt/redactar': 'Al FINAL de toda tu respuesta, añade un único bloque de código cercado ```json con la forma EXACTA que pida la instrucción del lanzamiento:\n\n- **Copy unificado** (un solo objeto, NO un array por red): el mismo `texto` y `copy_in` se reutilizan en todas las redes pedidas. Incluye siempre `copy_in` (`""` si no lleva imagen).\n\n```json\n{"texto": "<el copy, igual para todas las redes>", "copy_in": "<texto en la imagen>"}\n```\n\n- **Variante por red**: `{"piezas": [{"red": "<id>", "texto": "…", "copy_in": "…"}, …]}` con exactamente UNA pieza por red pedida (nunca dos de la misma), usando como `<id>` únicamente los ids exactos de la instrucción. **Piezas compuestas**: el almacén guarda UN solo `texto` por red, así que un **hilo** va numerado DENTRO de `texto` (un tuit por párrafo con prefijo `1/n `, cada tuit dentro del límite de la red) y un **carrusel** con las slides separadas por una línea con solo `---`. Si propones hilo/carrusel, esa ES la pieza de la red.',
}


def contrato_de(prompt_id: str) -> str | None:
    """Contrato de salida de `prompt_id`, o `None` si el prompt no es estructurado.

    `prompt/importar/parrilla` es un caso especial: su contrato lo INYECTA su módulo de dominio
    (el documento a parsear debe quedar al final del prompt, así que el esquema no puede ir por el
    placeholder común); aquí se expone SOLO para que el editor lo pinte read-only. Import diferido
    para no cargar el dominio salvo que se pida (y evitar ciclos).
    """
    if prompt_id == "prompt/importar/parrilla":
        from .dominio.parrilla_import_job import _CONTRATO_SALIDA

        return _CONTRATO_SALIDA
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
