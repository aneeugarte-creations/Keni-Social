// Google Trends como origen de una fuente: helpers de presentación compartidos por la página
// de Noticias. Trends guarda cada nota con el nombre del medio que cubrió el tema (un outlet
// suelto, a menudo extranjero); para que se vea de dónde viene, se marca "(Google Trends)".

/** ID de fuente de todo lo que llega de Google Trends (espejo de `FUENTE_ID` en el backend). */
export const FUENTE_ID_TRENDS = "google-trends";

/** True si la fuente proviene del descubridor de Google Trends. */
export function esFuenteTrends(fuenteId?: string | null): boolean {
  return fuenteId === FUENTE_ID_TRENDS;
}

/**
 * Nombre de fuente para mostrar, con "(Google Trends)" cuando viene del descubridor. Si el medio
 * concreto no se conoce, cae a "Google Trends" a secas.
 */
export function nombreFuente(nombre?: string | null, fuenteId?: string | null): string {
  const base = (nombre ?? "").trim();
  if (esFuenteTrends(fuenteId)) {
    return base ? `${base} (Google Trends)` : "Google Trends";
  }
  return base;
}
