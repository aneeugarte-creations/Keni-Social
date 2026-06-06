/**
 * FORMATO de una pieza (foto|video) — espejo del backend (`redes.redes_de_formato`).
 *
 * Regla del dueño: una pieza FOTO va a 3 redes (instagram, x, facebook); una VIDEO a las 5.
 * El flujo automático crea piezas FOTO. El humano ve un BADGE explícito ("Foto"/"Video") para
 * saber al instante de qué tipo de post se trata (y, por tanto, a cuántas redes va).
 *
 * Esta tabla NO es la fuente de verdad (lo es el backend): solo da la ETIQUETA y el nº de redes
 * para el badge. Desconocido/"" -> foto (el default seguro del backend).
 */

/** Formatos canónicos de pieza. */
export type Formato = "foto" | "video";

/** Etiqueta humana + nº de redes destino por formato (espejo del backend). */
const FORMATOS: Record<Formato, { etiqueta: string; redes: number }> = {
  foto: { etiqueta: "Foto", redes: 3 },
  video: { etiqueta: "Video", redes: 5 },
};

/** Formato canónico desde un valor crudo del backend; "" / desconocido -> "foto". */
export function normalizarFormato(formato: string | null | undefined): Formato {
  const f = (formato ?? "").trim().toLowerCase();
  return f === "video" ? "video" : "foto";
}

/** Etiqueta humana del formato para la UI ("Foto"/"Video"). Desconocido -> "Foto". */
export function etiquetaFormato(formato: string | null | undefined): string {
  return FORMATOS[normalizarFormato(formato)].etiqueta;
}

/** Nº de redes destino del formato (foto=3, video=5). Para el tooltip del badge. */
export function redesDeFormato(formato: string | null | undefined): number {
  return FORMATOS[normalizarFormato(formato)].redes;
}
