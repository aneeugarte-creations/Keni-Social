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
from typing import Any

from .. import media, repos, rota, rutas
from ..estados import NOMBRE_FRANJA_MANANA_DEFAULT, NOMBRE_FRANJA_TARDE_DEFAULT
from . import generar, jobspec
from . import parrilla_import as pi

_log = logging.getLogger("keni_consola.parrilla_import_job")

# Topes del prompt: acotamos por defensa el numero de filas de contexto que embebemos.
_MAX_FILAS_CONTEXTO = 500

# Nombres de slot por defecto (plantilla de la rota). Un turno propuesto puede usar SIEMPRE
# estos slots aunque la semana objetivo aun no tenga franjas (se siembran al aplicar). El
# "Descanso" se incluye: un documento puede planificar un descanso explicito.
_SLOTS_DEFECTO: tuple[str, ...] = (
    NOMBRE_FRANJA_MANANA_DEFAULT,
    NOMBRE_FRANJA_TARDE_DEFAULT,
    "Descanso",
)

# Endurecimiento del run READ-ONLY: el job SOLO debe LEER el documento y emitir JSON. Vetamos
# las herramientas de ESCRITURA (Write/Edit/Bash) y de RED (WebFetch/WebSearch), ademas de las
# tools MCP de la consola que MUTAN datos (`keni_*` de creacion/edicion/aprobacion). Topamos
# turnos y coste bajos (es una lectura + un JSON, no necesita muchos turnos).
ENDURECER: dict[str, Any] = {
    "disallowed_tools": [
        "Write",
        "Edit",
        "MultiEdit",
        "NotebookEdit",
        "Bash",
        "WebFetch",
        "WebSearch",
        # MCP de escritura de la consola (defensa: el job no debe mutar nada via MCP).
        "mcp__keni-social__keni_crear_contenido",
        "mcp__keni-social__keni_actualizar_contenido",
        "mcp__keni-social__keni_enviar_a_revision",
        "mcp__keni-social__keni_aprobar",
        "mcp__keni-social__keni_rechazar",
        "mcp__keni-social__keni_generar_copy",
    ],
    "max_turns": 6,
    "max_budget_usd": 0.5,
}


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
    '  {"tipo": "crear_turno", "fecha": "AAAA-MM-DD", "franja": "<NOMBRE de slot existente>", '
    '"miembro_id": "<id de miembro existente>", "miembro_nombre": "..."?, '
    '"nota_relevo": "..."?, "motivo": "..."?},\n'
    '  {"tipo": "modificar_turno", "turno_id": "<id de turno existente>", '
    '"cambios": {"miembro_id": "..."?, "estado": "propuesto|aprobado"?, "override": true?, '
    '"motivo": "..."?, "nota_relevo": "..."?}}\n'
    ']}'
)


