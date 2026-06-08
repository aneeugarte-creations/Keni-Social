// Fragmento del cliente API: dominio «sugerencias». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion } from "./_core";
import type {
  CuerpoActualizarSugerencia,
  CuerpoCrearSugerencia,
  RespuestaMensaje,
  RespuestaSugerencia,
  RespuestaSugerencias,
} from "@/types";

export const apiSugerencias = {
  // --- Buzón de sugerencias ---
  sugerencias: (signal?: AbortSignal) =>
    peticion<RespuestaSugerencias>("/sugerencias", { signal }),
  crearSugerencia: (cuerpo: CuerpoCrearSugerencia) =>
    peticion<RespuestaSugerencia>("/sugerencias", { metodo: "POST", json: cuerpo }),
  actualizarSugerencia: (id: string, cuerpo: CuerpoActualizarSugerencia) =>
    peticion<RespuestaSugerencia>(`/sugerencias/${encodeURIComponent(id)}`, {
      metodo: "PATCH",
      json: cuerpo,
    }),
  eliminarSugerencia: (id: string) =>
    peticion<RespuestaMensaje>(`/sugerencias/${encodeURIComponent(id)}`, { metodo: "DELETE" }),

};
