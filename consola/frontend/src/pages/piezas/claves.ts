import type { QueryClient } from "@tanstack/react-query";

import type { Pieza } from "@/types";

/** Claves de React Query para piezas (raíz para invalidar en bloque). */
export const CLAVE_PIEZAS = ["piezas"] as const;

/** Clave de la cadena de aprobación de UNA pieza (la precarga el batch del feed). */
export const claveCadenaAprobacion = (piezaId: string) =>
  ["cadena-aprobacion", piezaId] as const;

/**
 * Sustituye UNA publicación dentro de las cachés de listados (sin refetch). Soporta las dos
 * formas que viven bajo `CLAVE_PIEZAS`: la respuesta plana `{piezas: [...]}`
 * (lista/calendario) y la de infinite query `{pages: [{piezas: [...]}]}` (feed).
 * Cualquier otra forma (p. ej. `piezas/opciones`) se devuelve intacta.
 *
 * La usa el feed tras una reacción (like/dislike/deshacer/forzar): actualizar la pieza
 * afectada en sitio evita invalidar `CLAVE_PIEZAS` entero (que refetcheaba TODAS
 * las páginas del scroll infinito por cada click).
 */
export function remplazarPiezaEnCaches(queryClient: QueryClient, pub: Pieza): void {
  const remplazar = (lista: Pieza[]): Pieza[] =>
    lista.map((p) => (p.id === pub.id ? pub : p));
  queryClient.setQueriesData({ queryKey: CLAVE_PIEZAS }, (datos: unknown) => {
    if (!datos || typeof datos !== "object") return datos;
    if (Array.isArray((datos as { piezas?: unknown }).piezas)) {
      const d = datos as { piezas: Pieza[] };
      return { ...d, piezas: remplazar(d.piezas) };
    }
    if (Array.isArray((datos as { pages?: unknown }).pages)) {
      const d = datos as { pages: unknown[] };
      return {
        ...d,
        pages: d.pages.map((pagina) => {
          if (!pagina || typeof pagina !== "object") return pagina;
          if (!Array.isArray((pagina as { piezas?: unknown }).piezas)) return pagina;
          const pg = pagina as { piezas: Pieza[] };
          return { ...pg, piezas: remplazar(pg.piezas) };
        }),
      };
    }
    return datos;
  });
}
