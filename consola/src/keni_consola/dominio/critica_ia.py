"""Crítica IA (post-aprobación, con VISIÓN): el crítico que vota el nivel final de la cadena.

Tras los dos OK humanos, este módulo ENCOLA un `claude -p` con visión que critica la pieza
(arte sintético en marca periodística, coherencia imagen↔texto, sustancia, rigor factual,
hashtags, voz) y VOTA el nivel "Crítica IA" de la cadena. El arte viaja por S3: el worker lo
baja a un dir temporal (`prefetch_s3` + `dir_temporal`, igual que la importación de parrilla)
para que claude lo LEA con la herramienta Read. El post-procesado parsea el revision JSON y
aplica el voto vía `repos`:

  - `aprueba`  -> aprueba el nivel IA: la cadena queda completa y la pieza se programa sola.
  - `rechaza`  -> rechaza el nivel IA (DISLIKE de IA) + crea un comentario SIN RESOLVER con el
    problema, que frena la auto-programación (gate B) y deja la pieza en el feed para corregir.

El humano tiene la última palabra: al editar se reinicia la cadena (re-crítica) y un coordinador
puede `forzar` (que además resuelve el comentario de la IA). Gateado por `KENI_CRITICA_IA`.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any

from .. import config, repos, rutas
from ..estados import DECISION_APROBADO, DECISION_PENDIENTE, DECISION_RECHAZADO
from ..tiempo import ahora_iso
from . import colaboracion, generar, jobspec

_log = logging.getLogger("keni_consola.critica_ia")

# Herramientas VETADAS al crítico: solo LEE (la imagen) y razona; no escribe ni navega. Read/Glob
# se permiten (necesita Read para ver el arte); todo lo que muta o sale a la red, vetado.
_TOOLS_VETADAS: tuple[str, ...] = (
    "Write",
    "Edit",
    "MultiEdit",
    "NotebookEdit",
    "Bash",
    "WebFetch",
    "WebSearch",
    "mcp__keni-social__keni_crear_publicacion",
    "mcp__keni-social__keni_actualizar_publicacion",
    "mcp__keni-social__keni_enviar_a_revision",
    "mcp__keni-social__keni_aprobar",
    "mcp__keni-social__keni_rechazar",
)

# Tope de longitud del comentario que se sella en el nivel de la cadena (la BD lo guarda corto).
_MAX_COMENTARIO = 500

PROMPT_CRITICA = "prompt/critica"


def _endurecer() -> dict[str, Any]:
    """Run READ-ONLY: veta escritura/red, deja Read (para ver el arte). Acota turnos y coste."""
    return {
        "disallowed_tools": list(_TOOLS_VETADAS),
        "max_turns": 24,
        "max_budget_usd": 8.0,
    }


def _arte_para_prefetch(pub: dict[str, Any]) -> tuple[str, str]:
    """Clave de media del arte a criticar + su extensión, o `("", "")` si no hay foto real.

    Prefiere la FOTO real subida; si no, la imagen compuesta. `imagen_fuente` es una URL externa
    (no una clave de S3): no se puede prefetchear, así que esos casos van sin visión.
    """
    for campo in ("foto", "imagen"):
        clave = str(pub.get(campo) or "").strip()
        if clave:
            ext = clave.rsplit(".", 1)[-1].lower() if "." in clave else "jpg"
            return clave, (ext[:5] or "jpg")
    return "", ""


def _texto_hashtags(pub: dict[str, Any]) -> str:
    h = pub.get("hashtags")
    if isinstance(h, (list, tuple)):
        return " ".join(str(x) for x in h) or "(sin hashtags)"
    return str(h or "").strip() or "(sin hashtags)"


def _contexto_editorial(marca: str) -> str:
    """Voz/normas de la marca como contexto para el crítico (best-effort, "" si no hay)."""
    try:
        docs = generar.adjuntos_copy(marca)
    except Exception:  # noqa: BLE001 -- el contexto editorial es opcional; nunca rompe el lanzamiento
        return ""
    cuerpos = [d.cuerpo.strip() for d in docs if getattr(d, "cuerpo", "").strip()]
    if not cuerpos:
        return ""
    return "\n\n## Contexto editorial de la marca\n\n" + "\n\n---\n\n".join(cuerpos)


def _componer_prompt(*, pub: dict[str, Any], marca: str, red: str, ruta_arte: str) -> str:
    """Renderiza el prompt inicial `prompt/critica` con los datos de la pieza + contexto editorial."""
    from .. import libprompts

    cuerpo = libprompts.cuerpo_efectivo(PROMPT_CRITICA) or libprompts.cuerpo_inicial(PROMPT_CRITICA)
    if ruta_arte:
        arte = (
            "Hay una imagen adjunta. LÉELA con la herramienta Read en esta ruta y JÚZGALA "
            f"visualmente (no asumas, mírala): {ruta_arte}"
        )
    else:
        arte = (
            "La pieza no tiene todavía una foto real adjunta (el arte se sube o se genera "
            "aparte). No puedes juzgar la imagen: evalúa solo el texto y, si esta red exige una "
            "foto real para publicar, anótalo como observación."
        )
    from .. import marcas

    sust = {
        "{{MARCA}}": marcas.etiqueta_de(marca) or marca or "la marca",
        "{{RED}}": str(red or "la red"),
        "{{FORMATO}}": str(pub.get("formato") or "foto"),
        "{{COPY_IN}}": str(pub.get("copy_in") or "").strip() or str(pub.get("titulo") or ""),
        "{{COPY}}": str(pub.get("contenido") or "").strip() or "(sin copy)",
        "{{HASHTAGS}}": _texto_hashtags(pub),
        "{{ARTE}}": arte,
    }
    for marcador, valor in sust.items():
        cuerpo = cuerpo.replace(marcador, valor)
    return cuerpo + _contexto_editorial(marca)


def lanzar_para_publicacion(pieza_id: str) -> dict[str, Any] | None:
    """ENCOLA la crítica IA de una pieza si toca (flag ON, humanos OK, nivel IA pendiente).

    Devuelve el registro de generación encolado, o None si no aplica. Idempotente: la clave
    `critica-ia:{id}` evita un segundo run en curso; además se re-comprueba que el nivel IA
    siga pendiente (si ya fue votado o la cadena cambió, no encola).
    """
    pub = repos.obtener_pieza(pieza_id)
    plat = repos.obtener_pieza_fila(pieza_id)
    if pub is None or plat is None:
        return None
    if not config.etapa_activa(config.ENV_CRITICA_IA, str(pub.get("marca") or "")):
        return None
    cadena = repos.listar_aprobaciones(pieza_id)
    if not colaboracion.humanos_aprobados_ia_pendiente(cadena):
        return None

    marca = str(pub.get("marca") or "")
    red = str(pub.get("red") or "")
    clave_arte, ext = _arte_para_prefetch(pub)

    procesar_spec = jobspec.construir_critica_ia(pieza_id=pieza_id)
    procesar = jobspec.reconstruir_procesar({"procesar": procesar_spec})

    dir_temporal: Path | None = None
    prefetch: dict[str, str] | None = None
    ruta_arte = ""
    if clave_arte:
        base = rutas.dir_config() / "subidas-tmp"
        base.mkdir(parents=True, exist_ok=True)
        carpeta = base / f"critica-{uuid.uuid4().hex}"
        carpeta.mkdir(parents=True, exist_ok=True)
        ruta_arte = str(carpeta / f"arte.{ext}")
        dir_temporal = carpeta
        prefetch = {"clave": clave_arte, "destino": ruta_arte}

    prompt = _componer_prompt(pub=pub, marca=marca, red=red, ruta_arte=ruta_arte)
    return generar.lanzar(
        tipo="critica-ia",
        titulo=f"Crítica IA · {pub.get('titulo', '') or 'pieza'}",
        marca=marca,
        prompt=prompt,
        procesar=procesar,
        procesar_spec=procesar_spec,
        dir_temporal=dir_temporal,
        prefetch_s3=prefetch,
        endurecer=_endurecer(),
        clave_idem=f"critica-ia:{pieza_id}",
        publicacion_id=str(plat.get("publicacion_id", "") or ""),
    )


# --------------------------------------------------------------------------- #
# Post-procesado (corre en el WORKER al terminar el job)                        #
# --------------------------------------------------------------------------- #


def _parsear_revision(salida: str) -> dict[str, Any] | None:
    """Extrae el objeto JSON del revision de la salida de claude (o None si no es legible)."""
    if not salida:
        return None
    texto = salida.strip()
    # Quita una valla de código si la salida vino envuelta en ```json ... ```.
    valla = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", texto, re.DOTALL)
    crudo = valla.group(1) if valla else None
    if crudo is None:
        ini = texto.find("{")
        fin = texto.rfind("}")
        crudo = texto[ini : fin + 1] if ini != -1 and fin > ini else None
    if not crudo:
        return None
    try:
        datos = json.loads(crudo)
    except (ValueError, TypeError):
        return None
    return datos if isinstance(datos, dict) else None


def _resumen_nivel(revision: dict[str, Any] | None, decision: str) -> str:
    """Comentario CORTO que se sella en el nivel de la cadena (lo ve la UI en el nivel IA)."""
    if decision == DECISION_APROBADO:
        return "Crítica IA: sin objeciones de bloqueo."
    com = (revision or {}).get("comentario") if revision else ""
    return ("Crítica IA: " + (str(com).strip() or "pieza con problemas; revísala."))[:_MAX_COMENTARIO]


def _texto_comentario(revision: dict[str, Any] | None) -> str:
    """Comentario DETALLADO (sin resolver) que frena la programación y guía la corrección."""
    if not revision:
        return (
            "🤖 Crítica IA: no devolvió un revision legible; revisa la pieza a mano antes de "
            "programarla."
        )
    lineas = ["🤖 Crítica IA — esta pieza no debería salir tal cual:"]
    com = str(revision.get("comentario") or "").strip()
    if com:
        lineas.append(com)
    for p in revision.get("problemas") or []:
        if not isinstance(p, dict):
            continue
        sev = str(p.get("severidad") or "").strip()
        det = str(p.get("detalle") or "").strip()
        if det:
            lineas.append(f"• ({sev or 'media'}) {det}")
    rec = str(revision.get("recomendacion_formato") or "").strip().lower()
    if rec and rec not in ("foto", ""):
        lineas.append(f"• Recomendación de formato: {rec}.")
    return "\n".join(lineas)


def _reflejar_y_programar(pieza_id: str) -> None:
    """Aplica el estado de la cadena a la pieza y, si quedó aprobada, la programa (best-effort)."""
    cadena = repos.listar_aprobaciones(pieza_id)
    estado_global = colaboracion.estado_cadena(cadena)
    estado_pieza = colaboracion.estado_publicacion_para(estado_global)
    campos: dict[str, Any] = {
        "revisor_id": colaboracion.DECISOR_CRITICA_ID,
        "revisor_nombre": colaboracion.DECISOR_CRITICA_NOMBRE,
        "revisado_en": ahora_iso(),
    }
    if estado_pieza is not None:
        campos["estado"] = estado_pieza
    repos.actualizar_pieza(pieza_id, campos)
    if estado_global == DECISION_APROBADO:
        from .. import auto_programar

        try:
            auto_programar.programar_si_aprobada(pieza_id)
        except Exception:  # noqa: BLE001 -- programar es secundario al voto ya registrado
            _log.exception("Crítica IA: auto-programación falló para %s.", pieza_id)


def aplicar_revision(pieza_id: str, revision: dict[str, Any] | None) -> str | None:
    """Vota el nivel "Crítica IA" de la pieza según `revision`. Devuelve la decisión o None.

    None si la cadena ya no tiene el nivel IA pendiente (cadena cambió / ya votado): no hace
    nada. Si no hay revision legible, RECHAZA por seguridad (no se aprueba a ciegas).
    """
    cadena = repos.listar_aprobaciones(pieza_id)
    nivel = colaboracion.nivel_critica_ia(cadena)
    if nivel is None or nivel.get("decision") != DECISION_PENDIENTE:
        return None

    aprueba = bool(revision) and str(revision.get("veredicto") or "").strip().lower() == "aprueba"
    decision = DECISION_APROBADO if aprueba else DECISION_RECHAZADO
    repos.actualizar_aprobacion(
        nivel["id"],
        {
            "decision": decision,
            "decisor_id": colaboracion.DECISOR_CRITICA_ID,
            "decisor_nombre": colaboracion.DECISOR_CRITICA_NOMBRE,
            "comentario": _resumen_nivel(revision, decision),
            "decidido_en": ahora_iso(),
        },
    )
    if not aprueba:
        # DISLIKE de IA: comentario SIN RESOLVER que frena la auto-programación (gate B) y deja
        # la pieza en el feed con el problema visible para que un humano la corrija.
        plat = repos.obtener_pieza_fila(pieza_id)
        try:
            repos.crear_comentario(
                publicacion_id=str((plat or {}).get("publicacion_id", "") or ""),
                pieza_id=pieza_id,
                texto=_texto_comentario(revision),
                autor={
                    "id": colaboracion.DECISOR_CRITICA_ID,
                    "usuario": colaboracion.DECISOR_CRITICA_NOMBRE,
                },
            )
        except Exception:  # noqa: BLE001 -- el voto ya quedó; el comentario es secundario
            _log.exception("Crítica IA: no se pudo crear el comentario para %s.", pieza_id)
    _reflejar_y_programar(pieza_id)
    return decision


def construir_procesar_critica_ia(*, pieza_id: str):  # noqa: ANN201
    """Devuelve el callback `procesar(salida, metricas) -> dict` del job de crítica (worker)."""

    def procesar(salida: str, _metricas: object) -> dict[str, object]:
        revision = _parsear_revision(salida)
        decision = aplicar_revision(pieza_id, revision)
        return {"critica_ia": {"decision": decision or "", "veredicto": revision or {}}}

    return procesar
