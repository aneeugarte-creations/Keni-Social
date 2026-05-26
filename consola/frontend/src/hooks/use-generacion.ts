import { useQuery } from "@tanstack/react-query";
import * as React from "react";

import { api } from "@/lib/api";
import type { Generacion } from "@/types";

/** Cada cuánto sondeamos una generación en curso. */
const INTERVALO_MS = 1200;

/** `true` mientras la generación sigue en segundo plano. */
export function estaEjecutando(estado: string | undefined): boolean {
  return estado === "ejecutando";
}

/**
 * Sigue un TRABAJO de IA en segundo plano (copy/RSS/hashtags/imagen).
 *
 * El POST que lo lanza devuelve una `Generacion` con `estado="ejecutando"`; se la
 * pasamos a `iniciar(...)` y este hook SONDEA `GET /api/generaciones/{id}` cada
 * ~1.2 s hasta el estado terminal (`completado`/`error`), devolviendo la versión más
 * reciente (con el texto en vivo y las métricas parciales).
 *
 * ROBUSTEZ ANTE NAVEGACIÓN: si se pasa `persistKey`, el id de la generación en curso
 * se guarda en `sessionStorage`; al montar de nuevo (cambiar de pestaña y volver) el
 * hook REANUDA el sondeo de esa generación. El trabajo nunca se detiene (corre en el
 * servidor); esto solo recupera la vista en vivo. Al terminar, se limpia la clave.
 */
export function useGeneracion(persistKey?: string) {
  const [generacion, setGeneracion] = React.useState<Generacion | null>(null);

  // Reanudar desde sessionStorage al montar (solo si hay persistKey y un id guardado).
  React.useEffect(() => {
    if (!persistKey) return;
    const id = sessionStorage.getItem(persistKey);
    if (!id) return;
    let vivo = true;
    api
      .generacion(id)
      .then((r) => {
        if (vivo) setGeneracion(r.generacion);
      })
      .catch(() => {
        sessionStorage.removeItem(persistKey);
      });
    return () => {
      vivo = false;
    };
  }, [persistKey]);

  // A-1: la query de sondeo NO usa initialData para evitar que React Query marque
  // la entrada como ya-fresca y salte el primer refetch cuando el POST responde
  // directamente con estado "completado" (completado-inmediato). El fallback al
  // estado local se aplica solo para el primer render (antes del primer fetch).
  const habilitado = generacion !== null && estaEjecutando(generacion.estado);

  const { data } = useQuery({
    queryKey: ["generacion", generacion?.id],
    queryFn: ({ signal }) => api.generacion(generacion!.id, signal).then((r) => r.generacion),
    enabled: habilitado,
    // Sin initialData: la query parte de undefined y sondea desde la 1ª llamada.
    refetchInterval: (q) =>
      estaEjecutando(q.state.data?.estado ?? generacion?.estado) ? INTERVALO_MS : false,
  });

  // Si la query ya obtuvo datos los preferimos; si no, usamos el estado local
  // (cubre el caso completado-inmediato antes del primer fetch y el estado inicial).
  const actual = data ?? generacion;
  const actualId = actual?.id;
  const actualEstado = actual?.estado;

  // Persistimos el id mientras corre; lo limpiamos al terminar.
  React.useEffect(() => {
    if (!persistKey || !actualId) return;
    if (estaEjecutando(actualEstado)) sessionStorage.setItem(persistKey, actualId);
    else sessionStorage.removeItem(persistKey);
  }, [actualId, actualEstado, persistKey]);

  const iniciar = React.useCallback((g: Generacion) => setGeneracion(g), []);
  const limpiar = React.useCallback(() => {
    setGeneracion(null);
    if (persistKey) sessionStorage.removeItem(persistKey);
  }, [persistKey]);

  return {
    /** La generación más reciente conocida (en vivo mientras corre), o `null`. */
    generacion: actual,
    /** `true` mientras corre en segundo plano. */
    ejecutando: estaEjecutando(actual?.estado),
    /** Arranca el seguimiento de una generación recién lanzada. */
    iniciar,
    /** Olvida la generación actual (limpia la vista y el sessionStorage). */
    limpiar,
  };
}
