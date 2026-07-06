import { describe, expect, it } from "vitest";

import { imagenesRotas } from "./rasterizarDeck";

/** Fabrica una `<img>` con `src` y un `naturalWidth` fijado (jsdom no carga assets). */
function img(src: string, naturalWidth: number): HTMLImageElement {
  const el = document.createElement("img");
  if (src) el.setAttribute("src", src);
  Object.defineProperty(el, "naturalWidth", { value: naturalWidth });
  return el;
}

describe("imagenesRotas (puerta dura del rasterizador)", () => {
  it("señala las imágenes con src que terminaron sin píxeles", () => {
    const rota = img("/logo.png", 0);
    const sana = img("/qr.png", 220);
    expect(imagenesRotas([rota, sana])).toEqual([rota]);
  });

  it("ignora las <img> sin src (no hay nada que cargar)", () => {
    expect(imagenesRotas([img("", 0)])).toEqual([]);
  });
});
