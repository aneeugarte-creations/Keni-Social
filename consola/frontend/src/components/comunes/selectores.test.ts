import { describe, expect, it } from "vitest";

import {
  desdeNinguna,
  marcaCanonicaDesdeMetricas,
  marcaMetricasDesdeCanonica,
  MARCA_TODAS,
  NINGUNA,
  ningunaParam,
  RED_TODAS,
} from "./selectores";

/**
 * Tests del centinela canónico `NINGUNA` (#89 / N1) y sus helpers. Antes el
 * valor `"__ninguna__"` se declaraba localmente en `DialogoNueva` y
 * `Termometro`; ahora la única fuente de verdad vive aquí.
 */
describe("centinelas canónicos", () => {
  it("NINGUNA es el valor canónico __ninguna__", () => {
    expect(NINGUNA).toBe("__ninguna__");
  });

  it("NINGUNA es distinto de los centinelas de 'todas'", () => {
    expect(NINGUNA).not.toBe(MARCA_TODAS);
    expect(NINGUNA).not.toBe(RED_TODAS);
  });
});

describe("ningunaParam", () => {
  it("traduce el centinela a cadena vacía (campo sin valor)", () => {
    expect(ningunaParam(NINGUNA)).toBe("");
  });

  it("deja pasar un valor concreto sin tocarlo", () => {
    expect(ningunaParam("unotv")).toBe("unotv");
    expect(ningunaParam("instagram")).toBe("instagram");
  });
});

describe("desdeNinguna", () => {
  it("mapea vacío / null / undefined al centinela", () => {
    expect(desdeNinguna("")).toBe(NINGUNA);
    expect(desdeNinguna(null)).toBe(NINGUNA);
    expect(desdeNinguna(undefined)).toBe(NINGUNA);
  });

  it("deja pasar un valor concreto", () => {
    expect(desdeNinguna("claro-sports")).toBe("claro-sports");
  });

  it("es inverso de ningunaParam en ambos sentidos", () => {
    expect(ningunaParam(desdeNinguna(""))).toBe("");
    expect(desdeNinguna(ningunaParam("unotv"))).toBe("unotv");
  });
});

describe("traducción de id de marca métricas ↔ canónico", () => {
  it("convierte guion_bajo a slug-guion", () => {
    expect(marcaCanonicaDesdeMetricas("claro_sports")).toBe("claro-sports");
  });

  it("convierte slug-guion a guion_bajo", () => {
    expect(marcaMetricasDesdeCanonica("claro-sports")).toBe("claro_sports");
  });
});
