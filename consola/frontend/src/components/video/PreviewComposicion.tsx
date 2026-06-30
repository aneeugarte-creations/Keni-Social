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
 *
 * RECORTE (trim): la reproducción RESPETA `recorte_in_ms`/`recorte_out_ms` del clip base igual
 * que lo hará el render (-ss/-to en FFmpeg): play desde fuera del rango arranca en `recorte_in`
 * y al alcanzar `recorte_out` se pausa clavada en el corte (play de nuevo = replay desde
 * `recorte_in`). El SCRUBBING sí recorre el clip completo (estilo Canva: lo descartado se ve
 * atenuado en la barra) y el reloj muestra el tiempo DEL VÍDEO FINAL, no el del clip crudo.
 *
 * PiP EDITABLE (estilo Canva, con `pipEditable` + `onCajaPip`): la ventana PiP se ARRASTRA con
 * el puntero (mismo patrón window-mousemove del scrubbing) con clamp a los bordes del lienzo y
 * SNAP a bordes/centro (umbral ~8 px de pantalla, con guías visuales). La esquina inferior
 * derecha REDIMENSIONA manteniendo la proporción. Durante el gesto la caja transitoria vive en
 * estado local: el documento se actualiza UNA vez al soltar (commit → autoguardado del padre).
 * Con foco, las flechas mueven la ventana ±1 % del lienzo (Shift: ±5 %).
 */
import { Pause, Play } from "lucide-react";
import * as React from "react";

import { urlMedia } from "@/lib/api";
import {
  formatearDuracionMs,
  MIN_PIP_PX,
  pistaBase,
  pistaOverlay,
  pistaPip,
  pistaSubtitulos,
  presetParaAspecto,
  segmentoEn,
  type ComposicionVideo,
  type SegmentoSub,
} from "@/lib/video";

/** Mando externo del player: lo expone `playerRef` para que otros (timeline) busquen sin duplicar el player. */
export interface PreviewPlayerHandle {
  /** Busca a `t` segundos (clamp interno a [0, duración]). */
  buscarA: (t: number) => void;
}

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
  /** Notifica el tiempo actual del player (segundos): alimenta el playhead del timeline. */
  onTiempo?: (seg: number) => void;
  /** Notifica la duración real (segundos) al cargar metadatos (0 al cambiar de clip). */
  onDuracion?: (seg: number) => void;
  /** Expone `buscarA` para seeks externos (p. ej. arrastrar el playhead del timeline). */
  playerRef?: React.Ref<PreviewPlayerHandle>;
  /**
   * Habilita la edición DIRECTA de la ventana PiP sobre el preview (arrastrar/redimensionar/
   * flechas). Actívala solo en la sección PiP para no sorprender desde otras secciones.
   */
  pipEditable?: boolean;
  /** Commit de la caja PiP (px del lienzo) al soltar un gesto o pulsar una flecha. */
  onCajaPip?: (caja: { x?: number; y?: number; w?: number; h?: number }) => void;
  /**
   * Habilita el REENCUADRE inline: arrastrar sobre el vídeo mueve el punto focal del clip base
   * (solo con `ajuste === "cover"`). Actívalo en la sección Base. Muestra un marcador de foco.
   */
  reframeEditable?: boolean;
  /** Commit del foco del clip base (0..1) al soltar el gesto de reencuadre. */
  onFoco?: (foco: [number, number]) => void;
}

/** Umbral de SNAP del arrastre del PiP, en px de PANTALLA (constante a cualquier escala). */
const UMBRAL_SNAP_PX = 8;

