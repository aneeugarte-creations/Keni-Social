// Fragmento del cliente API: dominio «clips» (cajón de Fuentes → Internas, Claro Sports).
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion, query } from "./_core";
import type { CuerpoCrearClip, RespuestaClips, RespuestaCrearClip } from "@/types";

export const apiClips = {
  // --- Cajón Clips: vídeo/foto de WhatsApp -> pieza automática (video|carrusel) ---
  clips: (params: { marca?: string } = {}, signal?: AbortSignal) =>
    peticion<RespuestaClips>(`/clips${query(params)}`, { signal }),
  crearClip: (cuerpo: CuerpoCrearClip) =>
    peticion<RespuestaCrearClip>("/clips", {
      metodo: "POST",
      json: cuerpo,
    }),
};
