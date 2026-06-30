// Tipos y helpers PUROS del motor de edición de video (Ola VIDEO, "toque RRSS").
//
// Espejo del CONTRATO de `docs/maquina-contenido/08-video-engine.md` y del validador de
// `keni-shared/src/keni_shared/video.py`. El frontend edita el `documento` de composición en
// local y lo manda al backend (`POST /api/video/composiciones` + `PUT`), que lo re-valida y lo
// renderiza server-side con FFmpeg. Este fichero NO renderiza nada: solo construye/serializa el
// documento y normaliza los segmentos de subtítulos.
//
// Mantener sincronizado con el esquema Python (la fuente de verdad es el validador). Cualquier
// campo nuevo del sobre debe existir en ambos lados.

import type { Capa } from "@/editor/documento";

// v2 añade: pista `audio` (música mezclada con `amix`), `volumen`/`silenciar` por clip de vídeo
// y SEGMENTOS múltiples en la pista base (split/corte). Los documentos v1 son retro-compatibles
// (la pista audio falta → null; un solo clip base → un solo segmento).
export const VERSION_COMPOSICION = 2;

// --------------------------------------------------------------------------- #
// Presets de formato (espejo de keni_shared/video.py::PRESETS_FORMATO)         #
// --------------------------------------------------------------------------- #

export type AspectoVideo = "9:16" | "1:1" | "16:9";

/**
 * Un preset de formato tal como lo sirve `GET /api/video/formatos`:
 * `{preset, w, h, fps, safe_top, safe_bottom, redes}`. El nombre canónico del aspecto viene en
 * `preset` (9:16/1:1/16:9); `redes` son los ids de red que lo usan (para sugerir formato).
 */
export interface PresetFormatoVideo {
  preset: AspectoVideo | string;
  w: number;
  h: number;
  fps: number;
  safe_top: number;
  safe_bottom: number;
  redes?: string[];
}

// Presets locales (fallback si la API no responde). Idénticos a los de keni_shared/video.py.
export const PRESETS_FORMATO_VIDEO: Record<AspectoVideo, PresetFormatoVideo> = {
  "9:16": { preset: "9:16", w: 1080, h: 1920, fps: 30, safe_top: 220, safe_bottom: 320 },
  "1:1": { preset: "1:1", w: 1080, h: 1080, fps: 30, safe_top: 120, safe_bottom: 120 },
  "16:9": { preset: "16:9", w: 1920, h: 1080, fps: 30, safe_top: 80, safe_bottom: 120 },
};

export const ASPECTO_VIDEO_DEFECTO: AspectoVideo = "9:16";

export const ASPECTOS_VIDEO: AspectoVideo[] = ["9:16", "1:1", "16:9"];

export const ETIQUETA_ASPECTO: Record<AspectoVideo, string> = {
  "9:16": "Vertical · Reel / TikTok / Shorts",
  "1:1": "Cuadrado · Feed",
  "16:9": "Horizontal · YouTube / X",
};

/** Devuelve un preset por aspecto, cayendo al default si no se reconoce. */
export function presetParaAspecto(aspecto: string): PresetFormatoVideo {
  return PRESETS_FORMATO_VIDEO[(aspecto as AspectoVideo)] ?? PRESETS_FORMATO_VIDEO[ASPECTO_VIDEO_DEFECTO];
}

// --------------------------------------------------------------------------- #
// Esquema de COMPOSICIÓN (sobre JSON)                                           #
// --------------------------------------------------------------------------- #

export type AjusteVideo = "cover" | "contain";

/** Un clip de una pista de video (base o PiP). */
export interface ClipVideo {
  id: string;
  /** Clave de media (`videos/<sha>.mp4`), NO una URL. */
  media_id: string;
  inicio_ms: number;
  fin_ms: number;
  recorte_in_ms: number;
  recorte_out_ms: number;
  // Caja de destino en el lienzo (px). Para la base = todo el lienzo; para PiP = la ventana.
  x: number;
  y: number;
  w: number;
  h: number;
  ajuste: AjusteVideo;
  /** Punto focal 0..1 que dirige el `crop` del reencuadre cover. */
  foco: [number, number];
  /** Volumen del audio de ESTE clip (0..1). Ausente = 1 (volumen original). */
  volumen?: number;
  /** Silencia el audio de este clip (el render no lo mezcla). Ausente = false. */
  silenciar?: boolean;
}

export interface PistaVideo {
  id: string; // "base" | "pip"
  tipo: "video";
  /**
   * Clips de la pista. La pista BASE admite VARIOS clips ("segmentos") que el render concatena
   * en orden (corte/split); la pista PiP usa un único clip. Cada clip lleva su propio recorte.
   */
  clips: ClipVideo[];
}

