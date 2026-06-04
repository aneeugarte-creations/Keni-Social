// Auto-overlay por CONTRASTE WCAG: detecta titulares poco legibles sobre la foto y los arregla.
//
// «IA hacia adentro» para calidad: en vez de que el humano juzgue caso por caso si un texto se lee
// bien sobre la imagen, estimamos el brillo medio de la región de la foto BAJO cada caja de texto y
// el contraste (luminancia relativa WCAG) contra el color del texto. Lo que cae por debajo de AA
// (4.5:1, o 3:1 para texto grande) se marca y se ofrece «Arreglar» con una solución conservadora
// que reusa campos EXISTENTES (overlay inferior / contorno / sombra), sin tocar el esquema.
//
// MÉTODO DE MUESTREO
// ------------------
// El brillo se lee del <canvas> del Stage de Konva (`stageRef.current.toCanvas()`), que ya tiene
// pintado el documento tal cual se ve (foto + filtros + overlays por debajo del texto). Para cada
// texto muestreamos una rejilla de puntos dentro de su caja (en coords del documento, convertidas a
// px del canvas por la escala del Stage) y promediamos su luminancia. Así el contraste tiene en
// cuenta lo que REALMENTE hay debajo (incluido un overlay ya presente), no solo la foto cruda.
//
// La detección es PURA respecto a un `Muestreador` (brillo 0..1 de una caja), inyectable: en
// producción lo construye `muestreadorDeStage`; en tests se pasa uno sintético.

import type Konva from "konva";

import type { Capa, CapaTexto, Documento } from "./documento";
import { nuevaCapaOverlay } from "./documento";

// Luminancia relativa WCAG de un color sRGB (0..1). https://www.w3.org/TR/WCAG20/#relativeluminancedef
function canalLineal(c: number): number {
  const s = c / 255;
  return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
}
export function luminanciaRGB(r: number, g: number, b: number): number {
  return 0.2126 * canalLineal(r) + 0.7152 * canalLineal(g) + 0.0722 * canalLineal(b);
}

