/**
 * Claves de React Query y helpers compartidos por la sección Agentes.
 *
 * Vive en su propio módulo (sin componentes) para no romper el fast-refresh de
 * los `.tsx` y centralizar las claves de caché.
 */
import { ApiError } from "@/lib/api";

/** Clave del detalle de un agente. */
export function claveAgente(id: string): readonly string[] {
  return ["agentes", id] as const;
}

/** Clave de los runs de un agente. */
export function claveRuns(id: string): readonly string[] {
  return ["agentes", id, "runs"] as const;
}

/** Texto legible del error de la API (o un fallback en español). */
export function mensajeError(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo en un momento.";
}

/** Formatea una fecha ISO en formato corto es-MX; tolera fechas inválidas. */
export function formatearFecha(iso: string): string {
  if (!iso) return "";
  const fecha = new Date(iso);
  if (Number.isNaN(fecha.getTime())) return iso;
  return new Intl.DateTimeFormat("es-MX", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(fecha);
}
