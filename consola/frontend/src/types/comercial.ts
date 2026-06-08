import type { ActualComercial, MarcaDisponible } from "../types.gen";

// --- Comercial (seguimiento de publicaciones comerciales) ---

export type EstadoComercial = "activa" | "pausada" | "cerrada";
export type MetricaComercial = "interacciones" | "visualizaciones" | "alcance";

// `SnapshotComercial`, `ActualComercial`, `PublicacionComercial` (`api/comercial._a_dict`)
// y las respuestas `RespuestaPublicacionesComercial`/`RespuestaPublicacionComercial`/
// `RespuestaRefrescarComercial` se GENERAN desde el backend y se re-exportan desde el
// barrel (#101/#120). `fuente`/`es_muestra` (#124) son REQUERIDOS (el backend siempre los
// emite). El reporte (`RespuestaReporteComercial`, unión publicación|campaña) sigue a
// mano: su forma es polimórfica y aún no se modela en el subconjunto estable.

export interface OpcionComercial {
  id: string;
  nombre: string;
}

export interface RedComercial {
  id: string;
  nombre: string;
  limite?: number;
}

export interface OpcionesComercial {
  marcas: MarcaDisponible[];
  redes: RedComercial[];
  estados: OpcionComercial[];
  metricas: OpcionComercial[];
}

export interface CuerpoCrearComercial {
  /** Identidad preferida: el post real de Metricool elegido en el selector. */
  id_post_metricool?: string;
  /** Derivada del post (opcional); legado para el alta por enlace en demo. */
  url?: string;
  titulo?: string;
  marca?: string;
  cliente?: string;
  campania?: string;
  red?: string;
  metrica_objetivo?: MetricaComercial;
  objetivo?: number;
  estado?: EstadoComercial;
  publicado?: string;
  notas?: string;
}

export type CuerpoActualizarComercial = Partial<
  Omit<CuerpoCrearComercial, "url" | "id_post_metricool">
>;

export interface FiltrosComercial {
  estado?: string;
  cliente?: string;
  campania?: string;
  /** Permite pasarse a `query()` (Record<string, string | undefined>). */
  [clave: string]: string | undefined;
}

/** Datos de una pieza dentro de un reporte (nombres ya resueltos en servidor). */
export interface PiezaReporteComercial {
  id: string;
  titulo: string;
  url: string;
  cliente: string;
  campania: string;
  marca: string;
  marca_nombre: string;
  red: string;
  red_nombre: string;
  publicado: string;
  estado: EstadoComercial;
}

export interface ObjetivoReporteComercial {
  metrica: MetricaComercial;
  valor: number;
  progreso_pct: number;
  alcanzado: boolean;
  aviso_en: string;
}

export interface ReportePublicacionComercial {
  tipo: "publicacion";
  generado: string;
  /** Procedencia de las cifras (`"muestra"` = sintéticas). */
  fuente?: string;
  /** `true` mientras las cifras sean de muestra (sintéticas), no reales. */
  es_muestra?: boolean;
  publicacion: PiezaReporteComercial;
  periodo: { desde: string; hasta: string };
  actual: ActualComercial;
  objetivo: ObjetivoReporteComercial;
  puntos: number;
}

export interface FilaReporteCampania {
  publicacion: PiezaReporteComercial;
  actual: ActualComercial;
  objetivo: ObjetivoReporteComercial;
}

export interface ReporteCampaniaComercial {
  tipo: "campania";
  generado: string;
  /** Procedencia de las cifras (`"muestra"` = sintéticas). */
  fuente?: string;
  /** `true` mientras las cifras sean de muestra (sintéticas), no reales. */
  es_muestra?: boolean;
  campania: string;
  cliente: string;
  piezas: FilaReporteCampania[];
  total: {
    interacciones: number;
    alcance: number;
    engagement_pct: number;
    piezas: number;
  };
}

export type ReporteComercial = ReportePublicacionComercial | ReporteCampaniaComercial;

export interface RespuestaReporteComercial {
  reporte: ReporteComercial;
}