/** Un clip de la pista de AUDIO (música u otra fuente de sonido mezclada con el clip base). */
export interface ClipAudio {
  id: string;
  /** Clave de media de audio/vídeo del que se toma el sonido. */
  media_id: string;
  inicio_ms: number;
  fin_ms: number;
  recorte_in_ms: number;
  recorte_out_ms: number;
  /** Desplazamiento (ms) respecto al inicio de la composición donde entra este audio. */
  offset_ms: number;
  /** Volumen 0..1 (ausente = 1). */
  volumen?: number;
  /** Silencia este clip de audio. */
  silenciar?: boolean;
  /** Fundido de ENTRADA (ms): el volumen sube de 0 a `volumen` en este tiempo. Ausente = 0. */
  fade_in_ms?: number;
  /** Fundido de SALIDA (ms): el volumen baja a 0 en los últimos `fade_out_ms`. Ausente = 0. */
  fade_out_ms?: number;
}

/** Pista de AUDIO independiente: música u otras fuentes que el render mezcla (`amix`). */
export interface PistaAudio {
  id: string; // "audio"
  tipo: "audio";
  clips: ClipAudio[];
}

export interface PistaOverlay {
  id: string; // "overlay"
  tipo: "overlay";
  /** Mismo modelo `Documento.capas` del Estudio de imagen. */
  capas: Capa[];
}

export interface EstiloSubtitulos {
  fuente: string;
  tam: number;
  color: string;
  borde: string;
  posicion: "inferior" | "superior" | "centro";
  karaoke: boolean;
}

export interface PistaSubtitulos {
  id: string; // "subs"
  tipo: "subtitulos";
  subtitulo_id: string;
  estilo: EstiloSubtitulos;
}

export type PistaComposicion = PistaVideo | PistaOverlay | PistaSubtitulos | PistaAudio;

export interface FormatoComposicion {
  w: number;
  h: number;
  fps: number;
  preset: string;
}

/** Marcador en la línea de tiempo (en tiempo de SALIDA), para sincronizar cortes/revisiones. */
export interface Marcador {
  id: string;
  ms: number;
  etiqueta?: string;
}

export interface ComposicionVideo {
  version: number;
  marca: string;
  formato: FormatoComposicion;
  duracion_ms: number;
  pistas: PistaComposicion[];
  /** Marcadores en la línea de tiempo (opcional; documentos v1/v2 pueden no traerlos). */
  marcadores?: Marcador[];
}

export const ESTILO_SUBTITULOS_DEFECTO: EstiloSubtitulos = {
  fuente: "Barlow",
  tam: 64,
  color: "#FFFFFF",
  borde: "#000000",
  posicion: "inferior",
  karaoke: true,
};

// --------------------------------------------------------------------------- #
// Lectores de pistas (acceso tipado a las pistas por id/tipo)                   #
// --------------------------------------------------------------------------- #

export function pistaBase(doc: ComposicionVideo): PistaVideo | null {
  return (doc.pistas.find((p) => p.tipo === "video" && p.id === "base") as PistaVideo) ?? null;
}

export function pistaPip(doc: ComposicionVideo): PistaVideo | null {
  return (doc.pistas.find((p) => p.tipo === "video" && p.id === "pip") as PistaVideo) ?? null;
}

export function pistaOverlay(doc: ComposicionVideo): PistaOverlay | null {
  return (doc.pistas.find((p) => p.tipo === "overlay") as PistaOverlay) ?? null;
}

export function pistaSubtitulos(doc: ComposicionVideo): PistaSubtitulos | null {
  return (doc.pistas.find((p) => p.tipo === "subtitulos") as PistaSubtitulos) ?? null;
}

/** Pista de audio (música). `null` en documentos v1 que no la traen (retro-compat). */
export function pistaAudio(doc: ComposicionVideo): PistaAudio | null {
  return (doc.pistas.find((p) => p.tipo === "audio") as PistaAudio) ?? null;
}

/** Segmentos de la pista base, en orden de concatenación (vacío si no hay clip base). */
export function segmentosBase(doc: ComposicionVideo): ClipVideo[] {
  return pistaBase(doc)?.clips ?? [];
}

// --------------------------------------------------------------------------- #
// Constructores / mutadores (inmutables: devuelven una composición nueva)       #
// --------------------------------------------------------------------------- #

let _seq = 0;
function nuevoId(prefijo: string): string {
  _seq += 1;
  return `${prefijo}-${Date.now().toString(36)}-${_seq}`;
}

