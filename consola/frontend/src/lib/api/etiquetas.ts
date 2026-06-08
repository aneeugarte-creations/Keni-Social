// Fragmento del cliente API: dominio «etiquetas». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion } from "./_core";
import type {
  CuerpoActualizarEtiqueta,
  CuerpoCrearEtiqueta,
  RespuestaEtiqueta,
  RespuestaEtiquetas,
  RespuestaMensaje,
} from "@/types";

export const apiEtiquetas = {
  // --- Catálogo de etiquetas editoriales (campaña / vertical / tipo) ---
  etiquetas: (
    params: { marca?: string; clase?: string; activas?: boolean } = {},
    signal?: AbortSignal,
  ) => {
    const qs = new URLSearchParams();
    if (params.marca !== undefined) qs.set("marca", params.marca);
    if (params.clase) qs.set("clase", params.clase);
    if (params.activas) qs.set("activas", "1");
    const cola = qs.toString();
    return peticion<RespuestaEtiquetas>(`/etiquetas${cola ? `?${cola}` : ""}`, { signal });
  },
  crearEtiqueta: (cuerpo: CuerpoCrearEtiqueta) =>
    peticion<RespuestaEtiqueta>("/etiquetas", { metodo: "POST", json: cuerpo }),
  actualizarEtiqueta: (id: string, cuerpo: CuerpoActualizarEtiqueta) =>
    peticion<RespuestaEtiqueta>(`/etiquetas/${encodeURIComponent(id)}`, {
      metodo: "PATCH",
      json: cuerpo,
    }),
  eliminarEtiqueta: (id: string) =>
    peticion<RespuestaMensaje>(`/etiquetas/${encodeURIComponent(id)}`, { metodo: "DELETE" }),

};
