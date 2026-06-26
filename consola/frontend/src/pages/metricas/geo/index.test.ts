import { describe, expect, it } from "vitest";
import { centroideCiudad, centroidePais } from "./index";

describe("centroideCiudad", () => {
  it("resuelve un nombre de ciudad pelado", () => {
    expect(centroideCiudad("Monterrey")?.nombre).toBe("Monterrey");
  });

  // Instagram/Metricool entregan "Ciudad, Region" — antes daba 0 ubicaciones.
  it("resuelve 'Ciudad, Region' descartando el sufijo de region", () => {
    expect(centroideCiudad("Monterrey, Nuevo León")?.nombre).toBe("Monterrey");
    expect(centroideCiudad("Guadalajara, Jalisco")?.nombre).toBe("Guadalajara");
    expect(centroideCiudad("Tijuana, Baja California")?.nombre).toBe("Tijuana");
    expect(centroideCiudad("Cancún, Quintana Roo")?.nombre).toBe("Cancún");
  });

  it("resuelve 'Ciudad, Region, Pais' probando cada segmento", () => {
    expect(centroideCiudad("Puebla, Puebla, Mexico")?.nombre).toBe("Puebla");
  });

  it("aplica alias para la forma local de la capital", () => {
    expect(centroideCiudad("Mexico City, Distrito Federal")?.nombre).toBe("Mexico City");
    expect(centroideCiudad("Ciudad de México, Distrito Federal")?.nombre).toBe("Mexico City");
    expect(centroideCiudad("CDMX")?.nombre).toBe("Mexico City");
  });

  it("prefiere el pais indicado ante homonimos", () => {
    const mx = centroideCiudad("Mérida, Yucatán", "MX");
    expect(mx?.nombre).toBe("Mérida");
  });

  it("devuelve undefined si ningun segmento es una ciudad conocida", () => {
    expect(centroideCiudad("Pueblofantasma, Naníngun")).toBeUndefined();
    expect(centroideCiudad("")).toBeUndefined();
  });
});

describe("centroidePais (no debe cambiar)", () => {
  it("resuelve por codigo ISO alpha-2", () => {
    expect(centroidePais("MX")?.nombre).toBe("México");
  });
});