export function PreviewComposicion({
  doc,
  baseUrl,
  pipUrl,
  segmentos,
  altoMax = 520,
  atajoEspacio = true,
  onTiempo,
  onDuracion,
  playerRef,
  pipEditable = false,
  onCajaPip,
  reframeEditable = false,
  onFoco,
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

  // ── RECORTE del clip base (en segundos, leído del documento: NO se duplica estado) ──────────
  // El render solo incluirá [recorte_in, recorte_out]; la reproducción lo respeta (ver cabecera).
  const clipBase = pistaBase(doc)?.clips[0];
  const recInSeg = Math.max(0, (clipBase?.recorte_in_ms ?? 0) / 1000);
  const recOutCrudo = (clipBase?.recorte_out_ms ?? 0) / 1000;
  const recOutSeg = recOutCrudo > 0 ? recOutCrudo : durTotal;
  // Hay recorte efectivo si algún borde deja fuera ≥ 50 ms (evita falsos positivos por redondeo
  // entre la duración de los metadatos y el `recorte_out` guardado en ms).
  const hayRecorte = durTotal > 0 && (recInSeg > 0.05 || recOutSeg < durTotal - 0.05);

  // Cambiar de clip resetea el player (nuevo video = reloj a cero, en pausa).
  React.useEffect(() => {
    setReproduciendo(false);
    setTiempo(0);
    setDuracion(0);
  }, [baseUrl]);

  /**
   * Avanza el reloj con TOPE en `recorte_out`: mientras REPRODUCE, al alcanzar el corte pausa
   * base y PiP y clava el frame ahí (igual que terminará el vídeo final; play de nuevo = replay
   * desde `recorte_in` vía `alternar`). En pausa NO interviene: el scrubbing puede inspeccionar
   * libremente la parte descartada del clip.
   */
  const avanzarReloj = React.useCallback(
    (v: HTMLVideoElement) => {
      const t = v.currentTime || 0;
      if (reproduciendo && hayRecorte && t >= recOutSeg) {
        v.pause();
        try {
          videoPipRef.current?.pause();
        } catch {
          /* preview best-effort */
        }
        try {
          v.currentTime = recOutSeg;
        } catch {
          /* metadatos aún no listos */
        }
        setTiempo(recOutSeg);
        return;
      }
      setTiempo(t);
    },
    [reproduciendo, hayRecorte, recOutSeg],
  );

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
      if (v) avanzarReloj(v);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [reproduciendo, avanzarReloj]);

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
      // Respeta el recorte como lo hará el render: play desde FUERA del rango (antes de
      // `recorte_in` o en/tras `recorte_out`) arranca en `recorte_in` (replay incluido).
      if (hayRecorte) {
        const t = v.currentTime || 0;
        if (t < recInSeg || t >= recOutSeg - 0.05) buscarA(recInSeg);
      }
      // `play()` puede devolver undefined (jsdom) o una promesa que rechaza (autoplay): ambas
      // se absorben — si no arranca, el estado simplemente no pasa a "reproduciendo".
      void Promise.resolve(v.play()).catch(() => {});
      try {
        void Promise.resolve(pip?.play()).catch(() => {});
      } catch {
        /* preview best-effort */
      }
    }
  }, [reproduciendo, hayRecorte, recInSeg, recOutSeg, buscarA]);

  // Integración con el timeline: expone `buscarA` (seeks externos) y notifica reloj/duración.
  // Son props opcionales: sin ellas el player se comporta exactamente igual que antes.
  React.useImperativeHandle(playerRef, () => ({ buscarA }), [buscarA]);
  React.useEffect(() => {
    onTiempo?.(tiempo);
  }, [tiempo, onTiempo]);
  React.useEffect(() => {
    onDuracion?.(duracion);
  }, [duracion, onDuracion]);

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

  const pip = pistaPip(doc);
  const overlay = pistaOverlay(doc);
  const subs = pistaSubtitulos(doc);
  const preset = presetParaAspecto(doc.formato.preset);

  const clipPip = pip?.clips[0];

  // ------------------------------------------------------------------ //
  // PiP EDITABLE: arrastre + redimensionado + flechas sobre el preview   //
  // ------------------------------------------------------------------ //
  // Durante un gesto la caja TRANSITORIA (px del lienzo) y las guías de snap viven en estado
  // local: el documento global no se toca hasta soltar (un único commit vía `onCajaPip`, que
  // dispara el autoguardado del padre), igual que el trim del timeline.
  const [gestoPip, setGestoPip] = React.useState<{
    x: number;
    y: number;
    w: number;
    h: number;
    guiaV: number | null; // X del lienzo donde pintar la guía vertical (o null)
    guiaH: number | null; // Y del lienzo donde pintar la guía horizontal (o null)
  } | null>(null);

  const pipInteractivo = pipEditable && !!onCajaPip && !!clipPip;

  /** Arrastre de la ventana: mousedown en la caja; move/up en window (patrón del scrubbing). */
  const iniciarArrastrePip = React.useCallback(
    (e: React.MouseEvent) => {
      if (!clipPip || !onCajaPip || escala <= 0) return;
      e.preventDefault(); // evita seleccionar texto / drag nativo del <video>
      const origenX = e.clientX;
      const origenY = e.clientY;
      const { x: x0, y: y0, w: cw, h: ch } = clipPip;
      const maxX = Math.max(0, w - cw);
      const maxY = Math.max(0, h - ch);
      const umbral = UMBRAL_SNAP_PX / escala; // px de pantalla → px del lienzo
      // Imanes por eje: posición destino de la caja + coordenada del lienzo donde va la guía.
      const imanesX: [number, number][] = [[0, 0], [maxX / 2, w / 2], [maxX, w]];
      const imanesY: [number, number][] = [[0, 0], [maxY / 2, h / 2], [maxY, h]];
      let ultima = { x: x0, y: y0 };
      const mover = (ev: MouseEvent) => {
        let x = Math.min(Math.max(0, x0 + (ev.clientX - origenX) / escala), maxX);
        let y = Math.min(Math.max(0, y0 + (ev.clientY - origenY) / escala), maxY);
        let guiaV: number | null = null;
        let guiaH: number | null = null;
        for (const [destino, guia] of imanesX) {
          if (Math.abs(x - destino) <= umbral) {
            x = destino;
            guiaV = guia;
            break;
          }
        }
        for (const [destino, guia] of imanesY) {
          if (Math.abs(y - destino) <= umbral) {
            y = destino;
            guiaH = guia;
            break;
          }
        }
        ultima = { x, y };
        setGestoPip({ x, y, w: cw, h: ch, guiaV, guiaH });
      };
      const soltar = () => {
        window.removeEventListener("mousemove", mover);
        window.removeEventListener("mouseup", soltar);
        setGestoPip(null);
        // Commit ÚNICO al modelo (sin cambio real, `setCajaPip` devuelve el mismo doc).
        onCajaPip({ x: Math.round(ultima.x), y: Math.round(ultima.y) });
      };
      window.addEventListener("mousemove", mover);
      window.addEventListener("mouseup", soltar);
    },
    [clipPip, onCajaPip, escala, w, h],
  );

  /** Redimensionado desde la esquina inferior derecha, manteniendo la PROPORCIÓN de la caja. */
  const iniciarRedimensionPip = React.useCallback(
    (e: React.MouseEvent) => {
      if (!clipPip || !onCajaPip || escala <= 0) return;
      e.preventDefault();
      e.stopPropagation(); // que no arranque también el arrastre de la caja
      const origenX = e.clientX;
      const origenY = e.clientY;
      const { x: x0, y: y0, w: w0, h: h0 } = clipPip;
      const ratio = w0 > 0 && h0 > 0 ? w0 / h0 : 16 / 9;
      // Mínimo: ningún lado por debajo de MIN_PIP_PX; máximo: que la caja no salga del lienzo.
      const minW = Math.max(MIN_PIP_PX, MIN_PIP_PX * ratio);
      const maxW = Math.max(minW, Math.min(w - x0, (h - y0) * ratio));
      let ultima = { w: w0, h: h0 };
      const mover = (ev: MouseEvent) => {
        const dx = (ev.clientX - origenX) / escala;
        const dy = (ev.clientY - origenY) / escala;
        // Manda el delta dominante de la diagonal (estirar hacia abajo también agranda).
        const nuevoW = Math.min(Math.max(w0 + Math.max(dx, dy * ratio), minW), maxW);
        ultima = { w: nuevoW, h: nuevoW / ratio };
        setGestoPip({ x: x0, y: y0, w: ultima.w, h: ultima.h, guiaV: null, guiaH: null });
      };
      const soltar = () => {
        window.removeEventListener("mousemove", mover);
        window.removeEventListener("mouseup", soltar);
        setGestoPip(null);
        onCajaPip({ w: Math.round(ultima.w), h: Math.round(ultima.h) });
      };
      window.addEventListener("mousemove", mover);
      window.addEventListener("mouseup", soltar);
    },
    [clipPip, onCajaPip, escala, w, h],
  );

  /** Flechas con la caja enfocada: mueve ±1 % del lienzo (Shift: ±5 %). Clampa el modelo. */
  const moverPipTeclado = React.useCallback(
    (e: React.KeyboardEvent) => {
      if (!clipPip || !onCajaPip) return;
      const paso = e.shiftKey ? 0.05 : 0.01;
      const dx = Math.max(1, Math.round(w * paso));
      const dy = Math.max(1, Math.round(h * paso));
      const cambio =
        e.key === "ArrowLeft"
          ? { x: clipPip.x - dx }
          : e.key === "ArrowRight"
            ? { x: clipPip.x + dx }
            : e.key === "ArrowUp"
              ? { y: clipPip.y - dy }
              : e.key === "ArrowDown"
                ? { y: clipPip.y + dy }
                : null;
      if (!cambio) return;
      e.preventDefault(); // sin scroll de página; el clamp lo aplica `setCajaPip` en el modelo
      onCajaPip(cambio);
    },
    [clipPip, onCajaPip, w, h],
  );

  // Caja a PINTAR: la transitoria del gesto si lo hay; si no, la del documento.
  const cajaPip = gestoPip ?? clipPip;

  // ------------------------------------------------------------------ //
  // REENCUADRE inline: arrastrar sobre el vídeo mueve el foco del base   //
  // ------------------------------------------------------------------ //
  const [focoGesto, setFocoGesto] = React.useState<[number, number] | null>(null);
  const reframeInteractivo =
    reframeEditable && !!onFoco && !!clipBase && clipBase.ajuste === "cover";
  const focoActual: [number, number] = focoGesto ?? (clipBase ? clipBase.foco : [0.5, 0.5]);

  const iniciarReframe = React.useCallback(
    (e: React.MouseEvent) => {
      if (!onFoco) return;
      e.preventDefault();
      const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
      const calc = (cx: number, cy: number): [number, number] => {
        const fx = rect.width > 0 ? Math.min(1, Math.max(0, (cx - rect.left) / rect.width)) : 0.5;
        const fy = rect.height > 0 ? Math.min(1, Math.max(0, (cy - rect.top) / rect.height)) : 0.5;
        return [Number(fx.toFixed(4)), Number(fy.toFixed(4))];
      };
      let ultimo = calc(e.clientX, e.clientY);
      setFocoGesto(ultimo);
      const mover = (ev: MouseEvent) => {
        ultimo = calc(ev.clientX, ev.clientY);
        setFocoGesto(ultimo);
      };
      const soltar = () => {
        window.removeEventListener("mousemove", mover);
        window.removeEventListener("mouseup", soltar);
        setFocoGesto(null);
        onFoco(ultimo);
      };
      window.addEventListener("mousemove", mover);
      window.addEventListener("mouseup", soltar);
    },
    [onFoco],
  );

  const segActivo = segmentos && segmentos.length > 0 ? segmentoEn(segmentos, tiempo) : null;
  const progresoPct = durTotal > 0 ? Math.min(100, (tiempo / durTotal) * 100) : 0;
  // Reloj del VÍDEO FINAL: con recorte, el contador corre desde `recorte_in` y el total es la
  // duración recortada (lo que de verdad quedará tras el render). Sin recorte, el clip entero.
  const durFinalSeg = hayRecorte ? Math.max(0, recOutSeg - recInSeg) : durTotal;
  const tiempoFinalSeg = hayRecorte
    ? Math.min(Math.max(0, tiempo - recInSeg), durFinalSeg)
    : tiempo;
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
            onTimeUpdate={(e) => avanzarReloj(e.currentTarget)}
            onLoadedMetadata={(e) => {
              const d = e.currentTarget.duration;
              if (Number.isFinite(d) && d > 0) setDuracion(d);
            }}
            className="absolute inset-0 h-full w-full"
            style={{
              objectFit: clipBase?.ajuste === "contain" ? "contain" : "cover",
              objectPosition: `${focoActual[0] * 100}% ${focoActual[1] * 100}%`,
            }}
          />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center text-xs text-white/50">
            Sube un video base para previsualizar
          </div>
        )}

        {/* Reencuadre inline: capa de arrastre que mueve el foco del clip base + marcador. */}
        {reframeInteractivo && (
          <div
            data-testid="reframe-capa"
            role="application"
            aria-label="Arrastra para mover el foco del reencuadre"
            onMouseDown={iniciarReframe}
            className="absolute inset-0 z-[1] cursor-move"
          >
            <div
              className="pointer-events-none absolute h-7 w-7 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white/90 bg-white/10 shadow ring-1 ring-black/30"
              style={{ left: focoActual[0] * anchoPx, top: focoActual[1] * altoPx }}
            >
              <span className="absolute left-1/2 top-1/2 h-1.5 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white" />
            </div>
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

        {/* Ventana PiP. Con `pipEditable` es un objeto manipulable estilo Canva: arrastrar
            mueve, la esquina inferior derecha redimensiona y las flechas (con foco) desplazan.
            z-20 sobre los controles del player: en la sección PiP posicionar es la tarea. */}
        {clipPip && cajaPip && (
          <div
            data-testid="caja-pip"
            role={pipInteractivo ? "group" : undefined}
            aria-label={pipInteractivo ? "Ventana PiP" : undefined}
            aria-roledescription={
              pipInteractivo ? "ventana arrastrable; flechas para mover" : undefined
            }
            tabIndex={pipInteractivo ? 0 : undefined}
            onMouseDown={pipInteractivo ? iniciarArrastrePip : undefined}
            onKeyDown={pipInteractivo ? moverPipTeclado : undefined}
            className={`absolute overflow-hidden rounded border-2 border-white/80 shadow ${
              pipInteractivo
                ? "z-20 cursor-move hover:border-primary focus-visible:border-primary focus-visible:outline-none"
                : ""
            }`}
            style={{
              left: cajaPip.x * escala,
              top: cajaPip.y * escala,
              width: cajaPip.w * escala,
              height: cajaPip.h * escala,
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
            {pipInteractivo && (
              <div
                data-testid="pip-redimensionar"
                title="Redimensionar"
                onMouseDown={iniciarRedimensionPip}
                className="absolute bottom-0 right-0 h-3.5 w-3.5 cursor-nwse-resize rounded-tl-md border-l-2 border-t-2 border-white/80 bg-primary/80"
              />
            )}
          </div>
        )}

        {/* Guías de SNAP del arrastre del PiP (finas, solo durante el gesto imantado). */}
        {gestoPip?.guiaV != null && (
          <div
            data-testid="guia-snap-v"
            className="pointer-events-none absolute inset-y-0 z-30 w-px bg-fuchsia-400"
            style={{ left: gestoPip.guiaV * escala }}
          />
        )}
        {gestoPip?.guiaH != null && (
          <div
            data-testid="guia-snap-h"
            className="pointer-events-none absolute inset-x-0 z-30 h-px bg-fuchsia-400"
            style={{ top: gestoPip.guiaH * escala }}
          />
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
                aria-valuetext={`${formatearDuracionMs(tiempo * 1000)} de ${formatearDuracionMs(durTotal * 1000)}${
                  hayRecorte
                    ? ` (vídeo final: ${formatearDuracionMs(tiempoFinalSeg * 1000)} de ${formatearDuracionMs(durFinalSeg * 1000)})`
                    : ""
                }`}
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
                {/* Zonas DESCARTADAS por el recorte, atenuadas (estilo Canva): se puede scrubbear
                    sobre ellas para inspeccionar, pero NO estarán en el vídeo final. */}
                {hayRecorte && recInSeg > 0 && (
                  <div
                    data-testid="barra-descarte-in"
                    className="absolute left-0 top-1/2 h-1 -translate-y-1/2 rounded-l-full bg-black/60"
                    style={{ width: `${Math.min(100, (recInSeg / durTotal) * 100)}%` }}
                  />
                )}
                {hayRecorte && recOutSeg < durTotal && (
                  <div
                    data-testid="barra-descarte-out"
                    className="absolute right-0 top-1/2 h-1 -translate-y-1/2 rounded-r-full bg-black/60"
                    style={{ width: `${Math.min(100, ((durTotal - recOutSeg) / durTotal) * 100)}%` }}
                  />
                )}
                <div
                  className="absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white shadow"
                  style={{ left: `${progresoPct}%` }}
                />
              </div>

              {/* Reloj actual / total del VÍDEO FINAL (con recorte, lo que quedará tras el render). */}
              <span
                className="shrink-0 text-[10px] tabular-nums text-white/90"
                title={
                  hayRecorte
                    ? `Tiempo del vídeo final (corte ${formatearDuracionMs(recInSeg * 1000)}–${formatearDuracionMs(recOutSeg * 1000)} del clip)`
                    : undefined
                }
              >
                {formatearDuracionMs(tiempoFinalSeg * 1000)} / {formatearDuracionMs(durFinalSeg * 1000)}
              </span>
            </div>
          </>
        )}
      </div>
      <p className="text-[11px] text-muted-foreground/70">
        Preview aproximado
      </p>
    </div>
  );
}
