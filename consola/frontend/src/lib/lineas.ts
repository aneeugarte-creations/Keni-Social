/**
 * Líneas del plan editorial — etiquetas compartidas.
 *
 * La taxonomía de líneas (categorías del plan diario: mx, internacional, breaking…) se usa
 * en Programación (plan + horarios), en el Monitor y en la Mesa de redacción de Noticias.
 * Vive aquí para que las tres superficies digan lo mismo.
 */

/** Etiquetas legibles de las líneas del plan (fallback: la categoría capitalizada). */
export const ETIQUETA_LINEA: Record<string, string> = {
  mx: "Nacional",
  internacional: "Internacional",
  breaking: "Última hora",
  entretenimiento: "Entretenimiento",
  deportes: "Deportes",
  tendencias: "Tendencias",
  "ciencia-tech": "Ciencia y tec",
  gaming: "Gaming",
  evergreen: "Evergreen",
};

/** Etiqueta humana de una línea ('' → "Sin línea"; desconocida → capitalizada). */
export function etiquetaLinea(linea: string): string {
  if (!linea) return "Sin línea";
  return ETIQUETA_LINEA[linea] ?? linea.charAt(0).toUpperCase() + linea.slice(1);
}
