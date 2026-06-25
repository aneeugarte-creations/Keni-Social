/**
 * Contrato del Informe (deck PDF de Métricas): props ya listas para pintar, derivadas de los
 * datos reales por `desdeEntradas`. El componente `<Informe>` NO conoce React Query ni las
 * formas crudas del backend: solo consume estas props. Es el seam entre el adaptador (datos)
 * y la UI (deck). Cada lámina lleva su INSIGHT ya calculado: el deck cuenta qué pasó, no solo
 * cuánto.
 */

/** Tile de KPI del resumen. `delta` = variación vs periodo anterior (null = sin comparativa). */
export interface KpiInforme {
  etiqueta: string;
  valor: string;
  /** Texto largo para el title (número completo). */
  titulo: string;
  delta?: { texto: string; signo: "sube" | "baja" | "igual" | "nuevo" };
  /** Lectura secundaria cuando no hay delta (p. ej. "21 / día"): evita el hueco gris. */
  secundario?: string;
}

/** Punto de la serie diaria: visualizaciones e interacciones del día (small-multiple). */
export interface PuntoTendencia {
  fecha: string;
  Vistas: number;
  Interacciones: number;
}

/** Fila de un ranking horizontal (reparto por red, comparativa por marca): valor + % + color. */
export interface FilaRanking {
  /** Id canónico (red) o etiqueta (marca) para la clave. */
  clave: string;
  nombre: string;
  valor: number;
  pct: number;
  /** Color de la barra (paleta de deck desaturada para red; naranja de marca para cuentas). */
  color: string;
}

/** Segmento de la mezcla de interacciones (me gusta / comentarios / compartidos / guardados). */
export interface SegmentoMix {
  label: string;
  valor: number;
  pct: number;
  color: string;
}

/** Fila de la tabla Top piezas. */
export interface FilaPiezaInforme {
  titulo: string;
  /** Id canónico de red (facebook/instagram/tiktok/youtube/x) para `nombreRed`. */
  red: string;
  publicado: string;
  vistas: number;
  interacciones: number;
  engagement: number;
  /** Enlace público al post en su red (para el QR de "lo más visto"); ausente si no hay. */
  url?: string;
  /** Formato del post (reel/foto/carrusel/video/…) si el backend lo da. */
  formato?: string;
}

/** Conclusión del cierre: cifra grande + mini explicación. */
export interface ConclusionInforme {
  valor: string;
  label: string;
  /** sube → verde, baja → rojo, neutral → tinta (cuando no hay comparativa). */
  signo: "sube" | "baja" | "neutral";
  nota: string;
}

export interface InformeProps {
  /** Id normalizado de marca para el logo (unotv, claro-sports, …). null = todas las marcas. */
  marcaId: string | null;
  marcaLabel: string;
  esTodas: boolean;
  periodo: string;
  mesAnterior: string;
  /** Titular del mes (una frase determinista que resume la dirección del periodo). */
  titularMes: string;
  kpis: KpiInforme[];
  // --- Tendencia diaria (small-multiple vistas + interacciones) ---
  tendencia: PuntoTendencia[];
  /** Mejor día: su valor de vistas y qué fracción del mes concentró; null si no hay serie. */
  picoVistas: { fecha: string; pct: number; valor: number } | null;
  /** Media diaria de vistas (ancla de escala honesta). */
  mediaVistas: number;
  /** Media diaria de interacciones (caption simétrico al de vistas en la tendencia). */
  mediaInteracciones: number;
  // --- Reparto por red (ranking horizontal ordenado desc) ---
  porRed: FilaRanking[];
  /** Insight del reparto (red dominante + su %). */
  redInsight: string;
  // --- Engagement por red: interacción por vista, ranking desc (dónde ENGANCHA, no dónde se ve) ---
  engPorRed: Array<{ clave: string; nombre: string; rate: number; color: string }>;
  /** Insight de engagement por red (la red con más interacción por vista). */
  engInsight: string;
  /** Engagement global del periodo (Σ interacciones ÷ Σ vistas × 100), comparable al rate por red. */
  engMedia: number;
  // --- Seguidores: ganancia ACUMULADA desde 0 (la pendiente = el neto del titular) ---
  seguidores: Array<{ fecha: string; Ganados: number }>;
  /** Neto ganado en el periodo: cifra, %, por día y dirección. */
  seguidoresNeto: { texto: string; pct: string; porDia: string; signo: "sube" | "baja" | "igual" } | null;
  // --- Mezcla de interacciones (agregada, una barra 100 %) ---
  desgloseMix: { segmentos: SegmentoMix[]; total: number; altoValorPct: number };
  // --- Top piezas ---
  topPiezas: FilaPiezaInforme[];
  /** Fracción del total de vistas que aportó la pieza nº 1 (insight de la estrella). */
  pctEstrella: number;
  /** Cuántas veces rindió la pieza nº 1 frente a la pieza media del periodo (0 si no aplica). */
  multiploEstrella: number;
  /** Comparativa por marca (ranking); [] cuando no es modo "todas". */
  cuentas: FilaRanking[];
  conclusiones: ConclusionInforme[];
  /** Recomendaciones accionables para el próximo periodo (2-3, deterministas). */
  recomendaciones: string[];
}
