/**
 * Catálogo de SECCIONES configurables del dashboard de Métricas.
 *
 * Fuente única de los ids estables de sección (los consumen `Metricas.tsx` para el
 * render condicional, el panel "Configurar vista" para los checkboxes y, de forma
 * implícita vía `vistaConfig`, las vistas guardadas). Agrupadas para presentarlas
 * ordenadas en el panel. La visibilidad efectiva la resuelve `vistaConfig`
 * (`seccionVisible`): un id ausente = visible.
 */
export interface SeccionMeta {
  /** Id estable (no traducir; es la clave que persiste en `vistaConfig.secciones`). */
  id: string;
  /** Etiqueta legible (es-MX) para el panel de configuración. */
  etiqueta: string;
}

export interface GrupoSecciones {
  titulo: string;
  secciones: SeccionMeta[];
}

export const GRUPOS_SECCIONES: GrupoSecciones[] = [
  {
    titulo: "Resumen",
    secciones: [
      { id: "kpis", etiqueta: "Resumen del periodo" },
      { id: "analisis", etiqueta: "Análisis del periodo" },
      { id: "tendencia", etiqueta: "Tendencia diaria" },
    ],
  },
  {
    titulo: "Por marca",
    secciones: [
      { id: "marca-comparativa", etiqueta: "Comparativa por marca" },
      { id: "marca-detalle", etiqueta: "Detalle por marca" },
    ],
  },
  {
    titulo: "Por red",
    secciones: [
      { id: "red-evolucion", etiqueta: "Evolución por red" },
      { id: "red-detalle", etiqueta: "Detalle por red" },
      { id: "cobertura", etiqueta: "Cobertura por red" },
    ],
  },
  {
    titulo: "Estrategia digital",
    secciones: [
      { id: "seguidores", etiqueta: "Crecimiento de seguidores" },
      { id: "audiencia", etiqueta: "Altas y bajas de seguidores" },
      { id: "alcance-serie", etiqueta: "Alcance de cuenta" },
      { id: "demografia", etiqueta: "Demografía de la audiencia" },
      { id: "desglose", etiqueta: "Desglose de interacciones" },
      { id: "crosstab", etiqueta: "Rendimiento por formato" },
      { id: "por-categoria", etiqueta: "Rendimiento por categoría" },
      { id: "correlacion", etiqueta: "Seguidores frente a piezas" },
      { id: "ads", etiqueta: "Publicidad" },
    ],
  },
  {
    titulo: "Piezas",
    secciones: [
      { id: "panorama", etiqueta: "Panorama de piezas" },
      { id: "distribucion", etiqueta: "Distribución de engagement" },
      { id: "piezas-tabla", etiqueta: "Piezas del periodo" },
    ],
  },
  {
    titulo: "Comparativa",
    secciones: [{ id: "comparativa", etiqueta: "Comparar periodos" }],
  },
];

/** Todas las secciones aplanadas (orden de aparición). */
export const SECCIONES: SeccionMeta[] = GRUPOS_SECCIONES.flatMap((g) => g.secciones);

/** Todos los ids de sección, en orden de aparición. */
export const IDS_SECCIONES: string[] = SECCIONES.map((s) => s.id);

const ETIQUETA_POR_ID = new Map(SECCIONES.map((s) => [s.id, s.etiqueta]));

/** Etiqueta legible de una sección por su id (fuente única para cabeceras y barras ocultas). */
export function etiquetaSeccion(id: string): string {
  return ETIQUETA_POR_ID.get(id) ?? id;
}
