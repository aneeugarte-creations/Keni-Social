import type { ContenidoPlataforma } from "./contenido";

// --- Ola COLABORACIÓN: comentarios internos + versiones de copy + aprobación
//     multinivel sobre el tablero de contenido (inspirado en Planable). ---

/** Un comentario del hilo de discusión de una pieza. `plataforma_id` vacío = comentario
 *  del item entero; con valor = atado a una red concreta. `resuelto` marca el hilo cerrado. */
export interface ComentarioContenido {
  id: string;
  contenido_id: string;
  plataforma_id: string;
  autor_id: string;
  autor_nombre: string;
  texto: string;
  resuelto: boolean;
  creado: string;
  actualizado: string;
  /** Ids de usuarios mencionados (@) en el comentario. */
  menciones: string[];
}

export interface RespuestaComentarios {
  comentarios: ComentarioContenido[];
  total: number;
}

export interface RespuestaComentario {
  comentario: ComentarioContenido;
}

/** Un snapshot inmutable del copy de una plataforma (historial de versiones). `version`
 *  es el contador incremental 1-based por plataforma. */
export interface CopyVersion {
  id: string;
  plataforma_id: string;
  contenido_id: string;
  version: number;
  copy: string;
  autor_id: string;
  autor_nombre: string;
  nota: string;
  creado: string;
}

export interface RespuestaCopyVersiones {
  versiones: CopyVersion[];
  total: number;
  copy_actual: string;
}

/** Respuesta al guardar/revertir copy: la plataforma actualizada (+ la versión creada). */
export interface RespuestaCopyGuardado {
  plataforma: ContenidoPlataforma;
  version: CopyVersion | null;
}

export type DecisionAprobacion = "pendiente" | "aprobado" | "rechazado";

/** Un nivel de la cadena de aprobación multinivel de una pieza, con su decisión y traza. */
export interface NivelAprobacion {
  id: string;
  plataforma_id: string;
  contenido_id: string;
  nivel: number;
  etiqueta: string;
  decision: DecisionAprobacion;
  decisor_id: string;
  decisor_nombre: string;
  comentario: string;
  creado: string;
  decidido_en: string;
  /** Cargo del organigrama exigido para decidir este nivel ("" = sin requisito). Item C. */
  cargo_requerido: string;
}

/** Estado GLOBAL de una cadena: sin_cadena | pendiente | aprobado | rechazado. */
export type EstadoCadenaAprobacion =
  | "sin_cadena"
  | "pendiente"
  | "aprobado"
  | "rechazado";

export interface CadenaAprobacion {
  niveles: NivelAprobacion[];
  estado: EstadoCadenaAprobacion;
  /** Id del nivel que toca decidir ("" si la cadena no espera decisión). */
  nivel_actual: string;
  /** Niveles ya aprobados (gate A: cuántas firmas lleva). */
  aprobados: number;
  /** Mínimo de aprobaciones exigido para programar (gate A; 0 = gate desactivado). */
  minimo_aprobaciones: number;
  /** Comentarios sin resolver que bloquean publicar (gate B). */
  comentarios_sin_resolver: number;
}

/** Respuesta de decidir un nivel: el nivel actualizado + el estado global y la cadena. */
export interface RespuestaDecisionAprobacion {
  nivel: NivelAprobacion;
  estado: EstadoCadenaAprobacion;
  niveles: NivelAprobacion[];
}

/**
 * Respuesta del batch de cadenas del feed (`GET /api/publicaciones/cadenas?ids=`):
 * SIEMPRE una entrada por id pedida (las piezas sin cadena/inexistentes salen con
 * `estado="sin_cadena"` y `niveles=[]`, nunca se omiten).
 */
export interface RespuestaCadenasLote {
  cadenas: Record<string, CadenaAprobacion>;
}
