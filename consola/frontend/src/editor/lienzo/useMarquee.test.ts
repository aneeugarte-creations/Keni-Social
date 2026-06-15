// "Clicar fuera de la foto" durante el modo de imagen (encuadre/recorte): un clic izquierdo en el
// VACÍO del Stage sale del modo (vía `salirDeModoImagen`) y deselecciona, como en Canva. Antes el
// guard de `modoImagen` ignoraba ese clic y solo se salía con Esc o el botón "Listo". Fuera de modo,
// el comportamiento de siempre (deselección en clic seco) se mantiene.

import { act, renderHook } from "@testing-library/react";
import type Konva from "konva";
import { describe, expect, it, vi } from "vitest";

import { documentoVacio, nuevaCapaImagen } from "../documento";
import { crearStoreEditor } from "../store";
import { useMarquee } from "./useMarquee";

function montar(opts: { enModo?: boolean; espacio?: boolean } = {}) {
  const store = crearStoreEditor(documentoVacio({ w: 1080, h: 1080, safe_top: 0, safe_bottom: 0 }, "test"));
  const foto = nuevaCapaImagen("obj", { id: "foto-1", es_foto: true });
  store.getState().agregar(foto);
  store.getState().seleccionar(foto.id);
  // Stage falso: solo necesita identidad (target === stage) y `container()` para el camino marquee.
  const stage = {
    container: () => ({ getBoundingClientRect: () => ({ left: 0, top: 0 }) }),
  } as unknown as Konva.Stage;
  const stageRef = { current: stage };
  const espacioRef = { current: !!opts.espacio };
  const salirDeModoImagen = vi.fn();
  const hook = renderHook(() =>
    useMarquee({
      stageRef,
      espacioRef,
      modoImagen: opts.enModo ? foto : null,
      escala: 1,
      store,
      salirDeModoImagen,
    }),
  );
  return { store, stage, salirDeModoImagen, hook };
}

function clic(stage: unknown, over: { target?: unknown; button?: number } = {}) {
  return {
    target: "target" in over ? over.target : stage,
    evt: { button: over.button ?? 0, clientX: 0, clientY: 0, shiftKey: false },
  } as unknown as Konva.KonvaEventObject<MouseEvent>;
}

describe("useMarquee — clic fuera de la foto en modo imagen", () => {
  it("clic izquierdo en el VACÍO sale del modo y deselecciona", () => {
    const { store, stage, salirDeModoImagen, hook } = montar({ enModo: true });
    expect(store.getState().seleccion).toBe("foto-1");
    act(() => hook.result.current.onMouseDownStage(clic(stage)));
    expect(salirDeModoImagen).toHaveBeenCalledTimes(1);
    expect(store.getState().seleccion).toBeNull();
  });

  it("clic sobre un NODO (no el vacío) no sale del modo ni deselecciona", () => {
    const { store, stage, salirDeModoImagen, hook } = montar({ enModo: true });
    act(() => hook.result.current.onMouseDownStage(clic(stage, { target: { id: "otro" } })));
    expect(salirDeModoImagen).not.toHaveBeenCalled();
    expect(store.getState().seleccion).toBe("foto-1");
  });

  it("botón derecho en el vacío no sale del modo (no es un clic de selección)", () => {
    const { salirDeModoImagen, stage, hook } = montar({ enModo: true });
    act(() => hook.result.current.onMouseDownStage(clic(stage, { button: 2 })));
    expect(salirDeModoImagen).not.toHaveBeenCalled();
  });

  it("con ESPACIO pulsado (pan) no sale del modo", () => {
    const { salirDeModoImagen, stage, hook } = montar({ enModo: true, espacio: true });
    act(() => hook.result.current.onMouseDownStage(clic(stage)));
    expect(salirDeModoImagen).not.toHaveBeenCalled();
  });

  it("FUERA de modo, el clic seco sigue deseleccionando sin tocar salirDeModoImagen", () => {
    const { store, stage, salirDeModoImagen, hook } = montar({ enModo: false });
    act(() => hook.result.current.onMouseDownStage(clic(stage)));
    expect(salirDeModoImagen).not.toHaveBeenCalled();
    // El clic seco resuelve la deselección en el mouseup (sin arrastre = clic seco).
    act(() => window.dispatchEvent(new MouseEvent("mouseup")));
    expect(store.getState().seleccion).toBeNull();
  });
});
