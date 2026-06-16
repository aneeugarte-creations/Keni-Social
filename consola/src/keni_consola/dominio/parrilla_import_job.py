"""Capa de I/O del job de IMPORTACION de parrilla (#parrilla-import).

Separa los SIDE-EFFECTS del dominio PURO (`dominio.parrilla_import`): aqui se construye el
`Contexto` desde la BD (`repos`), se compone el PROMPT del `claude -p` READ-ONLY y se arma el
post-procesado (`procesar`) que el WORKER ejecuta al terminar el job: parsea el JSON de claude,
re-construye el contexto VIVO (las semanas tocadas por las operaciones, no una sola), valida
con el dominio puro y guarda las operaciones + resumen en la fila `parrilla_propuesta` (estado
`pendiente`, o `error` con motivo).

RANGO, NO SEMANA UNICA: un documento puede traer un AÑO entero. Hay DOS construcciones de
contexto: una para el PROMPT (pre-claude, sin fechas: solo roster + nombres de slot + enums) y
otra para VALIDACION/CONFLICTO (post-claude, con las fechas ya conocidas: calcula las semanas
tocadas, resuelve los nombres de franja de esas semanas y carga sus turnos vivos).

Claude NUNCA escribe en el calendario: el prompt le pide EXCLUSIVAMENTE un bloque JSON; el
codigo Python valida y, mas tarde y solo si el usuario acepta, aplica el diff (otra capa).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from .. import importador_calendario, media, repos, rota, rutas
from ..estados import NOMBRE_FRANJA_MANANA_DEFAULT, NOMBRE_FRANJA_TARDE_DEFAULT
from . import generar, jobspec
from . import parrilla_import as pi

_log = logging.getLogger("keni_consola.parrilla_import_job")

# CDMX (America/Mexico_City) ya no usa horario de verano (desde 2022): offset fijo -6.
_TZ_CDMX = timezone(timedelta(hours=-6))


def _hoy_cdmx() -> str:
    """Fecha de HOY en CDMX (AAAA-MM-DD). Ancla las fechas relativas/sin año del import."""
    return datetime.now(_TZ_CDMX).date().isoformat()

# Nombres de slot por defecto (plantilla de la rota), solo como REFERENCIA en el prompt: el
# documento puede usar estos u otros (un día puede tener 3+ franjas). NO se restringe a ellos;
# las franjas nuevas se crean al aplicar. "Descanso" se incluye (un documento puede planificarlo).
_SLOTS_DEFECTO: tuple[str, ...] = (
    NOMBRE_FRANJA_MANANA_DEFAULT,
    NOMBRE_FRANJA_TARDE_DEFAULT,
    "Descanso",
)

# Endurecimiento del run READ-ONLY: el job SOLO lee el documento y emite JSON. Vetamos las
# herramientas de ESCRITURA (Write/Edit/Bash) y de RED (WebFetch/WebSearch), mas las tools MCP
# de la consola que MUTAN datos. Presupuesto/turnos GENEROSOS: un documento puede traer un año
# entero (cientos/miles de operaciones). El coste real lo acota el tamaño del documento, no un
# tope artificial.
_TOOLS_VETADAS: tuple[str, ...] = (
    "Write",
    "Edit",
    "MultiEdit",
    "NotebookEdit",
    "Bash",
    "WebFetch",
    "WebSearch",
    "mcp__keni-social__keni_crear_contenido",
    "mcp__keni-social__keni_actualizar_contenido",
    "mcp__keni-social__keni_enviar_a_revision",
    "mcp__keni-social__keni_aprobar",
    "mcp__keni-social__keni_rechazar",
    "mcp__keni-social__keni_generar_copy",
)

# Herramientas de LECTURA de ficheros: solo se permiten cuando el documento se lee como FICHERO
# (PDF/imagen). Si transcribimos la tabla y la EMBEBEMOS en el prompt, las vetamos tambien: el
# run es una transformacion pura texto→JSON (ni siquiera necesita abrir nada), mas rapida/barata.
_TOOLS_LECTURA: tuple[str, ...] = ("Read", "Glob", "Grep")


def _endurecer(*, lee_fichero: bool, permitir_web: bool = False) -> dict[str, Any]:
    """Config de endurecimiento del job. `lee_fichero=False` (texto embebido) veta tambien las
    tools de lectura: el modelo solo transforma el texto del prompt en JSON.

    `esfuerzo="low"`: la importacion es MECANICA (transcribir filas a JSON), no necesita
    razonamiento profundo. Medido en el server: con effort `low` el run es ~3× mas rapido
    (primer token y total) con la MISMA cobertura de operaciones; con el default el modelo
    "piensa" minutos sobre el documento antes de emitir nada. Override por-job: NO toca el
    effort global (copy/otros siguen con su preferencia).

    `permitir_web=True` (SOLO el camino de FRASE escrita a mano): NO veta WebSearch/WebFetch,
    para que el modelo pueda IDENTIFICAR y DATAR online un evento nombrado por su titulo (p. ej.
    «la velada del año VI»), que no trae fecha en el propio texto. Sube el esfuerzo a `medium`:
    ya no es transcripcion mecanica, hay que buscar y razonar la fecha/recinto. El resto de
    vetos (Bash/Write/Edit + MCP de escritura) sigue en pie: el job solo LEE web y emite JSON."""
    vetadas = list(_TOOLS_VETADAS)
    if permitir_web:
        vetadas = [t for t in vetadas if t not in ("WebSearch", "WebFetch")]
    if not lee_fichero:
        vetadas += list(_TOOLS_LECTURA)
    return {
        "disallowed_tools": vetadas,
        "max_turns": 40,
        "max_budget_usd": 10.0,
        "esfuerzo": "medium" if permitir_web else "low",
    }


# Formatos que TRANSCRIBIMOS a texto en el server (claude no pelea con el binario): Excel (todas
# las hojas), CSV/TSV y texto plano. Lo demás (PDF, imagen, docx) lo lee claude como FICHERO.
_EXTS_TEXTO: tuple[str, ...] = (".txt", ".md", ".markdown", ".text", ".log")


def _tabla_a_texto(filas: list[list[Any]]) -> str:
    """Filas de celdas -> texto TSV (una fila por línea, saltando filas totalmente vacías)."""
    lineas: list[str] = []
    for fila in filas:
        celdas = ["" if c is None else str(c) for c in fila]
        if any(c.strip() for c in celdas):
            lineas.append("\t".join(celdas))
    return "\n".join(lineas)


def _xlsx_todas_las_hojas(datos: bytes) -> str | None:
    """Transcribe TODAS las hojas de un .xlsx a texto (una sección por hoja, con cabecera).

    CRÍTICO: un libro de parrilla suele tener MUCHAS hojas (una por sección/tema/semana).
    Aquí recorremos `wb.worksheets` enteras para no perder secciones.
    """
    import io

    try:
        import openpyxl
    except ImportError:
        return None
    try:
        wb = openpyxl.load_workbook(io.BytesIO(datos), read_only=True, data_only=True)
    except Exception:  # noqa: BLE001 -- no es un xlsx legible: que lo intente claude como fichero
        return None
    bloques: list[str] = []
    try:
        for ws in wb.worksheets:
            filas = [list(f) for f in ws.iter_rows(values_only=True)]
            texto = _tabla_a_texto(filas)
            if texto.strip():
                bloques.append(f"### HOJA: {ws.title}\n{texto}")
    finally:
        wb.close()
    return "\n\n".join(bloques) or None


def _extraer_texto_documento(datos: bytes, nombre: str) -> str | None:
    """Transcribe a TEXTO los formatos que claude no debería leer como binario (Excel/CSV/texto).

    Devuelve el texto a EMBEBER en el prompt, o None para formatos que claude lee mejor como
    fichero (PDF, imagen, Word). PURO salvo por openpyxl. Un .xlsx transcrito a TSV (TODAS las
    hojas) permite una transformación texto→JSON más eficiente.
    """
    n = (nombre or "").lower()
    if n.endswith((".xlsx", ".xlsm")):
        return _xlsx_todas_las_hojas(datos)
    if n.endswith((".csv", ".tsv")):
        try:
            filas = importador_calendario._leer_tabla(datos, nombre=nombre)
        except Exception:  # noqa: BLE001 -- si no se puede parsear, que lo lea claude como fichero
            return None
        return _tabla_a_texto(filas) or None
    if n.endswith(_EXTS_TEXTO):
        return datos.decode("utf-8", errors="replace") or None
    return None


# --------------------------------------------------------------------------- #
# Construccion del Contexto desde la BD (rango / multi-semana)                 #
# --------------------------------------------------------------------------- #


def semanas_de_operaciones(operaciones: list[dict[str, Any]] | None) -> set[str]:
    """Conjunto de lunes ISO de las semanas tocadas por las fechas de las operaciones.

    PURA respecto a la BD: solo mira las `fecha` de cada operacion (eventos y turnos). Fechas
    invalidas o vacias se ignoran. Lo usa la construccion del contexto de VALIDACION para saber
    que semanas cargar (franjas + turnos vivos).
    """
    lunes: set[str] = set()
    for op in operaciones or []:
        semana = rota.lunes_de_semana_iso(str(op.get("fecha", "") or ""))
        if semana:
            lunes.add(semana)
    return lunes


def construir_contexto_prompt(*, nombres_miembros: dict[str, str]) -> pi.Contexto:
    """Contexto MINIMO para el PROMPT (pre-claude): roster + slots por defecto, sin fechas.

    No necesita fechas ni turnos: el prompt solo embebe el roster valido y los NOMBRES de slot
    de franja que claude puede usar. La validacion real (rango/conflictos) ocurre despues con
    `construir_contexto_validacion`.
    """
    return pi.Contexto(
        miembros=dict(nombres_miembros),
        nombres_franja=set(_SLOTS_DEFECTO),
        turnos=[],
    )


def construir_contexto_validacion(
    operaciones: list[dict[str, Any]] | None,
    *,
    nombres_miembros: dict[str, str],
) -> pi.Contexto:
    """Contexto de VALIDACION/CONFLICTO (post-claude) para el RANGO de las operaciones.

    Calcula las semanas tocadas por las fechas de `operaciones`, carga las franjas y turnos
    VIVOS de cada una y construye un `Contexto` multi-semana:
      - `nombres_franja`: union de los nombres distintos de `rota_franjas` de esas semanas + la
        plantilla por defecto (`_SLOTS_DEFECTO`), normalizados.
      - `franjas_nombre`: mapa id->nombre de todas esas franjas (resuelve el slot de un turno).
      - `turnos`: los turnos vivos de todas esas semanas (para celdas ocupadas y modificar).

    Para las semanas SIN franjas, los nombres por defecto siguen siendo validos (el aplicar
    siembra la semana). NO persiste nada aqui (la siembra real ocurre en `aplicar_propuesta`).
    """
    nombres_franja: set[str] = set(_SLOTS_DEFECTO)
    franjas_nombre: dict[str, str] = {}
    turnos: list[dict[str, Any]] = []
    for semana in sorted(semanas_de_operaciones(operaciones)):
        for f in repos.listar_franjas_semana(semana):
            fid = str(f["id"])
            nombre = str(f.get("nombre", "") or "")
            if nombre:
                franjas_nombre[fid] = nombre
                nombres_franja.add(nombre)
        turnos.extend(repos.listar_turnos_rota(semana=semana))
    return pi.Contexto(
        miembros=dict(nombres_miembros),
        nombres_franja=nombres_franja,
        turnos=turnos,
        franjas_nombre=franjas_nombre,
    )


# --------------------------------------------------------------------------- #
# Prompt del claude -p READ-ONLY                                              #
# --------------------------------------------------------------------------- #

_ESQUEMA_JSON = (
    '{"operaciones": [\n'
    '  {"tipo": "crear_evento", "fecha": "AAAA-MM-DD", "hora": "HH:MM"|null, '
    '"titulo": "...", "contenido": "..."?, "nota": "..."?, '
    '"tipo_cobertura": "transmision|imagenes|no_cubrir"?, "prioridad": "alta|media|baja"?},\n'
    '  {"tipo": "crear_turno", "fecha": "AAAA-MM-DD", "franja": "<NOMBRE de la franja/slot tal '
    'como aparece en el documento>", "franja_inicio": "HH:MM"?, "franja_fin": "HH:MM"?, '
    '"miembro_id": "<id de miembro existente>", "miembro_nombre": "..."?, '
    '"nota_relevo": "..."?, "motivo": "..."?},\n'
    '  {"tipo": "modificar_turno", "turno_id": "<id de turno existente>", '
    '"cambios": {"miembro_id": "..."?, "estado": "propuesto|aprobado"?, "override": true?, '
    '"motivo": "..."?, "nota_relevo": "..."?}}\n'
    ']}'
)


# La plantilla del prompt vive en la Biblioteca de Texto como prompt EDITABLE (pestaña
# «Prompts»). Los fragmentos calculados (fuente/reglas según el modo, roster, slots, esquema y la
# cola con el documento embebido) se insertan en sus marcadores `{{...}}`. Si el store fallara,
# la red es la INICIAL del paquete (fuente única, sin texto duplicado aquí).
_PROMPT_ID = "prompt/importar/parrilla"


def _plantilla() -> str:
    """Cuerpo EFECTIVO de la plantilla (store del equipo > inicial del paquete)."""
    from .. import libtexto

    try:
        cuerpo = (libtexto.cuerpo_efectivo(_PROMPT_ID) or "").strip()
    except Exception:  # noqa: BLE001 -- nunca dejar la importación sin prompt por un fallo de lectura
        cuerpo = ""
    return cuerpo or libtexto.cuerpo_inicial(_PROMPT_ID).strip()


def _prompt_tareas(
    *, ruta_doc: str | None, texto_documento: str | None, hoy: str | None,
    permitir_web: bool = False,
) -> str:
    """Prompt AUTOCONTENIDO (en código, sin plantilla editable) para el modo `tareas`: extrae
    ENCARGOS sueltos del equipo (`clase='tarea'`), no eventos. Reusa la misma lógica de FUENTE
    (texto embebido vs fichero leído) que el modo eventos, pero pide `crear_tarea`.

    Va por código (no por la Biblioteca como el de eventos) porque es nuevo y simple: así el
    camino de eventos —con su plantilla editable y tuneada— queda intacto.

    `permitir_web=True` (FRASE escrita a mano en la pestaña Tarea): la frase NOMBRA un evento del
    mundo real (sin fecha en el propio texto), igual que en eventos. Se pide IDENTIFICARLO y
    DATARLO con la web (WebSearch/WebFetch) y volcar esa fecha en `fecha_objetivo`, en vez de
    tratar el texto como un encargo cerrado. Misma identificación que el modo eventos; lo único
    que cambia es la FORMA de salida (`crear_tarea` con `fecha_objetivo`, no `crear_evento`)."""
    ancla_hoy = (
        f"Hoy es {hoy} (zona horaria de Ciudad de México); resuelve cualquier fecha relativa o "
        "sin año respecto a hoy. "
        if hoy
        else ""
    )
    esquema = (
        '{"operaciones": [\n'
        '  {"tipo": "crear_tarea", "titulo": "<qué hay que hacer, conciso e imperativo>", '
        '"detalle": "<notas/contexto/lugar>"?, "prioridad": "alta|media|baja"?, '
        '"fecha_objetivo": "AAAA-MM-DD"?}\n'
        "]}"
    )
    encuadre = (
        "EXTRAES TAREAS (encargos sueltos del equipo de redes) de lo que te den: una lista de "
        "pendientes, un mensaje, una nota, un documento o una sola frase. Cada tarea es algo que "
        "ALGUIEN tiene que HACER (editar un clip, subir fotos, redactar un copy, diseñar una "
        "pieza, revisar algo…), NO un evento ni un partido a cubrir. Aunque haya UNA SOLA tarea, "
        "extráela."
    )
    recordatorio = (
        "\n\nIMPORTANTE: un `crear_tarea` por CADA pendiente, aunque sea uno solo. NO inventes "
        "fechas: si no hay deadline explícito, OMITE `fecha_objetivo`. Devuelve "
        '`{"operaciones": []}` ÚNICAMENTE si no hay ninguna tarea.'
    )
    if texto_documento is not None and permitir_web:
        # FRASE escrita a mano o ENLACE que el servidor no pudo leer: NOMBRA/apunta a un evento
        # real. Identificarlo y datarlo con la web; la fecha resuelta va en `fecha_objetivo` para
        # que la tarea quede fechada (igual que en eventos), no descartada por «no traer deadline».
        fuente = (
            f"{ancla_hoy}Lo que viene MÁS ABAJO es una FRASE que NOMBRA un evento del mundo real "
            "(un combate, un concierto, un partido, un estreno, una gala…) o un ENLACE a su página. "
            "Si es un ENLACE (empieza por http), ÁBRELO con WebFetch; si es un nombre, IDENTIFÍCALO "
            "con WebSearch. AVERIGUA su fecha exacta, hora, recinto/ciudad y de qué trata. Crea UNA "
            "`crear_tarea` cuyo `titulo` sea el evento, con su fecha real en `fecha_objetivo` "
            "(AAAA-MM-DD) y el recinto/ciudad en `detalle`. Si el nombre es ambiguo o recurrente, "
            "prefiere la edición FUTURA más próxima a hoy. Si tras buscar NO encuentras una fecha "
            "creíble, omite `fecha_objetivo`."
        )
        cola = f"\n\nFRASE O ENLACE A IDENTIFICAR:\n```\n{texto_documento}\n```{recordatorio}"
    elif texto_documento is not None:
        fuente = (
            f"{ancla_hoy}{encuadre} El texto de la fuente está más abajo (ya transcrito). Trabaja "
            "EXCLUSIVAMENTE con ese texto; NO abras ni leas ningún fichero ni uses herramientas."
        )
        cola = f"\n\nFUENTE (texto):\n```\n{texto_documento}\n```{recordatorio}"
    else:
        fuente = (
            f"{ancla_hoy}{encuadre} Lee EXCLUSIVAMENTE el documento en la ruta {ruta_doc} "
            "(PDF, imagen/captura o Word) y extrae de ahí las tareas."
        )
        cola = recordatorio
    return (
        "Conviertes lo que te den en una lista de TAREAS (encargos) en JSON. NO escribes en "
        "ninguna base de datos: SOLO devuelves un bloque JSON.\n\n"
        f"{fuente}\n\n"
        "Devuelve EXCLUSIVAMENTE un objeto JSON con esta forma (la única clave es `operaciones`):"
        f"\n{esquema}\n"
        "- `titulo` es obligatorio y conciso (lo que hay que hacer).\n"
        "- `prioridad` y `fecha_objetivo` son opcionales; omítelos si la fuente no los indica.\n"
        "- No añadas texto fuera del JSON."
        f"{cola}"
    )


def componer_prompt(
    *,
    ctx: pi.Contexto,
    ruta_doc: str | None = None,
    texto_documento: str | None = None,
    hoy: str | None = None,
    modo: str = "eventos",
    permitir_web: bool = False,
) -> str:
    """Prompt para que claude convierta el documento en operaciones JSON. PURO.

    DOS modos para la FUENTE del documento:
      - `texto_documento`: el documento ya viene TRANSCRITO (Excel/CSV/texto) e EMBEBIDO en el
        prompt; el run es una transformación texto→JSON sin abrir ficheros (rápido y barato).
      - `ruta_doc`: claude LEE el fichero en disco (PDF, imagen, Word) con su tool de lectura.

    `hoy` (AAAA-MM-DD, CDMX) ANCLA las fechas relativas/sin año: una nota o una frase suelta
    («el sábado», «20 de junio») no traen año; sin ancla no se pueden resolver. Si no se pasa,
    el prompt no incluye la frase de anclaje (los documentos de parrilla traen fechas explícitas).

    NO se ata a una semana: embebe el roster (id+nombre) y los enums, y pide extraer TODO el
    documento (cualquier fecha, cualquier nº de franjas/día), cada operación con fecha ISO.

    `permitir_web=True` (solo con `texto_documento`, en el camino de FRASE escrita a mano): trata
    el texto embebido como una FRASE/BÚSQUEDA que NOMBRA un evento del mundo real (sin fecha en el
    propio texto) y pide IDENTIFICARLO y DATARLO con la web (WebSearch/WebFetch) en vez de extraer
    solo lo literal. Así «la velada del año VI» se resuelve a su fecha/recinto reales. Sin el flag,
    el texto se trata como una transcripción cerrada (NO uses herramientas), comportamiento previo.

    `modo="tareas"` cambia por completo el encargo: extrae ENCARGOS sueltos (`crear_tarea`) en
    vez de eventos, con un prompt autocontenido (no usa la plantilla editable). El roster/slots
    no aplican (una tarea no lleva miembro ni franja).
    """
    if modo == "tareas":
        return _prompt_tareas(
            ruta_doc=ruta_doc, texto_documento=texto_documento, hoy=hoy,
            permitir_web=permitir_web,
        )
    lineas_miembros = "\n".join(
        f'  - id="{mid}" nombre="{nombre}"' for mid, nombre in ctx.miembros.items()
    ) or "  (no hay miembros asignables)"
    lineas_slots = "\n".join(f'  - "{n}"' for n in _SLOTS_DEFECTO)
    # Ancla de fecha: solo si el llamador la pasa (los tests de composición pura no lo hacen).
    ancla_hoy = (
        f"Hoy es {hoy} (zona horaria de Ciudad de México). Resuelve cualquier fecha relativa o "
        "sin año respecto a hoy: si una fecha no trae año, asume el año en curso (o el próximo si "
        "ese día ya pasó). "
        if hoy
        else ""
    )
    # Encuadre GENÉRICO inyectado por CÓDIGO (no por la plantilla editable): la plantilla viva en
    # el store de un equipo ya desplegado pudo inicializarse cuando esto solo importaba PARRILLAS de
    # turnos —y remataba con «si no es una parrilla, vacío»—. Como `importar_inicial` no pisa el
    # store, editar la INICIAL no llega a ese equipo. Estos fragmentos sí (van en {{FUENTE}} y
    # {{COLA_FUENTE}}, marcadores que toda versión de la plantilla conserva): generalizan el
    # encuadre y ANULAN ese corte para que UN solo evento (cartelera, nota, frase) también cuente.
    encuadre = (
        "EXTRAES EVENTOS de lo que te den. La fuente puede ser CUALQUIER COSA (una parrilla/rota de "
        "turnos, la cartelera o agenda de un recinto, una nota o página web de un evento, o una sola "
        "frase) y el evento de CUALQUIER TIPO (un partido, un concierto, una función de lucha libre, "
        "una rueda de prensa, un estreno, una conferencia…), no solo deportes ni turnos. Aunque haya "
        "UN SOLO evento, extráelo: NO exijas que la fuente sea una parrilla completa. "
    )
    recordatorio_final = (
        "\n\nIMPORTANTE: emite un `crear_evento` por CADA evento con fecha que aparezca arriba, "
        "aunque sea uno solo y aunque la fuente NO sea una parrilla de turnos. Devuelve "
        '`{"operaciones": []}` ÚNICAMENTE si no hay NINGÚN evento (ni turno) con fecha.'
    )

    if texto_documento is not None and permitir_web:
        # FRASE escrita a mano o ENLACE que el servidor no pudo leer (403/bloqueo): NO es un
        # documento cerrado. Hay que identificarlo/datarlo con la web; sin esto el modelo no
        # resuelve la fecha y devuelve `{"operaciones": []}` («no lo encuentra»).
        fuente = (
            f"{ancla_hoy}{encuadre}Lo que viene MÁS ABAJO NO es un documento completo: es una FRASE "
            "que NOMBRA uno o más eventos del mundo real (un combate, un concierto, un partido, un "
            "estreno, una gala…) o un ENLACE a la página de un evento. Si es un ENLACE (empieza por "
            "http), ÁBRELO con WebFetch y extrae el evento de esa página; si es un nombre, "
            "IDENTIFÍCALO con WebSearch. En ambos casos AVERIGUA su fecha exacta, hora, "
            "recinto/ciudad y de qué trata, y emite el `crear_evento` con su fecha ISO real. Si el "
            "nombre es ambiguo o recurrente, prefiere la edición/fecha FUTURA más próxima a hoy. Si "
            "tras buscar NO encuentras una fecha creíble para un evento, ese evento NO se emite."
        )
        regla_fuente = (
            "- Lo de abajo casi nunca trae la fecha: BÚSCALA/LÉELA en la web (WebSearch/WebFetch) "
            "antes de descartar nada. No inventes fechas; usa solo las que confirme la web."
        )
        cola_fuente = (
            f"\n\nFRASE O ENLACE A IDENTIFICAR:\n```\n{texto_documento}\n```{recordatorio_final}"
        )
    elif texto_documento is not None:
        fuente = (
            f"{ancla_hoy}{encuadre}El documento ya está TRANSCRITO a texto más abajo (es una hoja "
            "de cálculo/CSV, una página web o texto plano). Trabaja EXCLUSIVAMENTE con ese texto; NO "
            "abras ni leas ningún fichero ni uses herramientas. IMPORTANTE: el documento puede "
            "tener VARIAS HOJAS/secciones, cada una marcada con una línea «### HOJA: <nombre>»; "
            "recórrelas TODAS y extrae las operaciones de CADA hoja (no te quedes solo en la primera)."
        )
        regla_fuente = "- No uses herramientas: todo lo que necesitas está en el texto de abajo."
        cola_fuente = (
            f"\n\nDOCUMENTO (transcripción):\n```\n{texto_documento}\n```{recordatorio_final}"
        )
    else:
        fuente = (
            f"{ancla_hoy}{encuadre}Lee EXCLUSIVAMENTE el documento en la ruta {ruta_doc} "
            "(PDF, imagen/captura o Word)."
        )
        regla_fuente = "- No uses herramientas más allá de LEER el documento de la ruta indicada."
        cola_fuente = recordatorio_final

    # Inserta los fragmentos calculados en la plantilla editable. El orden deja COLA_FUENTE (que
    # puede llevar el documento embebido del usuario) al final, para no reescanear su contenido.
    return (
        _plantilla()
        .replace("{{FUENTE}}", fuente)
        .replace("{{MIEMBROS}}", lineas_miembros)
        .replace("{{SLOTS}}", lineas_slots)
        .replace("{{REGLA_FUENTE}}", regla_fuente)
        .replace("{{ESQUEMA_JSON}}", _ESQUEMA_JSON)
        .replace("{{COLA_FUENTE}}", cola_fuente)
    )


# --------------------------------------------------------------------------- #
# Lanzamiento del job (lo llama la API tras crear la propuesta)               #
# --------------------------------------------------------------------------- #


class ParrillaImportError(RuntimeError):
    """Error con mensaje ya en espanol, apto para mostrar al usuario."""


def lanzar(
    *,
    propuesta_id: str,
    doc_nombre: str,
    doc_ext: str,
    nombres_miembros: dict[str, str],
    autor: dict[str, str] | None = None,
    modo: str = "eventos",
) -> dict[str, Any]:
    """Compone el prompt y ENCOLA el job READ-ONLY. Dos caminos según el FORMATO del documento:

    - Hoja de cálculo / CSV / texto: lo TRANSCRIBIMOS a texto aquí (en el back, que tiene S3) y
      lo EMBEBEMOS en el prompt. El run es una transformación texto→JSON sin abrir ficheros (sin
      tools de lectura): rápido y barato.
    - PDF / imagen / Word: claude lo LEE como fichero. El back NO escribe los bytes: decide una
      ruta local (bajo `KENI_DATA_DIR`, idéntica en back y worker) y el WORKER baja el objeto de
      S3 a esa ruta (`prefetch_s3`) ANTES de correr claude. `dir_temporal` lo limpia al terminar.

    `doc_nombre` es la KEY del objeto en el almacén de media. Devuelve el registro de generación.
    """
    datos = media.leer_media(doc_nombre)
    if datos is None:
        raise ParrillaImportError("El documento subido ya no está disponible.")

    ctx = construir_contexto_prompt(nombres_miembros=nombres_miembros)
    procesar_spec = jobspec.construir_parrilla_import(propuesta_id=propuesta_id)
    procesar = jobspec.reconstruir_procesar({"procesar": procesar_spec})

    texto = _extraer_texto_documento(datos, doc_nombre)
    if texto is not None:
        # Documento TRANSCRITO y embebido: nada de ficheros ni tools de lectura.
        return generar.lanzar(
            tipo="parrilla-import",
            titulo="Importar parrilla",
            marca="",
            prompt=componer_prompt(ctx=ctx, texto_documento=texto, hoy=_hoy_cdmx(), modo=modo),
            procesar=procesar,
            procesar_spec=procesar_spec,
            autor=autor,
            endurecer=_endurecer(lee_fichero=False),
        )

    # Formato que claude lee como FICHERO (PDF/imagen/Word): el WORKER lo baja de S3 a `ruta_doc`
    # (misma ruta en back y worker vía `KENI_DATA_DIR`; no dependemos de /tmp compartido).
    base = rutas.dir_config() / "subidas-tmp"
    base.mkdir(parents=True, exist_ok=True)
    carpeta = base / f"parrilla-{uuid.uuid4().hex}"
    carpeta.mkdir(parents=True, exist_ok=True)
    ext = (doc_ext or "").lstrip(".") or "bin"
    ruta_doc = str(carpeta / f"documento.{ext}")
    return generar.lanzar(
        tipo="parrilla-import",
        titulo="Importar parrilla",
        marca="",
        prompt=componer_prompt(ctx=ctx, ruta_doc=ruta_doc, hoy=_hoy_cdmx(), modo=modo),
        procesar=procesar,
        procesar_spec=procesar_spec,
        dir_temporal=carpeta,
        prefetch_s3={"clave": doc_nombre, "destino": ruta_doc},
        autor=autor,
        endurecer=_endurecer(lee_fichero=True),
    )


def lanzar_desde_texto(
    *,
    propuesta_id: str,
    texto: str,
    nombres_miembros: dict[str, str],
    autor: dict[str, str] | None = None,
    modo: str = "eventos",
    permitir_web: bool = False,
) -> dict[str, Any]:
    """Encola el job READ-ONLY a partir de TEXTO ya extraído (un enlace o texto pegado), sin
    fichero. Es la MISMA rama "texto embebido" de `lanzar` (transformación texto→JSON sin tools
    de lectura): el texto se EMBEBE en el prompt y `claude -p` propone los eventos/turnos.

    `permitir_web=True` (lo pasa el camino de FRASE escrita a mano, NO el de enlace ya extraído):
    el texto es el NOMBRE de un evento, no una transcripción; se habilita la web para que el
    modelo lo IDENTIFIQUE y DATE online. Aplica a AMBOS modos (`eventos` y `tareas`): una frase
    en la pestaña Tarea nombra el mismo evento real, solo cambia la forma de salida.
    """
    web = permitir_web
    ctx = construir_contexto_prompt(nombres_miembros=nombres_miembros)
    procesar_spec = jobspec.construir_parrilla_import(propuesta_id=propuesta_id)
    procesar = jobspec.reconstruir_procesar({"procesar": procesar_spec})
    return generar.lanzar(
        tipo="parrilla-import",
        titulo="Importar parrilla",
        marca="",
        prompt=componer_prompt(
            ctx=ctx, texto_documento=texto, hoy=_hoy_cdmx(), modo=modo, permitir_web=web
        ),
        procesar=procesar,
        procesar_spec=procesar_spec,
        autor=autor,
        endurecer=_endurecer(lee_fichero=False, permitir_web=web),
    )


# --------------------------------------------------------------------------- #
# Post-procesado (corre en el WORKER al terminar el job)                       #
# --------------------------------------------------------------------------- #


def construir_procesar_parrilla_import(*, propuesta_id: str):  # noqa: ANN201
    """Devuelve el callback `procesar(salida, metricas) -> dict` del job de import (worker).

    Parsea el JSON de claude (que puede traer fechas de un año entero), re-construye el contexto
    VIVO de las SEMANAS tocadas por las fechas devueltas (no una sola), valida con el dominio
    puro y persiste el resultado en `parrilla_propuesta`: estado `pendiente` con las operaciones
    validas + un `resumen`, o `error` si claude no devolvió JSON legible / ninguna operación
    válida. El roster de miembros se resuelve aquí (no viaja en el spec: puede cambiar entre
    encolar y ejecutar) usando el MISMO criterio que la rota (usuarios con `cobertura`).

    El parseo se hace en DOS pasos porque el contexto multi-semana depende de las fechas: 1)
    extraer el bloque JSON crudo para conocer las fechas y cargar esas semanas; 2) validar las
    operaciones contra ese contexto. Asi un documento anual se valida contra el estado real de
    cada semana que toca.
    """

    def procesar(salida: str, _metricas: object) -> dict[str, Any]:
        nombres = _roster_miembros()
        # Paso 1: extraer las ops crudas para saber QUE semanas tocar (sin validar todavia).
        crudas = pi.extraer_bloque_json(salida or "") or []
        ctx = construir_contexto_validacion(crudas, nombres_miembros=nombres)
        validas, errores = pi.parsear_y_validar(salida or "", ctx)
        if not validas and errores and any(e.get("indice") == 0 for e in errores):
            # No hubo JSON legible en absoluto: marcamos la propuesta en error.
            motivo = next(
                (e["error"] for e in errores if e.get("indice") == 0),
                "El asistente no devolvió operaciones legibles.",
            )
            repos.actualizar_propuesta_parrilla(
                propuesta_id,
                {"estado": pi.ESTADO_ERROR, "error": motivo, "operaciones": []},
            )
            return {"propuesta_id": propuesta_id, "estado": pi.ESTADO_ERROR, "operaciones": 0}
        resumen = _resumen(validas, errores)
        repos.actualizar_propuesta_parrilla(
            propuesta_id,
            {
                "estado": pi.ESTADO_PENDIENTE,
                "operaciones": validas,
                "resumen": resumen,
                "error": "",
            },
        )
        return {
            "propuesta_id": propuesta_id,
            "estado": pi.ESTADO_PENDIENTE,
            "operaciones": len(validas),
            "errores": len(errores),
        }

    return procesar


def _roster_miembros() -> dict[str, str]:
    """Roster valido id->nombre (usuarios con cobertura), MISMO criterio que la rota.

    Import perezoso de `auth` para no acoplar este modulo de dominio al arranque de auth.
    """
    from .. import auth

    return {
        u["id"]: u["usuario"]
        for u in auth.listar_usuarios()
        if u.get("cobertura")
    }


def _resumen(validas: list[dict[str, Any]], errores: list[dict[str, Any]]) -> str:
    """Frase corta para la UI: cuántas operaciones de cada tipo + omitidas."""
    n_ev = sum(1 for o in validas if o.get("tipo") == "crear_evento")
    n_ta = sum(1 for o in validas if o.get("tipo") == "crear_tarea")
    n_tu = sum(1 for o in validas if o.get("tipo") == "crear_turno")
    n_mo = sum(1 for o in validas if o.get("tipo") == "modificar_turno")
    partes: list[str] = []
    if n_ev:
        partes.append(f"{n_ev} evento(s) nuevo(s)")
    if n_ta:
        partes.append(f"{n_ta} tarea(s) nueva(s)")
    if n_tu:
        partes.append(f"{n_tu} turno(s) nuevo(s)")
    if n_mo:
        partes.append(f"{n_mo} modificación(es) de turno")
    base = ", ".join(partes) if partes else "sin operaciones"
    if errores:
        base += f" · {len(errores)} fila(s) omitida(s)"
    return base


__all__ = [
    "componer_prompt",
    "construir_contexto_prompt",
    "construir_contexto_validacion",
    "construir_procesar_parrilla_import",
    "semanas_de_operaciones",
]
