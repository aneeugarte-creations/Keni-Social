/**
 * Utilidades compartidas de generaciones de IA.
 *
 * Fuente de verdad única para el mapeo tipo → etiqueta legible en español.
 * Se usa en la tabla de Actividad (columna Tipo), el desplegable de filtro
 * y cualquier componente que muestre el tipo de una generación.
 */

/** Mapa tipo → etiqueta legible para los tipos de generación conocidos. */
export const ETIQUETAS_TIPO_GENERACION: Record<string, string> = {
  copy: "Redactar",
  rss: "RSS",
  imagen: "Imagen",
  verificacion: "Verificar",
  "revision": "revisión editorial",
  autogen: "Auto-copy",
  "sugerir-hashtags": "Sugerir hashtags",
  run: "Run",
  pipeline: "Pipeline",
  insumos: "Cajones del día",
  "import-calendario": "Importar calendario",
  "render-video": "Render de video",
  transcribir: "Transcripción",
};

/**
 * Devuelve la etiqueta legible de un tipo de generación.
 * Si el tipo no está en el mapa, devuelve el raw tipo como fallback.
 */
export function etiquetaTipoGeneracion(tipo: string): string {
  return ETIQUETAS_TIPO_GENERACION[tipo] ?? tipo;
}
