/**
 * Utilidades compartidas del catálogo unificado de plantillas (planas + estructura).
 */
import type { PlantillaContenido, VariablePlantilla } from "@/types";

/** Clave de React Query del catálogo unificado de plantillas. */
export const CLAVE_PLANTILLAS = ["plantillas-contenido"] as const;

// Extrae los marcadores `{{clave}}` de una estructura (para detectar variables sin declarar).
const RE_MARCADOR = /\{\{\s*([a-zA-Z0-9_]+)\s*\}\}/g;

/** Claves `{{...}}` que aparecen en una estructura, en orden y sin repetir. */
export function clavesEnEstructura(estructura: string): string[] {
  const vistas: string[] = [];
  for (const m of estructura.matchAll(RE_MARCADOR)) {
    if (!vistas.includes(m[1])) vistas.push(m[1]);
  }
  return vistas;
}

/** Variables a rellenar al aplicar: las declaradas o, si no hay, las detectadas en la estructura. */
export function variablesAplicables(plantilla: PlantillaContenido): VariablePlantilla[] {
  if (plantilla.variables.length > 0) return plantilla.variables;
  return clavesEnEstructura(plantilla.estructura).map((c) => ({
    clave: c,
    etiqueta: "",
    ejemplo: "",
  }));
}