/**
 * Composición VACÍA para un aspecto dado. Trae las cuatro pistas del contrato (base, pip,
 * overlay, subs), todas vacías salvo el estilo de subtítulos. `duracion_ms` 0 hasta conocer
 * el clip base.
 */
export function composicionVacia(aspecto: AspectoVideo, marca = ""): ComposicionVideo {
  const f = presetParaAspecto(aspecto);
  return {
    version: VERSION_COMPOSICION,
    marca,
    formato: { w: f.w, h: f.h, fps: f.fps, preset: aspecto },
    duracion_ms: 0,
    pistas: [
      { id: "base", tipo: "video", clips: [] },
      { id: "pip", tipo: "video", clips: [] },
      { id: "overlay", tipo: "overlay", capas: [] },
      { id: "subs", tipo: "subtitulos", subtitulo_id: "", estilo: { ...ESTILO_SUBTITULOS_DEFECTO } },
      { id: "audio", tipo: "audio", clips: [] },
    ],
  };
}

/** Reescribe el formato a otro aspecto, preservando pistas y clips (reescala las cajas). */
export function cambiarAspecto(doc: ComposicionVideo, aspecto: AspectoVideo): ComposicionVideo {
  const f = presetParaAspecto(aspecto);
  const escX = f.w / doc.formato.w;
  const escY = f.h / doc.formato.h;
  return {
    ...doc,
    formato: { w: f.w, h: f.h, fps: f.fps, preset: aspecto },
    pistas: doc.pistas.map((p) => {
      if (p.tipo !== "video") return p;
      return {
        ...p,
        clips: p.clips.map((c) => ({
          ...c,
          x: Math.round(c.x * escX),
          y: Math.round(c.y * escY),
          w: Math.round(c.w * escX),
          h: Math.round(c.h * escY),
        })),
      };
    }),
  };
}

/** Fija (o reemplaza) el clip de la pista BASE a pantalla completa. */
export function setClipBase(
  doc: ComposicionVideo,
  mediaId: string,
  duracionMs: number,
): ComposicionVideo {
  const clip: ClipVideo = {
    id: nuevoId("c"),
    media_id: mediaId,
    inicio_ms: 0,
    fin_ms: duracionMs,
    recorte_in_ms: 0,
    recorte_out_ms: duracionMs,
    x: 0,
    y: 0,
    w: doc.formato.w,
    h: doc.formato.h,
    ajuste: "cover",
    foco: [0.5, 0.5],
  };
  return {
    ...doc,
    duracion_ms: duracionMs,
    pistas: doc.pistas.map((p) => (p.tipo === "video" && p.id === "base" ? { ...p, clips: [clip] } : p)),
  };
}

/** Duración mínima (ms) que debe conservar un segmento del clip base tras un trim/corte. */
export const MIN_RECORTE_MS = 1000;

/** Duración de salida (ms) de un segmento: lo que aporta al vídeo final tras su recorte. */
function durSegmento(c: ClipVideo): number {
  const inn = c.recorte_in_ms ?? 0;
  const out = c.recorte_out_ms || c.fin_ms || 0;
  return Math.max(0, out - inn);
}

/** Duración total de la pista base (suma de los segmentos tras su recorte). */
export function duracionBaseMs(doc: ComposicionVideo): number {
  return segmentosBase(doc).reduce((s, c) => s + durSegmento(c), 0);
}

// --------------------------------------------------------------------------- #
// Conversión de tiempo SALIDA ↔ FUENTE (para el player del preview)            #
// --------------------------------------------------------------------------- #
// El timeline trabaja en tiempo de SALIDA (vídeo final concatenado: [0, suma de
// segmentos]). El elemento <video> reproduce tiempo de FUENTE (currentTime del clip crudo).
// Con recorte o segmentos múltiples ambos NO coinciden: estas funciones traducen entre ellos
// para que el playhead, el seek y los subtítulos usen el dominio correcto.

/** Recorte (in, out) de un segmento en ms (con respaldo a inicio/fin). */
function recorteSeg(c: ClipVideo): { inn: number; out: number } {
  const inn = c.recorte_in_ms ?? 0;
  const out = c.recorte_out_ms || c.fin_ms || inn;
  return { inn, out: Math.max(inn, out) };
}

/** Tiempo de salida (ms) acumulado ANTES del segmento `idx` (0 para el primero). */
export function inicioSalidaSegmentoMs(doc: ComposicionVideo, idx: number): number {
  const segs = segmentosBase(doc);
  let acc = 0;
  for (let i = 0; i < idx && i < segs.length; i++) acc += durSegmento(segs[i]);
  return acc;
}

