// Fragmento del cliente API: dominio «actividad». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion, query } from "./_core";
import type {
  ActividadAgregados,
  RespuestaActividad,
} from "@/types";

export const apiActividad = {
  // --- Actividad IA unificada (feed de generaciones + runs de agentes) ---
  // Solo lectura: el backend fusiona ambas fuentes en un único feed con métricas
  // (tokens/coste/duración) y expone sus agregados (totales + por tipo + por día).
  actividad: (
    params: {
      limite?: number;
      offset?: number;
      fuente?: string;
      tipo?: string;
      marca?: string;
    } = {},
    signal?: AbortSignal,
  ) =>
    peticion<RespuestaActividad>(
      `/actividad${query({
        limite: params.limite != null ? String(params.limite) : undefined,
        offset: params.offset != null ? String(params.offset) : undefined,
        fuente: params.fuente,
        tipo: params.tipo,
        marca: params.marca,
      })}`,
      { signal },
    ),
  actividadAgregados: (params: { marca?: string } = {}, signal?: AbortSignal) =>
    peticion<ActividadAgregados>(
      `/actividad/agregados${query({ marca: params.marca })}`,
      { signal },
    ),

};
