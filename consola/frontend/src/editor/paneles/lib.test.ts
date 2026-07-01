// Tests de `nombreCapa`: nombre editable tiene prioridad; los marcos SIN nombre se etiquetan por su
// FORMA (Triángulo, Estrella…) y no todos como «Marco».

import { describe, expect, it } from "vitest";

import { nuevaCapaMarco, nuevaCapaTexto } from "../documento";

import { nombreCapa } from "./lib";

describe("nombreCapa — nombre por forma", () => {
  it("un marco rectángulo sin nombre cae en «Marco»", () => {
    expect(nombreCapa(nuevaCapaMarco({ forma: "rect" }))).toBe("Marco");
  });

  it.each([
    ["triangulo", "Triángulo"],
    ["rombo", "Rombo"],
    ["pentagono", "Pentágono"],
    ["hexagono", "Hexágono"],
    ["estrella", "Estrella"],
    ["flecha", "Flecha"],
    ["elipse", "Elipse"],
    ["linea", "Línea"],
  ] as const)("un marco %s se llama «%s»", (forma, etiqueta) => {
    expect(nombreCapa(nuevaCapaMarco({ forma }))).toBe(etiqueta);
  });

  it("el nombre editable manda sobre la forma", () => {
    expect(nombreCapa(nuevaCapaMarco({ forma: "estrella", nombre: "Sello" }))).toBe("Sello");
  });

  it("un texto sin nombre usa su contenido", () => {
    expect(nombreCapa(nuevaCapaTexto({ texto: "Hola mundo" }))).toBe("Hola mundo");
  });
});
