// --- Metricas ---
//
// Los tipos de métricas (`RangoMetrica`, `OpcionesMetricas`, `TotalMetricas`,
// `CuentaMetrica`, `ReporteMetricas`, `ComparativaMetrica`, `ComparativaPorMarca`,
// `CompararMetricas`) se GENERAN desde el backend y se re-exportan desde el barrel
// (`index.ts`).
// NOTA: `fuente` es REQUERIDO (el backend siempre lo emite; "" si es desconocida).

import type { PeriodoMetricas, TotalMetricas } from "../types.gen";

/** El total del reporte con `impresiones`: el VOLUMEN aditivo del periodo (impresiones en
 * FB/IG/X, reproducciones en TikTok/YouTube). Es la cifra de cabecera del periodo. El campo
 * es opcional porque solo está presente cuando la fuente lo aporta; la UI degrada si falta. */
export type TotalConImpresiones = TotalMetricas & { impresiones?: number };

/** Un día de la serie de alcance de cuenta: total + desglose por red. */
export interface PuntoAlcance {
  fecha: string;
  total: number;
  por_red: Record<string, number>;
}

/** Respuesta de `GET /api/metricas/serie-alcance`: alcance de cuenta día a día.
 *
 * Solo Instagram expone alcance de cuenta (reach diario), así que `por_red` solo trae
 * `instagram`. El alcance es un FLUJO diario, no un stock: por eso no hay `neto`, solo la
 * serie. `puntos` vacío = la fuente no expone alcance de cuenta (degradación honesta). */
export interface SerieAlcance {
  cuenta: string | null;
  rango: string;
  etiqueta_rango: string;
  periodo: PeriodoMetricas;
  fuente: string;
  puntos: PuntoAlcance[];
}

/** Altas y bajas de seguidores de UNA red en el periodo.
 *
 * `altas`/`bajas` son `null` donde la red no las separa (TikTok/IG: solo `neto`); `neto`
 * siempre viene. FB y YouTube sí dan altas/bajas brutas. */
export interface AudienciaPorRed {
  red: string;
  altas: number | null;
  bajas: number | null;
  neto: number;
}

/** Respuesta de `GET /api/metricas/audiencia`: flujo de audiencia (altas/bajas/neto) por red.
 *
 * `por_red` vacío = la fuente no expone flujo de audiencia (degradación honesta). */
export interface FlujoAudiencia {
  por_red: AudienciaPorRed[];
  etiqueta_rango: string;
  generado_en: string;
}

/** Un punto de una distribución demográfica/de mezcla: clave + valor.
 *
 * `valor` es un porcentaje (float) en las distribuciones demográficas (gender/age/country/
 * city) y un conteo (int) en la mezcla de formatos (`postsTypes`). */
export interface PuntoDistribucion {
  clave: string;
  valor: number;
}

/** Respuesta de `GET /api/metricas/demografia`: distribuciones de UNA marca×red.
 *
 * IG trae `gender`/`age`/`country`/`city` (%) + `postsTypes` (conteos); FB
 * `page_follows_country` (%) + `postsTypes`. `distribuciones` puede venir `{}` (la fuente no
 * la expone o sin datos). */
export interface Demografia {
  red: string;
  distribuciones: Record<string, PuntoDistribucion[]>;
}

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
  /** Clave del eje (tipo|campania|categoria|etiqueta_tipo). */
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
  /** Campos de rendimiento OPCIONALES de la fuente (Meta Ads): pueden no venir según la
   * cuenta/campaña. La UI los muestra solo cuando llegan (degradación elegante). */
  ctr?: number | null;
  cpc?: number | null;
  cpm?: number | null;
  conversiones?: number | null;
  tasa_conversion?: number | null;
  valor_conversiones?: number | null;
  objetivo?: string | null;
  estado?: string | null;
  presupuesto_diario?: number | null;
  /** Plataforma de origen tal cual la nombra el proveedor (p. ej. "facebook", "instagram"). */
  network?: string | null;
  /** Id de campaña en el proveedor: clave del drill-down a conjuntos de anuncios y anuncios. */
  provider_campaign_id?: string | null;
  /** Texto del anuncio/post impulsado, si la fuente lo trae. */
  caption?: string | null;
  /** Cuenta publicitaria de origen, si la fuente la trae. */
  cuenta?: string | null;
}

/** Un conjunto de anuncios (adgroup) dentro de una campaña pagada. */
export interface AdGroupAds {
  nombre: string;
  impresiones: number;
  clics: number;
  gasto: number;
  ctr?: number | null;
  cpc?: number | null;
  conversiones?: number | null;
  moneda?: string | null;
}

/** Un anuncio (creativo) dentro de un conjunto de anuncios. */
export interface AdCreativoAds {
  nombre: string;
  adgroup?: string | null;
  impresiones: number;
  clics: number;
  gasto: number;
  thumbnail_url?: string | null;
  ctr?: number | null;
  cpc?: number | null;
  conversiones?: number | null;
  moneda?: string | null;
}

/** Respuesta de `GET /api/metricas/ads/{provider_campaign_id}/desglose`: el detalle de
 * una campaña pagada en conjuntos de anuncios y anuncios. Puede no existir aún (404). */
export interface DesgloseAds {
  adgroups: AdGroupAds[];
  ads: AdCreativoAds[];
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
