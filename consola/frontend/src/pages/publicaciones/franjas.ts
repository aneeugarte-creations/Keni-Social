/**
 * Utilidades de franjas (colas de publicación).
 */

/** Clave de React Query para las franjas. */
export const CLAVE_FRANJAS = ["franjas"] as const;

/** Nombres de los días de la semana (0=lunes .. 6=domingo), es-MX. */
export const DIAS_SEMANA = [
  "Lunes",
  "Martes",
  "Miércoles",
  "Jueves",
  "Viernes",
  "Sábado",
  "Domingo",
] as const;

/** Abreviaturas de los días (0=lunes .. 6=domingo). */
export const DIAS_SEMANA_CORTO = [
  "Lun",
  "Mar",
  "Mié",
  "Jue",
  "Vie",
  "Sáb",
  "Dom",
] as const;

/** Nombre legible de un día de la semana (con fallback). */
export function nombreDia(dia: number): string {
  return DIAS_SEMANA[dia] ?? `Día ${dia}`;
}

/** Abreviatura de un día de la semana (con fallback). */
export function nombreDiaCorto(dia: number): string {
  return DIAS_SEMANA_CORTO[dia] ?? `D${dia}`;
}
