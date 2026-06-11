/**
 * LineaTiempo — banda de timeline ligera (estilo Canva) bajo el preview del Estudio de Video.
 *
 * QUÉ HACE
 *   - Regla de tiempo + PLAYHEAD arrastrable sincronizado bidireccional con el player del
 *     preview: arrastrar (o flechas ±1 s / Shift ±5 s) busca en el <video>; reproducir mueve
 *     el playhead (el padre pasa `tiempoSeg` desde `PreviewComposicion.onTiempo`).
 *   - El clip BASE como tarjeta con ancho ∝ duración recortada y ASAS de trim en los bordes:
 *     arrastrarlas fija `recorte_in_ms`/`recorte_out_ms` con etiqueta mm:ss viva; al soltar se
 *     emite `onTrim` y el preview salta al borde recortado. Mínimo 1 s (MIN_RECORTE_MS).
 *   - PiP y subtítulos como barras finas SOLO LECTURA (informativas, no editables aquí).
 *
 * QUÉ NO HACE (a propósito)
 *   - Nada de split/reorden/multi-clip: el render server-side soporta UN clip por pista
 *     (`motores/estudio_video/filtros.py::_clip_base` toma `clips[0]`). Esta UI no ofrece nada
 *     que el render fuera a ignorar. El trim SÍ lo respeta: `construir_comando` lo aplica con
 *     `-ss`/`-to` antes del input de FFmpeg.
 *
 * El eje temporal es el del CLIP BASE CRUDO (lo mismo que recorre el scrubbing del preview):
 * el recorte se dibuja como tarjeta dentro de ese eje y lo de fuera queda atenuado. La
 * REPRODUCCIÓN respeta el recorte igual que el render (PreviewComposicion arranca en
 * `recorte_in` y pausa en `recorte_out`); el scrubbing sí recorre el clip completo.
 */
import * as React from "react";

import {
  formatearDuracionMs,
  MIN_RECORTE_MS,
  pistaBase,
  pistaPip,
  type ComposicionVideo,
  type SegmentoSub,
} from "@/lib/video";

export interface LineaTiempoProps {
  doc: ComposicionVideo;
  /** Duración real (ms) del clip base según metadatos del <video>; 0 = derivar del documento. */
  duracionClipMs?: number;
  /** Tiempo actual del player (segundos). */
  tiempoSeg: number;
  /** Busca en el player (segundos): arrastrar el playhead / click en la banda. */
  onSeek: (seg: number) => void;
  /**
   * Commit del trim al SOLTAR un asa: `recorte_in_ms`/`recorte_out_ms` del clip base.
   * Se llama `onTrim` (no `onRecorte`) para no confundirlo con el recorte (crop) de imagen.
   */
  onTrim?: (inMs: number, outMs: number) => void;
  /** Segmentos de subtítulos (barra fina informativa, en tiempo del clip base). */
  segmentos?: SegmentoSub[];
  /** Desactiva el trim (p. ej. sin marca activa). El seek sigue activo (no muta nada). */
  disabled?: boolean;
}

/** Paso entre marcas de la regla: el menor que deja ≤ 8 etiquetas legibles. */
function pasoRegla(totalMs: number): number {
  const pasos = [1000, 2000, 5000, 10000, 15000, 30000, 60000, 120000, 300000];
  for (const p of pasos) if (totalMs / p <= 8) return p;
  return 600000;
}

