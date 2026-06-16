import { describe, expect, it } from "vitest";

import {
  parsearCarrusel,
  serializarCarrusel,
  slidePlacaEditable,
  type SlideCarrusel,
} from "./carrusel";

describe("carrusel · parse/serialize", () => {
  it("parsea slides mínimos {tipo,objeto} (retrocompat) y descarta basura", () => {
    const json = '[{"tipo":"imagen","objeto":"a.png"},{"tipo":"video","objeto":"v.mp4"},{"objeto":""},42]';
    expect(parsearCarrusel(json)).toEqual([
      { tipo: "imagen", objeto: "a.png" },
      { tipo: "video", objeto: "v.mp4" },
    ]);
  });

  it("'' / JSON inválido / no-array -> []", () => {
    expect(parsearCarrusel("")).toEqual([]);
    expect(parsearCarrusel(null)).toEqual([]);
    expect(parsearCarrusel("{}")).toEqual([]);
    expect(parsearCarrusel("no-json")).toEqual([]);
  });

  it("adopta la PROCEDENCIA cuando viene (foto/titular/plantillaId/fotoEncuadre)", () => {
    const json =
      '[{"tipo":"imagen","objeto":"artes/x.png","foto":"fotos/o.jpg","titular":"Clave 2",' +
      '"plantillaId":"plt-1","fotoEncuadre":"{\\"foco\\":[0.5,0.5],\\"zoom\\":1}"}]';
    expect(parsearCarrusel(json)).toEqual([
      {
        tipo: "imagen",
        objeto: "artes/x.png",
        foto: "fotos/o.jpg",
        titular: "Clave 2",
        plantillaId: "plt-1",
        fotoEncuadre: '{"foco":[0.5,0.5],"zoom":1}',
      },
    ]);
  });

  it("serializa SOLO los campos de procedencia presentes (los crudos quedan {tipo,objeto})", () => {
    const slides: SlideCarrusel[] = [
      { tipo: "imagen", objeto: "crudo.png" },
      { tipo: "imagen", objeto: "artes/x.png", titular: "T", foto: "fotos/o.jpg", plantillaId: "" },
      { tipo: "imagen", objeto: "" }, // se descarta (sin objeto)
    ];
    const json = serializarCarrusel(slides);
    expect(JSON.parse(json)).toEqual([
      { tipo: "imagen", objeto: "crudo.png" },
      { tipo: "imagen", objeto: "artes/x.png", titular: "T", foto: "fotos/o.jpg" },
    ]);
  });

  it("round-trip: parse(serialize(x)) preserva la procedencia (incl. sinPlaca)", () => {
    const slides: SlideCarrusel[] = [
      { tipo: "imagen", objeto: "artes/x.png", titular: "Clave", foto: "fotos/o.jpg" },
      { tipo: "imagen", objeto: "fotos/cruda.jpg", foto: "fotos/cruda.jpg", sinPlaca: true },
    ];
    expect(parsearCarrusel(serializarCarrusel(slides))).toEqual(slides);
  });

  it("sinPlaca solo se adopta/emite cuando es true (false/ausente se omite)", () => {
    expect(parsearCarrusel('[{"tipo":"imagen","objeto":"a","sinPlaca":false}]')).toEqual([
      { tipo: "imagen", objeto: "a" },
    ]);
    const json = serializarCarrusel([{ tipo: "imagen", objeto: "a", sinPlaca: false }]);
    expect(JSON.parse(json)).toEqual([{ tipo: "imagen", objeto: "a" }]);
  });

  it("vacío -> ''", () => {
    expect(serializarCarrusel([])).toBe("");
    expect(serializarCarrusel([{ tipo: "imagen", objeto: "" }])).toBe("");
  });

  it("slidePlacaEditable: imagen con titular/foto sí; cruda o video no", () => {
    expect(slidePlacaEditable({ tipo: "imagen", objeto: "x", titular: "T" })).toBe(true);
    expect(slidePlacaEditable({ tipo: "imagen", objeto: "x", foto: "f" })).toBe(true);
    expect(slidePlacaEditable({ tipo: "imagen", objeto: "x" })).toBe(false);
    expect(slidePlacaEditable({ tipo: "video", objeto: "x", titular: "T" })).toBe(false);
  });
});
