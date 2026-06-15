/**
 * Metadatos de presentación de los agentes/daemons de la máquina, en UN solo sitio (los consumen
 * la página Agentes y el detalle de agente). Son lo único que el latido del API (`LatidoDaemon`)
 * aún NO expone: la etiqueta humana del daemon y los prompts de la Biblioteca que gobiernan a
 * cada agente IA. Todo lo demás (clase, motor, estado, si gasta tokens, barrible…) se lee del API.
 *
 * TODO(backend): cuando el latido exponga `etiqueta` y `prompts`, estos mapas desaparecen y la UI
 * deja de tener que conocer los nombres de daemon de antemano.
 */

/** Nombre legible de cada daemon conocido; los no mapeados caen al nombre crudo capitalizado. */
const ETIQUETA_DAEMON: Record<string, string> = {
  investigacion: "Investigación",
  produccion: "Producción",
  recolectar: "Recolección de noticias",
  trends: "Tendencias",
  algoritmos: "Algoritmos de plataforma",
  noticias_gc: "GC de noticias",
  programador: "Programador de parrilla",
  vencimientos: "Vencimientos",
  comercial: "Comercial",
  metricas: "Métricas",
  metricas_piezas: "Métricas de piezas",
  alertas_rendimiento: "Alertas de rendimiento",
  media_gc: "GC de media",
  patrones: "Patrones de marca",
  reaper: "Reaper (cola)",
};

/** Un prompt de la Biblioteca que gobierna un agente IA (etiqueta visible + doc id). */
export interface PromptDaemon {
  etiqueta: string;
  doc: string;
}

/** Prompts de la Biblioteca que gobiernan cada agente de IA, por NOMBRE de daemon (el mismo
 *  mapeo que usan los cockpits de Investigación/Producción). Solo clase=ia tiene prompt. */
export const PROMPTS_POR_DAEMON: Record<string, PromptDaemon[]> = {
  investigacion: [{ etiqueta: "Verificar", doc: "prompt/verificar" }],
  produccion: [
    { etiqueta: "Redactar", doc: "prompt/redactar" },
    { etiqueta: "Ilustrar", doc: "prompt/ilustrar" },
  ],
};

/** Nombre legible de un daemon (mapa conocido, o el nombre crudo capitalizado). */
export function nombreLegible(daemon: string): string {
  return ETIQUETA_DAEMON[daemon] ?? daemon.charAt(0).toUpperCase() + daemon.slice(1);
}
