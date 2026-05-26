/**
 * Helpers de presentacion del apartado Comercial (fechas es-MX, estados, métricas).
 *
 * Los formateadores numéricos se reutilizan de Métricas (`../metricas/formato`)
 * para que toda la consola hable el mismo idioma visual.
 */
import type { BadgeProps } from "@/components/ui/badge";
import type { EstadoComercial, MetricaComercial } from "@/types";

/** Fecha corta es-MX a partir de un ISO (día + mes). Ej.: "25 may". */
export function fechaCorta(iso: string): string {
  if (!iso) return "—";
  const f = new Date(iso);
  if (Number.isNaN(f.getTime())) return iso;
  return new Intl.DateTimeFormat("es-MX", { day: "2-digit", month: "short" }).format(f);
}

/** Fecha con hora es-MX a partir de un ISO. Ej.: "25 may, 12:00". */
export function fechaHora(iso: string): string {
  if (!iso) return "—";
  const f = new Date(iso);
  if (Number.isNaN(f.getTime())) return iso;
  return new Intl.DateTimeFormat("es-MX", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(f);
}

/** Día legible es-MX a partir de `YYYY-MM-DD` (mediodía local para evitar desfases). */
export function fechaDia(dia: string): string {
  if (!dia) return "—";
  const f = new Date(`${dia}T12:00:00`);
  if (Number.isNaN(f.getTime())) return dia;
  return new Intl.DateTimeFormat("es-MX", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(f);
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
  return metrica === "alcance" ? "Alcance" : "Interacciones";
}
