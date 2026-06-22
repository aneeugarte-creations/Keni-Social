/**
 * Tests del selector de redes MULTI-SELECCIÓN: refleja `vistaConfig.red` (CSV de ids) y, al
 * marcar/desmarcar redes, las combina en el store (que filtra toda la página). "Todas las
 * redes" lo deja en `null`.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { etiquetaRed, SelectorRed } from "./SelectorRed";
import { useVistaConfig } from "./vistaConfig";

beforeEach(() => {
  localStorage.clear();
  useVistaConfig.getState().reset();
});

describe("etiquetaRed", () => {
  it("rotula una, varias o todas las redes", () => {
    expect(etiquetaRed(null)).toBe("Todas las redes");
    expect(etiquetaRed("instagram")).toBe("Instagram");
    expect(etiquetaRed("instagram,youtube")).toBe("Instagram + YouTube");
    expect(etiquetaRed("instagram,youtube,facebook")).toBe("3 redes");
  });
});

describe("SelectorRed", () => {
  it("arranca en 'Todas las redes' (red = null)", () => {
    render(<SelectorRed />);
    expect(screen.getByLabelText("Redes")).toHaveTextContent("Todas las redes");
    expect(useVistaConfig.getState().red).toBeNull();
  });

  it("combina varias redes a antojo (CSV en el store)", () => {
    render(<SelectorRed />);
    fireEvent.click(screen.getByLabelText("Redes"));

    fireEvent.click(screen.getByRole("menuitemcheckbox", { name: /Instagram/ }));
    expect(useVistaConfig.getState().red).toBe("instagram");

    fireEvent.click(screen.getByRole("menuitemcheckbox", { name: /YouTube/ }));
    expect(useVistaConfig.getState().red).toBe("instagram,youtube");

    // Desmarcar Instagram deja solo YouTube.
    fireEvent.click(screen.getByRole("menuitemcheckbox", { name: /Instagram/ }));
    expect(useVistaConfig.getState().red).toBe("youtube");
  });

  it("'Todas las redes' limpia la selección (null)", () => {
    useVistaConfig.getState().setRedes(["tiktok", "x"]);
    render(<SelectorRed />);
    fireEvent.click(screen.getByLabelText("Redes"));

    fireEvent.click(screen.getByRole("menuitemradio", { name: "Todas las redes" }));
    expect(useVistaConfig.getState().red).toBeNull();
  });
});
