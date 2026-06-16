// --- Campañas (agrupan piezas por hashtag; analítica al vuelo) ----------------
// Tipos a mano (como las rutas ad-hoc): el backend de campañas no está en el
// subconjunto estable generado, así que estos no salen de `types.gen`.

export interface CampaniaComercial {
  id: string;
  /** Marcas que abarca la campaña (ids canónicos). Multimarca. */
  marcas: string[];
  /** Nombres legibles de `marcas`, en el mismo orden. */
  marcas_nombres: string[];
  nombre: string;
  /** Hashtags tal como se escribieron (sin '#', conservando casing). */
  hashtags: string[];
  activa: boolean;
  fecha_creacion: string;
  fecha_actualizacion: string;
}

export interface RespuestaCampanias {
  campanias: CampaniaComercial[];
  fuente: string;
}

export interface RespuestaCampania {
  campania: CampaniaComercial;
}

/** Una pieza del periodo que entra en la campaña (fila de la tabla). */
export interface PiezaCampania {
  id: string;
  red: string;
  /** Marca de origen (nombre legible), útil para agrupar en campañas multimarca. */
  marca: string;
  titulo: string;
  publicado: string;
  visualizaciones: number;
  /** Visualizaciones INORGÁNICAS (Meta Ads). En una fila inorgánica son las impresiones del
   * boost; en una pieza orgánica es 0 (lo pagado vive en su propia fila). */
  visualizaciones_pagadas: number;
  interacciones: number;
  engagement_pct: number;
  url: string;
  formato: string;
  /** True si entró por cross-post (gemela sin hashtag de una pieza etiquetada). */
  por_cross_post: boolean;
  /** True si es una publicación INORGÁNICA (un boost de Meta Ads), no un post orgánico. */
  es_inorganico: boolean;
}

export interface KpisCampania {
  visualizaciones: number;
  interacciones: number;
  engagement_pct: number;
  piezas: number;
}

/** Un KPI comparado contra el periodo anterior (`variacion_pct` null si no hay base). */
export interface ComparativaKpi {
  actual: number;
  anterior: number;
  delta: number;
  variacion_pct: number | null;
}

export type ClaveKpiCampania = "visualizaciones" | "interacciones" | "engagement_pct" | "piezas";

export interface PuntoTendenciaCampania {
  fecha: string;
  visualizaciones: number;
  interacciones: number;
}

/** Una fila del desglose por red: agregados de la campaña en esa red. */
export interface DesgloseRedCampania {
  red: string;
  piezas: number;
  visualizaciones: number;
  interacciones: number;
  likes: number;
  comentarios: number;
  compartidos: number;
  guardados: number;
  engagement_pct: number;
}

/** Totales del INORGÁNICO (Meta/TikTok Ads) atribuido a la campaña. */
export interface InorganicoCampania {
  visualizaciones: number;
  gasto: number;
  clics: number;
  campanias: number;
  moneda: string;
}

export interface AnaliticaCampania {
  campania: CampaniaComercial;
  rango: string;
  periodo: { desde: string; hasta: string };
  fuente: string;
  kpis: KpisCampania;
  comparativa: Record<ClaveKpiCampania, ComparativaKpi>;
  tendencia: { puntos: PuntoTendenciaCampania[] };
  desglose_red: DesgloseRedCampania[];
  /** Nº de piezas añadidas por inferencia de cross-post (sin el hashtag propio). */
  cross_posts: number;
  /** Totales inorgánicos (Meta Ads): los boosts que entran como filas inorgánicas. */
  inorganico: InorganicoCampania;
  /** Piezas del periodo: orgánicas + inorgánicas (boosts), estas con `es_inorganico`. */
  piezas: PiezaCampania[];
  generado_en: string;
}

export interface CuerpoCrearCampania {
  marcas: string[];
  nombre: string;
  hashtags: string[];
}

export interface CuerpoActualizarCampania {
  nombre?: string;
  marcas?: string[];
  hashtags?: string[];
  activa?: boolean;
}
