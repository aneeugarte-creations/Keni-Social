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
// Catálogo de FORMAS compartido (marcos e imágenes). Espejo de `pathForma` en `dibujar.mjs` y de
// `_FORMAS` en `documento.py`. "rect"/"elipse" son retrocompatibles con documentos antiguos.
export type Forma = "rect" | "elipse" | "triangulo" | "rombo" | "pentagono" | "hexagono" | "estrella" | "flecha";
export const CATALOGO_FORMAS: Forma[] = [
  "rect", "elipse", "triangulo", "rombo", "pentagono", "hexagono", "estrella", "flecha",
];
export const ETIQUETA_FORMA: Record<Forma, string> = {
  rect: "Rectángulo",
  elipse: "Círculo",
  triangulo: "Triángulo",
  rombo: "Rombo",
  pentagono: "Pentágono",
  hexagono: "Hexágono",
  estrella: "Estrella",
  flecha: "Flecha",
};
// El marco además admite "linea" (un trazo recto), que no es una forma rellenable.
export type FormaMarco = Forma | "linea";
export type BindingTexto = "copy_in" | "etiqueta_default" | null;

// Modo de fusión de una capa (espejo del `MAPA_MEZCLA` de `dibujar.mjs`). La etiqueta interna es
// en español; el render la traduce a `globalCompositeOperation`. "normal" = source-over (default).
export type TipoMezcla = "normal" | "multiplicar" | "trama" | "superponer" | "aclarar" | "oscurecer";

// Etiquetas legibles de cada modo de fusión para la UI (orden del select del inspector).
export const ETIQUETA_MEZCLA: Record<TipoMezcla, string> = {
  normal: "Normal",
  multiplicar: "Multiplicar",
  trama: "Trama",
  superponer: "Superponer",
  aclarar: "Aclarar",
  oscurecer: "Oscurecer",
};

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
  mezcla?: TipoMezcla; // modo de fusión (def "normal" = source-over). Solo se persiste si != "normal".
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
  es_foto?: boolean; // ESTA capa es el hueco de foto de la plantilla (única; obligatoria en el estudio)
  forma?: Forma; // recorte de la imagen: catálogo de formas (rect def, elipse/círculo, polígonos…)
  radio?: number; // radio de esquinas redondeadas para rect, en px (def 0; ignorado si forma!=rect)
  filtros: Filtros | null;
  sombra?: Sombra | null; // sombra del rectángulo de la imagen (opcional)
}

export interface Sombra {
  dx: number;
  dy: number;
  color: string;
  desenfoque?: number; // blur px (def 0). >0 activa la sombra real del canvas.
  opacidad?: number; // 0..1 (def 1). <1 activa la sombra real del canvas.
}
// Relleno por degradado lineal (texto/marco). Sustituye al color sólido cuando está presente.
export interface RellenoDegradado {
  desde: string;
  hasta: string;
  angulo?: number; // grados (def 180 = vertical ↓). Misma convención que el fondo.
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
  relleno_degradado?: RellenoDegradado | null; // degradado del relleno (sustituye a `color`)
  contorno: Contorno | null;
  chip: Chip | null;
  ancla: "arriba" | "abajo";
  // Alineación VERTICAL del texto dentro de la CAJA (cuando `h>0`). La caja es de alto fijo e
  // inamovible: el texto se auto-encoge para caber y se posiciona arriba/centro/abajo dentro de
  // ella. `ancla` se mantiene por compatibilidad (camino legado h<=0).
  valign: "arriba" | "centro" | "abajo";
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
  relleno_degradado?: RellenoDegradado | null; // degradado del relleno (sustituye a `relleno`)
  borde: { color: string; grosor: number } | null;
  radio: number;
  sombra?: Sombra | null; // sombra de la forma del marco (opcional)
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
    valign: "centro",
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
  // Toda plantilla nace con su HUECO DE FOTO obligatorio: una imagen a sangre, marcada `es_foto`
  // y BLOQUEADA (no se puede borrar). Ahí entra la foto de la pieza al aplicar la plantilla.
  const hueco = nuevaCapaImagen("", {
    id: "foto",
    x: 0,
    y: 0,
    w: formato.w,
    h: formato.h,
    z: 0,
    es_foto: true,
    bloqueada: true,
    nombre: "Foto",
  });
  return {
    version: VERSION,
    marca,
    fuentes: { sans: "Barlow", condensada: "Barlow Condensed" },
    formato,
    fondo: { tipo: "color", color: "#111315" },
    capas: [hueco],
  };
}

// z máximo + 1, para insertar una capa nueva encima de todo.
export function zTope(doc: Documento): number {
  return doc.capas.reduce((m, c) => Math.max(m, c.z ?? 0), 0) + 1;
}
