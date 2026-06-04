import { describe, expect, it } from "vitest";

import { documentoVacio } from "./documento";

describe("documentoVacio", () => {
  it("nace con un hueco de foto a sangre, marcado y bloqueado", () => {
    const doc = documentoVacio({ w: 1080, h: 1350, safe_top: 60, safe_bottom: 96 }, "claro-sports");
    const imagenes = doc.capas.filter((c) => c.tipo === "imagen");
    expect(imagenes).toHaveLength(1);
    const hueco = imagenes[0];
    expect(hueco.tipo === "imagen" && hueco.es_foto).toBe(true);
    expect(hueco.bloqueada).toBe(true);
    // A sangre: cubre todo el lienzo.
    expect(hueco.w).toBe(1080);
    expect(hueco.h).toBe(1350);
  });
});
