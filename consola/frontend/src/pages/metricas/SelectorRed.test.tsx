/**
 * Tests del selector de red único: refleja `vistaConfig.red` y, al elegir una red,
 * la escribe en el store (que filtra toda la página). "Todas las redes" la deja en `null`.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { etiquetaRed, SelectorRed } from "./SelectorRed";
import { useVistaConfig } from "./vistaConfig";

beforeEach(() => {
  useVistaConfig.getState().reset();
});

describe("etiquetaRed", () => {
  it("traduce el id de red y rotula 'Todas las redes' cuando es null", () => {
    expect(etiquetaRed(null)).toBe("Todas las redes");
    expect(etiquetaRed("instagram")).toBe("Instagram");
    expect(etiquetaRed("youtube")).toBe("YouTube");
  });
});

describe("SelectorRed", () => {
  it("arranca en 'Todas las redes' (red = null)", () => {
    render(<SelectorRed />);
    expect(screen.getByLabelText("Red")).toHaveTextContent("Todas las redes");
    expect(useVistaConfig.getState().red).toBeNull();
  });

  it("al elegir una red la escribe en el store", async () => {
    render(<SelectorRed />);

    // Radix abre con Enter/Espacio y selecciona el item con Enter (jsdom no emite pointerup).
    fireEvent.keyDown(screen.getByLabelText("Red"), { key: "Enter" });
    const instagram = await screen.findByRole("option", { name: /Instagram/ });
    fireEvent.keyDown(instagram, { key: "Enter" });

    expect(useVistaConfig.getState().red).toBe("instagram");
  });

  it("'Todas las redes' vuelve a dejar la red en null", async () => {
    useVistaConfig.getState().setRed("tiktok");
    render(<SelectorRed />);

    fireEvent.keyDown(screen.getByLabelText("Red"), { key: "Enter" });
    const todas = await screen.findByRole("option", { name: "Todas las redes" });
    fireEvent.keyDown(todas, { key: "Enter" });

    expect(useVistaConfig.getState().red).toBeNull();
  });
});
