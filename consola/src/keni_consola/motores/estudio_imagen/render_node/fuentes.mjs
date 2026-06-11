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

// Familia real -> archivo(s). TODAS las caras son ESTÁTICAS por peso: Skia NO instancia el eje
// `wght` de un TTF variable (lo registra como una sola cara, la instancia por defecto, y pedir
// `300 …px` o `900 …px` pintaba siempre lo mismo), así que cada peso ofrecido necesita su TTF.
// Skia elige la cara más cercana al peso pedido (p. ej. Lato 900 -> Lato-Black.ttf; un peso sin
// cara cae al vecino, igual que el font-matching del navegador en el lienzo Konva).
// Montserrat trae 300..900 completos: Light (300) y los titulares ExtraBold (800) / Black (900)
// estilo Gotham que usa Claro Sports en sus posts deportivos.
// Oswald cubre 300..700 (Light y Medium reales): Anton solo existe en UN peso (400; así es la
// familia, no hay Anton Light oficial) y Oswald es su hermana condensada con pesos — el titular
// condensado fino se pide como Oswald + 300, nunca sintetizando un falso Anton adelgazado.
// CURSIVA: las caras *Italic* se registran bajo la MISMA familia; Skia elige la itálica cuando el
// font string lleva `italic` (Skia NUNCA sintetiza oblicuas, por eso hacen falta los TTF reales).
// Anton / Archivo Black / Oswald no tienen itálica (ver FAMILIAS_CON_CURSIVA en dibujar.mjs).
// Gemelas OFL de comerciales (las comerciales NO se pueden embeber): Poppins 300..900 (+itálicas;
// geométrica estilo Gotham/Proxima), Roboto Condensed 300/400/700 (≈ Univers Condensed),
// Mulish 400/700/800 (≈ Proxima Nova; su Bold es la cara pedida) y Nunito Sans 400/700/900
// (≈ Avenir Next; el 900 hace de "Heavy"). Solo uprights salvo Poppins: registrar una familia
// sin itálica la deja FUERA de FAMILIAS_CON_CURSIVA (botón I deshabilitado honesto).
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
  ["Oswald", "Oswald-Light.ttf"],
  ["Oswald", "Oswald-Regular.ttf"],
  ["Oswald", "Oswald-Medium.ttf"],
  ["Oswald", "Oswald-SemiBold.ttf"],
  ["Oswald", "Oswald-Bold.ttf"],
  ["Montserrat", "Montserrat-Light.ttf"],
  ["Montserrat", "Montserrat-Regular.ttf"],
  ["Montserrat", "Montserrat-Medium.ttf"],
  ["Montserrat", "Montserrat-SemiBold.ttf"],
  ["Montserrat", "Montserrat-Bold.ttf"],
  ["Montserrat", "Montserrat-ExtraBold.ttf"],
  ["Montserrat", "Montserrat-Black.ttf"],
  ["Montserrat", "Montserrat-LightItalic.ttf"],
  ["Montserrat", "Montserrat-Italic.ttf"],
  ["Montserrat", "Montserrat-MediumItalic.ttf"],
  ["Montserrat", "Montserrat-SemiBoldItalic.ttf"],
  ["Montserrat", "Montserrat-BoldItalic.ttf"],
  ["Montserrat", "Montserrat-ExtraBoldItalic.ttf"],
  ["Montserrat", "Montserrat-BlackItalic.ttf"],
  ["Lora", "Lora-Regular.ttf"],
  ["Lora", "Lora-Bold.ttf"],
  ["Lora", "Lora-Italic.ttf"],
  ["Lora", "Lora-BoldItalic.ttf"],
  ["Exo 2", "Exo2-Regular.ttf"],
  ["Exo 2", "Exo2-SemiBold.ttf"],
  ["Exo 2", "Exo2-Bold.ttf"],
  ["Exo 2", "Exo2-ExtraBold.ttf"],
  ["Exo 2", "Exo2-Italic.ttf"],
  ["Exo 2", "Exo2-SemiBoldItalic.ttf"],
  ["Exo 2", "Exo2-BoldItalic.ttf"],
  ["Exo 2", "Exo2-ExtraBoldItalic.ttf"],
  ["Lato", "Lato-Regular.ttf"],
  ["Lato", "Lato-Bold.ttf"],
  ["Lato", "Lato-Black.ttf"],
  ["Lato", "Lato-Italic.ttf"],
  ["Lato", "Lato-BoldItalic.ttf"],
  ["Lato", "Lato-BlackItalic.ttf"],
  ["Poppins", "Poppins-Light.ttf"],
  ["Poppins", "Poppins-Regular.ttf"],
  ["Poppins", "Poppins-Medium.ttf"],
  ["Poppins", "Poppins-SemiBold.ttf"],
  ["Poppins", "Poppins-Bold.ttf"],
  ["Poppins", "Poppins-ExtraBold.ttf"],
  ["Poppins", "Poppins-Black.ttf"],
  ["Poppins", "Poppins-LightItalic.ttf"],
  ["Poppins", "Poppins-Italic.ttf"],
  ["Poppins", "Poppins-MediumItalic.ttf"],
  ["Poppins", "Poppins-SemiBoldItalic.ttf"],
  ["Poppins", "Poppins-BoldItalic.ttf"],
  ["Poppins", "Poppins-ExtraBoldItalic.ttf"],
  ["Poppins", "Poppins-BlackItalic.ttf"],
  ["Roboto Condensed", "RobotoCondensed-Light.ttf"],
  ["Roboto Condensed", "RobotoCondensed-Regular.ttf"],
  ["Roboto Condensed", "RobotoCondensed-Bold.ttf"],
  ["Mulish", "Mulish-Regular.ttf"],
  ["Mulish", "Mulish-Bold.ttf"],
  ["Mulish", "Mulish-ExtraBold.ttf"],
  ["Nunito Sans", "NunitoSans-Regular.ttf"],
  ["Nunito Sans", "NunitoSans-Bold.ttf"],
  ["Nunito Sans", "NunitoSans-Black.ttf"],
];

// Catálogo de familias ofrecidas (el editor mantiene su propia copia para el selector).
export const CATALOGO = ["Barlow", "Barlow Condensed", "Anton", "Oswald", "Montserrat", "Archivo Black", "Lora", "Exo 2", "Lato", "Poppins", "Roboto Condensed", "Mulish", "Nunito Sans"];

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
