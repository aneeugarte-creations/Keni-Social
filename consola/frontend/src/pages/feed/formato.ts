/**
 * FORMATO de una pieza (foto|video|carrusel) — espejo del backend (`redes.redes_de_formato`).
 *
 * Regla del dueño: una pieza FOTO va a 3 redes (instagram, x, facebook); una VIDEO a las 5;
 * un CARRUSEL a 2 (instagram, facebook: carruseles nativos — portada compuesta + slides en
 * crudo). El flujo automático crea piezas FOTO. El humano ve un BADGE explícito
 * ("Foto"/"Video"/"Carrusel") para saber al instante de qué tipo de post se trata.
 *
 * Esta tabla NO es la fuente de verdad (lo es el backend): solo da la ETIQUETA y el nº de redes
 * para el badge. Desconocido/"" -> foto (el default seguro del backend).
 */

/** Formatos canónicos de pieza. */
export type Formato = "foto" | "video" | "carrusel";

/**
 * Clases estáticas (Tailwind las detecta) por nº de columnas de las rejillas del feed. Sin
 * prefijo responsive: aplican en TODOS los anchos. Único export compartido por la rejilla
 * plana de `FeedIdeacion` y la matriz interna de `GrupoIdea` (antes eran clones).
 */
export const GRID_COLS: Record<number, string> = {
  1: "grid-cols-1",
  2: "grid-cols-2",
  3: "grid-cols-3",
  4: "grid-cols-4",
  5: "grid-cols-5",
};

/**
 * Tope de ANCHURA del feed por nº de columnas EFECTIVAS: en monitores anchos una celda no
 * debe pasar de ~480-540px (la tarjeta pierde densidad y el copy se desparrama). Lo aplican
 * los TRES contenedores del feed (skeleton, grupos y rejilla plana) con `mx-auto w-full`.
 */
export const MAX_W_FEED: Record<number, string> = {
  // A 1 columna el tope respeta la regla de arriba: 576px (cercano al canon de feed social
  // ~600px) e igualado con el `max-w-xl` del feed móvil. Con `max-w-2xl` (672px) la imagen
  // 4:5 medía ~840px de alto y la línea de copy llegaba a ~90 caracteres.
  1: "max-w-xl",
  2: "max-w-4xl",
  3: "max-w-6xl",
  4: "max-w-screen-2xl",
  5: "max-w-screen-2xl",
};

// Pares de tono CANÓNICOS del design system (mismos 700/300 que `ui/badge.tsx` y
// `META_ESTADOS`): un solo verde para "OK/lista", un solo ámbar para "pendiente/atención"
// y un solo rojo para "rechazo/error" en toda la tarjeta del feed.
export const TEXTO_OK = "text-emerald-700 dark:text-emerald-300";
export const TEXTO_AVISO = "text-amber-700 dark:text-amber-300";
export const TEXTO_ERROR = "text-red-700 dark:text-red-300";

/**
 * Redes destino por formato — espejo EXACTO de `redes.redes_de_formato` del backend
 * (`consola/src/keni_consola/redes.py`): foto → instagram/x/facebook; video → las 5.
 * La matriz del feed lo usa para NO pintar huecos "No generado" en redes a las que la
 * idea nunca irá (una foto jamás genera TikTok/YouTube).
 */
export const REDES_POR_FORMATO: Record<Formato, readonly string[]> = {
  foto: ["instagram", "x", "facebook"],
  video: ["x", "instagram", "facebook", "tiktok", "youtube"],
  carrusel: ["instagram", "facebook"],
};

/** Etiqueta humana + nº de redes destino por formato (derivado de `REDES_POR_FORMATO`). */
const FORMATOS: Record<Formato, { etiqueta: string; redes: number }> = {
  foto: { etiqueta: "Foto", redes: REDES_POR_FORMATO.foto.length },
  video: { etiqueta: "Video", redes: REDES_POR_FORMATO.video.length },
  carrusel: { etiqueta: "Carrusel", redes: REDES_POR_FORMATO.carrusel.length },
};

/** Formato canónico desde un valor crudo del backend; "" / desconocido -> "foto". */
export function normalizarFormato(formato: string | null | undefined): Formato {
  const f = (formato ?? "").trim().toLowerCase();
  return f === "video" || f === "carrusel" ? f : "foto";
}

/** Etiqueta humana del formato para la UI ("Foto"/"Video"/"Carrusel"). Desconocido -> "Foto". */
export function etiquetaFormato(formato: string | null | undefined): string {
  return FORMATOS[normalizarFormato(formato)].etiqueta;
}

/** Nº de redes destino del formato (foto=3, video=5, carrusel=2). Para el tooltip del badge. */
export function redesDeFormato(formato: string | null | undefined): number {
  return FORMATOS[normalizarFormato(formato)].redes;
}
