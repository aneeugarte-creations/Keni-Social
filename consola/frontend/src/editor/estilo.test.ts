import { describe, expect, it } from "vitest";

import { nuevaCapaImagen, nuevaCapaMarco, nuevaCapaTexto } from "./documento";
import { aplicarEstilo, estiloDe } from "./estilo";

describe("estiloDe", () => {
  it("texto: incluye estilo tipográfico pero NO texto/posición", () => {
    const t = nuevaCapaTexto({ color: "#FF0000", tamano: 80, texto: "Hola", x: 50, y: 60 });
    const e = estiloDe(t);
    expect(e.tipo).toBe("texto");
    expect(e.campos).toMatchObject({ color: "#FF0000", tamano: 80, opacidad: 1 });
    expect("texto" in e.campos).toBe(false);
    expect("x" in e.campos).toBe(false);
    expect("w" in e.campos).toBe(false);
  });

  it("texto: cursiva y subrayado son parte del estilo (si están presentes en la capa)", () => {
    const t = nuevaCapaTexto({ cursiva: true, subrayado: true });
    const e = estiloDe(t);
    expect(e.campos).toMatchObject({ cursiva: true, subrayado: true });
    // Una capa sin esos flags (opcionales) no los inyecta como `undefined`.
    const sin = estiloDe(nuevaCapaTexto());
    expect("cursiva" in sin.campos).toBe(false);
    expect("subrayado" in sin.campos).toBe(false);
  });

  it("imagen: NO copia objeto/crop/foco/zoom/es_foto", () => {
    const im = nuevaCapaImagen("media-123", {
      foco: [0.2, 0.8],
      zoom: 2,
      crop: { cx: 0.1, cy: 0.1, cw: 0.5, ch: 0.5 },
      es_foto: true,
      forma: "elipse",
    });
    const e = estiloDe(im);
    expect(e.campos).toMatchObject({ forma: "elipse", ajuste: "cover" });
    for (const prohibido of ["objeto", "crop", "foco", "zoom", "es_foto"]) {
      expect(prohibido in e.campos).toBe(false);
    }
  });

  it("clona en profundidad (no comparte referencias con la capa)", () => {
    const t = nuevaCapaTexto({ sombra: { dx: 2, dy: 2, color: "#000000" } });
    const e = estiloDe(t);
    (e.campos as { sombra?: { dx: number } }).sombra!.dx = 99;
    expect(t.sombra?.dx).toBe(2);
  });
});

describe("aplicarEstilo", () => {
  it("entre el mismo tipo aplica todos los campos de estilo", () => {
    const origen = estiloDe(nuevaCapaTexto({ color: "#00FF00", tamano: 120 }));
    const destino = nuevaCapaTexto({ color: "#FFFFFF", tamano: 40 });
    const cambios = aplicarEstilo(destino, origen);
    expect(cambios).toMatchObject({ color: "#00FF00", tamano: 120 });
  });

  it("estilo de texto sobre un marco solo pega lo común (opacidad/mezcla)", () => {
    const origen = estiloDe(nuevaCapaTexto({ color: "#00FF00", opacidad: 0.5, mezcla: "multiplicar" }));
    const marco = nuevaCapaMarco();
    const cambios = aplicarEstilo(marco, origen) as Record<string, unknown>;
    expect(cambios.opacidad).toBe(0.5);
    expect(cambios.mezcla).toBe("multiplicar");
    expect("color" in cambios).toBe(false);
    expect("tamano" in cambios).toBe(false);
    expect("familia" in cambios).toBe(false);
  });

  it("marco -> imagen comparte forma/radio/sombra además de lo común", () => {
    const origen = estiloDe(nuevaCapaMarco({ forma: "hexagono", radio: 24, opacidad: 0.7 }));
    const img = nuevaCapaImagen("x");
    const cambios = aplicarEstilo(img, origen) as Record<string, unknown>;
    expect(cambios.forma).toBe("hexagono");
    expect(cambios.radio).toBe(24);
    expect(cambios.opacidad).toBe(0.7);
    // El marco no tiene `relleno` compatible con imagen: no debe colarse.
    expect("relleno" in cambios).toBe(false);
  });
});
