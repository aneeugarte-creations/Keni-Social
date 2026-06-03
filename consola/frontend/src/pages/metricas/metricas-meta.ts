/**
 * Metadatos compartidos de las cuatro métricas del reporte.
 *
 * Define el orden, las etiquetas en español y el formateador adecuado de cada
 * métrica para reutilizarlos en KPIs, tabla y comparativa, evitando repetir
 * literales por toda la página.
 */
import type { CuentaMetrica, TotalMetricas } from "@/types";

import { numeroCompacto, numeroCompleto, porcentaje } from "./formato";

/** Claves de métrica que se MUESTRAN (el `alcance` del contrato no se mide en ninguna
 * red con la fuente actual de posts, así que no se expone en la UI). */
export type ClaveMetrica = "visualizaciones" | "interacciones" | "engagement_pct";

export interface MetaMetrica {
  clave: ClaveMetrica;
  /** Etiqueta legible (es-MX). */
  etiqueta: string;
  /** Nombre interno que usa el backend en `ComparativaMetrica.metrica`. */
  metrica: string;
  /** Formato compacto para KPIs y gráficas. */
  compacto: (v: number) => string;
  /** Formato completo para tablas y tooltips. */
  completo: (v: number) => string;
  /** Color Tremor asociado (para gráficas / acentos). */
  color: "orange" | "sky" | "violet" | "emerald";
}

/** Las 4 métricas en el orden en que se muestran en toda la página. */
export const METRICAS: MetaMetrica[] = [
  {
    clave: "visualizaciones",
    etiqueta: "Visualizaciones",
    metrica: "visualizaciones",
    compacto: numeroCompacto,
    completo: numeroCompleto,
    color: "orange",
  },
  {
    clave: "interacciones",
    etiqueta: "Interacciones",
    metrica: "interacciones",
    compacto: numeroCompacto,
    completo: numeroCompleto,
    color: "violet",
  },
  {
    clave: "engagement_pct",
    etiqueta: "Engagement",
    metrica: "engagement_pct",
    compacto: porcentaje,
    completo: porcentaje,
    color: "emerald",
  },
];

/** Lee el valor de una métrica desde un total o una cuenta de forma tipada. */
export function valorMetrica(
  fuente: TotalMetricas | CuentaMetrica,
  clave: ClaveMetrica,
): number {
  return fuente[clave];
}
