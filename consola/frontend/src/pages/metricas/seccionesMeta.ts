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
      { id: "kpis", etiqueta: "Resumen del periodo (KPIs)" },
      { id: "analisis", etiqueta: "Análisis del periodo" },
      { id: "tendencia", etiqueta: "Tendencia diaria" },
    ],
  },
  {
    titulo: "Por marca",
    secciones: [{ id: "por-marca", etiqueta: "Comparativa y detalle por marca" }],
  },
  {
    titulo: "Por red",
    secciones: [
      { id: "por-red", etiqueta: "Evolución y detalle por red" },
      { id: "cobertura", etiqueta: "Cobertura por red" },
    ],
  },
  {
    titulo: "Estrategia digital",
    secciones: [
      { id: "seguidores", etiqueta: "Crecimiento de seguidores" },
      { id: "desglose", etiqueta: "Desglose de interacciones" },
      { id: "crosstab", etiqueta: "Cruce de métricas" },
      { id: "por-serie", etiqueta: "Rendimiento por serie" },
      { id: "por-linea", etiqueta: "Rendimiento por línea" },
      { id: "correlacion", etiqueta: "Correlación con seguidores" },
      { id: "ads", etiqueta: "Publicidad pagada" },
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

/** Todos los ids de sección, en orden de aparición. */
export const IDS_SECCIONES: string[] = GRUPOS_SECCIONES.flatMap((g) =>
  g.secciones.map((s) => s.id),
);