/**
 * Tiempo de SALIDA (ms) → segmento + tiempo de FUENTE (ms) del <video>. Clampa al rango total.
 * Para el caso de un solo segmento: `fuenteMs = salidaMs + recorte_in`.
 */
export function salidaAFuenteMs(
  doc: ComposicionVideo,
  salidaMs: number,
): { idx: number; fuenteMs: number } {
  const segs = segmentosBase(doc);
  if (segs.length === 0) return { idx: 0, fuenteMs: Math.max(0, salidaMs) };
  let restante = Math.max(0, salidaMs);
  for (let i = 0; i < segs.length; i++) {
    const dur = durSegmento(segs[i]);
    if (restante <= dur || i === segs.length - 1) {
      const { inn } = recorteSeg(segs[i]);
      return { idx: i, fuenteMs: inn + Math.min(restante, dur) };
    }
    restante -= dur;
  }
  return { idx: segs.length - 1, fuenteMs: recorteSeg(segs[segs.length - 1]).out };
}

/** Segmento `idx` + tiempo de FUENTE (ms) → tiempo de SALIDA (ms). */
export function fuenteASalidaMs(doc: ComposicionVideo, idx: number, fuenteMs: number): number {
  const segs = segmentosBase(doc);
  if (segs.length === 0) return Math.max(0, fuenteMs);
  const i = Math.min(Math.max(0, idx), segs.length - 1);
  const { inn, out } = recorteSeg(segs[i]);
  const dentro = Math.min(Math.max(inn, fuenteMs), out) - inn;
  return inicioSalidaSegmentoMs(doc, i) + dentro;
}

/** Reescribe los clips de la pista base y recalcula `duracion_ms` (= suma de segmentos). */
function conSegmentosBase(doc: ComposicionVideo, clips: ClipVideo[]): ComposicionVideo {
  const duracion = clips.reduce((s, c) => s + durSegmento(c), 0);
  return {
    ...doc,
    duracion_ms: duracion,
    pistas: doc.pistas.map((p) => (p.tipo === "video" && p.id === "base" ? { ...p, clips } : p)),
  };
}

/**
 * Fija el recorte temporal de un SEGMENTO del clip BASE (`recorte_in_ms`/`recorte_out_ms`), que
 * el render aplica con `trim`/`-ss`-`-to` (`motores/estudio_video/filtros.py`). Clampa a
 * `[0, maxMs]` (duración real del segmento si se conoce) con un mínimo de `MIN_RECORTE_MS`.
 * Recalcula `fin_ms` del segmento y `duracion_ms` del documento (= suma de segmentos). Sin clip
 * base o sin cambio real devuelve el MISMO objeto (los autoguardados comparan por referencia).
 * `idx` selecciona el segmento (0 por defecto: compat con la pista de un solo clip).
 */
export function setRecorteBase(
  doc: ComposicionVideo,
  inMs: number,
  outMs: number,
  maxMs?: number,
  idx = 0,
): ComposicionVideo {
  const clips = segmentosBase(doc);
  const clip = clips[idx];
  if (!clip) return doc;
  const tope =
    maxMs && maxMs > 0
      ? maxMs
      : Math.max(clip.recorte_out_ms || 0, clip.fin_ms || 0, durSegmento(clip) || 0);
  if (tope <= 0) return doc;
  const minDur = Math.min(MIN_RECORTE_MS, tope);
  const salida = Math.round(Math.min(Math.max(outMs, minDur), tope));
  const entrada = Math.round(Math.min(Math.max(0, inMs), salida - minDur));
  if (entrada === clip.recorte_in_ms && salida === clip.recorte_out_ms) return doc;
  const nuevos = clips.map((c, i) =>
    i === idx
      ? { ...c, recorte_in_ms: entrada, recorte_out_ms: salida, inicio_ms: 0, fin_ms: salida - entrada }
      : c,
  );
  return conSegmentosBase(doc, nuevos);
}

/**
 * DIVIDE (corta) el segmento `idx` de la pista base en su tiempo de salida local `msLocal`
 * (0..duración del segmento), produciendo dos segmentos consecutivos de la misma fuente. El
 * punto de corte en la fuente es `recorte_in + msLocal`. Si alguna mitad quedaría por debajo de
 * `MIN_RECORTE_MS`, no corta (devuelve el MISMO objeto). La duración total no cambia.
 */
