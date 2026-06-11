"""Catalogo de las VARIABLES `{{VAR}}` que la Consola sustituye al inyectar prompts.

Varios prompts del sistema son PLANTILLAS: llevan marcadores `{{NOMBRE}}` (mayusculas y
guion bajo) que el modulo que los inyecta sustituye por datos reales en el momento de
componer el prompt. Este catalogo es la fuente UNICA de transparencia para la UI de la
Biblioteca ("¿que significa este marcador y quien lo rellena?").

INVENTARIO REAL: cada entrada corresponde a una sustitucion `.replace("{{...}}", ...)`
que existe en el codigo (no se inventan variables). Cuando se cablea un marcador nuevo
en un modulo, se anade aqui su entrada. Origen = el proceso/modulo que la sustituye:

  - `dominio/perfil_editorial.py`  -> {{MARCA}} {{MAX_KEYWORDS}} {{EDITORIAL}}
  - `dominio/fusion_semantica.py`  -> {{HISTORIAS}}        (fusion Y fusion-verificacion)
  - `dominio/traduccion.py`        -> {{ITEMS}}
  - `sugerencias_editoriales.py`   -> {{PLATAFORMA}} {{FICHA}} {{LIMITE}} {{NOTICIAS}}
  - `dominio/insumos_parse.py`     -> {{RUTA}}
  - `importador_calendario.py`     -> {{RUTA}} {{MARCAS}} {{REDES}}
  - `dominio/parrilla_import_job.py` -> {{FUENTE}} {{MIEMBROS}} {{SLOTS}} {{REGLA_FUENTE}}
                                        {{ESQUEMA_JSON}} {{COLA_FUENTE}}

Lo sirve `GET /api/texto/variables` con la forma `{variables: [{nombre, descripcion,
ejemplo, origen}]}` (contrato con el frontend del rediseno).
"""

from __future__ import annotations

__all__ = ["catalogo_variables"]

