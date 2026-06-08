// Fragmento del cliente API: dominio «breaking». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion } from "./_core";
import type {
  CuerpoPreparar,
  RespuestaBreaking,
  RespuestaPreparar,
} from "@/types";

export const apiBreaking = {
  // --- Carril Rápido de Breaking (Claro Sports) ---
  breaking: {
    /**
     * Lista los temas del Radar marcados como breaking para la marca, con su estado de borrador.
     * GET /api/breaking?marca=claro-sports
     */
    listar: (marca?: string, signal?: AbortSignal) =>
      peticion<RespuestaBreaking>(
        `/breaking${marca ? `?marca=${encodeURIComponent(marca)}` : ""}`,
        { signal },
      ),
    /**
     * Prepara un borrador de copy para un tema breaking (DRAFT, nunca publica).
     * POST /api/breaking/preparar
     */
    preparar: (cuerpo: CuerpoPreparar) =>
      peticion<RespuestaPreparar>("/breaking/preparar", { metodo: "POST", json: cuerpo }),
  },


};
