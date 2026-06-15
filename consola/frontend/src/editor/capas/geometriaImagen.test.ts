import { describe, expect, it } from "vitest";

import { geometriaImagenEnCaja } from "./geometriaImagen";

// El marco de selección (Transformer) abraza el rect VISIBLE que devuelve este helper, así que
// estos tests son el contrato del "marco == foto renderizada" (estilo Canva).
describe("geometriaImagenEnCaja", () => {
  it("cover: el rect visible es EXACTAMENTE la caja (el desborde recortado no infla el marco)", () => {
    // Foto 200×100 (2:1) en caja 100×100: cover escala a 200×100 ⇒ desborda 100px en X.
    const g = geometriaImagenEnCaja(200, 100, 100, 100, "cover", [0.5, 0.5]);
    expect({ x: g.vx, y: g.vy, w: g.vw, h: g.vh }).toEqual({ x: 0, y: 0, w: 100, h: 100 });
    // El destino completo sí desborda.
    expect(g.dw).toBeCloseTo(200);
    expect(g.ix).toBeCloseTo(-50);
    // La fuente visible es la banda central (50..150) de la foto.
    expect(g.sx).toBeCloseTo(50);
    expect(g.sy).toBeCloseTo(0);
    expect(g.sw).toBeCloseTo(100);
    expect(g.sh).toBeCloseTo(100);
  });

  it("cover + foco en los extremos: la banda de fuente visible sigue al foco; el visible sigue siendo la caja", () => {
    const izq = geometriaImagenEnCaja(200, 100, 100, 100, "cover", [0, 0.5]);
    expect(izq.sx).toBeCloseTo(0);
    const der = geometriaImagenEnCaja(200, 100, 100, 100, "cover", [1, 0.5]);
    expect(der.sx).toBeCloseTo(100);
    expect([der.vx, der.vy, der.vw, der.vh]).toEqual([0, 0, 100, 100]);
  });

  it("contain: el rect visible abraza la foto letterboxed, NO la caja entera", () => {
    // Foto 200×100 en caja 100×100: contain ⇒ 100×50 centrada (letterbox arriba/abajo).
    const g = geometriaImagenEnCaja(200, 100, 100, 100, "contain", [0.5, 0.5]);
    expect({ x: g.vx, y: g.vy, w: g.vw, h: g.vh }).toEqual({ x: 0, y: 25, w: 100, h: 50 });
    // Se ve la foto ENTERA (fuente completa).
    expect([g.sx, g.sy, g.sw, g.sh]).toEqual([0, 0, 200, 100]);
  });

  it("zoom (reencuadre) sobre cover: visible = caja; la fuente se estrecha por el zoom", () => {
    const g = geometriaImagenEnCaja(100, 100, 100, 100, "cover", [0.5, 0.5], 2);
    expect([g.vx, g.vy, g.vw, g.vh]).toEqual([0, 0, 100, 100]);
    expect(g.sx).toBeCloseTo(25);
    expect(g.sy).toBeCloseTo(25);
    expect(g.sw).toBeCloseTo(50);
    expect(g.sh).toBeCloseTo(50);
  });

  it("crop: la fuente visible se expresa en px de la imagen ORIGINAL (origen del crop sumado)", () => {
    // Crop a la mitad derecha (cx .5, cw .5) de una foto 200×100 ⇒ efectiva 100×100, encaja exacta.
    const g = geometriaImagenEnCaja(200, 100, 100, 100, "cover", [0.5, 0.5], 1, { cx: 0.5, cy: 0, cw: 0.5, ch: 1 });
    expect([g.vx, g.vy, g.vw, g.vh]).toEqual([0, 0, 100, 100]);
    expect(g.sx).toBeCloseTo(100);
    expect(g.sy).toBeCloseTo(0);
    expect(g.sw).toBeCloseTo(100);
    expect(g.sh).toBeCloseTo(100);
  });

  it("intersección vacía (foco fuera de rango): cae al destino completo, nunca un rect nulo", () => {
    const g = geometriaImagenEnCaja(100, 100, 100, 100, "cover", [50, 0.5], 4);
    expect(g.vw).toBeGreaterThan(0);
    expect(g.vh).toBeGreaterThan(0);
  });

  it("fuente con dimensiones 0 no casca (cae a 1px)", () => {
    const g = geometriaImagenEnCaja(0, 0, 100, 50, "cover", [0.5, 0.5]);
    expect(Number.isFinite(g.vw)).toBe(true);
    expect(Number.isFinite(g.sh)).toBe(true);
  });
});
