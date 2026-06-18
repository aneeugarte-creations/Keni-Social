// Fragmento del cliente API: dominio «ralph» (overlay de agentes de desarrollo).
// El objeto compuesto vive en ./index.ts; aquí el fragmento + el helper de SSE.
import { BASE_API, peticion } from "./_core";
import type {
  CuerpoSpawnRalph,
  DeltaMensajeRalph,
  EstadoRalph,
  RespuestaOkRalph,
  RespuestaRalph,
  RespuestaRalphs,
} from "@/types/ralph";

export const apiRalph = {
  // Lista el pool de Ralphs + si el carril está disponible (admin-gated en el back).
  ralphs: (signal?: AbortSignal) => peticion<RespuestaRalphs>("/ralph", { signal }),
  // Lanza un Ralph nuevo con un prompt inicial y modelo (def "opus" en el back).
  spawnRalph: (cuerpo: CuerpoSpawnRalph) =>
    peticion<RespuestaRalph>("/ralph/spawn", { metodo: "POST", json: cuerpo }),
  // Envía un mensaje del humano a un Ralph en curso (la respuesta llega por el stream).
  mensajeRalph: (id: string, texto: string) =>
    peticion<RespuestaOkRalph>(`/ralph/${encodeURIComponent(id)}/mensaje`, {
      metodo: "POST",
      json: { texto },
    }),
  // Mata la sesión de un Ralph (cierra su subproceso claude en el server).
  killRalph: (id: string) =>
    peticion<RespuestaOkRalph>(`/ralph/${encodeURIComponent(id)}/kill`, { metodo: "POST" }),
};

/** Manejadores de los eventos del stream SSE de un Ralph. */
export interface ManejadoresStreamRalph {
  /** Delta de conversación (evento `mensaje`). */
  onMensaje?: (delta: DeltaMensajeRalph) => void;
  /** Cambio de estado del Ralph (evento `estado`). */
  onEstado?: (estado: EstadoRalph) => void;
  /** La conexión se abrió. */
  onAbierto?: () => void;
  /** La conexión falló (red/proxy/timeout). Tras esto el caller decide reabrir. */
  onError?: () => void;
}

/** URL del stream SSE de un Ralph (auth por cookie de sesión, same-origin). */
function urlStreamRalph(id: string): string {
  return `${BASE_API}/ralph/${encodeURIComponent(id)}/stream`;
}

/**
 * Abre el stream SSE de un Ralph y cablea sus eventos `mensaje`/`estado`, con el
 * mismo patrón de `EventSource` que `hooks/use-generacion.ts`: la conversación se
 * empuja token a token y los payloads malformados se ignoran (el siguiente evento
 * converge). Devuelve el `EventSource` para que el caller lo cierre (`.close()`),
 * o `null` si el entorno no soporta SSE (el caller degrada como crea conveniente).
 */
export function abrirStreamRalph(
  id: string,
  manejadores: ManejadoresStreamRalph,
): EventSource | null {
  if (typeof EventSource === "undefined") return null;
  const es = new EventSource(urlStreamRalph(id));

  es.onopen = () => manejadores.onAbierto?.();
  es.addEventListener("mensaje", (ev: MessageEvent) => {
    try {
      manejadores.onMensaje?.(JSON.parse(ev.data as string) as DeltaMensajeRalph);
    } catch {
      // Payload malformado: se ignora; el siguiente evento converge.
    }
  });
  es.addEventListener("estado", (ev: MessageEvent) => {
    try {
      const { estado } = JSON.parse(ev.data as string) as { estado: EstadoRalph };
      if (estado) manejadores.onEstado?.(estado);
    } catch {
      // Payload malformado: se ignora.
    }
  });
  es.onerror = () => {
    es.close();
    manejadores.onError?.();
  };

  return es;
}
