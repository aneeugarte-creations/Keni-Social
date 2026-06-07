"""Presets de FORMATO y validador de COMPOSICION del motor de video (Ola VIDEO).

Capa MAS BAJA del monorepo (keni_shared): SIN dependencias de keni-consola ni keni-metricas,
para que el back (API/render), el worker (ejecutor de render/ASR) y el frontend (UI del
Estudio de Video, via `GET /api/limites`/endpoints de video) lean de la MISMA fuente.

QUE VIVE AQUI
=============
  - `PRESETS_FORMATO`  : resoluciones canonicas por aspecto (9:16 / 1:1 / 16:9) con zonas
                         SEGURAS (safe_top / safe_bottom) razonables para sobreimpresos.
  - `preset_para_aspecto` / `preset_para_red` : resolucion de preset por aspecto o por id de
                         red (mapea sobre `limites_plataforma.VIDEO_SPECS`).
  - `validar_composicion(doc)` : validador LIGERO de la estructura minima del JSON de
                         composicion (ver `docs/maquina-contenido/G-video-engine.md`).
                         Normaliza y lanza `ValueError` (mensaje en espanol) si algo basico
                         falta. NO valida las capas del overlay (eso es del Estudio de imagen,
                         `motores/estudio_imagen/documento.py`) ni el contenido de los clips a
                         nivel de ffmpeg: solo la FORMA del sobre.

CONTRATO
========
El esquema completo de la composicion (pistas/clips/overlay/subtitulos) lo documenta
`docs/maquina-contenido/G-video-engine.md`. Este modulo es la fuente UNICA del CONTRATO de
formato; el render (motores/estudio_video) y el ASR (motores/transcripcion) los rellenan los
agentes A/B. Sin estado ni I/O: solo datos y funciones puras.
"""

from __future__ import annotations

from typing import Any

from . import limites_plataforma

# --------------------------------------------------------------------------- #
# Presets de formato (resolucion + zonas seguras por aspecto)                   #
# --------------------------------------------------------------------------- #

# Aspectos soportados (vertical, cuadrado, horizontal) con su resolucion CANONICA de salida y
# las zonas SEGURAS (px desde arriba/abajo) donde NO debe caer texto/logos importantes (la UI
# de cada red tapa esquinas con su chrome). Valores conservadores y redondos.
#   - w / h           : resolucion de render (px). Multiplos de 2 (requisito de H.264/yuv420p).
#   - fps             : cuadros por segundo por defecto del render.
#   - safe_top        : margen superior seguro (px).
#   - safe_bottom     : margen inferior seguro (px) — mayor en 9:16 (caption/botones de Reels/TikTok).
PRESETS_FORMATO: dict[str, dict[str, int]] = {
    # Vertical (Reels / TikTok / Shorts): el formato dominante del piloto AMX.
    "9:16": {"w": 1080, "h": 1920, "fps": 30, "safe_top": 220, "safe_bottom": 320},
    # Cuadrado (feed clasico): zonas seguras simetricas y moderadas.
    "1:1": {"w": 1080, "h": 1080, "fps": 30, "safe_top": 120, "safe_bottom": 120},
    # Horizontal (YouTube / X landscape): poco chrome arriba/abajo.
    "16:9": {"w": 1920, "h": 1080, "fps": 30, "safe_top": 80, "safe_bottom": 120},
}

# Aspecto por defecto cuando una red no declara `aspecto` o no se reconoce (el del piloto).
ASPECTO_DEFECTO = "9:16"


def aspectos() -> tuple[str, ...]:
    """Aspectos soportados, en orden estable (9:16, 1:1, 16:9)."""
    return tuple(PRESETS_FORMATO.keys())


def preset_para_aspecto(aspecto: str) -> dict[str, int]:
    """Preset de formato para un aspecto (`9:16` | `1:1` | `16:9`).

    Si el aspecto no se reconoce, cae al `ASPECTO_DEFECTO` (defensivo: nunca devuelve None,
    para que el render siempre tenga una resolucion). Devuelve una COPIA (no la mutable global).
    """
    base = PRESETS_FORMATO.get(aspecto) or PRESETS_FORMATO[ASPECTO_DEFECTO]
    return dict(base)


def preset_para_red(red_id: str) -> dict[str, int]:
    """Preset de formato sugerido para una red, via `limites_plataforma.VIDEO_SPECS`.

    Mapea el `aspecto` informativo de la red (X=16:9, el resto 9:16) a su preset de resolucion.
    Red desconocida -> `ASPECTO_DEFECTO`. Devuelve una COPIA con `aspecto` adjunto.
    """
    specs = limites_plataforma.video_specs_de(red_id) or {}
    aspecto = str(specs.get("aspecto") or ASPECTO_DEFECTO)
    preset = preset_para_aspecto(aspecto)
    preset["aspecto"] = aspecto  # type: ignore[assignment]  # eco del aspecto resuelto
    return preset