export function LineaTiempo({
  doc,
  duracionClipMs = 0,
  tiempoSeg,
  onSeek,
  onTrim,
  segmentos,
  disabled = false,
}: LineaTiempoProps) {
  const bandaRef = React.useRef<HTMLDivElement>(null);
  // Asa en arrastre (estado VISUAL durante el gesto): el commit va en el mouseup vía onTrim.
  const [arrastre, setArrastre] = React.useState<{ asa: "in" | "out"; ms: number } | null>(null);

  const clip = pistaBase(doc)?.clips[0];

  // Eje temporal = clip base crudo. Si los metadatos aún no cargaron, cae a lo que sabe el doc.
  const totalMs = Math.max(
    duracionClipMs || 0,
    clip?.recorte_out_ms ?? 0,
    clip?.fin_ms ?? 0,
    doc.duracion_ms || 0,
    1,
  );

  /** Posición X del puntero -> ms sobre el eje del timeline (clamp a [0, totalMs]). */
  const msDesdePuntero = React.useCallback(
    (clientX: number): number => {
      const el = bandaRef.current;
      if (!el) return 0;
      const rect = el.getBoundingClientRect();
      if (rect.width <= 0) return 0;
      const frac = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
      return frac * totalMs;
    },
    [totalMs],
  );

  /** Scrub del playhead: mousedown = seek; el arrastre sigue en window (no se pierde el gesto). */
  const iniciarScrub = React.useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      onSeek(msDesdePuntero(e.clientX) / 1000);
      const mover = (ev: MouseEvent) => onSeek(msDesdePuntero(ev.clientX) / 1000);
      const soltar = () => {
        window.removeEventListener("mousemove", mover);
        window.removeEventListener("mouseup", soltar);
      };
      window.addEventListener("mousemove", mover);
      window.addEventListener("mouseup", soltar);
    },
    [msDesdePuntero, onSeek],
  );

  /**
   * Arrastre de un asa de trim. Captura los bordes vigentes al empezar, clampa al mínimo de
   * 1 s y SOLO emite `onTrim` al soltar si hubo cambio real (click seco = no-op). Tras el
   * commit, el preview salta al borde recortado (feedback inmediato de dónde quedó el corte).
   */
  const iniciarTrim = React.useCallback(
    (asa: "in" | "out") => (e: React.MouseEvent) => {
      if (disabled || !onTrim || !clip) return;
      e.preventDefault();
      e.stopPropagation(); // que no dispare el scrub de la banda
      const vIn = clip.recorte_in_ms ?? 0;
      const vOut = clip.recorte_out_ms ?? totalMs;
      const minDur = Math.min(MIN_RECORTE_MS, totalMs);
      const clampa = (ms: number) =>
        asa === "in"
          ? Math.min(Math.max(0, ms), vOut - minDur)
          : Math.min(Math.max(vIn + minDur, ms), totalMs);
      let ultimo = asa === "in" ? vIn : vOut; // sin mover, el asa se queda donde estaba
      setArrastre({ asa, ms: ultimo });
      const mover = (ev: MouseEvent) => {
        ultimo = clampa(msDesdePuntero(ev.clientX));
        setArrastre({ asa, ms: ultimo });
      };
      const soltar = () => {
        window.removeEventListener("mousemove", mover);
        window.removeEventListener("mouseup", soltar);
        setArrastre(null);
        const fin = Math.round(ultimo);
        if (fin === (asa === "in" ? vIn : vOut)) return; // click sin arrastre: nada que guardar
        if (asa === "in") onTrim(fin, vOut);
        else onTrim(vIn, fin);
        onSeek(fin / 1000); // el preview salta al borde recortado al soltar
      };
      window.addEventListener("mousemove", mover);
      window.addEventListener("mouseup", soltar);
    },
    [disabled, onTrim, clip, totalMs, msDesdePuntero, onSeek],
  );

  /** Teclado del playhead: flechas ±1 s, Shift ±5 s, Home/End a los extremos. */
  const onTeclaPlayhead = React.useCallback(
    (e: React.KeyboardEvent) => {
      const paso = e.shiftKey ? 5 : 1;
      if (e.key === "ArrowRight") {
        e.preventDefault();
        onSeek(Math.min(totalMs / 1000, tiempoSeg + paso));
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        onSeek(Math.max(0, tiempoSeg - paso));
      } else if (e.key === "Home") {
        e.preventDefault();
        onSeek(0);
      } else if (e.key === "End") {
        e.preventDefault();
        onSeek(totalMs / 1000);
      }
    },
    [onSeek, totalMs, tiempoSeg],
  );

  // Sin clip base no hay nada que cronometrar (la sección Base ya invita a subirlo).
  if (!clip || !clip.media_id) return null;

  // Bordes vigentes: durante un arrastre, el asa activa usa el valor VISUAL del gesto.
  const inMs = arrastre?.asa === "in" ? arrastre.ms : clip.recorte_in_ms ?? 0;
  const outMs = arrastre?.asa === "out" ? arrastre.ms : clip.recorte_out_ms ?? totalMs;
  const pct = (ms: number) => `${(Math.min(Math.max(0, ms), totalMs) / totalMs) * 100}%`;
  const tiempoMs = Math.min(Math.max(0, tiempoSeg * 1000), totalMs);

  // Marcas de la regla (0, paso, 2·paso, …, ≤ total).
  const paso = pasoRegla(totalMs);
  const marcas: number[] = [];
  for (let ms = 0; ms <= totalMs; ms += paso) marcas.push(ms);

  // Barra informativa del PiP: en la salida arranca con el inicio del recorte base (t=0 del
  // render) y dura su recorte; si el PiP es más corto, FFmpeg congela su último frame (la
  // barra solo marca la parte "viva"). Solo lectura: el trim del PiP no se edita aquí.
  const clipPip = pistaPip(doc)?.clips[0];
  let barPip: { ini: number; fin: number } | null = null;
  if (clipPip?.media_id) {
    const durPip =
      Math.max(0, (clipPip.recorte_out_ms ?? 0) - (clipPip.recorte_in_ms ?? 0)) ||
      Math.max(0, (clipPip.fin_ms ?? 0) - (clipPip.inicio_ms ?? 0));
    barPip = { ini: inMs, fin: durPip > 0 ? Math.min(outMs, inMs + durPip) : outMs };
  }

  const segs = segmentos ?? [];

  return (
    <div className="select-none" data-testid="linea-tiempo">
      <div
        ref={bandaRef}
        onMouseDown={iniciarScrub}
        aria-label="Línea de tiempo de la composición"
        className="relative h-24 cursor-pointer touch-none overflow-hidden rounded-md border border-border bg-muted/40"
      >
        {/* Regla con marcas de tiempo */}
        <div className="pointer-events-none absolute inset-x-0 top-0 h-5 border-b border-border/60">
          {marcas.map((ms) => (
            <div
              key={ms}
              className="absolute top-0 h-full border-l border-border/60"
              style={{ left: pct(ms) }}
            >
              <span className="ml-0.5 text-[9px] tabular-nums leading-5 text-muted-foreground">
                {formatearDuracionMs(ms)}
              </span>
            </div>
          ))}
        </div>

        {/* Fila del clip base: lo fuera del recorte queda atenuado; la tarjeta es el recorte. */}
        <div className="absolute inset-x-0 top-5 h-12">
          {inMs > 0 && (
            <div
              className="absolute inset-y-1 left-0 rounded-l bg-background/70"
              style={{ width: pct(inMs) }}
            />
          )}
          {outMs < totalMs && (
            <div
              className="absolute inset-y-1 right-0 rounded-r bg-background/70"
              style={{ width: pct(totalMs - outMs) }}
            />
          )}
          <div
            data-testid="clip-base"
            className="absolute inset-y-1 overflow-hidden rounded border border-primary/60 bg-primary/15"
            style={{ left: pct(inMs), width: pct(Math.max(0, outMs - inMs)) }}
          >
            <span className="pointer-events-none absolute inset-0 flex items-center justify-center truncate px-3 text-[10px] font-medium tabular-nums text-foreground/80">
              Clip base · {formatearDuracionMs(outMs - inMs)}
            </span>
            {onTrim && (
              <>
                <button
                  type="button"
                  aria-label="Recortar inicio del clip"
                  disabled={disabled}
                  onMouseDown={iniciarTrim("in")}
                  className="absolute inset-y-0 left-0 z-10 w-2.5 cursor-ew-resize rounded-l bg-primary/80 hover:bg-primary disabled:cursor-default disabled:opacity-30"
                >
                  <span className="pointer-events-none mx-auto block h-4 w-0.5 rounded bg-primary-foreground/80" />
                </button>
                <button
                  type="button"
                  aria-label="Recortar fin del clip"
                  disabled={disabled}
                  onMouseDown={iniciarTrim("out")}
                  className="absolute inset-y-0 right-0 z-10 w-2.5 cursor-ew-resize rounded-r bg-primary/80 hover:bg-primary disabled:cursor-default disabled:opacity-30"
                >
                  <span className="pointer-events-none mx-auto block h-4 w-0.5 rounded bg-primary-foreground/80" />
                </button>
              </>
            )}
          </div>
        </div>

        {/* Barras finas SOLO LECTURA: PiP y subtítulos anclados a sus tiempos. */}
        <div className="pointer-events-none absolute inset-x-0 bottom-1 flex flex-col gap-1">
          {barPip && (
            <div className="relative h-1.5">
              <div
                title="PiP"
                aria-label="Barra de PiP"
                className="absolute inset-y-0 rounded-full bg-sky-400/70"
                style={{ left: pct(barPip.ini), width: pct(Math.max(0, barPip.fin - barPip.ini)) }}
              />
            </div>
          )}
          {segs.length > 0 && (
            <div className="relative h-1.5" aria-label="Barra de subtítulos">
              {segs.map((s) => (
                <div
                  key={s.id}
                  title={s.texto}
                  className="absolute inset-y-0 rounded-full bg-amber-400/70"
                  style={{
                    left: pct(s.inicio * 1000),
                    width: pct(Math.max(0, (s.fin - s.inicio) * 1000)),
                  }}
                />
              ))}
            </div>
          )}
        </div>

        {/* Etiqueta mm:ss VIVA del asa en arrastre (sobre la regla). */}
        {arrastre && (
          <span
            className="pointer-events-none absolute top-0 z-30 -translate-x-1/2 rounded bg-foreground px-1 py-0.5 text-[10px] font-medium tabular-nums text-background shadow"
            style={{ left: pct(arrastre.ms) }}
          >
            {formatearDuracionMs(arrastre.ms)}
          </span>
        )}

        {/* Playhead: línea + cabeza arrastrable y accesible (role=slider). */}
        <div
          className="pointer-events-none absolute bottom-0 top-0 z-10 w-px bg-red-500"
          style={{ left: pct(tiempoMs) }}
        />
        <div
          role="slider"
          tabIndex={0}
          aria-label="Cursor de reproducción"
          aria-valuemin={0}
          aria-valuemax={Math.round(totalMs / 1000)}
          aria-valuenow={Math.round(Math.min(tiempoSeg, totalMs / 1000))}
          aria-valuetext={`${formatearDuracionMs(tiempoMs)} de ${formatearDuracionMs(totalMs)}`}
          onMouseDown={(e) => {
            e.stopPropagation(); // que la banda no añada un segundo gesto de scrub
            iniciarScrub(e);
          }}
          onKeyDown={onTeclaPlayhead}
          className="absolute top-0 z-20 flex h-5 w-3 -translate-x-1/2 cursor-ew-resize items-start justify-center outline-none focus-visible:ring-1 focus-visible:ring-ring"
          style={{ left: pct(tiempoMs) }}
        >
          <span className="mt-0.5 block h-2.5 w-2.5 rounded-sm bg-red-500 shadow" />
        </div>
      </div>
      <p className="mt-1 text-[11px] text-muted-foreground/70">
        El scrubbing recorre todo el clip; la reproducción respeta el recorte.
      </p>
    </div>
  );
}
