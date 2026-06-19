/**
 * Rótulos legibles de los SLUGS de categoría del pool de NOTICIAS (mx, internacional, breaking…).
 *
 * El Plan, la programación y las métricas hablan ya en LÍNEAS reales (etiquetas vertical); este
 * mapa solo traduce el slug de categoría que arrastra una HISTORIA del pool (pre-pieza, capa de
 * ingesta) a un nombre legible para la Mesa de Noticias y el Detalle. No es el catálogo del plan.
 */

/** Catálogo de slugs de categoría conocidos (clave = slug, etiqueta = nombre legible). */
export const CATALOGO_LINEAS: { clave: string; etiqueta: string }[] = [
  { clave: "mx", etiqueta: "Nacional" },
  { clave: "internacional", etiqueta: "Internacional" },
  { clave: "breaking", etiqueta: "Última hora" },
  { clave: "entretenimiento", etiqueta: "Entretenimiento" },
  { clave: "evergreen", etiqueta: "Evergreen" },
  { clave: "regional", etiqueta: "Regional" },
  { clave: "deportes", etiqueta: "Deportes" },
  { clave: "futbol", etiqueta: "Fútbol" },
  { clave: "motor", etiqueta: "Motor" },
  { clave: "otros-deportes", etiqueta: "Otros deportes" },
  { clave: "gaming", etiqueta: "Gaming" },
  { clave: "negocios", etiqueta: "Negocios" },
  { clave: "tendencias", etiqueta: "Tendencias" },
  { clave: "ciencia-tech", etiqueta: "Ciencia y tecnología" },
  { clave: "salud", etiqueta: "Salud" },
  { clave: "medio-ambiente", etiqueta: "Medio ambiente" },
  { clave: "cultura", etiqueta: "Cultura" },
  { clave: "educacion", etiqueta: "Educación" },
  { clave: "impacto-social", etiqueta: "Impacto social" },
];

/** Etiquetas legibles de las líneas (fallback: la categoría capitalizada). */
export const ETIQUETA_LINEA: Record<string, string> = Object.fromEntries(
  CATALOGO_LINEAS.map((l) => [l.clave, l.etiqueta]),
);

/** Etiqueta humana de una línea ('' → "Sin línea"; desconocida → capitalizada). */
export function etiquetaLinea(linea: string): string {
  if (!linea) return "Sin línea";
  return ETIQUETA_LINEA[linea] ?? linea.charAt(0).toUpperCase() + linea.slice(1);
}
