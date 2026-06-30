/**
 * TimelineMultipista — timeline de VARIOS carriles del Estudio de Video (evolución de
 * LineaTiempo a multipista). Componente HOJA: edita en TIEMPO DE SALIDA (el vídeo final
 * concatenado) y emite intenciones por callback; el padre muta el documento y guarda.
 *
 * Estructura: una COLUMNA DE CABECERAS fija (etiqueta + controles de cada pista) y, a su
 * derecha, un VIEWPORT con scroll horizontal cuyo eje escala con el zoom. Todos los carriles
 * comparten ese mismo eje y el mismo playhead:
 *   1. Regla de tiempo + PLAYHEAD arrastrable (scrub con window-mousemove, flechas de teclado).
 *   2. VÍDEO — los segmentos de la pista base como tarjetas CONSECUTIVAS (ancho ∝ su duración
 *      de salida), con asas de trim en los bordes (commit al soltar → `onTrimSegmento`), una
 *      cuchilla que divide en el playhead (`onDividirSegmento`) y, por segmento, mover ◀/▶
 *      (`onMoverSegmento`) y eliminar (`onQuitarSegmento`, sólo si hay >1).
 *   3. AUDIO (base) — pista propia: una BARRA que abarca [0, total] reflejando volumen/silenciar
 *      (`onAudioBase`), con sus controles en la cabecera.
 *   4. MÚSICA — barra propia con su tramo, controles de volumen/silenciar/quitar, o «+ Música».
 *   5. PiP y SUBTÍTULOS — barras finas clicables (clic = seek al inicio de esa barra).
 *
 * El eje es [0, duración total de la base]. Cada segmento ocupa [inicio acumulado, +duración de
 * salida]; el render server-side concatena los segmentos en ese orden. El zoom sólo escala el
 * ancho del eje (px); las conversiones px↔ms leen el ancho REAL escalado vía
 * `getBoundingClientRect`, así los gestos quedan correctos a cualquier zoom y scroll. `disabled`
 * apaga la edición pero deja vivo el seek.
 *
 * Auto-scroll: cuando tiempoSeg cambia y el playhead queda fuera del viewport visible (con zoom
 * >1x), el contenedor scrolleable lo centra automáticamente. El arrastre manual (scrub o trim)
 * bloquea el efecto para no interferir con el gesto del usuario.
 *
 * Snap de trim: al arrastrar un asa, si el borde queda a <8 px (pantalla) del playhead, de un
 * borde de otro segmento o de una marca de la regla, enclava en ese punto y pinta una guía
 * vertical amarilla. El valor enclavado es el que se commitea al soltar.
 */
import * as React from "react";
import {
  ChevronLeft,
  ChevronRight,
  Maximize2,
  Music,
  Plus,
  Scissors,
  Trash2,
  Volume2,
  VolumeX,
  ZoomIn,
  ZoomOut,
} from "lucide-react";

import {
  duracionBaseMs,
  formatearDuracionMs,
  MIN_RECORTE_MS,
  pistaAudio,
  pistaPip,
  segmentosBase,
  VOLUMEN_DEFECTO,
  type ClipVideo,
  type ComposicionVideo,
  type SegmentoSub,
} from "@/lib/video";

export interface TimelineMultipistaProps {
  doc: ComposicionVideo;
  /** Tiempo actual del player (segundos de salida). */
  tiempoSeg: number;
  /** Busca en el player (segundos de salida): arrastrar el playhead / scrub de la regla. */
  onSeek: (seg: number) => void;
  /** Commit del trim de un segmento: `recorte_in_ms`/`recorte_out_ms` en la FUENTE del segmento. */
  onTrimSegmento?: (idx: number, inMs: number, outMs: number) => void;
  /** Cuchilla: divide el segmento en su tiempo de salida LOCAL (0..duración del segmento). */
  onDividirSegmento?: (idx: number, msLocal: number) => void;
  /** Elimina el segmento `idx` (sólo se ofrece con >1 segmento). */
  onQuitarSegmento?: (idx: number) => void;
  /** Reordena el segmento `idx` a la posición `destino`. */
  onMoverSegmento?: (idx: number, destino: number) => void;
  /** Volumen/silenciar del audio de la pista base (afecta a todos sus segmentos). */
  onAudioBase?: (cambios: { volumen?: number; silenciar?: boolean }) => void;
  /** Añade música a la composición. */
  onAnadirMusica?: () => void;
  /** Volumen/silenciar de la música. */
  onVolumenMusica?: (cambios: { volumen?: number; silenciar?: boolean }) => void;
  /** Quita la música. */
  onQuitarMusica?: () => void;
  /** Segmentos de subtítulos (barra fina clicable, en tiempo de salida). */
  segmentos?: SegmentoSub[];
  /** URL servible del clip base: para extraer THUMBNAILS de frames en el carril de vídeo. */
  baseUrl?: string;
  /** Trim del clip PiP (carril PiP editable): `recorte_in_ms`/`recorte_out_ms` en su fuente. */
  onTrimPip?: (inMs: number, outMs: number) => void;
  /** Fundidos de la música (carril de música): fade in/out en ms. */
  onFadeMusica?: (cambios: { fade_in_ms?: number; fade_out_ms?: number }) => void;
  /** Añadir un marcador en `ms` (tiempo de salida). */
  onAgregarMarcador?: (ms: number, etiqueta?: string) => void;
  /** Quitar un marcador por id. */
  onQuitarMarcador?: (id: string) => void;
  /** Desactiva la edición (el seek sigue activo). */
  disabled?: boolean;
}

