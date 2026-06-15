import { useQuery } from "@tanstack/react-query";
import * as React from "react";
import { toast } from "sonner";

import { api, ApiError, BASE_API } from "@/lib/api";
import type { Generacion } from "@/types";

/** Cada cuánto sondeamos una generación en curso (FALLBACK cuando no hay SSE). */
const INTERVALO_MS = 1200;

/** `true` mientras la generación sigue en segundo plano. */
export function estaEjecutando(estado: string | undefined): boolean {
  return estado === "ejecutando";
}

/**
 * Elige la instantánea MÁS AVANZADA de una misma generación.
 *
 * Mientras conviven dos transportes (SSE empujando + un fetch del sondeo que pudo
 * resolverse antes/después), la vista nunca debe RETROCEDER: gana la instantánea
 * terminal sobre la en-curso y, a igualdad de estado, la que tiene más texto
 * acumulado (salida + razonamiento solo crecen mientras corre).
 *
 * Si los ids difieren manda `a` (el estado local: una generación recién lanzada no
 * debe ser pisada por datos rezagados de la anterior).
 */
export function instantaneaMasAvanzada(
  a: Generacion | null,
  b: Generacion | null,
): Generacion | null {
  if (!a) return b;
  if (!b) return a;
  if (a.id !== b.id) return a;
  const aTerminal = !estaEjecutando(a.estado);
  const bTerminal = !estaEjecutando(b.estado);
  if (aTerminal !== bTerminal) return aTerminal ? a : b;
  const avance = (g: Generacion) =>
    (g.salida?.length ?? 0) + (g.razonamiento?.length ?? 0);
  return avance(b) > avance(a) ? b : a;
}

/** URL del stream SSE de una generación (misma forma de datos que el GET de sondeo). */
function urlStream(id: string): string {
  return `${BASE_API}/generaciones/${encodeURIComponent(id)}/stream`;
}

/**
 * Sigue un TRABAJO de IA en segundo plano (copy/RSS/hashtags/imagen).
 *
 * El POST que lo lanza devuelve una `Generacion` con `estado="ejecutando"`; se la
 * pasamos a `iniciar(...)` y este hook la sigue EN VIVO hasta el estado terminal
 * (`completado`/`error`), devolviendo la versión más reciente (con el texto en vivo
 * y las métricas parciales).
 *
 * SSE CON FALLBACK A SONDEO: mientras corre, el hook abre un `EventSource` contra
 * `GET /api/generaciones/{id}/stream` (el back lee el registro cada ~0.4 s y empuja
 * eventos `estado` solo cuando hay avance + un `terminal` al acabar). Una conexión
 * por trabajo en vez de ~0.8 req/s por cliente, y menos latencia percibida. Si SSE
 * no está disponible (proxy raro, red, entorno sin `EventSource`), DEGRADA al sondeo
 * de siempre (~1.2 s con React Query) sin que el consumidor note nada: la forma de
 * los datos es idéntica. La autenticación del stream viaja por la cookie de sesión
 * (same-origin), la misma vía que cubre descargas e `<img src>`.
 *
 * ROBUSTEZ ANTE NAVEGACIÓN: si se pasa `persistKey`, el id de la generación en curso
 * se guarda en `sessionStorage`; al montar de nuevo (cambiar de pestaña y volver) el
 * hook REANUDA el seguimiento de esa generación. El trabajo nunca se detiene (corre
 * en el servidor); esto solo recupera la vista en vivo. Al terminar, se limpia la clave.
 */