// Parsea un color hex (#RGB, #RRGGBB, #RRGGBBAA) a [r,g,b] 0..255. Ignora el alfa para luminancia.
export function hexARgb(hex: string): [number, number, number] {
  let h = (hex || "").trim().replace(/^#/, "");
  if (h.length === 3) h = h.split("").map((c) => c + c).join("");
  if (h.length < 6) return [255, 255, 255];
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return [Number.isNaN(r) ? 255 : r, Number.isNaN(g) ? 255 : g, Number.isNaN(b) ? 255 : b];
}

// Ratio de contraste WCAG entre dos luminancias relativas (1..21).
export function contraste(l1: number, l2: number): number {
  const claro = Math.max(l1, l2);
  const oscuro = Math.min(l1, l2);
  return (claro + 0.05) / (oscuro + 0.05);
}

// Umbral AA según el tamaño/peso del texto: 3:1 para texto grande (≥24px normal o ≥18.66px bold),
// 4.5:1 para el resto. Trabajamos en px del documento (el tamaño de fuente de la capa).
export function umbralAA(t: CapaTexto): number {
  const grande = t.tamano >= 24 && (t.peso >= 700 ? t.tamano >= 18.66 : t.tamano >= 24);
  return grande ? 3 : 4.5;
}

// Caja en coordenadas del documento.
export interface Caja {
  x: number;
  y: number;
  w: number;
  h: number;
}

// Devuelve el brillo (luminancia relativa 0..1) medio de la región del LIENZO bajo `caja`, o null si
// no se puede muestrear (caja fuera del canvas, etc.).
export type Muestreador = (caja: Caja) => number | null;

export interface Diagnostico {
  id: string;
  // Contraste estimado del texto contra el fondo bajo su caja.
  ratio: number;
  // Umbral AA aplicable.
  umbral: number;
  // Luminancia media del fondo bajo el texto (0..1).
  brilloFondo: number;
  // Caja del texto (coords documento), para decidir la corrección.
  caja: Caja;
}

// Caja efectiva de una capa de texto: si `h<=0` (auto-alto legado) usamos una estimación basada en
// el tamaño de fuente para tener una región que muestrear.
function cajaTexto(t: CapaTexto): Caja {
  const h = t.h > 0 ? t.h : Math.max(t.tamano * 1.4, 40);
  return { x: t.x, y: t.y, w: Math.max(t.w, 1), h };
}

/**
 * Analiza TODOS los textos visibles del documento y devuelve los que NO alcanzan AA. Puro respecto
 * al `Muestreador`. Los textos cuyo fondo no se puede muestrear se omiten (no se marcan como malos).
 */
export function analizarLegibilidad(doc: Documento, muestrear: Muestreador): Diagnostico[] {
  const malos: Diagnostico[] = [];
  for (const c of doc.capas) {
    if (c.tipo !== "texto" || !c.visible) continue;
    const t = c as CapaTexto;
    if (!t.texto || !t.texto.trim()) continue;
    const caja = cajaTexto(t);
    const brillo = muestrear(caja);
    if (brillo === null) continue;
    const lTexto = luminanciaRGB(...hexARgb(t.color));
    const ratio = contraste(lTexto, brillo);
    const umbral = umbralAA(t);
    if (ratio < umbral) {
      malos.push({ id: t.id, ratio, umbral, brilloFondo: brillo, caja });
    }
  }
  return malos;
}

// Construye un Muestreador a partir del Stage de Konva. Rasteriza el Stage a un <canvas> una sola
// vez y lee píxeles en una rejilla dentro de cada caja. `escala` = px de canvas por unidad de
// documento (el `scaleX` del Stage). Devuelve null si el canvas no es legible (p.ej. tainted).
export function muestreadorDeStage(stage: Konva.Stage, escala: number): Muestreador {
  let ctx: CanvasRenderingContext2D | null = null;
  let cw = 0;
  let ch = 0;
  try {
    const canvas = stage.toCanvas();
    ctx = canvas.getContext("2d", { willReadFrequently: true });
    cw = canvas.width;
    ch = canvas.height;
  } catch {
    ctx = null;
  }
  return (caja: Caja): number | null => {
    if (!ctx) return null;
    const PASOS = 5; // rejilla 5x5
    let suma = 0;
    let n = 0;
    for (let i = 0; i < PASOS; i++) {
      for (let j = 0; j < PASOS; j++) {
        const px = Math.round((caja.x + ((i + 0.5) / PASOS) * caja.w) * escala);
        const py = Math.round((caja.y + ((j + 0.5) / PASOS) * caja.h) * escala);
        if (px < 0 || py < 0 || px >= cw || py >= ch) continue;
        try {
          const d = ctx.getImageData(px, py, 1, 1).data;
          // Sobre fondo transparente (alfa 0) asumimos blanco del lienzo del editor.
          const a = d[3] / 255;
          const r = d[0] * a + 255 * (1 - a);
          const g = d[1] * a + 255 * (1 - a);
          const b = d[2] * a + 255 * (1 - a);
          suma += luminanciaRGB(r, g, b);
          n++;
        } catch {
          return null; // canvas tainted: abortamos el muestreo (cae al arreglo sin píxeles)
        }
      }
    }
    return n > 0 ? suma / n : null;
  };
}

// Una corrección a aplicar sobre el store: o bien añadir una capa overlay nueva, o bien actualizar
// una capa de texto (contorno/sombra). El llamador (UI) la traduce a `agregar`/`actualizar`.
export type Correccion =
  | { tipo: "overlay"; capa: Capa }
  | { tipo: "texto"; id: string; cambios: Partial<CapaTexto> };

// Decide la corrección CONSERVADORA para un texto poco legible:
//  - Si el texto está en la franja INFERIOR del lienzo, refuerza un overlay oscuro inferior (la
//    solución más natural para titulares al pie). Se calcula su altura para cubrir el texto.
//  - Si no, activa contorno o sombra oscuros en el propio texto (no requiere leer más píxeles).
// El sentido (oscuro vs claro) lo decide el brillo del fondo: fondo claro -> refuerzo oscuro; fondo
// muy oscuro y texto oscuro -> contorno claro.
export function correccionPara(doc: Documento, d: Diagnostico): Correccion {
  const t = doc.capas.find((c) => c.id === d.id) as CapaTexto | undefined;
  const { h } = doc.formato;
  const enInferior = d.caja.y >= h * 0.6;
  const fondoOscuro = d.brilloFondo < 0.3;

  if (enInferior) {
    // Overlay degradado-equivalente: capa overlay inferior. Cubre desde un poco por encima del
    // texto hasta el borde. `alto_frac` es la fracción del alto del lienzo que ocupa (anclado abajo
    // en el render). Tomamos la fracción necesaria para tapar el texto + margen.
    const desdeY = Math.max(0, d.caja.y - d.caja.h * 0.25);
    const altoFrac = Math.min(0.9, Math.max(0.25, (h - desdeY) / h));
    const overlay = nuevaCapaOverlay({
      x: 0,
      y: 0,
      w: doc.formato.w,
      h,
      color: fondoOscuro ? "#000000" : "#000000",
      alto_frac: altoFrac,
      alpha: 200, // ~0.78; suficiente para AA con texto blanco en la mayoría de fotos
      nombre: "Overlay legibilidad",
      z: (t?.z ?? 0) - 0.0001, // justo bajo el texto; el render ordena por z (se normaliza al insertar)
    });
    return { tipo: "overlay", capa: overlay };
  }

  // Fuera de la franja inferior: refuerzo en el propio texto.
  if (fondoOscuro) {
    // Texto presumiblemente oscuro sobre fondo oscuro -> contorno claro para despegarlo.
    return { tipo: "texto", id: d.id, cambios: { contorno: { color: "#FFFFFF", grosor: 6 } } };
  }
  // Fondo claro/medio -> sombra/contorno oscuro (lo más conservador: contorno negro fino + sombra).
  return {
    tipo: "texto",
    id: d.id,
    cambios: {
      contorno: { color: "#000000", grosor: 6 },
      sombra: { dx: 0, dy: 2, color: "#000000", desenfoque: 12, opacidad: 0.6 },
    },
  };
}
