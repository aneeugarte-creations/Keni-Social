// Contrato de los atajos del MODO RECORTE estilo Canva: Enter CONFIRMA (Hecho) y Escape CANCELA
// (restaura), respetando la CASCADA de Escape existente (recorte → reencuadre → deseleccionar).
// Y de los atajos de CREACIÓN (T/R/C/L) + «Ordenar» (tidy up, ⌥⇧T).

import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CapaMarco, CapaTexto } from "../documento";
import { documentoVacio, nuevaCapaMarco, nuevaCapaTexto } from "../documento";
import { crearStoreEditor } from "../store";
import { type LienzoApi, type ZoomApi, useAtajosTeclado } from "./useAtajosTeclado";

function montar(opts: { recorteId?: string | null; reencuadreId?: string | null; conSeleccion?: boolean } = {}) {
  const store = crearStoreEditor(documentoVacio({ w: 1080, h: 1080, safe_top: 0, safe_bottom: 0 }, "test"));
  const texto = nuevaCapaTexto({ id: "texto-1", nombre: "Texto", z: 1 });
  store.getState().agregar(texto);
  if (opts.conSeleccion) store.getState().seleccionar(texto.id);
  const zoom = {
    current: { acercar: vi.fn(), alejar: vi.fn(), ajustar: vi.fn(), real: vi.fn() } as ZoomApi,
  };
  // Viewport simulado: centrado en (300, 200) del documento, para comprobar que los elementos
  // nuevos nacen en el centro del VIEWPORT y no en el del lienzo ni en 0,0.
  const lienzo = {
    current: { centroViewport: vi.fn(() => ({ x: 300, y: 200 })), editarTexto: vi.fn() } as LienzoApi,
  };
  const onSalirReencuadre = vi.fn();
  const onCancelarRecorte = vi.fn();
  const onConfirmarRecorte = vi.fn();
  const hook = renderHook(() =>
    useAtajosTeclado({
      store,
      zoom,
      lienzo,
      reencuadreId: opts.reencuadreId ?? null,
      onSalirReencuadre,
      recorteId: opts.recorteId ?? null,
      onCancelarRecorte,
      onConfirmarRecorte,
    }),
  );
  return { store, hook, zoom, lienzo, onSalirReencuadre, onCancelarRecorte, onConfirmarRecorte };
}

// Como en un navegador real, el keydown se origina en el elemento enfocado (body) y BURBUJEA
// hasta window, donde escucha el hook.
const tecla = (key: string) => document.body.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
const teclaCon = (init: KeyboardEventInit) =>
  document.body.dispatchEvent(new KeyboardEvent("keydown", { bubbles: true, ...init }));

describe("useAtajosTeclado — zoom (ajustar a pantalla)", () => {
  it("⌘0 ajusta a pantalla", () => {
    const { zoom, hook } = montar();
    teclaCon({ key: "0", code: "Digit0", metaKey: true });
    expect(zoom.current.ajustar).toHaveBeenCalledTimes(1);
    hook.unmount();
  });

  it("⌥⌘0 (alias estándar de Canva) también ajusta, aunque Alt cambie e.key", () => {
    const { zoom, hook } = montar();
    // En macOS, ⌥0 puede reportar otra tecla en e.key; el hook se apoya en e.code.
    teclaCon({ key: "º", code: "Digit0", metaKey: true, altKey: true });
    expect(zoom.current.ajustar).toHaveBeenCalledTimes(1);
    expect(zoom.current.real).not.toHaveBeenCalled();
    hook.unmount();
  });

  it("⇧0 sigue siendo 100 % (no ajusta)", () => {
    const { zoom, hook } = montar();
    teclaCon({ key: ")", code: "Digit0", shiftKey: true });
    expect(zoom.current.real).toHaveBeenCalledTimes(1);
    expect(zoom.current.ajustar).not.toHaveBeenCalled();
    hook.unmount();
  });
});

describe("useAtajosTeclado — modo recorte (Canva)", () => {
  it("Enter con el recorte activo CONFIRMA (Hecho)", () => {
    const { onConfirmarRecorte, onCancelarRecorte, hook } = montar({ recorteId: "img-1" });
    tecla("Enter");
    expect(onConfirmarRecorte).toHaveBeenCalledTimes(1);
    expect(onCancelarRecorte).not.toHaveBeenCalled();
    hook.unmount();
  });

  it("Enter sin recorte activo no dispara nada", () => {
    const { onConfirmarRecorte, hook } = montar({ conSeleccion: true });
    tecla("Enter");
    expect(onConfirmarRecorte).not.toHaveBeenCalled();
    hook.unmount();
  });

  it("Escape con el recorte activo CANCELA y no toca la selección (cascada)", () => {
    const { store, onCancelarRecorte, hook } = montar({ recorteId: "img-1", conSeleccion: true });
    tecla("Escape");
    expect(onCancelarRecorte).toHaveBeenCalledTimes(1);
    expect(store.getState().seleccion).toBe("texto-1");
    hook.unmount();
  });

  it("la cascada de Escape sigue intacta: reencuadre → deseleccionar", () => {
    const conReencuadre = montar({ reencuadreId: "img-1", conSeleccion: true });
    tecla("Escape");
    expect(conReencuadre.onSalirReencuadre).toHaveBeenCalledTimes(1);
    expect(conReencuadre.store.getState().seleccion).toBe("texto-1");
    conReencuadre.hook.unmount();

    const sinModos = montar({ conSeleccion: true });
    tecla("Escape");
    expect(sinModos.store.getState().seleccion).toBeNull();
    sinModos.hook.unmount();
  });
});

