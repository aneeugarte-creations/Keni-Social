// Fragmento del cliente API: dominio «config» (ajustes de funcionalidad).
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion } from "./_core";
import type { RespuestaAjusteGuardado, RespuestaAjustes } from "@/types";

export const apiConfig = {
  // NOTA: el esfuerzo de razonamiento (`KENI_ESFUERZO`) se lee/escribe vía `/api/ajustes`
  // (select del grupo `tuning`).

  // --- Ajustes de funcionalidad (admin): toggles + tuning, aplican en caliente ---
  ajustes: (signal?: AbortSignal) => peticion<RespuestaAjustes>("/ajustes", { signal }),
  guardarAjuste: (cuerpo: { clave: string; valor?: boolean | number | string; reset?: boolean }) =>
    peticion<RespuestaAjusteGuardado>("/ajustes", { metodo: "POST", json: cuerpo }),
};
