/**
 * Helpers puros del editor de placa inline (sin estado React): geometría del titular, familias de
 * fuentes de un documento y carga de imágenes.
 */
import type { OrigenImagenPropio } from "@/components/media/EditorImagen";
import type { CapaTexto, Documento } from "@/editor/documento";
import { familiaRealDe } from "@/lib/placa/render";

/**
 * Origen PROPIO a DECLARAR cuando se REEMPLAZA la foto de un hueco por una propia (subir/galería/IA).
 * Solo el HUECO 0 —el FONDO de la placa, que porta el `foto` y la metadata de licencia de la pieza—
 * declara origen: sustituirlo limpia el crédito/stock heredado de la foto anterior. Un hueco
 * SECUNDARIO del collage no toca esa metadata, así que devuelve null (no declarar: declararlo
 * borraría la metadata de un fondo de stock que sigue en pie y lo desbloquearía sin licencia).
 */
export function origenFondoPropio(
  slot: number,
  origen: OrigenImagenPropio,
): OrigenImagenPropio | null {
  return slot === 0 ? origen : null;
}

/**
 * Caja (en px de lienzo) que ocupa la capa del titular, para situar el editor in place encima.
 * Modo CAJA (la capa trae `h>0`): la caja es ESA, fija e inamovible (`[y, y+h]`); el render
 * encoge el texto para caber. Modo LEGADO (`h<=0`, plantillas antiguas sin alto): se estima por
 * nº de líneas × interlineado, y con `ancla:"abajo"` el bloque crece hacia arriba desde `y`.
 */
export function cajaTitularLienzo(c: CapaTexto): { x: number; y: number; w: number; h: number } {
  if (c.h > 0) return { x: c.x, y: c.y, w: c.w, h: c.h };
  const interlineado = c.interlineado || 1.14;
  const maxLineas = Math.max(1, c.auto_ajuste?.max_lineas ?? 2);
  const h = Math.round(c.tamano * interlineado * maxLineas);
  return { x: c.x, y: c.ancla === "abajo" ? c.y - h : c.y, w: c.w, h };
}

/** Familias (reales) que usa un documento, para precargar solo esas fuentes. */
export function familiasDeDocumento(doc: Documento): string[] {
  const fr = familiaRealDe(doc.fuentes);
  const reales = new Set<string>([doc.fuentes.sans, doc.fuentes.condensada]);
  for (const c of doc.capas) {
    if (c.tipo === "texto") reales.add(fr(c.familia));
    else if (c.tipo === "logo" && c.tipo_logo === "wordmark") reales.add(fr(c.wordmark.familia));
  }
  return [...reales].filter(Boolean);
}

/** Carga una URL como `HTMLImageElement` (o null si falla/está vacía). */
export function cargarImagen(url: string | null): Promise<HTMLImageElement | null> {
  if (!url) return Promise.resolve(null);
  return new Promise((resolve) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => resolve(img);
    img.onerror = () => resolve(null);
    img.src = url;
  });
}
