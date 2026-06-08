// Constantes, helpers de geometría/matemática y preferencias persistidas del Lienzo.

import type { Capa } from "../documento";

export const RATIO_FIJO = new Set<Capa["tipo"]>(["imagen", "logo"]);
export const ZOOM_MIN = 0.2;
export const ZOOM_MAX = 4;

// Portapapeles de capas (módulo, para copiar/pegar incluso entre pestañas del workspace). Guarda
// TODA la selección múltiple, no solo la capa primaria.
export const portapapeles: { capas: Capa[] } = { capas: [] };

// Tamaños de celda de la rejilla ofrecidos en los controles (px del documento). "Fina" por defecto.
export const CELDAS: { px: number; etiqueta: string }[] = [
  { px: 8, etiqueta: "8" },
  { px: 16, etiqueta: "16" },
  { px: 24, etiqueta: "24" },
  { px: 32, etiqueta: "32" },
  { px: 48, etiqueta: "48" },
];

// Preferencias de los toggles de encuadre (imán/rejilla/tamaño/dentro-del-marco) en localStorage.
// Tolerante: si no hay localStorage o el valor es inválido, cae al default.
export function prefBool(clave: string, def: boolean): boolean {
  try {
    const v = localStorage.getItem(clave);
    return v === null ? def : v === "1";
  } catch {
    return def;
  }
}
export function prefNum(clave: string, def: number): number {
  try {
    const v = localStorage.getItem(clave);
    const n = v === null ? NaN : Number(v);
    return Number.isFinite(n) ? n : def;
  } catch {
    return def;
  }
}
export function guardarPref(clave: string, valor: boolean | number): void {
  try {
    localStorage.setItem(clave, typeof valor === "boolean" ? (valor ? "1" : "0") : String(valor));
  } catch {
    /* almacenamiento no disponible: las preferencias no se persisten, sin romper. */
  }
}

// Acota una posición de un eje para que la caja [pos, pos+tam] quede dentro de [0, total]. Si la
// caja es MAYOR que el lienzo (tam > total) no se fuerzan negativos absurdos: se permite el rango
// [total - tam, 0] (la capa puede sobresalir por igual a ambos lados, centrable a mano).
export function clampMarco(pos: number, tam: number, total: number): number {
  const min = Math.min(0, total - tam);
  const max = Math.max(0, total - tam);
  return Math.max(min, Math.min(max, pos));
}
