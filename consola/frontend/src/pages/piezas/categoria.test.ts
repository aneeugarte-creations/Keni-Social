import { describe, expect, it } from "vitest";

import { etiquetaCategoriaPieza } from "./categoria";

describe("etiquetaCategoriaPieza", () => {
  it("resuelve los slugs de sección a su nombre legible (igual que la Mesa)", () => {
    expect(etiquetaCategoriaPieza("salud")).toBe("Salud");
    expect(etiquetaCategoriaPieza("medio-ambiente")).toBe("Medio ambiente");
    expect(etiquetaCategoriaPieza("educacion")).toBe("Educación");
    expect(etiquetaCategoriaPieza("impacto-social")).toBe("Impacto social");
  });

  it("la señal del motor (breaking) → «Última hora»", () => {
    expect(etiquetaCategoriaPieza("breaking")).toBe("Última hora");
  });

  it("un slug fuera del catálogo cae a su forma capitalizada (no rompe)", () => {
    expect(etiquetaCategoriaPieza("loquesea")).toBe("Loquesea");
  });

  it("pieza sin categoría (vacío, espacios, o ausente en runtime) → '' (sin etiqueta)", () => {
    expect(etiquetaCategoriaPieza("")).toBe("");
    expect(etiquetaCategoriaPieza("   ")).toBe("");
    expect(etiquetaCategoriaPieza(undefined)).toBe("");
    expect(etiquetaCategoriaPieza(null)).toBe("");
  });
});
