// Constantes, helpers de geometría/matemática y preferencias persistidas del Lienzo.

import type { Capa } from "../documento";

export const RATIO_FIJO = new Set<Capa["tipo"]>(["imagen", "logo"]);
export const ZOOM_MIN = 0.2;
export const ZOOM_MAX = 4;

// Límites de la ESCALA EFECTIVA (px del documento : px de pantalla), estilo Canva: el zoom relativo
// al fit (ZOOM_MIN/ZOOM_MAX) por sí solo no garantiza poder llegar al 100% real ni a los niveles
// del menú cuando el documento es grande y el fit pequeño (p. ej. una story en un portátil).
export const ESCALA_MIN = 0.1; // 10%
export const ESCALA_MAX = 3; // 300%

// Niveles del menú de zoom (fracción de escala efectiva => 10/25/50/75/100/125/200/300 %).
export const PASOS_ZOOM: number[] = [0.1, 0.25, 0.5, 0.75, 1, 1.25, 2, 3];

// Acota el factor de zoom (relativo al fit) de forma que la escala efectiva (zoom * baseFit) pueda
// SIEMPRE alcanzar [ESCALA_MIN, ESCALA_MAX], sin recortar el rango relativo clásico cuando éste es
// más amplio. Así "300%" del menú es alcanzable aunque el fit sea pequeño.
export function clampZoom(zoom: number, baseFit: number): number {
  const fit = Math.max(baseFit, 1e-6);
  const min = Math.min(ZOOM_MIN, ESCALA_MIN / fit);
  const max = Math.max(ZOOM_MAX, ESCALA_MAX / fit);
  return Math.max(min, Math.min(max, zoom));
}

// Etiquetas VIVAS de gesto (estilo Canva): texto del rótulo flotante durante resize/rotación.
// Dimensiones en píxeles del DOCUMENTO (no de pantalla), redondeadas.
export function etiquetaTamano(w: number, h: number): string {
  return `${Math.round(w)} × ${Math.round(h)} px`;
}

// Grados normalizados a [0, 360) — así "-10°" se lee como 350° y 370° como 10°.
export function etiquetaGrados(grados: number): string {
  return `${((Math.round(grados) % 360) + 360) % 360}°`;
}

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
