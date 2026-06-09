import type { QueryClient } from "@tanstack/react-query";

import type { Publicacion } from "@/types";

/** Claves de React Query para publicaciones (raíz para invalidar en bloque). */
export const CLAVE_PUBLICACIONES = ["publicaciones"] as const;

/** Clave de la cadena de aprobación de UNA pieza (la siembra el batch del feed). */
export const claveCadenaAprobacion = (plataformaId: string) =>
  ["cadena-aprobacion", plataformaId] as const;

/**
 * Sustituye UNA publicación dentro de las cachés de listados (sin refetch). Soporta las dos
 * formas que viven bajo `CLAVE_PUBLICACIONES`: la respuesta plana `{publicaciones: [...]}`
 * (lista/calendario) y la de infinite query `{pages: [{publicaciones: [...]}]}` (feed).
 * Cualquier otra forma (p. ej. `publicaciones/opciones`) se devuelve intacta.
 *
 * La usa el feed tras una reacción (like/dislike/deshacer/forzar): actualizar la pieza
 * afectada en sitio evita invalidar `CLAVE_PUBLICACIONES` entero (que refetcheaba TODAS
 * las páginas del scroll infinito por cada click).
 */
export function remplazarPublicacionEnCaches(queryClient: QueryClient, pub: Publicacion): void {
  const remplazar = (lista: Publicacion[]): Publicacion[] =>
    lista.map((p) => (p.id === pub.id ? pub : p));
  queryClient.setQueriesData({ queryKey: CLAVE_PUBLICACIONES }, (datos: unknown) => {
    if (!datos || typeof datos !== "object") return datos;
    if (Array.isArray((datos as { publicaciones?: unknown }).publicaciones)) {
      const d = datos as { publicaciones: Publicacion[] };
      return { ...d, publicaciones: remplazar(d.publicaciones) };
    }
    if (Array.isArray((datos as { pages?: unknown }).pages)) {
      const d = datos as { pages: unknown[] };
      return {
        ...d,
        pages: d.pages.map((pagina) => {
          if (!pagina || typeof pagina !== "object") return pagina;
          if (!Array.isArray((pagina as { publicaciones?: unknown }).publicaciones)) return pagina;
          const pg = pagina as { publicaciones: Publicacion[] };
          return { ...pg, publicaciones: remplazar(pg.publicaciones) };
        }),
      };
    }
    return datos;
  });
}
