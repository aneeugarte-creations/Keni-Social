import { describe, expect, it } from "vitest";

import { estiloFuente, familiaReal } from "./tipografia";

// `estiloFuente` construye el `fontStyle` de Konva con el PESO NUMÉRICO REAL de la capa: Konva lo
// concatena tal cual en el shorthand del canvas y el navegador elige la MISMA cara que el export
// del servidor (`fuenteCss` pinta `${peso} …px`).
describe("estiloFuente (fontStyle Konva con peso real)", () => {
  it("pasa el peso numérico tal cual (Light 300, ExtraBold 800, Black 900…)", () => {
    for (const peso of [300, 400, 500, 600, 700, 800, 900]) {
      expect(estiloFuente({ familia: "Montserrat", peso })).toBe(String(peso));
    }
  });

  it("usa 700 por defecto si la capa no trae peso (mismo defecto que fuenteCss en el servidor)", () => {
    expect(estiloFuente({ familia: "Montserrat", peso: 0 })).toBe("700");
    expect(estiloFuente({ familia: "Barlow", peso: undefined as unknown as number })).toBe("700");
  });

  it("antepone italic SOLO en familias con itálica real (regla de dibujar.mjs)", () => {
    expect(estiloFuente({ familia: "Montserrat", peso: 900, cursiva: true })).toBe("italic 900");
    expect(estiloFuente({ familia: "Montserrat", peso: 300, cursiva: true })).toBe("italic 300");
    // Anton no tiene itálica: el flag se ignora (nada se sintetiza, igual que en el export).
    expect(estiloFuente({ familia: "Anton", peso: 400, cursiva: true })).toBe("400");
  });

  it("resuelve las familias lógicas legadas antes de decidir la cursiva", () => {
    // "sans" -> Barlow (tiene itálica real).
    expect(estiloFuente({ familia: "sans", peso: 700, cursiva: true })).toBe("italic 700");
  });
});

describe("familiaReal (familias lógicas legadas)", () => {
  it("mapea sans/condensada y deja pasar los nombres reales", () => {
    expect(familiaReal("sans")).toBe("Barlow");
    expect(familiaReal("condensada")).toBe("Barlow Condensed");
    expect(familiaReal("Montserrat")).toBe("Montserrat");
    expect(familiaReal(undefined)).toBe("Barlow");
  });
});
