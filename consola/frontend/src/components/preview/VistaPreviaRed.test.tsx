import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { VistaPreviaRed } from "./VistaPreviaRed";

/**
 * Copy del feed estilo red social (variante "limpia"): recortado a 2 líneas con un enlace
 * "más"/"menos" cuando el texto desborda. jsdom no calcula layout, así que forzamos que el
 * párrafo "desborde" (scrollHeight > clientHeight) para ejercitar el recorte y el toggle.
 */
describe("VistaPreviaRed · copy con 'leer más' (feed limpio)", () => {
  const origScroll = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "scrollHeight");
  const origClient = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "clientHeight");

  beforeEach(() => {
    // El párrafo (recortado a 2 líneas) reporta más alto real que el visible -> hay "más".
    Object.defineProperty(HTMLElement.prototype, "scrollHeight", { configurable: true, get: () => 100 });
    Object.defineProperty(HTMLElement.prototype, "clientHeight", { configurable: true, get: () => 40 });
  });
  afterEach(() => {
    if (origScroll) Object.defineProperty(HTMLElement.prototype, "scrollHeight", origScroll);
    if (origClient) Object.defineProperty(HTMLElement.prototype, "clientHeight", origClient);
  });

  it("muestra 'más' cuando el copy desborda y alterna a 'menos' al expandir", () => {
    render(
      <VistaPreviaRed
        red="instagram"
        marca="UnoTV"
        contenido={"línea uno\nlínea dos\nlínea tres\nlínea cuatro"}
        variante="limpia"
      />,
    );
    const mas = screen.getByRole("button", { name: "más" });
    expect(mas).toBeInTheDocument();
    fireEvent.click(mas);
    expect(screen.getByRole("button", { name: "menos" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "más" })).not.toBeInTheDocument();
  });
});
