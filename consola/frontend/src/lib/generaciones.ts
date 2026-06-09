/**
 * Utilidades compartidas de generaciones de IA.
 *
 * Fuente de verdad única para el mapeo tipo → etiqueta legible en español.
 * Se usa en la tabla de Actividad (columna Tipo), el desplegable de filtro
 * y cualquier componente que muestre el tipo de una generación.
 */

/** Mapa tipo → etiqueta legible para los tipos de generación conocidos. */
export const ETIQUETAS_TIPO_GENERACION: Record<string, string> = {
  copy: "Copy",
  rss: "RSS",
  imagen: "Imagen",
  verificacion: "Verificación",
  "qa-editorial": "QA editorial",
  autogen: "Auto-copy",
  run: "Run",
  pipeline: "Pipeline",
  insumos: "Cajones del día",
  // Etiqueta retenida para registros históricos: ya no se crean generaciones de
  // investigación (Agentes retirados), pero el historial puede tener tipo='investigacion'.
  investigacion: "Investigación",
  "import-calendario": "Importar calendario",
  "render-video": "Render de video",
  transcribir: "Transcripción",
  // Etiquetas retenidas para registros HISTÓRICOS: todo el trabajo de la máquina se sella
  // ahora tipo='pipeline' (criba QA, copy, arte, fusión/encaje del pool); estos tipos ya no
  // se crean pero el historial los trae.
  "noticias-ia": "IA de noticias",
  "qa-fuente": "Criba de fuente",
};

/**
 * Devuelve la etiqueta legible de un tipo de generación.
 * Si el tipo no está en el mapa, devuelve el raw tipo como fallback.
 */
export function etiquetaTipoGeneracion(tipo: string): string {
  return ETIQUETAS_TIPO_GENERACION[tipo] ?? tipo;
}
