// Catálogo de FORMATOS de lienzo (presets de red/plataforma) compartido por el editor.
//
// Antes vivía duplicado en `Paneles.tsx` (selector de aspect-ratio del inspector). Lo extraemos
// aquí para que tanto el inspector como «Adaptar a…» (reencuadre 1-clic) usen la MISMA lista, sin
// derivas. Cada preset es un `formato` del Documento (w, h, safe_top, safe_bottom).

import type { Documento } from "./documento";

export type Formato = Documento["formato"];

export interface PresetFormato {
  // Etiqueta corta para botones compactos (ratio): "9:16", "4:5"…
  etiqueta: string;
  // Nombre legible de la red/uso, para menús: "Story / Reel (9:16)".
  nombre: string;
  f: Formato;
}

// Presets ordenados por uso. Las zonas seguras (safe_top/safe_bottom) son las que ya usaba el
// inspector; el adaptador las respeta al recolocar texto.
export const PRESETS_FORMATO: PresetFormato[] = [
  { etiqueta: "9:16", nombre: "Story / Reel (9:16)", f: { w: 1080, h: 1920, safe_top: 220, safe_bottom: 420 } },
  { etiqueta: "4:5", nombre: "Feed vertical (4:5)", f: { w: 1080, h: 1350, safe_top: 60, safe_bottom: 96 } },
  { etiqueta: "1:1", nombre: "Feed cuadrado (1:1)", f: { w: 1080, h: 1080, safe_top: 60, safe_bottom: 96 } },
  { etiqueta: "16:9", nombre: "Horizontal / X (16:9)", f: { w: 1600, h: 900, safe_top: 56, safe_bottom: 72 } },
];

// ¿Dos formatos comparten dimensiones (mismo lienzo)? Para marcar el preset activo.
export function mismoFormato(a: Formato, b: Formato): boolean {
  return a.w === b.w && a.h === b.h;
}