export function dividirClipBase(doc: ComposicionVideo, idx: number, msLocal: number): ComposicionVideo {
  const clips = segmentosBase(doc);
  const c = clips[idx];
  if (!c) return doc;
  const inn = c.recorte_in_ms ?? 0;
  const out = c.recorte_out_ms || c.fin_ms || 0;
  const corte = Math.round(inn + msLocal);
  if (corte - inn < MIN_RECORTE_MS || out - corte < MIN_RECORTE_MS) return doc;
  const izq: ClipVideo = { ...c, id: nuevoId("c"), recorte_in_ms: inn, recorte_out_ms: corte, inicio_ms: 0, fin_ms: corte - inn };
  const der: ClipVideo = { ...c, id: nuevoId("c"), recorte_in_ms: corte, recorte_out_ms: out, inicio_ms: 0, fin_ms: out - corte };
  const nuevos = [...clips.slice(0, idx), izq, der, ...clips.slice(idx + 1)];
  return conSegmentosBase(doc, nuevos);
}

/** Elimina el segmento `idx` de la pista base (conserva al menos uno). */
export function quitarSegmentoBase(doc: ComposicionVideo, idx: number): ComposicionVideo {
  const clips = segmentosBase(doc);
  if (clips.length <= 1 || idx < 0 || idx >= clips.length) return doc;
  return conSegmentosBase(doc, clips.filter((_, i) => i !== idx));
}

/** Reordena el segmento `idx` a la posición `destino` (clamp); útil para arrastrar segmentos. */
export function moverSegmentoBase(doc: ComposicionVideo, idx: number, destino: number): ComposicionVideo {
  const clips = segmentosBase(doc);
  const dest = Math.min(Math.max(0, destino), clips.length - 1);
  if (idx < 0 || idx >= clips.length || idx === dest) return doc;
  const copia = [...clips];
  const [m] = copia.splice(idx, 1);
  copia.splice(dest, 0, m);
  return conSegmentosBase(doc, copia);
}

/** Actualiza el reencuadre (ajuste/foco) del clip base. */
export function setReencuadreBase(
  doc: ComposicionVideo,
  cambios: Partial<Pick<ClipVideo, "ajuste" | "foco">>,
): ComposicionVideo {
  return {
    ...doc,
    pistas: doc.pistas.map((p) =>
      p.tipo === "video" && p.id === "base"
        ? { ...p, clips: p.clips.map((c) => ({ ...c, ...cambios })) }
        : p,
    ),
  };
}

/** Fija (o reemplaza) el clip de la pista PiP con una caja por defecto (esquina inf-der). */
export function setClipPip(
  doc: ComposicionVideo,
  mediaId: string,
  duracionMs: number,
): ComposicionVideo {
  const w = Math.round(doc.formato.w * 0.34);
  const h = Math.round(w * (9 / 16));
  const clip: ClipVideo = {
    id: nuevoId("p"),
    media_id: mediaId,
    inicio_ms: 0,
    fin_ms: duracionMs,
    recorte_in_ms: 0,
    recorte_out_ms: duracionMs,
    x: doc.formato.w - w - 40,
    y: doc.formato.h - h - 40,
    w,
    h,
    ajuste: "cover",
    foco: [0.5, 0.5],
  };
  return {
    ...doc,
    pistas: doc.pistas.map((p) => (p.tipo === "video" && p.id === "pip" ? { ...p, clips: [clip] } : p)),
  };
}

/** Lado mínimo (px del lienzo) de la ventana PiP. */
export const MIN_PIP_PX = 80;

/**
 * Mueve/redimensiona la ventana PiP: clamp dentro del lienzo, lado mínimo `MIN_PIP_PX` y
 * redondeo a px enteros (el documento viaja al render server-side; sin decimales de gestos).
 * Sin clip PiP o sin cambio real devuelve el MISMO objeto (los autoguardados comparan por
 * referencia, igual que `setRecorteBase`).
 */
export function setCajaPip(
  doc: ComposicionVideo,
  caja: Partial<Pick<ClipVideo, "x" | "y" | "w" | "h">>,
): ComposicionVideo {
  const clip = pistaPip(doc)?.clips[0];
  if (!clip) return doc;
  const w = Math.round(Math.max(MIN_PIP_PX, Math.min(caja.w ?? clip.w, doc.formato.w)));
  const h = Math.round(Math.max(MIN_PIP_PX, Math.min(caja.h ?? clip.h, doc.formato.h)));
  const x = Math.round(Math.max(0, Math.min(caja.x ?? clip.x, doc.formato.w - w)));
  const y = Math.round(Math.max(0, Math.min(caja.y ?? clip.y, doc.formato.h - h)));
  if (x === clip.x && y === clip.y && w === clip.w && h === clip.h) return doc;
  return {
    ...doc,
    pistas: doc.pistas.map((p) =>
      p.tipo === "video" && p.id === "pip"
        ? { ...p, clips: p.clips.map((c, i) => (i === 0 ? { ...c, x, y, w, h } : c)) }
        : p,
    ),
  };
}

