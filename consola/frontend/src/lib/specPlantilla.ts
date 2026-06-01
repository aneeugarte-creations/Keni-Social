/**
 * Tipos del SPEC de plantilla de marca (espejo de `motores/estudio_imagen/spec_plantilla.py`).
 *
 * El editor lee/edita este spec y el SERVIDOR lo renderiza idéntico (única fuente de verdad de
 * píxeles). Coordenadas en px sobre el lienzo de cada formato. NO se renderiza en el navegador:
 * la "vista real" la sirve el endpoint de preview con el mismo motor que produce las placas.
 */

export type FormatoId = "vertical" | "feed" | "cuadrado";
export type Ajuste = "cover" | "contain";
export type Alineacion = "izquierda" | "centro" | "derecha" | "justificado";
/** La familia es un nombre del catálogo embebido (o las lógicas antiguas "sans"/"condensada"). */
export type FamiliaLogica = string;
export type BindingTexto = "copy_in" | "etiqueta_default" | null;

/** Catálogo de tipografías embebidas (SIL OFL). Debe coincidir con `render_node/fuentes.mjs`. */
export const CATALOGO_FUENTES = [
  "Barlow",
  "Barlow Condensed",
  "Anton",
  "Oswald",
  "Montserrat",
  "Archivo Black",
  "Lora",
] as const;

/** Normaliza la familia de un spec antiguo ("sans"/"condensada") al nombre real del catálogo. */
export function familiaCatalogo(familia: string): string {
  if (familia === "sans") return "Barlow";
  if (familia === "condensada") return "Barlow Condensed";
  return familia;
}

export const ALINEACIONES: { id: Alineacion; etiqueta: string }[] = [
  { id: "izquierda", etiqueta: "Izquierda" },
  { id: "centro", etiqueta: "Centrado" },
  { id: "derecha", etiqueta: "Derecha" },
  { id: "justificado", etiqueta: "Justificado" },
];

export const FORMATOS: { id: FormatoId; etiqueta: string; w: number; h: number }[] = [
  { id: "vertical", etiqueta: "9:16 (Reel/TikTok)", w: 1080, h: 1920 },
  { id: "feed", etiqueta: "4:5 (Feed)", w: 1080, h: 1350 },
  { id: "cuadrado", etiqueta: "1:1 (Cuadrado)", w: 1080, h: 1080 },
];

export interface Lienzo {
  w: number;
  h: number;
  safe_top: number;
  safe_bottom: number;
}

export interface Fondo {
  tipo: "color" | "degradado" | "imagen";
  color?: string;
  degradado?: { desde: string; hasta: string; angulo: number };
  imagen?: { media_id: string; ajuste: Ajuste };
}

export interface FotoSlot {
  x: number;
  y: number;
  w: number;
  h: number;
  ajuste: Ajuste;
  foco: [number, number];
  z: number;
}

export interface OverlayInferior {
  color: string;
  alto_frac: number;
  alpha: number;
}

export interface Wordmark {
  texto: string;
  color: string;
  fondo: string;
  familia: FamiliaLogica;
  peso: number;
}

export interface CapaLogo {
  tipo: "imagen" | "wordmark";
  media_id: string;
  wordmark: Wordmark;
  x: number;
  y: number;
  w: number;
  h: number;
  z: number;
}

export interface ChipTexto {
  color: string;
  pad_x: number;
  pad_y: number;
  radio: number;
}

export interface SombraTexto {
  dx: number;
  dy: number;
  color: string;
}

export interface CapaTexto {
  id: "titular" | "pleca" | "kicker";
  binding: BindingTexto;
  texto: string;
  x: number;
  y: number;
  w: number;
  familia: FamiliaLogica;
  tamano: number;
  peso: number;
  color: string;
  alineacion: Alineacion;
  mayusculas: boolean;
  interlineado: number;
  auto_ajuste: { max_lineas: number; tam_min: number };
  sombra: SombraTexto | null;
  chip: ChipTexto | null;
  z: number;
}

export interface FormatoSpec {
  lienzo: Lienzo;
  fondo: Fondo;
  foto_slot: FotoSlot;
  overlay_inferior: OverlayInferior | null;
  logo: CapaLogo;
  textos: CapaTexto[];
}

export interface PlantillaSpec {
  version: number;
  marca: string;
  fuentes: { sans: string; condensada: string };
  formatos: Record<FormatoId, FormatoSpec>;
}

// --- Helpers de UI (los ids del spec NO cambian; solo su rótulo visible) --------------------

export type IdTexto = CapaTexto["id"];

/** Rótulo legible de un bloque de texto (titular→Título, pleca→Etiqueta, kicker→Antetítulo). */
export function rotuloTexto(id: IdTexto): string {
  return id === "titular" ? "Título" : id === "pleca" ? "Etiqueta" : "Antetítulo";
}

/** Ids de texto que AÚN no están en un formato (para el botón "+ Texto"). */
export function idsTextoDisponibles(fmt: FormatoSpec): IdTexto[] {
  const usados = new Set(fmt.textos.map((t) => t.id));
  return (["titular", "pleca", "kicker"] as IdTexto[]).filter((i) => !usados.has(i));
}

/** Capa de texto nueva con valores razonables (centrada en horizontal, dentro del lienzo). */
export function nuevaCapaTexto(id: IdTexto, lienzo: Lienzo): CapaTexto {
  const margen = 56;
  const esTitulo = id === "titular";
  return {
    id,
    binding: id === "titular" ? "copy_in" : id === "pleca" ? "etiqueta_default" : null,
    texto: id === "kicker" ? "Antetítulo" : "",
    x: margen,
    y: Math.round(lienzo.h * (esTitulo ? 0.6 : 0.5)),
    w: lienzo.w - margen * 2,
    familia: esTitulo ? "condensada" : "sans",
    tamano: esTitulo ? 80 : id === "pleca" ? 36 : 40,
    peso: esTitulo ? 800 : 700,
    color: "#FFFFFF",
    alineacion: "izquierda",
    mayusculas: id === "pleca",
    interlineado: 1.14,
    auto_ajuste: { max_lineas: esTitulo ? 4 : 1, tam_min: esTitulo ? 40 : 28 },
    sombra: esTitulo ? { dx: 2, dy: 2, color: "#000000" } : null,
    chip: id === "pleca" ? { color: "#E30613", pad_x: 24, pad_y: 14, radio: 0 } : null,
    z: esTitulo ? 20 : id === "pleca" ? 21 : 22,
  };
}

/** Centra una caja en el lienzo (horizontal y/o vertical). Devuelve {x,y} nuevos. */
export function centrar(
  caja: { x: number; y: number; w: number; h: number },
  lienzo: Lienzo,
  eje: "h" | "v" | "ambos",
): { x: number; y: number } {
  const x = eje === "v" ? caja.x : Math.round((lienzo.w - caja.w) / 2);
  const y = eje === "h" ? caja.y : Math.round((lienzo.h - caja.h) / 2);
  return { x, y };
}
