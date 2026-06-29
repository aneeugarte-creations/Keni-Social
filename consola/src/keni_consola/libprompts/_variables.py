"""Catalogo de las VARIABLES `{{VAR}}` que la Consola sustituye al inyectar prompts.

Varios prompts del sistema son PLANTILLAS: llevan marcadores `{{NOMBRE}}` (mayusculas y
guion bajo) que el modulo que los inyecta sustituye por datos reales en el momento de
componer el prompt. Este catalogo es la fuente UNICA de transparencia para la UI de la
Prompts ("¿que significa este marcador y quien lo rellena?").

INVENTARIO REAL: cada entrada corresponde a una sustitucion `.replace("{{...}}", ...)`
que existe en el codigo (no se inventan variables). Cuando se cablea un marcador nuevo
en un modulo, se anade aqui su entrada. Origen = el proceso/modulo que la sustituye:

  - `dominio/perfil_editorial.py`  -> {{MARCA}} {{MAX_KEYWORDS}} {{EDITORIAL}}
  - `dominio/fusionar_semantica.py`  -> {{HISTORIAS}}        (fusionar Y fusionar-verificar)
  - `dominio/traducir.py`        -> {{ITEMS}}
  - `dominio/recibir_parse.py`     -> {{RUTA}}
  - `importador_calendario.py`     -> {{RUTA}} {{MARCAS}} {{REDES}}
  - `dominio/parrilla_import_job.py` -> {{FUENTE}} {{MIEMBROS}} {{SLOTS}} {{REGLA_FUENTE}}
                                        {{ESQUEMA_JSON}} {{COLA_FUENTE}}
  - `dominio/generar.py`             -> {{ETIQUETAS}} {{LIMITES}} {{IDS_JSON}} (envoltorio
                                        de redes); {{N_NOTAS}} {{MAX_SLIDES}}
                                        {{CATALOGO_FOTOS}} (decisión de carrusel);
                                        {{MODO_PUBLICACION}} {{VERSIONES}} {{CIERRE_JSON}}
                                        {{REDES_AMPLIAS}} {{REDES_ESTRECHAS}} {{TOPE_CORTO}}
                                        (copy unificado)

Lo sirve `GET /api/prompts/variables` con la forma `{variables: [{nombre, descripcion,
ejemplo, origen}]}` (contrato con el frontend del rediseno).
"""

from __future__ import annotations

__all__ = ["catalogo_variables"]

