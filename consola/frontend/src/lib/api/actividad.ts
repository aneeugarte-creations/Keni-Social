// Fragmento del cliente API: dominio «actividad». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion, query } from "./_core";
import type {
  ActividadAgregados,
  ColaMonitor,
  ColaSerie,
  RespuestaActividad,
  RespuestaPurgarCola,
  RespuestaReencolarCola,
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

  // --- Monitor de cola (snapshot en vivo + serie por día + acciones admin) ---
  cola: (signal?: AbortSignal) => peticion<ColaMonitor>("/actividad/cola", { signal }),
  colaSeries: (dias = 14, signal?: AbortSignal) =>
    peticion<ColaSerie>(`/actividad/cola/series${query({ dias: String(dias) })}`, { signal }),
  // Acciones ADMIN (el backend devuelve 403 si no es una sesión admin).
  colaPurgar: () =>
    peticion<RespuestaPurgarCola>("/actividad/cola/purgar", { metodo: "POST" }),
  colaReencolar: (genId: string) =>
    peticion<RespuestaReencolarCola>("/actividad/cola/reencolar", {
      metodo: "POST",
      json: { gen_id: genId },
    }),
};
