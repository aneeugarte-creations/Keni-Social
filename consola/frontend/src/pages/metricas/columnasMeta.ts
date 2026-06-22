/**
 * Catálogo de TABLAS configurables del dashboard de Métricas y sus columnas.
 *
 * Fuente única de los ids estables de tabla y de columna: los consumen las propias
 * tablas (orden/visibilidad efectivos vía `vistaConfig.columnasDe` + `columnasVisibles`)
 * y el panel "Configurar vista" (reordenar y mostrar/ocultar). El orden de `columnas`
 * aquí es el ORDEN BASE (el que se aplica si no hay nada guardado).
 */
export interface ColumnaMeta {
  /** Id estable de columna (clave que persiste en `vistaConfig.columnas[tabla]`). */
  id: string;
  /** Etiqueta legible (es-MX) para el panel de configuración. */
  etiqueta: string;
}

export interface TablaMeta {
  /** Id estable de tabla (clave en `vistaConfig.columnas`). */
  id: string;
  /** Título legible para el panel de configuración. */
  titulo: string;
  /** Columnas en su orden base. */
  columnas: ColumnaMeta[];
}

/** Id de cada tabla configurable (evita literales sueltos por el código). */
export const TABLA_CUENTAS = "cuentas";
export const TABLA_REDES = "redes";
export const TABLA_PIEZAS = "piezas";

export const TABLAS_CONFIG: TablaMeta[] = [
  {
    id: TABLA_CUENTAS,
    titulo: "Detalle por marca",
    columnas: [
      { id: "marca", etiqueta: "Marca" },
      { id: "visualizaciones", etiqueta: "Vistas" },
      { id: "interacciones", etiqueta: "Interacciones" },
      { id: "engagement_pct", etiqueta: "Engagement" },
    ],
  },
  {
    id: TABLA_REDES,
    titulo: "Detalle por red",
    columnas: [
      { id: "red", etiqueta: "Red" },
      { id: "visualizaciones", etiqueta: "Vistas" },
      { id: "interacciones", etiqueta: "Interacciones" },
      { id: "engagement_pct", etiqueta: "Engagement" },
    ],
  },
  {
    id: TABLA_PIEZAS,
    titulo: "Piezas del periodo",
    columnas: [
      { id: "pieza", etiqueta: "Pieza" },
      { id: "publicado", etiqueta: "Día" },
      { id: "visualizaciones", etiqueta: "Vistas" },
      { id: "engagement_pct", etiqueta: "Engagement" },
      { id: "comentarios", etiqueta: "Comentarios" },
      { id: "compartidos", etiqueta: "Compartidos" },
      { id: "guardados", etiqueta: "Guardados" },
      { id: "clics_enlace", etiqueta: "Clics a enlace" },
    ],
  },
];

/** Ids de columna (orden base) de una tabla. */
export function idsColumnas(tablaId: string): string[] {
  const t = TABLAS_CONFIG.find((x) => x.id === tablaId);
  return t ? t.columnas.map((c) => c.id) : [];
}