# --------------------------------------------------------------------------- #
# Validador LIGERO de la composicion                                            #
# --------------------------------------------------------------------------- #

# Tipos de pista validos del esquema de composicion (ver G-video-engine.md).
TIPOS_PISTA = frozenset({"video", "overlay", "subtitulos"})


def _entero_no_negativo(valor: Any, campo: str) -> int:
    """Coacciona `valor` a int >= 0; lanza ValueError (mensaje en espanol) si no se puede."""
    try:
        n = int(valor)
    except (TypeError, ValueError) as e:
        raise ValueError(f"'{campo}' debe ser un entero (recibido: {valor!r}).") from e
    if n < 0:
        raise ValueError(f"'{campo}' no puede ser negativo (recibido: {n}).")
    return n


def validar_composicion(doc: dict) -> dict:
    """Valida/normaliza la estructura MINIMA de una composicion de video. Devuelve el doc normalizado.

    Comprueba SOLO la forma del sobre (no el contenido de las capas ni los media reales):
      - `doc` es un dict con `formato` (dict con w/h enteros > 0) y `pistas` (lista).
      - cada pista es un dict con `id` (str no vacio) y `tipo` ∈ TIPOS_PISTA.
      - `version` (def 1), `marca` (str, def ""), `duracion_ms` (int >= 0, def 0) se normalizan.
      - `formato.fps`/`preset` se rellenan desde `PRESETS_FORMATO` si faltan (por w:h o preset).

    Lanza `ValueError` con un mensaje accionable en espanol ante cualquier fallo basico. NO
    muta el dict de entrada: trabaja sobre una copia superficial de las claves de nivel alto.
    """
    if not isinstance(doc, dict):
        raise ValueError("La composicion debe ser un objeto JSON.")

    formato = doc.get("formato")
    if not isinstance(formato, dict):
        raise ValueError("La composicion necesita un 'formato' (objeto con w/h).")
    w = _entero_no_negativo(formato.get("w"), "formato.w")
    h = _entero_no_negativo(formato.get("h"), "formato.h")
    if w <= 0 or h <= 0:
        raise ValueError("'formato.w' y 'formato.h' deben ser mayores que cero.")

    pistas = doc.get("pistas")
    if not isinstance(pistas, list):
        raise ValueError("La composicion necesita una lista 'pistas'.")

    ids_vistos: set[str] = set()
    pistas_norm: list[dict] = []
    for i, pista in enumerate(pistas):
        if not isinstance(pista, dict):
            raise ValueError(f"La pista #{i} debe ser un objeto.")
        pid = str(pista.get("id") or "").strip()
        if not pid:
            raise ValueError(f"La pista #{i} necesita un 'id' no vacio.")
        if pid in ids_vistos:
            raise ValueError(f"El id de pista '{pid}' esta repetido.")
        ids_vistos.add(pid)
        tipo = str(pista.get("tipo") or "").strip()
        if tipo not in TIPOS_PISTA:
            raise ValueError(
                f"La pista '{pid}' tiene un tipo invalido '{tipo}' "
                f"(validos: {', '.join(sorted(TIPOS_PISTA))})."
            )
        pistas_norm.append(pista)

    # Resolucion del preset/fps: si el formato no los trae, derivamos por w:h o caemos al defecto.
    preset_nombre = str(formato.get("preset") or "").strip()
    if preset_nombre not in PRESETS_FORMATO:
        preset_nombre = _aspecto_por_dimension(w, h)
    base = PRESETS_FORMATO[preset_nombre]
    fps = formato.get("fps")
    fps = _entero_no_negativo(fps, "formato.fps") if fps is not None else base["fps"]
    if fps <= 0:
        fps = base["fps"]

    return {
        "version": _entero_no_negativo(doc.get("version", 1), "version") or 1,
        "marca": str(doc.get("marca") or ""),
        "formato": {**formato, "w": w, "h": h, "fps": fps, "preset": preset_nombre},
        "duracion_ms": _entero_no_negativo(doc.get("duracion_ms", 0), "duracion_ms"),
        "pistas": pistas_norm,
    }


def _aspecto_por_dimension(w: int, h: int) -> str:
    """Mapea una resolucion (w, h) al preset mas cercano por relacion de aspecto.

    Compara la relacion w/h con la de cada preset y devuelve el mas proximo (defensivo: ante
    cualquier resolucion, siempre hay un preset). No exige coincidencia exacta de pixeles.
    """
    objetivo = w / h if h else 1.0
    mejor = ASPECTO_DEFECTO
    mejor_dist = float("inf")
    for nombre, p in PRESETS_FORMATO.items():
        ratio = p["w"] / p["h"]
        dist = abs(ratio - objetivo)
        if dist < mejor_dist:
            mejor, mejor_dist = nombre, dist
    return mejor


__all__ = [
    "ASPECTO_DEFECTO",
    "PRESETS_FORMATO",
    "TIPOS_PISTA",
    "aspectos",
    "preset_para_aspecto",
    "preset_para_red",
    "validar_composicion",
]
