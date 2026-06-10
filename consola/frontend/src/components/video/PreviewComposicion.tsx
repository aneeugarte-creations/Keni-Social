/**
 * Vista previa APROXIMADA de la composición de video (preview-only, NO frame-exacta).
 *
 * Honestidad (igual que en el Estudio de imagen): este preview es una aproximación en el
 * navegador con DOM/CSS — el RENDER FIEL lo produce el servidor con FFmpeg. No reproduce el
 * documento de capas pixel-a-pixel ni quema subtítulos; sirve para encuadrar, posicionar y
 * REVISAR la composición en movimiento.
 *
 * Dibuja, a escala del lienzo:
 *   - el clip BASE (<video>) con object-fit cover/contain y foco,
 *   - las cajas de las capas overlay (rectángulos/etiquetas, aproximados),
 *   - la ventana PiP (segundo <video>) en su x/y/w/h,
 *   - la caja de subtítulos con el segmento activo EN EL TIEMPO ACTUAL,
 *   - las zonas seguras (líneas punteadas) del preset.
 *
 * PLAYER (estilo Canva): botón play/pausa superpuesto (visible al hover o en pausa), barra de
 * progreso con scrubbing (arrastrar = seek) y reloj actual/total. El tiempo actual se lee del
 * <video> base (rAF mientras reproduce + `timeupdate` como red de seguridad) y alimenta los
 * SUBTÍTULOS para que se pinten sincronizados. El PiP se reproduce/pausa/busca junto al base
 * (best-effort: la sincronía fiel es del render). Espacio = play/pausa salvo que el foco esté
 * en un control editable; se apaga vía `atajoEspacio` cuando otro editor usa la barra
 * (p. ej. el pan con espacio del Lienzo en la sección Overlay).
 */
import { Pause, Play } from "lucide-react";
import * as React from "react";

import { urlMedia } from "@/lib/api";
import {
  formatearDuracionMs,
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
  /** Alto máximo del preview en px (escala el lienzo a este alto). */
  altoMax?: number;
  /**
   * Habilita el atajo global Espacio = play/pausa (default true). Apágalo cuando otro editor
   * en pantalla ya usa la barra espaciadora (p. ej. el pan del Lienzo en la sección Overlay).
   */
  atajoEspacio?: boolean;
}

