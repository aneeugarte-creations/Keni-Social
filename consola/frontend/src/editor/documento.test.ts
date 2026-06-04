import { describe, expect, it } from "vitest";

import { documentoVacio } from "./documento";

describe("documentoVacio", () => {
  it("nace LIMPIO, vacío y con fondo transparente", () => {
    const doc = documentoVacio({ w: 1080, h: 1350, safe_top: 60, safe_bottom: 96 }, "claro-sports");
    // Sin capas: un lienzo nuevo no trae nada predibujado (ni hueco de foto gris).
    expect(doc.capas).toHaveLength(0);
    // Fondo transparente: se ve el tablero en el editor y exporta con alfa.
    expect(doc.fondo.tipo).toBe("color");
    expect(doc.fondo.color).toBe("#00000000");
  });
});
