// Registro del CATÁLOGO de fuentes embebidas (SIL OFL, en `../fuentes/`) y resolución de la
// familia de una capa a un nombre real registrado en Skia.
//
// El editor elige la familia por NOMBRE real (p. ej. "Anton", "Barlow Condensed"); el servidor
// registra esas familias y las usa directamente. Compatibilidad: las familias lógicas antiguas
// "sans"/"condensada" se mapean a Barlow / Barlow Condensed. Solo el SERVIDOR necesita los
// archivos (la vista previa del editor también la renderiza el servidor).

import { GlobalFonts } from "@napi-rs/canvas";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const _aqui = dirname(fileURLToPath(import.meta.url));
const DIR_FUENTES = join(_aqui, "..", "fuentes");

// Familia real -> archivo(s). Las variables (Oswald/Montserrat/Lora) se registran una vez; Skia
// elige el peso por el eje variable al pedir `<peso>px`. Barlow trae estáticas por peso.
// CURSIVA: las caras *Italic* se registran bajo la MISMA familia; Skia elige la itálica cuando el
// font string lleva `italic` (Skia NUNCA sintetiza oblicuas, por eso hacen falta los TTF reales).
// Anton / Archivo Black / Oswald no tienen itálica (ver FAMILIAS_CON_CURSIVA en dibujar.mjs).
const ARCHIVOS = [
  ["Barlow", "Barlow-Regular.ttf"],
  ["Barlow", "Barlow-SemiBold.ttf"],
  ["Barlow", "Barlow-Bold.ttf"],
  ["Barlow", "Barlow-Italic.ttf"],
  ["Barlow", "Barlow-SemiBoldItalic.ttf"],
  ["Barlow", "Barlow-BoldItalic.ttf"],
  ["Barlow Condensed", "BarlowCondensed-SemiBold.ttf"],
  ["Barlow Condensed", "BarlowCondensed-Bold.ttf"],
  ["Barlow Condensed", "BarlowCondensed-ExtraBold.ttf"],
  ["Barlow Condensed", "BarlowCondensed-SemiBoldItalic.ttf"],
  ["Barlow Condensed", "BarlowCondensed-BoldItalic.ttf"],
  ["Barlow Condensed", "BarlowCondensed-ExtraBoldItalic.ttf"],
  ["Anton", "Anton-Regular.ttf"],
  ["Archivo Black", "ArchivoBlack-Regular.ttf"],
  ["Oswald", "Oswald-Variable.ttf"],
  ["Montserrat", "Montserrat-Variable.ttf"],
  ["Montserrat", "Montserrat-Italic-Variable.ttf"],
  ["Lora", "Lora-Variable.ttf"],
  ["Lora", "Lora-Italic-Variable.ttf"],
  ["Exo 2", "Exo2-Variable.ttf"],
  ["Exo 2", "Exo2-Italic-Variable.ttf"],
  ["Lato", "Lato-Regular.ttf"],
  ["Lato", "Lato-Bold.ttf"],
  ["Lato", "Lato-Black.ttf"],
  ["Lato", "Lato-Italic.ttf"],
  ["Lato", "Lato-BoldItalic.ttf"],
  ["Lato", "Lato-BlackItalic.ttf"],
];

// Catálogo de familias ofrecidas (el editor mantiene su propia copia para el selector).
export const CATALOGO = ["Barlow", "Barlow Condensed", "Anton", "Oswald", "Montserrat", "Archivo Black", "Lora", "Exo 2", "Lato"];

let _registradas = false;

export function registrarFuentes() {
  if (_registradas) return;
  for (const [familia, archivo] of ARCHIVOS) {
    GlobalFonts.registerFromPath(join(DIR_FUENTES, archivo), familia);
  }
  _registradas = true;
}

// Resuelve la familia de una capa a un nombre real registrado.
//   - "sans"        -> spec.fuentes.sans (o Barlow)        [compat con specs antiguos]
//   - "condensada"  -> spec.fuentes.condensada (o Barlow Condensed)
//   - cualquier otro -> ese mismo nombre (familia del catálogo)
export function familiaReal(fuentes, familia) {
  const f = fuentes || {};
  if (familia === "sans") return f.sans || "Barlow";
  if (familia === "condensada") return f.condensada || "Barlow Condensed";
  return familia || "Barlow";
}

export function fuenteCss(fuentes, familia, peso, tam) {
  return `${peso || 700} ${Math.round(tam)}px "${familiaReal(fuentes, familia)}"`;
}
