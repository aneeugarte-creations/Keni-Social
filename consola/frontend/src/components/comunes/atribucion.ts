/**
 * Lógica de etiqueta de la atribución por usuario (#130 Fase 1). Aparte del componente
 * para no romper el fast-refresh de React (un módulo que exporta componentes no debe
 * exportar también helpers no-componente).
 */

/** Texto de "desconocido" para registros legados / anónimos (sin autor). */
export const AUTOR_DESCONOCIDO = "desconocido";

/**
 * Etiqueta "por <usuario>" de un autor. Si no hay nombre (registro legado/anónimo),
 * devuelve "por desconocido". Recorta espacios; "" cuenta como sin autor.
 */
export function etiquetaAutor(nombre: string | null | undefined): string {
  const limpio = (nombre ?? "").trim();
  return `por ${limpio || AUTOR_DESCONOCIDO}`;
}
