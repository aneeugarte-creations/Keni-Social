import { describe, expect, it } from "vitest";

import { MIN_CROP, clampCrop, moverAsa } from "./recorte";

describe("clampCrop", () => {
  it("acota a [0,1] y respeta el mínimo", () => {
    const c = clampCrop({ cx: -0.5, cy: 2, cw: 0, ch: 5 });
    expect(c.cx).toBeGreaterThanOrEqual(0);
    expect(c.cy).toBeGreaterThanOrEqual(0);
    expect(c.cw).toBeGreaterThanOrEqual(MIN_CROP);
    expect(c.ch).toBeGreaterThanOrEqual(MIN_CROP);
    expect(c.cx + c.cw).toBeLessThanOrEqual(1 + 1e-9);
    expect(c.cy + c.ch).toBeLessThanOrEqual(1 + 1e-9);
  });

  it("mantiene un crop ya válido", () => {
    const c = clampCrop({ cx: 0.1, cy: 0.2, cw: 0.5, ch: 0.4 });
    expect(c).toEqual({ cx: 0.1, cy: 0.2, cw: 0.5, ch: 0.4 });
  });
});

describe("moverAsa", () => {
  const base = { cx: 0.2, cy: 0.2, cw: 0.6, ch: 0.6 };

  it("'mover' desplaza el rect sin cambiar tamaño y acota a los bordes", () => {
    const m = moverAsa(base, "mover", 0.1, -0.1);
    expect(m.cw).toBe(0.6);
    expect(m.ch).toBe(0.6);
    expect(m.cx).toBeCloseTo(0.3);
    expect(m.cy).toBeCloseTo(0.1);
    // No se sale por la derecha aunque empujemos mucho.
    const tope = moverAsa(base, "mover", 1, 0);
    expect(tope.cx + tope.cw).toBeLessThanOrEqual(1 + 1e-9);
  });

  it("asa 'e' crece el ancho hacia la derecha", () => {
    const m = moverAsa(base, "e", 0.1, 0);
    expect(m.cx).toBe(0.2);
    expect(m.cw).toBeCloseTo(0.7);
  });

  it("asa 'w' mueve el borde izquierdo y reduce el ancho", () => {
    const m = moverAsa(base, "w", 0.1, 0);
    expect(m.cx).toBeCloseTo(0.3);
    expect(m.cw).toBeCloseTo(0.5);
  });

  it("asa 'nw' mueve a la vez los bordes superior e izquierdo", () => {
    const m = moverAsa(base, "nw", 0.1, 0.1);
    expect(m.cx).toBeCloseTo(0.3);
    expect(m.cy).toBeCloseTo(0.3);
    expect(m.cw).toBeCloseTo(0.5);
    expect(m.ch).toBeCloseTo(0.5);
  });

  it("no permite que un borde cruce al opuesto (mínimo MIN_CROP)", () => {
    const m = moverAsa(base, "e", -1, 0);
    expect(m.cw).toBeGreaterThanOrEqual(MIN_CROP);
  });
});
