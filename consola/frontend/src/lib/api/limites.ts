// Fragmento del cliente API: dominio «limites». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion } from "./_core";
import type {
  RespuestaLimites,
} from "@/types";

export const apiLimites = {
  // --- Límites de caracteres por red (fuente única backend) ---
  limites: (signal?: AbortSignal) => peticion<RespuestaLimites>("/limites", { signal }),

};
