/**
 * Líneas del plan editorial — catálogo y etiquetas compartidas.
 *
 * La taxonomía de líneas (categorías del plan diario: mx, internacional, breaking…) se usa
 * en Programación (plan + horarios), en el Monitor y en la Mesa de redacción de Noticias.
 * Vive aquí para que las superficies digan lo mismo. El conjunto de líneas que ve CADA marca
 * es editable («Plan y horarios»); esto es solo el catálogo de sugerencias y sus etiquetas.
 */

/** Catálogo de líneas conocidas (clave = categoría, etiqueta = nombre legible). Las que tienen
 *  feeds se auto-rellenan; «evergreen»/«breaking» son líneas de publicación sin feed. */
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

/** Normaliza un texto libre a clave de línea (minúsculas, sin acentos, guiones). */
export function slugLinea(texto: string): string {
  return texto
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/** Resuelve un texto del usuario (etiqueta o clave) a una clave de línea del catálogo o slug. */
export function resolverClaveLinea(texto: string): string {
  const t = texto.trim();
  if (!t) return "";
  const porEtiqueta = CATALOGO_LINEAS.find((l) => l.etiqueta.toLowerCase() === t.toLowerCase());
  if (porEtiqueta) return porEtiqueta.clave;
  return slugLinea(t);
}
