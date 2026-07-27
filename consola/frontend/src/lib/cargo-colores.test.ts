import { describe, expect, it } from "vitest";

import { CARGOS_ORDENADOS } from "@/types";

import {
  degradadoCargo,
  familiaDeCargo,
  FAMILIA_DE_CARGO,
  META_FAMILIA,
  metaCargo,
} from "./cargo-colores";

describe("cargo-colores", () => {
  it("clasifica TODO el catálogo de cargos en una familia con paleta", () => {
    for (const cargo of CARGOS_ORDENADOS) {
      const familia = familiaDeCargo(cargo);
      expect(familia, `cargo sin familia: ${cargo}`).not.toBe("sin_cargo");
      expect(META_FAMILIA[familia]).toBeDefined();
    }
    // Y ninguna familia declarada se queda sin cargos que la usen (salvo el hueco de "sin cargo").
    const usadas = new Set(Object.values(FAMILIA_DE_CARGO));
    for (const familia of Object.keys(META_FAMILIA)) {
      if (familia === "sin_cargo") continue;
      expect(usadas.has(familia as (typeof FAMILIA_DE_CARGO)[keyof typeof FAMILIA_DE_CARGO])).toBe(
        true,
      );
    }
  });

  it("agrupa por función: coordinaciones juntas, community y content juntos", () => {
    expect(familiaDeCargo("coordinador_redes")).toBe(familiaDeCargo("coordinador_youtube"));
    expect(familiaDeCargo("community_manager")).toBe(familiaDeCargo("content_manager"));
    expect(familiaDeCargo("director")).not.toBe(familiaDeCargo("redactor"));
  });

  it("sin cargo (o desconocido) cae en la familia neutra", () => {
    expect(familiaDeCargo("")).toBe("sin_cargo");
    expect(familiaDeCargo(null)).toBe("sin_cargo");
    expect(metaCargo(undefined).etiqueta).toBe("Sin cargo");
  });

  it("cada familia pinta un degradado distinto", () => {
    const degradados = new Set(
      Object.keys(META_FAMILIA).map((f) => META_FAMILIA[f as keyof typeof META_FAMILIA].degradado.join()),
    );
    expect(degradados.size).toBe(Object.keys(META_FAMILIA).length);
    expect(degradadoCargo("director")).toMatch(/^linear-gradient\(135deg, #/);
  });
});
