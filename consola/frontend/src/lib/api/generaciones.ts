// Fragmento del cliente API: dominio «generaciones». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion } from "./_core";
import type {
  CuerpoGuardarHistorial,
  RespuestaGeneracion,
  RespuestaGeneraciones,
  RespuestaPublicaciones,
} from "@/types";

export const apiGeneraciones = {
  // --- Generaciones (sondeo de trabajos de IA en segundo plano) ---
  // Toda generación (copy/RSS/hashtags/imagen) responde de inmediato con `{generacion}`
  // (estado "ejecutando"); se sondea aquí hasta el estado terminal.
  generaciones: (signal?: AbortSignal) =>
    peticion<RespuestaGeneraciones>("/generaciones", { signal }),
  generacion: (id: string, signal?: AbortSignal) =>
    peticion<RespuestaGeneracion>(`/generaciones/${encodeURIComponent(id)}`, { signal }),
  // Cancela un trabajo en vuelo (#137): el backend mata el árbol del subproceso `claude`
  // y devuelve el registro en su estado terminal (error/motivo=cancelado). Idempotente.
  cancelarGeneracion: (id: string) =>
    peticion<RespuestaGeneracion>(`/generaciones/${encodeURIComponent(id)}/cancelar`, {
      metodo: "POST",
    }),

  // --- Historial de generaciones (NEUTRO; común a copy/documento) ---
  // Guardar una entrada del historial como publicaciones (borradores). El listado/detalle
  // del historial ya no tiene página propia.
  guardarHistorial: (id: string, cuerpo: CuerpoGuardarHistorial = {}) =>
    peticion<RespuestaPublicaciones>(`/prompts/historial/${encodeURIComponent(id)}/guardar`, {
      metodo: "POST",
      json: cuerpo,
    }),

};