describe("useAtajosTeclado — creación T/R/C/L (estilo Canva)", () => {
  // La edición en línea del texto se abre tras el commit de React (requestAnimationFrame):
  // en el test se ejecuta el callback al instante para poder afirmar de forma síncrona.
  const rafSincrono = () =>
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
      cb(0);
      return 0;
    });

  it("T crea la caja de texto del panel (Cuerpo), centrada en el viewport, seleccionada y en edición", () => {
    rafSincrono();
    const { store, lienzo, hook } = montar();
    const antes = store.getState().documento.capas.length;
    tecla("t");
    const st = store.getState();
    expect(st.documento.capas).toHaveLength(antes + 1);
    const capa = st.documento.capas[st.documento.capas.length - 1] as CapaTexto;
    // EXACTAMENTE el preset «Cuerpo» del panel Elementos.
    expect(capa.tipo).toBe("texto");
    expect(capa.texto).toBe("Texto de cuerpo");
    expect(capa.tamano).toBe(40);
    expect(capa.peso).toBe(400);
    expect(capa.w).toBe(760);
    // Centrada en el viewport (300, 200): x = 300 − 760/2; y = 200 − (40·1.14)/2 ≈ 177.
    expect(capa.x).toBe(300 - 380);
    expect(capa.y).toBe(200 - Math.round((40 * 1.14) / 2));
    // Queda seleccionada y entra directa en edición en línea.
    expect(st.seleccion).toBe(capa.id);
    expect(lienzo.current.editarTexto).toHaveBeenCalledWith(capa.id);
    hook.unmount();
    vi.unstubAllGlobals();
  });

  it("R, C y L crean rectángulo, elipse y línea con los MISMOS defaults que el panel", () => {
    const { store, hook } = montar();
    tecla("r");
    tecla("c");
    tecla("l");
    const capas = store.getState().documento.capas;
    const [rect, elipse, linea] = capas.slice(-3) as CapaMarco[];
    expect(rect).toMatchObject({ tipo: "marco", forma: "rect", relleno: "#E30613", borde: null, w: 360, h: 240 });
    expect(rect.x).toBe(300 - 180);
    expect(rect.y).toBe(200 - 120);
    expect(elipse).toMatchObject({ tipo: "marco", forma: "elipse", relleno: "#E30613", borde: null, w: 320, h: 320 });
    expect(linea).toMatchObject({ tipo: "marco", forma: "linea", relleno: null, borde: { color: "#FFFFFF", grosor: 8 }, w: 480, h: 0 });
    // Cada una queda encima de la anterior (z creciente) y seleccionada la última.
    expect(elipse.z).toBeGreaterThan(rect.z);
    expect(linea.z).toBeGreaterThan(elipse.z);
    expect(store.getState().seleccion).toBe(linea.id);
    hook.unmount();
  });

  it("cada creación es UN paso de deshacer", () => {
    const { store, hook } = montar();
    const antes = store.getState().documento.capas.length;
    tecla("r");
    expect(store.getState().documento.capas).toHaveLength(antes + 1);
    store.getState().deshacer();
    expect(store.getState().documento.capas).toHaveLength(antes);
    hook.unmount();
  });

  it("no crea nada con el modo recorte o reencuadre activos", () => {
    const conRecorte = montar({ recorteId: "img-1" });
    const antes = conRecorte.store.getState().documento.capas.length;
    tecla("r");
    expect(conRecorte.store.getState().documento.capas).toHaveLength(antes);
    conRecorte.hook.unmount();

    const conReencuadre = montar({ reencuadreId: "img-1" });
    tecla("t");
    expect(conReencuadre.store.getState().documento.capas).toHaveLength(antes);
    conReencuadre.hook.unmount();
  });

  it("no crea nada con modificadores (⌘R no es 'rectángulo') ni escribiendo en un campo", () => {
    const { store, hook } = montar();
    const antes = store.getState().documento.capas.length;
    teclaCon({ key: "r", metaKey: true });
    teclaCon({ key: "t", altKey: true });
    teclaCon({ key: "c", shiftKey: true });
    // Foco en un input: el atajo no debe robar la escritura.
    const input = document.createElement("input");
    document.body.appendChild(input);
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "t", bubbles: true }));
    input.remove();
    expect(store.getState().documento.capas).toHaveLength(antes);
    hook.unmount();
  });
});

