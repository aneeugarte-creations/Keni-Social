// Tipos del DOCUMENTO de capas del editor profesional — espejo de
// `motores/estudio_imagen/documento.py`. El editor (react-konva) edita estos objetos en local
// y el servidor los re-renderiza con el MISMO dibujante (`render_node/dibujar.mjs`).
//
// Mantener sincronizado con el esquema Python: cualquier campo nuevo debe existir en ambos lados
// (el validador Python es la fuente de verdad; este fichero es el contrato del cliente).

export const VERSION = 1;

export type TipoCapa = "imagen" | "texto" | "logo" | "marco" | "overlay" | "grupo";
export type Ajuste = "cover" | "contain";
export type Alineacion = "izquierda" | "centro" | "derecha" | "justificado";
export type FormaMarco = "rect" | "elipse" | "linea";
export type BindingTexto = "copy_in" | "etiqueta_default" | null;

// Rol de un texto en la plantilla: qué dato de la pieza lo rellena al aplicarla. `null` = texto fijo.
export const ETIQUETA_BINDING: Record<"fijo" | "copy_in" | "etiqueta_default", string> = {
  fijo: "Texto fijo",
  copy_in: "Titular (copy)",
  etiqueta_default: "Pleca / etiqueta",
};

export interface Fondo {
  tipo: "color" | "degradado" | "imagen";
  color?: string;
  degradado?: { desde: string; hasta: string; angulo?: number };
  imagen?: { media_id: string; ajuste?: Ajuste };
}

export interface CapaBase {
  id: string;
  tipo: TipoCapa;
  nombre?: string; // etiqueta editable en el panel de capas (el render la ignora)
  x: number;
  y: number;
  w: number;
  h: number;
  rotacion: number;
  opacidad: number; // 0..1
  z: number;
  visible: boolean;
  bloqueada: boolean;
}

export interface Filtros {
  brillo?: number; // 1 = neutro
  contraste?: number;
  saturacion?: number;
  desenfoque?: number; // px
}

export interface CapaImagen extends CapaBase {
  tipo: "imagen";
  objeto: string; // id de media ("" = vacío/placeholder)
  ajuste: Ajuste;
  foco: [number, number];
  zoom: number; // reencuadre dentro del marco (1 = ajuste base)
  filtros: Filtros | null;
}

export interface Sombra {
  dx: number;
  dy: number;
  color: string;
}
export interface Chip {
  color: string;
  pad_x: number;
  pad_y: number;
  radio: number;
}
export interface Contorno {
  color: string;
  grosor: number;
}

export interface CapaTexto extends CapaBase {
  tipo: "texto";
  texto: string;
  binding: BindingTexto;
  familia: string;
  tamano: number;
  peso: number;
  color: string;
  alineacion: Alineacion;
  mayusculas: boolean;
  interlineado: number;
  interletra: number; // letter-spacing en px
  auto_ajuste: { max_lineas: number; tam_min: number };
  sombra: Sombra | null;
  contorno: Contorno | null;
  chip: Chip | null;
  ancla: "arriba" | "abajo";
}

export interface CapaLogo extends CapaBase {
  tipo: "logo";
  tipo_logo: "imagen" | "wordmark";
  media_id: string;
  wordmark: { texto: string; color: string; fondo: string; familia: string; peso: number };
}

export interface CapaMarco extends CapaBase {
  tipo: "marco";
  forma: FormaMarco;
  relleno: string | null;
  borde: { color: string; grosor: number } | null;
  radio: number;
}

export interface CapaOverlay extends CapaBase {
  tipo: "overlay";
  color: string;
  alto_frac: number;
  alpha: number;
}

export interface CapaGrupo extends CapaBase {
  tipo: "grupo";
  capas: Capa[];
}

export type Capa = CapaImagen | CapaTexto | CapaLogo | CapaMarco | CapaOverlay | CapaGrupo;

