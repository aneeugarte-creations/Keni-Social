/**
 * Constantes y helpers compartidos por los paneles de Configuración.
 * Las claves de query (`CLAVE_*`) se usan tanto para leer como para invalidar
 * cachés desde el contenedor y desde cada panel.
 */
import { ApiError } from "@/lib/api";

export const CLAVE_IMAGEN = ["conexiones", "imagen"];
export const CLAVE_METRICOOL = ["conexiones", "metricool"];
export const CLAVE_POSTPROXY = ["conexiones", "postproxy"];
export const CLAVE_GOOGLE_ANALYTICS = ["conexiones", "google-analytics"];
export const CLAVE_GA_PROPIEDADES = ["conexiones", "google-analytics", "propiedades"];
export const CLAVE_FUENTES_STOCK = ["stock", "fuentes"];
export const CLAVE_AGENCIAS = ["stock", "agencias"];
export const CLAVE_AJUSTES = ["ajustes"];

/** Proveedores de imagen IA disponibles (gateway único OpenRouter). */
export const PROVEEDORES = [{ id: "openrouter", nombre: "OpenRouter (gateway de IA)" }];

/** Grupos de la sección «Máquina de contenido» del drawer del Monitor (proceso de PRODUCCIÓN,
 *  ADR 0011): el interruptor general, el maestro de Producción (Producción/Arte), sus excepciones
 *  por marca y la admisión del flujo continuo. Debe coincidir con `ajustes_catalogo.GRUPOS_MAQUINA`
 *  del backend. */
export const GRUPOS_MAQUINA = new Set([
  "maquina_global",
  "maestros_produccion",
  "automatizacion_marca_produccion",
  "pipeline_topes",
]);

/** Grupos de la sección «Investigación» del MISMO drawer del Monitor (Fase 3: UN solo sitio para
 *  los ajustes de la máquina): el maestro del proceso, sus excepciones por marca y el motor de
 *  noticias completo. `noticias_produccion_marca` (plan diario
 *  por marca) NO se pinta: su editor único es «Plan y horarios» de Programación. Debe coincidir
 *  con `ajustes_catalogo.GRUPOS_INVESTIGACION` del backend; el orden es el de pintado. */
export const GRUPOS_INVESTIGACION = [
  "maestros_investigacion",
  "automatizacion_marca_investigacion",
  "noticias_entrada",
  "noticias_rendimiento",
  "noticias_produccion",
  "noticias_tecnico",
] as const;

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