/** Quita el clip PiP (deja la pista vacía). */
export function quitarPip(doc: ComposicionVideo): ComposicionVideo {
  return {
    ...doc,
    pistas: doc.pistas.map((p) => (p.tipo === "video" && p.id === "pip" ? { ...p, clips: [] } : p)),
  };
}

/**
 * Fija el recorte temporal del clip PiP (`recorte_in_ms`/`recorte_out_ms`), igual que el base
 * pero para la ventana PiP. Clampa a `[0, maxMs]` con mínimo `MIN_RECORTE_MS`. Sin clip PiP o sin
 * cambio real devuelve el MISMO objeto (autoguardado por referencia).
 */
export function setRecortePip(
  doc: ComposicionVideo,
  inMs: number,
  outMs: number,
  maxMs?: number,
): ComposicionVideo {
  const clip = pistaPip(doc)?.clips[0];
  if (!clip) return doc;
  const tope =
    maxMs && maxMs > 0 ? maxMs : Math.max(clip.recorte_out_ms || 0, clip.fin_ms || 0);
  if (tope <= 0) return doc;
  const minDur = Math.min(MIN_RECORTE_MS, tope);
  const salida = Math.round(Math.min(Math.max(outMs, minDur), tope));
  const entrada = Math.round(Math.min(Math.max(0, inMs), salida - minDur));
  if (entrada === clip.recorte_in_ms && salida === clip.recorte_out_ms) return doc;
  return {
    ...doc,
    pistas: doc.pistas.map((p) =>
      p.tipo === "video" && p.id === "pip"
        ? { ...p, clips: p.clips.map((c, i) => (i === 0 ? { ...c, recorte_in_ms: entrada, recorte_out_ms: salida } : c)) }
        : p,
    ),
  };
}

/** Reemplaza las capas de la pista overlay (lo emite el editor de capas). */
export function setCapasOverlay(doc: ComposicionVideo, capas: Capa[]): ComposicionVideo {
  return {
    ...doc,
    pistas: doc.pistas.map((p) => (p.tipo === "overlay" ? { ...p, capas } : p)),
  };
}

// --------------------------------------------------------------------------- #
// Audio: silenciar/volumen del audio del clip base + pista de música           #
// --------------------------------------------------------------------------- #

/** Volumen por defecto (0..1) de un clip cuando no declara `volumen`. */
export const VOLUMEN_DEFECTO = 1;

/** Aplica `cambios` (volumen/silenciar) a TODOS los segmentos de la pista base (su audio). */
export function setAudioBase(
  doc: ComposicionVideo,
  cambios: { volumen?: number; silenciar?: boolean },
): ComposicionVideo {
  const clips = segmentosBase(doc);
  if (clips.length === 0) return doc;
  const vol = cambios.volumen != null ? Math.min(1, Math.max(0, cambios.volumen)) : undefined;
  return {
    ...doc,
    pistas: doc.pistas.map((p) =>
      p.tipo === "video" && p.id === "base"
        ? {
            ...p,
            clips: p.clips.map((c) => ({
              ...c,
              ...(vol != null ? { volumen: vol } : {}),
              ...(cambios.silenciar != null ? { silenciar: cambios.silenciar } : {}),
            })),
          }
        : p,
    ),
  };
}

/** Devuelve `pistas` garantizando que existe la pista `audio` (la añade en docs v1). */
function conPistaAudio(doc: ComposicionVideo): PistaComposicion[] {
  if (doc.pistas.some((p) => p.tipo === "audio")) return doc.pistas;
  return [...doc.pistas, { id: "audio", tipo: "audio", clips: [] } as PistaAudio];
}

/** Fija (o reemplaza) la música de la composición: un único clip de audio en la pista `audio`. */
export function setMusica(doc: ComposicionVideo, mediaId: string, duracionMs: number): ComposicionVideo {
  const clip: ClipAudio = {
    id: nuevoId("a"),
    media_id: mediaId,
    inicio_ms: 0,
    fin_ms: duracionMs,
    recorte_in_ms: 0,
    recorte_out_ms: duracionMs,
    offset_ms: 0,
    volumen: VOLUMEN_DEFECTO,
    silenciar: false,
  };
  return {
    ...doc,
    pistas: conPistaAudio(doc).map((p) => (p.tipo === "audio" ? { ...p, clips: [clip] } : p)),
  };
}

