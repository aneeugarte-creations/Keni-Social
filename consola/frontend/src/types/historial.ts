// --- Historial de generaciones de prompts ---
// (El listado/detalle del historial por HTTP se retiró en la consolidación;
// queda solo el cuerpo de "guardar como publicación".)

/**
 * Cuerpo opcional para recuperar una entrada del historial como publicación(es)
 * (`POST /api/prompts/historial/{id}/guardar`). Si la entrada no tiene piezas,
 * hay que indicar `red`; si las tiene, `redes` permite acotar cuáles guardar.
 */
export interface CuerpoGuardarHistorial {
  titulo?: string;
  /** Subconjunto de redes a guardar (cuando la entrada tiene piezas). */
  redes?: string[];
  /** Red obligatoria cuando la entrada no tiene piezas. */
  red?: string;
}
