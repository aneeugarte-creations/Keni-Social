/**
 * Contrato del Informe (deck PDF de Métricas): props ya listas para pintar, derivadas de los
 * datos reales por `desdeEntradas`. El componente `<Informe>` NO conoce React Query ni las
 * formas crudas del backend: solo consume estas props. Es el seam entre el adaptador (datos)
 * y la UI (deck).
 */

/** Tile de KPI del resumen. `delta` = variación vs periodo anterior (null = sin comparativa). */
export interface KpiInforme {
  etiqueta: string;
  valor: string;
  /** Texto largo para el title (número completo). */
  titulo: string;
  delta?: { texto: string; signo: "sube" | "baja" | "igual" | "nuevo" };
}

/** Serie apilada para un BarChart de Tremor (colores ya resueltos a hex/nombre Tremor). */
export interface SerieApilada {
  data: Array<Record<string, string | number>>;
  categorias: string[];
  colores: string[];
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
}

/** Fila de la comparativa por marca (solo modo "todas"). */
export interface CuentaInforme {
  marca: string;
  /** Duplicado de `vistas` con la clave que espera el BarChart (categoría "Vistas"). */
  Vistas: number;
  vistas: number;
  pct: number;
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
  kpis: KpiInforme[];
  tendencia: Array<{ fecha: string; Vistas: number }>;
  porRed: SerieApilada;
  seguidores: Array<{ fecha: string; Total: number }>;
  desglose: SerieApilada;
  topPiezas: FilaPiezaInforme[];
  /** Comparativa por marca; [] cuando no es modo "todas". */
  cuentas: CuentaInforme[];
  conclusiones: ConclusionInforme[];
  foco: string;
}
