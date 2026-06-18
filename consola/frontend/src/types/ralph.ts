// Tipos del overlay Ralph: agentes de desarrollo persistentes que se gestionan
// desde la burbuja naranja global. Reflejan el contrato `/api/ralph/*` (proxy
// admin al worker-ralph). El texto orientado al usuario llega en español.

/** Estado de un Ralph; gobierna el color de su bolita en el panel. */
export type EstadoRalph = "idle" | "activo" | "esperando" | "error";

/** Modelo con el que corre un Ralph. `opus` es el predeterminado del lanzador. */
export type ModeloRalph = "opus" | "sonnet" | "haiku";

/**
 * Tipo de Ralph:
 * - `operativo`: asistente del equipo de redes con el MCP de la app (lo ve todo el equipo).
 * - `dev`: agente de desarrollo sobre el repo (solo superadmin).
 */
export type TipoRalph = "operativo" | "dev";

/** Un agente Ralph en el pool. `nombre` viene del pool del back (ziggy, nova…). */
export interface Ralph {
  id: string;
  nombre: string;
  modelo: ModeloRalph;
  tipo: TipoRalph;
  estado: EstadoRalph;
  creado: string;
}

/** Quién emitió un mensaje de la conversación con un Ralph. */
export type AutorMensajeRalph = "tu" | "ralph";

/** Un mensaje de la conversación con un Ralph (se acumula a partir de deltas SSE). */
export interface MensajeRalph {
  id: string;
  autor: AutorMensajeRalph;
  texto: string;
  creado: string;
}

// ── Eventos SSE de `/api/ralph/{id}/stream` ──────────────────────────────────
/** Delta del evento `mensaje`: fragmento de texto a anexar a la conversación. */
export interface DeltaMensajeRalph {
  /** Quién habla; def `ralph` (el back solo emite los suyos por el stream). */
  autor?: AutorMensajeRalph;
  /** Fragmento a anexar (token a token, como las generaciones de copy). */
  delta: string;
  /** `true` cuando el mensaje actual queda cerrado (corta el "escribiendo…"). */
  fin?: boolean;
}

// ── Respuestas de la API ─────────────────────────────────────────────────────
/** `GET /api/ralph` → lista del pool + si el carril está disponible + rol del usuario. */
export interface RespuestaRalphs {
  disponible: boolean;
  /** El usuario es superadmin: puede lanzar también Ralphs de desarrollo (tipo `dev`). */
  superadmin: boolean;
  ralphs: Ralph[];
}

/** `POST /api/ralph/spawn` → el Ralph recién creado. */
export interface RespuestaRalph {
  ralph: Ralph;
}

/** Respuesta de acciones simples (`mensaje`, `kill`). */
export interface RespuestaOkRalph {
  ok: boolean;
}

/** Cuerpo de `POST /api/ralph/spawn`. */
export interface CuerpoSpawnRalph {
  prompt: string;
  modelo?: ModeloRalph;
  /** Tipo de Ralph; def `operativo`. `dev` requiere superadmin (lo valida el back). */
  tipo?: TipoRalph;
}
