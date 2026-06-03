import { describe, expect, it } from "vitest";

import {
  ENCUADRE_DEFECTO,
  esEncuadreDefecto,
  normalizarEncuadre,
  parsearEncuadre,
  serializarEncuadre,
} from "./encuadre";

describe("encuadre de foto", () => {
  it("normaliza foco a [0,1] y zoom a [1,6]", () => {
    expect(normalizarEncuadre({ foco: [-0.3, 1.8], zoom: 0.2 })).toEqual({
      foco: [0, 1],
      zoom: 1,
    });
    expect(normalizarEncuadre({ foco: [0.4, 0.6], zoom: 9 })).toEqual({
      foco: [0.4, 0.6],
      zoom: 6,
    });
  });

  it("reconoce el encuadre por defecto", () => {
    expect(esEncuadreDefecto(ENCUADRE_DEFECTO)).toBe(true);
    expect(esEncuadreDefecto({ foco: [0.5, 0.5], zoom: 1 })).toBe(true);
    expect(esEncuadreDefecto({ foco: [0.4, 0.5], zoom: 1 })).toBe(false);
    expect(esEncuadreDefecto({ foco: [0.5, 0.5], zoom: 1.5 })).toBe(false);
  });

  it("serializa solo si NO es el por defecto (no ensucia la pieza)", () => {
    expect(serializarEncuadre(null)).toBe("");
    expect(serializarEncuadre(ENCUADRE_DEFECTO)).toBe("");
    expect(serializarEncuadre({ foco: [0.2, 0.8], zoom: 1.5 })).toBe(
      JSON.stringify({ foco: [0.2, 0.8], zoom: 1.5 }),
    );
  });

  it("parsea JSON válido y descarta vacío/ inválido", () => {
    expect(parsearEncuadre("")).toBeNull();
    expect(parsearEncuadre("   ")).toBeNull();
    expect(parsearEncuadre("no-json")).toBeNull();
    expect(parsearEncuadre('{"zoom": 2}')).toBeNull(); // sin foco -> null
    expect(parsearEncuadre('{"foco": [0.2, 0.8], "zoom": 1.5}')).toEqual({
      foco: [0.2, 0.8],
      zoom: 1.5,
    });
  });

  it("ida y vuelta: serializar → parsear conserva el encuadre", () => {
    const e = { foco: [0.3, 0.7] as [number, number], zoom: 2 };
    expect(parsearEncuadre(serializarEncuadre(e))).toEqual(e);
  });
});
