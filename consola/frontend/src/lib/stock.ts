/**
 * Fotos de STOCK: ayuda visual NUNCA publicable sin autorizar.
 *
 * Una foto de stock se baja de una API gratuita o de la imagen original del artículo (RSS) y se
 * adjunta a la pieza como referencia. Mientras un humano no confirme que tiene derechos, la pieza
 * queda `imagen_origen="stock"` y `imagen_autorizada=false`: el back deja `falta_imagen` activo y
 * bloquea publicar (409). El front la pinta ATENUADA + watermark "SIN LICENCIA".
 */
import type { Pieza } from "@/types";

/** Valor de `imagen_origen` cuando la imagen adjunta es una foto de stock (ayuda visual). */
export const ORIGEN_STOCK = "stock";

/** Subconjunto de campos de stock que comparten `Pieza` y las respuestas de los endpoints stock. */
export interface DatosStock {
  imagen_origen?: string;
  imagen_proveedor?: string;
  imagen_autor?: string;
  imagen_licencia?: string;
  imagen_credito_url?: string;
  imagen_autorizada?: boolean;
}

/** ¿Esta pieza lleva una imagen de stock (autorizada o no)? */
export function esStock(p: DatosStock): boolean {
  return (p.imagen_origen ?? "") === ORIGEN_STOCK;
}

/**
 * STOCK_NO_AUTORIZADO: foto de stock que un humano AÚN no ha autorizado a publicar. Es la condición
 * que dispara el tratamiento visual (atenuada + "SIN LICENCIA") y el bloqueo de publicar en la UI.
 */
export function stockNoAutorizado(p: DatosStock): boolean {
  return esStock(p) && !p.imagen_autorizada;
}

/** Stock que un humano YA autorizó: la imagen vale como real (badge sutil, sin overlay). */
export function stockAutorizado(p: DatosStock): boolean {
  return esStock(p) && !!p.imagen_autorizada;
}

/** Mensaje único del bloqueo de publicar por stock sin licencia (tooltips/toasts/avisos). */
export const MENSAJE_BLOQUEO_STOCK =
  "Imagen de stock SIN LICENCIA: autorízala o sustitúyela antes de publicar.";

/** Nombre legible de un proveedor de stock para badges/atribución. */
export function nombreProveedor(proveedor: string | undefined): string {
  const p = (proveedor ?? "").trim().toLowerCase();
  const nombres: Record<string, string> = {
    pexels: "Pexels",
    pixabay: "Pixabay",
    wikimedia: "Wikimedia",
    nasa: "NASA",
    openverse: "Openverse",
    rss: "Fuente original",
    stock: "Stock",
  };
  return nombres[p] || (p ? p.charAt(0).toUpperCase() + p.slice(1) : "Stock");
}

/**
 * Consulta inicial del buscador de stock a partir del TÍTULO del tema de la pieza. El título suele
 * traer un sufijo " — <vertical>" (p. ej. "Negociaciones EE.UU.-Irán — Diplomacia"): lo cortamos y
 * usamos solo el tema, para que las APIs gratuitas devuelvan fotos relevantes y no aleatorias.
 */
export function temaDeTitulo(titulo: string | undefined): string {
  return (titulo ?? "").split(" — ")[0].trim();
}

/**
 * Consulta por defecto del buscador de fotos de stock: prefiere la KEYWORD visual que propone
 * Sugerir hashtags (`imagen_clave`, sujeto visual de 2-4 palabras), y cae al TEMA del título si no
 * la hay. Así la primera búsqueda da fotos del sujeto, no del titular largo.
 */
export function keywordBusqueda(p: { imagen_clave?: string; titulo?: string }): string {
  return p.imagen_clave?.trim() || temaDeTitulo(p.titulo);
}

/** Pie de atribución de una candidata/imagen de stock: "autor · licencia · proveedor". */
export function atribucionStock(d: {
  autor?: string;
  licencia?: string;
  proveedor?: string;
}): string {
  return [d.autor, d.licencia, nombreProveedor(d.proveedor)].filter((x) => !!x?.trim()).join(" · ");
}

/** Misma condición sobre una `Pieza` completa (azúcar de tipado para los consumidores). */
export function piezaStockNoAutorizado(p: Pieza): boolean {
  return stockNoAutorizado(p);
}
