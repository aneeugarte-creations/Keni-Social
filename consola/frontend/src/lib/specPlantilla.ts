/**
 * Tipos del SPEC de plantilla de marca (espejo de `motores/estudio_imagen/spec_plantilla.py`).
 *
 * El editor lee/edita este spec y el SERVIDOR lo renderiza idéntico (única fuente de verdad de
 * píxeles). Coordenadas en px sobre el lienzo de cada formato. NO se renderiza en el navegador:
 * la "vista real" la sirve el endpoint de preview con el mismo motor que produce las placas.
 */

export type FormatoId = "vertical" | "feed" | "cuadrado";
export type Ajuste = "cover" | "contain";
export type Alineacion = "izquierda" | "centro" | "derecha";
export type FamiliaLogica = "sans" | "condensada";
export type BindingTexto = "copy_in" | "etiqueta_default" | null;

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
