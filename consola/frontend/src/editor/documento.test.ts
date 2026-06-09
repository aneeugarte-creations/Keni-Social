import { describe, expect, it } from "vitest";

import { documentoVacio } from "./documento";

describe("documentoVacio", () => {
  it("nace transparente y con el hueco de foto OCULTO (marcado y bloqueado)", () => {
    const doc = documentoVacio({ w: 1080, h: 1350, safe_top: 60, safe_bottom: 96 }, "claro-sports");
    // Fondo transparente: se ve el tablero en el editor y exporta con alfa.
    expect(doc.fondo.tipo).toBe("color");
    expect(doc.fondo.color).toBe("#00000000");
    // Trae su hueco de foto (obligatorio para plantilla) pero OCULTO para no ensuciar el lienzo.
    const imagenes = doc.capas.filter((c) => c.tipo === "imagen");
    expect(imagenes).toHaveLength(1);
    const hueco = imagenes[0];
    expect(hueco.tipo === "imagen" && hueco.es_foto).toBe(true);
    expect(hueco.bloqueada).toBe(true);
    expect(hueco.visible).toBe(false);
  });

  it("preserva los márgenes laterales safe_left/safe_right del formato (aditivos)", () => {
    const doc = documentoVacio({ w: 1080, h: 1350, safe_top: 60, safe_bottom: 96, safe_left: 40, safe_right: 48 });
    expect(doc.formato.safe_left).toBe(40);
    expect(doc.formato.safe_right).toBe(48);
    // Retrocompat: un formato sin laterales no los inventa (quedan undefined => 0 al consumirse).
    const doc2 = documentoVacio({ w: 1080, h: 1080, safe_top: 60, safe_bottom: 96 });
    expect(doc2.formato.safe_left).toBeUndefined();
    expect(doc2.formato.safe_right).toBeUndefined();
  });
});