export interface Documento {
  version: number;
  marca: string;
  fuentes: { sans: string; condensada: string };
  formato: { w: number; h: number; safe_top: number; safe_bottom: number };
  fondo: Fondo;
  capas: Capa[];
}

// Catálogo de fuentes embebidas ofrecidas por el editor (espejo de `fuentes.mjs::CATALOGO` y
// `spec_plantilla.CATALOGO_FUENTES`). Las tipografías propias por marca (frente D) se añaden en runtime.
export const CATALOGO_FUENTES = [
  "Barlow",
  "Barlow Condensed",
  "Anton",
  "Oswald",
  "Montserrat",
  "Archivo Black",
  "Lora",
  "Exo 2",
  "Lato",
] as const;

// ---------------------------------------------------------------------------
// Factories — nuevas capas con valores por defecto razonables.
// ---------------------------------------------------------------------------

let _seq = 0;
function nuevoId(prefijo: string): string {
  _seq += 1;
  return `${prefijo}-${Date.now().toString(36)}-${_seq}`;
}

function base(tipo: TipoCapa, x: number, y: number, w: number, h: number, z: number): CapaBase {
  return { id: nuevoId(tipo), tipo, x, y, w, h, rotacion: 0, opacidad: 1, z, visible: true, bloqueada: false };
}

export function nuevaCapaTexto(parcial: Partial<CapaTexto> = {}): CapaTexto {
  return {
    ...base("texto", 80, 80, 600, 0, 20),
    tipo: "texto",
    texto: "Texto",
    binding: null,
    familia: "Barlow",
    tamano: 64,
    peso: 700,
    color: "#FFFFFF",
    alineacion: "izquierda",
    mayusculas: false,
    interlineado: 1.14,
    interletra: 0,
    auto_ajuste: { max_lineas: 4, tam_min: 40 },
    sombra: null,
    contorno: null,
    chip: null,
    ancla: "arriba",
    ...parcial,
  };
}

export function nuevaCapaImagen(objeto: string, parcial: Partial<CapaImagen> = {}): CapaImagen {
  return {
    ...base("imagen", 0, 0, 1080, 1080, 0),
    tipo: "imagen",
    objeto,
    ajuste: "cover",
    foco: [0.5, 0.5],
    zoom: 1,
    filtros: null,
    ...parcial,
  };
}

export function nuevaCapaMarco(parcial: Partial<CapaMarco> = {}): CapaMarco {
  return {
    ...base("marco", 80, 80, 400, 240, 15),
    tipo: "marco",
    forma: "rect",
    relleno: null,
    borde: { color: "#FFFFFF", grosor: 6 },
    radio: 0,
    ...parcial,
  };
}

export function nuevaCapaLogo(media_id: string, parcial: Partial<CapaLogo> = {}): CapaLogo {
  return {
    ...base("logo", 56, 56, 220, 96, 30),
    tipo: "logo",
    tipo_logo: media_id ? "imagen" : "wordmark",
    media_id,
    wordmark: { texto: "", color: "#FFFFFF", fondo: "#E30613", familia: "Barlow", peso: 700 },
    ...parcial,
  };
}

export function nuevaCapaOverlay(parcial: Partial<CapaOverlay> = {}): CapaOverlay {
  return {
    ...base("overlay", 0, 0, 1080, 1080, 10),
    tipo: "overlay",
    color: "#000000",
    alto_frac: 0.45,
    alpha: 200,
    ...parcial,
  };
}

export function documentoVacio(
  formato: { w: number; h: number; safe_top: number; safe_bottom: number },
  marca = "",
): Documento {
  return {
    version: VERSION,
    marca,
    fuentes: { sans: "Barlow", condensada: "Barlow Condensed" },
    formato,
    fondo: { tipo: "color", color: "#111315" },
    capas: [],
  };
}

// z máximo + 1, para insertar una capa nueva encima de todo.
export function zTope(doc: Documento): number {
  return doc.capas.reduce((m, c) => Math.max(m, c.z ?? 0), 0) + 1;
}
