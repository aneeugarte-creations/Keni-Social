import { describe, expect, it } from "vitest";

import { etiquetaPeriodo } from "./periodo";

describe("etiquetaPeriodo", () => {
  it("traduce presets y tokens de mes/rango", () => {
    expect(etiquetaPeriodo("semana", [{ id: "semana", etiqueta: "Última semana" }])).toBe("Última semana");
    expect(etiquetaPeriodo("mes:2026-06", [])).toBe("junio 2026");
    expect(etiquetaPeriodo("rango:2026-06-01_2026-06-30", [])).toBe("2026-06-01 – 2026-06-30");
  });
});
