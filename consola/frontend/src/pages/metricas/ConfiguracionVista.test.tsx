/**
 * Tests del panel "Configurar vista": refleja y muta `vistaConfig` (visibilidad de
 * secciones) y "Restablecer" vuelve al estado por defecto.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { ConfiguracionVista } from "./ConfiguracionVista";
import { useVistaConfig } from "./vistaConfig";

beforeEach(() => {
  useVistaConfig.getState().reset();
});

function abrir() {
  render(<ConfiguracionVista />);
  fireEvent.click(screen.getByRole("button", { name: "Configurar vista" }));
}

describe("ConfiguracionVista — secciones", () => {
  it("arranca con todas las secciones marcadas (visibles por defecto)", () => {
    abrir();
    expect(screen.getByRole("checkbox", { name: "Comparativa y detalle por marca" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
  });

  it("desmarcar una sección la oculta en el store", () => {
    abrir();
    fireEvent.click(screen.getByRole("checkbox", { name: "Publicidad pagada" }));
    expect(useVistaConfig.getState().seccionVisible("ads")).toBe(false);
  });

  it("'Restablecer' vuelve todo a visible", () => {
    useVistaConfig.getState().setSeccionVisible("ads", false);
    abrir();
    fireEvent.click(screen.getByRole("button", { name: /Restablecer/ }));
    expect(useVistaConfig.getState().seccionVisible("ads")).toBe(true);
  });
});
