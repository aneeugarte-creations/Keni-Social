// Vocabulario visual del kanban de sugerencias: etiquetas, columnas y aspecto de los badges.
import type { EstadoSugerencia } from "@/types";

export const CLAVE_SUGERENCIAS = ["sugerencias"] as const;

export const CATEGORIA_LABEL: Record<string, string> = {
  idea: "Idea",
  producto: "Producto",
  mejora: "Mejora",
  bug: "Bug",
};

export const ESTADO_LABEL: Record<string, string> = {
  nueva: "Ideas",
  discovery: "Discovery",
  en_cola: "En cola",
  building: "Building",
  revision: "Revisión",
  hecha: "Hecho",
  fallida: "Fallida",
  descartada: "Descartada",
};

export const COMPLEJIDAD_LABEL: Record<string, string> = {
  "": "Sin estimar",
  simple: "Simple",
  standard: "Estándar",
  complex: "Compleja",
};

export type VarianteBadge =
  | "secondary"
  | "aviso"
  | "ok"
  | "error"
  | "outline"
  | "destructive";

export const ESTADO_VARIANTE: Record<string, VarianteBadge> = {
  nueva: "secondary",
  discovery: "aviso",
  en_cola: "outline",
  building: "aviso",
  revision: "aviso",
  hecha: "ok",
  fallida: "error",
  descartada: "error",
};

export const COMPLEJIDAD_VARIANTE: Record<string, VarianteBadge> = {
  "": "outline",
  simple: "ok",
  standard: "secondary",
  complex: "aviso",
};

/** Columnas del kanban, en orden de flujo. Fallida/Descartada viven en una zona aparte. */
export const COLUMNAS: { estado: EstadoSugerencia; titulo: string }[] = [
  { estado: "nueva", titulo: "Ideas" },
  { estado: "discovery", titulo: "Discovery" },
  { estado: "en_cola", titulo: "En cola" },
  { estado: "building", titulo: "Building" },
  { estado: "revision", titulo: "Revisión" },
  { estado: "hecha", titulo: "Hecho" },
];

/** Estados que no son columna del flujo principal (zona archivada). */
export const ESTADOS_ARCHIVO: EstadoSugerencia[] = ["fallida", "descartada"];

export function etiqueta(mapa: Record<string, string>, clave: string): string {
  return mapa[clave] ?? clave;
}
