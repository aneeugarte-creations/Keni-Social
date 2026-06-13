import { describe, expect, it } from "vitest";

import { altoVisual, bandaOverlay, cajaVisual, documentoVacio, nuevaCapaMarco, nuevaCapaOverlay, nuevaCapaTexto } from "./documento";

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

describe("cajaVisual / bandaOverlay / altoVisual", () => {
  it("bandaOverlay espeja EXACTAMENTE al export (max(1, floor(h*alto_frac)))", () => {
    const ov = nuevaCapaOverlay({ h: 1350, alto_frac: 0.45 });
    // 1350*0.45 = 607.5 -> el export hace floor: 607 (el editor antes medía 607.5).
    expect(bandaOverlay(ov)).toBe(607);
    // Degenerados: nunca menos de 1px, como dibujarOverlayInferior.
    expect(bandaOverlay(nuevaCapaOverlay({ h: 100, alto_frac: 0 }))).toBe(1);
  });

  it("cajaVisual del overlay es su BANDA inferior (y+h-banda), no la caja del modelo", () => {
    const ov = nuevaCapaOverlay({ x: 0, y: -700, w: 1080, h: 1350, alto_frac: 0.45 });
    const vis = cajaVisual(ov);
    // Con el doc del bug real: la banda pinta arriba del lienzo aunque el modelo diga y=-700.
    expect(vis).toEqual({ x: 0, y: -700 + 1350 - 607, w: 1080, h: 607 });
  });

  it("cajaVisual del overlay con lado 'arriba' es su BANDA SUPERIOR (y), no la inferior", () => {
    const ov = nuevaCapaOverlay({ x: 0, y: 0, w: 1080, h: 1350, alto_frac: 0.45, lado: "arriba" });
    // Banda pegada al tope: y = la del modelo (no y+h-banda); mismo alto que la inferior.
    expect(cajaVisual(ov)).toEqual({ x: 0, y: 0, w: 1080, h: 607 });
  });

  it("cajaVisual del texto legado (h<=0) con ancla 'abajo' ancla el bloque por su borde INFERIOR", () => {
    const t = nuevaCapaTexto({ x: 80, y: 1254, w: 760, h: 0, tamano: 96, interlineado: 1.14, ancla: "abajo" });
    const alto = Math.round(96 * 1.14);
    expect(cajaVisual(t)).toEqual({ x: 80, y: 1254 - alto, w: 760, h: alto });
    // Con ancla 'arriba' (default) la y almacenada ya es el tope.
    const t2 = nuevaCapaTexto({ x: 80, y: 100, w: 760, h: 0, tamano: 96, interlineado: 1.14 });
    expect(cajaVisual(t2).y).toBe(100);
  });

  it("cajaVisual de las demás capas es su caja del modelo; altoVisual del overlay es la banda", () => {
    const m = nuevaCapaMarco({ x: 10, y: 20, w: 30, h: 40 });
    expect(cajaVisual(m)).toEqual({ x: 10, y: 20, w: 30, h: 40 });
    expect(altoVisual(nuevaCapaOverlay({ h: 1000, alto_frac: 0.5 }))).toBe(500);
  });
});