# Una entrada por variable: nombre (sin llaves), descripcion (1 frase: que inyecta la
# Consola), ejemplo (valor realista) y origen (que proceso la sustituye).
_CATALOGO: tuple[dict[str, str], ...] = (
    # --- Priorizacion: perfil de keywords por marca (prompt/editorial) ---
    {
        "nombre": "MARCA",
        "descripcion": "Id de la marca cuyo perfil editorial de temas/keywords se está derivando.",
        "ejemplo": "unotv",
        "origen": "Priorización · perfil de keywords por marca (prompt/editorial)",
    },
    {
        "nombre": "MAX_KEYWORDS",
        "descripcion": "Tope numérico de keywords que puede devolver el perfil de la marca.",
        "ejemplo": "30",
        "origen": "Priorización · perfil de keywords por marca (prompt/editorial)",
    },
    {
        "nombre": "EDITORIAL",
        "descripcion": "Texto completo de la línea editorial de la marca, del que se extraen los temas.",
        "ejemplo": "## Qué cubre UnoTV\nNoticias nacionales, …",
        "origen": "Priorización · perfil de keywords por marca (prompt/editorial)",
    },
    # --- Ingesta: fusion de historias + verificacion (prompt/fusion, prompt/fusion-verificacion) ---
    {
        "nombre": "HISTORIAS",
        "descripcion": "Lista JSON de historias candidatas (id, título, resumen) a agrupar o verificar antes de fundir.",
        "ejemplo": '[{"id": "c41", "texto": "Sheinbaum anuncia plan hídrico…"}]',
        "origen": "Ingesta de noticias · fusión de historias y verificación pre-fusión (prompt/fusion, prompt/fusion-verificacion)",
    },
    # --- Ingesta: traduccion/localizacion (prompt/traduccion) ---
    {
        "nombre": "ITEMS",
        "descripcion": "Lista JSON de titulares/resúmenes en otro idioma que hay que traducir y localizar a MX.",
        "ejemplo": '[{"id": "n7", "titulo": "Real Madrid clinch title…"}]',
        "origen": "Ingesta de noticias · traducción/localización MX (prompt/traduccion)",
    },
    # --- Sugerencias editoriales: digest por plataforma (prompt/sugerencias) ---
    {
        "nombre": "PLATAFORMA",
        "descripcion": "Nombre de la plataforma para la que se generan las sugerencias del digest.",
        "ejemplo": "Instagram",
        "origen": "Sugerencias editoriales · digest diario por plataforma (prompt/sugerencias)",
    },
    {
        "nombre": "FICHA",
        "descripcion": "Ficha editorial vigente de esa plataforma (convenciones y hábitos medidos).",
        "ejemplo": "Reels < 60s rinden mejor; carruseles para listas…",
        "origen": "Sugerencias editoriales · digest diario por plataforma (prompt/sugerencias)",
    },
    {
        "nombre": "LIMITE",
        "descripcion": "Límite técnico de caracteres de la plataforma, en texto legible.",
        "ejemplo": "2200 caracteres",
        "origen": "Sugerencias editoriales · digest diario por plataforma (prompt/sugerencias)",
    },
    {
        "nombre": "NOTICIAS",
        "descripcion": "Digest de noticias de cambios de algoritmo (título, resumen y fuente por línea).",
        "ejemplo": "- Instagram prioriza originales\n  fuente: https://…",
        "origen": "Sugerencias editoriales · digest diario por plataforma (prompt/sugerencias)",
    },
    # --- Archivos subidos: insumos del dia + importar calendario ---
    {
        "nombre": "RUTA",
        "descripcion": "Ruta local del archivo subido que el agente debe leer (insumo del día o calendario).",
        "ejemplo": "/tmp/keni-texto-ab12/insumo.pdf",
        "origen": "Buzón de insumos (prompt/insumos/*) e importar calendario (prompt/importar/calendario)",
    },
    {
        "nombre": "MARCAS",
        "descripcion": "Catálogo vigente de marcas válidas a las que puede asignarse cada fila importada.",
        "ejemplo": "UnoTV, Claro Sports",
        "origen": "Importar calendario de contenido (prompt/importar/calendario)",
    },
    {
        "nombre": "REDES",
        "descripcion": "Catálogo vigente de redes válidas a las que puede asignarse cada fila importada.",
        "ejemplo": "Instagram, Facebook, X, TikTok, YouTube",
        "origen": "Importar calendario de contenido (prompt/importar/calendario)",
    },
    # --- Importar rota/parrilla (prompt/importar/parrilla) ---
    {
        "nombre": "FUENTE",
        "descripcion": "Instrucción de dónde leer el documento fuente (transcripción embebida o ruta local).",
        "ejemplo": "Lee EXCLUSIVAMENTE el documento en la ruta /tmp/… (PDF, imagen o Word).",
        "origen": "Importar rota/parrilla (prompt/importar/parrilla)",
    },
    {
        "nombre": "MIEMBROS",
        "descripcion": "Lista del equipo conocido (una línea por persona) para mapear nombres del documento.",
        "ejemplo": '  - "Ana Pérez"\n  - "Luis García"',
        "origen": "Importar rota/parrilla (prompt/importar/parrilla)",
    },
    {
        "nombre": "SLOTS",
        "descripcion": "Nombres válidos de franja/turno a los que normalizar los horarios del documento.",
        "ejemplo": '  - "Matutino"\n  - "Vespertino"',
        "origen": "Importar rota/parrilla (prompt/importar/parrilla)",
    },
    {
        "nombre": "REGLA_FUENTE",
        "descripcion": "Regla sobre qué herramientas puede usar el agente según cómo llegue el documento.",
        "ejemplo": "- No uses herramientas: todo está en el texto de abajo.",
        "origen": "Importar rota/parrilla (prompt/importar/parrilla)",
    },
    {
        "nombre": "ESQUEMA_JSON",
        "descripcion": "Esquema JSON exacto que debe tener la salida estructurada de la importación.",
        "ejemplo": '{"operaciones": [{"persona": "…", "dia": "…", "franja": "…"}]}',
        "origen": "Importar rota/parrilla (prompt/importar/parrilla)",
    },
    {
        "nombre": "COLA_FUENTE",
        "descripcion": "Transcripción del documento embebida al final del prompt (vacía si se lee por ruta).",
        "ejemplo": "DOCUMENTO (transcripción):\n```\nLUNES Ana 9-14…\n```",
        "origen": "Importar rota/parrilla (prompt/importar/parrilla)",
    },
)


def catalogo_variables() -> list[dict[str, str]]:
    """Catalogo completo (copia) de variables `{{VAR}}`, en el orden del inventario."""
    return [dict(v) for v in _CATALOGO]
