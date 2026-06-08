// Fragmento del cliente API: dominio «config». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion } from "./_core";
import type {
  CuerpoGuardarConfig,
  CuerpoGuardarEsfuerzo,
  RespuestaAjusteGuardado,
  RespuestaAjustes,
  RespuestaConfig,
  RespuestaEsfuerzo,
  RespuestaMensaje,
} from "@/types";

export const apiConfig = {
  // --- Config ---
  config: (signal?: AbortSignal) => peticion<RespuestaConfig>("/config", { signal }),
  guardarConfig: (cuerpo: CuerpoGuardarConfig) =>
    peticion<RespuestaMensaje>("/config", { metodo: "POST", json: cuerpo }),
  esfuerzo: (signal?: AbortSignal) => peticion<RespuestaEsfuerzo>("/config/esfuerzo", { signal }),
  guardarEsfuerzo: (cuerpo: CuerpoGuardarEsfuerzo) =>
    peticion<RespuestaMensaje>("/config/esfuerzo", { metodo: "POST", json: cuerpo }),

  // --- Ajustes de funcionalidad (admin): toggles + tuning, aplican en caliente ---
  ajustes: (signal?: AbortSignal) => peticion<RespuestaAjustes>("/ajustes", { signal }),
  guardarAjuste: (cuerpo: { clave: string; valor?: boolean | number | string; reset?: boolean }) =>
    peticion<RespuestaAjusteGuardado>("/ajustes", { metodo: "POST", json: cuerpo }),

};
