import { describe, expect, it } from "vitest";

import { nombreCategoriaPlan } from "./categoria";

const CATEGORIAS = {
  fundacion: [
    { id: "salud", nombre: "Salud" },
    { id: "medio-ambiente", nombre: "Medio ambiente" },
    { id: "breaking", nombre: "Última hora" },
  ],
  "claro-sports": [{ id: "futbol", nombre: "Fútbol" }],
};

describe("nombreCategoriaPlan", () => {
  it("resuelve el nombre legible por id dentro de su marca", () => {
    expect(nombreCategoriaPlan("salud", "fundacion", CATEGORIAS)).toBe("Salud");
    expect(nombreCategoriaPlan("medio-ambiente", "fundacion", CATEGORIAS)).toBe(
      "Medio ambiente",
    );
  });

  it("la señal del motor (breaking) usa su rótulo del catálogo", () => {
    expect(nombreCategoriaPlan("breaking", "fundacion", CATEGORIAS)).toBe("Última hora");
  });

  it("categoría que no está en el plan de la marca (Fuera del plan) → '' (sin etiqueta)", () => {
    expect(nombreCategoriaPlan("internacional", "fundacion", CATEGORIAS)).toBe("");
  });

  it("una categoría de OTRA marca no se resuelve con la marca equivocada", () => {
    expect(nombreCategoriaPlan("futbol", "fundacion", CATEGORIAS)).toBe("");
  });

  it("pieza sin categoría (vacío, espacios, o ausente en runtime) → ''", () => {
    expect(nombreCategoriaPlan("", "fundacion", CATEGORIAS)).toBe("");
    expect(nombreCategoriaPlan("   ", "fundacion", CATEGORIAS)).toBe("");
    // Piezas legadas/parciales: el campo puede faltar pese a estar tipado como string.
    expect(nombreCategoriaPlan(undefined, "fundacion", CATEGORIAS)).toBe("");
    expect(nombreCategoriaPlan(null, "fundacion", CATEGORIAS)).toBe("");
  });

  it("catálogo aún no cargado → ''", () => {
    expect(nombreCategoriaPlan("salud", "fundacion", undefined)).toBe("");
  });

  it("marca sin categorías en el catálogo → ''", () => {
    expect(nombreCategoriaPlan("salud", "marca-nueva", CATEGORIAS)).toBe("");
  });
});