export function useGeneracion(persistKey?: string) {
  const [generacion, setGeneracion] = React.useState<Generacion | null>(null);
  // `true` mientras el EventSource está conectado y entregando (apaga el sondeo).
  const [sseConectado, setSseConectado] = React.useState(false);
  // SSE falló en esta sesión del hook (error de conexión/proxy/timeout del stream):
  // degradamos a sondeo y NO reintentamos en bucle (el sondeo ya converge solo).
  const sseRotoRef = React.useRef(false);

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

  const genId = generacion?.id;
  const generando = generacion !== null && estaEjecutando(generacion.estado);

  // --- SSE: una conexión por trabajo en curso; sustituye al sondeo mientras vive ---
  React.useEffect(() => {
    if (!genId || !generando) return;
    if (sseRotoRef.current) return; // ya degradamos a sondeo en esta sesión
    if (typeof EventSource === "undefined") return; // entorno sin SSE: sondeo
    const es = new EventSource(urlStream(genId));

    const aplicar = (ev: MessageEvent) => {
      try {
        const g = (JSON.parse(ev.data as string) as { generacion: Generacion | null })
          .generacion;
        // Solo la generación que seguimos, y sin retroceder (functional update:
        // compara contra el estado vigente, no contra el cierre del effect).
        if (g && g.id === genId) {
          setGeneracion((prev) => instantaneaMasAvanzada(g, prev) ?? g);
        }
      } catch {
        // Payload malformado: se ignora; el siguiente evento (o el sondeo) converge.
      }
    };
    const alTerminal = (ev: MessageEvent) => {
      aplicar(ev);
      // El servidor cierra tras `terminal`; cerramos nosotros primero para que el
      // cierre no dispare `onerror` (que marcaría SSE como roto sin estarlo).
      es.close();
      setSseConectado(false);
    };

    es.onopen = () => setSseConectado(true);
    es.addEventListener("estado", aplicar);
    es.addEventListener("terminal", alTerminal);
    es.onerror = () => {
      // No se pudo conectar, la red cayó o el stream agotó su timeout: degradamos
      // al sondeo de 1.2 s (React Query reanuda solo al apagarse `sseConectado`).
      sseRotoRef.current = true;
      es.close();
      setSseConectado(false);
    };
    return () => {
      es.close();
      setSseConectado(false);
    };
  }, [genId, generando]);

  // --- Sondeo (fallback y red de seguridad) ---
  // A-1: la query de sondeo NO usa initialData para evitar que React Query marque
  // la entrada como ya-fresca y salte el primer refetch cuando el POST responde
  // directamente con estado "completado" (completado-inmediato). El fallback al
  // estado local se aplica solo para el primer render (antes del primer fetch).
  // Con SSE conectado la query se APAGA (cero peticiones); si SSE cae, vuelve sola.
  const habilitado = generando && !sseConectado;

  const { data } = useQuery({
    queryKey: ["generacion", genId],
    queryFn: ({ signal }) => api.generacion(genId!, signal).then((r) => r.generacion),
    enabled: habilitado,
    // Sin initialData: la query parte de undefined y sondea desde la 1ª llamada.
    refetchInterval: (q) =>
      !sseConectado && estaEjecutando(q.state.data?.estado ?? generacion?.estado)
        ? INTERVALO_MS
        : false,
  });

  // La instantánea más avanzada entre el estado local (lo empuja el SSE / iniciar /
  // cancelar) y lo último que trajo el sondeo. Nunca retrocede; cubre también el
  // caso completado-inmediato antes del primer fetch y el estado inicial.
  const actual = instantaneaMasAvanzada(generacion, data ?? null);
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
  // local para CORTAR el seguimiento de inmediato (en vez de esperar al siguiente tick). El
  // trabajo corre en el servidor; esto solo lo detiene y refleja el resultado. Best-effort:
  // si la llamada falla (p. ej. ya terminó), el SSE/sondeo normal converge igual.
  const [cancelando, setCancelando] = React.useState(false);
  const cancelar = React.useCallback(async () => {
    if (!actualId) return;
    setCancelando(true);
    try {
      const r = await api.cancelarGeneracion(actualId);
      setGeneracion(r.generacion);
    } catch (e) {
      // El job ya pudo terminar antes de que llegara la cancelación: 404 (ya no existe)
      // o 409 (ya en estado terminal) se ignoran a propósito; el seguimiento refleja el
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
    /** Cancela el trabajo en curso (mata el subproceso en el servidor). */
    cancelar,
  };
}
