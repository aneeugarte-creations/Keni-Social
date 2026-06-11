/**
 * Constantes y helpers compartidos por los paneles de Configuración.
 * Las claves de query (`CLAVE_*`) se usan tanto para leer como para invalidar
 * cachés desde el contenedor y desde cada panel.
 */
import { ApiError } from "@/lib/api";

export const CLAVE_ESFUERZO = ["config", "esfuerzo"];
export const CLAVE_IMAGEN = ["conexiones", "imagen"];
export const CLAVE_METRICOOL = ["conexiones", "metricool"];
export const CLAVE_AJUSTES = ["ajustes"];

/** Proveedores de imagen IA disponibles (gateway único OpenRouter). */
export const PROVEEDORES = [{ id: "openrouter", nombre: "OpenRouter (gateway de IA)" }];

/** Grupos de ajustes que pinta el MONITOR (proceso de PRODUCCIÓN, ADR 0011): el interruptor
 *  general, el maestro de Producción (Producción/Arte), sus excepciones por marca y la admisión del
 *  flujo continuo. El proceso de INVESTIGACIÓN (su maestro y sus excepciones por marca) NO vive
 *  aquí: se edita en la página Investigación. Debe coincidir con `ajustes_catalogo.GRUPOS_MAQUINA`
 *  del backend. Configuración EXCLUYE estos grupos; el panel del Monitor pinta SOLO estos. */
export const GRUPOS_MAQUINA = new Set([
  "maquina_global",
  "maestros_produccion",
  "automatizacion_marca_produccion",
  "pipeline_topes",
]);

/**
 * Limpia emojis de estado (❌ ✅ ⚠️ …) que pueda traer el backend y normaliza
 * espacios y puntuación, para mostrar un texto sobrio en la consola.
 */
export function limpiarMensaje(texto: string): string {
  return texto
    .replace(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}]/gu, "")
    .replace(/️/g, "")
    .replace(/\s+/g, " ")
    .replace(/\s+([.,;:!?])/g, "$1")
    .trim();
}

/** Texto legible del error de la API (o un fallback en español). */
export function mensajeError(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return limpiarMensaje(error.message);
  return "Ocurrió un problema inesperado. Vuelve a intentarlo en un momento.";
}
