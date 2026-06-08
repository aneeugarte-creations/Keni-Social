// Fragmento del cliente API: dominio «metricool». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion } from "./_core";
import type {
  RespuestaProgramarMetricool,
} from "@/types";

export const apiMetricool = {
  // --- Programar/previsualizar una pieza en Metricool (respeta KENI_PUBLICAR_REAL) ---
  // Con el gate OFF (default) es DRY-RUN: previsualiza el cuerpo, NO publica nada.
  programarEnMetricool: (publicacionId: string) =>
    peticion<RespuestaProgramarMetricool>(
      `/publicaciones/${encodeURIComponent(publicacionId)}/metricool`,
      { metodo: "POST" },
    ),

};
