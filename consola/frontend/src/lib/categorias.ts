/**
 * Rótulos legibles de los SLUGS de categoría del pool de NOTICIAS (mx, internacional, breaking…).
 *
 * El Plan, la programación y las métricas hablan ya en CATEGORÍAS reales (etiquetas categoria); este
 * mapa solo traduce el slug de categoría que arrastra una HISTORIA del pool (pre-pieza, capa de
 * ingesta) a un nombre legible para la Mesa de Noticias y el Detalle. No es el catálogo del plan.
 */

/** Catálogo de slugs de categoría conocidos (clave = slug, etiqueta = nombre legible). */
export const CATALOGO_CATEGORIAS: { clave: string; etiqueta: string }[] = [
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

/** Etiquetas legibles de las categorías (fallback: la categoría capitalizada). */
export const ETIQUETA_CATEGORIA: Record<string, string> = Object.fromEntries(
  CATALOGO_CATEGORIAS.map((c) => [c.clave, c.etiqueta]),
);

/** Etiqueta humana de una categoría ('' → "Sin categoría"; desconocida → capitalizada). */
export function etiquetaCategoria(categoria: string): string {
  if (!categoria) return "Sin categoría";
  return ETIQUETA_CATEGORIA[categoria] ?? categoria.charAt(0).toUpperCase() + categoria.slice(1);
}

/** Clases Tailwind del color de UNA categoría, para señal visual consistente en programación. */
export interface ColorCategoria {
  /** Texto en el tono de la categoría (con su variante dark). */
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

// Color por CATEGORÍA: cada categoría (Evergreen, Internacional, Nacional…) tiene un tono fijo
// para distinguirlas de un vistazo en el plan y los KPIs. Tonos del 500/700 (texto legible);
// las clases son literales porque el JIT de Tailwind solo ve cadenas completas (no concatenadas).
// VERDE y ROJO NO se usan como color de categoría: están reservados para ESTADO (bien/mal) —
// p. ej. la píldora de una pieza (publicada=verde, vencida=rojo). Un punto de categoría verde/rojo
// se confundiría con ese significado, así que la identidad de categoría usa otros tonos.
const _c = (
  texto: string,
  punto: string,
  borde: string,
  barra: string,
  barraSuave: string,
): ColorCategoria => ({ texto, punto, borde, barra, barraSuave });

export const COLOR_CATEGORIA: Record<string, ColorCategoria> = {
  evergreen: _c("text-violet-700 dark:text-violet-300", "bg-violet-500", "border-violet-400 dark:border-violet-500", "bg-violet-500", "bg-violet-500/30"),
  internacional: _c("text-sky-700 dark:text-sky-300", "bg-sky-500", "border-sky-400 dark:border-sky-500", "bg-sky-500", "bg-sky-500/30"),
  mx: _c("text-indigo-700 dark:text-indigo-300", "bg-indigo-500", "border-indigo-400 dark:border-indigo-500", "bg-indigo-500", "bg-indigo-500/30"),
  breaking: _c("text-pink-700 dark:text-pink-300", "bg-pink-500", "border-pink-400 dark:border-pink-500", "bg-pink-500", "bg-pink-500/30"),
  entretenimiento: _c("text-fuchsia-700 dark:text-fuchsia-300", "bg-fuchsia-500", "border-fuchsia-400 dark:border-fuchsia-500", "bg-fuchsia-500", "bg-fuchsia-500/30"),
  regional: _c("text-cyan-700 dark:text-cyan-300", "bg-cyan-500", "border-cyan-400 dark:border-cyan-500", "bg-cyan-500", "bg-cyan-500/30"),
  deportes: _c("text-orange-700 dark:text-orange-300", "bg-orange-500", "border-orange-400 dark:border-orange-500", "bg-orange-500", "bg-orange-500/30"),
  futbol: _c("text-blue-700 dark:text-blue-300", "bg-blue-500", "border-blue-400 dark:border-blue-500", "bg-blue-500", "bg-blue-500/30"),
  motor: _c("text-amber-700 dark:text-amber-300", "bg-amber-500", "border-amber-400 dark:border-amber-500", "bg-amber-500", "bg-amber-500/30"),
  "otros-deportes": _c("text-violet-700 dark:text-violet-300", "bg-violet-500", "border-violet-400 dark:border-violet-500", "bg-violet-500", "bg-violet-500/30"),
  gaming: _c("text-purple-700 dark:text-purple-300", "bg-purple-500", "border-purple-400 dark:border-purple-500", "bg-purple-500", "bg-purple-500/30"),
  negocios: _c("text-blue-700 dark:text-blue-300", "bg-blue-500", "border-blue-400 dark:border-blue-500", "bg-blue-500", "bg-blue-500/30"),
  tendencias: _c("text-pink-700 dark:text-pink-300", "bg-pink-500", "border-pink-400 dark:border-pink-500", "bg-pink-500", "bg-pink-500/30"),
  "ciencia-tech": _c("text-cyan-700 dark:text-cyan-300", "bg-cyan-500", "border-cyan-400 dark:border-cyan-500", "bg-cyan-500", "bg-cyan-500/30"),
  salud: _c("text-sky-700 dark:text-sky-300", "bg-sky-500", "border-sky-400 dark:border-sky-500", "bg-sky-500", "bg-sky-500/30"),
  "medio-ambiente": _c("text-cyan-700 dark:text-cyan-300", "bg-cyan-500", "border-cyan-400 dark:border-cyan-500", "bg-cyan-500", "bg-cyan-500/30"),
  cultura: _c("text-yellow-700 dark:text-yellow-300", "bg-yellow-500", "border-yellow-400 dark:border-yellow-500", "bg-yellow-500", "bg-yellow-500/30"),
  educacion: _c("text-orange-700 dark:text-orange-300", "bg-orange-500", "border-orange-400 dark:border-orange-500", "bg-orange-500", "bg-orange-500/30"),
  "impacto-social": _c("text-purple-700 dark:text-purple-300", "bg-purple-500", "border-purple-400 dark:border-purple-500", "bg-purple-500", "bg-purple-500/30"),
};

/** Color neutro (categorías desconocidas o sin categoría): mantiene el look minimalista en gris. */
export const COLOR_CATEGORIA_NEUTRO: ColorCategoria = _c(
  "text-muted-foreground",
  "bg-muted-foreground/50",
  "border-border",
  "bg-foreground",
  "bg-foreground/20",
);

/** Color (clases Tailwind) de una categoría; cae a neutro si la categoría no está catalogada. */
export function colorCategoria(categoria: string): ColorCategoria {
  return COLOR_CATEGORIA[categoria] ?? COLOR_CATEGORIA_NEUTRO;
}
