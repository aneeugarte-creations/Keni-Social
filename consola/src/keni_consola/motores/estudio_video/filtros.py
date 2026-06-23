"""Construccion del FILTERGRAPH de FFmpeg para el motor de render de video (Ola VIDEO).

Funciones PURAS y testeables (sin I/O, sin subprocess): toman el `documento` ya validado de
una composicion + los recursos materializados (rutas de clips, PNG de overlay, ASS de
subtitulos) y devuelven el filtergraph y la lista de argumentos de ffmpeg. El ejecutor
(`__init__.ejecutar_render`) las usa tras bajar los media; los tests las verifican sin tocar
ffmpeg.

CONVENCIONES DEL ESQUEMA (ver `docs/maquina-contenido/08-video-engine.md`)
=========================================================================
  - `formato`: {w, h, fps, preset}. Lienzo de salida.
  - pista `video` con `id == "base"` (o la primera pista de video): clip de fondo. Se reencuadra
    al formato con scale/crop/pad segun `ajuste` ("cover"/"contain") y `foco` [fx, fy].
  - pista `video` con `id == "pip"` (o cualquier otra pista de video): se compone como PiP con
    `overlay` en la posicion/tamano x/y/w/h del clip.
  - pista `overlay`: ya HORNEADA a un PNG transparente del tamano del formato (lo hace el
    ejecutor con `estudio_imagen.renderizar_documento_bytes`); aqui solo se compone con `overlay`.
  - pista `subtitulos`: ASS ya materializado a disco; se quema con el filtro `subtitles=`.

El filtergraph se construye encadenando etiquetas `[vN]` deterministas para que el resultado sea
estable y comparable en los tests.
"""

from __future__ import annotations

from typing import Any

# Etiqueta de la cadena de video tras cada paso (estable -> testeable).
_LBL_BASE = "vbase"
_LBL_PIP = "vpip"
_LBL_OVL = "vovl"
_LBL_SUB = "vsub"


def _foco_seguro(foco: Any) -> tuple[float, float]:
    """Normaliza `foco` a (fx, fy) en [0, 1]; (0.5, 0.5) por defecto."""
    if isinstance(foco, (list, tuple)) and len(foco) == 2:
        try:
            fx = min(1.0, max(0.0, float(foco[0])))
            fy = min(1.0, max(0.0, float(foco[1])))
            return fx, fy
        except (TypeError, ValueError):
            return 0.5, 0.5
    return 0.5, 0.5


