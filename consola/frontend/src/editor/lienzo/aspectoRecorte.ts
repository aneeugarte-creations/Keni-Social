// Estado COMPARTIDO del MODO RECORTE que no cabe en el store del documento (vive en otro agente) ni
// puede pasar el Lienzo por props: la relación de aspecto FIJA elegida en el banner de recorte y de
// qué objeto se recorta (foto vs forma). Los chips del banner escriben aquí; los overlays leen la
// relación para acotar el gesto y el banner lee foto/forma para mostrar la ayuda correcta. Es un
// store de módulo (una única sesión de recorte activa a la vez, como el propio modo).

import { useStore } from "zustand";
import { createStore } from "zustand/vanilla";

import { PRESETS_FORMATO } from "../formatos";

// Relación de aspecto del recorte: `null` = LIBRE (sin acotar). Un número = ancho/alto a mantener.
export type RelacionAspecto = number | null;

// Chips del banner de recorte. "Libre" no acota; "Original" usa la proporción actual del objeto (se
// resuelve al pulsar, no es un valor fijo). El resto reusan los ratios de los formatos de plataforma.
export interface OpcionAspecto {
  clave: string; // id estable para React + comparación de activo
  etiqueta: string; // texto del chip ("1:1", "9:16"…)
  // Relación fija ancho/alto, o null para "Libre"/"Original" (este último se resuelve del objeto).
  ratio: RelacionAspecto;
  original?: boolean; // "Original": adopta la proporción del objeto en curso
}

const RATIOS_FORMATO = PRESETS_FORMATO.map((p) => ({
  clave: p.etiqueta,
  etiqueta: p.etiqueta,
  ratio: p.f.w / p.f.h,
}));

// "Libre" + presets de plataforma (1:1, 4:5, 9:16, 16:9) + "Original".
export const OPCIONES_ASPECTO: OpcionAspecto[] = [
  { clave: "libre", etiqueta: "Libre", ratio: null },
  ...RATIOS_FORMATO,
  { clave: "original", etiqueta: "Original", ratio: null, original: true },
];

interface EstadoAspecto {
  // Relación activa (null = Libre). Los overlays la leen para acotar el gesto.
  ratio: RelacionAspecto;
  clave: string; // chip activo
  // Objeto en recorte: los chips y el banner adaptan su comportamiento (foto reencuadra, forma
  // encoge el recuadro). null cuando no hay modo recorte activo.
  esImagen: boolean | null;
  fijar: (clave: string, ratio: RelacionAspecto) => void;
  // Al entrar al modo recorte: registra el tipo de objeto y reinicia la relación a Libre.
  iniciar: (esImagen: boolean) => void;
  limpiar: () => void;
}

const store = createStore<EstadoAspecto>((set) => ({
  ratio: null,
  clave: "libre",
  esImagen: null,
  fijar: (clave, ratio) => set({ clave, ratio }),
  iniciar: (esImagen) => set({ esImagen, ratio: null, clave: "libre" }),
  limpiar: () => set({ esImagen: null, ratio: null, clave: "libre" }),
}));

export const aspectoRecorteStore = store;

export function useAspectoRecorte<T>(selector: (s: EstadoAspecto) => T): T {
  return useStore(store, selector);
}
