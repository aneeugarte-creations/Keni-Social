// Fragmento del cliente API: dominio «config». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion } from "./_core";
import type {
  CuerpoGuardarConfig,
  RespuestaAjusteGuardado,
  RespuestaAjustes,
  RespuestaConfig,
  RespuestaMensaje,
} from "@/types";

export const apiConfig = {
  // --- Config ---
  config: (signal?: AbortSignal) => peticion<RespuestaConfig>("/config", { signal }),
  guardarConfig: (cuerpo: CuerpoGuardarConfig) =>
    peticion<RespuestaMensaje>("/config", { metodo: "POST", json: cuerpo }),
  // NOTA: el esfuerzo de razonamiento (`KENI_ESFUERZO`) se lee/escribe vía `/api/ajustes`
  // (select del grupo `tuning`); el shim deprecado `/api/config/esfuerzo` ya no se llama.

  // --- Ajustes de funcionalidad (admin): toggles + tuning, aplican en caliente ---
  ajustes: (signal?: AbortSignal) => peticion<RespuestaAjustes>("/ajustes", { signal }),
  guardarAjuste: (cuerpo: { clave: string; valor?: boolean | number | string; reset?: boolean }) =>
    peticion<RespuestaAjusteGuardado>("/ajustes", { metodo: "POST", json: cuerpo }),

};