export function PreviewComposicion({
  doc,
  baseUrl,
  pipUrl,
  segmentos,
  altoMax = 520,
  atajoEspacio = true,
}: PreviewComposicionProps) {
  const { w, h } = doc.formato;

  // Mide el ancho disponible del contenedor para CLAMPAR la escala: sin esto, un formato
  // horizontal (16:9 a 520px de alto ≈ 924px de ancho) desbordaría la columna de preview.
  const contRef = React.useRef<HTMLDivElement>(null);
  const [anchoDisp, setAnchoDisp] = React.useState(0);
  React.useEffect(() => {
    const el = contRef.current;
    if (!el) return;
    const medir = () => setAnchoDisp(el.clientWidth);
    medir();
    // jsdom (tests) no trae ResizeObserver: se queda con la medición inicial sin romper.
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(medir);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // ------------------------------------------------------------------ //
  // PLAYER: estado de reproducción, reloj y scrubbing                    //
  // ------------------------------------------------------------------ //
  const videoBaseRef = React.useRef<HTMLVideoElement>(null);
  const videoPipRef = React.useRef<HTMLVideoElement>(null);
  const barraRef = React.useRef<HTMLDivElement>(null);

  const [reproduciendo, setReproduciendo] = React.useState(false);
  const [tiempo, setTiempo] = React.useState(0); // segundos
  const [duracion, setDuracion] = React.useState(0); // segundos (de los metadatos del <video>)

  // Duración total a mostrar: la real del <video> si ya cargó metadatos; si no, la del documento.
  const durTotal = duracion > 0 ? duracion : (doc.duracion_ms || 0) / 1000;

  // Cambiar de clip resetea el player (nuevo video = reloj a cero, en pausa).
  React.useEffect(() => {
    setReproduciendo(false);
    setTiempo(0);
    setDuracion(0);
  }, [baseUrl]);

  // Mientras reproduce, un rAF lee `currentTime` del <video> para un reloj fluido (los eventos
  // `timeupdate` solo llegan ~4 veces/s). `timeupdate` queda como red de seguridad (y para
  // entornos sin rAF útil, como jsdom en tests).
  React.useEffect(() => {
    if (!reproduciendo) return;
    // jsdom (tests) puede no traer rAF: el `timeupdate` del <video> sigue moviendo el reloj.
    if (typeof requestAnimationFrame === "undefined") return;
    let raf = 0;
    const tick = () => {
      const v = videoBaseRef.current;
      if (v) setTiempo(v.currentTime || 0);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [reproduciendo]);

  /** Play/pausa del base, arrastrando al PiP (best-effort; la sincronía fiel es del render). */
  const alternar = React.useCallback(() => {
    const v = videoBaseRef.current;
    if (!v) return;
    const pip = videoPipRef.current;
    if (reproduciendo) {
      v.pause();
      try {
        pip?.pause();
      } catch {
        /* preview best-effort */
      }
    } else {
      // `play()` puede devolver undefined (jsdom) o una promesa que rechaza (autoplay): ambas
      // se absorben — si no arranca, el estado simplemente no pasa a "reproduciendo".
      void Promise.resolve(v.play()).catch(() => {});
      try {
        void Promise.resolve(pip?.play()).catch(() => {});
      } catch {
        /* preview best-effort */
      }
    }
  }, [reproduciendo]);

  /** Busca a `t` segundos (clamp a [0, durTotal]) en base + PiP y refresca el reloj. */
  const buscarA = React.useCallback(
    (t: number) => {
      const destino = Math.min(Math.max(0, t), durTotal > 0 ? durTotal : t);
      setTiempo(destino);
      const v = videoBaseRef.current;
      if (v) {
        try {
          v.currentTime = destino;
        } catch {
          /* metadatos aún no listos: el reloj ya quedó posicionado */
        }
      }
      const pip = videoPipRef.current;
      if (pip) {
        try {
          pip.currentTime = destino;
        } catch {
          /* preview best-effort */
        }
      }
    },
    [durTotal],
  );

  /** Convierte la posición X de un puntero sobre la barra en un seek. */
  const buscarDesdePuntero = React.useCallback(
    (clientX: number) => {
      const barra = barraRef.current;
      if (!barra || durTotal <= 0) return;
      const rect = barra.getBoundingClientRect();
      if (rect.width <= 0) return;
      const frac = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
      buscarA(frac * durTotal);
    },
    [buscarA, durTotal],
  );

  /**
   * Scrubbing: mousedown sobre la barra = seek; mientras se arrastra, mousemove/mouseup van a
   * `window` (patrón clásico de drag) para no perder el gesto al salir de la barra. Los taps
   * táctiles llegan vía los eventos mouse de compatibilidad del navegador.
   */
  const iniciarScrub = React.useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault(); // evita seleccionar texto al arrastrar
      buscarDesdePuntero(e.clientX);
      const mover = (ev: MouseEvent) => buscarDesdePuntero(ev.clientX);
      const soltar = () => {
        window.removeEventListener("mousemove", mover);
        window.removeEventListener("mouseup", soltar);
      };
      window.addEventListener("mousemove", mover);
      window.addEventListener("mouseup", soltar);
    },
    [buscarDesdePuntero],
  );

  // Atajo global: Espacio = play/pausa cuando el foco NO está en un control editable/activable
  // (input/textarea/select/botón/contenteditable). `e.repeat` evita el metralleo al mantenerla.
  React.useEffect(() => {
    if (!atajoEspacio || !baseUrl) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.code !== "Space" || e.repeat) return;
      const t = e.target as HTMLElement | null;
      if (
        t &&
        (t.tagName === "INPUT" ||
          t.tagName === "TEXTAREA" ||
          t.tagName === "SELECT" ||
          t.tagName === "BUTTON" ||
          t.isContentEditable ||
          t.closest("[contenteditable]"))
      )
        return;
      e.preventDefault(); // evita el scroll de página
      alternar();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [atajoEspacio, baseUrl, alternar]);

  // Escala: cabe en `altoMax` de alto Y en el ancho del contenedor (si ya se midió).
  const escala = Math.min(altoMax / h, anchoDisp > 0 ? anchoDisp / w : Infinity);
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
  const progresoPct = durTotal > 0 ? Math.min(100, (tiempo / durTotal) * 100) : 0;
  // Controles visibles en pausa; durante la reproducción solo al hover/foco (estilo Canva).
  const visControles = reproduciendo
    ? "opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100"
    : "opacity-100 transition-opacity";

  return (
    <div ref={contRef} className="flex w-full flex-col items-center gap-2">
      <div
        className="group relative overflow-hidden rounded-md border border-border bg-black shadow-sm"
        style={{ width: anchoPx, height: altoPx }}
        aria-label="Vista previa aproximada de la composición"
      >
        {/* Clip base */}
        {baseUrl ? (
          <video
            ref={videoBaseRef}
            src={urlMedia(baseUrl)}
            muted
            playsInline
            preload="metadata"
            onPlay={() => setReproduciendo(true)}
            onPause={() => setReproduciendo(false)}
            onEnded={() => setReproduciendo(false)}
            onTimeUpdate={(e) => setTiempo(e.currentTarget.currentTime || 0)}
            onLoadedMetadata={(e) => {
              const d = e.currentTarget.duration;
              if (Number.isFinite(d) && d > 0) setDuracion(d);
            }}
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
                ref={videoPipRef}
                src={urlMedia(pipUrl)}
                muted
                playsInline
                preload="metadata"
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

        {/* Caja de subtítulos (segmento activo en el tiempo actual del player) */}
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

        {/* Controles del player (solo con clip base): botón central + barra de progreso. */}
        {baseUrl && (
          <>
            <button
              type="button"
              onClick={alternar}
              aria-label={reproduciendo ? "Pausar" : "Reproducir"}
              className={`absolute left-1/2 top-1/2 z-10 flex h-12 w-12 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-black/60 text-white shadow hover:bg-black/75 focus-visible:opacity-100 ${visControles}`}
            >
              {reproduciendo ? (
                <Pause className="h-6 w-6" />
              ) : (
                <Play className="h-6 w-6 translate-x-0.5" />
              )}
            </button>

            <div
              className={`absolute inset-x-0 bottom-0 z-10 flex items-center gap-2 bg-gradient-to-t from-black/70 to-transparent px-2 pb-1.5 pt-5 ${visControles}`}
            >
              {/* Barra de progreso con scrubbing: mousedown = seek; arrastrar = seek continuo. */}
              <div
                ref={barraRef}
                role="slider"
                tabIndex={0}
                aria-label="Posición de reproducción"
                aria-valuemin={0}
                aria-valuemax={Math.round(durTotal)}
                aria-valuenow={Math.round(Math.min(tiempo, durTotal))}
                aria-valuetext={`${formatearDuracionMs(tiempo * 1000)} de ${formatearDuracionMs(durTotal * 1000)}`}
                onMouseDown={iniciarScrub}
                onKeyDown={(e) => {
                  if (e.key === "ArrowRight") {
                    e.preventDefault();
                    buscarA(tiempo + 5);
                  } else if (e.key === "ArrowLeft") {
                    e.preventDefault();
                    buscarA(tiempo - 5);
                  }
                }}
                className="relative h-4 min-w-0 flex-1 cursor-pointer touch-none"
              >
                <div className="absolute inset-x-0 top-1/2 h-1 -translate-y-1/2 rounded-full bg-white/30" />
                <div
                  className="absolute left-0 top-1/2 h-1 -translate-y-1/2 rounded-full bg-white"
                  style={{ width: `${progresoPct}%` }}
                />
                <div
                  className="absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white shadow"
                  style={{ left: `${progresoPct}%` }}
                />
              </div>

              {/* Reloj actual / total */}
              <span className="shrink-0 text-[10px] tabular-nums text-white/90">
                {formatearDuracionMs(tiempo * 1000)} / {formatearDuracionMs(durTotal * 1000)}
              </span>
            </div>
          </>
        )}
      </div>
      <p className="text-[11px] text-muted-foreground/70">
        Preview aproximado (DOM). El render fiel lo produce el servidor con FFmpeg.
      </p>
    </div>
  );
}