/** Cambia volumen/silenciar del primer clip de música. Sin música no hace nada. */
export function setVolumenMusica(
  doc: ComposicionVideo,
  cambios: { volumen?: number; silenciar?: boolean },
): ComposicionVideo {
  const pista = pistaAudio(doc);
  if (!pista || pista.clips.length === 0) return doc;
  const vol = cambios.volumen != null ? Math.min(1, Math.max(0, cambios.volumen)) : undefined;
  return {
    ...doc,
    pistas: doc.pistas.map((p) =>
      p.tipo === "audio"
        ? {
            ...p,
            clips: p.clips.map((c, i) =>
              i === 0
                ? {
                    ...c,
                    ...(vol != null ? { volumen: vol } : {}),
                    ...(cambios.silenciar != null ? { silenciar: cambios.silenciar } : {}),
                  }
                : c,
            ),
          }
        : p,
    ),
  };
}

/** Quita la música (deja la pista de audio vacía). */
export function quitarMusica(doc: ComposicionVideo): ComposicionVideo {
  if (!pistaAudio(doc)) return doc;
  return {
    ...doc,
    pistas: doc.pistas.map((p) => (p.tipo === "audio" ? { ...p, clips: [] } : p)),
  };
}

/** Fija los fundidos de entrada/salida (ms) del primer clip de música. Sin música, no hace nada. */
export function setFadeMusica(
  doc: ComposicionVideo,
  cambios: { fade_in_ms?: number; fade_out_ms?: number },
): ComposicionVideo {
  const pista = pistaAudio(doc);
  if (!pista || pista.clips.length === 0) return doc;
  const inn = cambios.fade_in_ms != null ? Math.max(0, Math.round(cambios.fade_in_ms)) : undefined;
  const out = cambios.fade_out_ms != null ? Math.max(0, Math.round(cambios.fade_out_ms)) : undefined;
  return {
    ...doc,
    pistas: doc.pistas.map((p) =>
      p.tipo === "audio"
        ? {
            ...p,
            clips: p.clips.map((c, i) =>
              i === 0
                ? { ...c, ...(inn != null ? { fade_in_ms: inn } : {}), ...(out != null ? { fade_out_ms: out } : {}) }
                : c,
            ),
          }
        : p,
    ),
  };
}

// --------------------------------------------------------------------------- #
// Marcadores de la línea de tiempo (tiempo de SALIDA)                          #
// --------------------------------------------------------------------------- #

/** Marcadores de la composición (vacío si no trae). */
export function marcadores(doc: ComposicionVideo): Marcador[] {
  return doc.marcadores ?? [];
}

/** Añade un marcador en `ms` (tiempo de salida), ordenado por tiempo. */
export function agregarMarcador(doc: ComposicionVideo, ms: number, etiqueta?: string): ComposicionVideo {
  const m: Marcador = { id: nuevoId("m"), ms: Math.max(0, Math.round(ms)), ...(etiqueta ? { etiqueta } : {}) };
  const lista = [...marcadores(doc), m].sort((a, b) => a.ms - b.ms);
  return { ...doc, marcadores: lista };
}

/** Quita el marcador `id`. */
export function quitarMarcador(doc: ComposicionVideo, id: string): ComposicionVideo {
  const lista = marcadores(doc);
  if (!lista.some((m) => m.id === id)) return doc;
  return { ...doc, marcadores: lista.filter((m) => m.id !== id) };
}

/** Liga la pista de subtítulos a un `subtitulo_id` y/o cambia su estilo. */
export function setSubtitulos(
  doc: ComposicionVideo,
  cambios: { subtitulo_id?: string; estilo?: Partial<EstiloSubtitulos> },
): ComposicionVideo {
  return {
    ...doc,
    pistas: doc.pistas.map((p) => {
      if (p.tipo !== "subtitulos") return p;
      return {
        ...p,
        subtitulo_id: cambios.subtitulo_id ?? p.subtitulo_id,
        estilo: cambios.estilo ? { ...p.estilo, ...cambios.estilo } : p.estilo,
      };
    }),
  };
}

// --------------------------------------------------------------------------- #
// Subtítulos: segmentos word-level del ASR (contrato §1 / §4.2)                #
// --------------------------------------------------------------------------- #

/** Una palabra con sus tiempos (salida word-level de faster-whisper). */
export interface PalabraSub {
  inicio: number; // segundos
  fin: number; // segundos
  texto: string;
}

/** Un segmento (línea) de subtítulo: texto editable + tiempos + palabras opcionales. */
export interface SegmentoSub {
  id: string;
  inicio: number; // segundos
  fin: number; // segundos
  texto: string;
  palabras?: PalabraSub[];
}

