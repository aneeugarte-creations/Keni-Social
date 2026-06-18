// Fragmento del cliente API: dominio «sugerencias» (kanban de auto-desarrollo).
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion } from "./_core";
import type {
  AccionCheckpoint,
  CuerpoActualizarSugerencia,
  CuerpoCrearSugerencia,
  RespuestaGeneracion,
  RespuestaMensaje,
  RespuestaPromoverSugerencia,
  RespuestaSugerencia,
  RespuestaSugerencias,
} from "@/types";

const enc = encodeURIComponent;

export const apiSugerencias = {
  // --- CRUD ---
  sugerencias: (signal?: AbortSignal) =>
    peticion<RespuestaSugerencias>("/sugerencias", { signal }),
  crearSugerencia: (cuerpo: CuerpoCrearSugerencia) =>
    peticion<RespuestaSugerencia>("/sugerencias", { metodo: "POST", json: cuerpo }),
  actualizarSugerencia: (id: string, cuerpo: CuerpoActualizarSugerencia) =>
    peticion<RespuestaSugerencia>(`/sugerencias/${enc(id)}`, {
      metodo: "PATCH",
      json: cuerpo,
    }),
  eliminarSugerencia: (id: string) =>
    peticion<RespuestaMensaje>(`/sugerencias/${enc(id)}`, { metodo: "DELETE" }),

  // --- Flujo de desarrollo ---
  // Lanza el wizard L1: genera el SPEC y estima complejidad.
  discoverySugerencia: (id: string) =>
    peticion<RespuestaGeneracion>(`/sugerencias/${enc(id)}/discovery`, { metodo: "POST" }),
  // Mueve a en_cola y encola el pipeline de desarrollo (analyze→plan→build→review).
  construirSugerencia: (id: string) =>
    peticion<RespuestaGeneracion>(`/sugerencias/${enc(id)}/construir`, { metodo: "POST" }),
  // Checkpoint humano sobre una pieza en revisión.
  checkpointSugerencia: (id: string, accion: AccionCheckpoint, comentario?: string) =>
    peticion<RespuestaSugerencia>(`/sugerencias/${enc(id)}/checkpoint`, {
      metodo: "POST",
      json: { accion, comentario },
    }),
  // Promueve la rama dev a main (checkpoint humano final).
  promoverSugerencia: (id: string) =>
    peticion<RespuestaPromoverSugerencia>(`/sugerencias/${enc(id)}/promover`, { metodo: "POST" }),
};
