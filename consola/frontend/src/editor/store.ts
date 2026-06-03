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
  // `seleccion` = capa PRIMARIA (la que edita el inspector). `seleccionMulti` = TODAS las
  // seleccionadas (siempre incluye la primaria); las operaciones múltiples usan esta.
  seleccion: string | null;
  seleccionMulti: string[];
  pasado: Documento[];
  futuro: Documento[];

  // Lectura derivada.
  capaSeleccionada: () => Capa | null;

  // Mutaciones (registran historial salvo que se diga lo contrario).
  cargar: (doc: Documento) => void;
  seleccionar: (id: string | null) => void;
  // Alterna una capa en la selección múltiple (shift/cmd-clic).
  alternar: (id: string) => void;
  seleccionarMuchas: (ids: string[]) => void;
  // Operaciones sobre la selección múltiple (un solo paso de historial).
  quitarMulti: () => void;
  duplicarMulti: () => void;
  aplicarPosiciones: (pos: { id: string; x: number; y: number }[]) => void;
  alinearMulti: (modo: "izq" | "centroH" | "der" | "arriba" | "centroV" | "abajo") => void;
  distribuir: (eje: "h" | "v") => void;
  agregar: (capa: Capa) => void;
  // Inserta VARIAS capas (un bloque) en un solo paso de historial, encima de todo, con ids frescos.
  insertarBloque: (capas: Capa[]) => void;
  actualizar: (id: string, cambios: Partial<Capa>, registrar?: boolean) => void;
  quitar: (id: string) => void;
  duplicar: (id: string) => void;
  reordenar: (id: string, delta: number) => void;
  traerAlFrente: (id: string) => void;
  enviarAlFondo: (id: string) => void;
  // Alinea la capa respecto al lienzo (o, si se pasa, una caja de referencia).
  alinear: (id: string, modo: "izq" | "centroH" | "der" | "arriba" | "centroV" | "abajo") => void;
  setFondo: (fondo: Documento["fondo"]) => void;
  setFormato: (formato: Documento["formato"]) => void;

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
      seleccionMulti: [],
      pasado: [],
      futuro: [],

      capaSeleccionada: () => {
        const { documento, seleccion } = get();
        return documento.capas.find((c) => c.id === seleccion) ?? null;
      },

      cargar: (doc) => set({ documento: doc, seleccion: null, seleccionMulti: [], pasado: [], futuro: [] }),

      seleccionar: (id) => set({ seleccion: id, seleccionMulti: id ? [id] : [] }),

      alternar: (id) =>
        set((s) => {
          if (s.seleccionMulti.includes(id)) {
            const resto = s.seleccionMulti.filter((x) => x !== id);
            return { seleccionMulti: resto, seleccion: s.seleccion === id ? (resto[resto.length - 1] ?? null) : s.seleccion };
          }
          return { seleccionMulti: [...s.seleccionMulti, id], seleccion: id };
        }),

      seleccionarMuchas: (ids) => set({ seleccionMulti: ids, seleccion: ids[ids.length - 1] ?? null }),

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
        set((s) => ({
          seleccion: s.seleccion === id ? null : s.seleccion,
          seleccionMulti: s.seleccionMulti.filter((x) => x !== id),
        }));
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

      traerAlFrente: (id) =>
        aplicar((doc) => {
          const max = doc.capas.reduce((m, c) => Math.max(m, c.z), 0);
          return conCapas(doc, doc.capas.map((c) => (c.id === id ? ({ ...c, z: max + 1 } as Capa) : c)));
        }),

      enviarAlFondo: (id) =>
        aplicar((doc) => {
          const min = doc.capas.reduce((m, c) => Math.min(m, c.z), 0);
          return conCapas(doc, doc.capas.map((c) => (c.id === id ? ({ ...c, z: min - 1 } as Capa) : c)));
        }),

      alinear: (id, modo) =>
        aplicar((doc) => {
          const f = doc.formato;
          return conCapas(
            doc,
            doc.capas.map((c) => {
              if (c.id !== id) return c;
              if (modo === "izq") return { ...c, x: 0 } as Capa;
              if (modo === "centroH") return { ...c, x: Math.round((f.w - c.w) / 2) } as Capa;
              if (modo === "der") return { ...c, x: f.w - c.w } as Capa;
              if (modo === "arriba") return { ...c, y: 0 } as Capa;
              if (modo === "centroV") return { ...c, y: Math.round((f.h - c.h) / 2) } as Capa;
              return { ...c, y: f.h - c.h } as Capa; // abajo
            }),
          );
        }),

      quitarMulti: () => {
        const ids = new Set(get().seleccionMulti);
        if (ids.size === 0) return;
        aplicar((doc) => conCapas(doc, doc.capas.filter((c) => !ids.has(c.id))));
        set({ seleccion: null, seleccionMulti: [] });
      },

      duplicarMulti: () => {
        const sel = get().seleccionMulti;
        if (sel.length === 0) return;
        const capas = get().documento.capas.filter((c) => sel.includes(c.id));
        let z = get().documento.capas.reduce((m, c) => Math.max(m, c.z), 0);
        const copias = capas.map((c, i) => ({
          ...clonar(c),
          id: `${c.tipo}-${Date.now().toString(36)}-${i}`,
          x: c.x + 24,
          y: c.y + 24,
          z: ++z,
        })) as Capa[];
        aplicar((doc) => conCapas(doc, [...doc.capas, ...copias]));
        set({ seleccionMulti: copias.map((c) => c.id), seleccion: copias[copias.length - 1]?.id ?? null });
      },

      aplicarPosiciones: (pos) => {
        const mapa = new Map(pos.map((p) => [p.id, p]));
        aplicar((doc) =>
          conCapas(
            doc,
            doc.capas.map((c) => {
              const p = mapa.get(c.id);
              return p ? ({ ...c, x: p.x, y: p.y } as Capa) : c;
            }),
          ),
        );
      },

      alinearMulti: (modo) => {
        const ids = new Set(get().seleccionMulti);
        if (ids.size === 0) return;
        aplicar((doc) => {
          const f = doc.formato;
          return conCapas(
            doc,
            doc.capas.map((c) => {
              if (!ids.has(c.id)) return c;
              if (modo === "izq") return { ...c, x: 0 } as Capa;
              if (modo === "centroH") return { ...c, x: Math.round((f.w - c.w) / 2) } as Capa;
              if (modo === "der") return { ...c, x: f.w - c.w } as Capa;
              if (modo === "arriba") return { ...c, y: 0 } as Capa;
              if (modo === "centroV") return { ...c, y: Math.round((f.h - c.h) / 2) } as Capa;
              return { ...c, y: f.h - c.h } as Capa;
            }),
          );
        });
      },

      distribuir: (eje) => {
        const sel = get().seleccionMulti;
        if (sel.length < 3) return;
        aplicar((doc) => {
          const elegidas = doc.capas.filter((c) => sel.includes(c.id));
          const orden = [...elegidas].sort((a, b) => (eje === "h" ? a.x - b.x : a.y - b.y));
          const primero = orden[0];
          const ultimo = orden[orden.length - 1];
          const ini = eje === "h" ? primero.x : primero.y;
          const fin = eje === "h" ? ultimo.x : ultimo.y;
          const paso = (fin - ini) / (orden.length - 1);
          const nuevaPos = new Map<string, number>();
          orden.forEach((c, i) => nuevaPos.set(c.id, Math.round(ini + paso * i)));
          return conCapas(
            doc,
            doc.capas.map((c) =>
              nuevaPos.has(c.id) ? ({ ...c, [eje === "h" ? "x" : "y"]: nuevaPos.get(c.id) } as Capa) : c,
            ),
          );
        });
      },

      setFondo: (fondo) => aplicar((doc) => ({ ...doc, fondo })),

      setFormato: (formato) => aplicar((doc) => ({ ...doc, formato })),

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
