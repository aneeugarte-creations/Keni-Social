import { describe, expect, it } from "vitest";

import { copyMuestra, ETIQUETA_MUESTRA, TITULAR_MUESTRA } from "./muestra";

describe("copyMuestra", () => {
  it("devuelve un titular largo para el binding copy_in (ver saltos de línea y auto-encogido)", () => {
    expect(copyMuestra("copy_in")).toBe(TITULAR_MUESTRA);
    // "Más bien largo": suficiente para forzar varias líneas en la caja del titular.
    expect(TITULAR_MUESTRA.length).toBeGreaterThan(40);
  });

  it("devuelve una pleca para el binding etiqueta_default", () => {
    expect(copyMuestra("etiqueta_default")).toBe(ETIQUETA_MUESTRA);
  });

  it("devuelve null para texto sin binding (usa su texto normal)", () => {
    expect(copyMuestra(null)).toBeNull();
    expect(copyMuestra(undefined)).toBeNull();
  });
});