describe("useAtajosTeclado — «Ordenar» (tidy up, ⌥⇧T)", () => {
  it("con 3+ capas seleccionadas reparte con espaciado uniforme (vía store.ordenarMulti)", () => {
    const { store, hook } = montar();
    const st = store.getState();
    st.agregar(nuevaCapaTexto({ id: "a", x: 0, y: 100, w: 100, h: 50, z: 2 }));
    st.agregar(nuevaCapaTexto({ id: "b", x: 130, y: 100, w: 100, h: 50, z: 3 }));
    st.agregar(nuevaCapaTexto({ id: "c", x: 500, y: 100, w: 100, h: 50, z: 4 }));
    st.seleccionarMuchas(["a", "b", "c"]);
    // En macOS ⌥⇧T cambia e.key; el atajo se apoya en e.code.
    teclaCon({ key: "ˇ", code: "KeyT", altKey: true, shiftKey: true });
    const capas = store.getState().documento.capas;
    const x = (id: string) => capas.find((c) => c.id === id)!.x;
    // Extensión 0..600, 3 cajas de 100 => hueco uniforme de 150: 0, 250, 500.
    expect([x("a"), x("b"), x("c")]).toEqual([0, 250, 500]);
    hook.unmount();
  });

  it("con 2 capas seleccionadas es un no-op: el atajo NI SIQUIERA llama a ordenarMulti (guard, como el botón)", () => {
    const { store, hook } = montar();
    const st = store.getState();
    st.agregar(nuevaCapaTexto({ id: "a", x: 0, y: 100, w: 100, h: 50, z: 2 }));
    st.agregar(nuevaCapaTexto({ id: "b", x: 130, y: 100, w: 100, h: 50, z: 3 }));
    st.seleccionarMuchas(["a", "b"]);
    const espia = vi.fn();
    store.setState({ ordenarMulti: espia });
    teclaCon({ key: "ˇ", code: "KeyT", altKey: true, shiftKey: true });
    expect(espia).not.toHaveBeenCalled();
    const capas = store.getState().documento.capas;
    expect(capas.find((c) => c.id === "b")!.x).toBe(130);
    expect(store.getState().puedeDeshacer()).toBe(true); // solo los `agregar`; el tidy no registró nada
    hook.unmount();
  });
});

describe("useAtajosTeclado — orden Z por teclado (⌘] / ⌘[ un paso; ⌘⇧] / ⌘⇧[ absoluto)", () => {
  // Tres capas apiladas con z 1/2/3 (a al fondo, c al frente); la del MEDIO seleccionada.
  const montarPila = () => {
    const store = crearStoreEditor(documentoVacio({ w: 1080, h: 1080, safe_top: 0, safe_bottom: 0 }, "test"));
    const st = store.getState();
    st.agregar(nuevaCapaMarco({ id: "a", x: 0, y: 0, w: 50, h: 50, z: 1, relleno: "#111111" }));
    st.agregar(nuevaCapaMarco({ id: "b", x: 0, y: 0, w: 50, h: 50, z: 2, relleno: "#222222" }));
    st.agregar(nuevaCapaMarco({ id: "c", x: 0, y: 0, w: 50, h: 50, z: 3, relleno: "#333333" }));
    st.seleccionar("b");
    const hook = renderHook(() =>
      useAtajosTeclado({
        store,
        zoom: { current: { acercar: vi.fn(), alejar: vi.fn(), ajustar: vi.fn(), real: vi.fn() } as ZoomApi },
        reencuadreId: null,
        recorteId: null,
      }),
    );
    const z = (id: string) => store.getState().documento.capas.find((c) => c.id === id)!.z;
    return { store, hook, z };
  };

  it("⌘] sube UN paso (z += 1), no salta al frente absoluto", () => {
    const { hook, z } = montarPila();
    teclaCon({ key: "]", metaKey: true });
    expect(z("b")).toBe(3); // 2 -> 3
    expect(z("c")).toBe(3); // c intacta (empatan; el orden final lo desempata el render)
    hook.unmount();
  });

  it("⌘[ baja UN paso (z -= 1)", () => {
    const { hook, z } = montarPila();
    teclaCon({ key: "[", metaKey: true });
    expect(z("b")).toBe(1); // 2 -> 1
    hook.unmount();
  });

  it("⌘⇧] trae al FRENTE absoluto (por encima de TODO)", () => {
    const { store, hook, z } = montarPila();
    teclaCon({ key: "]", metaKey: true, shiftKey: true });
    const maxOtras = Math.max(...store.getState().documento.capas.filter((c) => c.id !== "b").map((c) => c.z));
    expect(z("b")).toBeGreaterThan(maxOtras);
    hook.unmount();
  });

  it("⌘⇧[ envía al FONDO absoluto (por debajo de TODO)", () => {
    const { store, hook, z } = montarPila();
    teclaCon({ key: "[", metaKey: true, shiftKey: true });
    const minOtras = Math.min(...store.getState().documento.capas.filter((c) => c.id !== "b").map((c) => c.z));
    expect(z("b")).toBeLessThan(minOtras);
    hook.unmount();
  });
});
