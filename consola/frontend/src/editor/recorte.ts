// Utilidades del MODO RECORTE visual (crop con tiradores). El crop son fracciones 0..1 de la
// FUENTE: `{cx,cy,cw,ch}` = origen (esq. sup. izq.) + tamaño. El editor visual muestra la imagen
// COMPLETA y un rectángulo de recorte; estas funciones acotan ese rectángulo a [0,1] con un ancho
// y alto mínimos > 0. El render (`dibujar.mjs`) ya acota igual; aquí evitamos emitir crops inválidos.

import type { Crop } from "./documento";

// Recorte mínimo (en fracción) para no colapsar el rectángulo a 0.
export const MIN_CROP = 0.02;

// Acota un crop a [0,1] manteniendo cw,ch >= MIN_CROP y el rect dentro de la fuente.
export function clampCrop(c: Crop): Crop {
  const cw = Math.max(MIN_CROP, Math.min(1, c.cw));
  const ch = Math.max(MIN_CROP, Math.min(1, c.ch));
  const cx = Math.max(0, Math.min(1 - cw, c.cx));
  const cy = Math.max(0, Math.min(1 - ch, c.cy));
  return { cx, cy, cw, ch };
}

// Tiradores del rectángulo de recorte: 4 esquinas + 4 lados. `ew/ns` indican qué bordes mueve.
export type AsaRecorte = "nw" | "n" | "ne" | "e" | "se" | "s" | "sw" | "w" | "mover";

// Aplica el movimiento de un tirador (delta en fracciones) sobre un crop y lo acota. `mover`
// desplaza todo el rectángulo; las asas mueven los bordes correspondientes.
export function moverAsa(c: Crop, asa: AsaRecorte, dfx: number, dfy: number): Crop {
  if (asa === "mover") {
    const cx = Math.max(0, Math.min(1 - c.cw, c.cx + dfx));
    const cy = Math.max(0, Math.min(1 - c.ch, c.cy + dfy));
    return { ...c, cx, cy };
  }
  let { cx, cy, cw, ch } = c;
  const oeste = asa === "nw" || asa === "w" || asa === "sw";
  const este = asa === "ne" || asa === "e" || asa === "se";
  const norte = asa === "nw" || asa === "n" || asa === "ne";
  const sur = asa === "sw" || asa === "s" || asa === "se";
  if (oeste) {
    const nx = Math.max(0, Math.min(cx + cw - MIN_CROP, cx + dfx));
    cw = cw + (cx - nx);
    cx = nx;
  }
  if (este) {
    cw = Math.max(MIN_CROP, Math.min(1 - cx, cw + dfx));
  }
  if (norte) {
    const ny = Math.max(0, Math.min(cy + ch - MIN_CROP, cy + dfy));
    ch = ch + (cy - ny);
    cy = ny;
  }
  if (sur) {
    ch = Math.max(MIN_CROP, Math.min(1 - cy, ch + dfy));
  }
  return clampCrop({ cx, cy, cw, ch });
}
