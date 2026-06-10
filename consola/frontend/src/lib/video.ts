// Tipos y helpers PUROS del motor de edición de video (Ola VIDEO, "toque RRSS").
//
// Espejo del CONTRATO de `docs/maquina-contenido/G-video-engine.md` y del validador de
// `keni-shared/src/keni_shared/video.py`. El frontend edita el `documento` de composición en
// local y lo manda al backend (`POST /api/video/composiciones` + `PUT`), que lo re-valida y lo
// renderiza server-side con FFmpeg. Este fichero NO renderiza nada: solo construye/serializa el
// documento y normaliza los segmentos de subtítulos.
//
// Mantener sincronizado con el esquema Python (la fuente de verdad es el validador). Cualquier
// campo nuevo del sobre debe existir en ambos lados.

import type { Capa } from "@/editor/documento";

export const VERSION_COMPOSICION = 1;

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
}

export interface PistaVideo {
  id: string; // "base" | "pip"
  tipo: "video";
  clips: ClipVideo[];
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

export type PistaComposicion = PistaVideo | PistaOverlay | PistaSubtitulos;

export interface FormatoComposicion {
  w: number;
  h: number;
  fps: number;
  preset: string;
}

export interface ComposicionVideo {
  version: number;
  marca: string;
  formato: FormatoComposicion;
  duracion_ms: number;
  pistas: PistaComposicion[];
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

/** Duración mínima (ms) que debe conservar el clip base tras un trim. */
export const MIN_RECORTE_MS = 1000;

/**
 * Fija el recorte temporal del clip BASE (`recorte_in_ms`/`recorte_out_ms`), que el render
 * server-side aplica con `-ss`/`-to` antes del input de FFmpeg
 * (`motores/estudio_video/filtros.py::construir_comando`). Clampa a `[0, maxMs]` (la duración
 * real del clip, si se conoce) y garantiza un mínimo de `MIN_RECORTE_MS` (clips más cortos:
 * todo el clip). Recalcula `fin_ms` del clip y `duracion_ms` del documento (= duración
 * recortada; el worker la usa para el % de progreso del render). Sin clip base o sin cambio
 * real devuelve el MISMO objeto (los autoguardados comparan por referencia).
 */
export function setRecorteBase(
  doc: ComposicionVideo,
  inMs: number,
  outMs: number,
  maxMs?: number,
): ComposicionVideo {
  const clip = pistaBase(doc)?.clips[0];
  if (!clip) return doc;
  const tope =
    maxMs && maxMs > 0
      ? maxMs
      : Math.max(clip.recorte_out_ms || 0, clip.fin_ms || 0, doc.duracion_ms || 0);
  if (tope <= 0) return doc;
  const minDur = Math.min(MIN_RECORTE_MS, tope);
  const salida = Math.round(Math.min(Math.max(outMs, minDur), tope));
  const entrada = Math.round(Math.min(Math.max(0, inMs), salida - minDur));
  if (entrada === clip.recorte_in_ms && salida === clip.recorte_out_ms) return doc;
  const dur = salida - entrada;
  return {
    ...doc,
    duracion_ms: dur,
    pistas: doc.pistas.map((p) =>
      p.tipo === "video" && p.id === "base"
        ? {
            ...p,
            clips: p.clips.map((c, i) =>
              i === 0
                ? { ...c, recorte_in_ms: entrada, recorte_out_ms: salida, fin_ms: c.inicio_ms + dur }
                : c,
            ),
          }
        : p,
    ),
  };
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

/** Reemplaza las capas de la pista overlay (lo emite el editor de capas). */
export function setCapasOverlay(doc: ComposicionVideo, capas: Capa[]): ComposicionVideo {
  return {
    ...doc,
    pistas: doc.pistas.map((p) => (p.tipo === "overlay" ? { ...p, capas } : p)),
  };
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
  contenido_id: string;
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
