import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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

  it("recorta el copy y alterna al pulsar TODA el área de texto (no solo el enlace)", () => {
    render(
      <VistaPreviaRed
        red="instagram"
        marca="UnoTV"
        contenido={"línea uno\nlínea dos\nlínea tres\nlínea cuatro"}
        variante="limpia"
      />,
    );
    // Toda el área de texto es el toggle (role=button con aria-expanded); muestra "más" plegado.
    const toggle = screen.getByRole("button");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByText("más")).toBeInTheDocument();
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("menos")).toBeInTheDocument();
  });

  it("plegado, los enlaces del copy salen del tab-order; al expandir con «más» vuelven", () => {
    render(
      <VistaPreviaRed
        red="instagram"
        marca="UnoTV"
        contenido={"mira https://ejemplo.mx/nota\nlínea dos\nlínea tres"}
        variante="limpia"
      />,
    );
    // Con el clamp puesto el enlace puede quedar oculto: focus ring en un punto invisible.
    const enlace = screen.getByRole("link");
    expect(enlace).toHaveAttribute("tabindex", "-1");
    // El usuario de teclado expande con el botón "más" (tabulable); los enlaces entran al foco.
    fireEvent.click(screen.getByText("más"));
    expect(enlace).not.toHaveAttribute("tabindex");
  });

  it("con onAbrir hace la IMAGEN interactiva y deja el copy aparte", () => {
    const onAbrir = vi.fn();
    render(
      <VistaPreviaRed
        red="instagram"
        marca="UnoTV"
        contenido={"línea uno\nlínea dos\nlínea tres\nlínea cuatro"}
        variante="limpia"
        onAbrir={onAbrir}
      />,
    );
    // Hay dos botones: la imagen (abrir) y el toggle del copy. Pulsar la imagen abre; el copy no.
    fireEvent.click(screen.getByRole("button", { name: "Abrir para editar" }));
    expect(onAbrir).toHaveBeenCalledTimes(1);
  });
});
