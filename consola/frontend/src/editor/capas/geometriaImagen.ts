// Geometría PURA de una imagen ajustada a una caja (espejo del cálculo de `dibujarImagenEnCaja`
// en dibujar.mjs): dónde cae la imagen (cover/contain + foco + zoom + crop) y, sobre todo, qué
// parte queda VISIBLE dentro de la caja. El lienzo (Konva) pinta SOLO el rect visible para que el
// marco de selección (Transformer) abrace EXACTAMENTE la foto renderizada, como Canva: el bbox de
// un Group en Konva se calcula SIN considerar el clip, así que si se pintara el destino entero,
// con `cover`/zoom el desborde recortado inflaría el marco más ancho/alto que la foto visible.

import type { Ajuste, Crop } from "../documento";

export interface GeometriaImagen {
  // Destino COMPLETO del ajuste (coords locales de la caja; puede desbordarla con cover o zoom>1).
  ix: number;
  iy: number;
  dw: number;
  dh: number;
  // Rect VISIBLE = destino ∩ caja. Es la foto que se ve (la que debe abrazar el marco).
  vx: number;
  vy: number;
  vw: number;
  vh: number;
  // Sub-rect de la FUENTE (px de la imagen ORIGINAL) que corresponde al rect visible.
  sx: number;
  sy: number;
  sw: number;
  sh: number;
}

export function geometriaImagenEnCaja(
  iwTotal: number,
  ihTotal: number,
  w: number,
  h: number,
  ajuste: Ajuste,
  foco: [number, number] | undefined,
  zoom = 1,
  crop?: Crop | null,
): GeometriaImagen {
  // Imagen EFECTIVA = sub-rect fuente recortado (crop, fracciones 0..1 -> px). Espejo de `rectFuente`.
  const iw0 = iwTotal || 1;
  const ih0 = ihTotal || 1;
  const cx = crop ? Math.max(0, Math.min(1, crop.cx)) : 0;
  const cy = crop ? Math.max(0, Math.min(1, crop.cy)) : 0;
  const cw = crop ? Math.max(0, Math.min(1 - cx, crop.cw)) : 1;
  const ch = crop ? Math.max(0, Math.min(1 - cy, crop.ch)) : 1;
  const usaCrop = crop != null && cw > 0 && ch > 0 && (cx > 0 || cy > 0 || cw < 1 || ch < 1);
  const iw = usaCrop ? cw * iw0 : iw0;
  const ih = usaCrop ? ch * ih0 : ih0;
  const base = ajuste === "contain" ? Math.min(w / iw, h / ih) : Math.max(w / iw, h / ih);
  const escala = base * (zoom > 0 ? zoom : 1);
  const dw = iw * escala;
  const dh = ih * escala;
  const ix = (w - dw) * (foco?.[0] ?? 0.5);
  const iy = (h - dh) * (foco?.[1] ?? 0.5);
  // Rect visible: intersección del destino con la caja [0,w]×[0,h]. Si un foco fuera de rango
  // dejara la intersección vacía, caemos al destino completo (no dejar la capa invisible/inclicable).
  let vx = Math.max(0, ix);
  let vy = Math.max(0, iy);
  let vw = Math.min(w, ix + dw) - vx;
  let vh = Math.min(h, iy + dh) - vy;
  if (vw <= 0 || vh <= 0) {
    vx = ix;
    vy = iy;
    vw = dw;
    vh = dh;
  }
  // Fuente del rect visible (px de la imagen ORIGINAL): deshace la escala y suma el origen del crop.
  const sx = (usaCrop ? cx * iw0 : 0) + (vx - ix) / escala;
  const sy = (usaCrop ? cy * ih0 : 0) + (vy - iy) / escala;
  const sw = vw / escala;
  const sh = vh / escala;
  return { ix, iy, dw, dh, vx, vy, vw, vh, sx, sy, sw, sh };
}
