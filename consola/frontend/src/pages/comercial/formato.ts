/**
 * Helpers de presentacion del apartado Campañas (fechas es-MX).
 *
 * Los formateadores numéricos se reutilizan de Métricas (`../metricas/formato`)
 * para que toda la consola hable el mismo idioma visual.
 */
import { formatearDia, formatearFechaCorta, formatearFechaHoraCorta } from "@/lib/fecha";

// Fechas en hora CDMX (los instantes del backend son UTC): el formateo vive en
// `@/lib/fecha`. Aquí solo se conserva el fallback "—" propio de Campañas.

/** Fecha corta es-MX a partir de un ISO (día + mes). Ej.: "25 may". */
export function fechaCorta(iso: string): string {
  return formatearFechaCorta(iso) || "—";
}

/** Fecha con hora es-MX a partir de un ISO. Ej.: "25 may, 12:00". */
export function fechaHora(iso: string): string {
  return formatearFechaHoraCorta(iso) || "—";
}

/** Día legible es-MX a partir de `YYYY-MM-DD`. */
export function fechaDia(dia: string): string {
  return formatearDia(dia);
}
