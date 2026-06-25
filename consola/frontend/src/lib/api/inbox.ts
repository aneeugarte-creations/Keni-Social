// Fragmento del cliente API: dominio «inbox» (DMs y comentarios de FB/IG, solo lectura).
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion, query } from "./_core";
import type { RespuestaInboxComentarios, RespuestaInboxConversaciones } from "@/types";

export const apiInbox = {
  // --- Inbox de SOLO lectura (Metricool: Facebook/Instagram) ---
  // Mensajes directos de una marca. `marca` viaja en forma id_metricas (guion_bajo),
  // igual que el resto de fronteras de Métricas; obligatorio (sin él/desconocida → 400).
  inboxConversaciones: (params: { marca: string }, signal?: AbortSignal) =>
    peticion<RespuestaInboxConversaciones>(`/inbox/conversaciones${query(params)}`, { signal }),
  // Comentarios de publicaciones de los últimos `dias` (1..30, def 7 en el backend). El back
  // trocea por día y puede tardar varios segundos con `dias` alto: techo de tiempo amplio.
  inboxComentarios: (params: { marca: string; dias?: string }, signal?: AbortSignal) =>
    peticion<RespuestaInboxComentarios>(`/inbox/comentarios${query(params)}`, {
      signal,
      timeoutMs: 60_000,
    }),
};
