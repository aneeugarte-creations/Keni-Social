// Utilidades del MODO RECORTE visual (crop con tiradores). El crop son fracciones 0..1 de la
// FUENTE: `{cx,cy,cw,ch}` = origen (esq. sup. izq.) + tamaño. El editor visual muestra la imagen
// COMPLETA y un rectángulo de recorte; estas funciones acotan ese rectángulo a [0,1] con un ancho
// y alto mínimos > 0. El render (`dibujar.mjs`) ya acota igual; aquí evitamos emitir crops inválidos.

import { geometriaImagenEnCaja } from "./capas/geometriaImagen";
import type { Ajuste, Crop } from "./documento";

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

// ── Modo recorte estilo Canva ────────────────────────────────────────────────────────────────────

// Escala el RECORTE alrededor de un ANCLA (en fracciones 0..1 de la fuente): factor `f` > 1 =
// imagen más grande dentro del marco (rectángulo de recorte más pequeño). Mantiene la PROPORCIÓN
// del recorte y ACOTA el factor para no salirse de la fuente (mínimo) ni bajar de MIN_CROP
// (máximo), en vez de deformar el rectángulo. El punto del ancla conserva su posición RELATIVA
// dentro del recorte (lo que hay bajo el ancla no se mueve), salvo el clamp final a los bordes.
export function escalarCrop(c: Crop, f: number, ax: number, ay: number): Crop {
  const fMin = Math.max(c.cw, c.ch); // por debajo, cw' o ch' superaría la fuente (1)
  const fMax = Math.min(c.cw, c.ch) / MIN_CROP; // por encima, el lado menor bajaría de MIN_CROP
  const k = Math.max(fMin, Math.min(fMax, f > 0 ? f : fMin));
  return clampCrop({
    cx: ax - (ax - c.cx) / k,
    cy: ay - (ay - c.cy) / k,
    cw: c.cw / k,
    ch: c.ch / k,
  });
}

// Geometría del MODO RECORTE estilo Canva: dónde cae la imagen ORIGINAL COMPLETA (en px LOCALES de
// la caja; puede desbordarla) de modo que la región del crop aterrice EXACTAMENTE donde el render
// pinta la imagen recortada. Derivada de la geometría REAL del render (cover/contain + foco + zoom
// + crop) vía su rect visible y el sub-rect fuente: x_caja(s) = vx + (s − sx)·escalaSrc.
export interface VistaRecorte {
  fx: number; // esquina sup. izq. de la imagen original completa (px de la caja)
  fy: number;
  fw: number; // tamaño de la imagen original completa (px de la caja)
  fh: number;
  escalaSrc: number; // px de caja por px de fuente
}

export function vistaRecorte(
  iw: number,
  ih: number,
  w: number,
  h: number,
  ajuste: Ajuste,
  foco: [number, number] | undefined,
  zoom = 1,
  crop?: Crop | null,
): VistaRecorte {
  const g = geometriaImagenEnCaja(iw, ih, w, h, ajuste, foco, zoom, crop);
  const escalaSrc = g.sw > 0 ? g.vw / g.sw : 1;
  return {
    fx: g.vx - g.sx * escalaSrc,
    fy: g.vy - g.sy * escalaSrc,
    fw: iw * escalaSrc,
    fh: ih * escalaSrc,
    escalaSrc,
  };
}
