// Store del overlay Ralph (Zustand): el pool de Ralphs, el panel abierto/cerrado,
// el Ralph seleccionado y la conversación EN VIVO de cada uno.
//
// La conversación de cada Ralph se acumula a partir de los deltas que empuja su
// stream SSE (`abrirStreamRalph`), igual que el copy se construye token a token.
// Las conexiones `EventSource` viven FUERA del estado reactivo (un Map de módulo):
// son recursos imperativos, no datos que la UI deba renderizar.

import { create } from "zustand";

import { abrirStreamRalph, apiRalph } from "@/lib/api/ralph";
import { mensajeError } from "@/lib/api";
import type {
  CuerpoSpawnRalph,
  DeltaMensajeRalph,
  EstadoRalph,
  MensajeRalph,
  ModeloRalph,
  Ralph,
} from "@/types/ralph";

/** Conexiones SSE vivas por id de Ralph (imperativas, fuera del estado reactivo). */
const conexiones = new Map<string, EventSource>();

/** Id local para los mensajes de la conversación. */
function nuevoIdMensaje(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `m-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

interface EstadoRalphStore {
  /** El carril Ralph está disponible (worker-ralph arriba). */
  disponible: boolean;
  /** Pool actual de Ralphs. */
  ralphs: Ralph[];
  /** Id del Ralph cuyo chat está abierto, o `null`. */
  seleccionado: string | null;
  /** El panel de bolitas está desplegado. */
  panelAbierto: boolean;
  /** El lanzador (prompt + modelo) está abierto. */
  lanzadorAbierto: boolean;
  /** Conversación por Ralph (se llena con los deltas del SSE y los mensajes propios). */
  conversaciones: Record<string, MensajeRalph[]>;
  /** Un Ralph está emitiendo ahora mismo (indicador "escribiendo…"). */
  escribiendo: Record<string, boolean>;
  /** Mensaje en curso por Ralph (al que se anexan los deltas consecutivos). */
  msgEnCurso: Record<string, string | undefined>;
  /** La lista se está cargando por primera vez. */
  cargando: boolean;
  /** Hay un spawn en vuelo. */
  spawneando: boolean;

  // Acciones.
  cargar: () => Promise<void>;
  abrirPanel: () => void;
  cerrarPanel: () => void;
  alternarPanel: () => void;
  abrirLanzador: () => void;
  cerrarLanzador: () => void;
  seleccionar: (id: string | null) => void;
  spawn: (cuerpo: CuerpoSpawnRalph) => Promise<Ralph | null>;
  enviarMensaje: (id: string, texto: string) => Promise<void>;
  matar: (id: string) => Promise<void>;
  // Empujones del SSE.
  appendDelta: (id: string, delta: DeltaMensajeRalph) => void;
  aplicarEstado: (id: string, estado: EstadoRalph) => void;
}

export const useRalphStore = create<EstadoRalphStore>((set, get) => {
  /** Abre (si no existe) el stream SSE de un Ralph y cablea sus eventos al store. */
  function conectar(id: string): void {
    if (conexiones.has(id)) return;
    const es = abrirStreamRalph(id, {
      onMensaje: (delta) => get().appendDelta(id, delta),
      onEstado: (estado) => get().aplicarEstado(id, estado),
      onError: () => {
        // La conexión se cerró sola; soltamos la referencia para poder reabrir
        // al reseleccionar (el trabajo del Ralph sigue vivo en el servidor).
        conexiones.delete(id);
      },
    });
    if (es) conexiones.set(id, es);
  }

  /** Cierra el stream SSE de un Ralph si estaba abierto. */
  function desconectar(id: string): void {
    const es = conexiones.get(id);
    if (es) {
      es.close();
      conexiones.delete(id);
    }
  }

  return {
    disponible: false,
    ralphs: [],
    seleccionado: null,
    panelAbierto: false,
    lanzadorAbierto: false,
    conversaciones: {},
    escribiendo: {},
    msgEnCurso: {},
    cargando: false,
    spawneando: false,

    cargar: async () => {
      set({ cargando: true });
      try {
        const r = await apiRalph.ralphs();
        set({ disponible: r.disponible, ralphs: r.ralphs, cargando: false });
      } catch {
        // Carril no disponible o sin permiso: la burbuja queda inerte, sin ruido.
        set({ disponible: false, cargando: false });
      }
    },

    abrirPanel: () => set({ panelAbierto: true }),
    cerrarPanel: () => set({ panelAbierto: false, lanzadorAbierto: false, seleccionado: null }),
    alternarPanel: () => set((s) => ({ panelAbierto: !s.panelAbierto })),
    abrirLanzador: () => set({ lanzadorAbierto: true, seleccionado: null }),
    cerrarLanzador: () => set({ lanzadorAbierto: false }),

    seleccionar: (id) => {
      set({ seleccionado: id, lanzadorAbierto: false });
      if (id) conectar(id);
    },

    spawn: async (cuerpo) => {
      set({ spawneando: true });
      try {
        const { ralph } = await apiRalph.spawnRalph(cuerpo);
        set((s) => ({
          ralphs: [...s.ralphs.filter((r) => r.id !== ralph.id), ralph],
          seleccionado: ralph.id,
          lanzadorAbierto: false,
          panelAbierto: true,
          spawneando: false,
        }));
        conectar(ralph.id);
        return ralph;
      } catch (e) {
        set({ spawneando: false });
        throw new Error(mensajeError(e));
      }
    },

    enviarMensaje: async (id, texto) => {
      const limpio = texto.trim();
      if (!limpio) return;
      // Eco optimista del mensaje del humano; la respuesta del Ralph llega por SSE.
      set((s) => ({
        conversaciones: {
          ...s.conversaciones,
          [id]: [
            ...(s.conversaciones[id] ?? []),
            { id: nuevoIdMensaje(), autor: "tu", texto: limpio, creado: new Date().toISOString() },
          ],
        },
      }));
      conectar(id);
      await apiRalph.mensajeRalph(id, limpio);
    },

    matar: async (id) => {
      await apiRalph.killRalph(id);
      desconectar(id);
      set((s) => ({
        ralphs: s.ralphs.filter((r) => r.id !== id),
        seleccionado: s.seleccionado === id ? null : s.seleccionado,
        escribiendo: { ...s.escribiendo, [id]: false },
      }));
    },

    appendDelta: (id, delta) =>
      set((s) => {
        const autor = delta.autor ?? "ralph";
        const conv = s.conversaciones[id] ?? [];
        const enCurso = s.msgEnCurso[id];
        const ultimo = conv[conv.length - 1];
        let nuevaConv: MensajeRalph[];
        let nuevoEnCurso: string | undefined;
        // Anexa al mensaje en curso si es del mismo autor; si no, abre uno nuevo.
        if (enCurso && ultimo && ultimo.id === enCurso && ultimo.autor === autor) {
          nuevaConv = [...conv.slice(0, -1), { ...ultimo, texto: ultimo.texto + delta.delta }];
          nuevoEnCurso = ultimo.id;
        } else {
          const msg: MensajeRalph = {
            id: nuevoIdMensaje(),
            autor,
            texto: delta.delta,
            creado: new Date().toISOString(),
          };
          nuevaConv = [...conv, msg];
          nuevoEnCurso = msg.id;
        }
        return {
          conversaciones: { ...s.conversaciones, [id]: nuevaConv },
          msgEnCurso: { ...s.msgEnCurso, [id]: delta.fin ? undefined : nuevoEnCurso },
          escribiendo: { ...s.escribiendo, [id]: autor === "ralph" && !delta.fin },
        };
      }),

    aplicarEstado: (id, estado) =>
      set((s) => ({
        ralphs: s.ralphs.map((r) => (r.id === id ? { ...r, estado } : r)),
        // Un Ralph que ya no está activo deja de "escribir".
        escribiendo:
          estado === "activo" ? s.escribiendo : { ...s.escribiendo, [id]: false },
      })),
  };
});

/** Etiqueta legible de un modelo para el selector y las cabeceras. */
export const ETIQUETA_MODELO: Record<ModeloRalph, string> = {
  opus: "Opus",
  sonnet: "Sonnet",
  haiku: "Haiku",
};
