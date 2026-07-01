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

import type { Capa, CapaImagen, CapaLogo, CapaMarco, CapaOverlay, CapaTexto } from "@/editor/documento";
import { ControlesEncuadre } from "@/editor/lienzo/ControlesEncuadre";
import { useEncuadre } from "@/editor/lienzo/useEncuadre";
import { useZoomPan } from "@/editor/lienzo/useZoomPan";
import { urlMedia } from "@/lib/api";
import {
  duracionBaseMs,
  formatearDuracionMs,
  fuenteASalidaMs,
  MIN_PIP_PX,
  pistaBase,
  pistaOverlay,
  pistaPip,
  pistaSubtitulos,
  presetParaAspecto,
  salidaAFuenteMs,
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
  /**
   * Activa la gestión de ENCUADRE/ZOOM del lienzo (igual que el editor de imagen): barra inferior
   * de zoom (acercar/alejar/ajustar/%), pan con espacio/botón central y rueda, rejilla y zonas
   * seguras. Sin esta prop el preview se autoajusta como antes (sin barra).
   */
  conEncuadre?: boolean;
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
  conEncuadre = false,
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

  // El reloj `tiempo` y el playhead trabajan en tiempo de SALIDA (vídeo final concatenado). El
  // <video> reproduce tiempo de FUENTE; se convierte con `salidaAFuenteMs`/`fuenteASalidaMs`.
  const segs = pistaBase(doc)?.clips ?? [];
  const clipBase = segs[0];
  // Duración de SALIDA: suma de segmentos tras recorte; cae a los metadatos si aún no se conoce.
  const durSalida = duracionBaseMs(doc) / 1000 || (duracion > 0 ? duracion : 0);
  // Segmento ACTIVO en reproducción (los segmentos comparten media_id; el <video> es uno solo).
  const segIdxRef = React.useRef(0);

  // Tiempo de FUENTE (s) del frame actual: para situar los SUBTÍTULOS en el clip crudo.
  const tiempoFuenteSeg = salidaAFuenteMs(doc, tiempo * 1000).fuenteMs / 1000;

  // Cambiar de clip resetea el player (nuevo video = reloj a cero, en pausa, segmento 0).
  React.useEffect(() => {
    setReproduciendo(false);
    setTiempo(0);
    setDuracion(0);
    segIdxRef.current = 0;
  }, [baseUrl]);

  /**
   * Avanza el reloj de SALIDA mientras reproduce. Al alcanzar el `recorte_out` del segmento
   * activo: si hay siguiente segmento salta a su `recorte_in` (concatenación, como FFmpeg); si es
   * el último, pausa al final. En pausa solo refleja el tiempo de salida del frame actual.
   */
  const avanzarReloj = React.useCallback(
    (v: HTMLVideoElement) => {
      const lista = pistaBase(doc)?.clips ?? [];
      const idx = Math.min(segIdxRef.current, Math.max(0, lista.length - 1));
      const seg = lista[idx];
      const t = v.currentTime || 0;
      if (reproduciendo && seg) {
        const out = (seg.recorte_out_ms || seg.fin_ms || 0) / 1000;
        if (out > 0 && t >= out - 0.02) {
          if (idx < lista.length - 1) {
            const inn = (lista[idx + 1].recorte_in_ms ?? 0) / 1000;
            segIdxRef.current = idx + 1;
            try {
              v.currentTime = inn;
              if (videoPipRef.current) videoPipRef.current.currentTime = inn;
            } catch {
              /* metadatos aún no listos */
            }
            setTiempo(fuenteASalidaMs(doc, idx + 1, inn * 1000) / 1000);
            return;
          }
          v.pause();
          try {
            v.currentTime = out; // clava el último frame en el corte (no más allá)
            videoPipRef.current?.pause();
          } catch {
            /* preview best-effort */
          }
          setTiempo(durSalida);
          return;
        }
      }
      setTiempo(fuenteASalidaMs(doc, idx, t * 1000) / 1000);
    },
    [reproduciendo, doc, durSalida],
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

  /** Busca a `outSec` segundos de SALIDA: convierte a (segmento, tiempo de fuente) en base + PiP. */
  const buscarA = React.useCallback(
    (outSec: number) => {
      const total = durSalida > 0 ? durSalida : outSec;
      const destino = Math.min(Math.max(0, outSec), total);
      const { idx, fuenteMs } = salidaAFuenteMs(doc, destino * 1000);
      segIdxRef.current = idx;
      setTiempo(destino);
      const v = videoBaseRef.current;
      if (v) {
        try {
          v.currentTime = fuenteMs / 1000;
        } catch {
          /* metadatos aún no listos: el reloj ya quedó posicionado */
        }
      }
      const pip = videoPipRef.current;
      if (pip) {
        // El PiP tiene su propio recorte: su frame es el de la fuente + su recorte_in.
        const pipIn = (pistaPip(doc)?.clips[0]?.recorte_in_ms ?? 0) / 1000;
        try {
          pip.currentTime = fuenteMs / 1000 + pipIn;
        } catch {
          /* preview best-effort */
        }
      }
    },
    [durSalida, doc],
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
      // Al final del vídeo de salida, play = replay desde el inicio; si no, asegura el frame de
      // fuente correcto para el tiempo de salida actual antes de arrancar.
      if (durSalida > 0 && tiempo >= durSalida - 0.05) {
        buscarA(0);
      } else {
        const { idx, fuenteMs } = salidaAFuenteMs(doc, tiempo * 1000);
        segIdxRef.current = idx;
        try {
          v.currentTime = fuenteMs / 1000;
        } catch {
          /* metadatos aún no listos */
        }
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
  }, [reproduciendo, durSalida, tiempo, doc, buscarA]);

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
      if (!barra || durSalida <= 0) return;
      const rect = barra.getBoundingClientRect();
      if (rect.width <= 0) return;
      const frac = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
      buscarA(frac * durSalida);
    },
    [buscarA, durSalida],
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
    // Con `conEncuadre`, la barra espaciadora la usa el PAN del lienzo: no se duplica el play.
    if (!atajoEspacio || conEncuadre || !baseUrl) return;
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
  }, [atajoEspacio, conEncuadre, baseUrl, alternar]);

  // Atajo K = play/pausa (estándar YouTube/Premiere/DaVinci). No choca con el pan (que usa Espacio),
  // así que funciona también con `conEncuadre`. Ignora si el foco está en un control editable.
  React.useEffect(() => {
    if (!baseUrl) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.code !== "KeyK" || e.repeat) return;
      const t = e.target as HTMLElement | null;
      if (
        t &&
        (t.tagName === "INPUT" ||
          t.tagName === "TEXTAREA" ||
          t.tagName === "SELECT" ||
          t.isContentEditable ||
          t.closest("[contenteditable]"))
      )
        return;
      e.preventDefault();
      alternar();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [baseUrl, alternar]);

  // ENCUADRE/ZOOM (igual que el Lienzo de imagen): zoom/pan + toggles de rejilla/zonas. Los hooks
  // se llaman SIEMPRE (reglas de hooks); su salida solo se usa con `conEncuadre`.
  const scrollRef = React.useRef<HTMLDivElement>(null);
  const {
    medirRef,
    escala: escalaZoom,
    acercar,
    alejar,
    ajustarPantalla,
    zoomReal,
    fijarEscala,
    espacio,
    paneando,
    onMouseDownContenedor,
  } = useZoomPan({ w, h, maxAncho: 600, maxAlto: altoMax, scrollRef });
  const enc = useEncuadre();

  // Zoom con ctrl/cmd + rueda (anclado al centro, como botones); la rueda sola hace scroll/pan.
  const onRueda = React.useCallback(
    (e: React.WheelEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      e.preventDefault();
      if (e.deltaY < 0) acercar();
      else alejar();
    },
    [acercar, alejar],
  );

  // Escala efectiva: con `conEncuadre`, la del zoom; si no, autoajuste por alto/ancho del contenedor.
  const escala = conEncuadre
    ? escalaZoom
    : Math.min(altoMax / h, anchoDisp > 0 ? anchoDisp / w : Infinity);
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
  const [hoverReframe, setHoverReframe] = React.useState(false);
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

  // Subtítulos: se buscan en TIEMPO DE FUENTE (los segmentos del ASR están en el clip crudo).
  const segActivo = segmentos && segmentos.length > 0 ? segmentoEn(segmentos, tiempoFuenteSeg) : null;
  const progresoPct = durSalida > 0 ? Math.min(100, (tiempo / durSalida) * 100) : 0;
  // Controles visibles en pausa; durante la reproducción solo al hover/foco (estilo Canva).
  const visControles = reproduciendo
    ? "opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100"
    : "opacity-100 transition-opacity";

  const lienzo = (
      <div
        className="group relative overflow-hidden rounded-md border border-border bg-black shadow-sm"
        style={{ width: anchoPx, height: altoPx }}
        aria-label="Vista previa aproximada de la composición"
      >
        {/* Rejilla del encuadre (cosmética, no se exporta). */}
        {conEncuadre && enc.grid && (
          <div
            className="pointer-events-none absolute inset-0 z-[2]"
            style={{
              backgroundImage:
                "linear-gradient(to right, rgba(255,255,255,0.18) 1px, transparent 1px), linear-gradient(to bottom, rgba(255,255,255,0.18) 1px, transparent 1px)",
              backgroundSize: `${enc.paso * escala}px ${enc.paso * escala}px`,
            }}
          />
        )}
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

        {/* Reencuadre inline: arrastrar mueve el foco del clip base. RETÍCULA (cruz fina + anillo)
            que solo aparece al pasar el ratón o durante el arrastre (no una "bolita" permanente);
            cursor crosshair = "mover el foco en 2D". */}
        {reframeInteractivo && (
          <div
            data-testid="reframe-capa"
            role="application"
            aria-label="Arrastra para mover el foco del reencuadre"
            onMouseDown={iniciarReframe}
            onMouseEnter={() => setHoverReframe(true)}
            onMouseLeave={() => setHoverReframe(false)}
            className="absolute inset-0 z-[1] cursor-crosshair"
          >
            {(hoverReframe || focoGesto !== null) && (
              <div
                className="pointer-events-none absolute -translate-x-1/2 -translate-y-1/2"
                style={{ left: focoActual[0] * anchoPx, top: focoActual[1] * altoPx }}
              >
                <span className="absolute left-1/2 top-1/2 h-px w-9 -translate-x-1/2 -translate-y-1/2 bg-white/85 shadow-[0_0_1px_rgba(0,0,0,0.9)]" />
                <span className="absolute left-1/2 top-1/2 h-9 w-px -translate-x-1/2 -translate-y-1/2 bg-white/85 shadow-[0_0_1px_rgba(0,0,0,0.9)]" />
                <span className="absolute left-1/2 top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/90 ring-1 ring-black/40" />
              </div>
            )}
          </div>
        )}

        {/* Capas overlay: aproximación FIEL en DOM (texto/imagen/logo/marco), no cajas amarillas.
            El render fiel pixel-a-pixel es el del servidor; esto encuadra y revisa en movimiento. */}
        {overlay?.capas
          .filter((c) => c.visible !== false)
          .map((c) => (
            <CapaOverlayDOM key={c.id} capa={c} escala={escala} />
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

        {/* Zonas seguras (líneas punteadas + velo). En el editor de vídeo (`conEncuadre`) SOLO se
            muestran con el toggle `zonas` (como el Estudio de imagen): así el preview no sale
            "partido" con líneas azules por defecto. Fuera del editor se muestran siempre. */}
        {(!conEncuadre || enc.zonas) && (
          <>
            <div
              className="pointer-events-none absolute inset-x-0 top-0 border-b border-dashed border-cyan-400/40"
              style={{
                height: preset.safe_top * escala,
                background: conEncuadre ? "rgba(0,0,0,0.35)" : undefined,
              }}
            />
            <div
              className="pointer-events-none absolute inset-x-0 bottom-0 border-t border-dashed border-cyan-400/40"
              style={{
                height: preset.safe_bottom * escala,
                background: conEncuadre ? "rgba(0,0,0,0.35)" : undefined,
              }}
            />
          </>
        )}

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
                aria-valuemax={Math.round(durSalida)}
                aria-valuenow={Math.round(Math.min(tiempo, durSalida))}
                aria-valuetext={`${formatearDuracionMs(tiempo * 1000)} de ${formatearDuracionMs(durSalida * 1000)}`}
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

              {/* Reloj del VÍDEO FINAL (tiempo de salida / duración total tras recortes y cortes). */}
              <span className="shrink-0 text-[10px] tabular-nums text-white/90">
                {formatearDuracionMs(tiempo * 1000)} / {formatearDuracionMs(durSalida * 1000)}
              </span>
            </div>
          </>
        )}
      </div>
  );

  // Con encuadre: lienzo centrado + scroll/pan + barra inferior de zoom/encuadre (igual que el
  // Estudio de imagen). El lienzo puede desbordar al hacer zoom y se navega con scroll/pan.
  if (conEncuadre) {
    // El lienzo LLENA el área (como el Estudio de imagen); la barra de zoom FLOTA sobre él (no roba
    // alto) y el aviso "aproximado" es una etiqueta discreta. Así el preview usa todo el espacio.
    return (
      <div ref={contRef} className="relative flex min-h-0 w-full flex-1 flex-col">
        <div ref={medirRef} className="flex min-h-0 flex-1 items-center justify-center overflow-hidden">
          <div
            ref={scrollRef}
            onWheel={onRueda}
            onMouseDown={onMouseDownContenedor}
            className="max-h-full max-w-full overflow-auto"
            style={{ cursor: paneando ? "grabbing" : espacio ? "grab" : undefined }}
          >
            {lienzo}
          </div>
        </div>
        <span className="pointer-events-none absolute left-2 top-2 text-[10px] text-muted-foreground/60">
          Preview aproximado
        </span>
        {/* Barra de zoom/encuadre FLOTANTE, centrada abajo (igual que el editor de imagen). */}
        <div className="pointer-events-none absolute inset-x-0 bottom-2 z-10 flex justify-center">
          <div className="pointer-events-auto">
            <ControlesEncuadre
              iman={enc.iman}
              setIman={enc.setIman}
              grid={enc.grid}
              setGrid={enc.setGrid}
              tamCelda={enc.tamCelda}
              setTamCelda={enc.setTamCelda}
              dentroMarco={enc.dentroMarco}
              setDentroMarco={enc.setDentroMarco}
              zonas={enc.zonas}
              setZonas={enc.setZonas}
              escala={escala}
              alejar={alejar}
              acercar={acercar}
              zoomReal={zoomReal}
              ajustarPantalla={ajustarPantalla}
              fijarEscala={fijarEscala}
            />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div ref={contRef} className="flex w-full flex-col items-center gap-2">
      {lienzo}
      <p className="text-[11px] text-muted-foreground/70">Preview aproximado</p>
    </div>
  );
}

/**
 * Render APROXIMADO en DOM de una capa de overlay sobre el vídeo (texto/imagen/logo/marco/grupo).
 * No es pixel-a-pixel (eso es el render del servidor): degrada degradados/formas complejas a
 * sólido, pero muestra el texto y las imágenes FIELES (color/fuente/tamaño/imagen real) en vez de
 * cajas de marcador. El hueco de foto vacío no se pinta: lo cubre el vídeo.
 */
function CapaOverlayDOM({ capa, escala }: { capa: Capa; escala: number }) {
  const base: React.CSSProperties = {
    position: "absolute",
    left: capa.x * escala,
    top: capa.y * escala,
    width: capa.w * escala,
    height: capa.h * escala,
    opacity: capa.opacidad ?? 1,
    transform: capa.rotacion ? `rotate(${capa.rotacion}deg)` : undefined,
    overflow: "hidden",
  };

  if (capa.tipo === "texto") {
    const t = capa as CapaTexto;
    const justify =
      t.valign === "arriba" ? "flex-start" : t.valign === "abajo" ? "flex-end" : "center";
    const items =
      t.alineacion === "izquierda" ? "flex-start" : t.alineacion === "derecha" ? "flex-end" : "center";
    const textAlign =
      t.alineacion === "justificado"
        ? "justify"
        : t.alineacion === "izquierda"
          ? "left"
          : t.alineacion === "derecha"
            ? "right"
            : "center";
    const decor = [t.subrayado && "underline", t.tachado && "line-through"].filter(Boolean).join(" ");
    const sombraCss = t.sombra
      ? `${(t.sombra.dx || 0) * escala}px ${(t.sombra.dy || 0) * escala}px ${(t.sombra.desenfoque || 0) * escala}px ${t.sombra.color}`
      : undefined;
    // Chip: fondo "pill" que abraza el texto (inline-block respeta la alineación de la caja).
    const chipCss: React.CSSProperties = t.chip
      ? {
          display: "inline-block",
          background: t.chip.color,
          padding: `${(t.chip.pad_y || 0) * escala}px ${(t.chip.pad_x || 0) * escala}px`,
          borderRadius: (t.chip.radio || 0) * escala,
        }
      : {};
    return (
      <div
        style={{ ...base, display: "flex", flexDirection: "column", justifyContent: justify, alignItems: items }}
        title={capa.nombre ?? "texto"}
      >
        <div
          style={{
            width: "100%",
            color: t.color,
            fontFamily: `"${t.familia}", sans-serif`,
            fontSize: Math.max(6, t.tamano * escala),
            fontWeight: t.peso,
            fontStyle: t.cursiva ? "italic" : undefined,
            lineHeight: t.interlineado || 1.1,
            letterSpacing: (t.interletra || 0) * escala,
            textTransform: t.mayusculas ? "uppercase" : undefined,
            textAlign,
            textDecoration: decor || undefined,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            textShadow: sombraCss,
            WebkitTextStroke: t.contorno
              ? `${Math.max(0.4, t.contorno.grosor * escala)}px ${t.contorno.color}`
              : undefined,
          }}
        >
          <span style={chipCss}>{t.texto || ""}</span>
        </div>
      </div>
    );
  }

  if (capa.tipo === "imagen") {
    const im = capa as CapaImagen;
    if (!im.objeto) return null; // hueco de foto vacío: lo cubre el vídeo
    return (
      <img
        src={urlMedia(im.objeto)}
        alt=""
        style={{
          ...base,
          objectFit: im.ajuste === "contain" ? "contain" : "cover",
          objectPosition: `${(im.foco?.[0] ?? 0.5) * 100}% ${(im.foco?.[1] ?? 0.5) * 100}%`,
        }}
      />
    );
  }

  if (capa.tipo === "logo") {
    const lg = capa as CapaLogo;
    if (lg.tipo_logo === "imagen" && lg.media_id) {
      return <img src={urlMedia(lg.media_id)} alt="" style={{ ...base, objectFit: "contain" }} />;
    }
    const wm = lg.wordmark;
    return (
      <div
        style={{
          ...base,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: wm.fondo,
          color: wm.color,
          fontFamily: `"${wm.familia}", sans-serif`,
          fontWeight: wm.peso,
          fontSize: Math.max(6, capa.h * escala * 0.5),
        }}
      >
        {wm.texto}
      </div>
    );
  }

  if (capa.tipo === "marco") {
    const mc = capa as CapaMarco;
    return (
      <div
        style={{
          ...base,
          background: mc.relleno ?? undefined,
          border: mc.borde ? `${Math.max(0.4, mc.borde.grosor * escala)}px solid ${mc.borde.color}` : undefined,
          borderRadius: (mc.radio || 0) * escala,
        }}
      />
    );
  }

  if (capa.tipo === "overlay") {
    // Banda de legibilidad: gradiente full-width pegado a arriba/abajo de la caja, opaco en el
    // borde y desvaneciéndose hacia dentro (aprox. de la rampa del render).
    const ov = capa as CapaOverlay;
    const m = /^#?([0-9a-fA-F]{6})([0-9a-fA-F]{2})?$/.exec(ov.color || "#000000");
    const rgb = m ? m[1] : "000000";
    const aHex = m && m[2] ? parseInt(m[2], 16) / 255 : 1;
    const r = parseInt(rgb.slice(0, 2), 16);
    const g = parseInt(rgb.slice(2, 4), 16);
    const b = parseInt(rgb.slice(4, 6), 16);
    const aMax = ((ov.alpha ?? 238) / 255) * aHex;
    const arriba = ov.lado === "arriba";
    const bandH = Math.max(1, Math.floor(capa.h * (ov.alto_frac ?? 0.58))) * escala;
    return (
      <div style={base}>
        <div
          className="absolute inset-x-0"
          style={{
            height: bandH,
            ...(arriba ? { top: 0 } : { bottom: 0 }),
            background: `linear-gradient(to ${arriba ? "top" : "bottom"}, transparent, rgba(${r},${g},${b},${aMax}))`,
          }}
        />
      </div>
    );
  }

  if (capa.tipo === "grupo") {
    // Grupo: hijos en coordenadas absolutas del documento; se pintan igual que las capas raíz.
    const hijos = (capa as unknown as { capas?: Capa[] }).capas ?? [];
    return (
      <>
        {hijos
          .filter((c) => c.visible !== false)
          .map((c) => (
            <CapaOverlayDOM key={c.id} capa={c} escala={escala} />
          ))}
      </>
    );
  }

  return null;
}
