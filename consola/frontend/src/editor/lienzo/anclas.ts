// Helpers de las anclas del Transformer de Konva: el mapa ancla LATERAL → lado de la caja (gesto de
// recorte de imagen) y el estilo de cada tirador (laterales como píldora, esquinas como círculo).

import Konva from "konva";

import type { LadoCaja } from "../recorte";

// Anclas LATERALES del Transformer -> lado de la caja que mueven (gesto de recorte de imagen).
export const ANCLA_LADO: Record<string, LadoCaja> = {
  "middle-left": "izq",
  "middle-right": "der",
  "top-center": "arriba",
  "bottom-center": "abajo",
};

// Tiradores estilo Canva: laterales como PÍLDORA, esquinas como CÍRCULO (el rotador conserva su
// forma). Konva aplica la función a cada ancla en cada update (API oficial, no por-hack).
export function estiloAncla(ancla: Konva.Rect) {
  const nombre = ancla.name();
  if (nombre.includes("middle-left") || nombre.includes("middle-right")) {
    ancla.setAttrs({ width: 6, height: 16, offsetX: 3, offsetY: 8, cornerRadius: 3 });
  } else if (nombre.includes("top-center") || nombre.includes("bottom-center")) {
    ancla.setAttrs({ width: 16, height: 6, offsetX: 8, offsetY: 3, cornerRadius: 3 });
  } else if (!nombre.includes("rotater")) {
    ancla.setAttrs({ cornerRadius: ancla.width() / 2 });
  }
}
