import { useQuery } from "@tanstack/react-query";
import * as React from "react";
import { toast } from "sonner";

import { api, ApiError } from "@/lib/api";
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
 *
 * SONDEO vs SSE (#137): se MANTIENE el sondeo (cada ~1.2 s) y se le añade cancelación.
 * Es el cambio más pequeño y robusto: el registro YAML en disco ya es la fuente de verdad
 * (el backend persiste el texto en vivo token a token), el sondeo SOBREVIVE a recargas y
 * cambios de pestaña sin reconexión, y reaprovecha React Query (reintentos, dedupe). Mover
 * a SSE obligaría a mantener una conexión abierta por trabajo, reconectar al navegar y un
 * endpoint de streaming nuevo, sin un pago de UX que lo justifique (el desfase de ~1.2 s es
 * imperceptible). La pieza que faltaba —parar un trabajo colgado— se resuelve con `cancelar`
 * (un POST), no con streaming.
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
        // CARRERA: si mientras resolvía este fetch el usuario YA lanzó una generación
        // nueva (`iniciar`), la reanudación NO debe pisarla con la vieja. Solo se aplica
        // si seguimos sin generación activa (functional update: lee el estado vigente).
        if (vivo) setGeneracion((prev) => prev ?? r.generacion);
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

  // CANCELACIÓN (#137): pide al backend matar el árbol del subproceso `claude` del job en
  // vuelo. El backend responde con el registro en estado terminal; lo fijamos en el estado
  // local para CORTAR el sondeo de inmediato (en vez de esperar al siguiente tick). El
  // trabajo corre en el servidor; esto solo lo detiene y refleja el resultado. Best-effort:
  // si la llamada falla (p. ej. ya terminó), el sondeo normal converge igual.
  const [cancelando, setCancelando] = React.useState(false);
  const cancelar = React.useCallback(async () => {
    if (!actualId) return;
    setCancelando(true);
    try {
      const r = await api.cancelarGeneracion(actualId);
      setGeneracion(r.generacion);
    } catch (e) {
      // El job ya pudo terminar antes de que llegara la cancelación: 404 (ya no existe)
      // o 409 (ya en estado terminal) se ignoran a propósito; el sondeo refleja el
      // estado real. Cualquier OTRO error (red caída, 401, 5xx) sí merece feedback:
      // la cancelación no se aplicó y el usuario debe saberlo.
      const yaTermino = e instanceof ApiError && (e.status === 404 || e.status === 409);
      if (!yaTermino) {
        const mensaje = e instanceof ApiError || e instanceof Error ? e.message : null;
        toast.error(mensaje ? `No se pudo cancelar: ${mensaje}` : "No se pudo cancelar el trabajo.");
      }
    } finally {
      setCancelando(false);
    }
  }, [actualId]);

  return {
    /** La generación más reciente conocida (en vivo mientras corre), o `null`. */
    generacion: actual,
    /** `true` mientras corre en segundo plano. */
    ejecutando: estaEjecutando(actual?.estado),
    /** `true` mientras está en curso la petición de cancelación. */
    cancelando,
    /** Arranca el seguimiento de una generación recién lanzada. */
    iniciar,
    /** Olvida la generación actual (limpia la vista y el sessionStorage). */
    limpiar,
    /** Cancela el trabajo en vuelo (mata el subproceso en el servidor). */
    cancelar,
  };
}
