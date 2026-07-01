// Pesos REALES que carga cada familia del catálogo (espejo de las webfonts de `index.html`, que a
// su vez calcan las caras que Skia registra en el servidor). El selector de «Peso» las usa para
// ATENUAR los pesos que la familia no tiene (patrón Canva): elegir «Ligera (300)» en una familia
// que solo trae 400/600/700 caería silenciosamente a la cara más cercana, sin avisar.
//
// Las familias que faltan aquí (o los pesos lógicos legados "sans"/"condensada") resuelven vía
// `familiaReal` antes de consultar el mapa; una familia desconocida se trata como sin restricción
// (todos los pesos disponibles), para no bloquear tipografías propias de marca añadidas en runtime.

import { familiaReal } from "./tipografia";

// Peso -> lista de caras ESTÁTICAS que la familia embebe. Derivado del `<link>` de Google Fonts de
// `index.html` (`wght@…`). Barlow/Barlow Condensed son las familias por defecto (sans/condensada).
const PESOS_POR_FAMILIA: Record<string, number[]> = {
  Barlow: [400, 600, 700],
  "Barlow Condensed": [600, 700, 800],
  Anton: [400],
  Oswald: [300, 400, 500, 600, 700],
  Montserrat: [300, 400, 500, 600, 700, 800, 900],
  "Archivo Black": [400],
  Lora: [400, 700],
  "Exo 2": [400, 600, 700, 800],
  Lato: [400, 700, 900],
  Poppins: [300, 400, 500, 600, 700, 800, 900],
  "Roboto Condensed": [300, 400, 700],
  Mulish: [400, 700, 800],
  "Nunito Sans": [400, 700, 900],
  Jost: [300, 400, 500, 600, 700, 800, 900],
};

/**
 * Pesos que carga `familia` como caras reales, o `null` si la familia no está en el mapa (fuente de
 * marca u otra desconocida: sin restricción, todos los pesos disponibles). Resuelve antes las
 * familias lógicas legadas ("sans"/"condensada") a su fuente real.
 */
export function pesosDisponibles(familia: string | undefined): number[] | null {
  return PESOS_POR_FAMILIA[familiaReal(familia)] ?? null;
}

/**
 * ¿La familia embebe una cara para `peso`? `true` si la familia es desconocida (sin restricción) o
 * si el peso está entre sus caras reales. `false` solo cuando SABEMOS que ese peso no existe y el
 * navegador/Skia lo resolverían a otra cara.
 */
export function pesoDisponible(familia: string | undefined, peso: number): boolean {
  const pesos = pesosDisponibles(familia);
  return pesos === null || pesos.includes(peso);
}
