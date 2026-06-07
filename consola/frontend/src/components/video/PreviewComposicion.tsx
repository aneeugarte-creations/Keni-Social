/**
 * Vista previa APROXIMADA de la composición de video (preview-only, NO frame-exacta).
 *
 * Honestidad (igual que en el Estudio de imagen): este preview es una aproximación en el
 * navegador con DOM/CSS — el RENDER FIEL lo produce el servidor con FFmpeg. No reproduce el
 * documento de capas pixel-a-pixel ni quema subtítulos; sirve para encuadrar y posicionar.
 *
 * Dibuja, a escala del lienzo:
 *   - el clip BASE (<video>) con object-fit cover/contain y foco,
 *   - las cajas de las capas overlay (rectángulos/etiquetas, aproximados),
 *   - la ventana PiP (segundo <video>) en su x/y/w/h,
 *   - la caja de subtítulos con el segmento activo,
 *   - las zonas seguras (líneas punteadas) del preset.
 */
import * as React from "react";

import { urlMedia } from "@/lib/api";
import {
  pistaBase,
  pistaOverlay,
  pistaPip,
  pistaSubtitulos,
  presetParaAspecto,
  segmentoEn,
  type ComposicionVideo,
  type SegmentoSub,
} from "@/lib/video";

export interface PreviewComposicionProps {
  doc: ComposicionVideo;
  /** URL servible del clip base (de la subida). Si falta, se muestra un placeholder. */
  baseUrl?: string;
  /** URL servible del clip PiP. */
  pipUrl?: string;
  /** Segmentos de subtítulos a previsualizar (corregidos por el humano). */
  segmentos?: SegmentoSub[];
  /** Tiempo actual del preview en segundos (para resaltar subtítulo y sincronizar). */
  tiempo?: number;
  /** Ref del <video> base, para que el padre lea `currentTime`/controle reproducción. */
  videoRef?: React.RefObject<HTMLVideoElement>;
  /** Alto máximo del preview en px (escala el lienzo a este alto). */
  altoMax?: number;
}

export function PreviewComposicion({
  doc,
  baseUrl,
  pipUrl,
  segmentos,
  tiempo = 0,
  videoRef,
  altoMax = 520,
}: PreviewComposicionProps) {
  const { w, h } = doc.formato;
  const escala = altoMax / h;
  const anchoPx = w * escala;
  const altoPx = h * escala;

  const base = pistaBase(doc);
  const pip = pistaPip(doc);
  const overlay = pistaOverlay(doc);
  const subs = pistaSubtitulos(doc);
  const preset = presetParaAspecto(doc.formato.preset);

  const clipBase = base?.clips[0];
  const clipPip = pip?.clips[0];

  const segActivo = segmentos && segmentos.length > 0 ? segmentoEn(segmentos, tiempo) : null;

  return (
    <div className="flex flex-col items-center gap-2">
      <div
        className="relative overflow-hidden rounded-md border border-border bg-black shadow-sm"
        style={{ width: anchoPx, height: altoPx }}
        aria-label="Vista previa aproximada de la composición"
      >
        {/* Clip base */}
        {baseUrl ? (
          <video
            ref={videoRef}
            src={urlMedia(baseUrl)}
            muted
            playsInline
            className="absolute inset-0 h-full w-full"
            style={{
              objectFit: clipBase?.ajuste === "contain" ? "contain" : "cover",
              objectPosition: clipBase
                ? `${clipBase.foco[0] * 100}% ${clipBase.foco[1] * 100}%`
                : "center",
            }}
          />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center text-xs text-white/50">
            Sube un video base para previsualizar
          </div>
        )}

        {/* Capas overlay (aproximación: cajas con etiqueta) */}
        {overlay?.capas
          .filter((c) => c.visible !== false)
          .map((c) => (
            <div
              key={c.id}
              className="absolute border border-dashed border-amber-300/70"
              style={{
                left: c.x * escala,
                top: c.y * escala,
                width: c.w * escala,
                height: c.h * escala,
                opacity: c.opacidad ?? 1,
                transform: c.rotacion ? `rotate(${c.rotacion}deg)` : undefined,
                background:
                  c.tipo === "texto" ? "transparent" : "color-mix(in srgb, #fbbf24 12%, transparent)",
              }}
              title={c.nombre ?? c.tipo}
            >
              {c.tipo === "texto" && "texto" in c && (
                <span
                  className="block truncate px-0.5 text-amber-100"
                  style={{ fontSize: Math.max(8, ((c as { tamano?: number }).tamano ?? 32) * escala) }}
                >
                  {(c as { texto?: string }).texto || "Texto"}
                </span>
              )}
            </div>
          ))}

        {/* Ventana PiP */}
        {clipPip && (
          <div
            className="absolute overflow-hidden rounded border-2 border-white/80 shadow"
            style={{
              left: clipPip.x * escala,
              top: clipPip.y * escala,
              width: clipPip.w * escala,
              height: clipPip.h * escala,
            }}
          >
            {pipUrl ? (
              <video
                src={urlMedia(pipUrl)}
                muted
                playsInline
                className="h-full w-full"
                style={{ objectFit: clipPip.ajuste === "contain" ? "contain" : "cover" }}
              />
            ) : (
              <div className="flex h-full w-full items-center justify-center bg-black/70 text-[10px] text-white/60">
                PiP
              </div>
            )}
          </div>
        )}

        {/* Caja de subtítulos (segmento activo) */}
        {subs && segActivo && (
          <div
            className="pointer-events-none absolute inset-x-0 flex justify-center px-3"
            style={
              subs.estilo.posicion === "superior"
                ? { top: preset.safe_top * escala }
                : subs.estilo.posicion === "centro"
                  ? { top: "50%", transform: "translateY(-50%)" }
                  : { bottom: preset.safe_bottom * escala }
            }
          >
            <span
              className="rounded px-2 py-0.5 text-center font-semibold leading-tight"
              style={{
                color: subs.estilo.color,
                background: "rgba(0,0,0,0.55)",
                WebkitTextStroke: `1px ${subs.estilo.borde}`,
                fontSize: Math.max(9, subs.estilo.tam * escala),
              }}
            >
              {segActivo.texto}
            </span>
          </div>
        )}

        {/* Zonas seguras (líneas punteadas) */}
        <div
          className="pointer-events-none absolute inset-x-0 top-0 border-b border-dashed border-cyan-400/40"
          style={{ height: preset.safe_top * escala }}
        />
        <div
          className="pointer-events-none absolute inset-x-0 bottom-0 border-t border-dashed border-cyan-400/40"
          style={{ height: preset.safe_bottom * escala }}
        />
      </div>
      <p className="text-[11px] text-muted-foreground/70">
        Preview aproximado (DOM). El render fiel lo produce el servidor con FFmpeg.
      </p>
    </div>
  );
}
