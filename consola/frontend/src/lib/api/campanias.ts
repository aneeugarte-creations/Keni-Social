// Fragmento del cliente API: dominio «campañas» (agrupan piezas por hashtag; analítica al
// vuelo). El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { descargar, peticion, query } from "./_core";
import type {
  AnaliticaCampania,
  CuerpoActualizarCampania,
  CuerpoCrearCampania,
  RespuestaCampania,
  RespuestaCampanias,
  RespuestaMensaje,
} from "@/types";

export const apiCampanias = {
  // --- Campañas (agrupan piezas por hashtag; analítica al vuelo) ---
  campanias: (params: { marca?: string } = {}, signal?: AbortSignal) =>
    peticion<RespuestaCampanias>(`/campanias${query(params)}`, { signal }),
  campania: (id: string, signal?: AbortSignal) =>
    peticion<RespuestaCampania>(`/campanias/${encodeURIComponent(id)}`, { signal }),
  crearCampania: (cuerpo: CuerpoCrearCampania) =>
    peticion<RespuestaCampania>("/campanias", { metodo: "POST", json: cuerpo }),
  actualizarCampania: (id: string, cuerpo: CuerpoActualizarCampania) =>
    peticion<RespuestaCampania>(`/campanias/${encodeURIComponent(id)}`, {
      metodo: "PUT",
      json: cuerpo,
    }),
  eliminarCampania: (id: string) =>
    peticion<RespuestaMensaje>(`/campanias/${encodeURIComponent(id)}`, {
      metodo: "DELETE",
    }),
  analiticaCampania: (id: string, params: { rango?: string } = {}, signal?: AbortSignal) =>
    peticion<AnaliticaCampania>(
      `/campanias/${encodeURIComponent(id)}/analitica${query(params)}`,
      // La 1a carga de un combo frío descarga miles de posts+reels de Metricool (luego se
      // cachea y es instantánea). Techo amplio para que no la corte el timeout por defecto.
      { signal, timeoutMs: 90_000 },
    ),
  // Descarga la analítica de la campaña en csv|md|json (mismo dato que el panel; el backend
  // abre la URL con cabecera de descarga). `ocultarAds` replica el "modo cliente" (sin pauta).
  exportarCampania: (
    id: string,
    formato: "csv" | "md" | "json",
    params: { rango?: string; ocultarAds?: boolean } = {},
  ) =>
    descargar(
      `/campanias/${encodeURIComponent(id)}/export${query({
        fmt: formato,
        rango: params.rango,
        ocultar_ads: params.ocultarAds ? "1" : undefined,
      })}`,
    ),
};
