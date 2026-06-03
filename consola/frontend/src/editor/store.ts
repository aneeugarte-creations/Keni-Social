// Store del editor (Zustand): un Documento de capas + selección + historial undo/redo.
//
// Es un store POR DOCUMENTO (cada pestaña del workspace creará su propia instancia con
// `crearStoreEditor`), de modo que editar la plantilla de UnoTV no toca la de Claro Sports.
// La edición es local e instantánea; el servidor solo entra para el export de alta fidelidad.

import { createStore } from "zustand/vanilla";

import type { Capa, Documento } from "./documento";

const LIMITE_HISTORIAL = 50;

export interface EstadoEditor {
  documento: Documento;
  seleccion: string | null;
  pasado: Documento[];
  futuro: Documento[];

  // Lectura derivada.
  capaSeleccionada: () => Capa | null;

  // Mutaciones (registran historial salvo que se diga lo contrario).
  cargar: (doc: Documento) => void;
  seleccionar: (id: string | null) => void;
  agregar: (capa: Capa) => void;
  // Inserta VARIAS capas (un bloque) en un solo paso de historial, encima de todo, con ids frescos.
  insertarBloque: (capas: Capa[]) => void;
  actualizar: (id: string, cambios: Partial<Capa>, registrar?: boolean) => void;
  quitar: (id: string) => void;
  duplicar: (id: string) => void;
  reordenar: (id: string, delta: number) => void;
  setFondo: (fondo: Documento["fondo"]) => void;

  // Historial. `comenzarGesto` toma una instantánea ANTES de un arrastre/transform para que
  // todo el gesto cuente como UN paso de deshacer (las actualizaciones intermedias van sin
  // registrar). `deshacer`/`rehacer` mueven entre pilas.
  comenzarGesto: () => void;
  deshacer: () => void;
  rehacer: () => void;
  puedeDeshacer: () => boolean;
  puedeRehacer: () => boolean;
}

function clonar<T>(v: T): T {
  return structuredClone(v);
}

export type StoreEditor = ReturnType<typeof crearStoreEditor>;

export function crearStoreEditor(inicial: Documento) {
  return createStore<EstadoEditor>((set, get) => {
    // Aplica una mutación al documento; si `registrar`, empuja el estado previo al historial.
    const aplicar = (
      mut: (doc: Documento) => Documento,
      registrar = true,
    ): void => {
      set((s) => {
        const previo = s.documento;
        const siguiente = mut(clonar(previo));
        if (!registrar) return { documento: siguiente };
        const pasado = [...s.pasado, previo].slice(-LIMITE_HISTORIAL);
        return { documento: siguiente, pasado, futuro: [] };
      });
    };

    const conCapas = (doc: Documento, capas: Capa[]): Documento => ({ ...doc, capas });

    return {
      documento: inicial,
      seleccion: null,
      pasado: [],
      futuro: [],

      capaSeleccionada: () => {
        const { documento, seleccion } = get();
        return documento.capas.find((c) => c.id === seleccion) ?? null;
      },

      cargar: (doc) => set({ documento: doc, seleccion: null, pasado: [], futuro: [] }),

      seleccionar: (id) => set({ seleccion: id }),

      agregar: (capa) =>
        aplicar((doc) => conCapas(doc, [...doc.capas, capa])),

      insertarBloque: (capas) =>
        aplicar((doc) => {
          let z = doc.capas.reduce((m, c) => Math.max(m, c.z), 0);
          const frescas = capas.map((c, i) => ({
            ...clonar(c),
            id: `${c.tipo}-${Date.now().toString(36)}-${i}`,
            z: ++z,
          })) as Capa[];
          return conCapas(doc, [...doc.capas, ...frescas]);
        }),

      actualizar: (id, cambios, registrar = true) =>
        aplicar(
          (doc) =>
            conCapas(
              doc,
              doc.capas.map((c) => (c.id === id ? ({ ...c, ...cambios } as Capa) : c)),
            ),
          registrar,
        ),

      quitar: (id) => {
        aplicar((doc) => conCapas(doc, doc.capas.filter((c) => c.id !== id)));
        if (get().seleccion === id) set({ seleccion: null });
      },

      duplicar: (id) => {
        const orig = get().documento.capas.find((c) => c.id === id);
        if (!orig) return;
        const copia = {
          ...clonar(orig),
          id: `${orig.tipo}-${Date.now().toString(36)}-${Math.floor(performance.now())}`,
          x: orig.x + 24,
          y: orig.y + 24,
          z: Math.max(0, ...get().documento.capas.map((c) => c.z)) + 1,
        } as Capa;
        aplicar((doc) => conCapas(doc, [...doc.capas, copia]));
        set({ seleccion: copia.id });
      },

      reordenar: (id, delta) =>
        aplicar((doc) =>
          conCapas(
            doc,
            doc.capas.map((c) => (c.id === id ? ({ ...c, z: Math.max(0, c.z + delta) } as Capa) : c)),
          ),
        ),

      setFondo: (fondo) => aplicar((doc) => ({ ...doc, fondo })),

      comenzarGesto: () =>
        set((s) => ({ pasado: [...s.pasado, s.documento].slice(-LIMITE_HISTORIAL), futuro: [] })),

      deshacer: () =>
        set((s) => {
          if (s.pasado.length === 0) return {};
          const previo = s.pasado[s.pasado.length - 1];
          return {
            documento: previo,
            pasado: s.pasado.slice(0, -1),
            futuro: [s.documento, ...s.futuro].slice(0, LIMITE_HISTORIAL),
          };
        }),

      rehacer: () =>
        set((s) => {
          if (s.futuro.length === 0) return {};
          const siguiente = s.futuro[0];
          return {
            documento: siguiente,
            pasado: [...s.pasado, s.documento].slice(-LIMITE_HISTORIAL),
            futuro: s.futuro.slice(1),
          };
        }),

      puedeDeshacer: () => get().pasado.length > 0,
      puedeRehacer: () => get().futuro.length > 0,
    };
  });
}