def componer_prompt(*, ruta_doc: str, ctx: pi.Contexto) -> str:
    """Prompt para que claude LEA el documento y EMITA las operaciones como JSON. PURO.

    NO se ata a una semana: embebe el roster valido (id+nombre), los NOMBRES de slot de franja
    validos y los enums, y le pide extraer TODOS los eventos y turnos del documento, SEA CUAL
    SEA su fecha (puede ser un año entero), cada uno con una fecha ISO explicita (AAAA-MM-DD).
    Para los turnos usa el NOMBRE del slot de franja y un miembro existente. Le prohibe inventar
    gente o franjas y le exige una unica salida: un bloque ```json con el esquema.
    """
    lineas_miembros = "\n".join(
        f'  - id="{mid}" nombre="{nombre}"'
        for mid, nombre in list(ctx.miembros.items())[:_MAX_FILAS_CONTEXTO]
    ) or "  (no hay miembros asignables)"
    lineas_slots = "\n".join(f'  - "{n}"' for n in _SLOTS_DEFECTO)

    return (
        "Eres un asistente que convierte un documento de PLANIFICACIÓN de la rota/parrilla de un "
        "equipo de redes sociales en operaciones estructuradas. Lee EXCLUSIVAMENTE el documento "
        f"en la ruta {ruta_doc} (puede ser PDF, imagen/captura, Word, Excel o texto).\n\n"
        "EXTRAE TODOS los eventos y turnos que encuentres en el documento, SEA CUAL SEA su "
        "fecha: el documento puede cubrir una semana, un mes o un AÑO ENTERO. Cada operación "
        "DEBE llevar una fecha ISO explícita en formato AAAA-MM-DD (resuelve cualquier fecha "
        "relativa o abreviada a su fecha absoluta).\n\n"
        "MIEMBROS asignables (usa SOLO estos id en `miembro_id`; NO inventes personas; si el "
        "documento nombra a alguien que no está en esta lista, OMÍTELO):\n"
        f"{lineas_miembros}\n\n"
        "FRANJAS (slots) válidas para `crear_turno` (usa el NOMBRE EXACTO del slot en `franja`; "
        "NO inventes franjas ni uses ids):\n"
        f"{lineas_slots}\n\n"
        "Valores de enum válidos: tipo_cobertura ∈ {transmision, imagenes, no_cubrir}; "
        "prioridad ∈ {alta, media, baja}; estado ∈ {propuesto, aprobado}.\n\n"
        "REGLAS ESTRICTAS:\n"
        "- NO escribas en ningún sitio ni uses herramientas más allá de LEER el documento.\n"
        "- Solo puedes asignar miembros que aparezcan en la lista de arriba.\n"
        "- En `franja` usa SOLO uno de los nombres de slot de arriba.\n"
        "- Si el documento crea un turno para una persona que no existe, OMITE esa fila.\n"
        "- Emite SOLO operaciones que reflejen el documento; no inventes eventos ni turnos.\n\n"
        "SALIDA: responde con UN ÚNICO bloque de código cercado ```json con esta forma EXACTA, "
        "y NADA de texto antes ni después:\n"
        f"```json\n{_ESQUEMA_JSON}\n```\n"
        "Si el documento no contiene una parrilla, devuelve "
        '```json\n{"operaciones": []}\n```.'
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
) -> dict[str, Any]:
    """Compone el prompt y ENCOLA el job READ-ONLY; el WORKER baja el documento de S3.

    `doc_nombre` es la KEY del objeto en el almacen de media (lo subio la API). El back NO
    materializa los bytes: decide la RUTA local destino (bajo `KENI_DATA_DIR`, identica en back
    y worker) y embebe en el spec una instruccion `prefetch_s3` para que el WORKER descargue el
    objeto de S3 a esa ruta ANTES de correr claude (el worker tiene las credenciales S3). El dir
    se pasa como `dir_temporal` para que `generaciones` lo borre al terminar. Devuelve el
    registro de generacion (la API extrae su `id` -> `gen_id`). Verifica que el objeto exista.
    """
    # Verificamos que el documento sigue en el almacen (el back tambien tiene S3 en hosted).
    if media.leer_media(doc_nombre) is None:
        raise ParrillaImportError("El documento subido ya no está disponible.")

    # Ruta destino BAJO el volumen de datos COMPARTIDO (`KENI_DATA_DIR`): el back la decide pero
    # NO escribe los bytes; los baja el WORKER de S3 (ver `prefetch_s3` en el spec). Asi back y
    # worker resuelven la MISMA ruta y no dependemos de un /tmp compartido (que no existe entre
    # contenedores). `generaciones` borra este dir (`dir_temporal`) al terminar el job.
    base = rutas.dir_config() / "subidas-tmp"
    base.mkdir(parents=True, exist_ok=True)
    carpeta = base / f"parrilla-{uuid.uuid4().hex}"
    carpeta.mkdir(parents=True, exist_ok=True)
    ext = (doc_ext or "").lstrip(".") or "bin"
    ruta_doc = str(carpeta / f"documento.{ext}")

    ctx = construir_contexto_prompt(nombres_miembros=nombres_miembros)
    prompt = componer_prompt(ruta_doc=ruta_doc, ctx=ctx)
    procesar_spec = jobspec.construir_parrilla_import(propuesta_id=propuesta_id)
    return generar.lanzar(
        tipo="parrilla-import",
        titulo="Importar parrilla",
        marca="",
        prompt=prompt,
        procesar=jobspec.reconstruir_procesar({"procesar": procesar_spec}),
        procesar_spec=procesar_spec,
        dir_temporal=carpeta,
        prefetch_s3={"clave": doc_nombre, "destino": ruta_doc},
        autor=autor,
        endurecer=ENDURECER,
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
    n_tu = sum(1 for o in validas if o.get("tipo") == "crear_turno")
    n_mo = sum(1 for o in validas if o.get("tipo") == "modificar_turno")
    partes: list[str] = []
    if n_ev:
        partes.append(f"{n_ev} evento(s) nuevo(s)")
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
