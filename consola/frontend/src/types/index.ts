/**
 * Contrato tipado de la API de la Consola Keni (`/api/*`).
 *
 * Estos tipos reflejan exactamente las respuestas y cuerpos documentados en el
 * contrato del backend. El frontend se construye contra estos tipos; la
 * integracion runtime contra el backend real se valida al combinar ramas.
 *
 * Todo el texto orientado al usuario (nombres, detalles, mensajes) llega ya en
 * espanol desde el backend.
 *
 * Este barrel preserva la superficie de import `@/types`: re-exporta los tipos
 * GENERADOS desde el backend (`../types.gen`) y los tipos a mano repartidos por
 * dominio en ficheros hermanos (`./metricas`, `./piezas`, …).
 *
 * ── Tipos DERIVADOS del backend ─────────────────────────────────────────────
 * Un SUBCONJUNTO ESTABLE del contrato (estado, config, límites/redes, métricas y
 * las respuestas genéricas) ya NO se mantiene a mano: se GENERA desde el
 * backend (`keni_consola.esquema_api`) a `types.gen.ts` con `npm run gen:types`,
 * y se re-exporta abajo. Así esos tipos no se desincronizan en silencio (el guard
 * `npm run gen:types:check` falla si divergen). El RESTO sigue a mano en los
 * ficheros de dominio porque sus handlers construyen dicts ad-hoc, no modelos.
 */

// Re-export de los tipos generados desde el backend (NO editar `types.gen.ts`).
export type {
  ResultadoEstado,
  RespuestaEstado,
  MarcaDisponible,
  LimiteRed,
  RespuestaLimites,
  RangoMetrica,
  OpcionesMetricas,
  TotalMetricas,
  CuentaMetrica,
  RedMetrica,
  RedCobertura,
  MarcaCobertura,
  ReporteMetricas,
  ComparativaMetrica,
  ComparativaPorMarca,
  TotalComparativa,
  CompararMetricas,
  PiezaAnalisis,
  MovimientoAnalisis,
  SiguientePasoAnalisis,
  AnalisisDiario,
  EstadoMetricas,
  PeriodoMetricas,
  EstadisticasNumericas,
  PiezaMetrica,
  DistribucionBucket,
  AnaliticaPiezas,
  PuntoSerie,
  TendenciaDiaria,
  PiezaRendimiento,
  PiezasRendimiento,
  PiezaListado,
  PiezasListado,
  PuntoHistorico,
  VelocidadPieza,
  HistoricoPieza,
  PuntoSeguidores,
  SerieSeguidores,
  CeldaDesglose,
  DesgloseInteracciones,
  CeldaCrosstab,
  Crosstab,
  PostEstrella,
  ItemCorrelacion,
  CorrelacionSeguidores,
  Paginacion,
  MetricasRun,
  Pieza,
  RespuestaPiezas,
  RespuestaPieza,
  RespuestaColaAprobacion,
  RespuestaMensaje,
  ErrorApi,
} from "../types.gen";

// Tipos a mano, repartidos por dominio. `export *` arrastra tipos y valores
// (p. ej. los exports runtime de `./auth`: ETIQUETA_CARGO, CARGOS_ORDENADOS,
// etiquetaCargo).
export * from "./comun";
export * from "./sistema";
export * from "./generaciones";
export * from "./historial";
export * from "./fuentes";
export * from "./algoritmos";
export * from "./contenido";
export * from "./colaboracion";
export * from "./notificaciones";
export * from "./rota";
export * from "./metricas";
export * from "./piezas";
export * from "./media";
export * from "./biblioteca";
export * from "./buzon";
export * from "./campanias";
export * from "./auth";
export * from "./catalogo";
export * from "./prompts";
export * from "./noticias";
export * from "./marcas";
export * from "./vistas";
export * from "./inbox";
