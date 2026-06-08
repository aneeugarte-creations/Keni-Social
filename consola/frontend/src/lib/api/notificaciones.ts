// Fragmento del cliente API: dominio «notificaciones». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion, query } from "./_core";
import type {
  RespuestaContadorNotificaciones,
  RespuestaMencionesCandidatos,
  RespuestaNotificaciones,
} from "@/types";

export const apiNotificaciones = {
  // --- Notificaciones in-app (el "cajón" de la campana, acotado a la marca activa) ---
  notificaciones: (marcaId?: string, signal?: AbortSignal) =>
    peticion<RespuestaNotificaciones>(`/notificaciones${query({ marca_id: marcaId })}`, { signal }),
  contadorNotificaciones: (marcaId?: string, signal?: AbortSignal) =>
    peticion<RespuestaContadorNotificaciones>(
      `/notificaciones/contador${query({ marca_id: marcaId })}`,
      { signal },
    ),
  marcarNotificacionLeida: (id: string) =>
    peticion<{ ok: boolean }>(`/notificaciones/${encodeURIComponent(id)}/leer`, { metodo: "POST" }),
  marcarNotificacionesLeidas: (marcaId?: string) =>
    peticion<{ marcadas: number }>(`/notificaciones/leer-todas${query({ marca_id: marcaId })}`, {
      metodo: "POST",
    }),
  mencionesCandidatos: (marcaId?: string, signal?: AbortSignal) =>
    peticion<RespuestaMencionesCandidatos>(
      `/notificaciones/menciones-candidatos${query({ marca_id: marcaId })}`,
      { signal },
    ),

};
