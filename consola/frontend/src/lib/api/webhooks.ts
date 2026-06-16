// Fragmento del cliente API: dominio «webhooks». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion } from "./_core";
import type {
  CuerpoActualizarWebhook,
  CuerpoCrearWebhook,
  RespuestaMensaje,
  RespuestaMetricasPublicacion,
  RespuestaPreviewPublicacion,
  RespuestaProbarWebhook,
  RespuestaWebhook,
  RespuestaWebhooks,
} from "@/types";

export const apiWebhooks = {
  // --- Webhooks salientes + eventos internos del tablero ---
  webhooks: (signal?: AbortSignal) =>
    peticion<RespuestaWebhooks>("/webhooks", { signal }),
  crearWebhook: (cuerpo: CuerpoCrearWebhook) =>
    peticion<RespuestaWebhook>("/webhooks", { metodo: "POST", json: cuerpo }),
  actualizarWebhook: (id: string, cuerpo: CuerpoActualizarWebhook) =>
    peticion<RespuestaWebhook>(`/webhooks/${encodeURIComponent(id)}`, {
      metodo: "PATCH",
      json: cuerpo,
    }),
  eliminarWebhook: (id: string) =>
    peticion<RespuestaMensaje>(`/webhooks/${encodeURIComponent(id)}`, { metodo: "DELETE" }),
  probarWebhook: (id: string) =>
    peticion<RespuestaProbarWebhook>(`/webhooks/${encodeURIComponent(id)}/probar`, {
      metodo: "POST",
    }),
  /** Rendimiento real (Metricool) por pieza publicada del tablero. Mapa por `pieza.id`. */
  metricasPublicacion: (signal?: AbortSignal) =>
    peticion<RespuestaMetricasPublicacion>("/publicaciones/metricas", { signal }),
  /** Previsualiza un copy con sus variables `{...}` ya sustituidas (no persiste). */
  previewPublicacion: (publicacionId: string, texto: string, signal?: AbortSignal) =>
    peticion<RespuestaPreviewPublicacion>(
      `/publicaciones/${encodeURIComponent(publicacionId)}/preview`,
      { metodo: "POST", json: { texto }, signal },
    ),
};
