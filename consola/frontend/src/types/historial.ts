import type { PiezaGenerada } from "./comun";

// --- Historial de generaciones de prompts ---

export interface EntradaHistorial {
  id: string;
  prompt: string;
  prompt_nombre: string;
  marca: string;
  marca_nombre: string;
  fecha: string;
  preview: string;
  /** Atribución por usuario (#130 Fase 1): id estable de quien generó. "" si legado/anónimo. */
  autor_id: string;
  /** Nombre de quien generó (para mostrar). "" si legado/anónimo. */
  autor_nombre: string;
}

export interface RespuestaHistorial {
  historial: EntradaHistorial[];
}

export interface DetalleHistorial {
  id: string;
  prompt: string;
  marca: string;
  fecha: string;
  resultado: string;
  /** Título de la generación (puede venir vacío en entradas antiguas). */
  titulo: string;
  /** Piezas por red (pueden venir vacías en entradas antiguas). */
  piezas: PiezaGenerada[];
  /** Atribución por usuario (#130 Fase 1): id estable de quien generó. "" si legado/anónimo. */
  autor_id: string;
  /** Nombre de quien generó (para mostrar). "" si legado/anónimo. */
  autor_nombre: string;
}

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
