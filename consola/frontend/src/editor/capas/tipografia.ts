// Tipografía del lienzo Konva: resolución de familia lógica -> real y construcción del
// `fontStyle` de Konva para una capa de texto. Konva concatena `fontStyle` tal cual en el
// shorthand CSS del canvas (`<fontStyle> <fontVariant> <size>px <familia>`), así que aquí va el
// PESO NUMÉRICO REAL de la capa (300/800/900…), no un binario normal/bold: el export del servidor
// pinta `${peso} …px` (fuenteCss en fuentes.mjs / dibujar.mjs) y la previa debe elegir LA MISMA
// cara.
//
// Las webfonts de `index.html` cargan por familia EXACTAMENTE las caras que el backend registra
// en Skia (guard en fuentes.mirror.test.ts): así el font-matching del navegador y el de Skia
// resuelven igual también los pesos que no existen (p. ej. Barlow 900 -> 700 en ambos lados).

import { tieneCursiva } from "../../lib/placa/dibujar.mjs";

import type { CapaTexto } from "../documento";

// Resuelve las familias LÓGICAS del documento ("sans"/"condensada") a fuentes reales, para que
// el editor (Konva) pinte con la MISMA tipografía que el export del servidor (Barlow / Barlow
// Condensed por defecto). Cualquier otra familia (nombre real) se pasa tal cual. Espejo de
// `familiaReal` en `render_node/fuentes.mjs`.
export function familiaReal(familia: string | undefined): string {
  if (familia === "sans") return "Barlow";
  if (familia === "condensada") return "Barlow Condensed";
  return familia || "Barlow";
}

// `fontStyle` Konva de una capa de texto: peso numérico real (def 700, como `fuenteCss` en el
// servidor) y la CURSIVA solo si la familia REAL tiene itálica registrada (`tieneCursiva`, la
// misma regla que aplica el export en `dibujar.mjs`): así la previa nunca enseña una oblicua
// sintética del navegador que el servidor no pueda reproducir.
export function estiloFuente(c: Pick<CapaTexto, "peso" | "cursiva" | "familia">): string {
  const peso = c.peso || 700;
  const cursiva = !!c.cursiva && tieneCursiva(familiaReal(c.familia));
  return cursiva ? `italic ${peso}` : String(peso);
}

// Mide el ancho en px de `texto` con un canvas 2D offscreen — la MISMA medida (`measureText` +
// shorthand de font) que usa el export en `dibujarLogo`/`dibujarTexto`, para que la previa del
// wordmark se ciña al texto igual que el PNG. El canvas se crea una vez y se reutiliza. En
// entornos sin canvas 2D (tests jsdom) cae a una aproximación por glifo (~0.6 em): solo afecta a
// la previa, nunca al dato ni al export.
let _ctxMedida: CanvasRenderingContext2D | null | undefined;
export function medirTexto(texto: string, font: string): number {
  if (_ctxMedida === undefined) {
    try {
      _ctxMedida = typeof document !== "undefined" ? document.createElement("canvas").getContext("2d") : null;
    } catch {
      _ctxMedida = null; // jsdom sin canvas: getContext puede lanzar "Not implemented"
    }
  }
  if (!_ctxMedida) {
    const m = /(\d+(?:\.\d+)?)px/.exec(font);
    return texto.length * (m ? parseFloat(m[1]) : 16) * 0.6;
  }
  _ctxMedida.font = font;
  return _ctxMedida.measureText(texto).width;
}
