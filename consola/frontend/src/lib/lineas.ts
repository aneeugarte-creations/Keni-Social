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

/** Clases Tailwind del color de UNA línea, para señal visual consistente en programación. */
export interface ColorLinea {
  /** Texto en el tono de la línea (con su variante dark). */
  texto: string;
  /** Punto/acento sólido (un círculo de color). */
  punto: string;
  /** Borde en el tono (huecos del plan). */
  borde: string;
  /** Barra de progreso sólida (capa "publicados" del KPI). */
  barra: string;
  /** Barra suave (capa "generados" del KPI). */
  barraSuave: string;
}

// Color por LÍNEA editorial: cada línea (Evergreen, Internacional, Nacional…) tiene un tono fijo
// para distinguirlas de un vistazo en el plan y los KPIs. Tonos del 500/700 (texto legible);
// las clases son literales porque el JIT de Tailwind solo ve cadenas completas (no concatenadas).
const _c = (
  texto: string,
  punto: string,
  borde: string,
  barra: string,
  barraSuave: string,
): ColorLinea => ({ texto, punto, borde, barra, barraSuave });

export const COLOR_LINEA: Record<string, ColorLinea> = {
  evergreen: _c("text-emerald-700 dark:text-emerald-300", "bg-emerald-500", "border-emerald-400 dark:border-emerald-500", "bg-emerald-500", "bg-emerald-500/30"),
  internacional: _c("text-sky-700 dark:text-sky-300", "bg-sky-500", "border-sky-400 dark:border-sky-500", "bg-sky-500", "bg-sky-500/30"),
  mx: _c("text-indigo-700 dark:text-indigo-300", "bg-indigo-500", "border-indigo-400 dark:border-indigo-500", "bg-indigo-500", "bg-indigo-500/30"),
  breaking: _c("text-red-700 dark:text-red-300", "bg-red-500", "border-red-400 dark:border-red-500", "bg-red-500", "bg-red-500/30"),
  entretenimiento: _c("text-fuchsia-700 dark:text-fuchsia-300", "bg-fuchsia-500", "border-fuchsia-400 dark:border-fuchsia-500", "bg-fuchsia-500", "bg-fuchsia-500/30"),
  regional: _c("text-teal-700 dark:text-teal-300", "bg-teal-500", "border-teal-400 dark:border-teal-500", "bg-teal-500", "bg-teal-500/30"),
  deportes: _c("text-orange-700 dark:text-orange-300", "bg-orange-500", "border-orange-400 dark:border-orange-500", "bg-orange-500", "bg-orange-500/30"),
  futbol: _c("text-lime-700 dark:text-lime-300", "bg-lime-500", "border-lime-400 dark:border-lime-500", "bg-lime-500", "bg-lime-500/30"),
  motor: _c("text-amber-700 dark:text-amber-300", "bg-amber-500", "border-amber-400 dark:border-amber-500", "bg-amber-500", "bg-amber-500/30"),
  "otros-deportes": _c("text-violet-700 dark:text-violet-300", "bg-violet-500", "border-violet-400 dark:border-violet-500", "bg-violet-500", "bg-violet-500/30"),
  gaming: _c("text-purple-700 dark:text-purple-300", "bg-purple-500", "border-purple-400 dark:border-purple-500", "bg-purple-500", "bg-purple-500/30"),
  negocios: _c("text-blue-700 dark:text-blue-300", "bg-blue-500", "border-blue-400 dark:border-blue-500", "bg-blue-500", "bg-blue-500/30"),
  tendencias: _c("text-pink-700 dark:text-pink-300", "bg-pink-500", "border-pink-400 dark:border-pink-500", "bg-pink-500", "bg-pink-500/30"),
  "ciencia-tech": _c("text-cyan-700 dark:text-cyan-300", "bg-cyan-500", "border-cyan-400 dark:border-cyan-500", "bg-cyan-500", "bg-cyan-500/30"),
  salud: _c("text-rose-700 dark:text-rose-300", "bg-rose-500", "border-rose-400 dark:border-rose-500", "bg-rose-500", "bg-rose-500/30"),
  "medio-ambiente": _c("text-green-700 dark:text-green-300", "bg-green-500", "border-green-400 dark:border-green-500", "bg-green-500", "bg-green-500/30"),
  cultura: _c("text-yellow-700 dark:text-yellow-300", "bg-yellow-500", "border-yellow-400 dark:border-yellow-500", "bg-yellow-500", "bg-yellow-500/30"),
  educacion: _c("text-orange-700 dark:text-orange-300", "bg-orange-500", "border-orange-400 dark:border-orange-500", "bg-orange-500", "bg-orange-500/30"),
  "impacto-social": _c("text-teal-700 dark:text-teal-300", "bg-teal-500", "border-teal-400 dark:border-teal-500", "bg-teal-500", "bg-teal-500/30"),
};

/** Color neutro (líneas desconocidas o sin línea): mantiene el look minimalista en gris. */
export const COLOR_LINEA_NEUTRO: ColorLinea = _c(
  "text-muted-foreground",
  "bg-muted-foreground/50",
  "border-border",
  "bg-foreground",
  "bg-foreground/20",
);

/** Color (clases Tailwind) de una línea; cae a neutro si la línea no está catalogada. */
export function colorLinea(linea: string): ColorLinea {
  return COLOR_LINEA[linea] ?? COLOR_LINEA_NEUTRO;
}