# Una entrada por variable: nombre (sin llaves), descripcion (1 frase: que inyecta la
# Consola), ejemplo (valor realista) y origen (que proceso la sustituye).
_CATALOGO: tuple[dict[str, str], ...] = (
    # --- Priorizar (Investigacion): perfil de keywords por marca (prompt/priorizar) ---
    {
        "nombre": "MARCA",
        "descripcion": "Id de la marca para la que se compone el prompt (perfil editorial).",
        "ejemplo": "unotv",
        "origen": "Priorizar · perfil de keywords por marca (prompt/priorizar)",
    },
    {
        "nombre": "MAX_KEYWORDS",
        "descripcion": "Tope numérico de keywords que puede devolver el perfil de la marca.",
        "ejemplo": "30",
        "origen": "Priorizar · perfil de keywords por marca (prompt/priorizar)",
    },
    {
        "nombre": "EDITORIAL",
        "descripcion": "Texto completo de la línea editorial de la marca, del que se extraen los temas.",
        "ejemplo": "## Qué cubre UnoTV\nNoticias nacionales, …",
        "origen": "Priorizar · perfil de keywords por marca (prompt/priorizar)",
    },
    # --- Recolectar: fusionar historias + comprobacion (prompt/fusionar, prompt/fusionar-verificar) ---
    {
        "nombre": "HISTORIAS",
        "descripcion": "Lista JSON de historias candidatas (id, título, resumen) a agrupar o comprobar antes de fusionar.",
        "ejemplo": '[{"id": "c41", "texto": "Sheinbaum anuncia plan hídrico…"}]',
        "origen": "Recolectar noticias · fusionar historias y comprobación previa (prompt/fusionar, prompt/fusionar-verificar)",
    },
    # --- Recolectar: traducir/localizar (prompt/traducir) ---
    {
        "nombre": "ITEMS",
        "descripcion": "Lista JSON de titulares/resúmenes en otro idioma que hay que traducir y localizar a MX.",
        "ejemplo": '[{"id": "n7", "titulo": "Real Madrid clinch title…"}]',
        "origen": "Recolectar noticias · traducir/localizar MX (prompt/traducir)",
    },
    # --- Archivos subidos: lo recibido del dia + importar calendario ---
    {
        "nombre": "RUTA",
        "descripcion": "Ruta local del archivo subido que el agente debe leer (material recibido del día o calendario).",
        "ejemplo": "/tmp/keni-texto-ab12/recibido.pdf",
        "origen": "Recibir (prompt/recibir/*) e importar calendario (prompt/importar/calendario)",
    },
    {
        "nombre": "MARCAS",
        "descripcion": "Catálogo de marcas válidas asignables a cada fila importada.",
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
    # --- Envoltorios del copy (dominio/generar.py, prompt/envoltorios/*) ---
    {
        "nombre": "ETIQUETAS",
        "descripcion": "Nombres legibles de las redes pedidas para esta generación de copy.",
        "ejemplo": "Instagram, X, Facebook",
        "origen": "Pipeline de Redactar · envoltorios de redes y copy unificado (prompt/envoltorios/redes, "
        "prompt/envoltorios/copy-unico)",
    },
    {
        "nombre": "LIMITES",
        "descripcion": "Frase con el límite técnico de caracteres de cada red pedida, desde la fuente única "
        "del código (keni-shared).",
        "ejemplo": "X máx 25000 caracteres, Facebook sin tope técnico",
        "origen": "Pipeline de Redactar · envoltorio de redes (prompt/envoltorios/redes)",
    },
    {
        "nombre": "IDS_JSON",
        "descripcion": "Ids de red válidos (entre comillas) que el modelo puede usar en el bloque json de piezas.",
        "ejemplo": '"x", "facebook"',
        "origen": "Pipeline de Redactar · envoltorio de redes (prompt/envoltorios/redes)",
    },
    {
        "nombre": "N_NOTAS",
        "descripcion": "Cuántas notas (sub-historias) agrupa la historia para la decisión post|carrusel.",
        "ejemplo": "4",
        "origen": "Pipeline de Redactar · decisión de carrusel (prompt/envoltorios/carrusel)",
    },
    {
        "nombre": "MAX_SLIDES",
        "descripcion": "Tope de slides extra de un carrusel editorial (10 nativas de IG/FB menos la portada).",
        "ejemplo": "9",
        "origen": "Pipeline de Redactar · decisión de carrusel (prompt/envoltorios/carrusel)",
    },
    {
        "nombre": "CATALOGO_FOTOS",
        "descripcion": "Catálogo numerado de fotos de fuente propia (título de su nota por línea), o el aviso "
        "de que no hay ninguna.",
        "ejemplo": "FOTOS DISPONIBLES (…):\n  1. Concierto en el Zócalo",
        "origen": "Pipeline de Redactar · decisión de carrusel (prompt/envoltorios/carrusel)",
    },
    {
        "nombre": "MODO_PUBLICACION",
        "descripcion": "Matiz de publicación del copy unificado: vacío con dos versiones, « TAL CUAL» cuando "
        "un solo copy va igual a todas las redes.",
        "ejemplo": " TAL CUAL",
        "origen": "Pipeline de Redactar · copy unificado (prompt/envoltorios/copy-unico)",
    },
    {
        "nombre": "VERSIONES",
        "descripcion": "Sub-bloque ya montado por el código con qué versiones escribir: dos (texto + "
        "texto_corto) si se mezclan redes amplias y estrechas, una si no.",
        "ejemplo": "Escribe DOS versiones del MISMO mensaje (…) máximo 2200 caracteres.",
        "origen": "Pipeline de Redactar · copy unificado (prompt/envoltorios/copy-unico)",
    },
    {
        "nombre": "CIERRE_JSON",
        "descripcion": "Forma exacta del bloque json final, ya montada por el código (claves según la rama, "
        "y la decisión de carrusel si la historia agrupa 2+ notas).",
        "ejemplo": '{"texto": "<el copy>", "copy_in": "<…>"}. El `copy_in` es…',
        "origen": "Pipeline de Redactar · copy unificado (prompt/envoltorios/copy-unico)",
    },
    {
        "nombre": "REDES_AMPLIAS",
        "descripcion": "Nombres de las redes sin límite corto (reciben la versión completa `texto`), dentro "
        "del sub-bloque de versiones.",
        "ejemplo": "Instagram, Facebook",
        "origen": "Pipeline de Redactar · copy unificado (sub-bloque {{VERSIONES}} montado en dominio/generar.py)",
    },
    {
        "nombre": "REDES_ESTRECHAS",
        "descripcion": "Nombres de las redes con límite corto (reciben `texto_corto`), dentro del sub-bloque "
        "de versiones.",
        "ejemplo": "Instagram",
        "origen": "Pipeline de Redactar · copy unificado (sub-bloque {{VERSIONES}} montado en dominio/generar.py)",
    },
    {
        "nombre": "TOPE_CORTO",
        "descripcion": "Límite técnico más estricto (en caracteres) que acota el copy o su versión corta.",
        "ejemplo": "2200",
        "origen": "Pipeline de Redactar · copy unificado (sub-bloque {{VERSIONES}} montado en dominio/generar.py)",
    },
)


def catalogo_variables() -> list[dict[str, str]]:
    """Catalogo completo (copia) de variables `{{VAR}}`, en el orden del inventario."""
    return [dict(v) for v in _CATALOGO]
