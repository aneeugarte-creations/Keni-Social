import { describe, expect, it } from "vitest";

import { etiquetaCategoriaPieza } from "./categoria";

const LINEAS = [
  { id: "06ad3588a80e", nombre: "Salud", marca: "fundacion" },
  { id: "9f1c2d3e4a5b", nombre: "Educación", marca: "fundacion" },
  { id: "aabbccddeeff", nombre: "Internacional", marca: "" },
];

describe("etiquetaCategoriaPieza", () => {
  it("resuelve el ID de una categoría a su nombre vía `lineas` (no muestra el hash)", () => {
    expect(etiquetaCategoriaPieza("06ad3588a80e", LINEAS)).toBe("Salud");
    expect(etiquetaCategoriaPieza("9f1c2d3e4a5b", LINEAS)).toBe("Educación");
  });

  it("resuelve un slug de categoría conocido vía etiquetaCategoria (señal del motor / ingesta)", () => {
    expect(etiquetaCategoriaPieza("breaking", LINEAS)).toBe("Última hora");
    expect(etiquetaCategoriaPieza("salud", LINEAS)).toBe("Salud");
  });

  it("un id crudo NO resoluble (no está en `lineas` ni es slug conocido) → '' (nunca el hash)", () => {
    expect(etiquetaCategoriaPieza("deadbeef0000", LINEAS)).toBe("");
  });

  it("catálogo aún sin cargar → '' (no pinta el id hasta resolver)", () => {
    expect(etiquetaCategoriaPieza("06ad3588a80e", undefined)).toBe("");
  });

  it("pieza sin categoría (vacío, espacios, o ausente en runtime) → ''", () => {
    expect(etiquetaCategoriaPieza("", LINEAS)).toBe("");
    expect(etiquetaCategoriaPieza("   ", LINEAS)).toBe("");
    expect(etiquetaCategoriaPieza(undefined, LINEAS)).toBe("");
    expect(etiquetaCategoriaPieza(null, LINEAS)).toBe("");
  });
});