/** Estado del recurso de subtítulos (espejo de `video_subtitulos.estado`). */
export type EstadoSubtitulos = "pendiente" | "transcrito" | "editado" | "listo";

/**
 * Estado de un BORRADOR de composición (espejo de `video_composiciones.estado`). Es organización,
 * NO publicación: "listo" sólo marca que el humano dio por terminada la edición. Default "borrador".
 */
export type EstadoComposicion = "borrador" | "listo";

export const ESTADO_COMPOSICION_DEFECTO: EstadoComposicion = "borrador";

export const ETIQUETA_ESTADO_COMPOSICION: Record<EstadoComposicion, string> = {
  borrador: "Borrador",
  listo: "Listo",
};

/**
 * Resumen de una composición tal como lo sirve `GET /api/video/composiciones` (listado).
 * `documento` viene YA parseado a objeto por el backend (`_composicion_a_dict`). `marca_nombre`
 * es la etiqueta legible de la marca. `titulo`/`estado` son del borrador (def "" / "borrador").
 * Se usa en el GESTOR de composiciones.
 */
export interface ComposicionResumen {
  id: string;
  publicacion_id: string;
  marca: string;
  marca_nombre: string;
  titulo: string;
  estado: EstadoComposicion;
  documento: ComposicionVideo;
  creado: string;
  actualizado: string;
}

/**
 * Deriva un título por defecto para un borrador sin nombre, a partir del aspecto y la fecha.
 * P.ej. "Borrador 9:16 · 07/06/26".
 */
export function tituloBorradorPorDefecto(aspecto: string, fecha = new Date()): string {
  const f = fecha.toLocaleDateString("es-MX", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
  });
  return `Borrador ${aspecto} · ${f}`;
}

/** Recurso de subtítulos tal como lo sirve `GET /api/video/subtitulos/{id}`. */
export interface Subtitulo {
  id: string;
  composicion_id: string;
  idioma: string;
  estado: EstadoSubtitulos | string;
  segmentos: SegmentoSub[];
  ass?: string;
  transcrito_en?: string;
  actualizado?: string;
}

/**
 * Normaliza los segmentos crudos del backend a `SegmentoSub[]`. El ASR puede entregar
 * `start`/`end`/`text` (faster-whisper) o ya el español `inicio`/`fin`/`texto`; aceptamos
 * ambos y garantizamos un `id` estable por índice. Defensivo ante campos ausentes.
 */
export function normalizarSegmentos(crudos: unknown): SegmentoSub[] {
  if (!Array.isArray(crudos)) return [];
  return crudos.map((s, i) => {
    const o = (s ?? {}) as Record<string, unknown>;
    const inicio = Number(o.inicio ?? o.start ?? 0) || 0;
    const fin = Number(o.fin ?? o.end ?? 0) || 0;
    const texto = String(o.texto ?? o.text ?? "").trim();
    const palabrasCrudas = o.palabras ?? o.words;
    const palabras = Array.isArray(palabrasCrudas)
      ? palabrasCrudas.map((w) => {
          const wo = (w ?? {}) as Record<string, unknown>;
          return {
            inicio: Number(wo.inicio ?? wo.start ?? 0) || 0,
            fin: Number(wo.fin ?? wo.end ?? 0) || 0,
            texto: String(wo.texto ?? wo.word ?? wo.text ?? ""),
          } as PalabraSub;
        })
      : undefined;
    return {
      id: String(o.id ?? `seg-${i}`),
      inicio,
      fin,
      texto,
      ...(palabras ? { palabras } : {}),
    } as SegmentoSub;
  });
}

/** Formatea segundos a `mm:ss.s` para mostrar tiempos de segmento. */
export function formatearTiempo(seg: number): string {
  if (!Number.isFinite(seg) || seg < 0) seg = 0;
  const m = Math.floor(seg / 60);
  const s = seg - m * 60;
  return `${String(m).padStart(2, "0")}:${s.toFixed(1).padStart(4, "0")}`;
}

/** Segmento activo en `t` segundos (para resaltarlo en el preview), o null. */
export function segmentoEn(segmentos: SegmentoSub[], t: number): SegmentoSub | null {
  return segmentos.find((s) => t >= s.inicio && t <= s.fin) ?? null;
}

/**
 * Formatea milisegundos a `mm:ss` (reloj del player y duraciones de clip/composición).
 * Valores no finitos o negativos se tratan como 0.
 */
export function formatearDuracionMs(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) ms = 0;
  const total = Math.floor(ms / 1000);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}
