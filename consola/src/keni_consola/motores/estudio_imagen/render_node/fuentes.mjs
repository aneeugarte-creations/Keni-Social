// Registro de fuentes embebidas (paridad servidor↔editor) y resolución familia/peso → CSS.
//
// El SPEC usa familias LÓGICAS ("sans" / "condensada"); aquí se resuelven a las familias
// reales embebidas (Barlow / Barlow Condensed, SIL OFL, en `../fuentes/`). El servidor las
// registra en Skia con GlobalFonts; el editor las declara con @font-face (mismos archivos).

import { GlobalFonts } from "@napi-rs/canvas";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const _aqui = dirname(fileURLToPath(import.meta.url));
const DIR_FUENTES = join(_aqui, "..", "fuentes");

// Familia real -> archivos por peso. Skia elige el archivo por peso al pedir `<peso>px ...`.
const ARCHIVOS = [
  ["Barlow", "Barlow-Regular.ttf"],
  ["Barlow", "Barlow-SemiBold.ttf"],
  ["Barlow", "Barlow-Bold.ttf"],
  ["Barlow Condensed", "BarlowCondensed-SemiBold.ttf"],
  ["Barlow Condensed", "BarlowCondensed-Bold.ttf"],
  ["Barlow Condensed", "BarlowCondensed-ExtraBold.ttf"],
];

let _registradas = false;

export function registrarFuentes() {
  if (_registradas) return;
  for (const [familia, archivo] of ARCHIVOS) {
    GlobalFonts.registerFromPath(join(DIR_FUENTES, archivo), familia);
  }
  _registradas = true;
}

// Mapa logical -> familia real, con fallback razonable.
export function familiaReal(fuentes, logica) {
  const f = fuentes || {};
  if (logica === "condensada") return f.condensada || "Barlow Condensed";
  return f.sans || "Barlow";
}

// Construye la cadena CSS de fuente para ctx.font.
export function fuenteCss(fuentes, logica, peso, tam) {
  return `${peso || 700} ${Math.round(tam)}px "${familiaReal(fuentes, logica)}"`;
}
