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

/** Honestidad de las "Vistas" agregadas ENTRE redes: el total suma magnitudes que no
 * son la misma cosa (impresiones en Facebook/Instagram vs. reproducciones en
 * TikTok/YouTube), así que el agregado cross-red es informativo y debe leerse "por red".
 * Documentado en el backend (`mcp-metricas/.../schema.py` ResumenMetricas, #138). Texto
 * único para reusar en cada sitio donde se enseñan vistas sumadas entre redes. */
export const NOTA_VISTAS_CROSSRED =
  "Las vistas suman magnitudes distintas según la red: impresiones en Facebook e " +
  "Instagram, reproducciones en TikTok y YouTube. El total entre redes es orientativo; " +
  "para comparar, léelo por red.";

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
  /** Aclaración breve de cómo se calcula (solo para métricas derivadas). */
  descripcion?: string;
}

/** Las 4 métricas en el orden en que se muestran en toda la página. */
export const METRICAS: MetaMetrica[] = [
  {
    clave: "visualizaciones",
    etiqueta: "Vistas",
    metrica: "visualizaciones",
    compacto: numeroCompacto,
    completo: numeroCompleto,
    color: "orange",
    descripcion: NOTA_VISTAS_CROSSRED,
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
    descripcion: "Interacciones ÷ vistas, en porcentaje",
  },
];

/** Lee el valor de una métrica desde un total o una cuenta de forma tipada. */
export function valorMetrica(
  fuente: TotalMetricas | CuentaMetrica,
  clave: ClaveMetrica,
): number {
  return fuente[clave];
}
