// --- Metricas ---
//
// Los tipos de métricas (`RangoMetrica`, `OpcionesMetricas`, `TotalMetricas`,
// `CuentaMetrica`, `ReporteMetricas`, `ComparativaMetrica`, `ComparativaPorMarca`,
// `CompararMetricas`) se GENERAN desde el backend y se re-exportan desde el barrel
// (`index.ts`). Ver #101.
// NOTA: `fuente` ahora es REQUERIDO (el backend siempre lo emite, cae a "muestra").

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
