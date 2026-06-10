// Store del editor (Zustand): un Documento de capas + selección + historial undo/redo.
//
// Es un store POR DOCUMENTO (cada pestaña del workspace creará su propia instancia con
// `crearStoreEditor`), de modo que editar la plantilla de UnoTV no toca la de Claro Sports.
// La edición es local e instantánea; el servidor solo entra para el export de alta fidelidad.

import { createStore } from "zustand/vanilla";

import type { Capa, CapaImagen, CapaMarco, Documento, Forma } from "./documento";
import { altoVisual, nuevoId } from "./documento";

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
  aplicarPosiciones: (pos: { id: string; x: number; y: number }[], registrar?: boolean) => void;
  alinearMulti: (modo: "izq" | "centroH" | "der" | "arriba" | "centroV" | "abajo") => void;
  distribuir: (eje: "h" | "v") => void;
  // «Ordenar» (tidy up estilo Canva, ⌥⇧T): con 3+ capas seleccionadas las reparte con ESPACIADO
  // UNIFORME a lo largo del eje dominante de su disposición actual (el de mayor dispersión de
  // centros), alineando los centros en el eje perpendicular. Un paso de deshacer. Con <3, no-op.
  ordenarMulti: () => void;
  agregar: (capa: Capa) => void;
  // Inserta VARIAS capas (un bloque) en un solo paso de historial, encima de todo, con ids frescos.
  insertarBloque: (capas: Capa[]) => void;
  actualizar: (id: string, cambios: Partial<Capa>, registrar?: boolean) => void;
  // Marca la capa imagen `id` como HUECO DE FOTO (`es_foto`+bloqueada), SIN tocar las demás: una
  // plantilla puede tener varios huecos (collage de 2..12). Mínimo uno (lo exige el guardado).
  marcarHuecoFoto: (id: string) => void;
  // Convierte un MARCO en una capa IMAGEN (hueco para foto), conservando geometría/forma. Y al
  // revés: una IMAGEN en MARCO (forma rellena). El usuario alterna entre forma vacía y foto.
  convertirEnImagen: (id: string) => void;
  convertirEnMarco: (id: string) => void;
  quitar: (id: string) => void;
  duplicar: (id: string) => void;
  reordenar: (id: string, delta: number) => void;
  // Reasigna `z` para que el orden de pila coincida con `ids` (primero = más arriba). Para el
  // arrastre-reordenar del panel de capas.
  ordenarZ: (idsArribaPrimero: string[]) => void;
  traerAlFrente: (id: string) => void;
  enviarAlFondo: (id: string) => void;
  // Agrupa la selección múltiple en una capa `grupo` (hijos en coordenadas absolutas) / la deshace.
  agrupar: () => void;
  desagrupar: (id: string) => void;
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
          const frescas = capas.map((c) => ({
            ...clonar(c),
            id: nuevoId(c.tipo),
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

      marcarHuecoFoto: (id) =>
        aplicar((doc) =>
          conCapas(
            doc,
            doc.capas.map((c) =>
              // Marca ESTA imagen como hueco de foto (+ bloqueada). NO desmarca las demás: una
              // plantilla puede tener VARIOS huecos (collage de 2..12 fotos). Para quitar uno se
              // usa "Quitar" en su propio panel.
              c.id === id && c.tipo === "imagen"
                ? ({ ...c, es_foto: true, bloqueada: true } as Capa)
                : c,
            ),
          ),
        ),

      convertirEnImagen: (id) =>
        aplicar((doc) =>
          conCapas(
            doc,
            doc.capas.map((c) => {
              if (c.id !== id || c.tipo !== "marco") return c;
              const m = c as CapaMarco;
              // "linea" no tiene equivalente como recorte de imagen: cae a "rect".
              const forma: Forma = m.forma === "linea" ? "rect" : (m.forma as Forma);
              const img: CapaImagen = {
                id: m.id,
                tipo: "imagen",
                nombre: m.nombre,
                x: m.x, y: m.y, w: m.w, h: m.h,
                rotacion: m.rotacion, opacidad: m.opacidad, mezcla: m.mezcla, z: m.z,
                visible: m.visible, bloqueada: m.bloqueada,
                objeto: "", // hueco: el usuario asigna la foto
                ajuste: "cover",
                foco: [0.5, 0.5],
                zoom: 1,
                forma,
                radio: m.radio ?? 0,
                filtros: null,
                sombra: m.sombra ?? null,
              };
              return img;
            }),
          ),
        ),

      convertirEnMarco: (id) =>
        aplicar((doc) =>
          conCapas(
            doc,
            doc.capas.map((c) => {
              if (c.id !== id || c.tipo !== "imagen") return c;
              const im = c as CapaImagen;
              const marco: CapaMarco = {
                id: im.id,
                tipo: "marco",
                nombre: im.nombre,
                x: im.x, y: im.y, w: im.w, h: im.h,
                rotacion: im.rotacion, opacidad: im.opacidad, mezcla: im.mezcla, z: im.z,
                visible: im.visible, bloqueada: im.bloqueada,
                forma: (im.forma ?? "rect") as CapaMarco["forma"],
                relleno: "#888888", // relleno gris por defecto al vaciar la foto
                borde: null,
                radio: im.radio ?? 0,
                sombra: im.sombra ?? null,
              };
              return marco;
            }),
          ),
        ),

      quitar: (id) => {
        // No se borra una capa bloqueada (p. ej. el hueco de foto obligatorio).
        if (get().documento.capas.find((c) => c.id === id)?.bloqueada) return;
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
          id: nuevoId(orig.tipo),
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

      ordenarZ: (idsArribaPrimero) =>
        aplicar((doc) => {
          const n = idsArribaPrimero.length;
          const zPorId = new Map(idsArribaPrimero.map((id, i) => [id, n - i]));
          return conCapas(
            doc,
            doc.capas.map((c) => (zPorId.has(c.id) ? ({ ...c, z: zPorId.get(c.id)! } as Capa) : c)),
          );
        }),

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
        // Las capas bloqueadas (hueco de foto) no se borran ni en lote.
        const bloqueadas = new Set(
          get().documento.capas.filter((c) => c.bloqueada).map((c) => c.id),
        );
        const ids = new Set(get().seleccionMulti.filter((id) => !bloqueadas.has(id)));
        if (ids.size === 0) return;
        aplicar((doc) => conCapas(doc, doc.capas.filter((c) => !ids.has(c.id))));
        set({ seleccion: null, seleccionMulti: [] });
      },

      duplicarMulti: () => {
        const sel = get().seleccionMulti;
        if (sel.length === 0) return;
        const capas = get().documento.capas.filter((c) => sel.includes(c.id));
        let z = get().documento.capas.reduce((m, c) => Math.max(m, c.z), 0);
        const copias = capas.map((c) => ({
          ...clonar(c),
          id: nuevoId(c.tipo),
          x: c.x + 24,
          y: c.y + 24,
          z: ++z,
        })) as Capa[];
        aplicar((doc) => conCapas(doc, [...doc.capas, ...copias]));
        set({ seleccionMulti: copias.map((c) => c.id), seleccion: copias[copias.length - 1]?.id ?? null });
      },

      aplicarPosiciones: (pos, registrar = true) => {
        const mapa = new Map(pos.map((p) => [p.id, p]));
        aplicar((doc) =>
          conCapas(
            doc,
            doc.capas.map((c) => {
              const p = mapa.get(c.id);
              return p ? ({ ...c, x: p.x, y: p.y } as Capa) : c;
            }),
          ),
          registrar,
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

      ordenarMulti: () => {
        const sel = get().seleccionMulti;
        if (sel.length < 3) return;
        aplicar((doc) => {
          const elegidas = doc.capas.filter((c) => sel.includes(c.id));
          if (elegidas.length < 3) return doc;
          const cx = (c: Capa) => c.x + c.w / 2;
          const cy = (c: Capa) => c.y + altoVisual(c) / 2;
          // Eje DOMINANTE de la disposición actual: el de mayor dispersión de centros (empate => h).
          const xs = elegidas.map(cx);
          const ys = elegidas.map(cy);
          const eje: "h" | "v" =
            Math.max(...xs) - Math.min(...xs) >= Math.max(...ys) - Math.min(...ys) ? "h" : "v";
          const orden = [...elegidas].sort((a, b) => (eje === "h" ? cx(a) - cx(b) : cy(a) - cy(b)));
          // Reparto con HUECO uniforme dentro de la extensión actual (del borde inicial del primero
          // al borde final del último); puede ser negativo si se solapan — sigue siendo determinista.
          const tam = (c: Capa) => (eje === "h" ? c.w : altoVisual(c));
          const ini = Math.min(...orden.map((c) => (eje === "h" ? c.x : c.y)));
          const fin = Math.max(...orden.map((c) => (eje === "h" ? c.x + c.w : c.y + altoVisual(c))));
          const hueco = (fin - ini - orden.reduce((s, c) => s + tam(c), 0)) / (orden.length - 1);
          // Eje perpendicular: alinea los CENTROS al centro medio del conjunto.
          const perp = orden.reduce((s, c) => s + (eje === "h" ? cy(c) : cx(c)), 0) / orden.length;
          let cursor = ini;
          const pos = new Map<string, { x: number; y: number }>();
          for (const c of orden) {
            pos.set(
              c.id,
              eje === "h"
                ? { x: Math.round(cursor), y: Math.round(perp - altoVisual(c) / 2) }
                : { x: Math.round(perp - c.w / 2), y: Math.round(cursor) },
            );
            cursor += tam(c) + hueco;
          }
          return conCapas(
            doc,
            doc.capas.map((c) => {
              const p = pos.get(c.id);
              return p ? ({ ...c, x: p.x, y: p.y } as Capa) : c;
            }),
          );
        });
      },

      agrupar: () => {
        const sel = get().seleccionMulti;
        if (sel.length < 2) return;
        const elegidas = get().documento.capas.filter((c) => sel.includes(c.id)).sort((a, b) => a.z - b.z);
        if (elegidas.length < 2) return;
        // BBox que envuelve a las hijas considerando rotación (coordenadas absolutas, que se conservan dentro del grupo).
        // Calcula las 4 esquinas de cada capa rotada y toma min/max.
        const todos = elegidas.flatMap((c) => {
          const x = c.x, y = c.y, w = c.w, h = c.h, rot = c.rotacion || 0;
          const rad = (rot * Math.PI) / 180;
          const cos = Math.cos(rad);
          const sin = Math.sin(rad);
          // 4 esquinas: [x, y], [x+w, y], [x+w, y+h], [x, y+h] rotadas alrededor de (x, y)
          const esquinas = [
            [0, 0],
            [w, 0],
            [w, h],
            [0, h],
          ];
          return esquinas.map(([dx, dy]) => [
            x + dx * cos - dy * sin,
            y + dx * sin + dy * cos,
          ]);
        });
        const minX = Math.min(...todos.map(([px]) => px));
        const minY = Math.min(...todos.map(([_, py]) => py));
        const maxX = Math.max(...todos.map(([px]) => px));
        const maxY = Math.max(...todos.map(([_, py]) => py));
        const z = Math.max(...elegidas.map((c) => c.z));
        const grupo = {
          id: nuevoId("grupo"),
          tipo: "grupo" as const,
          x: minX, y: minY, w: maxX - minX, h: maxY - minY,
          rotacion: 0, opacidad: 1, z, visible: true, bloqueada: false,
          capas: elegidas.map((c) => clonar(c)),
        };
        const ids = new Set(sel);
        aplicar((doc) => conCapas(doc, [...doc.capas.filter((c) => !ids.has(c.id)), grupo as Capa]));
        set({ seleccion: grupo.id, seleccionMulti: [grupo.id] });
      },

      desagrupar: (id) => {
        const grupo = get().documento.capas.find((c) => c.id === id);
        if (!grupo || grupo.tipo !== "grupo") return;
        const hijas = grupo.capas.map((c) => clonar(c)) as Capa[];
        aplicar((doc) => conCapas(doc, [...doc.capas.filter((c) => c.id !== id), ...hijas]));
        set({ seleccion: hijas[hijas.length - 1]?.id ?? null, seleccionMulti: hijas.map((c) => c.id) });
      },

      setFondo: (fondo) => aplicar((doc) => ({ ...doc, fondo })),

      setFormato: (formato) => aplicar((doc) => ({ ...doc, formato })),

      comenzarGesto: () =>
        set((s) => ({ pasado: [...s.pasado, s.documento].slice(-LIMITE_HISTORIAL), futuro: [] })),

      deshacer: () =>
        set((s) => {
          if (s.pasado.length === 0) return {};
          const previo = s.pasado[s.pasado.length - 1];
          const idsPresentes = new Set(previo.capas.map((c) => c.id));
          // Sanea la selección: filtra seleccionMulti a ids que existan en el documento restaurado,
          // y pone seleccion a null si ya no existe.
          const seleccionMulti = s.seleccionMulti.filter((id) => idsPresentes.has(id));
          const seleccion = s.seleccion && idsPresentes.has(s.seleccion) ? s.seleccion : null;
          return {
            documento: previo,
            pasado: s.pasado.slice(0, -1),
            futuro: [s.documento, ...s.futuro].slice(0, LIMITE_HISTORIAL),
            seleccionMulti,
            seleccion,
          };
        }),

      rehacer: () =>
        set((s) => {
          if (s.futuro.length === 0) return {};
          const siguiente = s.futuro[0];
          const idsPresentes = new Set(siguiente.capas.map((c) => c.id));
          // Sanea la selección: filtra seleccionMulti a ids que existan en el documento restaurado,
          // y pone seleccion a null si ya no existe.
          const seleccionMulti = s.seleccionMulti.filter((id) => idsPresentes.has(id));
          const seleccion = s.seleccion && idsPresentes.has(s.seleccion) ? s.seleccion : null;
          return {
            documento: siguiente,
            pasado: [...s.pasado, s.documento].slice(-LIMITE_HISTORIAL),
            futuro: s.futuro.slice(1),
            seleccionMulti,
            seleccion,
          };
        }),

      puedeDeshacer: () => get().pasado.length > 0,
      puedeRehacer: () => get().futuro.length > 0,
    };
  });
}
