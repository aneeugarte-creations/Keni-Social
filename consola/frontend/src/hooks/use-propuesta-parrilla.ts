import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { EstadoPropuestaParrilla, PropuestaParrilla } from "@/types";

/** Cada cuánto sondeamos una propuesta mientras la genera el `claude -p`. */
const INTERVALO_MS = 1500;

/** `true` mientras el `claude -p` sigue analizando el documento. */
export function estaGenerando(estado: EstadoPropuestaParrilla | string | undefined): boolean {
  return estado === "generando";
}

/**
 * Sondea una PROPUESTA de import de parrilla por su id.
 *
 * Mismo patrón que `useGeneracion` (sondeo con React Query + `refetchInterval`), pero
 * contra el endpoint propio de la propuesta: `GET /api/parrilla/propuestas/{id}`. La
 * propuesta lleva su PROPIO estado (`generando` → `pendiente`/`error`), así que sondeamos
 * eso (no la generación cruda): se detiene en cuanto `estado != "generando"`.
 *
 * El `claude -p` corre en el servidor; esto solo refresca la vista. `enabled` deja que la
 * página no sondee hasta tener un `id` (p. ej. justo tras subir el documento).
 */
export function usePropuestaParrilla(id: string | null | undefined) {
  const { data, error, isPending, refetch } = useQuery({
    queryKey: ["parrilla", "propuesta", id] as const,
    queryFn: ({ signal }) => api.propuestaParrilla(id!, signal),
    enabled: Boolean(id),
    refetchInterval: (q) => (estaGenerando(q.state.data?.estado) ? INTERVALO_MS : false),
  });

  return {
    /** La propuesta más reciente conocida, o `undefined` mientras carga. */
    propuesta: data as PropuestaParrilla | undefined,
    /** `true` mientras el `claude -p` la genera. */
    generando: estaGenerando(data?.estado),
    /** `true` mientras se resuelve el primer fetch. */
    cargando: Boolean(id) && isPending,
    error,
    refetch,
  };
}
