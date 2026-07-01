// Tests del mapa de PESOS REALES por familia: qué caras embebe cada tipografía del catálogo, para
// atenuar en el selector los pesos que la familia no tiene (patrón Canva).
import { describe, expect, it } from "vitest";

import { pesoDisponible, pesosDisponibles } from "./pesosFamilia";

describe("pesosFamilia — pesos reales por familia", () => {
  it("Barlow (la 'sans' por defecto) embebe 400/600/700, no 300/500/800/900", () => {
    expect(pesosDisponibles("Barlow")).toEqual([400, 600, 700]);
    expect(pesoDisponible("Barlow", 300)).toBe(false);
    expect(pesoDisponible("Barlow", 500)).toBe(false);
    expect(pesoDisponible("Barlow", 700)).toBe(true);
    expect(pesoDisponible("Barlow", 900)).toBe(false);
  });

  it("Anton solo existe en un peso (400): el resto no está disponible", () => {
    expect(pesosDisponibles("Anton")).toEqual([400]);
    expect(pesoDisponible("Anton", 400)).toBe(true);
    expect(pesoDisponible("Anton", 300)).toBe(false);
    expect(pesoDisponible("Anton", 700)).toBe(false);
  });

  it("Montserrat cubre 300..900 completos", () => {
    for (const p of [300, 400, 500, 600, 700, 800, 900]) {
      expect(pesoDisponible("Montserrat", p)).toBe(true);
    }
  });

  it("resuelve las familias lógicas legadas: 'sans' -> Barlow, 'condensada' -> Barlow Condensed", () => {
    expect(pesosDisponibles("sans")).toEqual([400, 600, 700]);
    expect(pesosDisponibles("condensada")).toEqual([600, 700, 800]);
    expect(pesoDisponible("condensada", 300)).toBe(false);
    expect(pesoDisponible("condensada", 800)).toBe(true);
  });

  it("una familia desconocida (fuente de marca) no restringe: todos los pesos disponibles", () => {
    expect(pesosDisponibles("Fuente De Marca X")).toBeNull();
    expect(pesoDisponible("Fuente De Marca X", 300)).toBe(true);
    expect(pesoDisponible("Fuente De Marca X", 900)).toBe(true);
  });
});
