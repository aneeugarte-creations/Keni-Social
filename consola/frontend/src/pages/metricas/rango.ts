/**
 * Helpers del "token de rango" que el dashboard de Métricas envía al backend.
 *
 * El backend (`resolver_rango`) acepta, además de los presets ("semana"|"mes"|…):
 *   - `mes:AAAA-MM`               → un mes concreto
 *   - `rango:AAAA-MM-DD_AAAA-MM-DD` → un rango personalizado (desde/hasta)
 *
 * El token viaja como string por toda la cadena (es también la clave de cache), así
 * que aquí solo construimos/parseamos ese string. La etiqueta legible la calcula el
 * backend (`etiqueta_rango`) y llega en cada respuesta.
 */

export type ModoTiempo = "atajos" | "mes" | "personalizado";

/** Modo de UI implícito en un token (para inicializar el selector desde el valor actual). */
export function modoDesdeToken(token: string): ModoTiempo {
  if (token.startsWith("mes:")) return "mes";
  if (token.startsWith("rango:")) return "personalizado";
  return "atajos";
}

/** `mes:AAAA-MM` a partir de año y mes (1-12). */
export function tokenMes(anio: number, mes: number): string {
  return `mes:${anio}-${String(mes).padStart(2, "0")}`;
}

/** `rango:AAAA-MM-DD_AAAA-MM-DD` a partir de dos fechas ISO. */
export function tokenRango(desde: string, hasta: string): string {
  return `rango:${desde}_${hasta}`;
}

/** Año y mes de un token `mes:`, o null si no lo es. */
export function partesMes(token: string): { anio: number; mes: number } | null {
  const m = /^mes:(\d{4})-(\d{2})$/.exec(token);
  return m ? { anio: Number(m[1]), mes: Number(m[2]) } : null;
}

/** Fechas de un token `rango:`, o null si no lo es. */
export function partesRango(token: string): { desde: string; hasta: string } | null {
  const m = /^rango:(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})$/.exec(token);
  return m ? { desde: m[1], hasta: m[2] } : null;
}
