// --- Buzón de sugerencias (kanban de auto-desarrollo) ---

/** Columna del kanban + estados terminales del flujo de desarrollo. */
export type EstadoSugerencia =
  | "nueva"
  | "discovery"
  | "en_cola"
  | "building"
  | "revision"
  | "hecha"
  | "fallida"
  | "descartada";

/** Estimación de esfuerzo del discovery; vacía hasta que se calcula. */
export type ComplejidadSugerencia = "" | "simple" | "standard" | "complex";

/** Acción humana sobre el checkpoint de una pieza en revisión. */
export type AccionCheckpoint = "continuar" | "cambios" | "cancelar";

export interface Sugerencia {
  id: string;
  titulo: string;
  detalle: string;
  categoria: string;
  autor: string;
  /** Id del usuario que la creó (clave de propiedad; el resto del equipo solo ve las suyas). */
  autor_id: string;
  estado: EstadoSugerencia | string;
  complejidad: ComplejidadSugerencia | string;
  /** Fase del pipeline en curso: ''|analyze|plan|build|review. */
  fase: string;
  /** Markdown del discovery (SPEC). */
  spec: string;
  /** Salida de la fase de plan. */
  plan: string;
  /** Generación en curso (link a /api/generaciones/{gen_id}). '' si no hay. */
  gen_id: string;
  /** Rama dev creada para la pieza. */
  rama: string;
  diff_resumen: string;
  coste_usd: number;
  /** Hay un preview navegable del cambio publicado en `/api/preview/<id>/`. */
  preview_listo?: boolean;
  creada: string;
  actualizada: string;
}

export interface RespuestaSugerencias {
  sugerencias: Sugerencia[];
  categorias: string[];
  estados: string[];
  /** `true` => la sesión es superadmin: ve el TABLERO completo. El resto solo sus ideas. */
  superadmin: boolean;
}

export interface RespuestaSugerencia {
  sugerencia: Sugerencia;
}

export interface CuerpoCrearSugerencia {
  titulo: string;
  detalle?: string;
  categoria?: string;
}

export interface CuerpoActualizarSugerencia {
  estado?: string;
  titulo?: string;
  detalle?: string;
  categoria?: string;
}

export interface CuerpoCheckpoint {
  accion: AccionCheckpoint;
  comentario?: string;
}

export interface RespuestaPromoverSugerencia {
  ok: boolean;
  detalle: string;
}
