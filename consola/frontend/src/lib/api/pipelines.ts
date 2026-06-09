// Fragmento del cliente API: dominio «pipelines». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion, query } from "./_core";
import type {
  RespuestaPipelineDetalle,
  RespuestaPipelines,
} from "@/types";

export const apiPipelines = {
  // --- Pipelines (vista CI/CD del pipeline de contenido) ---
  pipelines: (
    params: {
      marca?: string; etapa?: string; estado?: string; limite?: number; desplazamiento?: number;
    } = {},
    signal?: AbortSignal,
  ) =>
    peticion<RespuestaPipelines>(
      `/pipelines${query({
        marca: params.marca,
        etapa: params.etapa || undefined,
        estado: params.estado || undefined,
        limite: params.limite != null ? String(params.limite) : undefined,
        desplazamiento: params.desplazamiento != null ? String(params.desplazamiento) : undefined,
      })}`,
      { signal },
    ),
  pipelineDetalle: (id: string, signal?: AbortSignal) =>
    peticion<RespuestaPipelineDetalle>(`/pipelines/${encodeURIComponent(id)}`, { signal }),

};
