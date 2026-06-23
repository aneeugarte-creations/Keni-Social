import { etiquetaLinea } from "@/lib/lineas";

/**
 * Rótulo legible de la categoría de una pieza para la cabecera del editor: el MISMO nombre que
 * usan la Mesa de Noticias y el Detalle (`etiquetaLinea` sobre `pieza.categoria`), p. ej.
 * "salud" → "Salud", "breaking" → "Última hora", "medio-ambiente" → "Medio ambiente". Devuelve
 * cadena vacía cuando la pieza no tiene categoría (no se pinta etiqueta); `Pieza.categoria` está
 * tipado `string` pero puede faltar en runtime (piezas legadas/parciales).
 */
export function etiquetaCategoriaPieza(categoria: string | null | undefined): string {
  const slug = (categoria ?? "").trim();
  if (!slug) return "";
  return etiquetaLinea(slug);
}
