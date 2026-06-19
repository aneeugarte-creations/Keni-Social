"""Tratamientos de Claude del gestor de AUDIO: lanzan un artefacto y lo rellenan en 2º plano.

Cada tratamiento (limpio/resumen/preguntas/ideas/corregido) es una generación `claude -p` sobre la
transcripción. A diferencia del lanzamiento manual de un prompt (`prompts_lanzar`), aquí la SALIDA se
ESCRIBE en su fila `audio_artefactos` (post-procesado `PROC_AUDIO_ARTEFACTO`): así el artefacto se
genera en segundo plano y aparece 'listo' en la lista aunque el frontend esté cerrado. El SRT y el
texto plano NO pasan por aquí (los genera el motor sin Claude).
"""

from __future__ import annotations

import json
from typing import Any

from .. import libprompts, repos
from . import generar, jobspec


class AudioArtefactoError(RuntimeError):
    """Error de un tratamiento de audio, con mensaje en español apto para mostrar."""


# tipo de artefacto -> (prompt de librería, formato del contenido, título legible). Solo los
# tratamientos de Claude; 'srt'/'texto' los crea el motor. 'corregido' es seguimiento de 'preguntas'.
TRATAMIENTOS: dict[str, tuple[str, str, str]] = {
    "limpio": ("prompt/audio/limpiar", "txt", "Limpio"),
    "resumen": ("prompt/audio/resumir", "md", "Resumen"),
    "preguntas": ("prompt/audio/aclarar", "md", "Preguntas"),
    "ideas": ("prompt/audio/ideas", "md", "Ideas"),
    "clips": ("prompt/audio/clips", "md", "Clips"),
    "capitulado": ("prompt/audio/capitulado", "txt", "Capítulos"),
    "corregido": ("prompt/audio/corregir", "txt", "Corregido"),
}

# Tratamientos que SIEMPRE parten de la transcripción con timestamps (no del texto de su fuente):
# necesitan los tiempos para localizar momentos ('clips') o anclar capítulos ('capitulado'), igual
# que 'corregido' los necesita para citar el fragmento.
_REQUIEREN_TIEMPOS = frozenset({"corregido", "clips", "capitulado"})


def _mmss(ms: Any) -> str:
    try:
        total = max(0, int(ms)) // 1000
    except (TypeError, ValueError):
        total = 0
    return f"{total // 60:02d}:{total % 60:02d}"


def bloque_de_transcripcion(transcripcion: dict[str, Any]) -> str:
    """Texto de la transcripción con timestamps por segmento, para inyectar como contexto del agente."""
    crudo = transcripcion.get("segmentos") or ""
    try:
        segs = json.loads(crudo) if isinstance(crudo, str) and crudo else (crudo or [])
    except (ValueError, TypeError):
        segs = []
    if isinstance(segs, list) and segs:
        return "\n".join(
            f"[{_mmss(s.get('inicio_ms', 0))}] {s.get('texto', '')}".rstrip() for s in segs
        )
    return transcripcion.get("texto") or ""


def construir_procesar_audio_artefacto(artefacto_id: str):  # noqa: ANN201 -- generaciones.Procesar
    """Post-procesado: escribe la salida de Claude en el artefacto y lo marca 'listo'."""

    def procesar(salida: str, _metricas: object) -> dict[str, object]:
        contenido = (salida or "").strip()
        repos.actualizar_audio_artefacto(
            artefacto_id, {"contenido": contenido, "estado": "listo", "error": ""}
        )
        return {"artefacto_id": artefacto_id}

    return procesar


def _fuente_del_tratamiento(
    transcripcion: dict[str, Any], tipo: str, origen: dict[str, Any] | None
) -> tuple[str, str, str]:
    """Texto de entrada + herencia (`origen_id`, `origen_version`) de un tratamiento.

    Regla: los tratamientos que requieren tiempos ('corregido'/'clips'/'capitulado') y la fuente base
    (sin origen, o el propio SRT) parten de la transcripción con timestamps; cualquier otro artefacto
    parte de su `contenido` (encadenar tratamientos). La versión es la `actualizado` de la fuente al
    generar, para detectar después si la fuente cambió.
    """
    if origen is None:
        return bloque_de_transcripcion(transcripcion), "", transcripcion.get("actualizado", "") or ""
    version = origen.get("actualizado", "") or ""
    if tipo in _REQUIEREN_TIEMPOS or origen.get("tipo") == "srt":
        return bloque_de_transcripcion(transcripcion), origen.get("id", "") or "", version
    return origen.get("contenido", "") or "", origen.get("id", "") or "", version


def lanzar_tratamiento(
    transcripcion: dict[str, Any],
    tipo: str,
    *,
    origen: dict[str, Any] | None = None,
    autor: dict[str, str] | None = None,
    respuestas: list[str] | None = None,
) -> dict[str, Any]:
    """Crea el artefacto (estado 'generando') y lanza la generación de Claude que lo rellenará.

    `origen` es el artefacto del que parte (None => transcripción base); fija la herencia del nuevo
    artefacto. Devuelve `{"artefacto": <fila>, "gen": <registro>}`. Lanza `AudioArtefactoError` si el
    tipo no es un tratamiento, si falta el prompt de librería o si no hay texto del que partir.
    """
    if tipo not in TRATAMIENTOS:
        raise AudioArtefactoError(f"Tratamiento no válido: {tipo!r}.")
    prompt_id, formato, titulo = TRATAMIENTOS[tipo]

    bloque, origen_id, origen_version = _fuente_del_tratamiento(transcripcion, tipo, origen)
    if not bloque.strip():
        raise AudioArtefactoError("La fuente del tratamiento aún no tiene texto.")
    if tipo == "corregido" and respuestas:
        dudas = "\n".join(f"- {r}" for r in respuestas if isinstance(r, str) and r.strip())
        if dudas:
            bloque = f"{bloque}\n\n## Respuestas del equipo a las dudas\n{dudas}"

    doc = libprompts.obtener(prompt_id)
    if doc is None or doc.tipo != "prompt":
        raise AudioArtefactoError(f"Falta el prompt «{prompt_id}» en la biblioteca.")
    publicado = libprompts.cuerpo_publicado(prompt_id)
    cuerpo = publicado if publicado is not None else doc.cuerpo

    artefacto = repos.crear_audio_artefacto(
        transcripcion_id=transcripcion["id"], tipo=tipo, titulo=titulo,
        formato=formato, estado="generando", origen_id=origen_id, origen_version=origen_version,
    )
    procesar_spec = jobspec.construir_audio_artefacto(artefacto["id"])
    prompt_final = generar.componer(cuerpo, [], bloque)
    try:
        gen = generar.lanzar(
            tipo="prompt",
            titulo=f"Audio · {titulo}",
            marca=transcripcion.get("marca", "") or "",
            prompt=prompt_final,
            procesar=jobspec.reconstruir_procesar({"procesar": procesar_spec}),
            procesar_spec=procesar_spec,
            autor=autor or {},
        )
    except Exception as e:  # noqa: BLE001 -- cola llena/presupuesto: marca el artefacto en error
        repos.actualizar_audio_artefacto(
            artefacto["id"], {"estado": "error", "error": "No se pudo lanzar el tratamiento (cola/presupuesto)."}
        )
        raise AudioArtefactoError("No se pudo lanzar el tratamiento (cola o presupuesto).") from e
    repos.actualizar_audio_artefacto(artefacto["id"], {"gen_id": gen["id"]})
    artefacto["gen_id"] = gen["id"]
    return {"artefacto": artefacto, "gen": gen}
