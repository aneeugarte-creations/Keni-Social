"""Capa de I/O del job de IMPORTACION de parrilla (#parrilla-import).

Separa los SIDE-EFFECTS del dominio PURO (`dominio.parrilla_import`): aqui se construye el
`Contexto` desde la BD (`repos`), se compone el PROMPT del `claude -p` READ-ONLY y se arma el
post-procesado (`procesar`) que el WORKER ejecuta al terminar el job: parsea el JSON de claude,
re-construye el contexto VIVO de la semana, valida con el dominio puro y guarda las operaciones
+ resumen en la fila `parrilla_propuesta` (estado `pendiente`, o `error` con motivo).

Claude NUNCA escribe en el calendario: el prompt le pide EXCLUSIVAMENTE un bloque JSON; el
codigo Python valida y, mas tarde y solo si el usuario acepta, aplica el diff (otra capa).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from .. import media, repos, rutas
from . import generar, jobspec
from . import parrilla_import as pi

_log = logging.getLogger("keni_consola.parrilla_import_job")

# Topes del prompt: una semana real tiene pocos eventos/turnos/miembros; acotamos por defensa.
_MAX_FILAS_CONTEXTO = 500

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
# Construccion del Contexto desde la BD (lo usa el job Y el /aplicar)          #
# --------------------------------------------------------------------------- #


def construir_contexto(semana: str, *, nombres_miembros: dict[str, str]) -> pi.Contexto:
    """Construye el `Contexto` de validacion de la semana objetivo desde `repos`.

    `nombres_miembros` (id -> nombre) es el roster valido (lo resuelve la API desde `auth`,
    igual que la rota). Lee las franjas y los turnos VIVOS de la semana. Se usa tanto al lanzar
    el job (snapshot para el prompt) como al re-validar en `/aplicar` (estado actual de la BD).
    """
    franjas = repos.listar_franjas_semana(semana) if semana else []
    turnos = repos.listar_turnos_rota(semana=semana) if semana else []
    dias = _dias_de_semana(semana)
    return pi.Contexto(
        semana=semana,
        dias=dias,
        franjas_ids={str(f["id"]) for f in franjas},
        miembros=dict(nombres_miembros),
        turnos=turnos,
    )


def _dias_de_semana(lunes_iso: str) -> list[str]:
    """Las 7 fechas ISO (lunes->domingo) de la semana. [] si `lunes_iso` no parsea."""
    from datetime import date, timedelta

    try:
        lunes = date.fromisoformat(lunes_iso)
    except (ValueError, TypeError):
        return []
    lunes = lunes - timedelta(days=lunes.weekday())
    return [(lunes + timedelta(days=i)).isoformat() for i in range(7)]


# --------------------------------------------------------------------------- #
# Prompt del claude -p READ-ONLY                                              #
# --------------------------------------------------------------------------- #

_ESQUEMA_JSON = (
    '{"operaciones": [\n'
    '  {"tipo": "crear_evento", "fecha": "YYYY-MM-DD", "hora": "HH:MM"|null, '
    '"titulo": "...", "contenido": "..."?, "nota": "..."?, '
    '"tipo_cobertura": "transmision|imagenes|no_cubrir"?, "prioridad": "alta|media|baja"?},\n'
    '  {"tipo": "crear_turno", "fecha": "YYYY-MM-DD", "franja_id": "<id de franja existente>", '
    '"miembro_id": "<id de miembro existente>", "miembro_nombre": "..."?, '
    '"nota_relevo": "..."?, "motivo": "..."?},\n'
    '  {"tipo": "modificar_turno", "turno_id": "<id de turno existente>", '
    '"cambios": {"miembro_id": "..."?, "estado": "propuesto|aprobado"?, "override": true?, '
    '"motivo": "..."?, "nota_relevo": "..."?}}\n'
    ']}'
)


def componer_prompt(
    *, ruta_doc: str, semana: str, ctx: pi.Contexto
) -> str:
    """Prompt para que claude LEA el documento y EMITA las operaciones como JSON. PURO.

    Embebe el CONTEXTO de la semana (dias, franjas con su id/nombre/rango, miembros validos,
    enums) para que claude SOLO pueda asignar franjas y miembros EXISTENTES. Le prohibe
    inventar gente o franjas y le exige una unica salida: un bloque ```json con el esquema.
    """
    franjas = repos.listar_franjas_semana(semana) if semana else []
    lineas_franjas = "\n".join(
        f'  - id="{f["id"]}" nombre="{f.get("nombre", "")}" '
        f'{f.get("inicio", "")}-{f.get("fin", "")}'
        + (" (DESCANSO)" if f.get("es_descanso") else "")
        for f in franjas[:_MAX_FILAS_CONTEXTO]
    ) or "  (la semana aún no tiene franjas: NO propongas crear_turno)"
    lineas_miembros = "\n".join(
        f'  - id="{mid}" nombre="{nombre}"'
        for mid, nombre in list(ctx.miembros.items())[:_MAX_FILAS_CONTEXTO]
    ) or "  (no hay miembros asignables)"
    turnos = repos.listar_turnos_rota(semana=semana) if semana else []
    lineas_turnos = "\n".join(
        f'  - turno_id="{t.get("id", "")}" fecha={t.get("fecha", "")} '
        f'franja_id="{t.get("franja_id", "")}" miembro_id="{t.get("miembro_id", "")}" '
        f'estado={t.get("estado", "")}'
        for t in turnos[:_MAX_FILAS_CONTEXTO]
    ) or "  (la semana no tiene turnos asignados todavía)"
    dias = ", ".join(ctx.dias)

    return (
        "Eres un asistente que convierte un documento de PLANIFICACIÓN de la rota/parrilla de un "
        "equipo de redes sociales en operaciones estructuradas. Lee EXCLUSIVAMENTE el documento "
        f"en la ruta {ruta_doc} (puede ser PDF, imagen/captura, Word, Excel o texto).\n\n"
        f"SEMANA OBJETIVO (lunes): {semana}. Las fechas de TODAS las operaciones deben caer en "
        f"estos días: {dias}. Ignora cualquier cosa del documento fuera de esta semana.\n\n"
        "FRANJAS de la semana (usa SOLO estos id en `franja_id`; NO inventes franjas):\n"
        f"{lineas_franjas}\n\n"
        "MIEMBROS asignables (usa SOLO estos id en `miembro_id`; NO inventes personas; si el "
        "documento nombra a alguien que no está en esta lista, OMÍTELO):\n"
        f"{lineas_miembros}\n\n"
        "TURNOS ya existentes (para `modificar_turno`, usa SOLO estos `turno_id`):\n"
        f"{lineas_turnos}\n\n"
        "Valores de enum válidos: tipo_cobertura ∈ {transmision, imagenes, no_cubrir}; "
        "prioridad ∈ {alta, media, baja}; estado ∈ {propuesto, aprobado}.\n\n"
        "REGLAS ESTRICTAS:\n"
        "- NO escribas en ningún sitio ni uses herramientas más allá de LEER el documento.\n"
        "- Solo puedes asignar miembros y franjas que aparezcan en las listas de arriba.\n"
        "- Si el documento crea un turno para una persona/franja que no existe, OMITE esa fila.\n"
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
    semana: str,
    nombres_miembros: dict[str, str],
    autor: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Materializa el documento en un temporal, compone el prompt y ENCOLA el job READ-ONLY.

    `doc_nombre` es la KEY del objeto en el almacen de media (lo subio la API). Se materializa
    en un dir temporal PERSISTENTE que `generaciones` borra al terminar el job, y se pasa como
    UNICO `--add-dir` (claude solo puede LEER ahi). Devuelve el registro de generacion (la API
    extrae su `id` -> `gen_id`). Lanza `ParrillaImportError` si el documento no existe.
    """
    datos = media.leer_media(doc_nombre)
    if datos is None:
        raise ParrillaImportError("El documento subido ya no está disponible.")

    # Materializamos el documento bajo el volumen de datos COMPARTIDO (`KENI_DATA_DIR`), NO en
    # /tmp: en hosted el `claude -p` corre en el contenedor WORKER, que comparte `/data` con el
    # back pero NO su /tmp. Un doc en /tmp sería invisible al worker y claude no leería nada
    # (→ 0 operaciones). `generaciones` borra este dir (`dir_temporal`) al terminar el job.
    base = rutas.dir_config() / "subidas-tmp"
    base.mkdir(parents=True, exist_ok=True)
    carpeta = base / f"parrilla-{uuid.uuid4().hex}"
    carpeta.mkdir(parents=True, exist_ok=True)
    ext = (doc_ext or "").lstrip(".") or "bin"
    archivo = f"documento.{ext}"
    (carpeta / archivo).write_bytes(datos)
    ruta_doc = str(carpeta / archivo)

    ctx = construir_contexto(semana, nombres_miembros=nombres_miembros)
    prompt = componer_prompt(ruta_doc=ruta_doc, semana=semana, ctx=ctx)
    procesar_spec = jobspec.construir_parrilla_import(
        propuesta_id=propuesta_id, semana=semana
    )
    return generar.lanzar(
        tipo="parrilla-import",
        titulo="Importar parrilla",
        marca="",
        prompt=prompt,
        procesar=jobspec.reconstruir_procesar({"procesar": procesar_spec}),
        procesar_spec=procesar_spec,
        dir_temporal=carpeta,
        autor=autor,
        endurecer=ENDURECER,
    )


# --------------------------------------------------------------------------- #
# Post-procesado (corre en el WORKER al terminar el job)                       #
# --------------------------------------------------------------------------- #


def construir_procesar_parrilla_import(*, propuesta_id: str, semana: str):  # noqa: ANN201
    """Devuelve el callback `procesar(salida, metricas) -> dict` del job de import (worker).

    Reconstruye el contexto VIVO de la semana, parsea+valida el JSON de claude y persiste el
    resultado en `parrilla_propuesta`: estado `pendiente` con las operaciones validas + un
    `resumen`, o `error` si claude no devolvió JSON legible / ninguna operación válida.
    El roster de miembros se resuelve aquí (no viaja en el spec: puede cambiar entre encolar y
    ejecutar) usando el MISMO criterio que la rota (usuarios con `cobertura`).
    """

    def procesar(salida: str, _metricas: object) -> dict[str, Any]:
        nombres = _roster_miembros()
        ctx = construir_contexto(semana, nombres_miembros=nombres)
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
    "construir_contexto",
    "construir_procesar_parrilla_import",
]
