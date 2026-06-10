/**
 * Helpers de presentacion del apartado Comercial (fechas es-MX, estados, métricas).
 *
 * Los formateadores numéricos se reutilizan de Métricas (`../metricas/formato`)
 * para que toda la consola hable el mismo idioma visual.
 */
import type { BadgeProps } from "@/components/ui/badge";
import { formatearDia, formatearFechaCorta, formatearFechaHoraCorta } from "@/lib/fecha";
import type { EstadoComercial, MetricaComercial } from "@/types";

// Fechas en hora CDMX (los instantes del backend son UTC): el formateo vive en
// `@/lib/fecha`. Aquí solo se conserva el fallback "—" propio de Comercial.

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

/** Etiqueta + variante de badge para el estado del seguimiento. */
export function presentacionEstado(estado: EstadoComercial): {
  texto: string;
  variante: BadgeProps["variant"];
} {
  switch (estado) {
    case "activa":
      return { texto: "Activa", variante: "ok" };
    case "pausada":
      return { texto: "Pausada", variante: "aviso" };
    case "cerrada":
      return { texto: "Cerrada", variante: "secondary" };
    default:
      return { texto: estado, variante: "secondary" };
  }
}

/** Nombre legible de la métrica del objetivo. */
export function etiquetaMetrica(metrica: MetricaComercial): string {
  if (metrica === "alcance") return "Alcance";
  if (metrica === "visualizaciones") return "Vistas";
  return "Interacciones";
}
