// Fragmento del cliente API: dominio «actividad». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion, query } from "./_core";
import type {
  ActividadAgregados,
  ColaMonitor,
  ColaSerie,
  EconomiaPorProceso,
  GateDiarioIA,
  ProduccionDia,
  RespuestaPriorizarCola,
  RespuestaPurgarCola,
  RespuestaReencolarCola,
} from "@/types";

export const apiActividad = {
  actividadAgregados: (params: { marca?: string } = {}, signal?: AbortSignal) =>
    peticion<ActividadAgregados>(
      `/actividad/agregados${query({ marca: params.marca })}`,
      { signal },
    ),

  // Economía por motor (ledger gasto_ia): total + serie por día + por tipo. `marca` vacía =
  // AGREGADO de todas; una marca acota el desglose. La consume la página Economía.
  economia: (params: { dias?: number; marca?: string } = {}, signal?: AbortSignal) =>
    peticion<EconomiaPorProceso>(
      `/actividad/economia${query({ dias: String(params.dias ?? 7), marca: params.marca })}`,
      { signal },
    ),

  // --- Monitor de cola (snapshot en vivo + serie por día + acciones admin) ---
  // `marca` acota las listas en_curso/esperando (los KPIs de capacidad siguen globales).
  cola: (params: { marca?: string } = {}, signal?: AbortSignal) =>
    peticion<ColaMonitor>(`/actividad/cola${query({ marca: params.marca })}`, { signal }),
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
  // Adelanta un job ESPERANDO al lote de fondo (lo sube a prioridad manual).
  colaPriorizar: (genId: string) =>
    peticion<RespuestaPriorizarCola>("/actividad/cola/priorizar", {
      metodo: "POST",
      json: { gen_id: genId },
    }),
  // Gate diario por % del límite semanal POR CUENTA: sube +10% el umbral del día de ESA cuenta y
  // reanuda la generación de sus marcas. Devuelve el estado del gate de la cuenta ya actualizado
  // (la misma forma que un bloque de `presupuesto.gate_diario_cuentas`).
  gateDiarioAceptar: (cuenta: string) =>
    peticion<GateDiarioIA>(
      `/actividad/cola/gate-diario/aceptar${query({ cuenta })}`,
      { metodo: "POST" },
    ),
  // Producción del día (líneas del plan editorial) para el Monitor.
  produccionDia: (marca: string, signal?: AbortSignal) =>
    peticion<ProduccionDia>(`/produccion/dia${query({ marca })}`, { signal }),
};
