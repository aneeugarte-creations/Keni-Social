import { describe, expect, it } from "vitest";

import { documentoVacio, nuevaCapaTexto, type CapaOverlay } from "./documento";
import {
  analizarLegibilidad,
  contraste,
  correccionPara,
  hexARgb,
  luminanciaRGB,
  umbralAA,
  type Muestreador,
} from "./legibilidad";

const F45 = { w: 1080, h: 1350, safe_top: 60, safe_bottom: 96 };

describe("WCAG helpers", () => {
  it("luminancia: blanco=1, negro=0", () => {
    expect(luminanciaRGB(255, 255, 255)).toBeCloseTo(1, 5);
    expect(luminanciaRGB(0, 0, 0)).toBeCloseTo(0, 5);
  });
  it("contraste blanco/negro = 21:1", () => {
    expect(contraste(1, 0)).toBeCloseTo(21, 5);
  });
  it("hexARgb soporta #RGB y #RRGGBBAA", () => {
    expect(hexARgb("#fff")).toEqual([255, 255, 255]);
    expect(hexARgb("#E30613")).toEqual([227, 6, 19]);
    expect(hexARgb("#00000080")).toEqual([0, 0, 0]);
  });
  it("umbral AA: 3:1 para titular grande, 4.5:1 si pequeño", () => {
    expect(umbralAA(nuevaCapaTexto({ tamano: 60, peso: 700 }))).toBe(3);
    expect(umbralAA(nuevaCapaTexto({ tamano: 16, peso: 400 }))).toBe(4.5);
  });
});

describe("analizarLegibilidad", () => {
  it("marca texto blanco sobre fondo claro como poco legible", () => {
    const doc = documentoVacio(F45, "uno");
    doc.capas.push(nuevaCapaTexto({ id: "t1", color: "#FFFFFF", x: 80, y: 200, w: 600, h: 120 }));
    const muestrear: Muestreador = () => 0.9; // fondo muy claro
    const malos = analizarLegibilidad(doc, muestrear);
    expect(malos.map((m) => m.id)).toContain("t1");
  });

  it("no marca texto blanco sobre fondo oscuro", () => {
    const doc = documentoVacio(F45, "uno");
    doc.capas.push(nuevaCapaTexto({ id: "t1", color: "#FFFFFF", x: 80, y: 200, w: 600, h: 120 }));
    const muestrear: Muestreador = () => 0.02; // fondo oscuro
    expect(analizarLegibilidad(doc, muestrear)).toHaveLength(0);
  });

  it("omite textos invisibles, vacíos o sin muestra", () => {
    const doc = documentoVacio(F45, "uno");
    doc.capas.push(nuevaCapaTexto({ id: "oculto", visible: false, color: "#FFFFFF" }));
    doc.capas.push(nuevaCapaTexto({ id: "vacio", texto: "  ", color: "#FFFFFF" }));
    doc.capas.push(nuevaCapaTexto({ id: "sinmuestra", color: "#FFFFFF" }));
    const muestrear: Muestreador = () => null; // sin muestra para ninguna caja
    expect(analizarLegibilidad(doc, muestrear)).toHaveLength(0);
  });
});

describe("correccionPara", () => {
  it("texto al pie -> overlay inferior", () => {
    const doc = documentoVacio(F45, "uno");
    doc.capas.push(nuevaCapaTexto({ id: "t1", color: "#FFFFFF", x: 80, y: 1100, w: 600, h: 150 }));
    const malos = analizarLegibilidad(doc, () => 0.9);
    const c = correccionPara(doc, malos[0]);
    expect(c.tipo).toBe("overlay");
    if (c.tipo === "overlay") {
      const ov = c.capa as CapaOverlay;
      expect(ov.tipo).toBe("overlay");
      expect(ov.alto_frac).toBeGreaterThan(0);
      expect(ov.alpha).toBeGreaterThan(0);
    }
  });

  it("texto arriba -> refuerzo en el propio texto (contorno/sombra)", () => {
    const doc = documentoVacio(F45, "uno");
    doc.capas.push(nuevaCapaTexto({ id: "t1", color: "#FFFFFF", x: 80, y: 100, w: 600, h: 120 }));
    const malos = analizarLegibilidad(doc, () => 0.9);
    const c = correccionPara(doc, malos[0]);
    expect(c.tipo).toBe("texto");
    if (c.tipo === "texto") {
      expect(c.cambios.contorno).toBeTruthy();
    }
  });
});
