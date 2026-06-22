"""Decisor de FORMATO (etapa PREVIA a Redactar): elige el camino de un tema —`foto` o `carrusel`.

Antes de redactar, un `claude -p` READ-ONLY y BARATO (Haiku) mira SEÑALES ligeras del tema (marca,
evento, nº de sub-historias, titulares, fuentes) y decide si la pieza luce mejor como un único post
de foto o como un carrusel de varias tarjetas. El post-procesado guarda el camino elegido en
`contenido.copy_pendiente` (JSON, SIN migración de esquema, igual que los contadores de intentos);
la etapa de Redactar lo lee y usa el prompt del camino (foto o carrusel). Así la decisión de formato
sale del prompt de Redactar a una etapa propia, visible y editable.

Mismo patrón READ-ONLY que `sugerir_hashtags`/`carrusel`: las señales viajan DENTRO del prompt
(autocontenido), así que el spec del post-procesado solo lleva el `publicacion_id`. Gateado por
`KENI_PIPELINE_DECISOR` (OFF por defecto: sin él, Redactar decide el formato como hoy).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from .. import config, marcas, repos
from . import generar, jobspec

_log = logging.getLogger("keni_consola.decisor")

PROMPT_DECISOR = "prompt/decisor"

# Caminos válidos del Decisor. Ante cualquier salida ilegible o desconocida, caemos a `foto`
# (el formato conservador): nunca forzamos un carrusel por una salida dudosa.
CAMINO_FOTO = "foto"
CAMINO_CARRUSEL = "carrusel"
CAMINOS = (CAMINO_FOTO, CAMINO_CARRUSEL)

# Herramientas VETADAS: la etapa solo razona sobre señales y devuelve un camino; no escribe, no
# navega, no toca el tablero. Mismo criterio READ-ONLY que sugerir-hashtags / la crítica IA.
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


def _endurecer() -> dict[str, Any]:
    """Run READ-ONLY y barato: veta escritura/red, acota turnos y coste, y va con `decisor_modelo`
    (haiku por defecto: una decisión binaria sobre señales ligeras no necesita el modelo grande)."""
    return {
        "disallowed_tools": list(_TOOLS_VETADAS),
        "max_turns": 4,
        "max_budget_usd": 0.5,
        "modelo": config.decisor_modelo(),
    }


def _copy_pendiente(tema: dict[str, Any]) -> dict[str, Any]:
    """Lee y parsea `copy_pendiente` (JSON) de un tema. {} si vacío o ilegible (best-effort)."""
    crudo = str(tema.get("copy_pendiente") or "").strip()
    if not crudo:
        return {}
    try:
        datos = json.loads(crudo)
    except (json.JSONDecodeError, ValueError):
        return {}
    return datos if isinstance(datos, dict) else {}


def _titulares(tema: dict[str, Any], pend: dict[str, Any]) -> list[str]:
    """Titulares de las sub-historias (señal del Decisor): el del tema + el de cada nota propia."""
    titulares: list[str] = []
    vistos: set[str] = set()
    for crudo in [tema.get("titulo")] + [f.get("titulo") for f in (pend.get("fotos_notas") or [])]:
        t = str(crudo or "").strip()
        if t and t.lower() not in vistos:
            vistos.add(t.lower())
            titulares.append(t)
    return titulares


def _componer_prompt(tema: dict[str, Any], pend: dict[str, Any]) -> str:
    """Renderiza `prompt/decisor` con las señales ligeras del tema (marca, evento, notas, titulares)."""
    from .. import libprompts

    cuerpo = libprompts.cuerpo_efectivo(PROMPT_DECISOR) or libprompts.cuerpo_inicial(PROMPT_DECISOR)
    marca = str(tema.get("marca") or "")
    try:
        n_notas = max(1, int(pend.get("n_notas") or 1))
    except (TypeError, ValueError):
        n_notas = 1
    titulares = _titulares(tema, pend)
    lista = "\n".join(f"  - {t}" for t in titulares) or "  - (sin titulares)"
    evento = str(tema.get("tema_macro") or tema.get("evento_id") or "").strip() or "(sin evento)"
    sust = {
        "{{MARCA}}": marcas.etiqueta_de(marca) or marca or "la marca",
        "{{EVENTO}}": evento,
        "{{N_NOTAS}}": str(n_notas),
        "{{N_FUENTES}}": str(max(n_notas, len(titulares))),
        "{{TITULARES}}": lista,
    }
    for marcador, valor in sust.items():
        cuerpo = cuerpo.replace(marcador, valor)
    return cuerpo


def lanzar_para_tema(tema: dict[str, Any]) -> dict[str, Any] | None:
    """ENCOLA el Decisor de formato de UN tema. None si no aplica (sin marca/flag OFF/sin pendiente).

    Lee las señales del tema + `copy_pendiente`, compone el prompt (autocontenido) y lanza un
    `claude -p` READ-ONLY con Haiku cuyo post-procesado guarda el camino en `copy_pendiente`.
    Idempotente por `decisor:{publicacion_id}`: mientras el job está en curso no se relanza.
    """
    publicacion_id = str(tema.get("id") or "").strip()
    marca = str(tema.get("marca") or "").strip()
    if not publicacion_id or not marca or not marcas.es_marca(marca):
        return None
    if not config.etapa_activa(config.ENV_PIPELINE_DECISOR, marca):
        return None
    pend = _copy_pendiente(tema)
    procesar_spec = jobspec.construir_decisor(publicacion_id=publicacion_id)
    procesar = jobspec.reconstruir_procesar({"procesar": procesar_spec})
    prompt = _componer_prompt(tema, pend)
    return generar.lanzar(
        tipo="decisor",
        titulo=f"Decisor · {tema.get('titulo', '') or 'tema'}",
        marca=marca,
        prompt=prompt,
        procesar=procesar,
        procesar_spec=procesar_spec,
        endurecer=_endurecer(),
        clave_idem=f"decisor:{publicacion_id}",
        publicacion_id=publicacion_id,
    )


# --------------------------------------------------------------------------- #
# Post-procesado (corre en el WORKER al terminar el job)                        #
# --------------------------------------------------------------------------- #


def parsear_camino(salida: str) -> str:
    """Extrae `camino` (`foto`|`carrusel`) del JSON de la salida. `foto` si ilegible/desconocido.

    Tolera vallas ```json y texto alrededor: prueba el bloque cercado y, si no cuela, el tramo de
    la primera `{` a la última `}`. Ante cualquier duda devuelve `foto` (formato conservador)."""
    if not salida:
        return CAMINO_FOTO
    texto = salida.strip()
    candidatos: list[str] = []
    valla = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", texto, re.DOTALL)
    if valla:
        candidatos.append(valla.group(1))
    ini, fin = texto.find("{"), texto.rfind("}")
    if ini != -1 and fin > ini:
        candidatos.append(texto[ini : fin + 1])
    for crudo in candidatos:
        try:
            datos = json.loads(crudo)
        except (ValueError, TypeError):
            continue
        if isinstance(datos, dict):
            camino = str(datos.get("camino") or "").strip().lower()
            if camino in CAMINOS:
                return camino
    return CAMINO_FOTO


def aplicar_camino(publicacion_id: str, camino: str) -> str:
    """Guarda el `camino` elegido en `copy_pendiente` del tema (merge, sin migración). Devuelve el camino.

    RE-LEE el tema fresco antes de escribir (como `anotar_intento`): si el copy ya se generó y
    limpió `copy_pendiente`, NO lo resucita — la decisión ya no aplica. Best-effort: un fallo de
    persistencia no rompe el post-procesado (el barrido reintentaría el decisor)."""
    camino = camino if camino in CAMINOS else CAMINO_FOTO
    try:
        fresco = repos.obtener_publicacion(publicacion_id)
    except Exception:  # noqa: BLE001 -- sin lectura no escribimos; el barrido reintenta
        return camino
    if fresco is None or not str(fresco.get("copy_pendiente") or "").strip():
        return camino  # el copy ya limpió el pendiente (o el tema desapareció): nada que decidir
    pend = _copy_pendiente(fresco)
    pend["camino"] = camino
    try:
        repos.actualizar_publicacion(
            publicacion_id, {"copy_pendiente": json.dumps(pend, ensure_ascii=False)}
        )
    except Exception:  # noqa: BLE001 -- sin persistir, Redactar decide el formato como sin Decisor
        _log.warning("decisor: no se pudo guardar el camino del tema %s", publicacion_id, exc_info=True)
    return camino


def construir_procesar_decisor(*, publicacion_id: str):  # noqa: ANN201
    """Devuelve el callback `procesar(salida, metricas) -> dict` del job (corre en el worker)."""

    def procesar(salida: str, _metricas: object) -> dict[str, object]:
        camino = aplicar_camino(publicacion_id, parsear_camino(salida))
        return {"camino": camino}

    return procesar
