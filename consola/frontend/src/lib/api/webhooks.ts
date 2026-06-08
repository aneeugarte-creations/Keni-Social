// Fragmento del cliente API: dominio «webhooks». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion } from "./_core";
import type {
  CuerpoActualizarWebhook,
  CuerpoAsistenteContenido,
  CuerpoCrearWebhook,
  RespuestaGeneracion,
  RespuestaMensaje,
  RespuestaMetricasContenido,
  RespuestaPreviewContenido,
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
  /** Rendimiento real (Metricool) por pieza publicada del tablero. Mapa por `contenido_plataforma.id`. */
  metricasContenido: (signal?: AbortSignal) =>
    peticion<RespuestaMetricasContenido>("/contenido/metricas", { signal }),
  /** Previsualiza un copy con sus variables `{...}` ya sustituidas (no persiste). */
  previewContenido: (contenidoId: string, texto: string, signal?: AbortSignal) =>
    peticion<RespuestaPreviewContenido>(
      `/contenido/${encodeURIComponent(contenidoId)}/preview`,
      { metodo: "POST", json: { texto }, signal },
    ),
  /** Lanza el asistente IA sobre un contenido (genera/resume/3 variantes). */
  asistenteContenido: (contenidoId: string, cuerpo: CuerpoAsistenteContenido) =>
    peticion<RespuestaGeneracion>(
      `/contenido/${encodeURIComponent(contenidoId)}/asistente`,
      { metodo: "POST", json: cuerpo },
    ),

};
