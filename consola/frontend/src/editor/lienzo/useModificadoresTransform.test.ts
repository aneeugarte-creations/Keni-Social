// Contrato de los modificadores VIVOS del Transformer: SHIFT invierte la proporción respecto a la
// base del tipo y restringe la rotación a 15°; ALT escala desde el centro. Se vuelca por eventos de
// teclado del documento, no al store.

import { renderHook } from "@testing-library/react";
import type Konva from "konva";
import { describe, expect, it } from "vitest";

import { useModificadoresTransform } from "./useModificadoresTransform";

// Transformer FALSO con los GetSet que usa el hook: cada uno guarda su valor y lo devuelve al
// llamarse sin argumento (misma forma que la API de Konva `tr.keepRatio(...)` / `tr.keepRatio()`).
function crearTrFalso() {
  const estado = { keepRatio: false, centeredScaling: false, rotationSnaps: [] as number[], rotationSnapTolerance: 0 };
  const getset =
    <K extends keyof typeof estado>(k: K) =>
    (v?: (typeof estado)[K]) => {
      if (v !== undefined) estado[k] = v;
      return estado[k];
    };
  const tr = {
    keepRatio: getset("keepRatio"),
    centeredScaling: getset("centeredScaling"),
    rotationSnaps: getset("rotationSnaps"),
    rotationSnapTolerance: getset("rotationSnapTolerance"),
  } as unknown as Konva.Transformer;
  return { tr, estado };
}

const keydown = (init: KeyboardEventInit) => document.dispatchEvent(new KeyboardEvent("keydown", init));
const keyup = (init: KeyboardEventInit) => document.dispatchEvent(new KeyboardEvent("keyup", init));

function montar(ratioBase: boolean, activo = true) {
  const { tr, estado } = crearTrFalso();
  const trRef = { current: tr };
  const hook = renderHook((props: { ratioBase: boolean; activo: boolean }) => useModificadoresTransform({ trRef, ...props }), {
    initialProps: { ratioBase, activo },
  });
  return { estado, hook };
}

describe("useModificadoresTransform — Shift (proporción + rotación 15°)", () => {
  it("base ratio-fijo (imagen/logo): al montar keepRatio=true; Shift lo LIBERA (false)", () => {
    const { estado, hook } = montar(true);
    expect(estado.keepRatio).toBe(true);
    keydown({ shiftKey: true });
    expect(estado.keepRatio).toBe(false);
    keyup({ shiftKey: false });
    expect(estado.keepRatio).toBe(true);
    hook.unmount();
  });

  it("base libre (texto/forma): al montar keepRatio=false; Shift lo BLOQUEA (true)", () => {
    const { estado, hook } = montar(false);
    expect(estado.keepRatio).toBe(false);
    keydown({ shiftKey: true });
    expect(estado.keepRatio).toBe(true);
    keyup({ shiftKey: false });
    expect(estado.keepRatio).toBe(false);
    hook.unmount();
  });

  it("Shift restringe la rotación a incrementos de 15° (tolerancia de medio paso)", () => {
    const { estado, hook } = montar(false);
    // Base: snaps suaves cada 45°.
    expect(estado.rotationSnaps).toEqual([0, 45, 90, 135, 180, 225, 270, 315]);
    expect(estado.rotationSnapTolerance).toBe(5);
    keydown({ shiftKey: true });
    expect(estado.rotationSnaps).toEqual(Array.from({ length: 24 }, (_, i) => i * 15));
    expect(estado.rotationSnapTolerance).toBe(7.5);
    keyup({ shiftKey: false });
    expect(estado.rotationSnaps).toEqual([0, 45, 90, 135, 180, 225, 270, 315]);
    hook.unmount();
  });
});

describe("useModificadoresTransform — Alt (escala desde el centro)", () => {
  it("Alt activa centeredScaling; soltarlo lo desactiva", () => {
    const { estado, hook } = montar(false);
    expect(estado.centeredScaling).toBe(false);
    keydown({ altKey: true });
    expect(estado.centeredScaling).toBe(true);
    keyup({ altKey: false });
    expect(estado.centeredScaling).toBe(false);
    hook.unmount();
  });

  it("Shift y Alt combinados (ambos flags a la vez)", () => {
    const { estado, hook } = montar(false);
    keydown({ shiftKey: true, altKey: true });
    expect(estado.keepRatio).toBe(true);
    expect(estado.centeredScaling).toBe(true);
    hook.unmount();
  });
});

describe("useModificadoresTransform — inactivo / limpieza", () => {
  it("con activo=false no engancha listeners (los modificadores no hacen nada)", () => {
    const { estado, hook } = montar(true, false);
    keydown({ shiftKey: true, altKey: true });
    expect(estado.keepRatio).toBe(false); // sin tocar (el hook no aplicó ni la base)
    expect(estado.centeredScaling).toBe(false);
    hook.unmount();
  });

  it("al desmontar restaura la base y deja de escuchar", () => {
    const { estado, hook } = montar(true);
    keydown({ shiftKey: true });
    expect(estado.keepRatio).toBe(false);
    hook.unmount();
    // Base restaurada al desmontar (ratioBase=true) y sin trabar el centeredScaling.
    expect(estado.keepRatio).toBe(true);
    expect(estado.centeredScaling).toBe(false);
    // Ya no escucha: un keydown posterior no cambia nada.
    keydown({ shiftKey: true });
    expect(estado.keepRatio).toBe(true);
  });

  it("perder el foco de la ventana (blur) resetea los modificadores a la base", () => {
    const { estado, hook } = montar(true);
    keydown({ shiftKey: true, altKey: true });
    expect(estado.keepRatio).toBe(false);
    expect(estado.centeredScaling).toBe(true);
    window.dispatchEvent(new Event("blur"));
    expect(estado.keepRatio).toBe(true);
    expect(estado.centeredScaling).toBe(false);
    hook.unmount();
  });
});
