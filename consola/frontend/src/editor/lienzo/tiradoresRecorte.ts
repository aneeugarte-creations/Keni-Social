// Tiradores COMPARTIDOS del MODO RECORTE (foto y forma): 8 asas sobre el MARCO con aspecto Canva
// —puntos en las esquinas, barras en los lados— para que recortar una foto y recortar una forma se
// vean idénticos. Aquí solo viven la GEOMETRÍA (posiciones relativas al recuadro), el ESTILO y la
// ETIQUETA accesible; cada overlay cablea sus propios gestos (la foto compensa el crop, la forma
// encoge el recuadro).

import type { AsaRecorte } from "../recorte";

export interface AsaMarco {
  asa: AsaRecorte;
  x: number; // px relativos al recuadro (0..W / 0..H)
  y: number;
  cursor: string;
}

// 8 tiradores (4 esquinas + 4 lados) colocados sobre el borde del recuadro `W×H`.
export function asasMarco(W: number, H: number): AsaMarco[] {
  return [
    { asa: "nw", x: 0, y: 0, cursor: "nwse-resize" },
    { asa: "n", x: W / 2, y: 0, cursor: "ns-resize" },
    { asa: "ne", x: W, y: 0, cursor: "nesw-resize" },
    { asa: "e", x: W, y: H / 2, cursor: "ew-resize" },
    { asa: "se", x: W, y: H, cursor: "nwse-resize" },
    { asa: "s", x: W / 2, y: H, cursor: "ns-resize" },
    { asa: "sw", x: 0, y: H, cursor: "nesw-resize" },
    { asa: "w", x: 0, y: H / 2, cursor: "ew-resize" },
  ];
}

const ESQUINAS = new Set<AsaRecorte>(["nw", "ne", "se", "sw"]);

// Estilo Canva: esquina = PUNTO; lado = BARRA (pill) a lo largo de su borde. Blanco con borde de
// marca y sombra suave (mismo lenguaje en foto y forma).
export function claseTirador(asa: AsaRecorte): string {
  const base =
    "pointer-events-auto absolute -translate-x-1/2 -translate-y-1/2 touch-none border border-primary bg-background shadow";
  if (ESQUINAS.has(asa)) return `${base} h-3 w-3 rounded-full`;
  if (asa === "n" || asa === "s") return `${base} h-1.5 w-6 rounded-full`; // lado horizontal
  return `${base} h-6 w-1.5 rounded-full`; // lado vertical (e / w)
}

const ETIQUETAS: Record<AsaRecorte, string> = {
  nw: "Recortar desde la esquina superior izquierda",
  n: "Recortar desde el borde superior",
  ne: "Recortar desde la esquina superior derecha",
  e: "Recortar desde el borde derecho",
  se: "Recortar desde la esquina inferior derecha",
  s: "Recortar desde el borde inferior",
  sw: "Recortar desde la esquina inferior izquierda",
  w: "Recortar desde el borde izquierdo",
  mover: "Mover",
};

export function etiquetaAsa(asa: AsaRecorte): string {
  return ETIQUETAS[asa];
}
