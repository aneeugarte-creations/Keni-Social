// Fragmento del cliente API: dominio «fuentes». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion, query } from "./_core";
import type {
  CuerpoActualizarFuenteRss,
  CuerpoAportarFuente,
  CuerpoCrearFuenteRss,
  RespuestaActivarPresets,
  RespuestaAportarFuente,
  RespuestaFuenteRss,
  RespuestaFuentesHub,
  RespuestaFuentesRss,
  RespuestaMensaje,
  RespuestaPresets,
} from "@/types";

export const apiFuentes = {
  // --- RSS (solo gestión de fuentes/feeds; los items viven en el pool de Noticias) ---
  fuentesRss: (signal?: AbortSignal) => peticion<RespuestaFuentesRss>("/rss/fuentes", { signal }),
  crearFuenteRss: (cuerpo: CuerpoCrearFuenteRss) =>
    peticion<RespuestaFuenteRss>("/rss/fuentes", { metodo: "POST", json: cuerpo }),
  actualizarFuenteRss: (id: string, cuerpo: CuerpoActualizarFuenteRss) =>
    peticion<RespuestaFuenteRss>(`/rss/fuentes/${encodeURIComponent(id)}`, {
      metodo: "PUT",
      json: cuerpo,
    }),
  eliminarFuenteRss: (id: string) =>
    peticion<RespuestaMensaje>(`/rss/fuentes/${encodeURIComponent(id)}`, { metodo: "DELETE" }),

  // --- Catálogo de fuentes: la vista "Todas" lista los feeds (desde fuentes_rss, tipo='rss')
  // + el estado honesto de agencias (Reuters/AFP). Solo lectura. ---
  fuentesHub: (tipo?: string, signal?: AbortSignal) =>
    peticion<RespuestaFuentesHub>(`/fuentes${query({ tipo })}`, { signal }),
  // APORTACION MANUAL (idea / enlace pegado / contenido interno): crea un item REAL en el
  // tablero (`flujo='importante'`) con su `origen` y, best-effort, le lanza copy de fondo.
  aportarFuente: (cuerpo: CuerpoAportarFuente) =>
    peticion<RespuestaAportarFuente>("/fuentes/aportar", { metodo: "POST", json: cuerpo }),

  // --- Catálogo de presets (Ola 4: Fuentes externas + idiomas) ---
  // Lista el catálogo curado de feeds listos para activar, opcionalmente filtrado por categoría.
  // Marca cada preset con `activa: bool` si ya existe una `fuentes_rss` con esa URL.
  fuentesPresets: (categoria?: string, signal?: AbortSignal) =>
    peticion<RespuestaPresets>(
      `/fuentes/presets${query({ categoria })}`,
      { signal },
    ),
  // Activa los presets elegidos: crea `fuentes_rss` de forma idempotente por URL.
  activarPresets: (cuerpo: { ids: string[]; marca?: string }) =>
    peticion<RespuestaActivarPresets>("/fuentes/presets/activar", { metodo: "POST", json: cuerpo }),

};
