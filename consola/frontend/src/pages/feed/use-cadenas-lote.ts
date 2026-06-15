/**
 * BATCH de cadenas de aprobación del feed: UNA llamada por página de feed en vez del N+1
 * de un `GET /plataformas/{id}/aprobacion` por pieza visible.
 *
 * Cómo encaja con las queries individuales de `PostFeed` (que se conservan como fuente de
 * verdad por pieza, p. ej. para refrescar SOLO la pieza reaccionada):
 *
 *  1. De las piezas cargadas se toman las que NECESITAN cadena (en revisión / aprobadas)
 *     y que AÚN no tienen nada en caché bajo `claveCadenaAprobacion(id)`.
 *  2. Esas ids "faltantes" se piden en UNA llamada (`GET /api/publicaciones/cadenas?ids=`)
 *     y el resultado se REPARTE con `setQueryData` a las claves individuales existentes.
 *  3. Mientras el lote está en curso, `pendiente(id)` devuelve true: `PostFeed` mantiene su
 *     query individual DESHABILITADA para esas ids (si no, cada tarjeta dispararía su GET
 *     en paralelo al lote y volveríamos al N+1). Al aterrizar el lote, las queries
 *     individuales encuentran datos frescos precargados y no refetchean (staleTime).
 *
 * El backend SIEMPRE devuelve una entrada por id pedida (sin cadena => `sin_cadena`), así
 * que ninguna id se queda "faltante" para siempre. Si el lote FALLA, `pendiente` se apaga
 * y las queries individuales hacen de fallback (comportamiento previo).
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { api } from "@/lib/api";
import { claveCadenaAprobacion } from "@/pages/publicaciones/claves";
import type { Publicacion } from "@/types";

import { etapaDePublicacion } from "./etapa";

/** Las piezas cuya cadena importa (mismo gate que `PostFeed`): en revisión o ya aprobadas. */
function necesitaCadena(p: Publicacion): boolean {
  return p.estado === "en_revision" || etapaDePublicacion(p) === "aprobada";
}

const NINGUNA: ReadonlySet<string> = new Set();

/**
 * Contexto que el feed provee a sus `PostFeed`: fuera del feed (otras superficies, tests)
 * es `null` y cada tarjeta carga su cadena individual como siempre.
 */
export const CadenasLoteContexto = React.createContext<{
  pendiente: (id: string) => boolean;
} | null>(null);

export function useCadenasLote(piezas: Publicacion[]): {
  /** true mientras la cadena de esa pieza viene en el lote en curso (no dispares tu GET). */
  pendiente: (id: string) => boolean;
} {
  const queryClient = useQueryClient();

  const elegibles = React.useMemo(
    () => [...new Set(piezas.filter(necesitaCadena).map((p) => p.id))],
    [piezas],
  );
  // Solo las que aún no tienen caché individual: las ya precargadas (o refrescadas tras una
  // reacción) no se vuelven a pedir en lote. Se recalcula en cada render; al aterrizar el
  // lote (precarga + rerender) queda vacío y la query se deshabilita sola.
  const faltantes = elegibles.filter(
    (id) => queryClient.getQueryData(claveCadenaAprobacion(id)) === undefined,
  );
  const claveLote = faltantes.join(",");

  const loteQuery = useQuery({
    queryKey: ["cadenas-aprobacion-lote", claveLote],
    enabled: faltantes.length > 0,
    // El lote es un mecanismo de PRECARGA, no una caché a mantener: una vez repartido,
    // la verdad vive en las claves individuales.
    staleTime: Infinity,
    gcTime: 0,
    queryFn: async ({ signal }) => {
      const res = await api.cadenasAprobacion(faltantes, signal);
      for (const [id, cadena] of Object.entries(res.cadenas)) {
        queryClient.setQueryData(claveCadenaAprobacion(id), cadena);
      }
      return res;
    },
  });

  const enVuelo = loteQuery.isFetching;
  const pendientes = React.useMemo<ReadonlySet<string>>(
    () => (enVuelo ? new Set(faltantes) : NINGUNA),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- faltantes se identifica por claveLote
    [enVuelo, claveLote],
  );
  return React.useMemo(
    () => ({ pendiente: (id: string) => pendientes.has(id) }),
    [pendientes],
  );
}