/** Paso entre marcas de la regla: el menor que deja ≤ 8 etiquetas legibles. */
function pasoRegla(totalMs: number): number {
  const pasos = [1000, 2000, 5000, 10000, 15000, 30000, 60000, 120000, 300000];
  for (const p of pasos) if (totalMs / p <= 8) return p;
  return 600000;
}

/** Duración de salida (ms) de un segmento: lo que aporta al vídeo final tras su recorte. */
function durSegMs(c: ClipVideo): number {
  const inn = c.recorte_in_ms ?? 0;
  const out = c.recorte_out_ms || c.fin_ms || 0;
  return Math.max(0, out - inn);
}

// Límites y paso del zoom del eje (1 = ajustado al viewport; >1 = más detalle + scroll).
const ZOOM_MIN = 1;
const ZOOM_MAX = 8;
const ZOOM_PASO = 1.5;

// Altura de cada carril (compartida por su cabecera y su pista para que casen en vertical).
const ALTO_REGLA = "h-5";
const ALTO_VIDEO = "h-16";
const ALTO_PISTA = "h-9";
const ALTO_BARRAS = "h-7";

export function TimelineMultipista({
  doc,
  tiempoSeg,
  onSeek,
  onTrimSegmento,
  onDividirSegmento,
  onQuitarSegmento,
  onMoverSegmento,
  onAudioBase,
  onAnadirMusica,
  onVolumenMusica,
  onQuitarMusica,
  segmentos,
  disabled = false,
}: TimelineMultipistaProps) {
  const ejeRef = React.useRef<HTMLDivElement>(null);
  const scrollRef = React.useRef<HTMLDivElement>(null);
  // true mientras el usuario arrastra (scrub o trim): bloquea el auto-scroll.
  const arrastrando = React.useRef(false);

  // Refs a valores calculados en render: permiten leerlos dentro de handlers de drag sin
  // stale closure (los handlers son useCallback con deps mínimas).
  const tiempoMsRef = React.useRef(0);
  const axisRef = React.useRef(1);
  const offsetsRef = React.useRef<number[]>([]);
  const segsRef = React.useRef<ClipVideo[]>([]);

  // Asa en arrastre (estado VISUAL del gesto): el commit va en el mouseup vía onTrimSegmento.
  const [arrastre, setArrastre] = React.useState<{ idx: number; asa: "in" | "out"; ms: number } | null>(
    null,
  );
  // Posición (ms) de la guía de snap durante el trim; null = sin guía activa.
  const [guiaSnap, setGuiaSnap] = React.useState<number | null>(null);
  // Zoom del eje (multiplicador del ancho). Sólo afecta a px; el modelo de tiempo no cambia.
  const [zoom, setZoom] = React.useState(1);

  // Valores derivados del doc (no son hooks; pueden computarse antes del early return).
  const segs = segmentosBase(doc);
  const total = duracionBaseMs(doc);
  const axisTotal = Math.max(total, 1);
  // tiempoMs se calcula aquí (antes del early return) para que el useEffect de auto-scroll lo use.
  const tiempoMs = Math.min(Math.max(0, tiempoSeg * 1000), axisTotal);

  // Sincronizar refs con los valores de este render para que los handlers los lean frescos.
  tiempoMsRef.current = tiempoMs;
  axisRef.current = axisTotal;
  segsRef.current = segs;

  /** Posición X del puntero -> ms sobre el eje de salida (clamp a [0, axisTotal]). */
  const msDesdePuntero = React.useCallback(
    (clientX: number): number => {
      const el = ejeRef.current;
      if (!el) return 0;
      const rect = el.getBoundingClientRect();
      if (rect.width <= 0) return 0;
      const frac = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
      return frac * axisTotal;
    },
    [axisTotal],
  );

  /** Scrub del playhead: mousedown = seek; el arrastre sigue en window (no se pierde el gesto). */
  const iniciarScrub = React.useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      arrastrando.current = true;
      onSeek(msDesdePuntero(e.clientX) / 1000);
      const mover = (ev: MouseEvent) => onSeek(msDesdePuntero(ev.clientX) / 1000);
      const soltar = () => {
        arrastrando.current = false;
        window.removeEventListener("mousemove", mover);
        window.removeEventListener("mouseup", soltar);
      };
      window.addEventListener("mousemove", mover);
      window.addEventListener("mouseup", soltar);
    },
    [msDesdePuntero, onSeek],
  );

  // Inicios acumulados (tiempo de salida) de cada segmento.
  const offsets = React.useMemo(() => {
    const acc: number[] = [];
    let t = 0;
    for (const c of segs) {
      acc.push(t);
      t += durSegMs(c);
    }
    return acc;
  }, [segs]);

  // Sincronizar ref de offsets tras el useMemo.
  offsetsRef.current = offsets;

  /**
   * Arrastre de un asa de trim del segmento `idx`. Mueve el borde DENTRO de su slot (encoge):
   * el asa izquierda crece `recorte_in_ms`, la derecha encoge `recorte_out_ms`. Clampa al mínimo
   * de 1 s y sólo emite `onTrimSegmento` al soltar si hubo cambio real.
   * Snap: si el borde queda a <8 px (pantalla) del playhead, de otro borde de segmento o de una
   * marca de la regla, enclava en ese punto y activa la guía amarilla.
   */
  const iniciarTrim = React.useCallback(
    (idx: number, asa: "in" | "out") => (e: React.MouseEvent) => {
      const seg = segsRef.current[idx];
      if (disabled || !onTrimSegmento || !seg) return;
      e.preventDefault();
      e.stopPropagation();
      const rIn = seg.recorte_in_ms ?? 0;
      const rOut = seg.recorte_out_ms || seg.fin_ms || 0;
      const dur = Math.max(0, rOut - rIn);
      const ini = offsetsRef.current[idx];
      const fin = ini + dur;
      const minDur = Math.min(MIN_RECORTE_MS, dur);
      const clampa = (ms: number) =>
        asa === "in" ? Math.min(Math.max(ini, ms), fin - minDur) : Math.min(Math.max(ini + minDur, ms), fin);
      let ultimo = asa === "in" ? ini : fin;
      setArrastre({ idx, asa, ms: ultimo });
      arrastrando.current = true;
      const mover = (ev: MouseEvent) => {
        let ms = clampa(msDesdePuntero(ev.clientX));
        const el = ejeRef.current;
        if (el) {
          const rect = el.getBoundingClientRect();
          const axis = axisRef.current;
          if (rect.width > 0) {
            // Umbral de snap en ms equivalente a 8 px de pantalla a la escala actual.
            const umbralMs = (8 / rect.width) * axis;
            const offs = offsetsRef.current;
            const ss = segsRef.current;
            const paso = pasoRegla(axis);
            // Candidatos: playhead, bordes de todos los segmentos, marcas de la regla.
            const candidatos: number[] = [tiempoMsRef.current];
            for (let i = 0; i < offs.length; i++) {
              candidatos.push(offs[i]);
              candidatos.push(offs[i] + durSegMs(ss[i]));
            }
            for (let m = 0; m <= axis; m += paso) candidatos.push(m);
            let snapMs: number | null = null;
            let minDist = Infinity;
            for (const c of candidatos) {
              const d = Math.abs(c - ms);
              if (d < umbralMs && d < minDist) {
                minDist = d;
                snapMs = c;
              }
            }
            if (snapMs !== null) ms = clampa(snapMs);
            setGuiaSnap(snapMs !== null ? ms : null);
          }
        }
        ultimo = ms;
        setArrastre({ idx, asa, ms: ultimo });
      };
      const soltar = () => {
        arrastrando.current = false;
        window.removeEventListener("mousemove", mover);
        window.removeEventListener("mouseup", soltar);
        setArrastre(null);
        setGuiaSnap(null);
        const nuevoIn = asa === "in" ? Math.round(rIn + (ultimo - ini)) : rIn;
        const nuevoOut = asa === "out" ? Math.round(rOut + (ultimo - fin)) : rOut;
        if (nuevoIn === rIn && nuevoOut === rOut) return; // click sin arrastre: nada que guardar
        onTrimSegmento(idx, nuevoIn, nuevoOut);
        onSeek(ultimo / 1000); // el preview salta al borde recortado al soltar
      };
      window.addEventListener("mousemove", mover);
      window.addEventListener("mouseup", soltar);
    },
    [disabled, onTrimSegmento, msDesdePuntero, onSeek],
  );

  /** Teclado del playhead: flechas ±1 s, Shift ±5 s, Home/End a los extremos. */
  const onTeclaPlayhead = React.useCallback(
    (e: React.KeyboardEvent) => {
      const paso = e.shiftKey ? 5 : 1;
      if (e.key === "ArrowRight") {
        e.preventDefault();
        onSeek(Math.min(axisTotal / 1000, tiempoSeg + paso));
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        onSeek(Math.max(0, tiempoSeg - paso));
      } else if (e.key === "Home") {
        e.preventDefault();
        onSeek(0);
      } else if (e.key === "End") {
        e.preventDefault();
        onSeek(axisTotal / 1000);
      }
    },
    [onSeek, axisTotal, tiempoSeg],
  );

  // Auto-scroll: cuando tiempoSeg cambia y el playhead queda fuera del viewport visible (con
  // zoom >1x), centra el contenedor en el playhead. No actúa durante el arrastre del usuario.
  React.useEffect(() => {
    if (arrastrando.current) return;
    const scroll = scrollRef.current;
    if (!scroll || zoom <= 1) return;
    const playheadPx = (tiempoMs / axisTotal) * scroll.scrollWidth;
    const visLeft = scroll.scrollLeft;
    const visRight = visLeft + scroll.clientWidth;
    if (playheadPx < visLeft || playheadPx > visRight) {
      scroll.scrollLeft = Math.max(0, playheadPx - scroll.clientWidth / 2);
    }
  }, [tiempoMs, axisTotal, zoom]);

  // Sin segmentos no hay nada que cronometrar.
  if (segs.length === 0) return null;

  const pct = (ms: number) => `${(Math.min(Math.max(0, ms), axisTotal) / axisTotal) * 100}%`;

  // Marcas de la regla (0, paso, 2·paso, …, ≤ total).
  const paso = pasoRegla(axisTotal);
  const marcas: number[] = [];
  for (let ms = 0; ms <= axisTotal; ms += paso) marcas.push(ms);

  // Segmento bajo el playhead y su tiempo de salida local (para la cuchilla).
  let segActivo = -1;
  let msLocalCorte = 0;
  for (let i = 0; i < segs.length; i++) {
    const ini = offsets[i];
    const fin = ini + durSegMs(segs[i]);
    if (tiempoMs >= ini && (tiempoMs < fin || i === segs.length - 1)) {
      segActivo = i;
      msLocalCorte = tiempoMs - ini;
      break;
    }
  }
  const puedeDividir =
    !disabled &&
    !!onDividirSegmento &&
    segActivo >= 0 &&
    msLocalCorte >= MIN_RECORTE_MS &&
    durSegMs(segs[segActivo]) - msLocalCorte >= MIN_RECORTE_MS;

  // Audio del clip base (todos los segmentos comparten valor; se lee del primero).
  const volBase = segs[0]?.volumen ?? VOLUMEN_DEFECTO;
  const mudoBase = segs[0]?.silenciar ?? false;

  // Música (primer clip de la pista de audio), si existe: tramo [offset, offset+dur] capado.
  const musica = pistaAudio(doc)?.clips[0] ?? null;
  let barMusica: { ini: number; fin: number } | null = null;
  if (musica) {
    const durMus =
      Math.max(0, (musica.recorte_out_ms ?? 0) - (musica.recorte_in_ms ?? 0)) ||
      Math.max(0, (musica.fin_ms ?? 0) - (musica.inicio_ms ?? 0));
    const ini = Math.min(Math.max(0, musica.offset_ms ?? 0), axisTotal);
    barMusica = { ini, fin: durMus > 0 ? Math.min(axisTotal, ini + durMus) : axisTotal };
  }
  const mudoMus = musica?.silenciar ?? false;
  const volMus = musica?.volumen ?? VOLUMEN_DEFECTO;

  // Barra informativa del PiP: arranca en 0 (salida) y dura su recorte, capado al total.
  const clipPip = pistaPip(doc)?.clips[0];
  let barPip: { ini: number; fin: number } | null = null;
  if (clipPip?.media_id) {
    const durPip =
      Math.max(0, (clipPip.recorte_out_ms ?? 0) - (clipPip.recorte_in_ms ?? 0)) ||
      Math.max(0, (clipPip.fin_ms ?? 0) - (clipPip.inicio_ms ?? 0));
    barPip = { ini: 0, fin: durPip > 0 ? Math.min(axisTotal, durPip) : axisTotal };
  }

  const segsSub = segmentos ?? [];
  const hayBarras = !!barPip || segsSub.length > 0;

  const acercar = () => setZoom((z) => Math.min(ZOOM_MAX, z * ZOOM_PASO));
  const alejar = () => setZoom((z) => Math.max(ZOOM_MIN, z / ZOOM_PASO));
  const ajustar = () => setZoom(1);

  return (
    <div className="select-none space-y-1" data-testid="timeline-multipista">
      {/* Barra de zoom del eje temporal: etiquetada «Zoom» para distinguirla del zoom del lienzo. */}
      <div
        className="flex items-center justify-end gap-1"
        title="Zoom temporal"
        aria-label="Zoom temporal"
      >
        <span className="mr-0.5 text-[10px] font-medium text-muted-foreground" aria-hidden="true">
          Zoom
        </span>
        <button
          type="button"
          aria-label="Alejar"
          disabled={zoom <= ZOOM_MIN}
          onClick={alejar}
          className="rounded border border-border p-1 text-muted-foreground hover:bg-accent/50 hover:text-foreground disabled:opacity-40"
        >
          <ZoomOut className="h-3.5 w-3.5" />
        </button>
        <span className="w-10 text-center text-[10px] tabular-nums text-muted-foreground" aria-label="Nivel de zoom">
          {Math.round(zoom * 100)}%
        </span>
        <button
          type="button"
          aria-label="Acercar"
          disabled={zoom >= ZOOM_MAX}
          onClick={acercar}
          className="rounded border border-border p-1 text-muted-foreground hover:bg-accent/50 hover:text-foreground disabled:opacity-40"
        >
          <ZoomIn className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          aria-label="Ajustar zoom"
          disabled={zoom === 1}
          onClick={ajustar}
          className="inline-flex items-center gap-1 rounded border border-border px-1.5 py-1 text-[10px] font-medium text-muted-foreground hover:bg-accent/50 hover:text-foreground disabled:opacity-40"
        >
          <Maximize2 className="h-3 w-3" /> Ajustar
        </button>
      </div>

      <div className="flex overflow-hidden rounded-md border border-border bg-muted/40">
        {/* Columna de CABECERAS (fija): etiqueta + controles de cada pista. */}
        <div className="w-36 shrink-0 border-r border-border/60">
          {/* Hueco bajo la regla. */}
          <div className={`${ALTO_REGLA} border-b border-border/60`} />

          {/* Vídeo: etiqueta + cuchilla. */}
          <div className={`${ALTO_VIDEO} flex flex-col justify-center gap-1 border-b border-border/40 px-2`}>
            <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
              Vídeo
            </span>
            {onDividirSegmento && (
              <button
                type="button"
                aria-label="Dividir en el cursor"
                disabled={!puedeDividir}
                onClick={() => onDividirSegmento(segActivo, Math.round(msLocalCorte))}
                className="inline-flex w-fit items-center gap-1 rounded border border-border px-1.5 py-0.5 text-[10px] font-medium text-foreground hover:bg-accent/50 disabled:cursor-default disabled:opacity-40"
              >
                <Scissors className="h-3 w-3" /> Dividir
              </button>
            )}
          </div>

          {/* Audio (base): silenciar + volumen. */}
          {onAudioBase && (
            <div className={`${ALTO_PISTA} flex items-center gap-1 border-b border-border/40 px-2`}>
              <button
                type="button"
                aria-label="Silenciar audio base"
                aria-pressed={mudoBase}
                disabled={disabled}
                onClick={() => onAudioBase({ silenciar: !mudoBase })}
                className={`rounded p-1 disabled:opacity-40 ${
                  mudoBase ? "text-destructive" : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {mudoBase ? <VolumeX className="h-3.5 w-3.5" /> : <Volume2 className="h-3.5 w-3.5" />}
              </button>
              <input
                type="range"
                min={0}
                max={1}
                step={0.01}
                value={volBase}
                disabled={disabled || mudoBase}
                onChange={(e) => onAudioBase({ volumen: Number(e.target.value) })}
                className="min-w-0 flex-1 disabled:opacity-40"
                aria-label="Volumen del audio base"
              />
            </div>
          )}

          {/* Música: controles si hay, «+ Música» si no. */}
          <div className={`${ALTO_PISTA} flex items-center gap-1 border-b border-border/40 px-2`}>
            {musica ? (
              <>
                {onVolumenMusica && (
                  <>
                    <button
                      type="button"
                      aria-label="Silenciar música"
                      aria-pressed={mudoMus}
                      disabled={disabled}
                      onClick={() => onVolumenMusica({ silenciar: !mudoMus })}
                      className={`rounded p-1 disabled:opacity-40 ${
                        mudoMus ? "text-destructive" : "text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      {mudoMus ? <VolumeX className="h-3.5 w-3.5" /> : <Volume2 className="h-3.5 w-3.5" />}
                    </button>
                    <input
                      type="range"
                      min={0}
                      max={1}
                      step={0.01}
                      value={volMus}
                      disabled={disabled || mudoMus}
                      onChange={(e) => onVolumenMusica({ volumen: Number(e.target.value) })}
                      className="min-w-0 flex-1 disabled:opacity-40"
                      aria-label="Volumen de la música"
                    />
                  </>
                )}
                {onQuitarMusica && (
                  <button
                    type="button"
                    aria-label="Quitar música"
                    disabled={disabled}
                    onClick={() => onQuitarMusica()}
                    className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-40"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                )}
              </>
            ) : (
              onAnadirMusica && (
                <button
                  type="button"
                  aria-label="Añadir música"
                  disabled={disabled}
                  onClick={() => onAnadirMusica()}
                  className="inline-flex items-center gap-1 rounded border border-dashed border-border px-2 py-0.5 text-[11px] font-medium text-muted-foreground hover:bg-accent/50 hover:text-foreground disabled:opacity-40"
                >
                  <Plus className="h-3 w-3" />
                  <Music className="h-3 w-3" /> Música
                </button>
              )
            )}
          </div>

          {/* PiP / subtítulos: etiqueta de la pista informativa. */}
          {hayBarras && (
            <div className={`${ALTO_BARRAS} flex items-center px-2`}>
              <span className="text-[9px] uppercase tracking-wide text-muted-foreground">PiP · Subs</span>
            </div>
          )}
        </div>

        {/* VIEWPORT con scroll horizontal: el eje escala con el zoom. */}
        <div ref={scrollRef} className="flex-1 overflow-x-auto">
          <div
            ref={ejeRef}
            aria-label="Pistas de la composición"
            className="relative"
            style={{ width: `${zoom * 100}%`, minWidth: "100%" }}
          >
            {/* Carril 1 · Regla con marcas de tiempo (scrub al pulsar). */}
            <div
              onMouseDown={iniciarScrub}
              aria-label="Regla de tiempo"
              className={`relative ${ALTO_REGLA} cursor-pointer touch-none border-b border-border/60`}
            >
              {marcas.map((ms) => (
                <div
                  key={ms}
                  className="pointer-events-none absolute top-0 h-full border-l border-border/60"
                  style={{ left: pct(ms) }}
                >
                  <span className="ml-0.5 text-[9px] tabular-nums leading-5 text-muted-foreground">
                    {formatearDuracionMs(ms)}
                  </span>
                </div>
              ))}
            </div>

            {/* Carril 2 · Vídeo: segmentos consecutivos. */}
            <div className={`relative ${ALTO_VIDEO} border-b border-border/40`}>
              {segs.map((seg, i) => {
                const rIn = seg.recorte_in_ms ?? 0;
                const rOut = seg.recorte_out_ms || seg.fin_ms || 0;
                const dur = Math.max(0, rOut - rIn);
                const ini = offsets[i];
                let left = ini;
                let width = dur;
                if (arrastre?.idx === i) {
                  if (arrastre.asa === "in") {
                    left = arrastre.ms;
                    width = ini + dur - arrastre.ms;
                  } else {
                    width = arrastre.ms - ini;
                  }
                }
                return (
                  <div
                    key={seg.id}
                    data-testid={`segmento-${i}`}
                    className="absolute inset-y-1 overflow-hidden rounded border border-primary/60 bg-primary/15"
                    style={{ left: pct(left), width: pct(width) }}
                  >
                    <div className="flex h-full flex-col items-center justify-center gap-1 px-2 text-center">
                      <span className="pointer-events-none text-[10px] font-medium tabular-nums text-foreground/80">
                        {formatearDuracionMs(width)}
                      </span>
                      {!disabled && (onMoverSegmento || onQuitarSegmento) && (
                        <div className="flex items-center gap-0.5">
                          {onMoverSegmento && (
                            <>
                              <button
                                type="button"
                                aria-label={`Mover segmento ${i + 1} a la izquierda`}
                                disabled={i === 0}
                                onClick={() => onMoverSegmento(i, i - 1)}
                                className="rounded p-0.5 text-muted-foreground hover:bg-accent/50 hover:text-foreground disabled:opacity-30"
                              >
                                <ChevronLeft className="h-3 w-3" />
                              </button>
                              <button
                                type="button"
                                aria-label={`Mover segmento ${i + 1} a la derecha`}
                                disabled={i === segs.length - 1}
                                onClick={() => onMoverSegmento(i, i + 1)}
                                className="rounded p-0.5 text-muted-foreground hover:bg-accent/50 hover:text-foreground disabled:opacity-30"
                              >
                                <ChevronRight className="h-3 w-3" />
                              </button>
                            </>
                          )}
                          {onQuitarSegmento && (
                            <button
                              type="button"
                              aria-label={`Eliminar segmento ${i + 1}`}
                              disabled={segs.length <= 1}
                              onClick={() => onQuitarSegmento(i)}
                              className="rounded p-0.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-30"
                            >
                              <Trash2 className="h-3 w-3" />
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                    {onTrimSegmento && (
                      <>
                        <button
                          type="button"
                          aria-label={`Recortar inicio del segmento ${i + 1}`}
                          disabled={disabled}
                          onMouseDown={iniciarTrim(i, "in")}
                          className="absolute inset-y-0 left-0 z-10 w-2 cursor-ew-resize bg-primary/80 hover:bg-primary disabled:cursor-default disabled:opacity-30"
                        >
                          <span className="pointer-events-none mx-auto block h-4 w-0.5 rounded bg-primary-foreground/80" />
                        </button>
                        <button
                          type="button"
                          aria-label={`Recortar fin del segmento ${i + 1}`}
                          disabled={disabled}
                          onMouseDown={iniciarTrim(i, "out")}
                          className="absolute inset-y-0 right-0 z-10 w-2 cursor-ew-resize bg-primary/80 hover:bg-primary disabled:cursor-default disabled:opacity-30"
                        >
                          <span className="pointer-events-none mx-auto block h-4 w-0.5 rounded bg-primary-foreground/80" />
                        </button>
                      </>
                    )}
                  </div>
                );
              })}
              {/* Línea de corte: indica visualmente dónde dividirá la cuchilla (sigue al playhead). */}
              {puedeDividir && (
                <div
                  aria-hidden="true"
                  className="pointer-events-none absolute inset-y-0 z-10 border-l-2 border-dashed border-orange-500/70"
                  style={{ left: pct(tiempoMs) }}
                />
              )}
            </div>

            {/* Carril 3 · Audio (base): pista propia (barra a lo largo de todo el eje). */}
            {onAudioBase && (
              <div className={`relative ${ALTO_PISTA} border-b border-border/40`}>
                <div
                  aria-label="Pista de audio base"
                  data-silenciado={mudoBase}
                  title={mudoBase ? "Audio base silenciado" : `Audio base · volumen ${Math.round(volBase * 100)}%`}
                  className={`absolute inset-y-1 flex items-center overflow-hidden rounded px-2 ${
                    mudoBase ? "bg-sky-400/25 ring-1 ring-inset ring-sky-400/40" : "bg-sky-400/50"
                  }`}
                  style={{ left: pct(0), width: pct(axisTotal) }}
                >
                  <span className="truncate text-[10px] font-medium text-sky-950/80">
                    {mudoBase ? "Audio · silenciado" : `Audio · ${Math.round(volBase * 100)}%`}
                  </span>
                </div>
              </div>
            )}

            {/* Carril 4 · Música: barra de su tramo (si hay). */}
            <div className={`relative ${ALTO_PISTA} border-b border-border/40`}>
              {barMusica && (
                <div
                  aria-label="Pista de música"
                  data-silenciado={mudoMus}
                  title={mudoMus ? "Música silenciada" : `Música · volumen ${Math.round(volMus * 100)}%`}
                  className={`absolute inset-y-1 flex items-center overflow-hidden rounded px-2 ${
                    mudoMus ? "bg-violet-400/15 ring-1 ring-inset ring-violet-400/30" : "bg-violet-400/50"
                  }`}
                  style={{ left: pct(barMusica.ini), width: pct(Math.max(0, barMusica.fin - barMusica.ini)) }}
                >
                  <span className="truncate text-[10px] font-medium text-violet-950/80">
                    {mudoMus ? "Música · silenciada" : `Música · ${Math.round(volMus * 100)}%`}
                  </span>
                </div>
              )}
            </div>

            {/* Carril 5 · PiP y subtítulos: barras finas clicables (clic = seek al inicio). */}
            {hayBarras && (
              <div className={`flex ${ALTO_BARRAS} flex-col justify-center gap-1`}>
                {barPip && (
                  <div className="relative h-1.5">
                    <div
                      title="PiP — clic para buscar"
                      aria-label="Barra de PiP"
                      role="button"
                      tabIndex={0}
                      onClick={() => onSeek(barPip.ini / 1000)}
                      onKeyDown={(e) => e.key === "Enter" && onSeek(barPip.ini / 1000)}
                      className="absolute inset-y-0 cursor-pointer rounded-full bg-sky-400/70 hover:bg-sky-400/90"
                      style={{ left: pct(barPip.ini), width: pct(Math.max(0, barPip.fin - barPip.ini)) }}
                    />
                  </div>
                )}
                {segsSub.length > 0 && (
                  <div className="relative h-1.5" aria-label="Barra de subtítulos">
                    {segsSub.map((s) => (
                      <div
                        key={s.id}
                        title={s.texto}
                        role="button"
                        tabIndex={0}
                        onClick={() => onSeek(s.inicio)}
                        onKeyDown={(e) => e.key === "Enter" && onSeek(s.inicio)}
                        className="absolute inset-y-0 cursor-pointer rounded-full bg-amber-400/70 hover:bg-amber-400/90"
                        style={{
                          left: pct(s.inicio * 1000),
                          width: pct(Math.max(0, (s.fin - s.inicio) * 1000)),
                        }}
                      />
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Playhead: línea vertical sobre todos los carriles + cabeza arrastrable (role=slider). */}
            <div
              className="pointer-events-none absolute inset-y-0 z-10 w-px bg-red-500"
              style={{ left: pct(tiempoMs) }}
            />
            <div
              role="slider"
              tabIndex={0}
              aria-label="Cursor de reproducción"
              aria-valuemin={0}
              aria-valuemax={Math.round(axisTotal / 1000)}
              aria-valuenow={Math.round(Math.min(tiempoSeg, axisTotal / 1000))}
              aria-valuetext={`${formatearDuracionMs(tiempoMs)} de ${formatearDuracionMs(axisTotal)}`}
              onMouseDown={(e) => {
                e.stopPropagation();
                iniciarScrub(e);
              }}
              onKeyDown={onTeclaPlayhead}
              className="absolute top-0 z-20 flex h-5 w-5 -translate-x-1/2 cursor-ew-resize items-start justify-center outline-none focus-visible:ring-1 focus-visible:ring-ring"
              style={{ left: pct(tiempoMs) }}
            >
              {/* Triángulo prominente (18px de alto) apuntando hacia abajo: indica posición exacta. */}
              <span
                style={{
                  display: "block",
                  width: 0,
                  height: 0,
                  borderLeft: "9px solid transparent",
                  borderRight: "9px solid transparent",
                  borderTop: "18px solid #ef4444",
                }}
              />
            </div>

            {/* Guía de snap: línea vertical amarilla visible durante el arrastre de un asa de trim. */}
            {guiaSnap !== null && (
              <div
                aria-hidden="true"
                className="pointer-events-none absolute inset-y-0 z-10 w-px bg-amber-400"
                style={{ left: pct(guiaSnap) }}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
