// Fragmento del cliente API: dominio «vistas guardadas» de Analíticas (presets nombrados
// que congelan config de vista + marca + periodo). El objeto compuesto vive en ./index.ts;
// aquí solo el fragmento + sus imports.
import { peticion, query } from "./_core";
import type {
  CuerpoActualizarVista,
  CuerpoCrearVista,
  RespuestaVista,
  RespuestaVistas,
} from "@/types";
import type { RespuestaMensaje } from "@/types";

export const apiVistas = {
  vistas: (params: { marca?: string } = {}, signal?: AbortSignal) =>
    peticion<RespuestaVistas>(`/metricas/vistas${query(params)}`, { signal }),
  crearVista: (cuerpo: CuerpoCrearVista) =>
    peticion<RespuestaVista>("/metricas/vistas", { metodo: "POST", json: cuerpo }),
  actualizarVista: (id: string, cuerpo: CuerpoActualizarVista) =>
    peticion<RespuestaVista>(`/metricas/vistas/${encodeURIComponent(id)}`, {
      metodo: "PUT",
      json: cuerpo,
    }),
  eliminarVista: (id: string) =>
    peticion<RespuestaMensaje>(`/metricas/vistas/${encodeURIComponent(id)}`, {
      metodo: "DELETE",
    }),
};
