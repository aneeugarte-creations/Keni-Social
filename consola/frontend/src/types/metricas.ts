// --- Metricas ---
//
// Los tipos de métricas (`RangoMetrica`, `OpcionesMetricas`, `TotalMetricas`,
// `CuentaMetrica`, `ReporteMetricas`, `ComparativaMetrica`, `ComparativaPorMarca`,
// `CompararMetricas`) se GENERAN desde el backend y se re-exportan desde el barrel
// (`index.ts`).
// NOTA: `fuente` es REQUERIDO (el backend siempre lo emite; "" si es desconocida).

/** Un grupo (valor de un eje) con su rendimiento agregado. */
export interface GrupoPorEtiqueta {
  /** Valor del eje (p. ej. "reel", "Mundial 2026", "Sin clasificar"). */
  valor: string;
  /** Nº de piezas del periodo en este grupo. */
  n: number;
  /** Suma de visualizaciones de las piezas del grupo. */
  visualizaciones: number;
  /** Engagement medio (%) de las piezas del grupo. */
  engagement_pct: number;
}

/** Una serie graficable: un eje de agrupación con sus grupos. */
export interface SeriePorEtiqueta {
  /** Clave del eje (tipo|campania|vertical|etiqueta_tipo). */
  eje: string;
  /** Etiqueta legible del eje para el tab/título. */
  etiqueta: string;
  grupos: GrupoPorEtiqueta[];
}

/** Respuesta de `GET /api/metricas/piezas-por-etiqueta` (Item C). */
export interface PiezasPorEtiqueta {
  marca: string;
  rango: string;
  etiqueta_rango: string;
  series: SeriePorEtiqueta[];
  /** Piezas del periodo (Metricool). */
  total: number;
  /** Enlazadas a un `contenido` por id_post_metricool. */
  enlazadas: number;
  /** Enlazadas por fuzzy-match de título (heurístico). */
  enlazadas_titulo: number;
  /** Sin enlace (caen en "Sin clasificar"). */
  sin_enlace: number;
  fuente: string;
}

/** Una campaña de publicidad pagada (Meta/TikTok Ads) del periodo a nivel marca. */
export interface CampaniaAdsMetrica {
  nombre: string;
  red: string;
  impresiones: number;
  gasto: number;
  clics: number;
  moneda: string;
  inicio: string;
  fin: string;
  es_post_impulsado: boolean;
}

/** Respuesta de `GET /api/metricas/ads`: el INORGÁNICO (Meta Ads) del periodo. */
export interface AdsMetricas {
  ads: CampaniaAdsMetrica[];
  total: {
    visualizaciones: number;
    gasto: number;
    clics: number;
    campanias: number;
    moneda: string;
  };
  etiqueta_rango: string;
  generado_en: string;
}

/** Un canal (marca×red×formato) con la ingesta ESTANCADA (se quedó atrás del feed). */
export interface AlertaIngestaItem {
  marca: string;
  red: string;
  formato: string;
  ultima_pieza: string;
  dias_sin_piezas: number;
  rezago_dias: number;
}

/** Respuesta de `GET /api/metricas/ingesta`: canales con la sincronización estancada. */
export interface IngestaMetricas {
  alertas: AlertaIngestaItem[];
  etiqueta_rango: string;
  generado_en: string;
}
