// Fragmento del cliente API: dominio «metricas». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion, query, descargar } from "./_core";
import type {
  AdsMetricas,
  AnalisisDiario,
  AnaliticaPiezas,
  CompararMetricas,
  CorrelacionSeguidores,
  Crosstab,
  DesgloseInteracciones,
  EstadoMetricas,
  HistoricoPieza,
  IngestaMetricas,
  MetricasLineas,
  OpcionesMetricas,
  PiezasListado,
  PiezasPorEtiqueta,
  PiezasRendimiento,
  ReporteMetricas,
  SerieSeguidores,
  TendenciaDiaria,
} from "@/types";

export const apiMetricas = {
  // --- Metricas ---
  metricasOpciones: (signal?: AbortSignal) =>
    peticion<OpcionesMetricas>("/metricas/opciones", { signal }),
  metricasReporte: (params: { rango?: string; marca?: string; red?: string }, signal?: AbortSignal) =>
    peticion<ReporteMetricas>(`/metricas/reporte${query(params)}`, { signal }),
  metricasComparar: (
    params: { rango_a?: string; rango_b?: string; marca?: string; red?: string },
    signal?: AbortSignal,
  ) => peticion<CompararMetricas>(`/metricas/comparar${query(params)}`, { signal }),
  metricasAnalisis: (params: { rango?: string; marca?: string; red?: string }, signal?: AbortSignal) =>
    peticion<AnalisisDiario>(`/metricas/analisis${query(params)}`, { signal }),
  // Analítica de piezas: estadísticas + top 5 + peores 5 + distribución del periodo.
  metricasPiezas: (params: { rango?: string; marca?: string; red?: string }, signal?: AbortSignal) =>
    peticion<AnaliticaPiezas>(`/metricas/piezas${query(params)}`, { signal }),
  // Serie diaria del periodo (visualizaciones + interacciones) para la tendencia.
  metricasTendencia: (params: { rango?: string; marca?: string; red?: string }, signal?: AbortSignal) =>
    peticion<TendenciaDiaria>(`/metricas/tendencia${query(params)}`, { signal }),
  // Drill-down marca -> pieza: piezas publicadas con su rendimiento REAL (Metricool),
  // enlazables al tablero. Sin rango (es por pieza publicada, no por periodo).
  metricasPiezasRendimiento: (params: { marca?: string }, signal?: AbortSignal) =>
    peticion<PiezasRendimiento>(`/metricas/piezas-rendimiento${query(params)}`, { signal }),
  // Listado COMPLETO de piezas del periodo (todas, no solo top/peores), tal como las
  // emite la fuente única; insumo de la tabla "Todas las piezas del periodo".
  metricasPiezasListado: (params: { rango?: string; marca?: string; red?: string }, signal?: AbortSignal) =>
    peticion<PiezasListado>(`/metricas/piezas-listado${query(params)}`, { signal }),
  // Histórico por pieza (snapshots acumulados, ADR 0007) + velocidad. `puntos` vacío =
  // la pieza aún no se sigue (sin histórico todavía). Se carga perezosamente por id.
  metricasPiezaHistorico: (params: { id: string }, signal?: AbortSignal) =>
    peticion<HistoricoPieza>(`/metricas/pieza-historico${query(params)}`, { signal }),
  // Rendimiento del periodo agrupado por serie/tipo (Item C): cruza piezas de Metricool
  // con el contenido de la BD para resolver tipo_contenido + etiquetas.
  metricasPiezasPorEtiqueta: (params: { rango?: string; marca?: string; red?: string }, signal?: AbortSignal) =>
    peticion<PiezasPorEtiqueta>(`/metricas/piezas-por-etiqueta${query(params)}`, { signal }),
  // Rendimiento del periodo agregado por LÍNEA de contenido (vertical) y por ORIGEN.
  // `marca` viaja en forma `id_metricas` (guion_bajo), igual que el resto de Métricas.
  metricasLineas: (params: { rango?: string; marca?: string; red?: string }, signal?: AbortSignal) =>
    peticion<MetricasLineas>(`/metricas/lineas${query(params)}`, { signal }),
  // --- Estrategia digital ---
  // Evolución de seguidores del periodo (total + por red) con el neto ganado/perdido.
  metricasSeguidores: (params: { rango?: string; marca?: string; red?: string }, signal?: AbortSignal) =>
    peticion<SerieSeguidores>(`/metricas/seguidores${query(params)}`, { signal }),
  // Desglose de interacciones (likes/comentarios/compartidos/guardados/video_views) por marca×red.
  metricasDesglose: (params: { rango?: string; marca?: string; red?: string }, signal?: AbortSignal) =>
    peticion<DesgloseInteracciones>(`/metricas/desglose${query(params)}`, { signal }),
  // Rendimiento cruzado marca×red×formato (n_piezas, engagement, rendimiento relativo medio).
  metricasCrosstab: (params: { rango?: string; marca?: string; red?: string }, signal?: AbortSignal) =>
    peticion<Crosstab>(`/metricas/crosstab${query(params)}`, { signal }),
  // Correlación seguidores ganados ↔ piezas publicadas por día (con la pieza estrella).
  metricasCorrelacion: (params: { rango?: string; marca?: string; red?: string }, signal?: AbortSignal) =>
    peticion<CorrelacionSeguidores>(`/metricas/correlacion${query(params)}`, { signal }),
  // Campañas de publicidad PAGADA del periodo (Meta/TikTok Ads): el inorgánico a nivel marca.
  metricasAds: (params: { rango?: string; marca?: string; red?: string }, signal?: AbortSignal) =>
    peticion<AdsMetricas>(`/metricas/ads${query(params)}`, { signal }),
  // Canales (marca×red×formato) con la ingesta estancada (se quedaron atrás del feed).
  metricasIngesta: (params: { rango?: string; marca?: string }, signal?: AbortSignal) =>
    peticion<IngestaMetricas>(`/metricas/ingesta${query(params)}`, { signal }),
  // Estado del refresco + "última actualización" del combo (para el botón Actualizar y el polling).
  metricasEstado: (params: { rango?: string; marca?: string }, signal?: AbortSignal) =>
    peticion<EstadoMetricas>(`/metricas/estado${query(params)}`, { signal }),
  // Dispara un refresco en 2º plano (prioriza el combo visto). Idempotente: si ya corre, no arranca otro.
  metricasRefrescar: (params: { rango?: string; marca?: string }) =>
    peticion<EstadoMetricas>(`/metricas/refrescar${query(params)}`, { metodo: "POST" }),
  exportarMetricas: (formato: "csv" | "md" | "json", params: { rango?: string; marca?: string; red?: string }) =>
    descargar(`/metricas/export.${formato}${query(params)}`),
  // Descarga del Top 5 / Peores 5 de piezas del periodo (Item B): mismo dato que la
  // analítica de piezas, serializado en csv|md|json. `fmt` viaja como query param.
  exportarPiezas: (formato: "csv" | "md" | "json", params: { rango?: string; marca?: string }) =>
    descargar(`/metricas/piezas-export${query({ fmt: formato, ...params })}`),

};