def _clip_base(pistas: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Primer clip de la pista de video BASE (id 'base' si existe; si no, la primera pista video)."""
    videos = [p for p in pistas if p.get("tipo") == "video"]
    if not videos:
        return None
    base = next((p for p in videos if p.get("id") == "base"), videos[0])
    clips = base.get("clips") or []
    return clips[0] if clips else None


def _pista_pip(pistas: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Primer clip de una pista de video PiP (id 'pip', o la 2a pista de video si la hay)."""
    videos = [p for p in pistas if p.get("tipo") == "video"]
    pip = next((p for p in videos if p.get("id") == "pip"), None)
    if pip is None and len(videos) >= 2:
        # Si no se nombra 'pip' explicitamente, la 2a pista de video actua como PiP.
        pip = videos[1]
    if pip is None:
        return None
    clips = pip.get("clips") or []
    return clips[0] if clips else None


def pista_overlay(pistas: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Primera pista de tipo `overlay` (capas estilo Documento del Estudio de imagen)."""
    return next((p for p in pistas if p.get("tipo") == "overlay"), None)


def pista_subtitulos(pistas: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Primera pista de tipo `subtitulos`."""
    return next((p for p in pistas if p.get("tipo") == "subtitulos"), None)


def recorte_de(clip: dict[str, Any]) -> tuple[float | None, float | None]:
    """Recorte temporal (segundos) de un clip: (inicio, fin) o None si no se define.

    Acepta `recorte_in_ms`/`recorte_out_ms` (preferente) y, como respaldo, `inicio_ms`/`fin_ms`.
    Devuelve segundos (ffmpeg `-ss`/`-to` trabajan en segundos).
    """
    in_ms = clip.get("recorte_in_ms")
    out_ms = clip.get("recorte_out_ms")
    if in_ms is None and out_ms is None:
        in_ms = clip.get("inicio_ms")
        out_ms = clip.get("fin_ms")
    ini = (float(in_ms) / 1000.0) if in_ms is not None else None
    fin = (float(out_ms) / 1000.0) if out_ms is not None else None
    return ini, fin


def filtro_reencuadre(w: int, h: int, ajuste: str, foco: Any, *, entrada: str, salida: str) -> str:
    """Cadena de reencuadre de una entrada `[entrada]` al lienzo w×h -> `[salida]`.

    - `ajuste == "cover"` (def): escala llenando el lienzo (manteniendo aspecto, recortando el
      sobrante) y recorta centrado en `foco` [fx, fy].
    - `ajuste == "contain"`: escala cabiendo dentro del lienzo (sin recorte) y rellena con `pad`
      (barras) centrando el contenido.
    """
    fx, fy = _foco_seguro(foco)
    if ajuste == "contain":
        # Cabe dentro: escala respetando aspecto, luego pad al lienzo completo (barras).
        escala = f"scale={w}:{h}:force_original_aspect_ratio=decrease"
        pad = f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2"
        return f"[{entrada}]{escala},{pad}[{salida}]"
    # cover: llena el lienzo, recorta el sobrante centrado en el foco.
    escala = f"scale={w}:{h}:force_original_aspect_ratio=increase"
    # Posicion del recorte segun el foco: clamp a [0, in-out] lo hace ffmpeg con la expresion.
    cx = f"(iw-{w})*{fx:.4f}"
    cy = f"(ih-{h})*{fy:.4f}"
    crop = f"crop={w}:{h}:{cx}:{cy}"
    return f"[{entrada}]{escala},{crop}[{salida}]"


def filtro_pip(clip: dict[str, Any], *, base: str, pip_in: str, salida: str) -> str:
    """Compone un clip PiP `[pip_in]` sobre `[base]` en su x/y/w/h -> `[salida]`.

    Escala el PiP a su w/h (si se dan) y lo superpone con `overlay` en x/y. Sin w/h, usa el PiP
    a su tamano nativo; sin x/y, lo ancla arriba-izquierda (0,0).
    """
    x = int(clip.get("x", 0))
    y = int(clip.get("y", 0))
    w = clip.get("w")
    h = clip.get("h")
    pasos = []
    fuente = pip_in
    if w and h:
        pasos.append(f"[{pip_in}]scale={int(w)}:{int(h)}[pipsc]")
        fuente = "pipsc"
    pasos.append(f"[{base}][{fuente}]overlay={x}:{y}[{salida}]")
    return ";".join(pasos)


def filtro_overlay_png(*, base: str, ovl_in: str, w: int, h: int, salida: str) -> str:
    """Compone el PNG de overlay `[ovl_in]` (horneado por el Estudio) sobre `[base]` -> `[salida]`.

    El PNG ya viene al tamano del formato; se escala defensivamente a w×h y se superpone en 0,0.
    """
    return f"[{ovl_in}]scale={w}:{h}[ovlsc];[{base}][ovlsc]overlay=0:0[{salida}]"


def _escapar_ruta_ass(ruta: str) -> str:
    """Escapa una ruta para incrustarla en el filtro `subtitles=`/`ass=` de ffmpeg.

    ffmpeg parsea el valor del filtro: hay que escapar `\\`, `:` y `'`. Se envuelve en comillas
    simples y se escapan las internas. (Patron estandar para rutas en filtros de ffmpeg.)
    """
    r = ruta.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    return f"'{r}'"


def filtro_subtitulos(ruta_ass: str, *, entrada: str, salida: str) -> str:
    """Quema un ASS en `[entrada]` con el filtro `ass=` -> `[salida]`.

    Usa `ass=` (no `subtitles=`) porque el ASS ya trae su propio estilo (lo produce el agente de
    ASR aplicando el `estilo` de la pista); `ass=` respeta ese estilo tal cual.
    """
    return f"[{entrada}]ass={_escapar_ruta_ass(ruta_ass)}[{salida}]"


def construir_filtergraph(
    documento: dict[str, Any],
    *,
    overlay_png: str | None = None,
    ass_path: str | None = None,
    tiene_pip: bool = False,
) -> tuple[str, str]:
    """Construye el filtergraph completo a partir del `documento` validado + recursos disponibles.

    Devuelve `(filtergraph, etiqueta_final)`: el string `-filter_complex` y la etiqueta de la
    cadena de video a mapear como salida. El ORDEN de entradas de ffmpeg que asume es:
      [0:v] = clip base ; [1:v] = clip pip (si `tiene_pip`) ; siguiente = overlay PNG (si lo hay).
    El ejecutor debe alinear los `-i` con este orden.

    Pasos (en orden de prioridad del contrato): reencuadre -> PiP -> overlay -> subtitulos.
    """
    formato = documento.get("formato") or {}
    w = int(formato.get("w") or 0)
    h = int(formato.get("h") or 0)
    pistas = documento.get("pistas") or []

    base_clip = _clip_base(pistas) or {}
    ajuste = str(base_clip.get("ajuste") or "cover")
    foco = base_clip.get("foco")

    pasos: list[str] = []
    # 1) Reencuadre del clip base ([0:v] -> [vbase]).
    pasos.append(filtro_reencuadre(w, h, ajuste, foco, entrada="0:v", salida=_LBL_BASE))
    actual = _LBL_BASE

    # 2) PiP (segundo video, [1:v]).
    if tiene_pip:
        pip_clip = _pista_pip(pistas) or {}
        pasos.append(filtro_pip(pip_clip, base=actual, pip_in="1:v", salida=_LBL_PIP))
        actual = _LBL_PIP

    # 3) Overlay PNG (horneado del Estudio de imagen). Es la siguiente entrada de ffmpeg.
    if overlay_png:
        idx_ovl = 2 if tiene_pip else 1
        pasos.append(filtro_overlay_png(base=actual, ovl_in=f"{idx_ovl}:v", w=w, h=h, salida=_LBL_OVL))
        actual = _LBL_OVL

    # 4) Subtitulos quemados (ASS a disco). Filtro de fichero, no consume una entrada `-i`.
    if ass_path:
        pasos.append(filtro_subtitulos(ass_path, entrada=actual, salida=_LBL_SUB))
        actual = _LBL_SUB

    return ";".join(pasos), actual


def construir_comando(
    ffmpeg_bin: str,
    documento: dict[str, Any],
    *,
    base_path: str,
    pip_path: str | None = None,
    overlay_png: str | None = None,
    ass_path: str | None = None,
    salida_path: str,
    progress_pipe: bool = True,
) -> list[str]:
    """Arma la lista de argv de ffmpeg (SIN shell) para renderizar la composicion.

    - Aplica el recorte temporal del clip base (`-ss`/`-to`) ANTES de su `-i` (recorte rapido).
    - Encadena el filtergraph de `construir_filtergraph` con `-filter_complex`.
    - Mapea la etiqueta de video final + el audio del clip base (si existe) y codifica H.264/AAC
      en yuv420p (compatible con redes), a los fps del formato.
    - Con `progress_pipe`, emite `-progress pipe:1` para parsear el avance del render.
    """
    pistas = documento.get("pistas") or []
    formato = documento.get("formato") or {}
    fps = int(formato.get("fps") or 30)
    base_clip = _clip_base(pistas) or {}
    pip_clip = _pista_pip(pistas) if pip_path else None

    tiene_pip = bool(pip_path)
    filtergraph, etiqueta = construir_filtergraph(
        documento, overlay_png=overlay_png, ass_path=ass_path, tiene_pip=tiene_pip
    )

    argv: list[str] = [ffmpeg_bin, "-y", "-hide_banner", "-nostdin"]

    # Entrada 0: clip base (con recorte temporal antes del -i).
    ini, fin = recorte_de(base_clip)
    if ini is not None:
        argv += ["-ss", f"{ini:.3f}"]
    if fin is not None:
        argv += ["-to", f"{fin:.3f}"]
    argv += ["-i", base_path]

    # Entrada 1: clip PiP (con su propio recorte).
    if pip_path:
        pini, pfin = recorte_de(pip_clip or {})
        if pini is not None:
            argv += ["-ss", f"{pini:.3f}"]
        if pfin is not None:
            argv += ["-to", f"{pfin:.3f}"]
        argv += ["-i", pip_path]

    # Entrada siguiente: PNG de overlay (imagen, loop a 1 frame; overlay la mantiene).
    if overlay_png:
        argv += ["-i", overlay_png]

    if filtergraph:
        argv += ["-filter_complex", filtergraph, "-map", f"[{etiqueta}]"]
    else:  # pragma: no cover - defensivo: sin filtros mapeamos el video crudo.
        argv += ["-map", "0:v"]

    # Audio del clip base, si lo trae (opcional: `?` no falla si no hay pista de audio).
    argv += ["-map", "0:a?"]

    argv += [
        "-r", str(fps),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
    ]
    if progress_pipe:
        argv += ["-progress", "pipe:1", "-nostats"]
    argv += [salida_path]
    return argv


__all__ = [
    "construir_comando",
    "construir_filtergraph",
    "filtro_overlay_png",
    "filtro_pip",
    "filtro_reencuadre",
    "filtro_subtitulos",
    "pista_overlay",
    "pista_subtitulos",
    "recorte_de",
]
