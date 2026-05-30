/**
 * Utilidad de composición de copy al editar/generar una publicación.
 *
 * (El catálogo de plantillas vive ahora unificado en `/activos/plantillas`; ver
 * `components/plantillas/`.)
 */

/**
 * Añade un enlace al final de un contenido. Inserta un par de saltos de línea
 * de separación si el contenido ya tenía texto; evita duplicar el enlace si ya
 * aparece tal cual.
 */
export function agregarEnlace(contenido: string, enlace: string): string {
  const url = enlace.trim();
  if (!url) return contenido;
  if (contenido.includes(url)) return contenido;
  const base = contenido.replace(/\s+$/, "");
  const sep = base ? "\n\n" : "";
  return `${base}${sep}${url}`;
}
