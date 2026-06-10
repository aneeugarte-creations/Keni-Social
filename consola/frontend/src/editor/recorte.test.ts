import { describe, expect, it } from "vitest";

import { MIN_CROP, clampCrop, escalarCrop, moverAsa, vistaRecorte } from "./recorte";

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

describe("escalarCrop (modo recorte estilo Canva)", () => {
  const base = { cx: 0.25, cy: 0.25, cw: 0.5, ch: 0.5 };

  it("f=2 reduce el recorte a la mitad alrededor del ancla (imagen el doble de grande)", () => {
    const m = escalarCrop(base, 2, 0.5, 0.5);
    expect(m).toEqual({ cx: 0.375, cy: 0.375, cw: 0.25, ch: 0.25 });
  });

  it("conserva la posición RELATIVA del ancla dentro del recorte", () => {
    const ax = 0.3, ay = 0.6;
    const relX = (ax - base.cx) / base.cw;
    const relY = (ay - base.cy) / base.ch;
    const m = escalarCrop(base, 1.7, ax, ay);
    expect((ax - m.cx) / m.cw).toBeCloseTo(relX);
    expect((ay - m.cy) / m.ch).toBeCloseTo(relY);
  });

  it("al alejar (f<1) acota el factor para no salirse de la fuente", () => {
    const m = escalarCrop(base, 0.1, 0.5, 0.5);
    expect(m).toEqual({ cx: 0, cy: 0, cw: 1, ch: 1 });
  });

  it("al acercar (f grande) respeta el mínimo MIN_CROP del lado menor", () => {
    const m = escalarCrop({ cx: 0, cy: 0, cw: 0.5, ch: 0.25 }, 1000, 0, 0);
    expect(Math.min(m.cw, m.ch)).toBeGreaterThanOrEqual(MIN_CROP - 1e-9);
    // Mantiene la proporción del recorte.
    expect(m.cw / m.ch).toBeCloseTo(2);
  });

  it("un factor inválido (<= 0) no produce NaN: cae al mínimo permitido", () => {
    const m = escalarCrop(base, 0, 0.5, 0.5);
    expect(Number.isFinite(m.cx)).toBe(true);
    expect(m.cw).toBeLessThanOrEqual(1);
  });
});

describe("vistaRecorte (imagen original completa en el modo recorte)", () => {
  it("sin crop, cover con la misma proporción: la imagen completa coincide con la caja", () => {
    const v = vistaRecorte(200, 100, 100, 50, "cover", [0.5, 0.5]);
    expect(v.escalaSrc).toBeCloseTo(0.5);
    expect(v.fx).toBeCloseTo(0);
    expect(v.fy).toBeCloseTo(0);
    expect(v.fw).toBeCloseTo(100);
    expect(v.fh).toBeCloseTo(50);
  });

  it("con crop, la REGIÓN recortada aterriza exactamente en el marco", () => {
    const crop = { cx: 0.5, cy: 0.5, cw: 0.5, ch: 0.5 };
    const v = vistaRecorte(100, 100, 50, 50, "cover", [0.5, 0.5], 1, crop);
    expect(v.escalaSrc).toBeCloseTo(1);
    // La esquina del crop (fracción 0.5 de la imagen completa) cae en el origen del marco…
    expect(v.fx + crop.cx * v.fw).toBeCloseTo(0);
    expect(v.fy + crop.cy * v.fh).toBeCloseTo(0);
    // …y el ancho del crop cubre el marco entero (cover con la misma proporción).
    expect(crop.cw * v.fw).toBeCloseTo(50);
  });

  it("contain con letterbox: la imagen completa queda centrada con su banda", () => {
    const v = vistaRecorte(100, 50, 100, 100, "contain", [0.5, 0.5]);
    expect(v.escalaSrc).toBeCloseTo(1);
    expect(v.fx).toBeCloseTo(0);
    expect(v.fy).toBeCloseTo(25);
    expect(v.fw).toBeCloseTo(100);
    expect(v.fh).toBeCloseTo(50);
  });
});
